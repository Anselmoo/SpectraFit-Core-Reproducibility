"""Preview of the benchmark in both stopping-tolerance modes (package 07, acceptance 3).

Runs every backend of ``oracles.backends.get_backends(tolerance_mode)`` on all 160
cases the way ``Backend.fit`` times them (one untimed warm-up, ``--reps`` timed
``run`` calls with ``build`` outside the timer, metrics from the last timed call) and
records per case: median time, RSS (``BackendOutcome.chi2``), nfev and termination
reason read from the raw library result (``results.json`` carries neither).

    python preview.py run --mode default --out <dir>
    python preview.py run --mode common --out <dir>
    python preview.py analyse --out <dir>

Definitions (fixed in README.md before the run): speed-up of spectrafit against a
comparator on a case = comparator median time / spectrafit median time; aggregated
as the geometric mean (the benchmark's headline statistic) and the median over the
cases where both produced an outcome; like-for-like = the two RSS agree within 1e-6
relative (|a - b| <= 1e-6 min(a, b)); "without optfn" drops the optimization-function
category.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from datetime import UTC, datetime
from importlib import metadata as md
from pathlib import Path
from typing import Any

import numpy as np

LIKE_REL = 1e-6
SUBJECT = "spectrafit"


def termination(backend: str, raw: Any) -> tuple[int | None, str]:
    """(nfev, termination reason) from a backend's raw result."""
    match backend:
        case "spectrafit":
            result, _best = raw
            return result.n_func_evals, f"{result.message} (success={result.success})"
        case "lmfit":
            ier = getattr(raw, "ier", None)
            return int(raw.nfev), f"{raw.message} (ier={ier}, success={raw.success})"
        case "jax":
            steps = int(raw.stats.get("num_steps", 0)) if hasattr(raw, "stats") else None
            return steps, f"{raw.result} (num_steps={steps})"
        case _:
            nfev = int(getattr(raw, "nfev", 0) or 0)
            msg = getattr(raw, "message", "all parameters fixed")
            return nfev, f"status={getattr(raw, 'status', None)}: {msg}"


