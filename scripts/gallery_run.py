#!/usr/bin/env python3
"""Run every script of the example gallery with the installed wheel and record each of its fits.

The mirror ``examples/`` is copied to ``--work``, laid out as in spectrafit-core
(``docs/tutorials/gallery/``), with the measured spectrum at
``reproducibility/spectra/eelsdb-fe2o3-l23/`` as the release ships it, so a script that
reads it relative to its own path finds it. Each script whose role is ``example`` or
``snippet`` in ``examples-manifest.json`` then runs once, unchanged, as ``python <script>``
with that folder as working directory, ``MPLBACKEND=Agg`` and a timeout; a small bootstrap
wraps ``spectrafit_core.fit``, ``fit_fast`` and ``GlobalFitGraph.fit`` before the script is
executed and records every call. The wrappers return the library's result unchanged.

Recorded per fit: the call (``fit``, ``fit_fast`` or ``GlobalFitGraph.fit``), the solver
requested, fitted parameters with standard errors, ``success``, the termination message,
iterations and function evaluations, RSS (weighted by ``1/sigma`` when the data carry
``sigma``), the condition number of ``J^T J`` the library reports, wall time, and the
Gauss-Newton stationarity of the endpoint by the definitions of ``audit/stationarity.py``
(central-difference Jacobian of ``spectrafit_core.evaluate`` over the free parameters, step
``6.06e-6 max(|theta|, 1e-3)``; active bound by the ``1e-4`` rule; held = active with the
gradient pointing out of the box; GN predicted decrease over the components not held divided
by RSS; stationary iff ``<= 1e-6``; an RSS below ``1e-24 sum(y^2)`` counts as zero and as
stationary). Ties (``expr_edges`` and ``Parameter.expr``) are applied to every evaluated
parameter vector, because ``spectrafit_core.evaluate`` takes the tied values as given. Joint fits
of several datasets (``GlobalFitGraph.fit``) and n-D data get no stationarity value; an IRLS fit
is measured on the plain RSS and marked as such, since the measure is not its criterion.

Recorded per script: exit code, wall time, the figures it wrote (copied to
``<out>/figures/``) and its fits. ``<out>/gallery.json`` holds everything; the script exits
non-zero if any script fails.

Drift check: every mirrored file must hash to the git blob id ``examples-manifest.json``
records; with ``--source`` (a spectrafit-core checkout) and ``--ref``, also to the blob of the
same path in ``docs/tutorials/gallery`` at that ref. The result is recorded per file.
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
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EXAMPLES = HERE / "examples"
MANIFEST = HERE / "examples-manifest.json"
GALLERY = Path("docs") / "tutorials" / "gallery"
SPECTRUM = Path("reproducibility") / "spectra" / "eelsdb-fe2o3-l23"
TIMEOUT_S = 600.0

BOOTSTRAP = r'''
import ast, json, math, os, runpy, sys, time
import numpy as np
import spectrafit_core as sc

AT_BOUND_REL, H_REL, THETA_FLOOR, GN_TOL, RSS_ZERO_REL = 1e-4, 6.06e-6, 1e-3, 1e-6, 1e-24
RECORDS = []


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _graph(g):
    return g if isinstance(g, sc.FitGraph) else sc.FitGraph.model_validate(g)


def _datasets(data):
    if isinstance(data, sc.MeasurementData):
        return [data]
    if isinstance(data, dict):
        return [sc.MeasurementData.model_validate(data)]
    return [d if isinstance(d, sc.MeasurementData) else sc.MeasurementData.model_validate(d) for d in data]


def _ties(graph):
    out = [(f"{e.target_node}.{e.target_param}", e.expression) for e in graph.expr_edges]
    for node in graph.nodes:
        for name, par in node.parameters.items():
            if getattr(par, "expr", None):
                out.append((f"{node.id}.{name}", par.expr))
    return [(k, ast.parse(x, mode="eval").body) for k, x in out]


def _expr(node, p):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return float(p[f"{node.value.id}.{node.attr}"])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_expr(node.operand, p)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        a, b = _expr(node.left, p), _expr(node.right, p)
        match node.op:
            case ast.Add():
                return a + b
            case ast.Sub():
                return a - b
            case ast.Mult():
                return a * b
            case _:
                return a / b
    raise ValueError(f"expression outside the tie grammar: {ast.dump(node)}")


def _apply_ties(ties, p):
    for _ in range(len(ties)):  # enough passes for any acyclic chain of ties
        for k, node in ties:
            p[k] = _expr(node, p)
    return p


def _free(graph):
    tied = {f"{e.target_node}.{e.target_param}" for e in graph.expr_edges}
    out = []
    for node in graph.nodes:
        for name, par in node.parameters.items():
            key = f"{node.id}.{name}"
            if par.vary and key not in tied and not getattr(par, "expr", None):
                out.append((key, float(par.min), float(par.max), float(par.value)))
    return out


def stationarity(graph, data, values):
    ds = _datasets(data)
    if len(ds) != 1:
        return {"computed": False, "reason": "more than one dataset"}
    d = ds[0]
    y = np.asarray(d.y, dtype=float)
    xs = np.asarray(d.x, dtype=float)
    if xs.reshape(y.size, -1).shape[1] != 1:
        return {"computed": False, "reason": "n-D data: spectrafit_core.evaluate is 1-D only"}
    w = 1.0 / np.asarray(d.sigma, dtype=float) if d.sigma is not None else np.ones_like(y)
    free = _free(graph)
    if not free:
        return {"computed": False, "reason": "no free parameter"}
    def model(p):
        return np.asarray(sc.evaluate(graph, p, d), dtype=float)
    ties = _ties(graph)
    p0 = _apply_ties(ties, dict(values))
    r = w * (y - model(p0))
    rss = float(r @ r)
    zero = rss <= RSS_ZERO_REL * float((w * y) @ (w * y))
    theta = np.array([p0[k] for k, *_ in free])
    scale = np.maximum(np.abs(theta), THETA_FLOOR)
    h = H_REL * scale
    jac = np.empty((y.size, theta.size))
    for i, (k, *_r) in enumerate(free):
        up, dn = dict(p0), dict(p0)
        up[k] += h[i]
        dn[k] -= h[i]
        _apply_ties(ties, up)
        _apply_ties(ties, dn)
        jac[:, i] = w * (model(up) - model(dn)) / (2.0 * h[i])
    if not np.all(np.isfinite(jac)):
        return {"computed": False, "reason": "non-finite Jacobian", "rss": rss}
    act = {}
    for k, lo, hi, guess in free:
        two = math.isfinite(lo) and math.isfinite(hi)
        tol = AT_BOUND_REL * ((hi - lo) if two else max(abs(guess), 1.0))
        if p0[k] - lo <= tol:
            act[k] = "lower"
        elif hi - p0[k] <= tol:
            act[k] = "upper"
    g = -2.0 * jac.T @ r
    held = np.array([(act.get(k) == "lower" and g[i] > 0) or (act.get(k) == "upper" and g[i] < 0)
                     for i, (k, *_r) in enumerate(free)], dtype=bool)
    js = jac[:, ~held] * scale[~held]
    if js.shape[1] and not zero:
        step, *_ = np.linalg.lstsq(js, r, rcond=None)
        gn = float(np.sum((js @ step) ** 2) / rss)
    else:
        gn = 0.0
    return {"computed": True, "ties_applied": [k for k, _ in ties], "rss": rss, "zero_rss": bool(zero),
            "gn_decrease_rel": None if zero else gn,
            "stationary": bool(zero or gn <= GN_TOL), "active": act,
            "held": [k for (k, *_r), hd in zip(free, held) if hd], "n_free": len(free)}


def record(call, graph, data, options, result, wall):
    rec = {"call": call, "wall_s": wall,
           "solver": getattr(options, "solver", None) if options is not None else "default"}
    try:
        rec |= {"success": bool(result.success), "message": str(result.message),
                "n_iter": result.n_iter, "nfev": result.n_func_evals,
                "condition_number_jtj": _num(getattr(result, "condition_number", None)),
                "r_squared": _num(getattr(result, "r_squared", None)), "chi2": _num(getattr(result, "chi2", None)),
                "parameters": {k: {"value": _num(v.value), "stderr": _num(v.stderr), "vary": bool(v.vary)}
                               for k, v in result.parameters.items()}}
        if call == "GlobalFitGraph.fit":
            rec["stationarity"] = {"computed": False, "reason": "joint fit of several datasets"}
        else:
            rec["stationarity"] = stationarity(_graph(graph), data, {k: v.value for k, v in result.parameters.items()})
            if str(rec["solver"]).startswith("irls"):
                rec["stationarity"]["objective"] = ("measured on the plain RSS; the solver minimises an "
                                                    "IRLS-reweighted cost, so the measure is not its criterion")
    except Exception as exc:  # recorded with the fit; the script itself is not affected
        rec["record_error"] = f"{type(exc).__name__}: {exc}"
    RECORDS.append(rec)


def wrap(fn, call):
    def inner(graph, data, options=None, *a, **kw):
        t = time.perf_counter()
        res = fn(graph, data, options, *a, **kw) if options is not None else fn(graph, data, *a, **kw)
        wall = time.perf_counter() - t
        out = res[0] if call == "fit_fast" and isinstance(res, tuple) else res
        record(call, graph, data, options, out, wall)
        return res
    return inner


sc.fit = wrap(sc.fit, "fit")
sc.fit_fast = wrap(sc.fit_fast, "fit_fast")
_gfit = sc.GlobalFitGraph.fit


def gfit(self, datasets, options=None, *a, **kw):
    t = time.perf_counter()
    res = _gfit(self, datasets, options, *a, **kw) if options is not None else _gfit(self, datasets, *a, **kw)
    record("GlobalFitGraph.fit", self, datasets, options, res, time.perf_counter() - t)
    return res


sc.GlobalFitGraph.fit = gfit
script, out = sys.argv[1], sys.argv[2]
sys.argv = [script]
sys.path[0] = os.path.dirname(os.path.abspath(script))  # as `python <script>.py`: the script's own folder
try:
    runpy.run_path(script, run_name="__main__")
finally:
    with open(out, "w") as fh:
        json.dump(RECORDS, fh)
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def drift_check(source: Path | None, ref: str | None, manifest: dict) -> dict:
    """Blob id of every mirrored file against the manifest and, with ``--source``, against ``--ref``."""
    rec: dict = {"files": {}}
    if source is not None and ref:
        rec["ref"] = ref
        rec["ref_commit"] = subprocess.run(["git", "rev-parse", ref], cwd=source, capture_output=True,
                                           text=True, check=True).stdout.strip()
    for f in manifest["files"]:
        row = {"manifest": f["git_blob"], "mirrored": git_blob_id((HERE / f["path"]).read_bytes())}
        if "ref" in rec:
            rel = f["path"].removeprefix("examples/")
            proc = subprocess.run(["git", "rev-parse", f"{ref}:{(GALLERY / rel).as_posix()}"], cwd=source,
                                  capture_output=True, text=True, check=False)
            row["ref"] = proc.stdout.strip() if proc.returncode == 0 else None
        row["equal"] = len(set(row.values())) == 1
        rec["files"][f["path"]] = row
    rec["equal"] = all(r["equal"] for r in rec["files"].values())
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--spectrum-dir", type=Path, help="the release's reproducibility/spectra/eelsdb-fe2o3-l23")
    ap.add_argument("--source", type=Path, help="spectrafit-core checkout for the drift check")
    ap.add_argument("--ref", help="ref of --source whose gallery the mirror must equal")
    ap.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    for f in manifest["files"]:
        if sha256(HERE / f["path"]) != f["sha256"]:
            raise SystemExit(f"{f['path']} differs from examples-manifest.json")
    drift = drift_check(args.source, args.ref, manifest)
    if args.work.exists():
        shutil.rmtree(args.work)
    gallery = args.work / GALLERY
    shutil.copytree(EXAMPLES, gallery)
    if args.spectrum_dir:
        shutil.copytree(args.spectrum_dir, args.work / SPECTRUM)
    boot = args.work / "_gallery_bootstrap.py"
    boot.write_text(BOOTSTRAP)
    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    env = os.environ | {"MPLBACKEND": "Agg", "PYTHONPATH": ""}
    env.pop("SPECTRAFIT_GALLERY_THEME", None)
    static = gallery / "_static"
    scripts = []
    for f in manifest["files"]:
        if f["role"] not in manifest["run_roles"]:
            continue
        rel = f["path"].removeprefix("examples/")
        fits_file = args.work / f"fits-{rel.replace('/', '__')}.json"
        before = {p: p.stat().st_mtime_ns for p in static.glob("*.png")} if static.exists() else {}
        t0 = time.perf_counter()
        try:
            proc = subprocess.run([sys.executable, str(boot), rel, str(fits_file)], cwd=gallery, env=env,
                                  capture_output=True, text=True, timeout=args.timeout, check=False)
            code, timed_out, stderr = proc.returncode, False, proc.stderr
        except subprocess.TimeoutExpired as exc:
            code, timed_out = None, True
            stderr = (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        wall = time.perf_counter() - t0
        new = sorted(p for p in (static.glob("*.png") if static.exists() else [])
                     if before.get(p) != p.stat().st_mtime_ns)
        for p in new:
            shutil.copyfile(p, figures / p.name)
        fits = json.loads(fits_file.read_text()) if fits_file.exists() else []
        entry = {"path": f["path"], "role": f["role"], "sha256": f["sha256"],
                 "status": "ok" if code == 0 else "failed", "exit_code": code, "timed_out": timed_out,
                 "wall_s": round(wall, 3), "figures": [p.name for p in new], "fits": fits}
        if code != 0:
            entry["stderr_tail"] = stderr.splitlines()[-20:]
        n_st = sum(1 for x in fits if x.get("stationarity", {}).get("stationary"))
        n_mc = sum(1 for x in fits if x.get("stationarity", {}).get("computed"))
        print(f"  {entry['status']:<7s} {f['path']:45s} {wall:6.1f} s  fits {len(fits):2d}  "
              f"stationary {n_st} of {n_mc} measured")
        scripts.append(entry)
    import spectrafit_core
    counts = {s: sum(e["status"] == s for e in scripts) for s in ("ok", "failed")}
    record = {
        "schema": "gallery-run/1",
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": platform.node(), "python": platform.python_version(),
        "spectrafit_core": spectrafit_core.__version__,
        "source": manifest["source"], "manifest_files_sha256": manifest.get("files_sha256"),
        "drift_check": drift, "timeout_s": args.timeout, "counts": counts, "scripts": scripts,
    }
    (args.out / "gallery.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"gallery: {counts['ok']} ok, {counts['failed']} failed; drift check equal={drift['equal']}")
    return 1 if counts["failed"] or not drift["equal"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
