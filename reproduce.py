#!/usr/bin/env python3
"""Regenerate every result and figure of the paper from the release.

Why this exists
---------------
The paper describes spectrafit-core 0.1.2. Its numbers must therefore come from
0.1.2 as a reader can install it, not from a development checkout. This script
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
* ``figures/figure3_benchmark.*``        Figure 3, drawn from the measured timing
* ``results/eels_fe2o3.json``            the constrained fit of a measured spectrum (Section 3.3)
* ``figures/figure4_eels.*``             Figure 4, by ``scripts/fig_eels.py``: the one figure
                                         the release has no script for, drawn with the wheel's
                                         public API from the spectrum the release ships

Measured on terra with the 0.1.2 wheel and the v0.1.2 harness (``bench/``), stored in
``results/timing/`` and verified here by the SHA-256 in ``pins.toml [timing_inputs]``:

* the timing benchmark (``bench_summary.json``, the five-depth ladder, the 50-seed
  sweep), ``param_agreement.json`` and ``audit_bias.json``. Wall-clock timing depends
  on the host and the measurement took 26 hours on 16 cores, so it is not repeated on
  every run. ``--benchmark`` re-measures one rung on the current host and reports it
  next to the measured value; it never replaces the stored files.

The 151-case timing archive shipped in the release (measured before the release) is
still verified by SHA-256 and copied to ``results/archived/``; the paper no longer
uses it.

``--examples`` is a separate target: it runs the Python files of the example gallery mirrored
into ``examples/`` (``scripts/mirror_gallery.py``, source commit and SHA-256 per file in
``examples-manifest.json``) as a smoke run with ``MPLBACKEND=Agg`` and a timeout per
script, and records exit code and wall time of each in ``results/examples-smoke.json``.
It needs no network and does not regenerate anything else.

After regeneration the script checks every number the paper states against the
data (``results/claims-report.json``) and exits non-zero if one no longer holds.

Usage
-----
    uv run --locked reproduce.py                  # regenerate, check claims
    uv run --locked reproduce.py --check          # compare with the stored results, write nothing
    uv run --locked reproduce.py --source DIR     # use an existing checkout of the tag
    uv run --locked --group benchmark reproduce.py --benchmark --reps 4
    uv run --locked reproduce.py --examples       # smoke run of examples/ only
    uv run --locked reproduce.py --targets all    # every target below, into results/

Targets (``--targets``, comma-separated, default ``core``)
----------------------------------------------------------
``core``                the regeneration above (NIST tables, Figures 1 to 4, claims)
``nist-both``           NIST StRD from both certified starts (``nist_table2.py --start both``)
``usage``               the short usage scripts in ``usage/``, run unchanged, output compared
``gallery``             every script of ``examples/`` with its fits recorded (``scripts/gallery_run.py``)
``eels-far``            the bounded Fe L2,3 fit from 500 far starts, free and constrained model, per solver
``bench-tolerance``     the benchmark at the libraries' default stopping tolerances and at one common tolerance
``bench-ablation``      analytic against finite-difference Jacobian (backend ``spectrafit_fd``)
``audit-stationarity``  stationarity of every benchmark endpoint at the common tolerance (solver audit)
``interop-fe-l23``      the Fe L2,3 constrained graph JSON fitted by SpectraFit-Core and by lmfit (from 1.3.1)
``overview``            ``results/overview/overview.html`` and ``overview.pdf`` from the outputs above

Each target writes ``results/<target>/`` with a ``README.md`` and ``run.json`` (command, times,
load, host, Python, wheel SHA-256, SHA-256 of every file).

Dry run
-------
``--dry-run`` runs the targets against a release candidate before the release exists, in an
environment built by ``scripts/dry_run_env.py``. It needs ``--source`` (a checkout holding the
candidate's commit), ``--source-commit`` and ``--out`` (a folder outside this repository);
``SPECTRAFIT_RC_VERSION`` and ``SPECTRAFIT_RC_SHA256`` name the candidate. Nothing in this
repository is written: results, figures, checksums and the cache all go below ``--out``.
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
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))
import run_record  # noqa: E402
PINS = tomllib.loads((HERE / "pins.toml").read_text())
# The release the stored timing measured, from pins.toml [timing] library
# ("spectrafit-core <version>, ..."); labels the claims computed from results/timing/.
TIMING_VERSION = re.fullmatch(r"spectrafit-core (\S+), .+", PINS["timing"]["library"]).group(1)
CACHE = HERE / ".cache"
RESULTS = HERE / "results"
FIGURES = HERE / "figures"
# The release's figure scripts, run unmodified in the release's own layout.
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
# Figure 4 has no script in the release; this repository adds one. It reads the measured
# spectrum from the release export (redistributed there under the ODbL with attribution).
OWN_SCRIPTS = {"fig_eels": HERE / "scripts" / "fig_eels.py"}
EELS_SPECTRUM = Path("reproducibility") / "spectra" / "eelsdb-fe2o3-l23" / "DspecTi3wqG.msa"
EELS_JSON = "eels_fe2o3.json"
EELS_FIGURE = "figure4_eels"
# What the scripts read: the harness, the figure scripts with their inputs, and the
# crate manifests that fig_architecture.py counts.
EXPORT_PATHS = ["reproducibility", "python/oracles", "crates", "Cargo.toml"]
SOLVERS = ["spectrafit_core", "lmfit", "scipy_lm", "scipy_trf"]
TIMING = RESULTS / "timing"
# The product name in the figure labels. The release's figure scripts print the package
# id ("spectrafit-core", "spectrafit"); the article writes "SpectraFit-Core". These are
# the only edits made to the release's scripts: each (old, new) must match exactly once,
# and the hashes before and after are recorded in results/provenance.json.
LABEL_PATCHES: dict[str, list[tuple[str, str]]] = {
    "reproducibility/figures/fig_nist_dual.py": [
        ('"$\\\\bullet$ spectrafit-core   $\\\\circ$ lmfit"', '"$\\\\bullet$ SpectraFit-Core   $\\\\circ$ lmfit"'),
        ('label="spectrafit-core fit"', 'label="SpectraFit-Core fit"'),
        ('label="spectrafit-core, worst parameter"', 'label="SpectraFit-Core, worst parameter"'),
    ],
    "reproducibility/figures/fig_benchmark_profile.py": [
        ('SUBJECT = "spectrafit"\n', 'SUBJECT = "spectrafit"\nDISPLAY = {"spectrafit": "SpectraFit-Core"}\n'),
        # the longer name on two lines, so the rotated tick at the left edge stays inside the figure
        ('[f"{b}  {int((ratios[b] == 1.0).sum())}',
         '[(f"{DISPLAY[b]}\\n" if b in DISPLAY else f"{b}  ") + f"{int((ratios[b] == 1.0).sum())}'),
        ('label=f"{backend}  (n={len(col)})"', 'label=f"{DISPLAY.get(backend, backend)}  (n={len(col)})"'),
    ],
}
# The measured timing, put where the release's fig_benchmark_profile.py reads it.
TIMING_OVERLAY = {
    "results/timing/bench_summary.json": "reproducibility/figures/bench_summary.json",
    "results/timing/ladder/ladder.json": "reproducibility/ladder/ladder.json",
}
# The Python files of the example gallery: mirrored by scripts/mirror_gallery.py, run by --examples.
EXAMPLES = HERE / "examples"
EXAMPLES_MANIFEST = HERE / "examples-manifest.json"
EXAMPLES_SMOKE = "examples-smoke.json"
EXAMPLES_TIMEOUT_S = 600.0
# Mirrored files the smoke run does not execute, with the reason. The mirror is not edited;
# a script that needs network, data outside the gallery or a GUI is listed here instead.
EXAMPLES_SKIP: dict[str, str] = {
    "examples/misspecified_model.py":
        "reads reproducibility/spectra/eelsdb-fe2o3-l23/DspecTi3wqG.msa from the root of a "
        "spectrafit-core checkout (Path(__file__).parents[3]), outside the gallery folder",
}
STDERR_TAIL_LINES = 20


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
    apply_label_patches(work)
    kept = CACHE / "archived-inputs"
    if kept.exists():
        shutil.rmtree(kept)
    kept.mkdir()
    for rel, digest in PINS["archived_inputs"].items():
        got = sha256(work / rel)
        if got != digest:
            raise SystemExit(f"archived input {rel} has sha256 {got}, pinned {digest}")
        shutil.copyfile(work / rel, kept / Path(rel).name)
    return work


LABEL_PATCH_RECORD: dict[str, dict[str, str]] = {}


def apply_label_patches(work: Path) -> None:
    """Write the product name into the figure labels of the exported release scripts."""
    for rel, edits in LABEL_PATCHES.items():
        path = work / rel
        before = sha256(path)
        text = path.read_text(encoding="utf-8")
        for old, new in edits:
            if text.count(old) != 1:
                raise SystemExit(f"label patch for {rel} expects exactly one {old!r}, found {text.count(old)}")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        LABEL_PATCH_RECORD[rel] = {"release_sha256": before, "patched_sha256": sha256(path)}


def verify_timing() -> None:
    """The measured timing files must be the ones whose SHA-256 pins.toml records."""
    for rel, digest in PINS["timing_inputs"].items():
        path = HERE / rel
        if not path.exists():
            raise SystemExit(f"timing input {rel} is missing")
        got = sha256(path)
        if got != digest:
            raise SystemExit(f"timing input {rel} has sha256 {got}, pinned {digest}")


def overlay_timing(source: Path) -> None:
    """Replace the release's 151-case timing inputs of Figure 3 by the measured ones.

    ``fig_benchmark_profile.py`` reads ``bench_summary.json`` next to itself and the
    repetition ladder (``../ladder/ladder.json`` plus ``../ladder/rungs/*/manifest.json``)
    for the depth it states. The script is not changed; only its inputs are.
    """
    for rel, dest in TIMING_OVERLAY.items():
        shutil.copyfile(HERE / rel, source / dest)
    rungs = source / "reproducibility" / "ladder" / "rungs"
    shutil.rmtree(rungs)
    for manifest in sorted((TIMING / "ladder" / "rungs").glob("*/manifest.json")):
        (rungs / manifest.parent.name).mkdir(parents=True)
        shutil.copyfile(manifest, rungs / manifest.parent.name / "manifest.json")


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
    overlay_timing(source)
    for stem in FIGURE_MAP:
        print(f"  drawing    {stem}.py")
        run([sys.executable, f"{stem}.py"], cwd=figs, env=env)
    eels_out = CACHE / "eels"
    if eels_out.exists():
        shutil.rmtree(eels_out)
    print("  fitting    scripts/fig_eels.py (Figure 4)")
    run([sys.executable, str(OWN_SCRIPTS["fig_eels"]), "--spectrum", str(source / EELS_SPECTRUM),
         "--out", str(eels_out)], cwd=HERE, env=env | {"PYTHONPATH": ""})
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
    shutil.copyfile(CACHE / "eels" / EELS_JSON, into_results / EELS_JSON)
    for ext in ("pdf", "png"):
        shutil.copyfile(CACHE / "eels" / f"{EELS_FIGURE}.{ext}", into_figures / f"{EELS_FIGURE}.{ext}")
    archived = into_results / "archived"
    archived.mkdir(exist_ok=True)
    for rel in PINS["archived_inputs"]:  # as verified, before overlay_timing replaced them
        shutil.copyfile(CACHE / "archived-inputs" / Path(rel).name, archived / Path(rel).name)
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
    timing = TIMING  # the stored measurement, in --check mode too
    bench = json.loads((timing / "bench_summary.json").read_text())
    ladder = json.loads((timing / "ladder" / "ladder.json").read_text())
    sweep = json.loads((timing / "seed-sweep" / "sweep.json").read_text())
    agree = json.loads((timing / "param_agreement.json").read_text())
    bias = json.loads((timing / "audit_bias.json").read_text())
    eels = json.loads((results / EELS_JSON).read_text())

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
    hm_ratio = {}
    for s in bench["solvers"][1:]:
        r = [c["m"][s]["med_ms"] / c["m"]["spectrafit"]["med_ms"]
             for c in cases if c["m"].get(s) and c["m"][s].get("med_ms")]
        hm_ratio[s] = len(r) / sum(1 / x for x in r)
    scipy_cfg = ("scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox")
    medians = {s: st.median(c["m"][s]["med_ms"] for c in cases if c["m"].get(s) and c["m"][s].get("med_ms"))
               for s in ("spectrafit", "lmfit")}

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
    free, con = eels["free"], eels["constrained"]
    ms, kappa = eels.get("multistart", {}), eels.get("condition_number", {})
    ms_starts = ms.get("starts", [])
    ms_counts = {k: sum(1 for r in ms_starts if r.get("outcome") == k)
                 for k in ("better_minimum", "flat_valley", "neither")}
    profs = eels.get("profiles", {})
    iv_free = profs.get("free", {}).get("intervals", {})
    iv_con = profs.get("constrained", {}).get("intervals", {})
    f95, c95, c68 = iv_free.get("95", {}), iv_con.get("95", {}), iv_con.get("68", {})
    free_grid = eels.get("profile_protocol", {}).get("grids", {}).get("free", {})
    free_width = (free_grid.get("to", 0) - free_grid.get("from", 0) if f95.get("open_lower") or f95.get("open_upper")
                  else f95.get("width"))
    con_width = c95.get("width_bisected")
    con_half68 = c68.get("width_bisected", float("nan")) / 2
    # The free fit from the default start against the lowest RSS the free profile and the
    # seeded starts reach (eels-04, eels-05). Its success flag and termination reason are
    # recorded as stored; the EELS result stores no stationarity measure for it.
    gmin = profs.get("free", {}).get("global_minimum", {})
    ms_best = min((r["rss"] for r in ms_starts), default=float("nan"))
    free_default = {"L3": free["step_l3"]["value"], "rss": free["rss"], "r2": free["r_squared"],
                    "success": free.get("success"), "termination": free.get("message"),
                    "stationarity": free.get("stationarity"),
                    "best_of_seeded_starts_rss": ms_best,
                    "profile_minimum": {"L3": gmin.get("a"), "rss": gmin.get("rss"),
                                        "at_bound": gmin.get("at_bound")}}
    below_default = bool(gmin) and gmin["rss"] < min(free["rss"], ms_best)

    # The interop target's record, read from the stored results (as the timing is), also under --check.
    interop_path = RESULTS / INTEROP_JSON
    interop = json.loads(interop_path.read_text()) if interop_path.exists() else None

    def c(cid: str, source: str, statement: str, observed: object, ok: bool) -> dict:
        return {"id": cid, "source": source, "statement": statement, "observed": observed, "ok": bool(ok)}

    reg, arc = "regenerated", f"measured-{TIMING_VERSION}"
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
        c("bench-01", arc, "160 cases", len(cases), len(cases) == 160),
        c("bench-02", arc, "14.4 times faster than lmfit in geometric mean, 11.6 in harmonic mean",
          {"geomean": _gm(speed), "harmonic": len(speed) / sum(1 / x for x in speed)},
          round(_gm(speed), 1) == 14.4 and round(len(speed) / sum(1 / x for x in speed), 1) == 11.6),
        c("bench-03", arc, "factors 6.1, 7.7 and 6.5 against the SciPy configurations and 4.7 against JAX",
          ratio, [round(ratio[s], 1) for s in
                  ("scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox", "jax")] == [6.1, 7.7, 6.5, 4.7]),
        c("bench-04", arc, "fastest backend on 140 of the 160 cases", fastest, fastest == 140),
        c("bench-05", arc, "by category the speedup ranges from 4.9 to 26.4; tied-parameter cases 14.0",
          {k: round(v, 2) for k, v in cat.items()},
          round(min(cat.values()), 1) == 4.9 and round(max(cat.values()), 1) == 26.4
          and round(cat["tied"], 1) == 14.0),
        c("bench-06", arc, "the headline moves between 14.1 and 14.5 across the five depths",
          depth, len(depth) == 5 and round(min(depth), 1) == 14.1 and round(max(depth), 1) == 14.5),
        c("bench-07", arc, "14.16 with a standard deviation of 0.31 across 50 seeds",
          {"n": len(seeds), "mean": st.mean(seeds), "sd": st.stdev(seeds)},
          len(seeds) == 50 and round(st.mean(seeds), 2) == 14.16 and round(st.stdev(seeds), 2) == 0.31),
        c("bench-08", arc, "the 20 cases it loses are the optimisation functions",
          sorted(lost), lost == {"optfn"} and len(cases) - fastest == 20),
        c("bench-09", arc, "excluding the optimisation-function category lowers the headline to 13.2",
          no_optfn, round(no_optfn, 1) == 13.2),
        c("bench-10", arc, "against the three SciPy configurations the harmonic means are 1.3 to 2.0",
          {s: round(hm_ratio[s], 3) for s in scipy_cfg},
          round(min(hm_ratio[s] for s in scipy_cfg), 1) == 1.3 and round(max(hm_ratio[s] for s in scipy_cfg), 1) == 2.0),
        c("bench-11", arc, "against JAX the geometric and harmonic means are 4.7 and 4.1",
          {"geomean": ratio["jax"], "harmonic": hm_ratio["jax"]},
          round(ratio["jax"], 1) == 4.7 and round(hm_ratio["jax"], 1) == 4.1),
        c("bench-12", arc, "the median solve takes 0.54 ms with spectrafit-core and 7.1 ms with lmfit",
          medians, round(medians["spectrafit"], 2) == 0.54 and round(medians["lmfit"], 1) == 7.1),
        c("agree-02", arc, "CX-017: the six backends report the same coefficient of determination to three "
          "significant figures; parameter errors lie between 660 % and 1.3 million %",
          {"r2": cx_r2, "param_err_pct": cx_err},
          len(cx) == 6 and {f"{v:.3g}" for v in cx_r2.values()} == {"0.962"}
          and 660 <= min(cx_err.values()) < 670 and 1.25e6 <= max(cx_err.values()) < 1.35e6),
        c("agree-01", arc, "on 94 cases the six backends agree to within 0.74 percentage points; 37 remain",
          {"n": agree["n_well_conditioned"], "spread": agree["max_cross_backend_spread_pct_points"],
           "excluded": agree["excluded_stratum"]["n"]},
          agree["n_well_conditioned"] == 94 and agree["excluded_stratum"]["n"] == 37
          and round(agree["max_cross_backend_spread_pct_points"], 2) == 0.74),
        c("bias-01", arc, "about 139 microseconds against 6.5 for plain array code, roughly a factor of 21",
          bias["bias"], round(bias["bias"]["wheel_us"]) == 139 and round(bias["bias"]["numpy_us"], 1) == 6.5
          and round(bias["bias"]["ratio"]) == 21),
        c("bias-02", arc, "35 registered kernels: 24 agree bit for bit, 11 do not; all of those "
          "to better than 4e-16",
          {"n": len(dev), "exact": bias["parity"]["n_exact"], "nonzero": len(nonzero),
           "largest_two": nonzero[-2:]},
          len(dev) == 35 and bias["parity"]["n_exact"] == 24 and len(nonzero) == 11
          and nonzero[-1] < 4e-16),
        c("eels-01", reg, "the Fe L2,3 edge of Fe2O3 is fitted between 700 and 735 eV",
          eels["spectrum"]["window_ev"], eels["spectrum"]["window_ev"] == [700.0, 735.0]),
        c("eels-04", reg, "the L3 step is 1701 \u00b1 34 counts with the relationships (R^2 0.99888); without "
          "them the fit from the default start ends at RSS 21.93e6 (R^2 0.99890), while the profile reaches "
          "RSS 20.74e6 at L3 = 1000",
          {"L3": con["step_l3"], "r2_constrained": con["r_squared"], "free_default_start": free_default},
          round(con["step_l3"]["value"]) == 1701 and round(con["step_l3"]["stderr"]) == 34
          and round(con["r_squared"], 5) == 0.99888 and round(free["r_squared"], 5) == 0.99890
          and round(free["rss"] / 1e6, 2) == 21.93 and below_default
          and gmin["a"] == 1000 and round(gmin["rss"] / 1e6, 2) == 20.74),
        c("eels-05", reg, "the L3 branching ratio is 0.820 \u00b1 0.002 with the relationships; without them "
          "no value is stated, because the default-start fit does not reach the lowest RSS found (see eels-04)",
          {"constrained": con["branching_l3"], "default_start_reaches_lowest_rss_found": not below_default},
          round(con["branching_l3"]["value"], 3) == 0.820 and round(con["branching_l3"]["stderr"], 3) == 0.002
          and below_default),
        c("eels-06", reg, "the 95 % profile interval of the L3 step is 600 counts wide without the relationships "
          "and 74.45 with them, a ratio of 8.06; both intervals are boundary_affected",
          {"free_width": f95.get("width"), "constrained_width": con_width,
           "ratio": None if not (con_width and f95.get("width")) else f95["width"] / con_width,
           "boundary_affected": {"free": f95.get("boundary_affected"), "constrained": c95.get("boundary_affected")}},
          f95.get("closed", False) and c95.get("closed", False) and con_width is not None
          and round(f95["width"]) == 600 and round(con_width, 2) == 74.45
          and round(f95["width"] / con_width, 2) == 8.06
          and f95.get("boundary_affected") is True and c95.get("boundary_affected") is True),
        c("eels-07", reg, "the independent fit is also run from 50 seeded starts; the seed, the sampling rule "
          "and, per start, the residual, the L3 step, the success flag and the distance of every parameter "
          "to its bounds are recorded",
          {"n": len(ms_starts), "seed": ms.get("seed"), "counts": ms_counts, "outcome": ms.get("outcome")},
          len(ms_starts) == 50 and isinstance(ms.get("seed"), int) and bool(ms.get("sampling"))
          and all({"rss", "step_l3", "success", "bounds", "outcome"} <= r.keys() for r in ms_starts)
          and sum(ms_counts.values()) == 50
          and ms.get("outcome") in {"better_minimum", "flat_valley", "confirmation"}
          and (ms.get("outcome") == "better_minimum") == (ms_counts["better_minimum"] > 0)),
        c("eels-08", reg, "the condition number of J^T J is recorded for both fits, with the condition number "
          "of J as its square root", kappa,
          all(isinstance(kappa.get(k, {}).get("jtj"), float) and kappa[k]["jtj"] > 0
              and abs(kappa[k]["j"] ** 2 / kappa[k]["jtj"] - 1) < 1e-9 for k in ("free", "constrained"))),
        c("eels-09a", reg, "fitted independently, the 95 % profile interval of the L3 step is recorded on its grid "
          "(threshold of 1.2.0 dropped; README, Deviations in 1.3.0)", f95,
          bool(f95) and {"lower", "upper", "closed", "width"} <= f95.keys()),
        c("eels-09b", reg, "with the four relationships the 95 % profile interval of the L3 step is closed on its "
          "grid; its width and its ratio to the interval without them (the free grid if that interval is open) "
          "are recorded (threshold of 1.2.0 dropped; README, Deviations in 1.3.0)",
          {"constrained": c95, "free_width_used": free_width,
           "ratio": None if not (con_width and free_width) else free_width / con_width},
          bool(c95) and c95.get("closed", False) and con_width is not None and free_width is not None),
        c("eels-09c", reg, "the 68 % half-width of the constrained profile and the reported standard error of the "
          "L3 step are recorded (threshold of 1.2.0 dropped; README, Deviations in 1.3.0)",
          {"half_width": con_half68, "stderr": con["step_l3"]["stderr"]},
          math.isfinite(con_half68) and math.isfinite(con["step_l3"]["stderr"])),
        c("eels-10", reg, "the bound status of the reported fits is recorded",
          eels.get("at_bound"),
          isinstance(eels.get("at_bound"), dict)
          and {"free", "constrained", "free_default_start"} <= set(eels["at_bound"])),
        *interop_claims(interop, c, reg),
    ]


