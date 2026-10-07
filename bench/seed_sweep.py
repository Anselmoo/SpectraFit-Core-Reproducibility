#!/usr/bin/env python3
"""Seed sweep over the release harness: one benchmark per catalogue seed, stop on failure.

The archived 50-seed sweep was run by ``scripts/bench_ladder.py --seeds 50
--headline-only`` at spectrafit-core commit 0fd4b5d, which is not part of any release.
This is the minimal replacement for spectrafit-core 0.1.2. Per seed it does what
0fd4b5d's ``one_rung`` did:

* one child process per seed, working directory and ``PYTHONPATH`` of the export, that
  runs the release's ``cli.run`` at that seed (``bench/_seed_point.py``);
* copies the run directory the child wrote, digests its files, reads its headline;
* records the catalogue fingerprint of that seed (algorithm copied from 0fd4b5d).

Differences from 0fd4b5d, all forced by 0.1.2 not having the options it used:

* the seed and the single analysed case reach ``build_report`` through
  ``_seed_point.py`` instead of ``oracles.cli run --seed S --headline-only``;
* the per-seed record is written raw (``point.json``); ``bench/assemble.py`` turns it
  into the ``bench-provenance/2`` and ``bench-seed-sweep/1`` documents;
* the sweep stops at the first seed that exits non-zero instead of running the rest.

    python bench/seed_sweep.py --src <export> --out <dir> --commit <sha> \\
        --seed-base 20260603 --seeds 50 --reps 10 --mc 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADLINE_KEYS = (  # 0fd4b5d scripts/bench_ladder.py _HEADLINE_KEYS
    "geomean_speedup_vs_baseline", "harmonic_mean_speedup_vs_baseline", "max_abs_delta_r2",
    "spectrafit_win_rate", "n_cases", "regressions", "backends", "saturated_categories",
    "baseline_solver_id",
)
RESOURCE_KEYS = ("peak_rss_gb", "mmap_regions", "jax_cache_clears", "jax_compile_budget")
# Copied from 0fd4b5d scripts/bench_ladder.py _catalog_fingerprint, so fingerprints are
# computed the same way as in the archived sweep.
FINGERPRINT = (
    "import hashlib,json;import numpy as np;"
    "from oracles.cases import build_catalog;"
    "cat=build_catalog({seed});"
    "f=[[c.id,int(np.asarray(c.x).size),float(c.spec.noise),"
    "[k.model for k in c.comp_true]] for c in cat];"
    "print(hashlib.sha256(json.dumps(f,sort_keys=True,"
    "separators=(',',':')).encode()).hexdigest())"
)


def now() -> datetime:
    return datetime.now(UTC)


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def loadavg() -> list[float]:
    return [round(x, 2) for x in os.getloadavg()]


def parse_resources(stdout: str) -> dict:
    import re

    out: dict = {}
    for key in RESOURCE_KEYS:
        if m := re.search(rf"\b{key}=([\d.]+)\b", stdout):
            out[key] = float(m.group(1)) if key == "peak_rss_gb" else int(m.group(1))
    return out


def newest_run(reports: Path) -> str | None:
    if not reports.is_dir():
        return None
    runs = sorted(d.name for d in reports.iterdir() if d.is_dir())
    return runs[-1] if runs else None


def one_seed(seed: int, args: argparse.Namespace, env: dict) -> dict:
    reports = args.src / ".spectrafit_reports" / "benchmark"
    dest = args.out / f"seed_{seed}"
    if dest.exists():
        raise SystemExit(f"{dest} exists; this driver never overwrites a point")
    dest.mkdir(parents=True)
    started = now()
    uid_raw = f"{platform.node()}|{stamp(started)}|{args.commit}|{args.reps * 1_000_003 + seed}"
    load_start = loadavg()
    before = newest_run(reports)
    print(f"  seed_{seed}: reps={args.reps} (suite depth {max(1, args.reps // 2)}) "
          f"started {stamp(started)}", flush=True)
    proc = subprocess.run(
        [sys.executable, str(HERE / "_seed_point.py"), "--seed", str(seed),
         "--reps", str(args.reps), "--mc", str(args.mc)],
        cwd=args.src, env=env, capture_output=True, text=True, check=False,
    )
    finished = now()
    load_end = loadavg()
    (dest / "run.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    after = newest_run(reports)
    produced = after if after and after != before else None
    headline, artifacts = {}, []
    if produced:
        shutil.copytree(reports / produced, dest / "run")
        artifacts = [{"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                     for p in sorted((dest / "run").iterdir()) if p.is_file()]
        manifest = json.loads((dest / "run" / "manifest.json").read_text(encoding="utf-8"))
        headline = {k: manifest.get(k) for k in HEADLINE_KEYS}
    fp = subprocess.run([sys.executable, "-c", FINGERPRINT.format(seed=seed)], cwd=args.src,
                        env=env, capture_output=True, text=True, timeout=600, check=False)
    fingerprint = fp.stdout.strip() if len(fp.stdout.strip()) == 64 else None
    point = {
        "run_uid": hashlib.sha256(uid_raw.encode()).hexdigest()[:16],
        "capture": "live",
        "params": {
            "reps_requested": args.reps,
            "reps_effective": max(1, args.reps // 2),
            "mc": args.mc,
            "seed": seed,
            "catalog_fingerprint_sha256": fingerprint,
            "xla_flags": os.environ.get("XLA_FLAGS", ""),
            "headline_only": True,
        },
        "timing": {"started_utc": stamp(started), "finished_utc": stamp(finished),
                   "wall_seconds": round((finished - started).total_seconds(), 1)},
        "exit_status": proc.returncode,
        "local_run_dir": produced,
        "resources": {**parse_resources(proc.stdout),
                      "load_average_start": load_start, "load_average_end": load_end},
        "headline": headline,
        "artifacts": artifacts,
    }
    (dest / "point.json").write_text(json.dumps(point, indent=2) + "\n", encoding="utf-8")
    geo = headline.get("geomean_speedup_vs_baseline")
    print(f"  seed_{seed}: exit {proc.returncode}, {point['timing']['wall_seconds']:.0f} s, "
          f"n_cases {headline.get('n_cases')}, geomean {geo}", flush=True)
    return point


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True, help="export of the release (cwd of every point)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--commit", required=True, help="commit the export was made from (for run_uid)")
    ap.add_argument("--seed-base", type=int, default=20260603)
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--mc", type=int, default=8)
    args = ap.parse_args()
    args.src, args.out = args.src.resolve(), args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(args.src / "python")}
    seeds = [args.seed_base + i for i in range(args.seeds)]
    print(f"seed sweep: {len(seeds)} catalogues {seeds[0]}..{seeds[-1]} at --reps {args.reps} "
          f"--mc {args.mc}, headline-only, on {platform.node()} @ {args.commit[:8]}", flush=True)
    for s in seeds:
        point = one_seed(s, args, env)
        if point["exit_status"] != 0 or not point["local_run_dir"]:
            print(f"STOP: seed {s} exited {point['exit_status']} "
                  f"(run dir {point['local_run_dir']}); remaining seeds not run", flush=True)
            return point["exit_status"] or 1
    print(f"done: {len(seeds)} seeds", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
