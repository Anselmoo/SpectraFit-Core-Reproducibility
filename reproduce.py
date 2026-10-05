#!/usr/bin/env python3
"""Regenerate every result and figure of the SoftwareX paper from the release.

Why this exists
---------------
The paper describes spectrafit-core 0.1.0. Its numbers must therefore come from
0.1.0 as a reader can install it, not from a development checkout. This script
is a thin, pinned *consumer* of the release:

* the compiled library comes from the PyPI wheel pinned in ``uv.lock``;
* the benchmark harness and the figure scripts come from the public repository
  at the release tag, verified by commit hash;
* nothing from the harness is copied into this repository, so there is no second
  copy that could drift from the one the release ships.

What is regenerated and what is not
-----------------------------------
Regenerated on every run (seconds):

* ``results/nist_table2.json``           Table 1, shipped tolerance 1e-12
* ``results/nist_table2_tol1e15.json``   the same at 1e-15
* ``results/nist_head_to_head.json``     per-dataset curves behind Figure 2
* ``figures/figure1_architecture.*``     Figure 1
* ``figures/figure2_nist.*``             Figure 2
* ``figures/figure3_benchmark.*``        Figure 3, drawn from the archived timing

Taken from the release archive and verified by SHA-256, not re-measured:

* the timing benchmark (``bench_summary.json``, the ladder, the seed sweep) and
  the two measurements derived from a full benchmark run (``param_agreement.json``,
  ``audit_bias.json``). Wall-clock timing depends on the host, and the archived
  ladder took about 17 hours on a 16-core machine. ``--benchmark`` re-measures one
  rung on the current host and reports it next to the archived value; it never
  replaces the archived files.

After regeneration the script checks every number the paper states against the
data (``results/claims-report.json``) and exits non-zero if one no longer holds.

Usage
-----
    uv run --locked reproduce.py                  # regenerate, check claims
    uv run --locked reproduce.py --check          # compare with the stored results, write nothing
    uv run --locked reproduce.py --source DIR     # use an existing checkout of the tag
    uv run --locked --group benchmark reproduce.py --benchmark --reps 4
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import math
import os
import platform
import re
import shutil
import statistics as st
import io
import subprocess
import sys
import tarfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = tomllib.loads((HERE / "pins.toml").read_text())
CACHE = HERE / ".cache"
RESULTS = HERE / "results"
FIGURES = HERE / "figures"
# Three scripts of the release (fig_architecture.py, extract_bench_summary.py,
# measure_audit_bias.py) look for the repository root one directory above where it
# is: they were written for a path three levels deep and ship two levels deep. The
# scripts are run unmodified, so the export nests ``reproducibility/`` one level
# down, which puts ``crates/`` and ``python/`` where the scripts look for them.
UPSTREAM_FIGS = Path("reproducibility") / "figures"

# script -> extra argv. Order matters: fig_nist_dual reads nist_head_to_head.json.
MEASUREMENTS: list[tuple[str, list[str]]] = [
    ("nist_head_to_head.py", []),
    ("nist_table2.py", []),
    ("nist_table2.py", ["--tolerance", "1e-15"]),
]
# upstream stem -> name in this folder
FIGURE_MAP = {
    "fig_architecture": "figure1_architecture",
    "fig_nist_dual": "figure2_nist",
    "fig_benchmark_profile": "figure3_benchmark",
}
REGENERATED_JSON = ["nist_head_to_head.json", "nist_table2.json", "nist_table2_tol1e15.json"]
# What the scripts read: the harness, the figure scripts with their inputs, and the
# crate manifests that fig_architecture.py counts.
EXPORT_PATHS = ["reproducibility", "python/oracles", "crates", "Cargo.toml"]
SOLVERS = ["spectrafit_core", "lmfit", "scipy_lm", "scipy_trf"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_digest(path: Path) -> str:
    """SHA-256 of a result file without its wall-clock fields.

    ``nist_head_to_head.json`` records how long each fit took (``ms``). That
    number changes on every run; the fitted values do not.
    """
    def strip(node: object) -> object:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k != "ms"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    canonical = json.dumps(strip(json.loads(path.read_text())), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"FAILED ({proc.returncode}): {' '.join(cmd)}")
    return proc.stdout


# --------------------------------------------------------------------------- source


def ensure_source(source: Path | None) -> Path:
    """Export the pinned release commit into ``.cache/work`` and return that path.

    The files are read from the commit object with ``git archive``, so a checkout
    passed with ``--source`` is never modified and its working-tree state does
    not matter. Only the paths the scripts need are exported, in the release's
    own layout.
    """
    src = PINS["source"]
    if source is None:
        source = CACHE / f"SpectraFit-Core-{src['tag']}"
        if not (source / ".git").exists():
            CACHE.mkdir(exist_ok=True)
            print(f"cloning {src['repository']} at {src['tag']} ...")
            run(["git", "clone", "--quiet", "--depth", "1", "--branch", src["tag"],
                 src["repository"], str(source)], cwd=HERE)
    probe = subprocess.run(["git", "cat-file", "-e", f"{src['commit']}^{{commit}}"],
                           cwd=source, capture_output=True, check=False)
    if probe.returncode != 0:
        raise SystemExit(f"{source} does not contain the pinned commit {src['commit']} ({src['tag']})")
    work = CACHE / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    tar = subprocess.run(["git", "archive", "--format=tar", src["commit"], *EXPORT_PATHS],
                         cwd=source, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(work, filter="data")
    for rel, digest in PINS["archived_inputs"].items():
        got = sha256(work / rel)
        if got != digest:
            raise SystemExit(f"archived input {rel} has sha256 {got}, pinned {digest}")
    return work


def harness_path(source: Path) -> Path:
    """Expose ``oracles`` alone on the import path.

    Putting the checkout's ``python/`` on ``PYTHONPATH`` would also expose its
    ``spectrafit_core`` source package, which has no compiled extension and would
    shadow the installed wheel. Only the harness is copied out.
    """
    target = CACHE / "harness"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source / "python" / "oracles", target / "oracles")
    return target


def check_environment() -> dict[str, str]:
    versions = {name: md.version(name) for name in PINS["packages"]}
    drift = {n: (v, PINS["packages"][n]) for n, v in versions.items() if v != PINS["packages"][n]}
    if drift:
        lines = ", ".join(f"{n} {got} (pinned {want})" for n, (got, want) in drift.items())
        raise SystemExit(f"environment differs from pins.toml: {lines}. Run with `uv run --locked`.")
    versions["matplotlib"] = md.version("matplotlib")
    return versions


# --------------------------------------------------------------------------- regenerate


def regenerate(source: Path) -> dict[str, dict]:
    """Run the release's own scripts in place; return {name: (archived, regenerated)}."""
    figs = source / UPSTREAM_FIGS
    release_copy = CACHE / "release-archive"
    release_copy.mkdir(exist_ok=True)
    for n in REGENERATED_JSON:  # keep what the release shipped before overwriting it
        shutil.copyfile(figs / n, release_copy / n)
    archived = {n: json.loads((release_copy / n).read_text()) for n in REGENERATED_JSON}
    env = os.environ | {
        "PYTHONPATH": str(harness_path(source)),
        "MPLBACKEND": "Agg",
        # Fixed PDF/PNG timestamps, so an unchanged figure hashes the same twice.
        "SOURCE_DATE_EPOCH": str(PINS["source"]["source_date_epoch"]),
    }
    for script, argv in MEASUREMENTS:
        print(f"  measuring  {script} {' '.join(argv)}".rstrip())
        run([sys.executable, script, *argv], cwd=figs, env=env)
    for stem in FIGURE_MAP:
        print(f"  drawing    {stem}.py")
        run([sys.executable, f"{stem}.py"], cwd=figs, env=env)
    return {n: {"archived": archived[n], "regenerated": json.loads((figs / n).read_text())}
            for n in REGENERATED_JSON}