def interop_claims(rec: dict | None, c, reg: str) -> list[dict]:
    """Claims of the interop-fe-l23 target (from 1.3.1).

    The thresholds were fixed after the first run (cloud sandbox, 20 Nov 2026), not before it.
    """
    if rec is None:
        missing = f"{INTEROP_JSON.as_posix()} not found; run --targets interop-fe-l23"
        return [c(f"interop-0{i}", reg, s, missing, False) for i, s in enumerate(INTEROP_STATEMENTS, 1)]
    sfc, lm, cmp_ = rec["sfc"], rec["lmfit"], rec["comparison"]

    def term(b: dict) -> dict:
        return {"success": b["termination"]["success"], "message": b["termination"]["message"],
                "gn_decrease_rel": b["stationarity"]["gn_decrease_rel"],
                "stationary": b["stationarity"]["stationary"]}

    gaps = {"sfc": sfc["model_gap_lmfit_vs_engine"], "lmfit": lm["model_gap_lmfit_vs_engine"]}
    s1, s2, s3, s4 = INTEROP_STATEMENTS
    return [
        c("interop-01", reg, s1, {"sfc": term(sfc), "lmfit": term(lm)},
          all(b["termination"]["success"] is True and b["stationarity"]["stationary"] is True
              for b in (sfc, lm))),
        c("interop-02", reg, s2, {"rss_sfc": sfc["rss"], "rss_lmfit": lm["rss"],
                                  "rss_rel_diff": cmp_["rss_rel_diff"]},
          abs(cmp_["rss_rel_diff"]) <= 1e-6),
        c("interop-03", reg, s3, {"param_rel_diff_max": cmp_["param_rel_diff_max"],
                                  "argmax": cmp_["param_rel_diff_argmax"]},
          cmp_["param_rel_diff_max"] <= 1e-3),
        c("interop-04", reg, s4, gaps, all(g <= 1e-10 for g in gaps.values())),
    ]


