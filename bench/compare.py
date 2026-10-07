#!/usr/bin/env python3
"""Print every timing number the paper reports, archive against measurement, as Markdown.

Left: the 151-case archive shipped in the release (``results/archived/``, pre-release
commit 990a4c7 / 0fd4b5d, 15 to 17 August 2026). Right: the 160-case measurement of
record (``results/timing/``, spectrafit-core 0.1.2, 6 to 7 October 2026). Same
computations as the claims in ``reproduce.py``. Standard library only.

    python bench/compare.py > table.md
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "results"
BACKENDS = ("jax", "scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox")


def gm(xs: list[float]) -> float:
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def numbers(bench: dict, ladder: dict, sweep: dict, agree: dict, bias: dict) -> dict[str, str]:
    cases = bench["cases"]
    speed = [c["m"]["spectrafit"]["speedup"] for c in cases]

    def quickest(c: dict) -> str:
        timed = {s: m["med_ms"] for s, m in c["m"].items() if m and m.get("med_ms") is not None}
        return min(timed, key=timed.get)

    fastest = sum(quickest(c) == "spectrafit" for c in cases)
    lost = sorted({c["category"] for c in cases if quickest(c) != "spectrafit"})
    by_cat: dict[str, list[float]] = {}
    for c in cases:
        by_cat.setdefault(c["category"], []).append(c["m"]["spectrafit"]["speedup"])
    m = bench["manifest"]
    depth = {r["reps_effective"]: r["headline"]["geomean_speedup_vs_baseline"] for r in ladder["rungs"]}
    seeds = [r["headline"]["geomean_speedup_vs_baseline"] for r in sweep["rungs"]]
    dev = sorted(v for v in bias["parity"]["deviations"].values() if v > 0)
    out = {
        "cases": f"{len(cases)}",
        "categories": f"{len(by_cat)}",
        "geometric-mean speed-up vs lmfit": f"{gm(speed):.2f}",
        "harmonic-mean speed-up vs lmfit": f"{len(speed) / sum(1 / x for x in speed):.2f}",
        "largest \\|Δr²\\|": f"{m['max_abs_delta_r2']:.2e}",
        "spectrafit-core win rate (gate)": f"{100 * m['spectrafit_win_rate']:.1f} %",
        "regressions": f"{m['regressions']}",
        "fastest backend on": f"{fastest} of {len(cases)}",
        "categories where it is not fastest": ", ".join(lost),
        "headline without optfn": f"{gm([s for c, s in zip(cases, speed) if c['category'] != 'optfn']):.2f}",
    }
    for b in BACKENDS:
        out[f"factor vs {b}"] = f"{gm([c['m'][b]['med_ms'] / c['m']['spectrafit']['med_ms'] for c in cases if c['m'].get(b) and c['m'][b].get('med_ms')]):.2f}"
    for k in sorted(set(by_cat) | {"robust"}):
        out[f"category {k}"] = f"{gm(by_cat[k]):.2f} ({len(by_cat[k])})" if k in by_cat else "—"
    for eff in sorted(depth):
        out[f"depth {eff} (--reps {2 * eff})"] = f"{depth[eff]:.2f}"
    out |= {
        "seeds": f"{len(seeds)}",
        "seed mean ± sd": f"{st.mean(seeds):.2f} ± {st.stdev(seeds):.2f}",
        "seed range": f"{min(seeds):.2f} to {max(seeds):.2f}",
        "agreement: cases on all six / with truth": f"{agree['n_all_six']} / {agree['n_with_truth']}",
        "agreement: well-conditioned cases": f"{agree['n_well_conditioned']}",
        "agreement: max cross-backend spread": f"{agree['max_cross_backend_spread_pct_points']:.2f} pp",
        "agreement: excluded stratum": f"{agree['excluded_stratum']['n']}",
        "bias: wheel per evaluation": f"{bias['bias']['wheel_us']:.1f} µs",
        "bias: NumPy per evaluation": f"{bias['bias']['numpy_us']:.2f} µs",
        "bias: ratio": f"{bias['bias']['ratio']:.1f}",
        "parity: kernels / exact / largest": f"{len(bias['parity']['deviations'])} / {bias['parity']['n_exact']} / {dev[-1]:.2e}",
    }
    return out


def load(base: Path, ladder: str, sweep: str) -> dict[str, str]:
    j = lambda rel: json.loads((base / rel).read_text())  # noqa: E731
    return numbers(j("bench_summary.json"), j(ladder), j(sweep), j("param_agreement.json"), j("audit_bias.json"))


def main() -> None:
    old = load(ROOT / "archived", "ladder.json", "sweep.json")
    new = load(ROOT / "timing", "ladder/ladder.json", "seed-sweep/sweep.json")
    print("| | 151 cases, `990a4c7`, Aug 2026 (archived) | 160 cases, 0.1.2, Oct 2026 (of record) |")
    print("|---|---|---|")
    for k in dict.fromkeys([*old, *new]):
        print(f"| {k} | {old.get(k, '—')} | {new.get(k, '—')} |")


if __name__ == "__main__":
    main()
