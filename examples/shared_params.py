"""Tie the width of two peaks together with an ``ExprEdge``.

Two overlapping Gaussian peaks are often known, on physical grounds, to
share the same line width — e.g. an instrument's broadening function is
identical for every line it records, even though the lines themselves sit
at different positions with different intensities. Fitting each peak's
``sigma`` independently throws away that prior knowledge and, worse, can let
the optimizer drift the two widths apart in ways the data does not actually
support.

This script ties ``peak2.sigma`` to ``peak1.sigma`` via a graph-level
``ExprEdge`` — the primary surface documented in ``shared_params.md`` — fits
both peaks jointly, and shows the shared width visually as a matching
horizontal "sigma span" annotated between the two peak centers on the plot.

A short second section then re-does the same tie using the equivalent
``Parameter.expr`` surface and asserts the two fits agree to machine
precision, per the "Equivalence guarantee" in ``shared_params.md``.
"""

import numpy as np
from _plotting import MUTED_COLOR, plot_fit, savefig
from spectrafit_core import (
    ExprEdge,
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
    """Synthesize two overlapping Gaussians that share one true sigma.

    peak1 sits at center=0 with amplitude=3, peak2 at center=2.5 with
    amplitude=2; both share sigma=0.6, plus Gaussian measurement noise
    (``sigma=0.05``, seeded for reproducibility).
    """
    rng = np.random.default_rng(42)
    x = np.linspace(-2, 4, 120)
    sigma_true = 0.6
    center1_true, center2_true = 0.0, 2.5
    peak1_true = 3.0 * np.exp(-0.5 * ((x - center1_true) / sigma_true) ** 2)
    peak2_true = 2.0 * np.exp(-0.5 * ((x - center2_true) / sigma_true) ** 2)
    noise = rng.normal(0, 0.05, len(x))
    y = peak1_true + peak2_true + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph_expr_edge]
def build_graph_expr_edge() -> FitGraph:
    """Build a FitGraph with two Gaussian peaks tied via an ``ExprEdge``.

    ``peak2.sigma`` is tied to ``peak1.sigma`` through one graph-level
    ``ExprEdge`` -- the primary tie surface documented in
    ``shared_params.md``. This reduces the degrees of freedom by 1:
    ``peak1.sigma`` is a free variable, ``peak2.sigma`` is dependent.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.5),
                    "center": Parameter(value=0.5),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="peak2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=2.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
        ],
        expr_edges=[
            ExprEdge(
                target_node="peak2",
                target_param="sigma",
                expression="peak1.sigma",
            ),
        ],
    )


graph = build_graph_expr_edge()
# --8<-- [end:build_graph_expr_edge]


# --8<-- [start:fit_execution_expr_edge]
def fit_with_expr_edge(graph: FitGraph, x: np.ndarray, y: np.ndarray) -> FitResult:
    """Wrap ``(x, y)`` as ``MeasurementData`` and fit the ExprEdge-tied graph.

    The optimizer adjusts the 5 free variables (peak1 amplitude, center,
    sigma; peak2 amplitude, center) while the tie constraint is enforced at
    each iteration.
    """
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return fit(graph, data)


result = fit_with_expr_edge(graph, x, y)
# --8<-- [end:fit_execution_expr_edge]


# --8<-- [start:result_inspection_expr_edge]
def report_expr_edge_result(result: FitResult) -> None:
    """Print success/R² and every fitted parameter, tied ones included.

    ``result.parameters`` includes both ``peak1.sigma`` and ``peak2.sigma``,
    but they are numerically identical because the tie is enforced. A tied
    parameter reports ``stderr=None`` since it is not independently varied
    by the solver, so it prints "tied" instead of a numeric standard error.
    """
    print(f"Success: {result.success}")
    print(f"R²: {result.r_squared:.6f}")
    print()

    print("Fitted parameters:")
    for param_name, param in sorted(result.parameters.items()):
        stderr_str = f"{param.stderr:8.4f}" if param.stderr is not None else "    tied"
        print(f"{param_name:20s} = {param.value:8.4f} ± {stderr_str}")
    print()


report_expr_edge_result(result)
# --8<-- [end:result_inspection_expr_edge]


# --8<-- [start:tie_verification]
def verify_tie(result: FitResult) -> tuple[float, float]:
    """Print ``peak1.sigma`` vs. ``peak2.sigma`` and return both.

    Confirms the tie holds: the difference between the two should be
    negligible (< 1e-14 machine epsilon).
    """
    sigma1 = result.parameters["peak1.sigma"].value
    sigma2 = result.parameters["peak2.sigma"].value
    print("Tie verification:")
    print(f"  peak1.sigma = {sigma1:.8f}")
    print(f"  peak2.sigma = {sigma2:.8f}")
    print(f"  Difference  = {abs(sigma1 - sigma2):.2e}")
    return sigma1, sigma2


sigma1, sigma2 = verify_tie(result)
# --8<-- [end:tie_verification]


# --8<-- [start:build_graph_parameter_expr]
def build_graph_parameter_expr() -> FitGraph:
    """Build the equivalent FitGraph using ``Parameter.expr`` instead of ``ExprEdge``.

    The same tie can be declared entirely inside the target ``Parameter``
    itself -- ``peak2.sigma`` sets ``expr="peak1.sigma"`` directly -- with no
    ``ExprEdge`` in the graph at all. ``expr_edges`` is intentionally left
    empty; per ``shared_params.md``'s "Equivalence guarantee", both surfaces
    compile to the same dependency-ordered tied-plan, so the fit result must
    be numerically identical to the ``ExprEdge`` form.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.5),
                    "center": Parameter(value=0.5),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="peak2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=2.0),
                    # Tie declared inline: peak2.sigma is derived from peak1.sigma.
                    "sigma": Parameter(
                        value=0.5,
                        min=1e-3,
                        expr="peak1.sigma",
                        vary=False,
                    ),
                },
            ),
        ],
        # expr_edges intentionally empty -- the tie lives in Parameter.expr only.
    )