def collect(source: Path, into_results: Path, into_figures: Path) -> None:
    figs = source / UPSTREAM_FIGS
    into_results.mkdir(parents=True, exist_ok=True)
    into_figures.mkdir(parents=True, exist_ok=True)
    for n in REGENERATED_JSON:
        shutil.copyfile(figs / n, into_results / n)
    for stem, name in FIGURE_MAP.items():
        for ext in ("pdf", "png"):
            shutil.copyfile(figs / f"{stem}.{ext}", into_figures / f"{name}.{ext}")
    archived = into_results / "archived"
    archived.mkdir(exist_ok=True)
    for rel in PINS["archived_inputs"]:
        shutil.copyfile(source / rel, archived / Path(rel).name)
    # The three NIST files as the release shipped them, for the drift report.
    shipped = into_results / "release-archive"
    shipped.mkdir(exist_ok=True)
    for n in REGENERATED_JSON:
        shutil.copyfile(CACHE / "release-archive" / n, shipped / n)


# --------------------------------------------------------------------------- drift


def table_drift(pair: dict) -> dict:
    """Cell-by-cell difference between the archived and the regenerated Table 1."""
    old = {d["name"]: d["columns"] for d in pair["archived"]["datasets"]}
    new = {d["name"]: d["columns"] for d in pair["regenerated"]["datasets"]}
    cells, worst = [], {}
    for name, cols in new.items():
        for col, value in cols.items():
            before = old[name][col]
            if value is None or before is None:
                continue
            delta = value - before
            cells.append({"dataset": name, "column": col, "archived": before,
                          "regenerated": value, "delta": delta})
            if abs(delta) > abs(worst.get(col, {"delta": 0.0})["delta"]):
                worst[col] = {"dataset": name, "delta": delta}
    moved = [c for c in cells if abs(c["delta"]) >= 0.05]
    return {"n_cells": len(cells), "n_cells_moved_by_0.05_or_more": len(moved),
            "largest_change_per_column": worst, "moved_cells": moved}


