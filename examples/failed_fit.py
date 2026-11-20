"""A fit that fails, and a worse one that says it succeeded.

Every other page in this gallery ends ``success=True``. That is not what
fitting is like, and a reader who only ever sees converged examples learns
nothing about how this library reports trouble. Three fits of the *same*
data are run here from different starting guesses:

* one that returns ``success=False`` and names the reason,
* one that returns ``success=True`` with a negative :math:`r^2` -- worse
  than a horizontal line through the mean -- because the degeneracy guard
  is deliberately narrow,
* one that recovers the planted truth from the same bad guess by asking
  for ``solver="global"`` instead of local ``"lm"``.

The guard lives in ``crates/spectrafit-solver/src/postfit.rs``: when a fit
converges with :math:`r^2 < 0`, it is demoted to a failure only if some free
``.amplitude``/``.height`` parameter has fallen below **1% of max |y|**.
That threshold is the whole difference between the first two cases, and it
is why ``success`` is necessary but not sufficient -- read ``r_squared``
and the recovered parameters too.
"""

import numpy as np
from _plotting import MUTED_COLOR, savefig
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
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """One clean, well-sampled Gaussian peak with light noise.

    Deliberately easy data: nothing below fails because the measurement is
    hard. Every failure on this page is caused by where the fit was told to
    start, not by the data.
    """
    rng = np.random.default_rng(7)
    x = np.linspace(-4, 4, 120)
    y_true = AMPLITUDE_TRUE * np.exp(-0.5 * ((x - CENTER_TRUE) / SIGMA_TRUE) ** 2)
    return x, y_true + rng.normal(0, 0.05, len(x))


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph(amplitude: float, center: float, sigma: float) -> FitGraph:
    """One Gaussian, with the *initial guess* supplied by the caller."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=amplitude),
                    "center": Parameter(value=center),
                    "sigma": Parameter(value=sigma, min=1e-3),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:three_fits]
def three_fits(x: np.ndarray, y: np.ndarray) -> dict[str, FitResult]:
    """Same data, same model, three outcomes.

    ``reported`` and ``silent`` differ only in their starting guess; the
    solver is local ``"lm"`` in both. ``recovered`` reuses ``silent``'s bad
    guess and changes only the solver.
    """
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return {
        "reported": fit(build_graph(50.0, -3.9, 0.05), data, FitOptions(solver="lm")),
        "silent": fit(build_graph(3.0, -3.9, 0.8), data, FitOptions(solver="lm")),
        "recovered": fit(build_graph(3.0, -3.9, 0.8), data, FitOptions(solver="global")),
    }


results = three_fits(x, y)
# --8<-- [end:three_fits]


# --8<-- [start:inspect]
def inspect(results: dict[str, FitResult], y: np.ndarray) -> None:
    """Print what each fit reported, and check the three outcomes hold.

    The ``|A|/max|y|`` column is the quantity the degeneracy guard actually
    tests. Watch it straddle the 1% threshold between the first two rows
    while ``r^2`` stays essentially identical -- that is the guard's
    boundary, made visible.
    """
    y_max_abs = float(np.abs(y).max())
    header = (
        f"{'case':11s} {'success':>8s} {'r^2':>9s} {'amplitude':>10s} {'|A|/max|y|':>11s}  message"
    )
    print(header)
    for name, result in results.items():
        amp = result.parameters["peak.amplitude"].value
        print(
            f"{name:11s} {result.success!s:>8s} {result.r_squared:9.4f} "
            f"{amp:10.4f} {abs(amp) / y_max_abs:11.4f}  {result.message}",
        )

    reported, silent, recovered = results["reported"], results["silent"], results["recovered"]

    # The guard fires: amplitude collapsed under 1% of max|y| with r^2 < 0.
    assert not reported.success
    assert "degenerate_fit" in reported.message
    assert reported.r_squared < 0

    # The guard stays silent on a fit that is just as wrong, because its
    # amplitude landed above the 1% threshold. This is the case the page exists
    # for: `success` alone would have told a caller everything was fine.
    assert silent.success
    assert silent.r_squared < 0
    assert abs(silent.parameters["peak.amplitude"].value) / y_max_abs > 1e-2

    # Same bad guess, global solver, truth recovered.
    assert recovered.success
    assert recovered.r_squared > 0.99
    assert abs(recovered.parameters["peak.amplitude"].value - AMPLITUDE_TRUE) < 0.05
    assert abs(recovered.parameters["peak.center"].value - CENTER_TRUE) < 0.05


inspect(results, y)
# --8<-- [end:inspect]

if __name__ == "__main__":
    # Two panels, because one will not do the job. On the left the three curves
    # over the data: the recovery traces the peak, and both failures lie flat
    # along zero, on top of each other. That overlap is the finding, not a
    # drawing problem -- so the right panel rescales to the failures' own y-range
    # to show they are in fact different curves, one of which said so and one of
    # which did not.
    import matplotlib.pyplot as plt

    fig, (ax_main, ax_zoom) = plt.subplots(
        1,
        2,
        figsize=(11.0, 4.6),
        gridspec_kw={"width_ratios": [1.55, 1.0]},
    )

    styles = (
        ("reported", MUTED_COLOR, "--", 1.9, "lm — success=False (guard fired)"),
        ("silent", "#C44E52", ":", 2.4, "lm — success=True, r²<0 (guard silent)"),
    )

    ax_main.scatter(x, y, s=18, alpha=0.55, color="#4C72B0", label="data", zorder=2)
    ax_main.plot(
        x,
        results["recovered"].best_fit,
        color="#55A868",
        linewidth=2.0,
        label="global — recovers truth (r²=0.998)",
        zorder=3,
    )
    for key, colour, dashes, width, label in styles:
        ax_main.plot(
            x,
            results[key].best_fit,
            color=colour,
            linestyle=dashes,
            linewidth=width,
            label=label,
            zorder=4,
        )
    ax_main.set_xlabel("x")
    ax_main.set_ylabel("y")
    ax_main.set_title("Same data, same model, three outcomes")
    ax_main.legend(loc="upper left", fontsize=8.5)

    for key, colour, dashes, width, label in styles:
        ax_zoom.plot(
            x,
            results[key].best_fit,
            color=colour,
            linestyle=dashes,
            linewidth=width,
            label=label,
        )
    ax_zoom.axhline(0.0, color=MUTED_COLOR, linewidth=0.9, zorder=1)
    ax_zoom.set_xlim(-4.0, -1.6)
    ax_zoom.set_ylim(-0.095, 0.02)
    ax_zoom.set_xlabel("x")
    ax_zoom.set_ylabel("y (rescaled)")
    magnification = (ax_main.get_ylim()[1] - ax_main.get_ylim()[0]) / (
        ax_zoom.get_ylim()[1] - ax_zoom.get_ylim()[0]
    )
    ax_zoom.set_title(f"The two failures, y magnified {magnification:.0f}x")
    ax_zoom.legend(loc="lower right", fontsize=8.5)

    fig.tight_layout()
    savefig(fig, "failed_fit")
