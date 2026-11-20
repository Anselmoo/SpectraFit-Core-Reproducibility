"""Escaping local minima with the global solver.

When initial guesses are poor, or the objective is genuinely multi-modal
(e.g. two overlapping peaks whose starting positions are ambiguous or
swapped), a local solver like ``"lm"`` can stop far from the right answer.
``"global"`` (Differential Evolution + LM refinement, per
:class:`~spectrafit_core.FitOptions`'s own docstring) explores the full
parameter space with DE before refining locally, at the cost of materially
more wall-clock time than any local solver.

``solver="global"`` does not appear in any other gallery script — it is
real and exercised by the Rust solver's own optimization-landscape test
suite, but this is its first demonstration on a spectroscopy-shaped fit
rather than a synthetic test function.
"""

import time

import numpy as np
from _plotting import ANNOTATION_BBOX, MUTED_COLOR, plot_fit, savefig
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

PEAK1_TRUE = {"amplitude": 2.0, "center": -3.0, "sigma": 0.6}
PEAK2_TRUE = {"amplitude": 1.4, "center": 3.0, "sigma": 0.6}


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize two well-separated Gaussian peaks (with noise)."""
    rng = np.random.default_rng(4)
    x = np.linspace(-6, 6, 200)
    y_true = PEAK1_TRUE["amplitude"] * np.exp(
        -0.5 * ((x - PEAK1_TRUE["center"]) / PEAK1_TRUE["sigma"]) ** 2,
    ) + PEAK2_TRUE["amplitude"] * np.exp(
        -0.5 * ((x - PEAK2_TRUE["center"]) / PEAK2_TRUE["sigma"]) ** 2,
    )
    noise = rng.normal(0, 0.05, len(x))
    y = y_true + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """Two Gaussian nodes, both initial ``center`` guesses seeded at 0.0.

    A deliberately bad start: rather than guessing near either true peak
    (-3.0 and 3.0), both nodes start at the same wrong location, squarely
    between them. A local solver has no gradient information pointing it
    toward the correct two-peak split from here.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="p1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0, min=-6.0, max=6.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="p2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0, min=-6.0, max=6.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:run_solvers]
def run_solvers(data: MeasurementData) -> dict[str, tuple[FitResult, float]]:
    """Fit the same bad-start graph with ``"lm"`` and ``"global"``, timed.

    Returns ``{"lm": (result, elapsed_s), "global": (result, elapsed_s)}``.
    Single timed calls, not a median-of-many like ``varpro_vs_lm.py`` —
    ``"global"``'s differential-evolution search is meaningfully slower per
    call, and one measurement is enough to show the order-of-magnitude gap
    without materially slowing down gallery regeneration.
    """
    runs: dict[str, tuple[FitResult, float]] = {}
    for solver_name in ("lm", "global"):
        start = time.perf_counter()
        result = fit(build_graph(), data, FitOptions(solver=solver_name))
        elapsed = time.perf_counter() - start
        runs[solver_name] = (result, elapsed)
    return runs


data = MeasurementData(x=x.tolist(), y=y.tolist())
runs = run_solvers(data)
lm_result, lm_time = runs["lm"]
global_result, global_time = runs["global"]
# --8<-- [end:run_solvers]


# --8<-- [start:compare]
def compare(lm_result: FitResult, global_result: FitResult) -> None:
    """Report chi2/r_squared for both — the concrete evidence of the wrong answer.

    ``lm``, started with both peaks at the same wrong location, stops
    (``converged_ftol``) where both peaks coincide in a single broad blob
    straddling the gap between the true peaks. The Jacobian is rank-deficient
    there, so the end point cannot be verified as a minimum, and
    ``success=False`` reports that; ``chi2`` and $r^2 = 0.035$ show the wrong
    answer. ``global`` explores via differential evolution first
    (``n_de_generations`` reports how many generations that took) and
    recovers the planted two-peak solution.
    """
    print(f"{'solver':8s} {'chi2':>10s} {'r_squared':>10s} {'success':>8s}")
    for name, result in (("lm", lm_result), ("global", global_result)):
        print(
            f"{name:8s} {result.chi2:10.3f} {result.r_squared:10.4f} {result.success!s:>8s}",
        )
    print(f"\nglobal: n_de_generations = {global_result.n_de_generations}")

    assert not lm_result.success
    assert global_result.success
    assert global_result.r_squared > 0.98, (
        "global should recover the true two-peak solution on this fixture"
    )
    assert lm_result.r_squared < 0.5, (
        "lm, started with both peaks at the same wrong location, should stop "
        "at a visibly wrong end point on this fixture"
    )
    assert global_result.chi2 < lm_result.chi2


compare(lm_result, global_result)
# --8<-- [end:compare]

if __name__ == "__main__":
    # Plot the data with the global solver's correct two-peak fit, overlaying
    # lm's wrong end point for contrast, with a text panel reporting the
    # measured wall-clock gap and fit-quality numbers.
    fig, ax = plot_fit(
        x,
        y,
        np.array(global_result.best_fit),
        components=global_result.components,
        title="Bad initial guess: lm's wrong end point vs. global's correct fit",
    )
    ax.plot(
        x,
        lm_result.best_fit,
        color=MUTED_COLOR,
        linestyle=":",
        linewidth=1.6,
        label="lm fit (peaks coincide)",
        zorder=3,
    )
    ax.legend(loc="best")
    ax.text(
        0.02,
        0.02,
        (
            f"lm:     r2={lm_result.r_squared:.3f}, chi2={lm_result.chi2:.2f}, "
            f"{lm_time * 1e3:.2f} ms\n"
            f"global: r2={global_result.r_squared:.3f}, chi2={global_result.chi2:.2f}, "
            f"{global_time * 1e3:.2f} ms ({global_result.n_de_generations} DE generations)"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    savefig(fig, "global_optimizer")