# --------------------------------------------------------------------------- claims


def _gm(xs: list[float]) -> float:
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def claims(results: Path, nist_dir: Path | None = None) -> list[dict]:
    """Every number the paper states, recomputed from the data it cites.

    ``nist_dir`` selects which copy of the three NIST files is checked: the
    regenerated one (default) or the one the release shipped.
    """
    nist_dir = nist_dir or results
    t = json.loads((nist_dir / "nist_table2.json").read_text())
    t15 = json.loads((nist_dir / "nist_table2_tol1e15.json").read_text())
    h2h = json.loads((nist_dir / "nist_head_to_head.json").read_text())
    arch = results / "archived"
    bench = json.loads((arch / "bench_summary.json").read_text())
    ladder = json.loads((arch / "ladder.json").read_text())
    sweep = json.loads((arch / "sweep.json").read_text())
    agree = json.loads((arch / "param_agreement.json").read_text())
    bias = json.loads((arch / "audit_bias.json").read_text())

    rows = t["datasets"]
    col = lambda c: {r["name"]: r["columns"][c] for r in rows}  # noqa: E731
    sf, lm = col("spectrafit_core"), col("lmfit")
    wins = dict.fromkeys(SOLVERS, 0)
    last = dict.fromkeys(SOLVERS, 0)
    for r in rows:
        v = {c: r["columns"][c] for c in SOLVERS}
        wins[max(v, key=v.get)] += 1
        last[min(v, key=v.get)] += 1
    sf_last = [r["name"] for r in rows
               if min(SOLVERS, key=lambda c, r=r: r["columns"][c]) == "spectrafit_core"]
    sigma = {n: v for n, v in col("sigma").items() if v is not None}
    sigma_wo = [v for n, v in sigma.items() if n != "Lanczos1"]
    sf15 = {r["name"]: r["columns"]["spectrafit_core"] for r in t15["datasets"]}
    raised = sum(sf15[n] > sf[n] + 1e-9 for n in sf)
    lowered = sum(sf15[n] < sf[n] - 1e-9 for n in sf)
    gap = max(
        max(abs(a - b) for a, b in zip(r["spectrafit"]["resid"], r["lmfit"]["resid"], strict=True))
        / (max(r["y"]) - min(r["y"]))
        for r in h2h
    )

    cases = bench["cases"]
    speed = [c["m"]["spectrafit"]["speedup"] for c in cases]
    ratio = {
        s: _gm([c["m"][s]["med_ms"] / c["m"]["spectrafit"]["med_ms"]
                for c in cases if c["m"].get(s) and c["m"][s].get("med_ms")])
        for s in bench["solvers"][1:]
    }

    def quickest(case: dict) -> str:
        timed = {s: m["med_ms"] for s, m in case["m"].items() if m and m.get("med_ms") is not None}
        return min(timed, key=timed.get)

    fastest = sum(quickest(c) == "spectrafit" for c in cases)
    lost = {c["category"] for c in cases if quickest(c) != "spectrafit"}
    no_optfn = _gm([c["m"]["spectrafit"]["speedup"] for c in cases if c["category"] != "optfn"])
    cx = next(c for c in cases if c["id"] == "CX-017")["m"]
    cx_r2 = {s: m["r2"] for s, m in cx.items()}
    cx_err = {s: m["param_err"] for s, m in cx.items()}
    by_cat: dict[str, list[float]] = {}
    for c in cases:
        by_cat.setdefault(c["category"], []).append(c["m"]["spectrafit"]["speedup"])
    cat = {k: _gm(v) for k, v in by_cat.items()}
    depth = [r["headline"]["geomean_speedup_vs_baseline"] for r in ladder["rungs"]]
    seeds = [r["headline"]["geomean_speedup_vs_baseline"] for r in sweep["rungs"]]
    dev = bias["parity"]["deviations"]
    nonzero = sorted(v for v in dev.values() if v > 0)

    def c(cid: str, source: str, statement: str, observed: object, ok: bool) -> dict:
        return {"id": cid, "source": source, "statement": statement, "observed": observed, "ok": bool(ok)}

    reg, arc = "regenerated", "archived"
    return [
        c("nist-01", reg, "22 of the 27 NIST problems are implemented", len(rows), len(rows) == 22),
        c("nist-02", reg, "spectrafit-core recovers every certified value to more than six "
          "significant figures; the minimum is 6.5, on Thurber",
          {"min": min(sf.values()), "dataset": min(sf, key=sf.get)},
          min(sf.values()) > 6 and round(min(sf.values()), 1) == 6.5 and min(sf, key=sf.get) == "Thurber"),
        c("nist-03", reg, "lmfit clears the four-figure threshold on all 22, minimum 4.6",
          min(lm.values()), min(lm.values()) >= 4 and round(min(lm.values()), 1) == 4.6),
        c("nist-04", reg, "the two SciPy configurations fall to 2.2 on Hahn1 and clear the threshold elsewhere",
          {s: {n: v for n, v in col(s).items() if v < 4} for s in ("scipy_lm", "scipy_trf")},
          all({n for n, v in col(s).items() if v < 4} == {"Hahn1"} and round(col(s)["Hahn1"], 1) == 2.2
              for s in ("scipy_lm", "scipy_trf"))),
        c("nist-05", reg, "spectrafit-core is the most accurate on 15 datasets, the two SciPy "
          "configurations on seven between them, and lmfit on none", wins,
          wins["spectrafit_core"] == 15 and wins["scipy_lm"] + wins["scipy_trf"] == 7 and wins["lmfit"] == 0),
        c("nist-06", reg, "spectrafit-core is the least accurate of the four on Lanczos1 only",
          sf_last, sf_last == ["Lanczos1"]),
        c("nist-07", reg, "standard errors are defined on 20 of the 22 datasets (not Eckerle4, DanWood)",
          sorted(set(sf) - set(sigma)), sorted(set(sf) - set(sigma)) == ["DanWood", "Eckerle4"]),
        c("nist-08", reg, "the median standard-error agreement lies between 7.8 and 7.9 significant "
          "figures, and with one exception none falls below 5.8",
          {"median": st.median(sigma.values()), "min_without_Lanczos1": min(sigma_wo)},
          7.8 <= st.median(sigma.values()) < 7.9 and min(sigma_wo) >= 5.8),
        c("nist-09", reg, "Lanczos1: values agree to 8.7 figures, standard errors to 0.6",
          {"value": sf["Lanczos1"], "sigma": sigma["Lanczos1"]},
          round(sf["Lanczos1"], 1) == 8.7 and round(sigma["Lanczos1"], 1) == 0.6),
        c("nist-10", reg, "parameters recovered by spectrafit-core and lmfit differ by up to 3.5 significant figures",
          max(sf[n] - lm[n] for n in sf), round(max(sf[n] - lm[n] for n in sf), 1) == 3.5),
        c("nist-11", reg, "the fitted curves agree to within 8e-7 of the range of a dataset",
          gap, gap < 8e-7),
        c("nist-12", reg, "a rerun at 1e-15 raises the agreement of spectrafit-core on most datasets and lowers none",
          {"raised": raised, "lowered": lowered, "unchanged": len(sf) - raised - lowered},
          lowered == 0 and raised >= 11),
        c("bench-01", arc, "151 cases", len(cases), len(cases) == 151),
        c("bench-02", arc, "16.4 times faster than lmfit in geometric mean, 13.8 in harmonic mean",
          {"geomean": _gm(speed), "harmonic": len(speed) / sum(1 / x for x in speed)},
          round(_gm(speed), 1) == 16.4 and round(len(speed) / sum(1 / x for x in speed), 1) == 13.8),
        c("bench-03", arc, "factors 6.2, 7.9 and 6.5 against the SciPy configurations and 4.9 against JAX",
          ratio, [round(ratio[s], 1) for s in
                  ("scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox", "jax")] == [6.2, 7.9, 6.5, 4.9]),
        c("bench-04", arc, "fastest backend on 131 of the 151 cases", fastest, fastest == 131),
        c("bench-05", arc, "by category the speedup ranges from 8.9 to 28.3; tied-parameter cases 14.1",
          {k: round(v, 2) for k, v in cat.items()},
          round(min(cat.values()), 1) == 8.9 and round(max(cat.values()), 1) == 28.3
          and round(cat["tied"], 1) == 14.1),
        c("bench-06", arc, "the headline moves between 15.8 and 16.4 across the five depths",
          depth, len(depth) == 5 and round(min(depth), 1) == 15.8 and round(max(depth), 1) == 16.4),
        c("bench-07", arc, "15.95 with a standard deviation of 0.38 across 50 seeds",
          {"n": len(seeds), "mean": st.mean(seeds), "sd": st.stdev(seeds)},
          len(seeds) == 50 and round(st.mean(seeds), 2) == 15.95 and round(st.stdev(seeds), 2) == 0.38),
        c("bench-08", arc, "the 20 cases it loses are the optimisation functions",
          sorted(lost), lost == {"optfn"} and len(cases) - fastest == 20),
        c("bench-09", arc, "excluding the optimisation-function category lowers the headline to 15.1",
          no_optfn, round(no_optfn, 1) == 15.1),
        c("agree-02", arc, "CX-017: the six backends report the same coefficient of determination to three "
          "significant figures; parameter errors lie between 660 % and 1.3 million %",
          {"r2": cx_r2, "param_err_pct": cx_err},
          len(cx) == 6 and {f"{v:.3g}" for v in cx_r2.values()} == {"0.962"}
          and 660 <= min(cx_err.values()) < 670 and 1.25e6 <= max(cx_err.values()) < 1.35e6),
        c("agree-01", arc, "on 93 cases the six backends agree to within 0.23 percentage points; 31 remain",
          {"n": agree["n_well_conditioned"], "spread": agree["max_cross_backend_spread_pct_points"],
           "excluded": agree["excluded_stratum"]["n"]},
          agree["n_well_conditioned"] == 93 and agree["excluded_stratum"]["n"] == 31
          and round(agree["max_cross_backend_spread_pct_points"], 2) == 0.23),
        c("bias-01", arc, "about 75 microseconds against 3 for plain array code, roughly a factor of 25",
          bias["bias"], round(bias["bias"]["wheel_us"]) == 75 and round(bias["bias"]["numpy_us"]) == 3
          and round(bias["bias"]["ratio"]) == 25),
        c("bias-02", arc, "35 registered kernels: 23 agree bit for bit, 12 do not; all but one of those "
          "to better than 4e-16, the exception at 5e-7",
          {"n": len(dev), "exact": bias["parity"]["n_exact"], "nonzero": len(nonzero),
           "largest_two": nonzero[-2:]},
          len(dev) == 35 and bias["parity"]["n_exact"] == 23 and len(nonzero) == 12
          and nonzero[-2] < 4e-16 and 4e-7 < nonzero[-1] < 5e-7),
    ]


