#!/usr/bin/env python3
"""Build the environment of a dry run: the archive's pinned packages plus a release candidate.

A dry run checks the archive against a release candidate of spectrafit-core before the
release exists on PyPI. The candidate comes from a package index that is named only for
this run, in the environment of the process that runs this script; it never enters
``pyproject.toml`` or ``uv.lock`` (``tests/test_dry_run_isolation.py`` fails if it does).

Steps:

1. ``uv venv`` at ``--venv`` (outside this repository) with the Python of ``uv.lock``;
2. every package of ``uv.lock`` except spectrafit-core, exactly as locked (``uv export --locked``,
   installed with ``--no-deps``), for the dependency groups named with ``--group``;
3. ``spectrafit-core==$SPECTRAFIT_RC_VERSION`` from the index ``$SPECTRAFIT_RC_INDEX``, installed with
   ``--no-deps --require-hashes`` against ``$SPECTRAFIT_RC_SHA256``, so a wheel with another digest is
   refused before it is installed;
4. ``uv pip check`` and a comparison of the candidate's declared requirements (with the extras the
   groups request) against what is installed;
5. a record (``--record``): interpreter, packages, wheel SHA-256 and tag, SHA-256 of the
   installed compiled extension, index host, and every requirement the lock does not satisfy.

Environment of the run (none of it is written to the record except the index host):

* ``SPECTRAFIT_RC_INDEX``: simple-index URL without credentials;
* ``SPECTRAFIT_RC_VERSION``: the candidate, e.g. ``0.1.3rc2``;
* ``SPECTRAFIT_RC_SHA256``: SHA-256 of its wheel;
* ``UV_INDEX_RC_USERNAME`` / ``UV_INDEX_RC_PASSWORD``: credentials uv sends to that index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent.parent
PACKAGE = "spectrafit-core"
GROUP_EXTRAS = {"benchmark": {"benchmark", "jax"}}


def sh(cmd: list[str], **kw) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"FAILED ({proc.returncode}): {' '.join(cmd)}")
    return proc.stdout


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set; a dry run names its index, version and wheel digest at run time")
    return value


def probe(python: Path) -> dict:
    """Versions and the compiled extension, read by the environment's own interpreter."""
    code = r"""
import hashlib, importlib.metadata as md, json, pathlib, platform, sys
import spectrafit_core
pkg = pathlib.Path(spectrafit_core.__file__).parent
core = sorted(pkg.glob("_core*.so")) + sorted(pkg.glob("_core*.pyd"))
dist = md.distribution("spectrafit-core")
print(json.dumps({
    "python": platform.python_version(), "executable": sys.executable,
    "spectrafit_core_version": spectrafit_core.__version__, "spectrafit_core_file": spectrafit_core.__file__,
    "core_extension": core[0].name if core else None,
    "core_extension_sha256": hashlib.sha256(core[0].read_bytes()).hexdigest() if core else None,
    "requires_dist": dist.requires or [],
    "wheel_tags": [ln.split(":", 1)[1].strip() for ln in (dist.read_text("WHEEL") or "").splitlines()
                   if ln.startswith("Tag:")],
    "packages": {d.metadata["Name"].lower(): d.version for d in md.distributions()},
}))
"""
    return json.loads(sh([str(python), "-I", "-c", code]))


