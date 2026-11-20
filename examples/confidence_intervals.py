"""Compute 95% confidence intervals for fitted parameters.

Every :class:`~spectrafit_core.ParameterResult` carries ``stderr``, the
estimated standard error (1-sigma) of that parameter, derived from the
diagonal of the fit's covariance matrix (see
[Solver — Post-fit statistics](../../explanation/solver-selection.md#post-fit-statistics)).
This script turns that into the more commonly reported 95% confidence
interval using the standard normal ("Wald") approximation:

    ci_95 = value +/- 1.959964 * stderr

This is a **linear approximation** around the fitted optimum — it assumes
the parameter's sampling distribution is well described by a normal
distribution with the reported variance. That holds well for well-determined,
close-to-linear problems (the case here), but can understate or misshape the
true interval for a strongly nonlinear or poorly-determined parameter. A
tighter alternative (profile-likelihood confidence intervals, which trace the
actual chi2 surface rather than assuming a local quadratic shape) is not yet
covered by a gallery tutorial. See ``confidence_intervals.md`` for the
narrative walkthrough.
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

# Standard normal two-sided 95% critical value (scipy.stats.norm.ppf(0.975)).
Z_95 = 1.959964


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize a single Gaussian peak on a constant background (with noise).

    Same shape as fitting.py, extended here with confidence-interval
    reporting downstream.
    """
    rng = np.random.default_rng(3)
    x = np.linspace(-3, 3, 100)
    peak = 2.0 * np.exp(-0.5 * ((x - 0.5) / 0.8) ** 2)
    background = 0.1
    noise = rng.normal(0, 0.05, len(x))
    y = peak + background + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """Build a FitGraph: one Gaussian peak + one constant background."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.5),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=0.0)},
            ),
        ],
    )


graph = build_graph()
# --8<-- [end:build_graph]


# --8<-- [start:fit_execution]
def run_fit(graph: FitGraph, x: np.ndarray, y: np.ndarray) -> FitResult:
    """Wrap the measurement data and invoke the Levenberg-Marquardt solver."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return fit(graph, data)


result = run_fit(graph, x, y)
# --8<-- [end:fit_execution]


# --8<-- [start:confidence_intervals]
def build_confidence_intervals(result: FitResult) -> dict[str, tuple[float, float]]:
    """Print success/R², then turn each parameter's ``stderr`` into a 95% Wald CI.

    ``ci_95 = value +/- Z_95 * stderr`` (see the module docstring for the
    linear-approximation caveat). Asserts the fit succeeded and every
    returned CI is properly ordered (lo <= hi).
    """
    print(f"Success: {result.success}")
    print(f"R²: {result.r_squared:.6f}")
    print()

    print(
        f"{'parameter':18s} {'value':>10s} {'stderr':>10s} {'95% CI low':>12s} {'95% CI high':>12s}",
    )
    ci_by_param: dict[str, tuple[float, float]] = {}
    for name, param in sorted(result.parameters.items()):
        if param.stderr is None:
            print(
                f"{name:18s} {param.value:10.4f} {'n/a':>10s} {'n/a':>12s} {'n/a':>12s}",
            )
            continue
        half_width = Z_95 * param.stderr
        ci_lo, ci_hi = param.value - half_width, param.value + half_width
        ci_by_param[name] = (ci_lo, ci_hi)
        print(
            f"{name:18s} {param.value:10.4f} {param.stderr:10.4f} {ci_lo:12.4f} {ci_hi:12.4f}",
        )

    assert result.success
    assert all(lo <= hi for lo, hi in ci_by_param.values()), "CI bounds must be ordered"
    return ci_by_param


ci_by_param = build_confidence_intervals(result)
# --8<-- [end:confidence_intervals]

if __name__ == "__main__":
    # Plot data + fitted curve with a residuals subplot, then annotate the
    # peak's center and amplitude with their 95% CI directly on the plot.
    best_fit = np.array(result.best_fit)
    fit_residuals = y - best_fit
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        residuals=fit_residuals,
        title="Single-peak fit with 95% parameter confidence intervals",
    )

    center = result.parameters["peak.center"].value
    amplitude = result.parameters["peak.amplitude"].value
    center_lo, center_hi = ci_by_param["peak.center"]
    amp_lo, amp_hi = ci_by_param["peak.amplitude"]

    # Vertical error bar on the peak apex for the amplitude CI.
    ax.errorbar(
        [center],
        [amplitude],
        yerr=[[amplitude - amp_lo], [amp_hi - amplitude]],
        fmt="none",
        ecolor=MUTED_COLOR,
        elinewidth=1.4,
        capsize=4,
        zorder=4,
    )
    # Horizontal error bar at the apex height for the center CI.
    ax.errorbar(
        [center],
        [amplitude],
        xerr=[[center - center_lo], [center_hi - center]],
        fmt="o",
        color=MUTED_COLOR,
        markersize=4,
        elinewidth=1.4,
        capsize=4,
        zorder=4,
    )
    ax.text(
        0.98,
        0.05,
        f"center    = {center:.3f}  95% CI [{center_lo:.3f}, {center_hi:.3f}]\n"
        f"amplitude = {amplitude:.3f}  95% CI [{amp_lo:.3f}, {amp_hi:.3f}]",
        transform=ax.transAxes,
        fontsize=8,
        ha="right",
        va="bottom",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    savefig(fig, "confidence_intervals")
