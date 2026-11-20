"""What every output of the harness records about the run that produced it.

Each target of ``reproduce.py`` writes its files into one folder and, next to them, a
``README.md`` and a ``run.json`` with: the command, start and end time (UTC), wall time,
the load average before and after, the host, the Python, the spectrafit-core version, the
SHA-256 of its wheel and of the installed compiled extension, and the SHA-256 of every
file the target wrote.

The wheel SHA-256 is the one the run was installed with: in a dry run the digest that
``scripts/dry_run_env.py`` verified (``SPECTRAFIT_RC_SHA256``); otherwise the digest that
``uv.lock`` records for the installed wheel's file name.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import os
import platform
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "RAYON_NUM_THREADS")


def thread_setting() -> str:
    """``library-defaults`` (no thread variable set), ``caps-1`` (all four set to 1) or ``mixed``."""
    values = [os.environ.get(k) for k in THREAD_VARS]
    if all(v is None for v in values):
        return "library-defaults"
    return "caps-1" if all(v == "1" for v in values) else "mixed"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> list[float] | None:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except OSError:
        return None


def core_extension() -> dict:
    import spectrafit_core

    pkg = Path(spectrafit_core.__file__).parent
    found = sorted(pkg.glob("_core*.so")) + sorted(pkg.glob("_core*.pyd"))
    return {"file": found[0].name, "sha256": sha256(found[0])} if found else {"file": None, "sha256": None}


def locked_wheel_sha256(version: str) -> str | None:
    """SHA-256 that ``uv.lock`` records for the spectrafit-core wheel of this platform."""
    try:
        lock = tomllib.loads((HERE / "uv.lock").read_text())
    except OSError:
        return None
    for pkg in lock.get("package", []):
        if pkg.get("name") == "spectrafit-core" and pkg.get("version") == version:
            for wheel in pkg.get("wheels", []):
                url = wheel.get("url", "")
                if "manylinux" in url and platform.machine() in url and "cp313" in url:
                    return wheel.get("hash", "").removeprefix("sha256:")
    return None


def wheel_record() -> dict:
    """The installed spectrafit-core: version, wheel SHA-256 and compiled extension."""
    version = md.version("spectrafit-core")
    rc = os.environ.get("SPECTRAFIT_RC_VERSION")
    if rc and rc == version:
        digest, origin = os.environ.get("SPECTRAFIT_RC_SHA256"), "dry run: verified by scripts/dry_run_env.py"
    else:
        digest, origin = locked_wheel_sha256(version), "uv.lock"
    return {"version": version, "wheel_sha256": digest, "wheel_sha256_from": origin,
            "core_extension": core_extension()}


def archive_state() -> dict:
    """Commit of this repository and whether its working tree differs from it."""
    import subprocess

    def git(*args: str) -> str | None:
        proc = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(status) if status is not None else None}


def environment() -> dict:
    return {
        "archive": archive_state(),
        "host": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cores": os.cpu_count(),
        "python": platform.python_version(),
        "spectrafit_core": wheel_record(),
        "packages": {n: md.version(n) for n in ("numpy", "scipy", "lmfit", "matplotlib")},
        "threads": {k: os.environ.get(k) for k in THREAD_VARS},
        "thread_setting": thread_setting(),
    }


class Run:
    """Context manager around one target: times it and writes ``run.json`` and ``README.md``."""

    def __init__(self, out: Path, target: str, command: str, summary: str = "") -> None:
        self.out, self.target, self.command, self.summary = out, target, command, summary
        self.notes: list[str] = []

    def __enter__(self) -> Run:
        self.out.mkdir(parents=True, exist_ok=True)
        self.start, self.load_start, self.t0 = utc(), load(), time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        wall = time.perf_counter() - self.t0
        files = {p.relative_to(self.out).as_posix(): sha256(p) for p in sorted(self.out.rglob("*"))
                 if p.is_file() and p.name not in {"run.json", "README.md"}}
        record = {"schema": "harness-run/1", "target": self.target, "command": self.command,
                  "start_utc": self.start, "end_utc": utc(), "wall_s": round(wall, 1),
                  "load_start": self.load_start, "load_end": load(),
                  "status": "ok" if exc_type is None else f"failed: {exc_type.__name__}: {exc}",
                  "environment": environment(), "notes": self.notes, "files_sha256": files}
        (self.out / "run.json").write_text(json.dumps(record, indent=1) + "\n")
        w = record["environment"]["spectrafit_core"]
        lines = [f"# {self.target}", "", self.summary, "",
                 "| item | value |", "|---|---|",
                 f"| command | `{self.command}` |",
                 f"| start / end (UTC) | {record['start_utc']} / {record['end_utc']} |",
                 f"| wall time | {wall:.1f} s |",
                 f"| load average (1, 5, 15 min) before / after | {self.load_start} / {record['load_end']} |",
                 f"| host | {record['environment']['host']} ({record['environment']['platform']}, "
                 f"{record['environment']['cores']} cores) |",
                 f"| archive commit | `{record['environment']['archive']['commit']}`"
                 f"{' (working tree modified)' if record['environment']['archive']['dirty'] else ''} |",
                 f"| Python | {record['environment']['python']} |",
                 f"| spectrafit-core | {w['version']} |",
                 f"| wheel SHA-256 | `{w['wheel_sha256']}` ({w['wheel_sha256_from']}) |",
                 f"| compiled extension SHA-256 | `{w['core_extension']['sha256']}` |",
                 f"| thread caps | {record['environment']['threads']} |",
                 f"| status | {record['status']} |", ""]
        if self.notes:
            lines += ["Notes:", "", *[f"- {n}" for n in self.notes], ""]
        lines += ["Files (SHA-256):", "", *[f"- `{k}` `{v}`" for k, v in files.items()], ""]
        (self.out / "README.md").write_text("\n".join(ln for ln in lines if ln is not None) + "\n")
