#!/usr/bin/env python3
"""Fe L2,3 fit of Fe2O3 from 500 seeded starts, with and without the four tied relationships.

Supplementary to the archive; no claim rests on it. It runs no fit: it reads the spectrafit
fits of the ``eels-far`` target (``results/eels-far/eels_far.json``), which fitted the same
500 start vectors once without and once with the four relationships of ``fig_eels.TIES``,
with the same solver (``FitOptions(solver="lm")`` of the installed wheel), the same bounds and
the same settings; the starts are drawn by ``fig_eels.sample_start`` from
``numpy.random.default_rng([20261110, 0])``. The only difference between the two arms is
whether the relationships are applied.

Writes, next to this script:

* ``eels_with_vs_without_relationships.json``: one record per fit (arm, start, all fitted
  parameters, reported success, termination message, RSS, Gauss-Newton stationarity flag,
  L3 and L2 step amplitudes and their sum, L3 white-line branching ratio by
  ``fig_eels.branching``), the two reference points and the SHA-256 of every input;
* ``eels_with_vs_without_relationships.{pdf,png}``: (a) the distribution of the fitted
  L3 + L2 step amplitude per arm, with the region 2550 to 2700 counts shaded; (b) the fitted
  L3 step amplitude against the fitted L2 step amplitude, coloured by arm, with the same region
  and the two reference points of the fit without the relationships from ``eels_fe2o3.json``:
  the fit from the default start and the lowest point of the L3 step profile.

Run from the repository root:
``uv run --locked python supplementary/eels_with_vs_without_relationships/eels_with_vs_without_relationships.py``
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAME = "eels_with_vs_without_relationships"
ARMS = {"free": "without relationships", "constrained": "with relationships"}
COLOURS = {"free": "#b5651d", "constrained": "#2f6f8f"}
REGION = (2550.0, 2700.0)  # L3 + L2 step amplitude, counts
MM = 1 / 25.4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fig_eels():
    spec = importlib.util.spec_from_file_location("fig_eels", ROOT / "scripts" / "fig_eels.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def records(far: dict, fe) -> list[dict]:
    out = []
    for f in far["fits"]:
        if f["arm"] != "spectrafit" or not f.get("ok") or not f.get("params"):
            continue
        p = f["params"]
        l3, l2 = p["step_l3.amplitude"], p["step_l2.amplitude"]
        out.append({"arm": ARMS[f["model"]], "model": f["model"], "start": f["start"],
                    "success": f["success"], "termination": f["message"], "rss": f["rss"],
                    "stationary": f["stationary"], "step_l3_amplitude": l3, "step_l2_amplitude": l2,
                    "step_sum": l3 + l2, "branching_l3": float(fe.branching(p)),
                    "step_l3_amplitude_stderr": f.get("step_l3_amplitude_stderr"),
                    "condition_number_jtj": f.get("condition_number_jtj"), "params": p})
    return out


def references(eels: dict) -> dict:
    free = eels["free"]
    gmin = eels["profiles"]["free"]["global_minimum"]
    return {
        "default_start_without_relationships": {
            "step_l3_amplitude": free["step_l3"]["value"], "step_l2_amplitude": free["step_l2"]["value"],
            "rss": free["rss"], "success": free["success"], "termination": free["message"]},
        "profile_lowest_point_without_relationships": {
            "step_l3_amplitude": gmin["a"], "step_l2_amplitude": gmin["params"]["step_l2.amplitude"],
            "rss": gmin["rss"], "at_bound": gmin["at_bound"]},
    }


def draw(rows: list[dict], refs: dict, out: Path) -> None:
    plt.rcParams.update({"font.size": 7, "axes.linewidth": 0.6, "pdf.fonttype": 42})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(170 * MM, 70 * MM), layout="constrained")
    sums = {m: np.array([r["step_sum"] for r in rows if r["model"] == m]) for m in ARMS}
    lo = min(float(v.min()) for v in sums.values())
    hi = max(float(v.max()) for v in sums.values())
    bins = np.linspace(min(lo, REGION[0]) - 50.0, max(hi, REGION[1]) + 50.0, 61)
    for ax in (ax1,):
        ax.axvspan(*REGION, color="0.85", lw=0, zorder=0, label="L3 + L2 = 2550 to 2700")
    for m, label in ARMS.items():
        ax1.hist(sums[m], bins=bins, histtype="step", lw=1.0, color=COLOURS[m], label=f"{label} (n={len(sums[m])})")
    ax1.set_xlabel("fitted L3 + L2 step amplitude (counts)")
    ax1.set_ylabel("number of fits")
    ax1.set_title("(a) L3 + L2 step amplitude per arm", loc="left")
    ax1.legend(frameon=False, loc="upper right")

    xmax = max(max(r["step_l3_amplitude"] for r in rows), 1.0) * 1.05
    ymax = max(max(r["step_l2_amplitude"] for r in rows), 1.0) * 1.05
    lo_s, hi_s = REGION  # the band L3 + L2 in [lo_s, hi_s] in the first quadrant
    ax2.fill([0.0, 0.0, hi_s, lo_s], [lo_s, hi_s, 0.0, 0.0], color="0.85", lw=0, zorder=0)
    for m, label in ARMS.items():
        sel = [r for r in rows if r["model"] == m]
        for ok, face in ((True, COLOURS[m]), (False, "none")):
            pts = [(r["step_l3_amplitude"], r["step_l2_amplitude"]) for r in sel if r["success"] is ok]
            if pts:
                a = np.array(pts)
                ax2.scatter(a[:, 0], a[:, 1], s=6, lw=0.5, facecolors=face, edgecolors=COLOURS[m],
                            alpha=0.7, label=f"{label}, success={ok} (n={len(pts)})")
    ax2.plot([0.0, xmax], [0.0, xmax / 2.0], ls="--", lw=0.8, color=COLOURS["constrained"], zorder=1,
             label="with relationships: L2 = L3/2")
    best = min((r for r in rows if r["model"] == "constrained"), key=lambda r: r["rss"])
    ax2.scatter([best["step_l3_amplitude"]], [best["step_l2_amplitude"]], marker="*", s=70,
                facecolors=COLOURS["constrained"], edgecolors="k", lw=0.6, zorder=6,
                label="with relationships, lowest RSS of the 500 fits")
    d, g = refs["default_start_without_relationships"], refs["profile_lowest_point_without_relationships"]
    ax2.scatter([d["step_l3_amplitude"]], [d["step_l2_amplitude"]], marker="X", s=40, c="k", zorder=5,
                label="without relationships, default start")
    ax2.scatter([g["step_l3_amplitude"]], [g["step_l2_amplitude"]], marker="D", s=30, facecolors="none",
                edgecolors="k", lw=1.0, zorder=5, label="without relationships, lowest profile point")
    ax2.set_xlim(0, xmax)
    ax2.set_ylim(0, ymax)
    ax2.set_xlabel("fitted L3 step amplitude (counts)")
    ax2.set_ylabel("fitted L2 step amplitude (counts)")
    ax2.set_title("(b) L3 and L2 step amplitude per fit", loc="left")
    ax2.legend(frameon=False, fontsize=5.5, loc="upper right")
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{NAME}.{ext}", dpi=300 if ext == "png" else None,
                    metadata={"CreationDate": None} if ext == "pdf" else {"Software": None})
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--far", type=Path, default=ROOT / "results" / "eels-far" / "eels_far.json")
    ap.add_argument("--eels", type=Path, default=ROOT / "results" / "eels_fe2o3.json")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    far, eels = json.loads(args.far.read_text()), json.loads(args.eels.read_text())
    fe = load_fig_eels()
    rows = records(far, fe)
    refs = references(eels)
    args.out.mkdir(parents=True, exist_ok=True)
    doc = {"schema": f"{NAME}/1", "spectrafit_core": far["spectrafit_core"],
           "starts": {"n": far["definitions"]["n_starts"], "seed": far["definitions"]["seed"],
                      "stream": far["definitions"]["stream"], "rule": "fig_eels.sample_start"},
           "arms": {m: {"label": l, "n_fits": sum(r["model"] == m for r in rows)} for m, l in ARMS.items()},
           "region_step_sum": list(REGION),
           "inputs_sha256": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha256(p)
                             for p in (args.far, args.eels, ROOT / "scripts" / "fig_eels.py", Path(__file__).resolve())},
           "references": refs, "fits": rows}
    (args.out / f"{NAME}.json").write_text(json.dumps(doc, indent=1) + "\n")
    os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
    draw(rows, refs, args.out)
    print(f"wrote {NAME}.json ({len(rows)} fits), {NAME}.pdf, {NAME}.png in {args.out}")


if __name__ == "__main__":
    main()
