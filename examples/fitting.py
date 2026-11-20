"""Fit a single Gaussian peak plus a constant background, then plot the result.

The simplest possible spectrafit_core workflow: one peak node, one background
node, a single dataset. See ``fitting.md`` for the narrative walkthrough.
"""

import numpy as np
from _plotting import plot_fit, savefig
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize a single Gaussian peak (amplitude 2.0, center 0.5) in noisy background.

    Adds a 0.1 constant background plus Gaussian measurement noise
    (``sigma=0.05``, seeded for reproducibility).
    """
    rng = np.random.default_rng(42)
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
    """Build a FitGraph: one Gaussian peak + one constant background.

    The ``sigma`` parameter has a lower bound ``min=1e-3`` to prevent the
    optimizer from driving it to zero.
    """
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
                parameters={
                    "c": Parameter(value=0.0),
                },
            ),
        ],
    )


graph = build_graph()
# --8<-- [end:build_graph]


# --8<-- [start:fit_execution]
def run_fit(graph: FitGraph, x: np.ndarray, y: np.ndarray) -> FitResult:
    """Wrap the measurement data and invoke the Levenberg-Marquardt solver.

    ``fit(graph, data)`` iteratively adjusts parameters to minimize the
    residuals until convergence.
    """
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return fit(graph, data)


result = run_fit(graph, x, y)
# --8<-- [end:fit_execution]


# --8<-- [start:result_inspection]
def report_result(result: FitResult) -> None:
    """Print success/goodness-of-fit, fitted parameters, and residual summary.

    Reads ``success`` (did the solver converge), ``r_squared`` and ``chi2``
    (goodness-of-fit), ``parameters`` (value ± stderr per fitted parameter,
    1sigma), and ``residuals`` (observed minus fitted, whose RMS and range
    describe noise level and systematic error).
    """
    print(f"Success: {result.success}")
    print(f"R²: {result.r_squared:.6f}")
    print(f"χ²: {result.chi2:.6f}")
    print()

    for param_name, param in sorted(result.parameters.items()):
        print(f"{param_name:15s} = {param.value:8.4f} ± {param.stderr:8.4f}")
    print()

    residuals = np.array(result.residuals)
    print(f"Residual RMS:   {np.sqrt(np.mean(residuals**2)):.6f}")
    print(f"Residual range: [{np.min(residuals):.6f}, {np.max(residuals):.6f}]")


report_result(result)
# --8<-- [end:result_inspection]

if __name__ == "__main__":
    # Plot data + fitted curve with a residuals subplot below.
    best_fit = np.array(result.best_fit)
    fit_residuals = y - best_fit
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        residuals=fit_residuals,
        title="Single-dataset Gaussian fit",
    )
    savefig(fig, "fitting")
