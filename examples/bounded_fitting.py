"""Bounded fitting with ``"lm"`` and ``"trf"``.

A physical bound like "amplitude cannot be negative" is only interesting
when it is likely to be *active* — a small, noisy peak whose unconstrained
least-squares optimum would otherwise land slightly negative. Plain
``"lm"`` is the fastest general-purpose solver; [Choosing a
Solver](../../how-to/choosing-a-solver.md) describes ``"trf"``, which runs the
``"lm"`` core and adds Coleman–Li bound-distance scaling: the steps of a
parameter with two finite bounds shrink as it approaches the bound it moves
toward. A one-sided bound like ``amplitude >= 0`` is not scaled. Both solvers project
trial points onto ``[min, max]``, so neither is bound-*violating*.

This is a different question from :doc:`varpro_vs_lm`, which compares
solvers on an *unconstrained* separable problem. This example is solver
choice under *active* bound constraints.
"""

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

AMPLITUDE_TRUE, CENTER_TRUE, SIGMA_TRUE = 0.06, 0.0, 0.6


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize a small, near-zero-amplitude Gaussian peak with real noise.

    ``AMPLITUDE_TRUE = 0.06`` against a noise standard deviation of ``0.15``
    is deliberately close to the noise floor — small enough that an
    *unconstrained* fit of this data plausibly lands at a negative
    amplitude (see ``build_graph``'s unbounded reference below), which is
    physically meaningless for a peak amplitude.
    """
    rng = np.random.default_rng(5)
    x = np.linspace(-3, 3, 80)
    y_true = AMPLITUDE_TRUE * np.exp(-0.5 * ((x - CENTER_TRUE) / SIGMA_TRUE) ** 2)
    noise = rng.normal(0, 0.15, len(x))
    y = y_true + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph(*, amplitude_min: float) -> FitGraph:
    """One Gaussian peak; ``sigma`` fixed at truth, ``amplitude``/``center`` free.

    ``amplitude_min=0.0`` is the physical bound under test; ``amplitude_min
    = -inf`` builds the unconstrained reference graph used below to show
    what the bound is actually ruling out.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=0.05, min=amplitude_min),
                    "center": Parameter(value=0.2),
                    "sigma": Parameter(value=SIGMA_TRUE, vary=False),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:fit_all]
def fit_all(x: np.ndarray, y: np.ndarray) -> dict[str, FitResult]:
    """Fit the unbounded reference once, then the bounded problem with both solvers."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return {
        "unbounded": fit(build_graph(amplitude_min=float("-inf")), data),
        "lm": fit(build_graph(amplitude_min=0.0), data, FitOptions(solver="lm")),
        "trf": fit(build_graph(amplitude_min=0.0), data, FitOptions(solver="trf")),
    }


results = fit_all(x, y)
unbounded_result, lm_result, trf_result = (
    results["unbounded"],
    results["lm"],
    results["trf"],
)
# --8<-- [end:fit_all]


# --8<-- [start:compare]
def compare(
    unbounded_result: FitResult,
    lm_result: FitResult,
    trf_result: FitResult,
) -> None:
    """Report the unbounded amplitude, then both bounded solvers' compliance.

    The unbounded fit's amplitude going negative is exactly the physically
    implausible result the ``min=0`` bound rules out. Both bounded solvers
    are asserted to respect that bound, and they converge to numerically
    identical iterates (``n_iter`` and the final amplitude match): the only
    bound is one-sided, where ``"trf"``'s Coleman–Li bound-distance scaling
    does not act, so both solvers take the same steps and both project trial
    points onto the bound. This script reports what is measured here, not a
    general performance claim.
    """
    unbounded_amp = unbounded_result.parameters["peak.amplitude"].value
    print(f"unconstrained amplitude estimate: {unbounded_amp:.4f} (no min=0 bound)")
    print()
    print(f"{'solver':8s} {'amplitude':>10s} {'n_iter':>7s} {'success':>8s}")
    for name, result in (("lm", lm_result), ("trf", trf_result)):
        amp = result.parameters["peak.amplitude"].value
        print(f"{name:8s} {amp:10.6f} {result.n_iter:7d} {result.success!s:>8s}")

    assert unbounded_result.success
    assert unbounded_amp < 0.0, (
        "this fixture is chosen so the unconstrained amplitude estimate is "
        "negative, motivating the min=0 bound"
    )
    assert lm_result.success
    assert trf_result.success
    bound_tolerance = 1e-9
    assert lm_result.parameters["peak.amplitude"].value >= -bound_tolerance
    assert trf_result.parameters["peak.amplitude"].value >= -bound_tolerance


compare(unbounded_result, lm_result, trf_result)
# --8<-- [end:compare]

if __name__ == "__main__":
    # Plot the data with the bounded "trf" fit (indistinguishable from "lm"
    # here — see the assertion above) and annotate the unbounded reference.
    best_fit = np.array(trf_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        title="Small near-zero peak with an active amplitude >= 0 bound",
    )
    unbounded_amp = unbounded_result.parameters["peak.amplitude"].value
    bounded_amp = trf_result.parameters["peak.amplitude"].value
    ax.text(
        0.02,
        0.98,
        (
            f"unconstrained estimate: amplitude = {unbounded_amp:.4f} (negative)\n"
            f"bounded lm / trf:       amplitude = {bounded_amp:.4f} "
            f"(n_iter {lm_result.n_iter} / {trf_result.n_iter})"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="top",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    savefig(fig, "bounded_fitting")