def run_mode(mode: str, reps: int, out: Path) -> None:
    """All cases x backends in one tolerance mode -> ``<out>/<mode>.json``."""
    from oracles.backends import get_backends
    from oracles.cases import build_catalog

    backends = get_backends(tolerance_mode=mode)
    rows: list[dict[str, Any]] = []
    t_start = time.perf_counter()
    for case in build_catalog():
        for b in backends:
            row: dict[str, Any] = {"case": case.id, "category": case.category, "backend": b.name}
            if not b.is_supported(case):
                rows.append(row | {"supported": False})
                continue
            try:
                b._warmup(case)  # the same warm-up Backend.fit does
                times, raw = [], None
                for _ in range(reps):
                    model = b.build(case)
                    t0 = time.perf_counter()
                    raw = b.run(model, case)
                    times.append((time.perf_counter() - t0) * 1e3)
                outcome = b.extract(raw, case)
                nfev, reason = termination(b.name, raw)
                rows.append(
                    row
                    | {
                        "supported": True,
                        "ms": float(np.median(times)),
                        "ms_reps": times,
                        "rss": float(outcome.chi2),
                        "success": bool(outcome.success),
                        "nfev": nfev,
                        "termination": reason,
                    },
                )
            except Exception as exc:  # noqa: BLE001  # recorded with the case
                rows.append(row | {"supported": True, "error": f"{type(exc).__name__}: {exc}"})
        print(f"{mode} {case.id} done ({time.perf_counter() - t_start:.0f}s)", flush=True)
    record = {
        "mode": mode,
        "tolerances": None
        if backends[0].tolerances is None
        else backends[0].tolerances.model_dump(),
        "reps": reps,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": {"node": platform.node(), "platform": platform.platform()},
        "python": sys.version.split()[0],
        "versions": {
            p: md.version(p)
            for p in ("spectrafit-core", "lmfit", "scipy", "numpy", "jax", "optimistix")
        },
        "spectrafit_core_direct_url": md.distribution("spectrafit-core").read_text(
            "direct_url.json",
        ),
        "wall_s": time.perf_counter() - t_start,
        "rows": rows,
    }
    (out / f"{mode}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


def _like(a: float, b: float) -> bool:
    return abs(a - b) <= LIKE_REL * min(a, b) if min(a, b) > 0 else a == b


def speedups(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per comparator: speed-up aggregates over all / like-for-like, with and without optfn."""
    by = {(r["case"], r["backend"]): r for r in rows if "ms" in r}
    comparators = sorted({r["backend"] for r in rows} - {SUBJECT})
    out: dict[str, dict[str, Any]] = {}
    for comp in comparators:
        pairs = [
            (
                cid,
                cat,
                by[(cid, comp)]["ms"] / by[(cid, SUBJECT)]["ms"],
                _like(by[(cid, SUBJECT)]["rss"], by[(cid, comp)]["rss"]),
            )
            for (cid, b), r in by.items()
            if b == SUBJECT and (cid, comp) in by
            for cat in [r["category"]]
        ]
        res: dict[str, Any] = {}
        for scope, keep in (("all", lambda p: True), ("without_optfn", lambda p: p[1] != "optfn")):
            for subset, like in (("all_cases", False), ("like_for_like", True)):
                vals = [p[2] for p in pairs if keep(p) and (p[3] or not like)]
                res[f"{scope}/{subset}"] = {
                    "n": len(vals),
                    "geomean": math.exp(float(np.mean(np.log(vals)))) if vals else None,
                    "median": float(np.median(vals)) if vals else None,
                }
        out[comp] = res
    return out


def analyse(out: Path) -> None:
    """Both modes -> ``summary.json`` and ``report.md``."""
    recs = {
        m: json.loads((out / f"{m}.json").read_text(encoding="utf-8"))
        for m in ("default", "common")
    }
    summary = {m: speedups(r["rows"]) for m, r in recs.items()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    lines = ["# Common-tolerance preview: speed-up of spectrafit per comparator", ""]
    for m, r in recs.items():
        lines += [
            (
                f"- {m}: tolerances {r['tolerances']}, reps {r['reps']}, wall {r['wall_s'] / 60:.1f} min, "
                f"spectrafit-core {r['versions']['spectrafit-core']} ({r['spectrafit_core_direct_url']}), "
                f"host {r['host']['node']}"
            ),
        ]
    lines += [
        "",
        "| mode | comparator | scope | cases | n | geomean | median |",
        "|---|---|---|---|---|---|---|",
    ]
    for m, per in summary.items():
        for comp, res in per.items():
            for key, v in res.items():
                scope, subset = key.split("/")
                g = "-" if v["geomean"] is None else f"{v['geomean']:.3g}"
                md_ = "-" if v["median"] is None else f"{v['median']:.3g}"
                lines.append(f"| {m} | {comp} | {scope} | {subset} | {v['n']} | {g} | {md_} |")
    lines += [
        "",
        "## Termination reasons per backend and mode",
        "",
        "| mode | backend | reason | n |",
        "|---|---|---|---|",
    ]
    for m, r in recs.items():
        counts: dict[tuple[str, str], int] = {}
        for row in r["rows"]:
            if row.get("supported") is False:
                continue
            reason = row.get("termination") or row.get("error", "?")
            key = (row["backend"], reason.split(" (")[0][:90])
            counts[key] = counts.get(key, 0) + 1
        lines += [f"| {m} | {b} | {t} | {n} |" for (b, t), n in sorted(counts.items())]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[: 8 + 4 * 6 * 2]))


def main() -> None:
    """Command line."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("run", "analyse"))
    ap.add_argument("--mode", dest="tol_mode", choices=("default", "common"))
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    match args.mode:
        case "run":
            run_mode(args.tol_mode, args.reps, args.out)
        case _:
            analyse(args.out)


if __name__ == "__main__":
    main()
