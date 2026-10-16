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
from spectrafit_core import (
    MeasurementData, FitOptions, __version__ as SF_VERSION, arctan_step, compose, constant, fit,
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


def read_msa(path: Path) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for line in path.read_text(encoding="latin-1").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        left, _, right = line.partition(",")
        x.append(float(left))
        y.append(float(right))
    return np.asarray(x), np.asarray(y)


def bounded(factory, node_id, **spec):
    """``spec``: name=(start, lower, upper); None leaves a side open."""
    kwargs = {}
    for name, (start, lower, upper) in spec.items():
        kwargs[name] = start
        if lower is not None:
            kwargs[f"{name}_min"] = lower
        if upper is not None:
            kwargs[f"{name}_max"] = upper
    return factory(node_id, **kwargs)


def nodes(start: dict | None = None):
    """Same components and bounds for both fits; ``start`` overrides the starting values."""
    s = start or {}

    def v(key, default):
        return s.get(key, default)

    out = [
        bounded(constant, "bg", c=(v("bg.c", 5700.0), 0.0, None)),
        bounded(arctan_step, "step_l3", amplitude=(v("step_l3.amplitude", 1900.0), 0.0, None),
                center=(v("step_l3.center", 710.0), 705.0, 715.0), sigma=(v("step_l3.sigma", 0.6), 0.3, 5.0)),
        bounded(arctan_step, "step_l2", amplitude=(v("step_l2.amplitude", 950.0), 0.0, None),
                center=(v("step_l2.center", 723.0), 718.0, 728.0), sigma=(v("step_l2.sigma", 0.6), 0.3, 5.0)),
    ]
    for node_id, centre, height, width in L3_LINES + L2_LINES:
        out.append(bounded(gaussian, node_id, amplitude=(v(f"{node_id}.amplitude", height), 0.0, None),
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
    args = ap.parse_args()
    digest = hashlib.sha256(args.spectrum.read_bytes()).hexdigest()
    if digest != SPECTRUM_SHA256:
        raise SystemExit(f"{args.spectrum} is not the EELSDB file this figure is made from ({digest})")

    raw_x, raw_y = read_msa(args.spectrum)
    keep = (raw_x >= WINDOW_EV[0]) & (raw_x <= WINDOW_EV[1])
    x, y = raw_x[keep], raw_y[keep]
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    options = FitOptions(solver="lm")

    constrained = (compose(nodes())
                   .bind("step_l3.amplitude / 2", to="step_l2.amplitude")
                   .bind("step_l3.sigma", to="step_l2.sigma")
                   .bind("l3_c.center", to="step_l3.center")
                   .bind("l2_b.center", to="step_l2.center"))
    fit_c = fit(constrained.build(), data, options)
    # The free fit from two starts: the default guesses and the constrained solution.
    starts = {"default": fit(compose(nodes()).build(), data, options),
              "constrained_solution": fit(compose(nodes({k: p.value for k, p in fit_c.parameters.items()})).build(),
                                          data, options)}
    best = min(starts, key=lambda k: rss(starts[k], y))
    fits = {"free": starts[best], "constrained": fit_c}
    n_params = sum(len(n.parameters) for n in nodes())

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
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "eels_fe2o3.json").write_text(json.dumps(record, indent=1) + "\n")
    plot(x, y, fits, record, args.out / "figure4_eels.png")
    for key in ("free", "constrained"):
        r = record[key]
        print(f"{key:12s} r2={r['r_squared']:.4f} steps={r['step_l3']['value']:.0f}/"
              f"{r['step_l2']['value']:.4g} branching={r['branching_l3']['value']:.3f}"
              f"±{r['branching_l3']['stderr']:.3f}")


if __name__ == "__main__":
    main()