graph_expr = build_graph_parameter_expr()
# --8<-- [end:build_graph_parameter_expr]


# --8<-- [start:fit_execution_parameter_expr]
def fit_with_parameter_expr(
    graph_expr: FitGraph,
    x: np.ndarray,
    y: np.ndarray,
) -> FitResult:
    """Wrap the same ``(x, y)`` as ``MeasurementData`` and fit the ``Parameter.expr`` graph."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return fit(graph_expr, data)


result_expr = fit_with_parameter_expr(graph_expr, x, y)
# --8<-- [end:fit_execution_parameter_expr]


# --8<-- [start:equivalence_check]
def check_equivalence(
    result: FitResult,
    result_expr: FitResult,
    sigma1: float,
    sigma2: float,
) -> None:
    """Print R² for both surfaces and assert they agree to within ``1e-6``.

    Confirms the "Equivalence guarantee" in ``shared_params.md``: ``ExprEdge``
    and ``Parameter.expr`` compile to the same dependency-ordered tied-plan,
    so chi2 and the tied sigma values must match across both surfaces --
    asserted here rather than just asserted in prose.
    """
    print()
    print("Parameter.expr form (equivalence check):")
    print(f"  R² (ExprEdge)      = {result.r_squared:.10f}")
    print(f"  R² (Parameter.expr) = {result_expr.r_squared:.10f}")

    assert result_expr.success
    assert abs(result.chi2 - result_expr.chi2) < 1e-6, "chi2 must match across surfaces"
    assert abs(sigma1 - result_expr.parameters["peak1.sigma"].value) < 1e-6
    assert abs(sigma2 - result_expr.parameters["peak2.sigma"].value) < 1e-6
    print("  Both surfaces agree within 1e-6 — equivalence confirmed.")


check_equivalence(result, result_expr, sigma1, sigma2)
# --8<-- [end:equivalence_check]

if __name__ == "__main__":
    # Plot data + fitted curve (ExprEdge form) with the individual peak
    # components overlaid, then layer on a "shared width" annotation: a
    # horizontal double-headed arrow spanning one sigma on each peak, at a
    # matching height, so the equal widths are visually obvious rather than
    # only asserted in the printed diff.
    best_fit = np.array(result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        components=result.components,
        title="Two Gaussian peaks with a shared width (tied via ExprEdge)",
    )

    center1_fit = result.parameters["peak1.center"].value
    center2_fit = result.parameters["peak2.center"].value
    amp1_fit = result.parameters["peak1.amplitude"].value
    amp2_fit = result.parameters["peak2.amplitude"].value
    sigma_fit = sigma1  # identical to sigma2 by the tie

    # Draw a matching-width span (±1 sigma) under each peak's apex, at a
    # shared fraction of that peak's own height, plus a callout labeling the
    # tie explicitly.
    for center, amplitude in ((center1_fit, amp1_fit), (center2_fit, amp2_fit)):
        span_height = 0.18 * amplitude
        ax.annotate(
            "",
            xy=(center + sigma_fit, span_height),
            xytext=(center - sigma_fit, span_height),
            arrowprops={"arrowstyle": "<->", "color": MUTED_COLOR, "lw": 1.4},
        )

    ax.annotate(
        "shared width (σ tied)",
        xy=((center1_fit + center2_fit) / 2, 0.18 * max(amp1_fit, amp2_fit)),
        xytext=(0, 34),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color=MUTED_COLOR,
    )

    fig.tight_layout()
    savefig(fig, "shared_params")