INTEROP_STATEMENTS = (
    ("the Fe L2,3 constrained graph JSON is fitted by SpectraFit-Core and by lmfit; both report success "
     "and both endpoints are stationary by the script's measure (Gauss-Newton decrease / RSS <= 1e-6)"),
    "the RSS of the two endpoints differs by at most 1e-6 relative",
    "the largest relative difference of a free parameter between the two endpoints is at most 1e-3",
    ("the lmfit translation equals the engine model (spectrafit_core.evaluate) to 1e-10 relative at both "
     "endpoints"),
)


# --------------------------------------------------------------------------- optional timing


def benchmark(source: Path, reps: int) -> dict:
    """Re-measure one rung on this host. Reported, never substituted."""
    workdir = CACHE / "benchmark-run"
    workdir.mkdir(parents=True, exist_ok=True)
    env = os.environ | {"PYTHONPATH": str(harness_path(source))}
    print(f"  benchmarking 160 cases x 6 backends at --reps {reps}; the measured rung took "
          "70 minutes at --reps 4 on terra (16 cores)")
    run([sys.executable, "-m", "oracles.cli", "run", "--reps", str(reps)], cwd=workdir, env=env)
    manifests = sorted(workdir.rglob("manifest.json"), key=lambda p: p.stat().st_mtime)
    if not manifests:
        raise SystemExit("the benchmark wrote no manifest.json")
    m = json.loads(manifests[-1].read_text())
    return {"run_dir": str(manifests[-1].parent), "reps": reps,
            "geomean_speedup_vs_baseline": m.get("geomean_speedup_vs_baseline"),
            "harmonic_mean_speedup_vs_baseline": m.get("harmonic_mean_speedup_vs_baseline"),
            "max_abs_delta_r2": m.get("max_abs_delta_r2"), "n_cases": m.get("n_cases")}


