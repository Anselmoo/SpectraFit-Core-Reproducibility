#!/usr/bin/env python3
"""The bounded Fe L2,3 fit of ``fig_eels.py`` from 500 far starts, per model and solver.

Starts
------
500 starts drawn by ``fig_eels.sample_start`` from ``numpy.random.default_rng([20261110, 0])``,
one after another, over the parameter table of the main bounds. Start ``i`` is the ``i``-th
draw. The same 500 vectors are used for both models: for the constrained model the four
relationships of ``fig_eels.TIES`` then set the tied parameters from the drawn values.

Models: ``free`` (34 free parameters) and ``constrained`` (the four relationships, 30 free).

Solvers (arms), each from every start with the same bounds:

* ``spectrafit``: ``fit(graph, data, FitOptions(solver="lm"))`` of the installed wheel;
* ``scipy-trf``: ``scipy.optimize.least_squares(method="trf", x_scale="jac", jac="2-point")``
  at its default tolerances, start clipped to the bounds;
* ``lmfit-default``: ``lmfit.minimize(method="leastsq")`` at its default tolerances, the
  relationships as parameter expressions;
* ``lmfit-common``: the same with ``ftol = xtol = gtol = 1e-8``, the common stopping tolerance
  of the benchmark (``--tolerance-mode common``).

Measurement of an endpoint (the same code for every arm)
--------------------------------------------------------
* RSS from the wheel's ``evaluate``; a NumPy copy of the model must agree with it to 1e-9
  relative to ``max|y|``.
* Active bound: within ``1e-4 (upper - lower)`` of a bound (two finite bounds), or within
  ``1e-4 max(|default start|, 1)`` (one finite bound).
* Held component: active, with the gradient ``-2 J^T r`` pointing out of the box.
* Gauss-Newton stationarity: central-difference Jacobian with step
  ``6.06e-6 max(|theta|, 1e-3)``; predicted decrease of the Gauss-Newton step over the
  components not held, divided by RSS; **stationary** iff that is ``<= 1e-6`` and the endpoint
  lies within the bounds (to ``1e-12`` relative).
* Recorded per fit: RSS, reported success, stationary, GN measure, held and active components,
  amplitudes at 0 (an ``*.amplitude`` at its lower bound), iterations, function evaluations,
  wall time, ``step_l3.amplitude``, the termination message; for ``spectrafit`` also the
  condition number of ``J^T J`` and the standard error of ``step_l3.amplitude``.

Summary per model and arm
-------------------------
stationary count, reported-success count, the 2 x 2 table of reported success against
stationary, count reaching the best known minimum (RSS within ``1e-6`` relative of
``BEST_KNOWN``), for the free model the below-D count (stationary and RSS below
``D (1 - 1e-6)``), endpoints with at least one amplitude at 0 and the number of such
amplitudes, and the spread of ``step_l3.amplitude`` (minimum, quartiles, maximum) over all
endpoints and over the stationary ones. For the lowest-RSS stationary endpoint per model: its
arm and start, the condition numbers of the central-difference ``J`` and of ``J^T J``, and its
held components. The tables are reported without interpretation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SEED, STREAM, N_STARTS = 20261110, 0, 500
MODELS = ("free", "constrained")
ARMS = ("spectrafit", "scipy-trf", "lmfit-default", "lmfit-common")
COMMON_TOL = 1e-8
D_FREE = 21934809.1349
BEST_KNOWN = {"free": 20737458.001439333, "constrained": 22377888.243276}
BEST_REL = 1e-6
AT_BOUND_REL = 1e-4
BOUND_OK_REL = 1e-12
EQUIV_TOL = 1e-9
H_REL, THETA_FLOOR = 6.06e-6, 1e-3
GN_TOL = 1e-6
KEY_A = "step_l3.amplitude"
TIES = {
    "step_l2.amplitude": ("step_l3.amplitude / 2", lambda p: p["step_l3.amplitude"] / 2),
    "step_l2.sigma": ("step_l3.sigma", lambda p: p["step_l3.sigma"]),
    "step_l3.center": ("l3_c.center", lambda p: p["l3_c.center"]),
    "step_l2.center": ("l2_b.center", lambda p: p["l2_b.center"]),
}

_fe = None
_state: dict = {}


def fe():
    global _fe
    if _fe is None:
        spec = importlib.util.spec_from_file_location("fig_eels", HERE / "fig_eels.py")
        _fe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_fe)
    return _fe


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init_worker(spectrum: str) -> None:
    from spectrafit_core import MeasurementData

    m = fe()
    if sha256(Path(spectrum)) != m.SPECTRUM_SHA256:
        raise SystemExit(f"{spectrum}: checksum differs from fig_eels.SPECTRUM_SHA256")
    x, y = m.read_msa(Path(spectrum))
    keep = (x >= m.WINDOW_EV[0]) & (x <= m.WINDOW_EV[1])
    x, y = x[keep], y[keep]
    _state.update(x=x, y=y, data=MeasurementData(x=x.tolist(), y=y.tolist()), wheel_graph=m.graph("free"))


def model_np(p: dict) -> np.ndarray:
    x = _state["x"]
    out = np.full_like(x, p["bg.c"])
    for s in ("step_l3", "step_l2"):
        out = out + p[f"{s}.amplitude"] * (0.5 + np.arctan((x - p[f"{s}.center"]) / p[f"{s}.sigma"]) / np.pi)
    for nid, *_ in fe().L3_LINES + fe().L2_LINES:
        out = out + p[f"{nid}.amplitude"] * np.exp(-0.5 * ((x - p[f"{nid}.center"]) / p[f"{nid}.sigma"]) ** 2)
    return out


def model_wheel(p: dict) -> np.ndarray:
    from spectrafit_core import evaluate

    return np.asarray(evaluate(_state["wheel_graph"], p, _state["data"]), dtype=float)


class Setting:
    def __init__(self, model: str):
        self.model = model
        self.table = fe().param_table({})
        self.keys = [k for k, *_ in self.table]
        self.default = {k: d for k, d, _, _ in self.table}
        self.lo = {k: lo for k, _, lo, _ in self.table}
        self.hi = {k: hi for k, _, _, hi in self.table}
        self.tied = TIES if model == "constrained" else {}
        self.free = [k for k in self.keys if k not in self.tied]

    def full(self, values: dict) -> dict:
        p = {k: float(values[k]) for k in self.keys}
        for target, (_, fn) in self.tied.items():
            p[target] = fn(p)
        return p

    def with_free(self, base: dict, theta) -> dict:
        p = dict(base)
        p.update(zip(self.free, map(float, theta)))
        return self.full(p)

    def active(self, p: dict) -> dict[str, str]:
        out = {}
        for k in self.free:
            lo, hi = self.lo[k], self.hi[k]
            two = np.isfinite(lo) and np.isfinite(hi)
            tol = AT_BOUND_REL * ((hi - lo) if two else max(abs(self.default[k]), 1.0))
            if p[k] - lo <= tol:
                out[k] = "lower"
            elif hi - p[k] <= tol:
                out[k] = "upper"
        return out

    def bounds_ok(self, p: dict) -> bool:
        return all(self.lo[k] - BOUND_OK_REL * max(abs(self.lo[k]), 1.0) <= p[k]
                   <= self.hi[k] + BOUND_OK_REL * max(abs(self.hi[k]), 1.0)
                   for k in self.free if np.isfinite(p[k]))


def jacobian(s: Setting, p: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    theta = np.array([p[k] for k in s.free])
    scale = np.maximum(np.abs(theta), THETA_FLOOR)
    h = H_REL * scale
    jac = np.empty((_state["y"].size, theta.size))
    for i in range(theta.size):
        up, dn = theta.copy(), theta.copy()
        up[i] += h[i]
        dn[i] -= h[i]
        jac[:, i] = (model_np(s.with_free(p, up)) - model_np(s.with_free(p, dn))) / (2.0 * h[i])
    return theta, scale, jac


def stationarity(s: Setting, p: dict, active: dict) -> dict:
    y = _state["y"]
    _theta, scale, jac = jacobian(s, p)
    r = y - model_np(p)
    rss = float(r @ r)
    g = -2.0 * jac.T @ r
    held = np.array([(active.get(k) == "lower" and g[i] > 0) or (active.get(k) == "upper" and g[i] < 0)
                     for i, k in enumerate(s.free)], dtype=bool)
    js = jac[:, ~held] * scale[~held]
    step, *_ = np.linalg.lstsq(js, r, rcond=None)
    gn = float(np.sum((js @ step) ** 2) / rss)
    return {"gn_decrease_rel": gn, "stationary": gn <= GN_TOL, "held": [k for k, hd in zip(s.free, held) if hd]}


def endpoint(s: Setting, p: dict | None, wall: float, **info) -> dict:
    rec = {"wall_s": wall, **info}
    if p is None or not all(np.isfinite(v) for v in p.values()):
        return rec | {"ok": False}
    f = model_wheel(p)
    gap = float(np.max(np.abs(model_np(p) - f)) / np.max(np.abs(_state["y"])))
    if gap > EQUIV_TOL:
        raise SystemExit(f"NumPy model differs from the wheel by {gap:.3g} (relative) at an endpoint")
    rss = float(np.sum((_state["y"] - f) ** 2))
    if not np.isfinite(rss):
        return rec | {"ok": False}
    act = s.active(p)
    st = stationarity(s, p, act)
    ok_b = s.bounds_ok(p)
    return rec | {
        "ok": True, "rss": rss, "stationary": bool(st["stationary"] and ok_b), "gn": st["gn_decrease_rel"],
        "bounds_ok": ok_b, "active": act, "held": st["held"],
        "amplitudes_at_0": sorted(k for k, v in act.items() if k.endswith(".amplitude") and v == "lower"),
        "step_l3_amplitude": p[KEY_A], "params": p,
    }


def run_spectrafit(s: Setting, start: dict) -> dict:
    from spectrafit_core import FitOptions, fit

    t = time.perf_counter()
    try:
        r = fit(fe().graph(s.model, s.full(start), (), {}), _state["data"], FitOptions(solver="lm"))
    except Exception as exc:  # noqa: BLE001  # recorded with the fit
        return endpoint(s, None, time.perf_counter() - t, error=f"{type(exc).__name__}: {exc}")
    wall = time.perf_counter() - t
    p = {k: float(r.parameters[k].value) for k in s.keys}
    return endpoint(s, p, wall, success=bool(r.success), message=r.message, n_iter=r.n_iter,
                    nfev=r.n_func_evals, condition_number_jtj=getattr(r, "condition_number", None),
                    step_l3_amplitude_stderr=r.parameters[KEY_A].stderr)


def run_trf(s: Setting, start: dict) -> dict:
    from scipy.optimize import least_squares

    base = s.full(start)
    lb = np.array([s.lo[k] for k in s.free])
    ub = np.array([s.hi[k] for k in s.free])
    x0 = np.clip(np.array([base[k] for k in s.free]), lb, ub)
    y = _state["y"]
    t = time.perf_counter()
    try:
        res = least_squares(lambda th: y - model_np(s.with_free(base, th)), x0, bounds=(lb, ub), method="trf",
                            x_scale="jac", jac="2-point")
    except Exception as exc:  # noqa: BLE001
        return endpoint(s, None, time.perf_counter() - t, error=f"{type(exc).__name__}: {exc}")
    return endpoint(s, s.with_free(base, res.x), time.perf_counter() - t, success=bool(res.success),
                    message=res.message, status=int(res.status), nfev=int(res.nfev), n_iter=None)


def lmfit_name(k: str) -> str:
    return k.replace(".", "__")


def run_lmfit(s: Setting, start: dict, tol: float | None) -> dict:
    import lmfit

    base = s.full(start)
    params = lmfit.Parameters()
    for k in s.keys:
        if k not in s.tied:
            params.add(lmfit_name(k), value=float(np.clip(base[k], s.lo[k], s.hi[k])), min=s.lo[k], max=s.hi[k])
    for k, (expr, _) in s.tied.items():
        params.add(lmfit_name(k), expr=" ".join(lmfit_name(t) if "." in t else t for t in expr.split()))
    y = _state["y"]

    def resid(pars):
        v = pars.valuesdict()
        return y - model_np(s.full({k: v[lmfit_name(k)] for k in s.keys}))

    kws = {} if tol is None else {"ftol": tol, "xtol": tol, "gtol": tol}
    t = time.perf_counter()
    try:
        res = lmfit.minimize(resid, params, method="leastsq", **kws)
    except Exception as exc:  # noqa: BLE001
        return endpoint(s, None, time.perf_counter() - t, error=f"{type(exc).__name__}: {exc}")
    p = s.full({k: res.params[lmfit_name(k)].value for k in s.keys})
    return endpoint(s, p, time.perf_counter() - t, success=bool(res.success), message=res.message,
                    status=getattr(res, "ier", None), nfev=res.nfev, n_iter=None)


def starts() -> list[dict]:
    table = Setting("free").table
    rng = np.random.default_rng([SEED, STREAM])
    return [fe().sample_start(rng, table) for _ in range(N_STARTS)]


def run_task(task: tuple[str, str, int, dict]) -> dict:
    model, arm, i, start = task
    s = Setting(model)
    match arm:
        case "spectrafit":
            rec = run_spectrafit(s, start)
        case "scipy-trf":
            rec = run_trf(s, start)
        case "lmfit-default":
            rec = run_lmfit(s, start, None)
        case "lmfit-common":
            rec = run_lmfit(s, start, COMMON_TOL)
        case _:
            raise SystemExit(f"unknown arm {arm}")
    return {"model": model, "arm": arm, "start": i} | rec


def quartiles(v: list[float]) -> dict | None:
    if not v:
        return None
    q = np.quantile(np.asarray(v), [0.0, 0.25, 0.5, 0.75, 1.0])
    return dict(zip(("min", "q25", "median", "q75", "max"), map(float, q)))


def summarise(rows: list[dict], model: str, arm: str) -> dict:
    sel = [r for r in rows if r["model"] == model and r["arm"] == arm]
    ok = [r for r in sel if r["ok"]]
    st = [r for r in ok if r["stationary"]]
    best = BEST_KNOWN[model]
    out = {
        "n": len(sel), "ok": len(ok), "stationary": len(st),
        "reported_success": sum(bool(r.get("success")) for r in ok),
        "success_vs_stationary": {f"success={a}, stationary={b}":
                                  sum(bool(r.get("success")) == a and r["stationary"] == b for r in ok)
                                  for a in (True, False) for b in (True, False)},
        "reaching_best_known": sum(r["rss"] <= best * (1 + BEST_REL) for r in ok),
        "reaching_best_known_stationary": sum(r["rss"] <= best * (1 + BEST_REL) for r in st),
        "endpoints_with_amplitude_at_0": sum(bool(r["amplitudes_at_0"]) for r in ok),
        "amplitudes_at_0": sum(len(r["amplitudes_at_0"]) for r in ok),
        "lowest_rss": min((r["rss"] for r in ok), default=None),
        "lowest_stationary_rss": min((r["rss"] for r in st), default=None),
        "step_l3_amplitude_all": quartiles([r["step_l3_amplitude"] for r in ok]),
        "step_l3_amplitude_stationary": quartiles([r["step_l3_amplitude"] for r in st]),
        "fit_wall_s_sum": float(sum(r["wall_s"] for r in sel)),
        "errors": sorted({r["error"] for r in sel if not r["ok"] and r.get("error")}),
    }
    if model == "free":
        out["below_D_stationary"] = sum(r["rss"] < D_FREE * (1 - 1e-6) for r in st)
        out["below_D_any"] = sum(r["rss"] < D_FREE * (1 - 1e-6) for r in ok)
    return out


def best_stationary(rows: list[dict], model: str) -> dict | None:
    st = [r for r in rows if r["model"] == model and r["ok"] and r["stationary"]]
    if not st:
        return None
    r = min(st, key=lambda r: r["rss"])
    s = Setting(model)
    _theta, _scale, jac = jacobian(s, r["params"])
    sv = np.linalg.svd(jac, compute_uv=False)
    cond_j = float(sv[0] / sv[-1]) if sv[-1] > 0 else math.inf
    return {"arm": r["arm"], "start": r["start"], "rss": r["rss"], "gn": r["gn"],
            "step_l3_amplitude": r["step_l3_amplitude"], "held": r["held"], "active": r["active"],
            "condition_number_j": cond_j, "condition_number_jtj": cond_j ** 2,
            "condition_number_jtj_wheel": r.get("condition_number_jtj"),
            "jacobian": "central difference over the free parameters, unscaled (definitions above)",
            "params": r["params"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spectrum", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--limit", type=int, default=None, help="first N starts only (a smoke test)")
    args = ap.parse_args()
    models = [m for m in args.models.split(",") if m]
    arms = [a for a in args.arms.split(",") if a]
    if set(models) - set(MODELS) or set(arms) - set(ARMS):
        raise SystemExit(f"models from {MODELS}, arms from {ARMS}")
    import spectrafit_core

    init_worker(str(args.spectrum))
    vectors = starts()[: args.limit]
    tasks = [(m, a, i, v) for m in models for a in arms for i, v in enumerate(vectors)]
    tasks.sort(key=lambda t: ARMS.index(t[1]) == 0)  # the slow comparators first, for packing
    t0 = time.perf_counter()
    with ProcessPoolExecutor(args.workers, initializer=init_worker, initargs=(str(args.spectrum),)) as pool:
        rows = list(pool.map(run_task, tasks, chunksize=4))
    wall = time.perf_counter() - t0
    rows.sort(key=lambda r: (MODELS.index(r["model"]), ARMS.index(r["arm"]), r["start"]))
    summary = {m: {a: summarise(rows, m, a) for a in arms} for m in models}
    record = {
        "schema": "eels-far-starts/1",
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": platform.node(), "python": platform.python_version(),
        "spectrafit_core": spectrafit_core.__version__,
        "packages": {n: __import__(n).__version__ for n in ("numpy", "scipy", "lmfit")},
        "threads": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                    "MKL_NUM_THREADS", "RAYON_NUM_THREADS")},
        "workers": args.workers, "wall_s": wall,
        "fig_eels_sha256": sha256(HERE / "fig_eels.py"), "script_sha256": sha256(Path(__file__)),
        "spectrum_sha256": sha256(args.spectrum),
        "definitions": {"seed": SEED, "stream": STREAM, "n_starts": len(vectors), "common_tol": COMMON_TOL,
                        "D_free": D_FREE, "best_known": BEST_KNOWN, "best_rel": BEST_REL, "gn_tol": GN_TOL,
                        "at_bound_rel": AT_BOUND_REL},
        "starts": vectors,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "eels_far.json").write_text(json.dumps(record | {"fits": rows}) + "\n")
    best = {m: best_stationary(rows, m) for m in models}
    (args.out / "summary.json").write_text(json.dumps({k: v for k, v in record.items() if k != "starts"}
                                                      | {"summary": summary, "best_stationary": best},
                                                      indent=1) + "\n")
    print(f"eels-far: {len(rows)} fits in {wall:.0f} s")
    for m, per in summary.items():
        for a, v in per.items():
            extra = f" below-D {v['below_D_stationary']}" if m == "free" else ""
            print(f"  {m:11s} {a:13s} stationary {v['stationary']:3d}/{v['n']} success {v['reported_success']:3d} "
                  f"best-known {v['reaching_best_known']:3d} amp0 {v['endpoints_with_amplitude_at_0']}/"
                  f"{v['amplitudes_at_0']}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