# --------------------------------------------------------------------------- optional timing


def benchmark(source: Path, reps: int) -> dict:
    """Re-measure one rung on this host. Reported, never substituted."""
    workdir = CACHE / "benchmark-run"
    workdir.mkdir(parents=True, exist_ok=True)
    env = os.environ | {"PYTHONPATH": str(harness_path(source))}
    print(f"  benchmarking 151 cases x 6 backends at --reps {reps}; the archived run took "
          "77 minutes at --reps 4 on 16 cores")
    run([sys.executable, "-m", "oracles.cli", "run", "--reps", str(reps)], cwd=workdir, env=env)
    manifests = sorted(workdir.rglob("manifest.json"), key=lambda p: p.stat().st_mtime)
    if not manifests:
        raise SystemExit("the benchmark wrote no manifest.json")
    m = json.loads(manifests[-1].read_text())
    return {"run_dir": str(manifests[-1].parent), "reps": reps,
            "geomean_speedup_vs_baseline": m.get("geomean_speedup_vs_baseline"),
            "harmonic_mean_speedup_vs_baseline": m.get("harmonic_mean_speedup_vs_baseline"),
            "max_abs_delta_r2": m.get("max_abs_delta_r2"), "n_cases": m.get("n_cases")}


# --------------------------------------------------------------------------- provenance