# --------------------------------------------------------------------------- examples


def verify_examples() -> dict:
    """The mirrored files and the generated README must be the ones ``examples-manifest.json`` records."""
    manifest = json.loads(EXAMPLES_MANIFEST.read_text())
    generated = manifest["generated"]
    listed = {f["path"] for f in manifest["files"]} | {generated["path"]}
    present = {p.relative_to(HERE).as_posix() for p in EXAMPLES.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts}
    if listed != present:
        raise SystemExit(f"examples/ differs from the manifest: missing {sorted(listed - present)}, "
                         f"not listed {sorted(present - listed)}")
    for f in manifest["files"]:
        got = sha256(HERE / f["path"])
        if got != f["sha256"]:
            raise SystemExit(f"{f['path']} has sha256 {got}, the manifest records {f['sha256']}")
    if sha256(HERE / generated["path"]) != generated["sha256"]:
        raise SystemExit(f"{generated['path']} differs from the one scripts/mirror_gallery.py generated")
    return manifest


def run_examples(versions: dict[str, str], timeout_s: float) -> dict:
    """Run every example of the mirror once, as a reader would, and record the outcome.

    The scripts run from a copy in ``.cache/examples-run/`` so the figures they write
    (``_static/``) never enter the mirror. Each runs as ``python <script>`` with the copy
    as working directory, so the sibling import ``from _plotting import ...`` resolves.
    """
    manifest = verify_examples()
    work = CACHE / "examples-run"
    if work.exists():
        shutil.rmtree(work)
    CACHE.mkdir(exist_ok=True)
    shutil.copytree(EXAMPLES, work)
    env = os.environ | {
        "MPLBACKEND": "Agg",
        "PYTHONPATH": "",  # the installed wheel only
        "SOURCE_DATE_EPOCH": str(PINS["source"]["source_date_epoch"]),
    }
    env.pop("SPECTRAFIT_GALLERY_THEME", None)  # light pass, as the gallery pages show it
    static = work / "_static"
    scripts = []
    for f in manifest["files"]:
        if f["role"] not in manifest["run_roles"]:
            continue
        rel = f["path"].removeprefix("examples/")
        entry: dict = {"path": f["path"], "role": f["role"], "sha256": f["sha256"]}
        if f["path"] in EXAMPLES_SKIP:
            print(f"  skipped    {f['path']}")
            scripts.append(entry | {"status": "skipped", "skip_reason": EXAMPLES_SKIP[f["path"]],
                                    "exit_code": None, "timed_out": False, "wall_s": None})
            continue
        before = set(static.glob("*.png")) if static.exists() else set()
        start = time.perf_counter()
        try:
            proc = subprocess.run([sys.executable, rel], cwd=work, env=env, capture_output=True,
                                  text=True, timeout=timeout_s, check=False)
            code, timed_out, stderr = proc.returncode, False, proc.stderr
        except subprocess.TimeoutExpired as exc:
            err = exc.stderr or b""
            code, timed_out = None, True
            stderr = err.decode(errors="replace") if isinstance(err, bytes) else err
        wall = time.perf_counter() - start
        after = set(static.glob("*.png")) if static.exists() else set()
        entry |= {"status": "ok" if code == 0 else "failed", "exit_code": code, "timed_out": timed_out,
                  "wall_s": round(wall, 3), "figures": sorted(p.name for p in after - before)}
        if code != 0:
            entry["stderr_tail"] = stderr.splitlines()[-STDERR_TAIL_LINES:]
        print(f"  {entry['status']:<10s} {f['path']}  exit {code}  {wall:.1f} s")
        scripts.append(entry)
    count = {s: sum(e["status"] == s for e in scripts) for s in ("ok", "failed", "skipped")}
    return {
        "schema": "examples-smoke/1",
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "reproduce.py " + " ".join(sys.argv[1:]),
        "source": manifest["source"],
        "manifest_files_sha256": manifest["files_sha256"],
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu": cpu_model(), "packages": versions,
                        "env": {k: env.get(k) for k in ("MPLBACKEND", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                         "MKL_NUM_THREADS", "RAYON_NUM_THREADS")}},
        "timeout_s": timeout_s,
        "counts": count,
        "scripts": scripts,
    }


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
        "own_scripts_sha256": {p.relative_to(HERE).as_posix(): sha256(p) for p in OWN_SCRIPTS.values()},
        "label_patches": {"edits": {k: [list(e) for e in v] for k, v in LABEL_PATCHES.items()},
                          "scripts": LABEL_PATCH_RECORD},
        "eels_spectrum_sha256": sha256(source / EELS_SPECTRUM),
        "upstream_scripts_sha256": {
            s: sha256(source / UPSTREAM_FIGS / s)
            for s in sorted({m for m, _ in MEASUREMENTS} | {f"{f}.py" for f in FIGURE_MAP}
                            | {"extract_bench_summary.py"})
        },
        "timing": dict(PINS["timing"]),
        "timing_inputs_sha256": dict(PINS["timing_inputs"]),
        "archived_inputs_sha256": dict(PINS["archived_inputs"]),
        **extra,
    }


