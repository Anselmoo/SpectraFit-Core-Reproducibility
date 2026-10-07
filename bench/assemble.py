#!/usr/bin/env python3
"""Turn a finished timing chain (bench/run_timing.sh) into results/timing/.

Two subcommands:

``capture <run-root>``
    Called by the chain before the first rung. Records, from the measuring interpreter
    and the export it runs, what the archived ``bench-ladder/2`` records carried and the
    release's ``scripts/bench_ladder.py`` no longer records: the host fields of 0fd4b5d's
    ``environment()`` (thread variables, CPU flags, cgroup limits, container, CI), the
    numpy BLAS, and the run configuration of 0fd4b5d's ``_probe_run_config()`` (catalogue
    fingerprint, backend support, r2 ceiling tolerance, Python build). Written to
    ``<run-root>/capture.json``.

``build <run-root> <out>``
    Writes the schema-2 documents the archive has, from what the chain produced:
    ``ladder/ladder.json`` (``bench-ladder/2``), ``seed-sweep/sweep.json``
    (``bench-seed-sweep/1``), one ``bench-provenance/2`` record per rung and per seed,
    the run directories' ``manifest.json`` and ``trust.json``, their ``results.json`` and
    ``audit.json`` gzipped without timestamps (``gzip -n`` equivalent), the three derived
    files, the host snapshots and a run-level ``provenance.json``. Then checks the result
    against the archived files of the release (same key paths) and against itself.

Fields the release cannot supply are written as null and listed in ``NULL_FIELDS``;
nothing is copied from the archived 151-case records.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

COMMIT = "1e304188a7376caf128fcb432a16554ed44ad32a"
TAG = "v0.1.2"
W = Path(__file__).resolve().parent.parent
SCHEMA_RUNG = "spectrafit-core/bench-provenance/2"
SCHEMA_LADDER = "spectrafit-core/bench-ladder/2"
SCHEMA_SWEEP = "spectrafit-core/bench-seed-sweep/1"
LADDER_REPS = (4, 10, 20, 50, 100)
THREAD_ENV_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                   "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "RAYON_NUM_THREADS",
                   "XLA_FLAGS", "JAX_PLATFORMS", "SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET")
GZIP_PAYLOADS = ("results.json", "audit.json")
KEEP_RAW = ("manifest.json", "trust.json")
# Present in the archived records, not obtainable from spectrafit-core 0.1.2:
# Backend.solver_settings() was removed in 0.1.2, so the per-backend solver description
# the archive carries under config.solvers has no source in the release.
NULL_FIELDS = {
    "config.solvers.<backend>.library": "Backend.solver_settings() removed in 0.1.2",
    "config.solvers.<backend>.algorithm": "Backend.solver_settings() removed in 0.1.2",
    "config.solvers.<backend>.bounds": "Backend.solver_settings() removed in 0.1.2",
    "config.solvers.<backend>.stopping": "Backend.solver_settings() removed in 0.1.2",
    "config.solvers.<backend>.runtime": "Backend.solver_settings() removed in 0.1.2",
}
SOLVER_PACKAGE = {"spectrafit": "spectrafit-core", "lmfit": "lmfit", "jax": "optimistix",
                  "scipy-ls-lm": "scipy", "scipy-ls-trf": "scipy", "scipy-ls-dogbox": "scipy"}

# Verbatim from 0fd4b5d scripts/bench_ladder.py methodology(); every sentence checked
# against the v0.1.2 harness (engine.py suite/analyzed reps, _base.py warm-up and timing
# loop, _engine_profile.py default_rng(1000 + k), _lmfit.py DE seed 0, _jax.py budget).
METHODOLOGY = {
    "timing": {
        "clock": "time.perf_counter (monotonic)",
        "unit": "milliseconds",
        "timed_region": "Backend.run only — model construction and result serialization are outside the timer",
        "warmup": "one untimed solve per (case, backend) before the timed reps",
        "reps_semantics": "the suite phase runs max(1, reps // 2) timed solves; the analyzed phase runs "
                          "the full reps. Both are recorded per rung as reps_effective and reps_requested",
        "aggregate": "median of the per-rep timings",
    },
    "accuracy": {
        "primary": "r^2 of the fit against the noisy data",
        "gate": "max |delta r^2| between spectrafit and the baseline solver",
        "recovered": "a solve counts as recovered when its r^2 is within r2_ceiling_tol of the "
                     "noiseless-truth curve's r^2 against the same noisy data — the best any solver "
                     "can reach on that case",
        "reduced_chi2_dof": "n - n_free, reported per backend as fit_dof",
        "information_criteria": "Gaussian log-likelihood AIC/BIC (N*ln(chi2/N) + 2k / + k*ln(N)), "
                                "matched across backends",
        "param_recovery": "max relative shape-parameter error vs planted truth, components matched by graph index",
    },
    "determinism": {
        "catalog_seed": 20260603,
        "noise": "numpy default_rng, seeded per Monte-Carlo draw (1000 + k)",
        "stochastic_solvers": "lmfit differential_evolution is seeded (seed=0)",
        "known_nondeterminism": "wall-clock timings; jax compile scheduling",
    },
    "comparability_caveats": [
        "solver stopping tolerances are NOT normalized across backends — each runs at its own library "
        "default, recorded per backend under config.solvers",
        "jax's compiled-executable cache is bounded (see oracles.backends._jax), so its cold-time column "
        "reflects a partly cold cache; this removes a cross-case compile-reuse advantage the other "
        "backends never had",
        "backends do not all support every case (see config.backend_support), so an aggregate is not "
        "over an identical case set for every backend",
    ],
}

# 0fd4b5d _probe_run_config(), without b.solver_settings() (absent in 0.1.2).
PROBE = """
import hashlib, json, platform
import numpy as np
from oracles.backends import get_backends
from oracles.cases import build_catalog
from oracles.backends._jax import _R2_CEILING_TOL