def unmet(requires: list[str], extras: set[str], installed: dict[str, str]) -> list[str]:
    """Requirements of the candidate (base and requested extras) whose package is not installed."""
    missing = []
    for req in requires:
        name = re.split(r"[ ;<>=!~\[(]", req, maxsplit=1)[0].lower().replace("_", "-")
        marker = req.split(";", 1)[1] if ";" in req else ""
        wanted = re.findall(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
        if wanted and not set(wanted) & extras:
            continue
        if name not in installed:
            missing.append(req)
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", type=Path, required=True, help="environment to create (outside this repository)")
    ap.add_argument("--group", action="append", default=[], help="dependency group of pyproject.toml to add")
    ap.add_argument("--record", type=Path, required=True, help="JSON record of the environment")
    args = ap.parse_args()

    index = required_env("SPECTRAFIT_RC_INDEX")
    version = required_env("SPECTRAFIT_RC_VERSION")
    digest = required_env("SPECTRAFIT_RC_SHA256").lower()
    if "@" in urlsplit(index).netloc:
        raise SystemExit("SPECTRAFIT_RC_INDEX carries credentials; pass them as UV_INDEX_RC_USERNAME/PASSWORD")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit("SPECTRAFIT_RC_SHA256 is not a SHA-256 hex digest")
    venv = args.venv.resolve()
    if venv.is_relative_to(HERE):
        raise SystemExit(f"{venv} lies inside this repository; a dry-run environment lives outside it")
    if venv.exists():
        raise SystemExit(f"{venv} exists; a dry run starts from a new environment")

    python = venv / "bin" / "python"
    sh(["uv", "venv", "--quiet", "--python", "3.13", str(venv)], cwd=HERE)
    groups = [a for g in args.group for a in ("--group", g)]
    with tempfile.TemporaryDirectory(prefix=".dry-run-env-", dir=venv.parent) as tmp:
        locked = Path(tmp) / "locked.txt"
        sh(["uv", "export", "--locked", "--no-hashes", "--no-emit-project", "--no-emit-package", PACKAGE,
            "--no-header", "--no-annotate", *groups, "-o", str(locked)], cwd=HERE)
        sh(["uv", "pip", "install", "--quiet", "--python", str(python), "--no-deps", "-r", str(locked)], cwd=tmp)
        candidate = Path(tmp) / "candidate.txt"
        candidate.write_text(f"{PACKAGE}=={version} --hash=sha256:{digest}\n")
        sh(["uv", "pip", "install", "--quiet", "--python", str(python), "--no-deps", "--require-hashes",
            "--index", f"rc={index}", "--index-strategy", "first-index", "-r", str(candidate)], cwd=tmp)
        locked_lines = sorted(ln for ln in locked.read_text().splitlines() if ln and not ln.startswith("#"))
    check = subprocess.run(["uv", "pip", "check", "--python", str(python)], capture_output=True, text=True,
                           check=False)
    env = probe(python)
    if env["spectrafit_core_version"] != version:
        raise SystemExit(f"installed spectrafit-core is {env['spectrafit_core_version']}, expected {version}")
    if not Path(env["spectrafit_core_file"]).resolve().is_relative_to(venv):
        raise SystemExit(f"spectrafit_core resolves to {env['spectrafit_core_file']}, outside {venv}")
    extras = set().union(*(GROUP_EXTRAS.get(g, set()) for g in args.group)) if args.group else set()
    # Read from the installed wheel's WHEEL file (one wheel can carry several tags).
    tag = ", ".join(env["wheel_tags"]) or None
    record = {
        "schema": "dry-run-environment/1",
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": {"node": platform.node(), "platform": platform.platform(), "machine": platform.machine()},
        "venv": str(venv),
        "uv": sh(["uv", "--version"]).strip(),
        "uv_lock_sha256": hashlib.sha256((HERE / "uv.lock").read_bytes()).hexdigest(),
        "groups": args.group,
        "index_host": urlsplit(index).netloc,
        "candidate": {"name": PACKAGE, "version": version, "wheel_sha256": digest,
                      "wheel_tag": tag, "verified_by": "uv pip install --require-hashes"},
        "interpreter": {"python": env["python"], "executable": env["executable"]},
        "core_extension": env["core_extension"], "core_extension_sha256": env["core_extension_sha256"],
        "locked_requirements": locked_lines,
        "candidate_requirements": env["requires_dist"],
        "candidate_requirements_not_installed": unmet(env["requires_dist"], extras, env["packages"]),
        "pip_check": {"exit_code": check.returncode, "output": (check.stdout + check.stderr).strip()},
        "packages": dict(sorted(env["packages"].items())),
    }
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(record, indent=1) + "\n")
    print(f"dry-run environment {venv}: spectrafit-core {version}, wheel sha256 {digest[:12]}..., "
          f"_core sha256 {env['core_extension_sha256'][:12]}..., pip check exit {check.returncode}, "
          f"unmet {record['candidate_requirements_not_installed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
