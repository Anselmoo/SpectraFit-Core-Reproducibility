r"""Hold a parameter fixed at a known constant instead of fitting it.

Every :class:`~spectrafit_core.Parameter` has a ``vary`` flag: "whether the
solver may adjust this parameter" (see the field's own docstring in
``parameters.py``). Setting ``vary=False`` excludes the parameter from the
optimizer's free-parameter vector entirely — it keeps whatever ``value`` it
was constructed with for the whole fit. This is the right tool when a
parameter's value is already known from an independent measurement (e.g. a
background level read off a blank/dark scan, or an instrument-broadening
:math:`\sigma` from a calibration standard) rather than something this same
noisy dataset should also be asked to estimate.

This is a different mechanism from :doc:`shared_params`'s ``expr``: ``expr``
ties a parameter's value to *another fitted parameter* via an expression;
``vary=False`` with no ``expr`` pins a parameter to a *known constant*, with
nothing else in the graph to derive it from.
"""

import numpy as np
from _plotting import ANNOTATION_BBOX, plot_fit, savefig
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

#: Stand-in for a background level measured independently of this dataset
#: (e.g. from a blank/dark scan) — known exactly, not something to estimate.
TRUE_BACKGROUND = 0.35


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize a Gaussian peak on top of ``TRUE_BACKGROUND`` (with noise)."""
    rng = np.random.default_rng(11)
    x = np.linspace(-3, 3, 120)
    peak = 2.0 * np.exp(-0.5 * ((x - 0.5) / 0.7) ** 2)
    noise = rng.normal(0, 0.05, len(x))
    y = peak + TRUE_BACKGROUND + noise
    return x, y


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph(*, fix_background: bool) -> FitGraph:
    """One Gaussian peak + one constant background node.

    When ``fix_background`` is True, ``bg.c`` is constructed with
    ``value=TRUE_BACKGROUND, vary=False`` — pinned to the known value and
    excluded from the optimizer's free set for the whole fit. When False, it
    starts from the same value but is left ``vary=True`` (the default) and
    must be estimated from this noisy data like every other free parameter.
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
                    "c": Parameter(value=TRUE_BACKGROUND, vary=not fix_background),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:fit_both]
def fit_both(x: np.ndarray, y: np.ndarray) -> dict[str, FitResult]:
    """Fit the same noisy data with ``bg.c`` fixed, then again with it free."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return {
        "fixed": fit(build_graph(fix_background=True), data),
        "free": fit(build_graph(fix_background=False), data),
    }


results = fit_both(x, y)
fixed_result, free_result = results["fixed"], results["free"]
# --8<-- [end:fit_both]


# --8<-- [start:compare]
def compare(fixed_result: FitResult, free_result: FitResult) -> None:
    """Report dof, per-parameter stderr, and the fixed parameter's absent stderr.

    Two facts are *guaranteed* and asserted below: fixing ``bg.c`` removes it
    from the free-parameter vector, so ``dof = n_points - n_free`` is exactly
    one higher in the fixed model; and ``ParameterResult.stderr`` for ``bg.c``
    is ``None`` in the fixed run, since a fixed parameter was never part of
    the optimization the covariance matrix describes. The peak parameters'
    stderr being *tighter* in the fixed run (printed below, not hard-asserted
    beyond a non-strict bound) is the expected direction for a correctly-known
    fixed value — removing a genuinely-correlated nuisance parameter from the
    free set cannot increase the remaining parameters' Fisher information —
    but the exact margin is specific to this one seeded example, not a
    general accuracy claim.
    """
    print(f"{'':10s} {'dof':>5s} {'amplitude stderr':>18s} {'sigma stderr':>14s}")
    for name, result in (("fixed", fixed_result), ("free", free_result)):
        amp_stderr = result.parameters["peak.amplitude"].stderr
        sigma_stderr = result.parameters["peak.sigma"].stderr
        assert amp_stderr is not None
        assert sigma_stderr is not None
        print(f"{name:10s} {result.dof:5d} {amp_stderr:18.5f} {sigma_stderr:14.5f}")

    bg_fixed_stderr = fixed_result.parameters["bg.c"].stderr
    bg_free_stderr = free_result.parameters["bg.c"].stderr
    print(f"\nbg.c stderr — fixed: {bg_fixed_stderr!r}, free: {bg_free_stderr!r}")

    assert fixed_result.success
    assert free_result.success
    assert fixed_result.dof == free_result.dof + 1, (
        "fixing bg.c removes it from the free set, raising dof by exactly 1"
    )
    assert bg_fixed_stderr is None, (
        "a vary=False parameter is never in the optimization vector, so its stderr is not estimable"
    )
    assert bg_free_stderr is not None
    fixed_amp_stderr = fixed_result.parameters["peak.amplitude"].stderr
    free_amp_stderr = free_result.parameters["peak.amplitude"].stderr
    assert fixed_amp_stderr is not None
    assert free_amp_stderr is not None
    assert fixed_amp_stderr <= free_amp_stderr * 1.05, (
        "a correctly-known fixed background should not noticeably widen the "
        "peak amplitude's uncertainty relative to fitting it"
    )


compare(fixed_result, free_result)
# --8<-- [end:compare]

if __name__ == "__main__":
    # Plot the fixed-background fit, with a text panel comparing both runs'
    # degrees of freedom and stderr side by side.
    best_fit = np.array(fixed_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        title="Peak + background: background fixed at a known value",
    )
    amp_fixed = fixed_result.parameters["peak.amplitude"]
    amp_free = free_result.parameters["peak.amplitude"]
    ax.text(
        0.02,
        0.98,
        (
            f"fixed bg.c: dof={fixed_result.dof}, amplitude stderr={amp_fixed.stderr:.4f}\n"
            f"free  bg.c: dof={free_result.dof}, amplitude stderr={amp_free.stderr:.4f}\n"
            "bg.c stderr is None when fixed (never in the free set)"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="top",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    savefig(fig, "fixed_params")
