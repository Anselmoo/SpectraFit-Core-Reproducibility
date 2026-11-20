"""Compare VarPro against Levenberg-Marquardt on a separable multi-peak fit.

VarPro (``solver="varpro"``) solves each node's linear amplitude coefficient
analytically at every step, so its outer optimizer only ever sees the
nonlinear shape parameters (``center``, ``sigma``) — a smaller, often
better-conditioned parameter space than LM's, which optimizes amplitude and
shape together. This holds exactly when VarPro's preconditions hold: no tied
parameters, and no bound constraints on the nonlinear parameters. The graph
below (two bare Gaussian peaks, no background node) is built without any
``min``/``max`` on ``center``/``sigma`` and without any ``ExprEdge``, so it
stays squarely inside those preconditions.

This script reports **measured** wall-clock time for both solvers on one
small demo problem — it is not a general performance claim. Whether VarPro
or LM is faster in absolute terms depends on problem size, peak count, and
hardware; the project's own aggregate speed comparison across the full
benchmark case catalog lives on the [Performance](../../performance/index.md)
page, not in this gallery script. See ``varpro_vs_lm.md`` for the narrative
walkthrough.
"""

import time

import numpy as np
from _plotting import ANNOTATION_BBOX, plot_fit, savefig
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


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize two overlapping Gaussians of different width and amplitude.

    No background node — ``amplitude`` is the only linear parameter per
    node, which is what keeps the graph built from this data inside
    VarPro's separability preconditions (see the module docstring).
    """
    rng = np.random.default_rng(7)
    x = np.linspace(-4, 6, 200)
    sigma1_true, sigma2_true = 0.7, 1.0
    center1_true, center2_true = 0.0, 3.0
    peak1_true = 2.5 * np.exp(-0.5 * ((x - center1_true) / sigma1_true) ** 2)
    peak2_true = 1.8 * np.exp(-0.5 * ((x - center2_true) / sigma2_true) ** 2)
    noise = rng.normal(0, 0.04, len(x))
    y = peak1_true + peak2_true + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """A fresh, unbounded, untied FitGraph — VarPro's preconditions hold."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.3),
                    "sigma": Parameter(value=0.5),
                },
            ),
            ModelNodeSpec(
                id="peak2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.5),
                    "center": Parameter(value=2.7),
                    "sigma": Parameter(value=0.8),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:run_solvers]
def run_solvers(
    data: MeasurementData,
    n_reps: int = 9,
) -> dict[str, tuple[FitResult, float]]:
    """Fit ``build_graph()`` with both solvers, print the side-by-side report.

    A fresh ``FitGraph`` is built per call (cheap, and avoids any doubt about
    shared mutable state). One untimed warm-up call per solver first
    (import/JIT-style first-call overhead is not representative of
    steady-state solver cost), then the median of ``n_reps`` timed reps.

    Returns ``{"lm": (result, median_time), "varpro": (result, median_time)}``.
    """
    runs: dict[str, tuple[FitResult, float]] = {}
    for solver_name in ("lm", "varpro"):
        result = fit(
            build_graph(),
            data,
            FitOptions(solver=solver_name),
        )  # warm-up, untimed
        times: list[float] = []
        for _ in range(n_reps):
            graph = build_graph()
            start = time.perf_counter()
            result = fit(graph, data, FitOptions(solver=solver_name))
            times.append(time.perf_counter() - start)
        median_time = sorted(times)[len(times) // 2]
        runs[solver_name] = (result, median_time)

    print(
        f"{'solver':8s} {'success':8s} {'n_iter':7s} {'chi2':>12s} {'median wall time':>18s}",
    )
    for name, (result, elapsed) in runs.items():
        print(
            f"{name:8s} {result.success!s:8s} {result.n_iter:7d} "
            f"{result.chi2:12.6f} {elapsed * 1e3:15.3f} ms",
        )
    return runs


# Prepare measurement data (shared across both solver runs).
data = MeasurementData(x=x.tolist(), y=y.tolist())
N_REPS = 9
runs = run_solvers(data, N_REPS)
lm_result, lm_time = runs["lm"]
varpro_result, varpro_time = runs["varpro"]
# --8<-- [end:run_solvers]


# --8<-- [start:verify_agreement]
def verify_agreement(lm_result: FitResult, varpro_result: FitResult) -> None:
    """Print per-parameter deltas, then assert both solvers agree.

    This is the actual guaranteed property: VarPro is not a different
    model, just a different (smaller) parameter space to search. ``chi2``
    is asserted to match within ``1e-4``; every fitted parameter agrees to
    within ``1e-7`` in practice (see the printed deltas below).
    """
    print()
    print("Fitted parameters agree between solvers to within:")
    for node, param in (
        ("peak1", "amplitude"),
        ("peak1", "center"),
        ("peak1", "sigma"),
        ("peak2", "amplitude"),
        ("peak2", "center"),
        ("peak2", "sigma"),
    ):
        key = f"{node}.{param}"
        diff = abs(
            lm_result.parameters[key].value - varpro_result.parameters[key].value,
        )
        print(f"  {key:18s} Delta = {diff:.2e}")

    assert lm_result.success
    assert varpro_result.success
    assert abs(lm_result.chi2 - varpro_result.chi2) < 1e-4, (
        "lm and varpro should converge to the same optimum on this separable problem"
    )


verify_agreement(lm_result, varpro_result)
# --8<-- [end:verify_agreement]

if __name__ == "__main__":
    # Plot data + the VarPro fit (the two solvers' curves are visually
    # indistinguishable at this scale — the assertion above is what actually
    # proves agreement) with a text panel reporting both solvers' measured
    # stats directly on the plot, neither declared a "winner".
    best_fit = np.array(varpro_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        components=varpro_result.components,
        title="Separable 2-peak fit: VarPro vs. Levenberg-Marquardt",
    )
    ax.text(
        0.02,
        0.02,
        (
            f"lm:     {lm_result.n_iter} iter, {lm_time * 1e3:.3f} ms (median of {N_REPS})\n"
            f"varpro: {varpro_result.n_iter} iter, {varpro_time * 1e3:.3f} ms (median of {N_REPS})\n"
            "both converge to the same chi2 (see assertion above)"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    fig.tight_layout()
    savefig(fig, "varpro_vs_lm")