def cpu_model() -> str:
    try:
        if sys.platform == "darwin":
            return run(["sysctl", "-n", "machdep.cpu.brand_string"], cwd=HERE).strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except (OSError, SystemExit):
        pass
    return platform.processor() or "unknown"


def repository_state() -> dict:
    """Commit and dirty state of this repository, read before the run writes anything."""
    def git(*args: str) -> str | None:
        proc = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = git("status", "--porcelain")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
        "dirty_paths": sorted(line[3:] for line in status.splitlines()) if status else [],
    }


def host_details() -> dict:
    """What decides the last digits of a fit besides the packages: kernel, C/maths library,
    CPU features and the BLAS/LAPACK that NumPy and SciPy were built with and actually loaded."""
    import numpy
    import scipy
    import scipy.linalg  # noqa: F401  (loads SciPy's LAPACK, as least_squares does)

    def build_deps(mod) -> dict:
        deps = mod.show_config(mode="dicts").get("Build Dependencies", {})
        return {k: {f: deps[k].get(f) for f in ("name", "version", "found")} for k in ("blas", "lapack") if k in deps}

    details: dict = {
        "kernel": platform.release(),
        "libc": " ".join(platform.libc_ver()).strip() or None,
        "blas_lapack": {"numpy_build": build_deps(numpy), "scipy_build": build_deps(scipy)},
    }
    if sys.platform.startswith("linux"):
        try:
            details["ldd"] = run(["ldd", "--version"], cwd=HERE).splitlines()[0]
        except SystemExit:
            details["ldd"] = None
        flags = next((ln.split(":", 1)[1].split() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                      if ln.startswith("flags")), [])
        details["cpu_flags"] = sorted(flags)
        maps = Path("/proc/self/maps").read_text().splitlines()
        pattern = re.compile(r"(openblas|blas|lapack|mkl|blis|gfortran|libm\.so|quadmath)", re.IGNORECASE)
        paths = {ln.split()[-1] for ln in maps if len(ln.split()) >= 6 and pattern.search(ln.split()[-1])}
        # Shared libraries only (not SciPy's own extension modules); wheel-bundled ones are named
        # relative to site-packages so the path does not depend on where the environment lives.
        details["blas_lapack"]["loaded"] = sorted(
            p.split("site-packages/", 1)[-1] for p in paths if ".cpython-" not in Path(p).name)
    elif sys.platform == "darwin":
        out = run(["sysctl", "hw.optional"], cwd=HERE)
        details["cpu_flags"] = sorted(ln.split(":")[0].removeprefix("hw.optional.")
                                      for ln in out.splitlines() if ln.strip().endswith(": 1"))
        details["blas_lapack"]["loaded"] = None  # no /proc/self/maps; the build info above names Accelerate
    return details