def write_checksums(root: Path = HERE) -> None:
    """One manifest over everything in ``root`` that a reader may want to verify."""
    skip_dirs = {".git", ".cache", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "cache"}
    lines = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or skip_dirs & set(rel.parts) or rel.name in {"checksums.sha256", ".DS_Store"}:
            continue
        lines.append(f"{sha256(path)}  {rel.as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- targets

TARGETS = ("core", "nist-both", "usage", "gallery", "eels-far", "bench-tolerance", "bench-ablation",
           "audit-stationarity", "interop-fe-l23", "overview")
# The benchmark runs of the solver audit and the Jacobian ablation, at the harness defaults.
BENCH_REPS, BENCH_MC = 5, 20
ABLATION_BACKENDS = "spectrafit,spectrafit_fd,lmfit,jax,scipy-ls-lm,scipy-ls-trf,scipy-ls-dogbox"
AUDIT_BACKENDS = "spectrafit,scipy-ls-trf,lmfit"
DRY_RUN: dict | None = None


def resolve_targets(spec: str) -> list[str]:
    names = list(TARGETS) if spec == "all" else [t.strip() for t in spec.split(",") if t.strip()]
    unknown = [t for t in names if t not in TARGETS]
    if unknown:
        raise SystemExit(f"unknown targets {unknown}; choose from {', '.join(TARGETS)} or all")
    return [t for t in TARGETS if t in names]


def setup_dry_run(args: argparse.Namespace) -> dict:
    """Point every output below ``--out`` and name the candidate instead of the pinned release."""
    global CACHE, RESULTS, FIGURES
    missing = [f for f, v in (("--source", args.source), ("--source-commit", args.source_commit),
                              ("--out", args.out)) if not v]
    if missing:
        raise SystemExit(f"--dry-run needs {', '.join(missing)}")
    version = os.environ.get("SPECTRAFIT_RC_VERSION")
    digest = os.environ.get("SPECTRAFIT_RC_SHA256")
    if not version or not digest:
        raise SystemExit("--dry-run needs SPECTRAFIT_RC_VERSION and SPECTRAFIT_RC_SHA256 in the environment")
    out = args.out.resolve()
    if out.is_relative_to(HERE):
        raise SystemExit(f"--out {out} lies inside this repository; a dry run writes nothing here")
    CACHE = (args.cache or out / "cache").resolve()
    if CACHE.is_relative_to(HERE):
        raise SystemExit(f"--cache {CACHE} lies inside this repository")
    RESULTS, FIGURES = out / "results", out / "figures"
    commit = run(["git", "rev-parse", f"{args.source_commit}^{{commit}}"], cwd=args.source).strip()
    epoch = int(run(["git", "log", "-1", "--format=%ct", commit], cwd=args.source).strip())
    PINS["source"] = PINS["source"] | {"tag": f"dry-run {version}", "commit": commit,
                                       "source_date_epoch": epoch}
    PINS["packages"]["spectrafit-core"] = version
    PINS["software"]["wheel"] = (f"spectrafit-core=={version}, release candidate, wheel sha256 {digest}, "
                                 "installed by scripts/dry_run_env.py")
    return {"out": str(out), "cache": str(CACHE), "candidate": version, "wheel_sha256": digest,
            "source_commit": commit, "core_extension": run_record.core_extension()}


def target_env(source: Path) -> dict[str, str]:
    return os.environ | {
        "PYTHONPATH": str(CACHE / "harness"),
        "MPLBACKEND": "Agg",
        "SOURCE_DATE_EPOCH": str(PINS["source"]["source_date_epoch"]),
    }


def latest_run_dir(root: Path) -> Path:
    manifests = sorted(root.rglob("manifest.json"), key=lambda p: p.stat().st_mtime)
    if not manifests:
        raise SystemExit(f"no manifest.json below {root}")
    return manifests[-1].parent


def t_nist_both(source: Path, ctx: dict) -> None:
    out = RESULTS / "nist-both"
    with run_record.Run(out, "nist-both", "nist_table2.py --start both",
                        "NIST StRD, 22 datasets, from Start 1 and Start 2, four implementations.") as r:
        run([sys.executable, "nist_table2.py", "--start", "both", "--out", str(out / "nist_table2_both.json")],
            cwd=source / UPSTREAM_FIGS, env=ctx["env"])
        r.notes.append(f"upstream script sha256 {sha256(source / UPSTREAM_FIGS / 'nist_table2.py')}")


# The release's second implementation: the Fe L2,3 constrained graph JSON fitted by lmfit.
INTEROP_SCRIPT = Path("reproducibility") / "interop" / "fe_l23_lmfit.py"
INTEROP_JSON = Path("interop-fe-l23") / "fe_l23_lmfit.json"
# The first run, 20 Nov 2026, in a cloud sandbox (Ubuntu 24.04.5, x86_64, the same uv.lock, compiled
# extension sha256 2e672905...1ebd). Every run is compared with it value by value; a difference is
# reported in the run's README, never adjusted. The model gap was recorded to three digits.
INTEROP_REFERENCE = {
    "sfc.termination.success": True, "sfc.termination.message": "converged_ftol",
    "sfc.rss": 22377890.07972057, "sfc.termination.nfev": 90, "sfc.termination.njev": 64,
    "sfc.stationarity.stationary": True, "sfc.stationarity.gn_decrease_rel": 3.6171712122110617e-07,
    "sfc.stationarity.active": {"l2_c.center": "lower"},
    "lmfit.termination.success": True, "lmfit.termination.message": "Fit succeeded.",
    "lmfit.rss": 22377892.949173372, "lmfit.termination.nfev": 3619,
    "lmfit.stationarity.stationary": True, "lmfit.stationarity.gn_decrease_rel": 6.685595510085018e-07,
    "lmfit.stationarity.active": {"l2_c.center": "lower"},
    "comparison.rss_rel_diff": 1.282271380536494e-07,
    "comparison.param_rel_diff_max": 4.1647585229427766e-04,
    "comparison.param_rel_diff_argmax": "l3_e.sigma",
}
INTEROP_REFERENCE_GAP = {"sfc.model_gap_lmfit_vs_engine": "1.87e-16", "lmfit.model_gap_lmfit_vs_engine": "1.87e-16"}


def _dig(record: dict, dotted: str) -> object:
    node: object = record
    for part in dotted.split("."):
        node = node[part] if isinstance(node, dict) and part in node else None
    return node


def interop_vs_reference(record: dict) -> list[str]:
    """One line per reference quantity: identical, or both values."""
    lines = []
    for key, ref in INTEROP_REFERENCE.items():
        got = _dig(record, key)
        lines.append(f"{key}: {'identical' if got == ref else 'DIFFERS'} (this run {got!r}, reference {ref!r})")
    for key, ref in INTEROP_REFERENCE_GAP.items():
        got = _dig(record, key)
        shown = f"{got:.3g}" if isinstance(got, float) else repr(got)
        lines.append(f"{key} (3 digits): {'identical' if shown == ref else 'DIFFERS'} "
                     f"(this run {got!r}, reference {ref})")
    return lines


def t_interop_fe_l23(source: Path, ctx: dict) -> None:
    out = RESULTS / "interop-fe-l23"
    shown = out.relative_to(HERE) if out.is_relative_to(HERE) else out
    with run_record.Run(out, "interop-fe-l23", f"{INTEROP_SCRIPT.as_posix()} --out {shown}",
                        "Fe L2,3 constrained model, one graph JSON file, fitted by SpectraFit-Core and by "
                        "lmfit (the release's graph_to_lmfit.py translation).") as r:
        run([sys.executable, str(source / INTEROP_SCRIPT), "--out", str(out)], cwd=source, env=ctx["env"])
        r.notes.append(f"upstream script sha256 {sha256(source / INTEROP_SCRIPT)}; translator sha256 "
                       f"{sha256(source / INTEROP_SCRIPT.parent / 'graph_to_lmfit.py')}; graph sha256 "
                       f"{sha256(source / INTEROP_SCRIPT.parent / 'fe_l23_constrained.graph.json')}")
        r.notes.append("header.git_commit and header.git_dirty in fe_l23_lmfit.json are this archive's "
                       "commit and state: the release export in .cache/work has no .git, so the script's "
                       "git call resolves to the enclosing repository; the release commit is pins.toml [source]")
        record = json.loads((out / "fe_l23_lmfit.json").read_text())
        diffs = interop_vs_reference(record)
        n_diff = sum("DIFFERS" in d for d in diffs)
        r.notes.append(f"compared with the reference run of 20 Nov 2026 (cloud sandbox, Ubuntu 24.04.5, x86_64, "
                       f"same uv.lock and compiled extension): {len(diffs) - n_diff} of {len(diffs)} "
                       f"quantities identical")
        r.notes.extend(diffs)


def t_usage(source: Path, ctx: dict) -> None:
    out = RESULTS / "usage"
    with run_record.Run(out, "usage", "scripts/usage_smoke.py",
                        "The usage scripts of usage/, each run unchanged; documented output compared.") as r:
        run([sys.executable, str(HERE / "scripts" / "usage_smoke.py"), "--out", str(out),
             "--spectrum", str(source / EELS_SPECTRUM)], cwd=HERE, env=ctx["env"] | {"PYTHONPATH": ""})
        r.notes.append("record: usage.json")


def t_gallery(source: Path, ctx: dict) -> None:
    out = RESULTS / "gallery"
    with run_record.Run(out, "gallery", "scripts/gallery_run.py",
                        "Every script of examples/, run with the installed wheel; every fit recorded.") as r:
        drift = ["--source", str(ctx["gallery_source"]), "--ref", ctx["gallery_ref"]] if ctx["gallery_ref"] else []
        run([sys.executable, str(HERE / "scripts" / "gallery_run.py"), "--out", str(out),
             "--work", str(CACHE / "gallery-run"), "--spectrum-dir", str(source / EELS_SPECTRUM.parent), *drift],
            cwd=HERE, env=ctx["env"] | {"PYTHONPATH": ""})
        r.notes.append("record: gallery.json; figures: figures/; drift check against "
                       + (f"{ctx['gallery_ref']} of {ctx['gallery_source']}" if drift else "the manifest only"))


def t_eels_far(source: Path, ctx: dict) -> None:
    out = RESULTS / "eels-far"
    with run_record.Run(out, "eels-far", f"scripts/eels_far_starts.py --workers {ctx['workers']}",
                        "Bounded Fe L2,3 fit from 500 far starts, free and constrained model.") as r:
        run([sys.executable, str(HERE / "scripts" / "eels_far_starts.py"), "--spectrum",
             str(source / EELS_SPECTRUM), "--out", str(out), "--workers", str(ctx["workers"])],
            cwd=HERE, env=ctx["env"] | {"PYTHONPATH": ""})
        r.notes.append("records: eels_far.json (per fit), summary.json (per model and arm)")


def t_bench_tolerance(source: Path, ctx: dict) -> None:
    out = RESULTS / "bench-tolerance"
    script = str(HERE / "bench" / "common_tolerance.py")
    with run_record.Run(out, "bench-tolerance", f"bench/common_tolerance.py run --mode default|common "
                        f"--reps {BENCH_REPS}; analyse",
                        "160 cases x 6 backends at the default and at the common stopping tolerance.") as r:
        for mode in ("default", "common"):
            run([sys.executable, script, "run", "--mode", mode, "--reps", str(BENCH_REPS), "--out", str(out)],
                cwd=CACHE, env=ctx["env"])
        run([sys.executable, script, "analyse", "--out", str(out)], cwd=CACHE, env=ctx["env"])
        r.notes.append("records: default.json, common.json, summary.json, report.md")


def t_bench_ablation(source: Path, ctx: dict) -> None:
    out = RESULTS / "bench-ablation"
    work = CACHE / "bench-ablation"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    cmd = ["-m", "oracles.cli", "run", "--backends", ABLATION_BACKENDS, "--reps", str(BENCH_REPS),
           "--mc", str(BENCH_MC)]
    with run_record.Run(out, "bench-ablation", "python " + " ".join(cmd),
                        "Analytic (spectrafit) against finite-difference (spectrafit_fd) Jacobian, "
                        "with every comparator, 160 cases.") as r:
        run([sys.executable, *cmd], cwd=work, env=ctx["env"])
        run_dir = latest_run_dir(work / ".spectrafit_reports")
        run([sys.executable, str(HERE / "bench" / "ablation_summary.py"), str(run_dir), str(out)],
            cwd=CACHE, env=ctx["env"])
        shutil.copyfile(run_dir / "manifest.json", out / "manifest.json")
        r.notes.append(f"harness run directory (not copied, {run_dir.name}): results.json sha256 "
                       f"{sha256(run_dir / 'results.json')}")


def t_audit_stationarity(source: Path, ctx: dict) -> None:
    out = RESULTS / "audit-stationarity"
    work = CACHE / "audit-stationarity"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    capture = work / "capture.jsonl"
    cli = ["run", "--tolerance-mode", "common", "--backends", AUDIT_BACKENDS, "--reps", str(BENCH_REPS),
           "--mc", str(BENCH_MC)]
    with run_record.Run(out, "audit-stationarity", "audit/capture_run.py -- " + " ".join(cli)
                        + "; audit/stationarity.py",
                        "Stationarity (Gauss-Newton measure) of every endpoint of spectrafit, scipy trf and "
                        "lmfit at the common tolerance, 156 cases.") as r:
        run([sys.executable, str(HERE / "audit" / "capture_run.py"), "--capture", str(capture), "--", *cli],
            cwd=work, env=ctx["env"])
        run_dir = latest_run_dir(work / ".spectrafit_reports")
        run([sys.executable, str(HERE / "audit" / "stationarity.py"), "--capture", str(capture),
             "--results", str(run_dir / "results.json"), "--out", str(out)], cwd=work, env=ctx["env"])
        r.notes.append(f"capture.jsonl sha256 {sha256(capture)}; results.json sha256 "
                       f"{sha256(run_dir / 'results.json')} (not copied)")


def t_overview(source: Path, ctx: dict) -> None:
    out = RESULTS / "overview"
    with run_record.Run(out, "overview", "scripts/overview.py",
                        "One generated report over every target: overview.html and overview.pdf.") as r:
        run([sys.executable, str(HERE / "scripts" / "overview.py"), "--results", str(RESULTS),
             "--out", str(out)], cwd=HERE, env=ctx["env"] | {"PYTHONPATH": ""})
        r.notes.append("generated from the files of the other targets; every figure has its data file")


TARGET_FUNCS = {"nist-both": t_nist_both, "usage": t_usage, "gallery": t_gallery, "eels-far": t_eels_far,
                "bench-tolerance": t_bench_tolerance, "bench-ablation": t_bench_ablation,
                "audit-stationarity": t_audit_stationarity, "interop-fe-l23": t_interop_fe_l23,
                "overview": t_overview}


def core(args: argparse.Namespace, source: Path, versions: dict, repository: dict) -> int:
    """The regeneration of 1.2.0: NIST tables, Figures 1 to 4, drift and claims."""
    with run_record.Run(CACHE / "core-run", "core", "reproduce.py core",
                        "NIST tables, Figures 1 to 4, EELS fit, drift and claims.") as r:
        pairs = regenerate(source)
        results = CACHE / "check" / "results" if args.check else RESULTS
        figures = CACHE / "check" / "figures" if args.check else FIGURES
        collect(source, results, figures)
        r.notes.append(f"results in {results}, figures in {figures}")
    drift = table_drift(pairs["nist_table2.json"])
    report = claims(results)
    failed = [c for c in report if not c["ok"]]
    shipped = {c["id"]: c["ok"] for c in claims(results, results / "release-archive")
               if c["id"].startswith("nist")}
    for c in report:
        if c["id"] in shipped:
            c["holds_on_release_archive"] = shipped[c["id"]]
    extra: dict = {"repository": repository,
                   "drift_vs_release_archive": {k: v for k, v in drift.items() if k != "moved_cells"}}
    if DRY_RUN:
        extra["dry_run"] = DRY_RUN
    if args.benchmark:
        extra["benchmark_on_this_host"] = benchmark(source, args.reps)
    (results / "drift-report.json").write_text(json.dumps(drift, indent=1) + "\n")
    (results / "claims-report.json").write_text(json.dumps(report, indent=1) + "\n")
    (results / "provenance.json").write_text(json.dumps(provenance(source, versions, extra), indent=1) + "\n")
    shutil.copyfile(CACHE / "core-run" / "run.json", results / "core-run.json")

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
        stored = [n for n in [*REGENERATED_JSON, EELS_JSON] if (RESULTS / n).exists()]
        new_files = [n for n in [*REGENERATED_JSON, EELS_JSON] if n not in stored]
        changed = [n for n in stored if content_digest(RESULTS / n) != content_digest(results / n)]
        print("check      " + ("stored results are current" if not changed
                               else "differs from stored results: " + ", ".join(changed)))
        if new_files:
            print("           not stored yet (compared with nothing): " + ", ".join(new_files))
        return 1 if (changed or failed) else 0
    return 1 if failed else 0


def main() -> int:
    global DRY_RUN
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, help="existing checkout of the pinned tag (default: clone into .cache/)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate into .cache/ and compare with the stored results; write nothing")
    ap.add_argument("--benchmark", action="store_true", help="also re-measure one timing rung on this host")
    ap.add_argument("--reps", type=int, default=4, help="--reps for --benchmark (default 4, the shallowest measured rung)")
    ap.add_argument("--examples", action="store_true",
                    help="only run the mirrored example gallery (examples/) as a smoke run; with --check the "
                         "record goes to .cache/check/results/ and nothing in the repository is written")
    ap.add_argument("--examples-timeout", type=float, default=EXAMPLES_TIMEOUT_S,
                    help=f"timeout per example in seconds (default {EXAMPLES_TIMEOUT_S:.0f})")
    ap.add_argument("--targets", default="core", help=f"comma-separated, from {', '.join(TARGETS)}; or all")
    ap.add_argument("--workers", type=int, default=14, help="worker processes of the eels-far target (default 14)")
    ap.add_argument("--dry-run", action="store_true",
                    help="run against a release candidate (see Dry run above); writes only below --out")
    ap.add_argument("--out", type=Path, help="dry run: output folder outside this repository")
    ap.add_argument("--cache", type=Path, help="dry run: cache folder (default <out>/cache)")
    ap.add_argument("--source-commit", help="dry run: the candidate's commit in --source")
    ap.add_argument("--gallery-ref", help="gallery target: ref of --source whose docs/tutorials/gallery the "
                                          "mirror must equal (drift check), e.g. develop")
    args = ap.parse_args()
    targets = resolve_targets(args.targets)

    repository = repository_state()  # before anything below writes into the tree
    if args.dry_run:
        if args.check or args.examples or args.benchmark:
            raise SystemExit("--dry-run runs targets only; --check, --examples and --benchmark do not apply")
        DRY_RUN = setup_dry_run(args)
    versions = check_environment()
    verify_timing()
    if args.examples:
        return examples_main(args, repository, versions)
    source = ensure_source(args.source)
    print(f"source     {PINS['source']['tag']} @ {PINS['source']['commit'][:12]}")
    print(f"library    spectrafit-core {versions['spectrafit-core']} (wheel), "
          f"{platform.machine()} {platform.system()}, Python {platform.python_version()}")
    print(f"targets    {', '.join(targets)}")
    status = 0
    if "core" in targets:
        status |= core(args, source, versions, repository)
        if args.check:
            return status
    ctx = {"env": target_env(source), "workers": args.workers, "gallery_ref": args.gallery_ref,
           "gallery_source": args.source}
    if any(t in targets for t in TARGET_FUNCS) and not (CACHE / "harness").exists():
        harness_path(source)
    for t in targets:
        if t in TARGET_FUNCS:
            print(f"  target     {t}")
            TARGET_FUNCS[t](source, ctx)
    if DRY_RUN:
        write_checksums(Path(DRY_RUN["out"]))
        print(f"wrote      {DRY_RUN['out']} (dry run; nothing in {HERE} was written)")
        return status
    run([sys.executable, str(HERE / "build_crate.py")], cwd=HERE)
    write_checksums()
    print("wrote      results/, figures/, ro-crate-metadata.json, checksums.sha256")
    return status


def examples_main(args: argparse.Namespace, repository: dict, versions: dict[str, str]) -> int:
    print(f"examples   {EXAMPLES_MANIFEST.name}, spectrafit-core {versions['spectrafit-core']} (wheel), "
          f"timeout {args.examples_timeout:.0f} s per script")
    record = run_examples(versions, args.examples_timeout) | {"repository": repository}
    results = CACHE / "check" / "results" if args.check else RESULTS
    results.mkdir(parents=True, exist_ok=True)
    (results / EXAMPLES_SMOKE).write_text(json.dumps(record, indent=1) + "\n")
    c = record["counts"]
    print(f"\nexamples   {c['ok']} ok, {c['failed']} failed, {c['skipped']} skipped; "
          f"record in {(results / EXAMPLES_SMOKE).relative_to(HERE)}")
    if not args.check:
        run([sys.executable, str(HERE / "build_crate.py")], cwd=HERE)
        write_checksums()
        print("wrote      results/examples-smoke.json, ro-crate-metadata.json, checksums.sha256")
    return 1 if c["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
