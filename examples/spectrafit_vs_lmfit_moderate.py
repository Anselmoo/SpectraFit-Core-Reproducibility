"""A moderately complex 4-peak spectrum, cross-checked against real lmfit.

Every other script in this gallery only ever compares spectrafit against
*itself* — a different solver (``varpro_vs_lm.py``), a different parameter
surface (``shared_params.py``), a different dimensionality
(``3d_fitting.py``). **This is the first tutorial in this gallery to
include lmfit as an external cross-check, not just spectrafit's own
alternate solvers.** lmfit is a separate, independently-implemented
least-squares package (its own Levenberg-Marquardt driver, its own parameter
bookkeeping) — agreement with it is a genuinely independent oracle in a way
agreement between two spectrafit solvers is not.

The scenario is also more realistic than the gallery's single/double-peak
examples: four overlapping peaks of *mixed* shape (two Gaussian, two
Lorentzian) sitting on a sloped (linear) background — the kind of composite
lineshape a real spectrum (XPS, Raman, UV-Vis, ...) usually looks like,
rather than one or two isolated peaks in flat noise.

The lmfit composite model is built by hand, following the exact pattern
used by the project's own lmfit oracle backend
(``python/oracles/backends/_lmfit.py``): one ``lmfit.Model(fn, prefix=...)``
per component, summed with ``+``, ``.make_params(...)`` per component
merged together, then ``composite.fit(y, params, x=x)``. The per-peak numpy
formulas below use the same convention as ``python/oracles/models.py``:
``amplitude`` is the peak height at ``center`` (not the integrated area),
Gaussian ``sigma`` is the standard deviation, and Lorentzian ``sigma`` is
the half-width at half maximum (HWHM) — so a bare hand-rolled lmfit model
matches spectrafit's own convention exactly instead of e.g. lmfit's builtin
``GaussianModel``/``LorentzianModel``, which normalize by area.

See ``spectrafit_vs_lmfit_moderate.md`` for the narrative walkthrough.
"""

from __future__ import annotations

import time

import lmfit
import numpy as np
from _plotting import ANNOTATION_BBOX, plot_fit, savefig
from lmfit.model import ModelResult
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


