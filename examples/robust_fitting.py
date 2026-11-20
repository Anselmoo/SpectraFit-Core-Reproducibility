"""Robust fitting against outliers with IRLS.

A handful of corrupted or spiked data points shouldn't be allowed to drag a
plain least-squares fit off the true peak. ``"irls"`` / ``"irls:bisquare"``
/ ``"irls:cauchy"`` (Iteratively Re-weighted Least Squares) down-weight
points with large residuals automatically instead of treating every point
as equally trustworthy. [Choosing a Solver](../../how-to/choosing-a-solver.md)
recommends ``"irls:bisquare"`` (Tukey bisquare weights) once "more than
roughly 5-10% of points are corrupted" — heavier contamination than plain
``"irls"``'s Huber weights are tuned for, but not yet the extreme,
heavy-tailed case ``"irls:cauchy"`` targets. This is the only
outlier-robustness example in the gallery; every IRLS variant is exercised
end-to-end (not just against plain LM) in
``tests/unit/spectrafit_core/test_irls_weights.py``.
"""

import numpy as np
from _plotting import MUTED_COLOR, OUTLINE_COLOR, plot_fit, savefig
from spectrafit_core import (
    FitGraph,
    FitOptions,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

AMPLITUDE_TRUE, CENTER_TRUE, SIGMA_TRUE = 3.0, 0.3, 0.8


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthesize a clean Gaussian peak, then inject a handful of spike outliers.

    Four points (about 2.7% of the 150-point series) get a spike of 2.5-4.0
    in absolute y-units added to their true value -- 0.83-1.33x the true peak
    amplitude of 3.0 -- at random x-positions and random sign, a stand-in for
    detector glitches or cosmic-ray hits rather than ordinary measurement
    noise. Returns ``(x, y, spike_idx)`` so the spikes can be marked on the
    plot.
    """
    rng = np.random.default_rng(21)
    x = np.linspace(-4, 4, 150)
    y_true = AMPLITUDE_TRUE * np.exp(-0.5 * ((x - CENTER_TRUE) / SIGMA_TRUE) ** 2)
    noise = rng.normal(0, 0.06, len(x))
    y = y_true + noise

    n_spikes = 4
    spike_idx = rng.choice(len(x), n_spikes, replace=False)
    spike_magnitude = rng.uniform(2.5, 4.0, n_spikes)
    spike_sign = np.sign(rng.standard_normal(n_spikes))
    y[spike_idx] += spike_magnitude * spike_sign
    return x, y, spike_idx


x, y, spike_idx = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """A single Gaussian peak, amplitude bounded non-negative."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0, min=0.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:fit_both]
def fit_both(x: np.ndarray, y: np.ndarray) -> dict[str, FitResult]:
    """Fit the spiked data with plain ``"lm"`` and with ``"irls:bisquare"``."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return {
        "lm": fit(build_graph(), data, FitOptions(solver="lm")),
        "irls:bisquare": fit(build_graph(), data, FitOptions(solver="irls:bisquare")),
    }


results = fit_both(x, y)
lm_result, irls_result = results["lm"], results["irls:bisquare"]
# --8<-- [end:fit_both]


# --8<-- [start:compare]
def compare(lm_result: FitResult, irls_result: FitResult) -> None:
    """Report recovered center/amplitude error against ground truth, numerically.

    Not just "IRLS looks better on the plot" — the actual absolute error
    against the known planted ``AMPLITUDE_TRUE``/``CENTER_TRUE`` for both
    solvers, so the outlier-robustness claim is a checked number rather than
    an eyeballed curve.
    """
    print(
        f"{'solver':16s} {'amplitude':>10s} {'|err|':>8s} {'center':>9s} {'|err|':>8s}",
    )
    errors: dict[str, tuple[float, float]] = {}
    for name, result in (("lm", lm_result), ("irls:bisquare", irls_result)):
        amp = result.parameters["peak.amplitude"].value
        center = result.parameters["peak.center"].value
        amp_err = abs(amp - AMPLITUDE_TRUE)
        center_err = abs(center - CENTER_TRUE)
        errors[name] = (amp_err, center_err)
        print(f"{name:16s} {amp:10.4f} {amp_err:8.4f} {center:9.4f} {center_err:8.4f}")

    assert lm_result.success
    assert irls_result.success
    lm_amp_err, lm_center_err = errors["lm"]
    irls_amp_err, irls_center_err = errors["irls:bisquare"]
    assert irls_amp_err < lm_amp_err, (
        "irls:bisquare should recover amplitude closer to truth than plain lm "
        "once the spikes are down-weighted"
    )
    assert irls_center_err < lm_center_err, (
        "irls:bisquare should recover center closer to truth than plain lm "
        "once the spikes are down-weighted"
    )


compare(lm_result, irls_result)
# --8<-- [end:compare]

if __name__ == "__main__":
    # Plot the data (spikes marked separately) with both fitted curves
    # overlaid, so the visual pull toward the spikes is directly comparable
    # to the numeric errors reported above.
    fig, ax = plot_fit(
        x,
        y,
        np.array(irls_result.best_fit),
        title="Outlier-robust fitting: plain lm vs. irls:bisquare",
    )
    ax.scatter(
        x[spike_idx],
        y[spike_idx],
        s=60,
        facecolors="none",
        edgecolors=OUTLINE_COLOR,
        linewidths=1.4,
        zorder=5,
        label="injected spikes",
    )
    ax.plot(
        x,
        lm_result.best_fit,
        color=MUTED_COLOR,
        linestyle=":",
        linewidth=1.6,
        label="lm fit (pulled toward spikes)",
        zorder=3,
    )
    ax.legend(loc="best")
    savefig(fig, "robust_fitting")
