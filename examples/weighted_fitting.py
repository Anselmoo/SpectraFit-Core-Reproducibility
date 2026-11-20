"""Sigma-weighted fitting: passing per-point uncertainty changes the fit.

When per-point measurement uncertainty is known — heteroscedastic noise,
e.g. counting statistics where the noise standard deviation scales with the
signal itself — pass it as :class:`~spectrafit_core.MeasurementData`'s
``sigma``. This is distinct from :doc:`confidence_intervals`, which derives
*output* uncertainty (``stderr`` -> a confidence interval) from the Jacobian
after the fact, always under the assumption of uniform per-point weighting.
Supplying ``sigma`` here changes an *input*: what the solver actually
minimizes, and which of two different covariance formulas it uses to report
``stderr``.

[Solver — Post-fit statistics](../../explanation/solver-selection.md#post-fit-statistics)
documents both paths precisely:

* No ``sigma`` supplied: ``cov = (JᵀJ)⁻¹ · (chi2 / dof)`` — a
  "scale-from-residuals" estimate that assumes every point is equally
  reliable.
* ``sigma`` supplied: ``cov = (Jw'Jw)⁻¹`` with ``Jw[i, :] = J[i, :] / sigma_i``
  — the Jacobian itself is weighted by each point's actual uncertainty
  before the covariance is formed.

Note that the *reported* ``chi2`` is always the same fresh unweighted
sum-of-squares regardless of ``sigma`` (see the same reference) — ``sigma``
changes what the solver optimizes and how ``stderr`` is computed, not how
``chi2`` is reported.
"""

import numpy as np
from _plotting import ANNOTATION_BBOX, MUTED_COLOR, plot_fit, savefig
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

AMPLITUDE_TRUE, CENTER_TRUE, SIGMA_TRUE, BACKGROUND_TRUE = 30.0, 0.2, 0.7, 4.0
NOISE_SCALE = 0.6


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthesize a peak on a background with Poisson-like, signal-scaled noise.

    ``sigma_i = sqrt(signal_i) * NOISE_SCALE`` mimics counting statistics:
    the low-signal baseline is comparatively quiet, the high-signal peak
    apex is comparatively noisy. Returns ``(x, y, sigma_true)`` — the true
    per-point sigma is normally not directly known, but here it is exactly
    what was used to draw the noise, so it can be passed to the weighted fit
    below as if it came from an independent noise model (e.g. a detector's
    counting-statistics calibration).
    """
    rng = np.random.default_rng(3)
    x = np.linspace(-3, 3, 100)
    signal = BACKGROUND_TRUE + AMPLITUDE_TRUE * np.exp(
        -0.5 * ((x - CENTER_TRUE) / SIGMA_TRUE) ** 2,
    )
    sigma_true = np.sqrt(signal) * NOISE_SCALE
    noise = rng.normal(0, 1, len(x)) * sigma_true
    y = signal + noise
    return x, y, sigma_true


x, y, sigma_true = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """One Gaussian peak + one constant background node (both models fit this)."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=20.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=1.0)},
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:fit_both]
def fit_both(
    x: np.ndarray,
    y: np.ndarray,
    sigma_true: np.ndarray,
) -> dict[str, FitResult]:
    """Fit once with ``sigma=None`` (uniform weighting), once with the true sigma."""
    data_unweighted = MeasurementData(x=x.tolist(), y=y.tolist())
    data_weighted = MeasurementData(
        x=x.tolist(),
        y=y.tolist(),
        sigma=sigma_true.tolist(),
    )
    return {
        "unweighted": fit(build_graph(), data_unweighted),
        "weighted": fit(build_graph(), data_weighted),
    }


results = fit_both(x, y, sigma_true)
unweighted_result, weighted_result = results["unweighted"], results["weighted"]
# --8<-- [end:fit_both]


# --8<-- [start:compare]
def compare(
    x: np.ndarray,
    unweighted_result: FitResult,
    weighted_result: FitResult,
) -> tuple[float, float]:
    """Compare both fits against the true noiseless model in two x-regions.

    ``baseline_mask`` picks points far from the peak (low true signal, low
    true sigma); ``peak_mask`` picks points near the apex (high true signal,
    high true sigma). Returns the mean absolute deviation from the true
    model in the baseline region for ``(unweighted, weighted)`` — the
    concrete number backing the claim that the weighted fit tracks the
    low-noise region more tightly, since it correctly discounts the noisier
    high-signal points instead of treating them as equally trustworthy.
    """
    true_model = BACKGROUND_TRUE + AMPLITUDE_TRUE * np.exp(
        -0.5 * ((x - CENTER_TRUE) / SIGMA_TRUE) ** 2,
    )
    baseline_mask = np.abs(x - CENTER_TRUE) > 2 * SIGMA_TRUE
    err_unweighted = np.abs(np.array(unweighted_result.best_fit) - true_model)
    err_weighted = np.abs(np.array(weighted_result.best_fit) - true_model)
    baseline_err_unweighted = float(err_unweighted[baseline_mask].mean())
    baseline_err_weighted = float(err_weighted[baseline_mask].mean())

    print(f"{'':12s} {'amplitude':>10s} {'stderr':>10s} {'baseline |err|':>16s}")
    for name, result, baseline_err in (
        ("unweighted", unweighted_result, baseline_err_unweighted),
        ("weighted", weighted_result, baseline_err_weighted),
    ):
        amp = result.parameters["peak.amplitude"]
        print(f"{name:12s} {amp.value:10.4f} {amp.stderr:10.4f} {baseline_err:16.4f}")

    assert unweighted_result.success
    assert weighted_result.success
    assert baseline_err_weighted < baseline_err_unweighted, (
        "the weighted fit should track the low-noise baseline more tightly "
        "than the unweighted fit on this seeded example"
    )
    return baseline_err_unweighted, baseline_err_weighted


baseline_err_unweighted, baseline_err_weighted = compare(
    x,
    unweighted_result,
    weighted_result,
)
# --8<-- [end:compare]

if __name__ == "__main__":
    # Plot the weighted fit as the main curve, with the true per-point sigma
    # drawn as error bars and the unweighted fit overlaid for contrast.
    best_fit = np.array(weighted_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        title="Sigma-weighted vs. unweighted fitting under signal-scaled noise",
    )
    ax.errorbar(
        x,
        y,
        yerr=sigma_true,
        fmt="none",
        ecolor=MUTED_COLOR,
        elinewidth=0.8,
        alpha=0.5,
        zorder=1,
    )
    ax.plot(
        x,
        unweighted_result.best_fit,
        color=MUTED_COLOR,
        linestyle=":",
        linewidth=1.6,
        label="unweighted fit",
        zorder=3,
    )
    ax.legend(loc="best")
    ax.text(
        0.02,
        0.02,
        (
            f"baseline mean |err vs. truth|:\n"
            f"  unweighted: {baseline_err_unweighted:.4f}\n"
            f"  weighted:   {baseline_err_weighted:.4f}"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    savefig(fig, "weighted_fitting")
