#!/usr/bin/env python3
"""Figure 4 of the article: one measured spectrum, fitted with and without stated relationships.

Why this script lives here
--------------------------
Figures 1 to 3 are drawn by the release's own scripts (``reproducibility/figures/`` at the
pinned tag). Figure 4 has no script in the release, so it is the one script this
repository adds. It uses only the public API of the pinned wheel and reads the spectrum
from the pinned release export, verified by SHA-256; nothing is copied from the release.

What it does
------------
The Fe L2,3 edge of Fe2O3 (EELS Data Base, contributor Qiang Xu, ODbL) is fitted between
700 and 735 eV twice, with the same components, bounds and starting values: a constant
background, one arctangent edge step per spin-orbit edge (L3, L2) and Gaussian white
lines, six at L3 (the last for the charge-transfer satellite) and three at L2.

* The free fit lets both steps vary independently. It is started twice, from the default
  guesses and from the constrained solution, and the start with the lower residual sum of
  squares is reported. From the default guesses alone it stops in a local minimum with the
  L3 step width at its lower bound; both starts are recorded.
* The constrained fit states four expression edges: the L2 step is half the L3 step (the
  2:1 occupation of the 2p3/2 and 2p1/2 levels), both steps share one width, and each step
  sits at the centre of its main white-line component.

The L3 branching ratio of the white-line areas carries a standard error from the delta
method over the fit covariance.

Three checks on the free fit are recorded next to it; none of them changes the figure.

* Profiles of both fits: the residual sum of squares with the L3 step amplitude fixed on a
  grid and every other parameter free, each point the best of walks in both directions, the
  reported fit and seeded random starts (``PROTOCOL``). Profile intervals at 68.27 % and 95 %
  from F(1, nu), with the likelihood-ratio form for comparison, and residual diagnostics at
  each model's lowest RSS. This is the main evidence for how well the data determine the step.
  States with a lower RSS than a reported fit that sit at a bound it does not touch are listed
  as ``bound_limited_states``.
* 50 seeded starts of the free fit, drawn by a fixed rule from a fixed seed (both written
  to the JSON), each classified by a rule fixed before the first run (``RULE`` below).
* The condition number of J^T J for both fits, as the wheel reports it, and its square root,
  the condition number of J. Every parameter's distance to its bounds is recorded too.

``--bound KEY=LOWER,UPPER`` replaces one parameter's bounds for a sensitivity run; the
replaced bounds are written to the JSON.

Writes ``eels_fe2o3.json`` (every number the article states about this fit) and
``figure4_eels.png`` / ``figure4_eels.pdf`` into ``--out``.

    python scripts/fig_eels.py --spectrum <release>/reproducibility/spectra/eelsdb-fe2o3-l23/DspecTi3wqG.msa --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import stats
from spectrafit_core import (
    MeasurementData, FitOptions, __version__ as SF_VERSION, arctan_step, compose, constant, evaluate, fit,
    gaussian)

WINDOW_EV = (700.0, 735.0)
SPECTRUM_SHA256 = "28e88f85350c353f524c828740c533312dc897505410ac940cd544060df963d4"
# White lines and satellites, (id, centre, height, width) as starting values. The
# Fe2O3 L3 edge carries the crystal-field multiplet and a charge-transfer
# satellite near 716 eV; L2 is broader and carries less structure.
L3_LINES = [("l3_a", 708.9, 4000.0, 0.4), ("l3_b", 709.3, 15000.0, 0.4), ("l3_c", 710.8, 28000.0, 0.6),
            ("l3_d", 712.2, 9000.0, 0.9), ("l3_e", 713.8, 5000.0, 1.2), ("l3_s", 716.5, 1500.0, 2.0)]
L2_LINES = [("l2_a", 722.3, 4000.0, 0.6), ("l2_b", 723.8, 4000.0, 0.9), ("l2_c", 725.2, 2000.0, 1.2)]
WHITE_LINES = {"L3": tuple(n for n, *_ in L3_LINES), "L2": tuple(n for n, *_ in L2_LINES)}

SEED = 20261109
N_STARTS = 50
# Fixed before the first seeded run. The reference is the reported free fit.
RULE = {
    "reference": {"rss": 22492836.38, "step_l3": 1704.0, "step_l3_stderr": 1008.0},
    "better_minimum": "all of: (1) success; (2) RSS lower than the reference RSS by more than 1e-6 "
                      "relative; (3) no free parameter at a bound that the reference fit does not also "
                      "sit at; (4) step_l3.amplitude differs from the reference by more than its "
                      "standard error",
    "flat_valley": "(1) to (3) hold but (4) does not",
    "at_bound": "|theta - b| <= 1e-4 * (upper - lower) for two finite bounds, "
                "<= 1e-4 * max(|default start|, 1) for a one-sided bound",
    "outcome": "better_minimum if any start is one; else flat_valley if any start is one; "
               "else confirmation",
}
AT_BOUND_REL = 1e-4
SAMPLING = ("one draw per parameter and start, in node order, numpy default_rng(seed). Centres: "
            "uniform within +-2 eV of the default start, clipped to the bounds. Other parameters with "
            "two finite bounds: uniform within the bounds. Parameters with an open side (amplitudes, "
            "background): default start * exp(N(0, 1)), i.e. log-normal with sigma_log = 1, clipped "
            "to the finite bound.")
PROFILE_KEY = "step_l3.amplitude"
# The four expression edges of the constrained fit, (expression, target).
TIES = [("step_l3.amplitude / 2", "step_l2.amplitude"), ("step_l3.sigma", "step_l2.sigma"),
        ("l3_c.center", "step_l3.center"), ("l2_b.center", "step_l2.center")]
# Profile protocol, fixed after a first provisional look at the free profile (recorded in the JSON).
PROFILE = {
    "free": {"grid": (0.0, 3500.0, 25.0), "bisect": False},
    "constrained": {"grid": (1404.0, 2004.0, 5.0), "bisect": True},
}
K_RANDOM = 20
BISECT_TOL = 0.1
ROBUST_REL = 1e-6
LEVELS = {"68": 0.6827, "95": 0.95}
LR_LEVELS = {"68": 1.0, "95": 3.84}
PROTOCOL = {
    "parameter": PROFILE_KEY,
    "grids": {m: {"from": g["grid"][0], "to": g["grid"][1], "step": g["grid"][2]} for m, g in PROFILE.items()},
    "per_point": f"best of: a walk upward warm-started from the lower neighbour, a walk downward warm-started "
                 f"from the upper neighbour, the reported fit of the model, and {K_RANDOM} seeded random starts "
                 f"(sampling rule below, numpy default_rng([seed, model, round(10 a)])); every other parameter "
                 f"free within its bounds",
    "robustness": f"number of starts whose RSS is within {ROBUST_REL} relative of the point's best",
    "global_minimum": "lowest RSS over the profile and, for the free model, the seeded multi-start",
    "s2": "RSS_min / (n - p) of the model, p = its number of free parameters",
    "interval": "{a : RSS(a) - RSS_min <= q s^2}, q = F_{1-alpha}(1, nu) at 68.27 % and 95 %; "
                "likelihood-ratio form n ln(RSS(a)/RSS_min) <= 1.0 and 3.84 for comparison",
    "bisection": f"constrained model: each interval end bisected to {BISECT_TOL} counts with the same "
                 f"per-point protocol",
    "boundary_affected": "an interval is marked when a or any other free parameter is at a bound at a "
                         "point inside it; the asymptotic levels do not hold there",
    "thresholds_set": "after a provisional look at the free profile and multi-start, before this run",
}


def read_msa(path: Path) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for line in path.read_text(encoding="latin-1").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        left, _, right = line.partition(",")
        x.append(float(left))
        y.append(float(right))
    return np.asarray(x), np.asarray(y)


def bounded(factory, node_id, fixed=(), bounds=None, **spec):
    """``spec``: name=(start, lower, upper); None leaves a side open.

    ``fixed`` holds keys (``node.param``) that do not vary; ``bounds`` maps keys to
    replacement (lower, upper) pairs.
    """
    kwargs = {}
    for name, (start, lower, upper) in spec.items():
        key = f"{node_id}.{name}"
        lower, upper = (bounds or {}).get(key, (lower, upper))
        kwargs[name] = start
        if lower is not None:
            kwargs[f"{name}_min"] = lower
        if upper is not None:
            kwargs[f"{name}_max"] = upper
        if key in fixed:
            kwargs[f"{name}_vary"] = False
    return factory(node_id, **kwargs)


def nodes(start: dict | None = None, fixed=(), bounds: dict | None = None):
    """Same components and bounds for both fits; ``start`` overrides the starting values,
    ``fixed`` and ``bounds`` are passed to :func:`bounded`."""
    s = start or {}

    def v(key, default):
        return s.get(key, default)

    out = [
        bounded(constant, "bg", fixed, bounds, c=(v("bg.c", 5700.0), 0.0, None)),
        bounded(arctan_step, "step_l3", fixed, bounds, amplitude=(v("step_l3.amplitude", 1900.0), 0.0, None),
                center=(v("step_l3.center", 710.0), 705.0, 715.0), sigma=(v("step_l3.sigma", 0.6), 0.3, 5.0)),
        bounded(arctan_step, "step_l2", fixed, bounds, amplitude=(v("step_l2.amplitude", 950.0), 0.0, None),
                center=(v("step_l2.center", 723.0), 718.0, 728.0), sigma=(v("step_l2.sigma", 0.6), 0.3, 5.0)),
    ]
    for node_id, centre, height, width in L3_LINES + L2_LINES:
        out.append(bounded(gaussian, node_id, fixed, bounds, amplitude=(v(f"{node_id}.amplitude", height), 0.0, None),
                           center=(v(f"{node_id}.center", centre), centre - 1.2, centre + 1.2),
                           sigma=(v(f"{node_id}.sigma", width), 0.1, 4.0)))
    return out


def rss(result, y) -> float:
    return float(np.sum((y - np.asarray(result.best_fit)) ** 2))


def area(p: dict, node: str) -> float:
    return p[f"{node}.amplitude"] * abs(p[f"{node}.sigma"]) * np.sqrt(2.0 * np.pi)


def branching(p: dict) -> float:
    a3 = sum(area(p, n) for n in WHITE_LINES["L3"])
    a2 = sum(area(p, n) for n in WHITE_LINES["L2"])
    return a3 / (a3 + a2)


def branching_with_error(result) -> tuple[float, float]:
    """L3 white-line branching ratio and its standard error by the delta method."""
    values = {k: v.value for k, v in result.parameters.items()}
    order, cov = result.covariance_param_order, np.asarray(result.covariance)
    grad = np.zeros(len(order))
    for i, key in enumerate(order):
        step = 1e-6 * max(abs(values[key]), 1e-6)
        up, down = dict(values), dict(values)
        up[key] += step
        down[key] -= step
        grad[i] = (branching(up) - branching(down)) / (2.0 * step)
    return branching(values), float(np.sqrt(grad @ cov @ grad))


def summarise(result, n_free: int) -> dict:
    p = result.parameters
    b, b_se = branching_with_error(result)
    return {
        "success": result.success, "message": result.message, "r_squared": result.r_squared,
        "aic": result.aic, "n_free": n_free,
        "step_l3": {"value": p["step_l3.amplitude"].value, "stderr": p["step_l3.amplitude"].stderr},
        "step_l2": {"value": p["step_l2.amplitude"].value, "stderr": p["step_l2.amplitude"].stderr},
        "step_sigma": [p["step_l3.sigma"].value, p["step_l2.sigma"].value],
        "branching_l3": {"value": b, "stderr": b_se},
    }



def param_table(bounds: dict | None = None) -> list[tuple[str, float, float, float]]:
    """(key, default start, lower, upper) for every parameter, in node order; open sides are inf."""
    return [(f"{n.id}.{k}", float(p.value), float(p.min), float(p.max))
            for n in nodes(bounds=bounds) for k, p in n.parameters.items()]


def sample_start(rng: np.random.Generator, table) -> dict:
    """One seeded start by the rule in ``SAMPLING``."""
    start = {}
    for key, default, lower, upper in table:
        if key.endswith(".center"):
            value = rng.uniform(max(lower, default - 2.0), min(upper, default + 2.0))
        elif np.isfinite(lower) and np.isfinite(upper):
            value = rng.uniform(lower, upper)
        else:
            value = float(np.clip(default * np.exp(rng.normal(0.0, 1.0)), lower, upper))
        start[key] = float(value)
    return start


def bound_status(result, table) -> dict:
    """Distance of every free parameter to its bounds, and the side it sits at (``RULE['at_bound']``)."""
    out = {}
    for key, default, lower, upper in table:
        p = result.parameters[key]
        if not p.vary or p.expr:
            continue
        two_sided = np.isfinite(lower) and np.isfinite(upper)
        tol = AT_BOUND_REL * ((upper - lower) if two_sided else max(abs(default), 1.0))
        d_lo, d_hi = p.value - lower, upper - p.value
        side = "lower" if d_lo <= tol else "upper" if d_hi <= tol else None
        out[key] = {"to_lower": d_lo if np.isfinite(lower) else None,
                    "to_upper": d_hi if np.isfinite(upper) else None, "at": side}
    return out


def at_bound(status: dict) -> dict[str, str]:
    return {k: v["at"] for k, v in status.items() if v["at"]}


def classify(rec: dict, reference_at: dict[str, str]) -> str:
    """``better_minimum``, ``flat_valley`` or ``neither`` by ``RULE``."""
    ref = RULE["reference"]
    c1 = rec["success"] is True
    c2 = rec["rss"] is not None and rec["rss"] < ref["rss"] * (1.0 - 1e-6)
    c3 = all(reference_at.get(k) == side for k, side in rec["at_bound"].items())
    c4 = rec["step_l3"] is not None and abs(rec["step_l3"] - ref["step_l3"]) > ref["step_l3_stderr"]
    if c1 and c2 and c3:
        return "better_minimum" if c4 else "flat_valley"
    return "neither"


def multistart(data, y, options, table, bounds, reference_at, seed: int, n: int) -> dict:
    """The free fit from ``n`` seeded starts; every start is recorded, failures included."""
    rng = np.random.default_rng(seed)
    starts = []
    for i in range(n):
        start = sample_start(rng, table)
        rec = {"index": i, "start": start, "success": False, "rss": None, "step_l3": None,
               "step_l3_stderr": None, "n_iter": None, "message": None, "bounds": {}, "at_bound": {},
               "params": None}
        try:
            r = fit(compose(nodes(start, bounds=bounds)).build(), data, options)
            status = bound_status(r, table)
            rec |= {"success": bool(r.success), "rss": rss(r, y), "message": r.message, "n_iter": r.n_iter,
                    "step_l3": r.parameters[PROFILE_KEY].value, "step_l3_stderr": r.parameters[PROFILE_KEY].stderr,
                    "step_l3_sigma": r.parameters["step_l3.sigma"].value,
                    "bounds": status, "at_bound": at_bound(status),
                    "params": {k: q.value for k, q in r.parameters.items()}}
            if not np.isfinite(rec["rss"]):
                rec["rss"], rec["success"] = None, False
        except Exception as exc:  # recorded, not dropped
            rec["message"] = f"{type(exc).__name__}: {exc}"
        rec["outcome"] = classify(rec, reference_at)
        starts.append(rec)
    better = [r for r in starts if r["outcome"] == "better_minimum"]
    flat = [r for r in starts if r["outcome"] == "flat_valley"]
    outcome = "better_minimum" if better else "flat_valley" if flat else "confirmation"
    ok = [r for r in starts if r["rss"] is not None]
    best = min(ok, key=lambda r: r["rss"]) if ok else None

    def brief(rs):
        return [{"index": r["index"], "rss": r["rss"], "delta_rss": r["rss"] - RULE["reference"]["rss"],
                 "step_l3": r["step_l3"]} for r in sorted(rs, key=lambda r: r["rss"])]

    return {"n": n, "seed": seed, "sampling": SAMPLING, "rule": RULE, "reference_at_bound": reference_at,
            "outcome": outcome, "starts": starts,
            "summary": {"n_success": sum(r["success"] for r in starts),
                        "n_failed": sum(r["rss"] is None for r in starts),
                        "n_at_bound": sum(bool(r["at_bound"]) for r in starts),
                        "n_at_bound_not_shared": sum(any(reference_at.get(k) != v for k, v in r["at_bound"].items())
                                                     for r in starts),
                        "best": None if best is None else brief([best])[0],
                        "better_minimum": brief(better), "flat_valley": brief(flat),
                        "rss_sorted": sorted(r["rss"] for r in ok)}}


def graph(model: str, start: dict | None = None, fixed=(), bounds: dict | None = None):
    builder = compose(nodes(start, fixed, bounds))
    if model == "constrained":
        for expr, target in TIES:
            builder = builder.bind(expr, to=target)
    return builder.build()


class Profiler:
    """RSS of one model with ``PROFILE_KEY`` fixed at a, by the protocol in ``PROFILE``/``PROTOCOL``."""

    def __init__(self, model, data, y, options, table, bounds, reference, seed):
        self.model, self.data, self.y, self.options = model, data, y, options
        self.table, self.bounds, self.seed = table, bounds, seed
        self.reference = {k: p.value for k, p in reference.parameters.items()}
        self.code = {"free": 1, "constrained": 2}[model]

    def run(self, a: float, start: dict, label: str) -> dict:
        try:
            r = fit(graph(self.model, start | {PROFILE_KEY: a}, (PROFILE_KEY,), self.bounds), self.data, self.options)
            value = rss(r, self.y)
            return {"label": label, "rss": value if np.isfinite(value) else None, "success": bool(r.success),
                    "n_iter": r.n_iter, "params": {k: p.value for k, p in r.parameters.items()},
                    "at_bound": at_bound(bound_status(r, self.table))}
        except Exception as exc:  # recorded, not dropped
            return {"label": label, "rss": None, "success": False, "n_iter": None, "params": None,
                    "at_bound": {}, "error": f"{type(exc).__name__}: {exc}"}

    def independent(self, a: float) -> list[dict]:
        rng = np.random.default_rng([self.seed, self.code, int(round(10 * a))])
        cands = [self.run(a, self.reference, "reference")]
        cands += [self.run(a, sample_start(rng, self.table), f"random_{k}") for k in range(K_RANDOM)]
        return cands

    @staticmethod
    def best(cands: list[dict]) -> dict:
        return min((c for c in cands if c["rss"] is not None), key=lambda c: c["rss"])

    def summarise(self, a: float, cands: list[dict]) -> dict:
        b = self.best(cands)
        robust = sum(1 for c in cands if c["rss"] is not None and c["rss"] <= b["rss"] * (1 + ROBUST_REL))
        lower_a = self.table_lookup(PROFILE_KEY)
        a_at = abs(a - lower_a) <= AT_BOUND_REL * max(abs(self.table_default(PROFILE_KEY)), 1.0)
        return {"a": a, "rss": b["rss"], "success": b["success"], "n_iter": b["n_iter"], "best_from": b["label"],
                "n_starts": len(cands), "robust": robust, "a_at_bound": bool(a_at),
                "at_bound": b["at_bound"], "params": b["params"]}

    def table_lookup(self, key):
        return next(lo for k, _, lo, _ in self.table if k == key)

    def table_default(self, key):
        return next(d for k, d, _, _ in self.table if k == key)

    def grid(self) -> list[dict]:
        lo, hi, step = PROFILE[self.model]["grid"]
        grid = np.round(np.arange(lo, hi + step / 2, step), 6)
        cands = [self.independent(float(a)) for a in grid]
        for i in range(1, grid.size):  # walk upward
            cands[i].append(self.run(float(grid[i]), self.best(cands[i - 1])["params"], "walk_up"))
        for i in range(grid.size - 2, -1, -1):  # walk downward
            cands[i].append(self.run(float(grid[i]), self.best(cands[i + 1])["params"], "walk_down"))
        return [self.summarise(float(a), c) for a, c in zip(grid, cands)]

    def point(self, a: float, inside: dict, outside: dict) -> dict:
        cands = self.independent(a)
        cands.append(self.run(a, inside["params"], "warm_inside"))
        cands.append(self.run(a, outside["params"], "warm_outside"))
        return self.summarise(a, cands)


def interval(points: list[dict], rss_min: float, threshold: float, key=None) -> dict:
    """Grid interval {a : excess(a) <= threshold}; ``key`` maps a point to its excess."""
    key = key or (lambda q: q["rss"] - rss_min)
    inside = [i for i, q in enumerate(points) if q["rss"] is not None and key(q) <= threshold]
    if not inside:
        return {"lower": None, "upper": None, "closed": False}
    i0, i1 = inside[0], inside[-1]
    span = points[i0:i1 + 1]
    affected = sorted({k for q in span for k in q["at_bound"]} | ({PROFILE_KEY} if any(q["a_at_bound"] for q in span) else set()))
    return {"lower": points[i0]["a"], "upper": points[i1]["a"], "i": [i0, i1],
            "contiguous": len(inside) == i1 - i0 + 1, "open_lower": i0 == 0, "open_upper": i1 == len(points) - 1,
            "closed": i0 > 0 and i1 < len(points) - 1, "width": points[i1]["a"] - points[i0]["a"],
            "boundary_affected": bool(affected), "at_bound_inside": affected}


def bisect_end(prof: Profiler, points, rss_min, threshold, i_in, i_out) -> dict:
    """Bisect between an inside and an outside grid point to ``BISECT_TOL``."""
    a_in, a_out = points[i_in]["a"], points[i_out]["a"]
    q_in, q_out = points[i_in], points[i_out]
    steps = []
    while abs(a_in - a_out) > BISECT_TOL:
        mid = 0.5 * (a_in + a_out)
        q = prof.point(mid, q_in, q_out)
        inside = q["rss"] is not None and q["rss"] - rss_min <= threshold
        steps.append({"a": mid, "rss": q["rss"], "inside": inside, "robust": q["robust"], "at_bound": q["at_bound"]})
        if inside:
            a_in, q_in = mid, q
        else:
            a_out, q_out = mid, q
    return {"inside": a_in, "outside": a_out, "end": 0.5 * (a_in + a_out), "steps": steps}


def residual_diagnostics(model: str, params: dict, data, y, s2: float) -> dict:
    """Lag-1 autocorrelation of the residuals and s^2 against the Poisson expectation."""
    r = y - np.asarray(evaluate(graph("free"), params, data), dtype=float)
    rc = r - r.mean()
    return {"lag1_autocorrelation": float(np.sum(rc[:-1] * rc[1:]) / np.sum(rc * rc)),
            "s2": s2, "mean_counts": float(y.mean()), "s2_over_mean_counts": float(s2 / y.mean())}


def profile_model(model, data, y, options, table, bounds, reference, seed, n_free, extra_minima=()) -> tuple[dict, dict]:
    """Profile, global minimum, intervals and residual diagnostics of one model."""
    prof = Profiler(model, data, y, options, table, bounds, reference, seed)
    points = prof.grid()
    ok = [q for q in points if q["rss"] is not None]
    candidates = [(q["rss"], "profile", q["a"], q["params"], q["at_bound"]) for q in ok]
    candidates += [(m["rss"], "multistart", m["step_l3"], m["params"], m["at_bound"])
                   for m in extra_minima if m["rss"] is not None]
    rss_min, source, a_min, p_min, at_min = min(candidates, key=lambda c: c[0])
    n = int(y.size)
    nu = n - n_free
    s2 = rss_min / nu
    out = {"points": points, "global_minimum": {"rss": rss_min, "a": a_min, "source": source, "at_bound": at_min,
                                                "n": n, "p": n_free, "nu": nu, "s2": s2, "params": p_min},
           "intervals": {}, "intervals_lr": {}}
    for level, prob in LEVELS.items():
        q = float(stats.f.ppf(prob, 1, nu))
        iv = interval(points, rss_min, q * s2) | {"q": q, "level": prob}
        if PROFILE[model]["bisect"] and iv.get("closed"):
            i0, i1 = iv["i"]
            lo = bisect_end(prof, points, rss_min, q * s2, i0, i0 - 1)
            hi = bisect_end(prof, points, rss_min, q * s2, i1, i1 + 1)
            iv |= {"bisected": {"lower": lo, "upper": hi}, "lower_bisected": lo["end"], "upper_bisected": hi["end"],
                   "width_bisected": hi["end"] - lo["end"]}
        out["intervals"][level] = iv
    for level, crit in LR_LEVELS.items():
        out["intervals_lr"][level] = interval(points, rss_min, crit, key=lambda p_: n * np.log(p_["rss"] / rss_min)) \
            | {"criterion": crit}
    out["residual_diagnostics"] = residual_diagnostics(model, p_min, data, y, s2)
    return out


def bound_limited(model_profile: dict, reported_rss: float, reported_at: dict, multistart_starts=()) -> list[dict]:
    """States with lower RSS than the reported fit that sit at a bound the reported fit does not."""
    states = []
    for q in model_profile["points"]:
        extra = {k: v for k, v in q["at_bound"].items() if reported_at.get(k) != v}
        if q["a_at_bound"]:
            extra[PROFILE_KEY] = "lower"
        if q["rss"] is not None and q["rss"] < reported_rss and extra:
            states.append({"source": "profile", "a": q["a"], "rss": q["rss"], "at_bound": q["at_bound"],
                           "not_shared": extra})
    for m in multistart_starts:
        extra = {k: v for k, v in m["at_bound"].items() if reported_at.get(k) != v}
        if m["rss"] is not None and m["rss"] < reported_rss and extra:
            states.append({"source": f"multistart_{m['index']}", "a": m["step_l3"], "rss": m["rss"],
                           "at_bound": m["at_bound"], "not_shared": extra})
    return sorted(states, key=lambda st: st["rss"])


def plot(x, y, fits, record, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import AutoMinorLocator, MultipleLocator

    navy, indigo, violet, grey, red = "#14145a", "#3c3cb4", "#8a7cf0", "#7a7a7a", "#d0103a"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.linewidth": 0.8,
                         "xtick.direction": "out", "ytick.direction": "out",
                         "xtick.major.size": 4, "ytick.major.size": 4,
                         "xtick.minor.size": 2.2, "ytick.minor.size": 2.2})
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.0), sharex=True, sharey="row",
                             gridspec_kw={"height_ratios": [3.2, 1.0], "hspace": 0.07, "wspace": 0.14})
    titles = {"free": "A   Edge steps fitted independently",
              "constrained": "B   Four expression edges on the steps"}
    k = 1e3
    for col, (key, result) in enumerate(fits.items()):
        comp = {name: np.asarray(v) for name, v in result.components.items()}
        continuum = comp["bg"] + comp["step_l3"] + comp["step_l2"]
        ax, ar = axes[0][col], axes[1][col]
        for group, colour in (("L3", indigo), ("L2", violet)):
            for node in WHITE_LINES[group]:
                ax.fill_between(x, continuum / k, (continuum + comp[node]) / k, color=colour,
                                alpha=0.22, lw=0)
                ax.plot(x, (continuum + comp[node]) / k, color=colour, lw=0.6, alpha=0.9)
        ax.plot(x, y / k, "o", ms=1.4, mfc=grey, mec="none", alpha=0.7, label="measured", zorder=3)
        ax.plot(x, np.asarray(result.best_fit) / k, color=navy, lw=1.1, label="fit", zorder=4)
        ax.plot(x, continuum / k, color=red, lw=1.3, ls=(0, (4, 2)), label="background + edge steps",
                zorder=5)
        rec = record[key]
        s3, s2 = rec["step_l3"], rec["step_l2"]
        se3 = f" ± {s3['stderr']:.0f}" if s3["stderr"] is not None else ""
        se2 = f" ± {s2['stderr']:.0f}" if s2["stderr"] is not None else " (tied)"
        ax.text(0.97, 0.96, f"L$_3$ step {s3['value']:.0f}{se3}\nL$_2$ step {s2['value']:.0f}{se2}\n"
                f"$r^2$ = {rec['r_squared']:.5f}", transform=ax.transAxes, ha="right", va="top",
                fontsize=7.5, color=navy, linespacing=1.4)
        ax.set_title(titles[key], loc="left", fontsize=8.5, color=navy, pad=4)
        # The continuum where the two fits differ, magnified.
        inset = ax.inset_axes([0.52, 0.36, 0.46, 0.36])
        window = (x >= 714.0) & (x <= 735.0)
        inset.plot(x[window], y[window] / k, "o", ms=1.0, mfc=grey, mec="none", alpha=0.7)
        inset.plot(x[window], np.asarray(result.best_fit)[window] / k, color=navy, lw=0.9)
        inset.plot(x[window], continuum[window] / k, color=red, lw=1.1, ls=(0, (4, 2)))
        inset.set_xlim(714.0, 735.0)
        inset.set_ylim(5.0, 13.0)
        inset.xaxis.set_major_locator(MultipleLocator(5))
        inset.xaxis.set_minor_locator(MultipleLocator(1))
        inset.yaxis.set_major_locator(MultipleLocator(2))
        inset.yaxis.set_minor_locator(MultipleLocator(0.5))
        inset.tick_params(labelsize=6.5, pad=1.5)
        ar.plot(x, (y - np.asarray(result.best_fit)) / k, color=indigo, lw=0.6)
        ar.axhline(0.0, color=grey, lw=0.6)
        ar.set_xlabel("Energy loss (eV)")
        for a in (ax, ar):
            a.spines[["top", "right"]].set_visible(False)
            a.xaxis.set_major_locator(MultipleLocator(5))
            a.xaxis.set_minor_locator(MultipleLocator(1))
            a.yaxis.set_minor_locator(AutoMinorLocator(5))
            a.set_xlim(700.0, 735.0)
    axes[0][0].set_ylim(0.0, 41.0)
    axes[0][0].yaxis.set_major_locator(MultipleLocator(10))
    axes[1][0].set_ylim(-1.6, 1.6)
    axes[1][0].yaxis.set_major_locator(MultipleLocator(1))
    axes[0][0].set_ylabel("Intensity (10$^3$ counts)")
    axes[1][0].set_ylabel("Residual\n(10$^3$ counts)")
    handles, labels = axes[0][0].get_legend_handles_labels()
    handles += [plt.Rectangle((0, 0), 1, 1, color=indigo, alpha=0.35),
                plt.Rectangle((0, 0), 1, 1, color=violet, alpha=0.35)]
    labels += ["L$_3$ lines and satellite", "L$_2$ lines"]
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=7, frameon=False,
               bbox_to_anchor=(0.5, -0.045), handlelength=1.8, columnspacing=1.2)
    fig.text(0.995, -0.085, "Data: EELS Data Base (eelsdb.eu), contributor Qiang Xu, ODbL",
             ha="right", va="bottom", fontsize=6, color=grey)
    fig.savefig(out, dpi=400, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spectrum", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--starts", type=int, default=N_STARTS, help="seeded starts of the free fit")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--bound", action="append", default=[], metavar="KEY=LOWER,UPPER",
                    help="replace one parameter's bounds (sensitivity runs; recorded in the JSON)")
    args = ap.parse_args()
    bounds = {}
    for item in args.bound:
        key, _, pair = item.partition("=")
        lower, upper = (float(v) for v in pair.split(","))
        bounds[key] = (lower, upper)
    digest = hashlib.sha256(args.spectrum.read_bytes()).hexdigest()
    if digest != SPECTRUM_SHA256:
        raise SystemExit(f"{args.spectrum} is not the EELSDB file this figure is made from ({digest})")

    raw_x, raw_y = read_msa(args.spectrum)
    keep = (raw_x >= WINDOW_EV[0]) & (raw_x <= WINDOW_EV[1])
    x, y = raw_x[keep], raw_y[keep]
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    options = FitOptions(solver="lm")

    fit_c = fit(graph("constrained", bounds=bounds), data, options)
    # The free fit from two starts: the default guesses and the constrained solution.
    starts = {"default": fit(compose(nodes(bounds=bounds)).build(), data, options),
              "constrained_solution": fit(compose(nodes({k: p.value for k, p in fit_c.parameters.items()},
                                                        bounds=bounds)).build(), data, options)}
    best = min(starts, key=lambda k: rss(starts[k], y))
    fits = {"free": starts[best], "constrained": fit_c}
    n_params = sum(len(n.parameters) for n in nodes())
    table = param_table(bounds)
    status = {"free": bound_status(fits["free"], table), "constrained": bound_status(fit_c, table),
              "free_default_start": bound_status(starts["default"], table)}
    reference_at = at_bound(status["free"])

    record = {
        "spectrum": {"file": args.spectrum.name, "sha256": digest, "window_ev": list(WINDOW_EV),
                     "points": int(x.size), "source": "https://eelsdb.eu/spectra/iron-oxide-2/",
                     "licence": "ODbL", "contributor": "Qiang Xu"},
        "software": {"spectrafit-core": SF_VERSION, "numpy": np.__version__},
        "free": summarise(fits["free"], n_params) | {
            "start": best, "rss": rss(fits["free"], y),
            "starts": {k: {"rss": rss(r, y), "r_squared": r.r_squared,
                           "step_l3": r.parameters["step_l3.amplitude"].value,
                           "step_l3_sigma": r.parameters["step_l3.sigma"].value} for k, r in starts.items()}},
        "constrained": summarise(fits["constrained"], n_params - 4) | {"rss": rss(fits["constrained"], y)},
        "bound_overrides": {k: list(v) for k, v in bounds.items()},
        "condition_number": {
            key: {"jtj": float(r.condition_number), "j": float(np.sqrt(r.condition_number)),
                  "note": "jtj is FitResult.condition_number, the condition number of J^T J"}
            for key, r in fits.items() if r.condition_number is not None},
        "at_bound": {k: at_bound(v) for k, v in status.items()},
        "bounds_distance": status,
        "multistart": multistart(data, y, options, table, bounds, reference_at, args.seed, args.starts),
        "profile_protocol": PROTOCOL | {"seed": args.seed, "k_random": K_RANDOM, "sampling": SAMPLING},
    }
    n_free = {"free": n_params, "constrained": n_params - len(TIES)}
    record["profiles"] = {
        model: profile_model(model, data, y, options, table, bounds, fits[model], args.seed, n_free[model],
                             record["multistart"]["starts"] if model == "free" else ())
        for model in ("free", "constrained")}
    record["bound_limited_states"] = {
        model: bound_limited(record["profiles"][model], record[model]["rss"], at_bound(status[model]),
                             record["multistart"]["starts"] if model == "free" else ())
        for model in ("free", "constrained")}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "eels_fe2o3.json").write_text(json.dumps(record, indent=1) + "\n")
    plot(x, y, fits, record, args.out / "figure4_eels.png")
    for key in ("free", "constrained"):
        r = record[key]
        print(f"{key:12s} r2={r['r_squared']:.4f} steps={r['step_l3']['value']:.0f}/"
              f"{r['step_l2']['value']:.4g} branching={r['branching_l3']['value']:.3f}"
              f"±{r['branching_l3']['stderr']:.3f}")
    ms = record["multistart"]
    print(f"at bound     {record['at_bound']}")
    for model, prof in record["profiles"].items():
        g = prof["global_minimum"]
        print(f"{model:12s} minimum RSS {g['rss']:.10g} at a = {g['a']:.1f} ({g['source']}), at bound {g['at_bound']}")
        for level, iv in prof["intervals"].items():
            print(f"{'':12s} {level} %: [{iv.get('lower_bisected', iv['lower'])}, {iv.get('upper_bisected', iv['upper'])}]"
                  f" closed={iv['closed']} boundary_affected={iv.get('boundary_affected')}")
    print(f"{ms['n']} seeded starts (seed {ms['seed']}): outcome {ms['outcome']}, "
          f"{ms['summary']['n_success']} succeeded, best {ms['summary']['best']}")
    if ms["outcome"] == "better_minimum":
        print("NOTE: a seeded start meets all four conditions of RULE; Figure 4A is not switched "
              "automatically.")


if __name__ == "__main__":
    main()