cat = build_catalog()
finger = [
    [c.id, int(np.asarray(c.x).size), float(c.spec.noise),
     [comp.model for comp in c.comp_true]]
    for c in cat
]
digest = hashlib.sha256(json.dumps(finger, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
backends = get_backends()
try:
    blas = np.__config__.CONFIG.get("Build Dependencies", {}).get("blas", {})
except Exception:
    blas = {}
print("@@CONFIG@@" + json.dumps({
    "catalog": {"n_cases": len(cat), "fingerprint_sha256": digest,
                "n_points_distinct": sorted({int(np.asarray(c.x).size) for c in cat})},
    "backends": [b.name for b in backends],
    "backend_support": {b.name: sum(1 for c in cat if b.is_supported(c)) for b in backends},
    "r2_ceiling_tol": _R2_CEILING_TOL,
    "python_build": list(platform.python_build()),
    "blas": {k: blas.get(k) for k in ("name", "version")},
}))
"""


# --------------------------------------------------------------------------- helpers


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def gzip_n(src: Path, dest: Path) -> None:
    """gzip without file name or timestamp, so the same input always hashes the same."""
    with src.open("rb") as fi, dest.open("wb") as raw, \
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as fo:
        shutil.copyfileobj(fi, fo, 1 << 20)


def seconds(a: str, b: str) -> float:
    f = "%Y-%m-%dT%H:%M:%SZ"
    return round((datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds(), 1)


def key_paths(node: object, prefix: str = "") -> set[str]:
    """Every key path in a JSON document; list items and per-name maps collapse to one."""
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            k = "<name>" if prefix.endswith(("solvers", "backend_support", "packages", "thread_env")) else k
            p = f"{prefix}.{k}" if prefix else k
            out.add(p)
            out |= key_paths(v, p)
    elif isinstance(node, list):
        for v in node:
            out |= key_paths(v, prefix + "[]")
    return out


# --------------------------------------------------------------------------- capture


def cpu_flags() -> list[str]:  # 0fd4b5d _cpu_flags
    interesting = ("avx", "avx2", "avx512f", "avx512dq", "avx512vl", "fma", "sse4_2")
    for line in (read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("flags"):
            present = set(line.split(":", 1)[1].split())
            return [f for f in interesting if f in present]
    return []


def cpu_quota() -> float | None:  # 0fd4b5d _cpu_quota
    if (v2 := read("/sys/fs/cgroup/cpu.max")) and not v2.startswith("max"):
        quota, _, period = v2.partition(" ")
        try:
            return round(int(quota) / int(period), 2)
        except (ValueError, ZeroDivisionError):
            return None
    quota, period = read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"), read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and not quota.startswith("-1"):
        try:
            return round(int(quota) / int(period), 2)
        except (ValueError, ZeroDivisionError):
            return None
    return None


def memory_max_gb() -> float | None:  # 0fd4b5d _memory_max_gb
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        raw = read(path)
        if raw and not raw.startswith("max"):
            try:
                value = int(raw)
            except ValueError:
                continue
            if value < 1 << 62:
                return round(value / 1024**3, 1)
    return None


def container() -> str | None:  # 0fd4b5d _container
    for var in ("CI_JOB_IMAGE", "DOCKER_IMAGE", "IMAGE_TAG"):
        if image := os.environ.get(var):
            return image
    if Path("/.dockerenv").exists():
        return "docker (image tag not exported to the job environment)"
    if Path("/run/.containerenv").exists():
        return "podman (image tag not exported to the job environment)"
    return None


def ci() -> str | None:  # 0fd4b5d _ci
    if os.environ.get("GITLAB_CI"):
        return f"gitlab-ci runner={os.environ.get('CI_RUNNER_DESCRIPTION') or os.environ.get('CI_RUNNER_ID') or '?'}"
    if os.environ.get("GITHUB_ACTIONS"):
        return f"github-actions runner={os.environ.get('RUNNER_NAME', '?')}"
    if os.environ.get("CI"):
        return "unidentified CI (CI=true)"
    return None


def capture(root: Path) -> int:
    src = root / "src"
    env = {**os.environ, "PYTHONPATH": str(src / "python")}
    proc = subprocess.run([sys.executable, "-c", PROBE], cwd=src, env=env,
                          capture_output=True, text=True, timeout=900, check=False)
    probe = next((json.loads(ln.removeprefix("@@CONFIG@@")) for ln in proc.stdout.splitlines()
                  if ln.startswith("@@CONFIG@@")), None)
    if probe is None:
        sys.stderr.write(proc.stdout + proc.stderr)
        return 1
    mhz = read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    out = {
        "captured_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.executable,
        "host_extra": {
            "thread_env": {k: os.environ.get(k) for k in THREAD_ENV_KEYS},
            "cpu_flags": cpu_flags(),
            "cpu_max_mhz": float(mhz) if mhz and mhz.isdigit() else None,
            "cpu_governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
            "cpu_quota": cpu_quota(),
            "memory_max_gb": memory_max_gb(),
            "container": container(),
            "ci": ci(),
        },
        "probe": probe,
        "uv_lock_sha256": sha256(W / "uv.lock"),
        "export_files_sha256": {str(p.relative_to(src)): sha256(p) for p in sorted(src.rglob("*"))
                                if p.is_file() and ".spectrafit_reports" not in p.parts
                                and "__pycache__" not in p.parts},
    }
    dump(root / "capture.json", out)
    print(f"capture: {probe['catalog']['n_cases']} cases, fingerprint {probe['catalog']['fingerprint_sha256'][:12]}")
    return 0


# --------------------------------------------------------------------------- build


def environment(raw_env: dict, cap: dict) -> dict:
    """Schema-2 environment: the release driver's own record plus what capture() added."""
    host = dict(raw_env["host"]) | cap["host_extra"]
    versions = dict(raw_env["versions"])
    return {
        # The export has no .git, so bench_ladder.py recorded an empty commit. The commit
        # is the one the export was made from with `git archive` (pins.toml).
        "git": {"commit": COMMIT, "branch": f"tag {TAG} (git archive export)", "dirty": False},
        "host": host,
        "versions": {
            "python": versions["python"],
            "rustc": versions["rustc"],
            "packages": {k: v for k, v in versions.items() if k not in ("python", "rustc")},
            "uv_lock_sha256": cap["uv_lock_sha256"],
            "blas": cap["probe"]["blas"],
        },
    }


def config(cap: dict, packages: dict) -> dict:
    probe = cap["probe"]
    return {
        "catalog": probe["catalog"],
        "solvers": {b: {"library": None, "algorithm": None, "bounds": None,
                        "version": packages.get(SOLVER_PACKAGE.get(b, b)), "stopping": None, "runtime": None}
                    for b in probe["backends"]},
        "backend_support": probe["backend_support"],
        "r2_ceiling_tol": probe["r2_ceiling_tol"],
        "python_build": probe["python_build"],
    }


def copy_run(run: Path, dest: Path) -> list[dict]:
    """manifest/trust as they are, results/audit gzipped; artifacts digest the originals."""
    dest.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for p in sorted(run.iterdir()):
        if not p.is_file():
            continue
        artifacts.append({"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)})
        if p.name in KEEP_RAW:
            shutil.copyfile(p, dest / p.name)
        elif p.name in GZIP_PAYLOADS:
            gzip_n(p, dest / f"{p.name}.gz")
        else:
            raise SystemExit(f"unexpected file in run dir: {p}")
    return artifacts


def record(point: dict, artifacts: list[dict], env: dict, cfg: dict, headline: dict) -> dict:
    return {
        "schema_version": SCHEMA_RUNG,
        "run_uid": point["run_uid"],
        "capture": "live",
        "params": point["params"],
        "timing": point["timing"],
        "exit_status": point["exit_status"],
        "local_run_dir": point["local_run_dir"],
        "resources": point["resources"],
        "headline": headline,
        "artifacts": artifacts,
        "environment": env,
        "methodology": METHODOLOGY,
        "config": cfg,
    }


def summary(rec: dict, with_seed: bool) -> dict:
    row = {"run_uid": rec["run_uid"], "reps_requested": rec["params"]["reps_requested"],
           "reps_effective": rec["params"]["reps_effective"]}
    if with_seed:
        row["seed"] = rec["params"]["seed"]
    return row | {"exit_status": rec["exit_status"], **rec["timing"],
                  "resources": rec["resources"], "headline": rec["headline"]}


def build(root: Path, out: Path, partial: bool) -> int:
    cap = load(root / "capture.json")
    steps = {s["step"]: s for s in map(json.loads, (root / "steps.jsonl").read_text().splitlines())} \
        if (root / "steps.jsonl").exists() else {}
    problems: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    ladder_rungs, sweep_rungs = [], []
    env = cfg = None

    # ---- ladder: one invocation of the release's bench_ladder.py per depth
    for i, reps in enumerate(LADDER_REPS, start=1):
        eff = max(1, reps // 2)
        d = root / "ladder" / f"r{reps:03d}" / f"rung_{eff:03d}"
        if not (d / "provenance.json").exists():
            if partial:
                continue
            raise SystemExit(f"missing {d}/provenance.json")
        raw = load(d / "provenance.json")
        if env is None:
            env = environment({k: raw[k] for k in ("host", "versions")}, cap)
            cfg = config(cap, env["versions"]["packages"])
        manifest = load(d / "run" / "manifest.json")
        headline = {k: manifest.get(k) for k in (
            "geomean_speedup_vs_baseline", "harmonic_mean_speedup_vs_baseline", "max_abs_delta_r2",
            "spectrafit_win_rate", "n_cases", "regressions", "backends", "saturated_categories",
            "baseline_solver_id")}
        for k, v in raw["headline"].items():
            if headline.get(k) != v:
                problems.append(f"rung {reps}: headline {k} {raw['headline'][k]} != manifest {headline.get(k)}")
        step = steps.get(i, {})
        point = {
            "run_uid": raw["run_uid"],
            "params": raw["params"] | {"catalog_fingerprint_sha256": cap["probe"]["catalog"]["fingerprint_sha256"],
                                       "headline_only": False},
            "timing": raw["timing"] | {"wall_seconds": seconds(raw["timing"]["started_utc"],
                                                               raw["timing"]["finished_utc"])},
            "exit_status": raw["exit_status"],
            "local_run_dir": raw["local_run_dir"],
            # load averages: the chain's own reading at the start and end of this step
            "resources": raw["resources"] | {"load_average_start": step.get("load_start"),
                                             "load_average_end": step.get("load_end")},
        }
        dest = out / "ladder" / "rungs" / f"rung_{eff:03d}"
        artifacts = copy_run(d / "run", dest)
        shutil.copyfile(d / "run.log", dest / "run.log")
        rec = record(point, artifacts, env, cfg, headline)
        dump(dest / "provenance.json", rec)
        ladder_rungs.append(summary(rec, with_seed=False))

    # ---- seed sweep: bench/seed_sweep.py
    seed_dirs = sorted((root / "seed-sweep").glob("seed_*")) if (root / "seed-sweep").is_dir() else []
    for d in seed_dirs:
        point = load(d / "point.json")
        if env is None:  # sweep-only (smoke) build: take host/versions from the ladder rung of capture
            raise SystemExit("seed sweep needs a ladder rung for the environment record")
        manifest = load(d / "run" / "manifest.json")
        for k, v in point["headline"].items():
            if manifest.get(k) != v:
                problems.append(f"{d.name}: headline {k} != manifest")
        dest = out / "seed-sweep" / "rungs" / d.name
        artifacts = copy_run(d / "run", dest)
        if artifacts != point["artifacts"]:
            problems.append(f"{d.name}: run files changed since the point was recorded")
        shutil.copyfile(d / "run.log", dest / "run.log")
        rec = record(point, artifacts, env, cfg, point["headline"])
        dump(dest / "provenance.json", rec)
        sweep_rungs.append(summary(rec, with_seed=True))

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if ladder_rungs:
        dump(out / "ladder" / "ladder.json", {"schema_version": SCHEMA_LADDER, "generated_utc": now,
                                              "environment": env, "methodology": METHODOLOGY,
                                              "config": cfg, "rungs": ladder_rungs})
    if sweep_rungs:
        dump(out / "seed-sweep" / "sweep.json", {"schema_version": SCHEMA_SWEEP, "generated_utc": now,
                                                 "environment": env, "methodology": METHODOLOGY,
                                                 "config": cfg, "rungs": sweep_rungs})

    # ---- derived files and host snapshots
    figs = root / "post" / "reproducibility" / "figures"
    for name in ("bench_summary.json", "param_agreement.json", "audit_bias.json"):
        if (figs / name).exists():
            shutil.copyfile(figs / name, out / name)
        elif not partial:
            raise SystemExit(f"missing {figs / name}")
    for label in ("before", "after"):
        if (root / f"host-{label}.txt").exists():
            (out / "host").mkdir(exist_ok=True)
            shutil.copyfile(root / f"host-{label}.txt", out / "host" / f"{label}.txt")

    # ---- run-level provenance
    dump(out / "provenance.json", {
        "what": "timing benchmark of spectrafit-core 0.1.2 (PyPI wheel) with the v0.1.2 harness, on terra",
        "source": {"repository": "https://github.com/Anselmoo/SpectraFit-Core.git", "tag": TAG, "commit": COMMIT,
                   "export": "git archive of the commit: scripts/bench_ladder.py python/oracles reproducibility "
                             "tests/parity crates Cargo.toml; python/ holds only oracles, so the wheel is imported",
                   "export_files_sha256": cap["export_files_sha256"]},
        "uv_lock_sha256": cap["uv_lock_sha256"],
        "drivers_sha256": {f"bench/{p.name}": sha256(p) for p in sorted((W / "bench").iterdir())
                           if p.is_file() and p.suffix in {".py", ".sh"}},
        "chain_steps": [steps[k] for k in sorted(steps)],
        "capture": {k: cap[k] for k in ("captured_utc", "python", "host_extra")},
        "null_fields": NULL_FIELDS,
        "preflight": (root / "preflight.txt").read_text(encoding="utf-8") if (root / "preflight.txt").exists() else None,
        "assembled_utc": now,
    })

    # ---- checks
    archive = root / "src" / "reproducibility"
    allowed_extra = {"rungs[].resources", "params.catalog_fingerprint_sha256"}
    pairs = [(out / "ladder" / "ladder.json", archive / "ladder" / "ladder.json"),
             (out / "seed-sweep" / "sweep.json", archive / "seed-sweep" / "sweep.json")]
    pairs += [(p, archive / "ladder" / "rungs" / "rung_002" / "provenance.json")
              for p in sorted((out / "ladder" / "rungs").glob("*/provenance.json"))]
    pairs += [(p, archive / "seed-sweep" / "rungs" / "seed_20260603" / "provenance.json")
              for p in sorted((out / "seed-sweep" / "rungs").glob("*/provenance.json"))]
    for new, old in pairs:
        if not new.exists():
            continue
        a, b = key_paths(load(new)), key_paths(load(old))
        # Sub-keys of a documented null field (NULL_FIELDS) are absent by construction.
        missing = sorted(p for p in b - a if not p.startswith(
            ("config.solvers.<name>.stopping.", "config.solvers.<name>.runtime.")))
        extra = sorted(p for p in a - b if not any(p.endswith(x) for x in allowed_extra))
        if missing or extra:
            problems.append(f"{new.relative_to(out)}: keys missing {missing} extra {extra}")
    for rec_path in sorted(out.glob("*/rungs/*/provenance.json")):
        rec = load(rec_path)
        if rec["exit_status"] != 0:
            problems.append(f"{rec_path.parent.name}: exit {rec['exit_status']}")
        if rec["headline"].get("n_cases") != 160 and not partial:
            problems.append(f"{rec_path.parent.name}: n_cases {rec['headline'].get('n_cases')}")
        if rec["resources"].get("jax_compile_budget") != 64:
            problems.append(f"{rec_path.parent.name}: jax_compile_budget {rec['resources'].get('jax_compile_budget')}")
    if (out / "bench_summary.json").exists() and ladder_rungs:
        bs = load(out / "bench_summary.json")
        rungs_dir = out / "ladder" / "rungs"
        deepest_dir = rungs_dir / "rung_050" if not partial else max(rungs_dir.glob("rung_*"))
        deepest = load(deepest_dir / "provenance.json")
        if bs["n_cases"] != 160 or bs["manifest"]["run_id"] != deepest["local_run_dir"]:
            problems.append(f"bench_summary: n_cases {bs['n_cases']}, run_id {bs['manifest']['run_id']}, "
                            f"deepest rung {deepest['local_run_dir']}")
    for p in problems:
        print("PROBLEM", p)
    print(f"assembled {len(ladder_rungs)} rungs, {len(sweep_rungs)} seeds into {out}; "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("root", type=Path)
    b = sub.add_parser("build")
    b.add_argument("root", type=Path)
    b.add_argument("out", type=Path)
    b.add_argument("--partial", action="store_true", help="smoke test: allow missing rungs and files")
    args = ap.parse_args()
    if args.cmd == "capture":
        return capture(args.root.resolve())
    return build(args.root.resolve(), args.out.resolve(), args.partial)


if __name__ == "__main__":
    raise SystemExit(main())