# --8<-- [start:formulas]
# Per-peak numpy formulas -- same convention as python/oracles/models.py:
# ``amplitude`` is the peak height (not area), Gaussian ``sigma`` is the
# standard deviation, Lorentzian ``sigma`` is the HWHM. These are handed
# straight to ``lmfit.Model`` below, exactly the way
# ``python/oracles/backends/_lmfit.py`` wraps ``PeakModel.evaluate``.
def gaussian(
    x: np.ndarray,
    amplitude: float,
    center: float,
    sigma: float,
) -> np.ndarray:
    """Gaussian peak: ``amplitude`` at ``center``, std-dev ``sigma``."""
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def lorentzian(
    x: np.ndarray,
    amplitude: float,
    center: float,
    sigma: float,
) -> np.ndarray:
    """Lorentzian peak normalized to ``amplitude`` at ``center`` (HWHM ``sigma``)."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2)


def linear_bg(x: np.ndarray, slope: float, intercept: float) -> np.ndarray:
    """Linear background ``slope*x + intercept``."""
    return slope * x + intercept


# --8<-- [end:formulas]

TRUE = {
    "peak1": {"shape": "gaussian", "amplitude": 3.0, "center": -1.0, "sigma": 0.6},
    "peak2": {"shape": "lorentzian", "amplitude": 2.2, "center": 0.6, "sigma": 0.5},
    "peak3": {"shape": "gaussian", "amplitude": 2.6, "center": 5.0, "sigma": 0.9},
    "peak4": {"shape": "lorentzian", "amplitude": 1.6, "center": 6.4, "sigma": 0.55},
}
BG_TRUE = {"slope": 0.04, "intercept": 0.5}

# Deliberately off-true starting guesses (a realistic "eyeballed from the
# plot" starting point, not the answer key) — shared by both backends so
# the comparison is apples-to-apples.
GUESS = {
    "peak1": {"amplitude": 2.4, "center": -0.6, "sigma": 0.45},
    "peak2": {"amplitude": 1.7, "center": 1.0, "sigma": 0.35},
    "peak3": {"amplitude": 2.0, "center": 5.4, "sigma": 0.7},
    "peak4": {"amplitude": 1.1, "center": 6.8, "sigma": 0.4},
}
BG_GUESS = {"slope": 0.0, "intercept": 0.3}


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize the 4-peak + linear-background spectrum (with noise).

    Sums every ``TRUE`` component (2 Gaussian + 2 Lorentzian) plus the
    linear background, then adds Gaussian measurement noise (``sigma=0.06``,
    seeded for reproducibility).
    """
    rng = np.random.default_rng(11)
    x = np.linspace(-4, 10, 320)
    y = (
        gaussian(
            x,
            TRUE["peak1"]["amplitude"],
            TRUE["peak1"]["center"],
            TRUE["peak1"]["sigma"],
        )
        + lorentzian(
            x,
            TRUE["peak2"]["amplitude"],
            TRUE["peak2"]["center"],
            TRUE["peak2"]["sigma"],
        )
        + gaussian(
            x,
            TRUE["peak3"]["amplitude"],
            TRUE["peak3"]["center"],
            TRUE["peak3"]["sigma"],
        )
        + lorentzian(
            x,
            TRUE["peak4"]["amplitude"],
            TRUE["peak4"]["center"],
            TRUE["peak4"]["sigma"],
        )
        + linear_bg(x, BG_TRUE["slope"], BG_TRUE["intercept"])
    )
    noise = rng.normal(0, 0.06, len(x))
    return x, y + noise


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """A 5-node FitGraph: 2 Gaussian + 2 Lorentzian peaks + a linear background."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=GUESS["peak1"]["amplitude"], min=0.0),
                    "center": Parameter(value=GUESS["peak1"]["center"]),
                    "sigma": Parameter(value=GUESS["peak1"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="peak2",
                model_type=ModelType.LORENTZIAN,
                parameters={
                    "amplitude": Parameter(value=GUESS["peak2"]["amplitude"], min=0.0),
                    "center": Parameter(value=GUESS["peak2"]["center"]),
                    "sigma": Parameter(value=GUESS["peak2"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="peak3",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=GUESS["peak3"]["amplitude"], min=0.0),
                    "center": Parameter(value=GUESS["peak3"]["center"]),
                    "sigma": Parameter(value=GUESS["peak3"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="peak4",
                model_type=ModelType.LORENTZIAN,
                parameters={
                    "amplitude": Parameter(value=GUESS["peak4"]["amplitude"], min=0.0),
                    "center": Parameter(value=GUESS["peak4"]["center"]),
                    "sigma": Parameter(value=GUESS["peak4"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.LINEAR,
                parameters={
                    "slope": Parameter(value=BG_GUESS["slope"]),
                    "intercept": Parameter(value=BG_GUESS["intercept"]),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]

# (lmfit prefix, model fn, node id, init guess dict) — node id is only used
# to map lmfit's flat "prefix_param" names back to spectrafit's "node.param"
# dotted names for the side-by-side table below.
COMPONENTS = (
    ("p0_", gaussian, "peak1", GUESS["peak1"]),
    ("p1_", lorentzian, "peak2", GUESS["peak2"]),
    ("p2_", gaussian, "peak3", GUESS["peak3"]),
    ("p3_", lorentzian, "peak4", GUESS["peak4"]),
    ("bg_", linear_bg, "bg", BG_GUESS),
)


# --8<-- [start:build_lmfit]
def build_lmfit_model() -> tuple[lmfit.Model, lmfit.Parameters]:
    """Build the composite lmfit model + params, mirroring LmfitBackend.build()."""
    composite = None
    params = None
    for prefix, fn, _node_id, guess in COMPONENTS:
        m = lmfit.Model(fn, prefix=prefix)
        composite = m if composite is None else composite + m
        pars = m.make_params(**guess)
        if "sigma" in guess:
            pars[f"{prefix}sigma"].set(min=1e-6)
        if "amplitude" in guess:
            pars[f"{prefix}amplitude"].set(min=0.0)
        params = pars if params is None else params.update(pars) or params
    return composite, params


# --8<-- [end:build_lmfit]


# --8<-- [start:report]
def run_and_report(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[FitResult, ModelResult, float, float, float, float]:
    """Fit both backends once each (plus an untimed warm-up), print the report.

    Returns ``(sf_result, lmfit_result, sf_time, lmfit_time, lmfit_chi2,
    max_abs_diff)`` -- everything the assertions step and the ``__main__``
    plotting block need, so neither has to re-run either backend or
    recompute the per-parameter comparison.
    """
    data = MeasurementData(x=x.tolist(), y=y.tolist())

    # Backend 1: spectrafit-core's own fit().
    fit(build_graph(), data)  # warm-up, untimed
    start = time.perf_counter()
    sf_result = fit(build_graph(), data)
    sf_time = time.perf_counter() - start

    # Backend 2: a real lmfit composite model, built by hand exactly the way
    # python/oracles/backends/_lmfit.py's LmfitBackend.build() does: one
    # lmfit.Model(fn, prefix=...) per component, summed with "+", each
    # component's make_params(...) merged into one Parameters object, then
    # composite.fit(y, params, x=x).
    composite, lmfit_params = build_lmfit_model()
    composite.fit(y, lmfit_params, x=x)  # warm-up, untimed
    _, lmfit_params_fresh = build_lmfit_model()
    start = time.perf_counter()
    lmfit_result = composite.fit(y, lmfit_params_fresh, x=x)
    lmfit_time = time.perf_counter() - start

    lmfit_best_fit = np.asarray(lmfit_result.best_fit, dtype=float)
    lmfit_chi2 = float(np.sum((y - lmfit_best_fit) ** 2))

    print(f"{'backend':10s} {'success':8s} {'chi2':>12s} {'wall time':>14s}")
    print(
        f"{'spectrafit':10s} {sf_result.success!s:8s} "
        f"{sf_result.chi2:12.6f} {sf_time * 1e3:11.3f} ms",
    )
    print(
        f"{'lmfit':10s} {lmfit_result.success!s:8s} {lmfit_chi2:12.6f} {lmfit_time * 1e3:11.3f} ms",
    )
    print()

    print(f"{'parameter':16s} {'spectrafit':>12s} {'lmfit':>12s} {'|Delta|':>10s}")
    max_abs_diff = 0.0
    for prefix, _fn, node_id, guess in COMPONENTS:
        for param_name in guess:
            sf_value = sf_result.parameters[f"{node_id}.{param_name}"].value
            lmfit_value = lmfit_result.params[f"{prefix}{param_name}"].value
            diff = abs(sf_value - lmfit_value)
            max_abs_diff = max(max_abs_diff, diff)
            print(
                f"{node_id + '.' + param_name:16s} {sf_value:12.6f} "
                f"{lmfit_value:12.6f} {diff:10.2e}",
            )

    print()
    print(f"Largest |Delta| across all 14 fitted parameters: {max_abs_diff:.2e}")

    return sf_result, lmfit_result, sf_time, lmfit_time, lmfit_chi2, max_abs_diff


sf_result, lmfit_result, sf_time, lmfit_time, lmfit_chi2, max_abs_diff = run_and_report(
    x,
    y,
)
# --8<-- [end:report]


# --8<-- [start:assertions]
def verify_agreement(
    sf_result: FitResult,
    lmfit_result: ModelResult,
    lmfit_chi2: float,
    max_abs_diff: float,
) -> None:
    """Assert both fits succeeded and agree to within a tight tolerance.

    Both backends should converge to matching parameter values (within
    ``1e-4``) and matching ``chi2`` (within ``1e-4``) on this well-posed
    4-peak + linear-background problem -- in practice both land within
    ``~1e-5`` of each other.
    """
    assert sf_result.success
    assert lmfit_result.success
    assert max_abs_diff < 1e-4, (
        "spectrafit and lmfit should converge to matching parameter values "
        "(within 1e-4) on this well-posed 4-peak + linear-background problem "
        "-- in practice both land within ~1e-5 of each other"
    )
    assert abs(sf_result.chi2 - lmfit_chi2) < 1e-4, (
        "spectrafit and lmfit should converge to matching chi2 on this problem"
    )


verify_agreement(sf_result, lmfit_result, lmfit_chi2, max_abs_diff)
# --8<-- [end:assertions]

if __name__ == "__main__":
    # Plot data + the spectrafit fit with all 5 components overlaid (4
    # peaks + the linear background), then annotate the lmfit cross-check
    # numbers directly on the plot so the agreement is visible, not just
    # asserted.
    best_fit = np.array(sf_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        components=sf_result.components,
        title="4-peak fit (2 Gaussian + 2 Lorentzian + linear bg): spectrafit vs. lmfit",
    )
    ax.text(
        0.02,
        0.02,
        (
            f"spectrafit: chi2={sf_result.chi2:.4f}, {sf_time * 1e3:.2f} ms\n"
            f"lmfit:      chi2={lmfit_chi2:.4f}, {lmfit_time * 1e3:.2f} ms\n"
            f"max |Delta param| = {max_abs_diff:.2e} (see assertions above)"
        ),
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )
    fig.tight_layout()
    savefig(fig, "spectrafit_vs_lmfit_moderate")