def provenance(source: Path, versions: dict[str, str], extra: dict) -> dict:
    lock = HERE / "uv.lock"
    return {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "reproduce.py " + " ".join(sys.argv[1:]),
        "software": PINS["source"] | {"doi": PINS["software"]["doi"], "wheel": PINS["software"]["wheel"]},
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu": cpu_model(),
            "cores": os.cpu_count(),
            "packages": versions,
            "uv_lock_sha256": sha256(lock) if lock.exists() else None,
            **host_details(),
        },
        "upstream_scripts_sha256": {
            s: sha256(source / UPSTREAM_FIGS / s)
            for s in sorted({m for m, _ in MEASUREMENTS} | {f"{f}.py" for f in FIGURE_MAP}
                            | {"extract_bench_summary.py"})
        },
        "archived_inputs_sha256": dict(PINS["archived_inputs"]),
        **extra,
    }


def write_checksums() -> None:
    """One manifest over everything in this folder that a reader may want to verify."""
    skip_dirs = {".git", ".cache", ".venv", "__pycache__"}
    lines = []
    for path in sorted(HERE.rglob("*")):
        rel = path.relative_to(HERE)
        if not path.is_file() or skip_dirs & set(rel.parts) or rel.name in {"checksums.sha256", ".DS_Store"}:
            continue
        lines.append(f"{sha256(path)}  {rel.as_posix()}")
    (HERE / "checksums.sha256").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, help="existing checkout of the pinned tag (default: clone into .cache/)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate into .cache/ and compare with the stored results; write nothing")
    ap.add_argument("--benchmark", action="store_true", help="also re-measure one timing rung on this host")
    ap.add_argument("--reps", type=int, default=4, help="--reps for --benchmark (default 4, the shallowest archived rung)")
    args = ap.parse_args()

    repository = repository_state()  # before anything below writes into the tree
    versions = check_environment()
    source = ensure_source(args.source)
    print(f"source     {PINS['source']['tag']} @ {PINS['source']['commit'][:12]}")
    print(f"library    spectrafit-core {versions['spectrafit-core']} (wheel), "
          f"{platform.machine()} {platform.system()}, Python {platform.python_version()}")
    pairs = regenerate(source)

    results = CACHE / "check" / "results" if args.check else RESULTS
    figures = CACHE / "check" / "figures" if args.check else FIGURES
    collect(source, results, figures)

    drift = table_drift(pairs["nist_table2.json"])
    report = claims(results)
    failed = [c for c in report if not c["ok"]]
    # The same NIST statements, checked on the files the release shipped.
    shipped = {c["id"]: c["ok"] for c in claims(results, results / "release-archive")
               if c["id"].startswith("nist")}
    for c in report:
        if c["id"] in shipped:
            c["holds_on_release_archive"] = shipped[c["id"]]
    extra: dict = {"repository": repository,
                   "drift_vs_release_archive": {k: v for k, v in drift.items() if k != "moved_cells"}}
    if args.benchmark:
        extra["benchmark_on_this_host"] = benchmark(source, args.reps)

    (results / "drift-report.json").write_text(json.dumps(drift, indent=1) + "\n")
    (results / "claims-report.json").write_text(json.dumps(report, indent=1) + "\n")
    (results / "provenance.json").write_text(
        json.dumps(provenance(source, versions, extra), indent=1) + "\n")

    print(f"\nTable 1    {drift['n_cells_moved_by_0.05_or_more']} of {drift['n_cells']} cells differ from the "
          "release archive by 0.05 significant figures or more")
    for col, w in drift["largest_change_per_column"].items():
        print(f"           {col:16s} largest change {w['delta']:+.2f} on {w['dataset']}")
    print(f"claims     {len(report) - len(failed)} of {len(report)} hold")
    both = [c["id"] for c in report if c.get("holds_on_release_archive") is False]
    print("           NIST statements that do not hold on the release's own archived files: "
          + (", ".join(both) if both else "none"))
    for c in failed:
        print(f"  FAILS    {c['id']}: {c['statement']}\n           observed: {json.dumps(c['observed'])[:200]}")

    if args.check:
        changed = [n for n in REGENERATED_JSON
                   if not (RESULTS / n).exists() or content_digest(RESULTS / n) != content_digest(results / n)]
        print("check      " + ("stored results are current" if not changed
                               else "differs from stored results: " + ", ".join(changed)))
        return 1 if (changed or failed) else 0

    run([sys.executable, str(HERE / "build_crate.py")], cwd=HERE)
    write_checksums()
    print("wrote      results/, figures/, ro-crate-metadata.json, checksums.sha256")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
