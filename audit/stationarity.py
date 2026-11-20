"""Stationarity, RSS ratio, iterations and success flags of the 07 fallback comparison.

Track F, issue #93. Reads the end points recorded by ``run/capture_run.py`` during
the harness run and applies the definitions fixed in ``README.md`` (committed before
the run). Writes ``table.json`` and ``table.md``.

    env -u VIRTUAL_ENV uv run --locked --no-sync python stationarity.py \
        --capture run/capture.jsonl --results <run dir>/results.json --out .

The stationarity test is the convention of ``crosscheck.stationarity`` (ledger
2026-11-09-eels-solver-crosscheck): central-difference Jacobian with step
``H_REL * max(|theta|, THETA_FLOOR)``, "held" = at an active bound by the 1e-4 rule
with the gradient pointing outward, Gauss-Newton predicted decrease over the
components not held divided by RSS, stationary iff that is <= ``GN_TOL``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

BACKENDS = ("spectrafit", "scipy-ls-trf", "lmfit")
AT_BOUND_REL = 1e-4  # active bound, the #66 rule
H_REL, THETA_FLOOR = 6.06e-6, 1e-3
GN_TOL = 1e-6  # stationary: Gauss-Newton predicted decrease / RSS <= this
EQUIV_TOL = 1e-9  # evaluator vs the backend's own best_fit, relative to max|y|
SAME_REL = 1e-6  # |a - b| <= SAME_REL * min(a, b)
RSS_ZERO_REL = 1e-24  # RSS <= RSS_ZERO_REL * sum(y^2) counts as zero
SPLIT_CATEGORIES = ("robust", "optfn")


def load_capture(path: Path) -> dict[tuple[str, str, int], dict[str, Any]]:
    """(case, backend, seq) -> captured record."""
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        out[(rec["case"], rec["backend"], rec["seq"])] = rec
    return out


def fallback_bounds(
    name: str,
    value: float,
    x_min: float,
    x_max: float,
    x_span: float,
    y_max_abs: float,
) -> tuple[float, float]:
    """Port of ``fallback_bounds`` (crates/spectrafit-solver/src/global.rs:409)."""
    lname = name.lower()
    if "center" in lname or "position" in lname:
        return (x_min, x_max) if x_max > x_min else (value - x_span, value + x_span)
    if "amplitude" in lname or "height" in lname:
        cap = max(4.0 * y_max_abs, abs(value) * 2.0, 1.0)
        return (min(0.0, value), cap)
    if "sigma" in lname or "gamma" in lname or "width" in lname:
        return (1e-6, max(x_span, abs(value) * 4.0, 1e-3))
    pad = max(2.0 * x_span, abs(value) * 2.0, 10.0)
    return (value - pad, value + pad)


def boxes(case: Any) -> tuple[list[str], np.ndarray, dict[str, tuple]]:
    """Parameter names (``p{i}.{name}``), start values, and each backend's box.

    The box of a backend is the one its adapter hands to the library: lower, upper
    and free mask over the full parameter vector.
    """
    from oracles.backends._lmfit import LmfitBackend
    from oracles.backends._scipy_ls import _build_initial_guess
    from oracles.backends._spectrafit import SpectraFitBackend
    from oracles.backends._tolerance import tolerances_for
    from oracles.models import get_model

    tol = tolerances_for("common")
    trf = _build_initial_guess(case)
    names = [n.replace("_", ".", 1) for n in trf.names]
    n = len(names)
    free_trf = np.zeros(n, dtype=bool)
    free_trf[trf.free_indices] = True
    guess = np.asarray(
        [float(c.to_params()[p]) for c in case.comp_guess for p in get_model(c.model).param_names],
    )
    out: dict[str, tuple] = {"scipy-ls-trf": (trf.lo.copy(), trf.hi.copy(), free_trf)}

    graph, _data, _opt = SpectraFitBackend(tolerances=tol).build(case)
    lo, hi, free = np.full(n, -np.inf), np.full(n, np.inf), np.zeros(n, dtype=bool)
    x_min, x_max = float(np.min(case.x)), float(np.max(case.x))
    x_span = x_max - x_min if x_max > x_min else 10.0
    y_max_abs = float(np.max(np.abs(case.y)))
    for node in graph.nodes:
        for pname, par in node.parameters.items():
            j = names.index(f"{node.id}.{pname}")
            lo[j], hi[j], free[j] = float(par.min), float(par.max), bool(par.vary)
            if case.solver_hint == "global" and free[j]:
                fb = fallback_bounds(pname, float(par.value), x_min, x_max, x_span, y_max_abs)
                lo[j] = lo[j] if math.isfinite(lo[j]) else fb[0]
                hi[j] = hi[j] if math.isfinite(hi[j]) else fb[1]
    out["spectrafit"] = (lo, hi, free)

    _comp, params, _x, _y = LmfitBackend(tol).build(case)
    lo, hi, free = np.full(n, -np.inf), np.full(n, np.inf), np.zeros(n, dtype=bool)
    for j, nm in enumerate(names):
        par = params[nm.replace(".", "_", 1)]
        lo[j], hi[j] = float(par.min), float(par.max)
        free[j] = bool(par.vary) and not par.expr
    out["lmfit"] = (lo, hi, free)
    return names, guess, out


def active(theta: np.ndarray, lo: np.ndarray, hi: np.ndarray, free: np.ndarray, guess) -> dict:
    """Free components at an active bound by the 1e-4 rule -> 'lower' / 'upper'."""
    out: dict[int, str] = {}
    for j in np.flatnonzero(free):
        two = math.isfinite(lo[j]) and math.isfinite(hi[j])
        tol = AT_BOUND_REL * ((hi[j] - lo[j]) if two else max(abs(guess[j]), 1.0))
        if theta[j] - lo[j] <= tol:
            out[int(j)] = "lower"
        elif hi[j] - theta[j] <= tol:
            out[int(j)] = "upper"
    return out


def stationarity(case: Any, theta: np.ndarray, free: np.ndarray, act: dict) -> dict[str, Any]:
    """GN predicted decrease / RSS over the free components not held."""
    from oracles.backends._scipy_ls import _predict

    y = case.y
    r = y - _predict(theta, case)
    rss = float(r @ r)
    zero = rss <= RSS_ZERO_REL * float(y @ y)
    idx = np.flatnonzero(free)
    th = theta[idx]
    scale = np.maximum(np.abs(th), THETA_FLOOR)
    h = H_REL * scale
    jac = np.empty((y.size, idx.size))
    for c, j in enumerate(idx):
        up, dn = theta.copy(), theta.copy()
        up[j] += h[c]
        dn[j] -= h[c]
        jac[:, c] = (_predict(up, case) - _predict(dn, case)) / (2.0 * h[c])
    if not np.all(np.isfinite(jac)):
        return {"rss": rss, "jac_finite": False}
    g = -2.0 * jac.T @ r
    held = np.array(
        [
            (act.get(int(j)) == "lower" and g[c] > 0) or (act.get(int(j)) == "upper" and g[c] < 0)
            for c, j in enumerate(idx)
        ],
        dtype=bool,
    )
    js = jac[:, ~held] * scale[~held]
    if js.shape[1] and not zero:
        step, *_ = np.linalg.lstsq(js, r, rcond=None)
        gn = float(np.sum((js @ step) ** 2) / rss)
    else:
        gn = 0.0
    return {
        "rss": rss,
        "jac_finite": True,
        "zero_rss": bool(zero),
        "gn_decrease_rel": None if zero else gn,
        "stationary": bool(zero or gn <= GN_TOL),
        "n_held": int(held.sum()),
    }


def iters(backend: str, raw: dict) -> dict[str, float | None]:
    """Counters as each library reports them (see README, Iterations)."""
    match backend:
        case "spectrafit":
            return {
                "accepted_steps": raw["n_iter"],
                "nfev": raw["n_func_evals"],
                "njev": raw["n_jac_evals"],
            }
        case "scipy-ls-trf":
            nj = raw["njev"]
            return {
                "accepted_steps": None if nj is None else nj - 1,
                "nfev": raw["nfev"],
                "njev": nj,
            }
        case _:
            return {"accepted_steps": raw.get("nit"), "nfev": raw["nfev"], "njev": None}


def same(a: float, b: float) -> bool:
    """|a - b| <= SAME_REL * min(a, b)."""
    return abs(a - b) <= SAME_REL * min(a, b)


def quantiles(v: list[float]) -> dict[str, float | int | None]:
    """n, median, p25, p75, p90, max."""
    if not v:
        return {"n": 0}
    a = np.asarray(v, dtype=float)
    return {
        "n": int(a.size),
        "median": float(np.median(a)),
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
        "max": float(np.max(a)),
    }


def evaluate_endpoints(cap: dict, catalog: list) -> tuple[list[dict], list[dict]]:
    """Per case: three end points or an exclusion with its reason."""
    from oracles.backends._scipy_ls import _predict

    rows, excluded = [], []
    for case in catalog:
        names, guess, bx = boxes(case)
        per: dict[str, Any] = {}
        reasons = []
        for b in BACKENDS:
            rec = cap.get((case.id, b, 0))
            if rec is None:
                reasons.append(f"{b}: no end point (unsupported or raised)")
                continue
            p = rec["outcome_params"]
            if missing := [k for k in names if k not in p]:
                reasons.append(f"{b}: parameter keys missing from the outcome: {missing}")
                continue
            theta = np.asarray([np.nan if p[k] is None else p[k] for k in names], dtype=float)
            if not np.all(np.isfinite(theta)):
                reasons.append(f"{b}: non-finite end point")
                continue
            f = _predict(theta, case)
            own = np.asarray([np.nan if v is None else v for v in rec["best_fit"]], dtype=float)
            gap = float(np.max(np.abs(f - own)) / np.max(np.abs(case.y)))
            if not np.isfinite(gap) or gap > EQUIV_TOL:
                reasons.append(f"{b}: evaluator differs from its best_fit by {gap:.3g}")
                continue
            lo, hi, free = bx[b]
            act = active(theta, lo, hi, free, guess)
            st = stationarity(case, theta, free, act)
            if not st["jac_finite"] or not math.isfinite(st["rss"]):
                reasons.append(f"{b}: non-finite RSS or Jacobian at the end point")
                continue
            seq1 = cap.get((case.id, b, 1))
            per[b] = {
                "at_bound": bool(act),
                "active": {names[j]: s for j, s in act.items()},
                "equivalence_gap": gap,
                **st,
                "lib_success": rec["raw"]["lib_success"],
                "harness_success": rec["outcome_success"],
                "message": rec["raw"].get("message"),
                "iters": iters(b, rec["raw"]),
                "outcome_chi2": rec["outcome_chi2"],
                "outcome_reduced_chi2": rec["outcome_reduced_chi2"],
                "rss_over_sum_y2": st["rss"] / float(case.y @ case.y),
                "chi2_recompute_rel": abs(st["rss"] - rec["outcome_chi2"])
                / max(rec["outcome_chi2"], 1e-300),
                "seq1_chi2": None if seq1 is None else seq1["outcome_chi2"],
            }
        if reasons:
            excluded.append({"case": case.id, "category": case.category, "reasons": reasons})
            continue
        zero_thr = RSS_ZERO_REL * float(case.y @ case.y)
        eff = {b: max(per[b]["rss"], zero_thr) for b in BACKENDS}
        best = min(eff.values())
        for b in BACKENDS:
            per[b]["rss_ratio"] = eff[b] / best
            per[b]["at_min"] = same(eff[b], best)
        rows.append(
            {
                "case": case.id,
                "category": case.category,
                "solver_hint": case.solver_hint,
                "n_free": int(bx["scipy-ls-trf"][2].sum()),
                "endpoints": per,
                "rss_eff": eff,
            },
        )
    return rows, excluded


def summarise(rows: list[dict]) -> dict[str, Any]:
    """All tables over one fixed case set ``rows``."""
    out: dict[str, Any] = {"n_cases": len(rows)}
    stat, ratio, its, flags = {}, {}, {}, {}
    for b in BACKENDS:
        eps = [r["endpoints"][b] for r in rows]
        stat[b] = {
            kind: {
                "stationary": sum(e["stationary"] for e in eps if e["at_bound"] == ab),
                "n": sum(e["at_bound"] == ab for e in eps),
            }
            for kind, ab in (("free", False), ("at_bound", True))
        }
        stat[b]["zero_rss"] = sum(e["zero_rss"] for e in eps)
        rr = [e["rss_ratio"] for e in eps]
        ratio[b] = quantiles(rr) | {"at_min": sum(e["at_min"] for e in eps)}
        its[b] = {
            k: quantiles([e["iters"][k] for e in eps if e["iters"][k] is not None])
            for k in ("accepted_steps", "nfev", "njev")
        }
        for flag in ("lib_success", "harness_success"):
            c = Counter((bool(e[flag]), bool(e["stationary"])) for e in eps)
            flags.setdefault(b, {})[flag] = {
                f"success={s}/stationary={t}": c[(s, t)]
                for s in (True, False)
                for t in (True, False)
            }
    pair = {}
    for other in ("scipy-ls-trf", "lmfit"):
        q = [r["rss_eff"]["spectrafit"] / r["rss_eff"][other] for r in rows]
        eq = [same(r["rss_eff"]["spectrafit"], r["rss_eff"][other]) for r in rows]
        pair[f"spectrafit/{other}"] = {
            "n": len(q),
            "median": float(np.median(q)) if q else None,
            "lt1": sum((not e) and v < 1 for v, e in zip(q, eq, strict=True)),
            "eq1": sum(eq),
            "gt1": sum((not e) and v > 1 for v, e in zip(q, eq, strict=True)),
        }
    out |= {
        "stationary": stat,
        "rss_ratio": ratio,
        "pairwise": pair,
        "iterations": its,
        "success_x_stationary": flags,
    }
    return out


def check_results(rows: list[dict], results: Path | None) -> dict[str, Any]:
    """Compare the captured suite-phase outcomes with ``results.json``."""
    if results is None:
        return {"checked": False}
    suite = {c["id"]: c for c in json.loads(results.read_text(encoding="utf-8"))["suite"]}
    n = mism_success = mism_chi2 = missing = 0
    for r in rows:
        for b, e in r["endpoints"].items():
            m = suite.get(r["case"], {}).get("m", {}).get(b)
            if m is None:
                missing += 1
                continue
            n += 1
            mism_success += bool(m["success"]) != bool(e["harness_success"])
            a, c = float(m["redChi2"]), float(e["outcome_reduced_chi2"])
            mism_chi2 += not (abs(a - c) <= 1e-9 * max(abs(a), abs(c), 1e-300))
    return {
        "checked": True,
        "n": n,
        "missing": missing,
        "success_mismatch": mism_success,
        "red_chi2_mismatch": mism_chi2,
    }


def consistency(rows: list[dict]) -> dict[str, Any]:
    """Suite-phase vs analysed-phase RSS of the same (case, backend)."""
    out = {}
    for b in BACKENDS:
        d = [
            abs(e["seq1_chi2"] - e["outcome_chi2"]) / max(e["outcome_chi2"], 1e-300)
            for r in rows
            if (e := r["endpoints"][b])["seq1_chi2"] is not None
        ]
        rc = [r["endpoints"][b]["chi2_recompute_rel"] for r in rows]
        out[b] = {
            "n": len(d),
            "max_rel_diff": max(d) if d else None,
            "max_rel_rss_recompute_vs_outcome_chi2": max(rc) if rc else None,
        }
    return out


def fmt(v: Any) -> str:
    """Compact number."""
    if v is None:
        return "-"
    if isinstance(v, int):
        return str(v)
    return f"{v:.4g}"


def markdown(t: dict[str, Any]) -> str:
    """table.md from table.json."""
    a = t["all"]
    lines = [
        "# 07 fallback comparison: spectrafit (fallback build) vs scipy trf vs lmfit",
        "",
        f"Common case set: {a['n_cases']} cases (excluded: {len(t['excluded'])}).",
        "Tolerance mode `common` (ftol = xtol = gtol = 1e-8 where the backend has the test).",
        "",
        "## Stationarity (stationary / n)",
        "",
        "| backend | free | at bound | zero RSS |",
        "|---|---|---|---|",
    ]
    for b, s in a["stationary"].items():
        lines.append(
            f"| {b} | {s['free']['stationary']}/{s['free']['n']} | "
            f"{s['at_bound']['stationary']}/{s['at_bound']['n']} | {s['zero_rss']} |",
        )
    lines += [
        "",
        "## RSS ratio RSS_backend / min over the three",
        "",
        "| backend | median | p90 | max | at min (1e-6 rel) |",
        "|---|---|---|---|---|",
    ]
    for b, q in a["rss_ratio"].items():
        lines.append(
            f"| {b} | {fmt(q.get('median'))} | {fmt(q.get('p90'))} | {fmt(q.get('max'))} | "
            f"{q['at_min']}/{q['n']} |",
        )
    lines += ["", "| pair | median | < 1 | = 1 | > 1 |", "|---|---|---|---|---|"]
    for k, p in a["pairwise"].items():
        lines.append(f"| {k} | {fmt(p['median'])} | {p['lt1']} | {p['eq1']} | {p['gt1']} |")
    lines += [
        "",
        "## Iterations and evaluations (median [p25, p75])",
        "",
        "| backend | accepted steps | nfev | njev |",
        "|---|---|---|---|",
    ]
    for b, it in a["iterations"].items():
        cells = [
            "-"
            if not q.get("n")
            else f"{fmt(q['median'])} [{fmt(q['p25'])}, {fmt(q['p75'])}] (n={q['n']})"
            for q in (it["accepted_steps"], it["nfev"], it["njev"])
        ]
        lines.append(f"| {b} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Success flag x stationary",
        "",
        "| backend | flag | S+st | S+non-st | F+st | F+non-st |",
        "|---|---|---|---|---|---|",
    ]
    for b, fl in a["success_x_stationary"].items():
        for flag, c in fl.items():
            v = list(c.values())
            lines.append(f"| {b} | {flag} | {v[0]} | {v[1]} | {v[2]} | {v[3]} |")
    lines += [
        "",
        "## Same case set, split by category",
        "",
        "| part | n | backend | free st/n | at-bound st/n | RSS ratio median | at min |",
        "|---|---|---|---|---|---|---|",
    ]
    for part, s in t["by_part"].items():
        for b in BACKENDS:
            st, q = s["stationary"][b], s["rss_ratio"][b]
            lines.append(
                f"| {part} | {s['n_cases']} | {b} | {st['free']['stationary']}/{st['free']['n']} | "
                f"{st['at_bound']['stationary']}/{st['at_bound']['n']} | {fmt(q.get('median'))} | "
                f"{q['at_min']}/{q['n']} |",
            )
    lines += ["", "## Excluded cases", "", "| case | category | reasons |", "|---|---|---|"]
    lines += [
        f"| {e['case']} | {e['category']} | {'; '.join(e['reasons'])} |" for e in t["excluded"]
    ]
    lines += [
        "",
        "## Checks",
        "",
        f"- results.json vs capture: {t['results_check']}",
        f"- suite vs analysed phase RSS: {t['consistency']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    """Command line."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--results", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    from oracles.cases import build_catalog

    rows, excluded = evaluate_endpoints(load_capture(args.capture), build_catalog())
    parts = {c: [r for r in rows if r["category"] == c] for c in SPLIT_CATEGORIES}
    parts["other"] = [r for r in rows if r["category"] not in SPLIT_CATEGORIES]
    table = {
        "definitions": {
            "AT_BOUND_REL": AT_BOUND_REL,
            "H_REL": H_REL,
            "THETA_FLOOR": THETA_FLOOR,
            "GN_TOL": GN_TOL,
            "EQUIV_TOL": EQUIV_TOL,
            "SAME_REL": SAME_REL,
            "RSS_ZERO_REL": RSS_ZERO_REL,
        },
        "all": summarise(rows),
        "by_part": {k: summarise(v) for k, v in parts.items()},
        "excluded": excluded,
        "results_check": check_results(rows, args.results),
        "consistency": consistency(rows),
        "cases": rows,
    }
    (args.out / "table.json").write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    (args.out / "table.md").write_text(markdown(table), encoding="utf-8")
    print(markdown(table))


if __name__ == "__main__":
    main()
