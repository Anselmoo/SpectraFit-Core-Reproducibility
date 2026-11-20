"""Reduce an ablation run's results.json to per-case rows and the preview table (#93).

Usage: python ablation_summary.py <run-dir> <out-dir>

Writes <out-dir>/per_case.json (per case: med_ms, red_chi2, success per backend)
and <out-dir>/summary.json + prints a Markdown table. Like-for-like rule (WS4):
a (SFC variant, comparator) pair counts on a case only if both report the same
final RSS within 1e-6 relative. Every backend reports reduced chi2 = RSS / (n - n_free)
with the same n and n_free on a case, so equal reduced chi2 within 1e-6 relative is
equal RSS within 1e-6 relative.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REL = 1e-6
SFC = ("spectrafit", "spectrafit_fd")


def main() -> None:
    """Write per_case.json and summary.json and print the preview table."""
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rep = json.loads((run / "results.json").read_text(encoding="utf-8"))
    rows = [
        {
            "id": case["id"],
            "category": case["category"],
            "m": {
                b: {"med_ms": m["medMs"], "red_chi2": m["redChi2"], "success": m["success"]}
                for b, m in sorted(case["m"].items())
            },
        }
        for case in rep["suite"]
    ]
    (out / "per_case.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")

    backends = sorted({b for r in rows for b in r["m"]})
    comparators = [b for b in backends if b not in SFC]
    med = {b: statistics.median(r["m"][b]["med_ms"] for r in rows if b in r["m"]) for b in backends}
    pairs = {}
    for s in SFC:
        for c in [*comparators, *(x for x in SFC if x != s)]:
            ratios = []
            for r in rows:
                a, b = r["m"].get(s), r["m"].get(c)
                if not a or not b or a["med_ms"] <= 0 or b["med_ms"] <= 0:
                    continue
                x, y = a["red_chi2"], b["red_chi2"]
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                if abs(x - y) <= REL * max(abs(x), abs(y)) or x == y:
                    ratios.append(b["med_ms"] / a["med_ms"])
            pairs[f"{s}_vs_{c}"] = {
                "like_for_like_cases": len(ratios),
                "geomean_speedup": math.exp(statistics.fmean(map(math.log, ratios)))
                if ratios
                else None,
                "median_speedup": statistics.median(ratios) if ratios else None,
            }
    summary = {
        "run": run.name,
        "n_cases": len(rows),
        "git_commit": rep.get("gitCommit"),
        "median_med_ms": med,
        "pairs": pairs,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(f"cases: {len(rows)}  commit: {rep.get('gitCommit')}")
    print("| backend | median of per-case median time (ms) |\n|---|---|")
    for b in backends:
        print(f"| {b} | {med[b]:.4g} |")
    print(
        "\n| pair | like-for-like cases | geomean speed-up | median speed-up |\n|---|---|---|---|",
    )
    for k, v in pairs.items():
        g = "n/a" if v["geomean_speedup"] is None else f"{v['geomean_speedup']:.3g}"
        m = "n/a" if v["median_speedup"] is None else f"{v['median_speedup']:.3g}"
        print(f"| {k} | {v['like_for_like_cases']} | {g} | {m} |")


if __name__ == "__main__":
    main()
