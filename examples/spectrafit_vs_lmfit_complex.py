"""Cross-check spectrafit-core against a hand-built lmfit oracle on a messy spectrum.

An XPS-style core-level region with three different lineshape families, a
linear background, and one physically-motivated tied linewidth.

This is deliberately **more complex** than the rest of this gallery: eight
heavily overlapping peaks (not two or four), mixed lineshapes (Gaussian AND
Lorentzian AND pseudo-Voigt in the same graph, not just one shape repeated),
a linear background node, and an ``ExprEdge`` tie motivated by real physics --
``p3``/``p4`` are modeled as the two components of one spin-orbit doublet
(e.g. a carboxyl 2p-like doublet), whose natural (Lorentzian) linewidth must
be identical by the underlying physics, so ``p4.sigma`` is tied to
``p3.sigma`` exactly as in ``shared_params.py``.

The lmfit side is built by hand, mirroring the REAL oracle pattern in
``python/oracles/backends/_lmfit.py`` (not invented lmfit syntax): one
``lmfit.Model(fn, prefix=f"{node_id}_")`` per node, summed with ``+`` into one
composite, ``.make_params(**guess)`` per node, and the same dotted-to-underscore
translation ``_lmfit.py`` uses for ``expr_edges`` (its lines ~91-103) applied
here to translate spectrafit's ``"p3.sigma"`` into lmfit's ``"p3_sigma"``.

Honesty note (read before trusting the numbers): an 8-peak, 27-free-parameter,
heavily-overlapping fit with a tied parameter is NOT the well-conditioned,
provably-unique-optimum problem that ``varpro_vs_lm.py``'s bare two-peak case
is. Overlapping peaks trade amplitude/width against their neighbors along
near-degenerate directions of the cost surface, so two independently-implemented
Levenberg-Marquardt solvers (spectrafit-core's Rust ``"lm"`` and lmfit's SciPy
``leastsq`` wrapper) starting from the same initial guess can land in
*different* corners of a shallow, elongated valley -- close in chi2, not
necessarily close in every individual parameter. This script reports what it
actually measures, with a deliberately loose per-parameter tolerance, rather
than asserting an agreement neither solver's local optimizer can actually
guarantee here.
"""

from __future__ import annotations

import re
import time

import lmfit
import numpy as np
from _plotting import ANNOTATION_BBOX, MUTED_COLOR, plot_fit, savefig
from lmfit.model import ModelResult
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

# --8<-- [start:formulas]
# Peak formulas -- identical to spectrafit-core's own convention
# (docs/reference/models/index.md / python/oracles/models.py): ``amplitude``
# is the peak HEIGHT at ``center``
# (never an integrated area), and ``sigma`` is the Gaussian standard deviation
# / Lorentzian HWHM (never a FWHM). Defined locally rather than imported from
# ``python/oracles/models.py`` -- that module is internal benchmark-harness
# code, not a dependency of this public gallery -- so this script stays
# trivially runnable AND the lmfit oracle stays genuinely independent of
# spectrafit-core's own implementation.


def gaussian(x, amplitude, center, sigma):
    """Gaussian peak: ``amplitude`` at ``center``, std-dev ``sigma``."""
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def lorentzian(x, amplitude, center, sigma):
    """Lorentzian peak normalized to ``amplitude`` at ``center`` (HWHM ``sigma``)."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2)


def pseudo_voigt(x, amplitude, center, sigma, fraction):
    """Pseudo-Voigt: ``fraction``*Lorentzian + (1-``fraction``)*Gaussian, peak ``amplitude``."""
    mix = float(np.clip(fraction, 0.0, 1.0))
    z = (x - center) / sigma
    lorentz = amplitude / (1.0 + z**2)
    gauss = amplitude * np.exp(-0.5 * z**2)
    return mix * lorentz + (1.0 - mix) * gauss


def linear(x, slope, intercept):
    """Linear background ``slope``*x + ``intercept``."""
    return slope * x + intercept


PEAK_FN = {"gaussian": gaussian, "lorentzian": lorentzian, "pseudo_voigt": pseudo_voigt}
MODEL_TYPE = {
    "gaussian": ModelType.GAUSSIAN,
    "lorentzian": ModelType.LORENTZIAN,
    "pseudo_voigt": ModelType.PSEUDO_VOIGT,
}
# --8<-- [end:formulas]

# Scenario: an 8-component core-level spectroscopy region (XPS-style). Three
# lineshape families in one graph (Gaussian-dominated instrumental broadening,
# Lorentzian-dominated lifetime broadening, and a Gaussian/Lorentzian mixture
# via pseudo-Voigt), a linear background, and one tied linewidth: ``p3``/``p4``
# are the two members of one spin-orbit doublet and therefore share an
# identical natural (Lorentzian) linewidth by construction.
LABELS = {
    "p0": "C-C / C-H (aliphatic), Gaussian",
    "p1": "C-O / C-N, pseudo-Voigt",
    "p2": "C=O (carbonyl), pseudo-Voigt",
    "p3": "COOH doublet A (2p3/2-like), Lorentzian",
    "p4": "COOH doublet B (2p1/2-like), Lorentzian, sigma tied to p3",
    "p5": "shake-up satellite 1, Gaussian",
    "p6": "shake-up satellite 2, Gaussian",
    "p7": "trace / plasmon-loss tail, Lorentzian",
    "bg": "linear background",
}

PEAK_ORDER = ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"]

TRUE: dict[str, tuple[str, dict[str, float]]] = {
    "p0": ("gaussian", {"amplitude": 9.0, "center": 284.8, "sigma": 0.55}),
    "p1": (
        "pseudo_voigt",
        {"amplitude": 4.2, "center": 285.9, "sigma": 0.60, "fraction": 0.35},
    ),
    "p2": (
        "pseudo_voigt",
        {"amplitude": 2.6, "center": 287.3, "sigma": 0.55, "fraction": 0.45},
    ),
    "p3": ("lorentzian", {"amplitude": 1.6, "center": 288.8, "sigma": 0.42}),
    "p4": (
        "lorentzian",
        {"amplitude": 0.8, "center": 289.5, "sigma": 0.42},
    ),  # tied to p3
    "p5": ("gaussian", {"amplitude": 1.3, "center": 290.6, "sigma": 0.50}),
    "p6": ("gaussian", {"amplitude": 0.9, "center": 292.0, "sigma": 0.65}),
    "p7": ("lorentzian", {"amplitude": 0.5, "center": 293.6, "sigma": 0.50}),
}
BG_TRUE = {"slope": -0.01, "intercept": 0.30}

# Initial guesses fed to BOTH backends -- deliberately offset from the truth
# (not a "cheat" start at the answer), and the SAME starting point for both
# backends, so the n_iter/timing comparison below is actually meaningful.
GUESS: dict[str, dict[str, float]] = {
    "p0": {"amplitude": 7.5, "center": 284.6, "sigma": 0.70},
    "p1": {"amplitude": 3.0, "center": 286.2, "sigma": 0.70, "fraction": 0.50},
    "p2": {"amplitude": 2.0, "center": 287.6, "sigma": 0.70, "fraction": 0.50},
    "p3": {"amplitude": 1.2, "center": 288.6, "sigma": 0.55},
    "p4": {"amplitude": 0.6, "center": 289.7, "sigma": 0.55},
    "p5": {"amplitude": 1.0, "center": 290.9, "sigma": 0.60},
    "p6": {"amplitude": 0.7, "center": 292.3, "sigma": 0.80},
    "p7": {"amplitude": 0.35, "center": 293.9, "sigma": 0.60},
}
BG_GUESS = {"slope": 0.0, "intercept": 0.20}


# --8<-- [start:data]
def synthesize_data() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize the 8-peak + linear-background spectrum (with noise).

    Sums every ``TRUE`` component plus the linear background, then adds
    Gaussian measurement noise (``sigma=0.06``, seeded for reproducibility).
    """
    rng = np.random.default_rng(11)
    x = np.linspace(280.0, 296.0, 480)
    y_true = np.zeros_like(x)
    for pid in PEAK_ORDER:
        kind, true_params = TRUE[pid]
        y_true = y_true + PEAK_FN[kind](x, **true_params)
    y_true = y_true + linear(x, **BG_TRUE)
    noise = rng.normal(0, 0.06, len(x))
    return x, y_true + noise


x, y = synthesize_data()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph() -> FitGraph:
    """Fresh FitGraph: 8 peaks (3 lineshape families) + linear bg + 1 ExprEdge tie."""
    nodes = []
    for pid in PEAK_ORDER:
        kind, _ = TRUE[pid]
        guess = GUESS[pid]
        parameters = {
            "amplitude": Parameter(value=guess["amplitude"], min=0.0),
            "center": Parameter(value=guess["center"]),
            "sigma": Parameter(value=guess["sigma"], min=1e-3),
        }
        if kind == "pseudo_voigt":
            parameters["fraction"] = Parameter(
                value=guess["fraction"],
                min=0.0,
                max=1.0,
            )
        nodes.append(
            ModelNodeSpec(id=pid, model_type=MODEL_TYPE[kind], parameters=parameters),
        )
    nodes.append(
        ModelNodeSpec(
            id="bg",
            model_type=ModelType.LINEAR,
            parameters={
                "slope": Parameter(value=BG_GUESS["slope"]),
                "intercept": Parameter(value=BG_GUESS["intercept"]),
            },
        ),
    )
    return FitGraph(
        nodes=nodes,
        expr_edges=[
            # p4 (the 2p1/2-like doublet partner) shares p3's natural linewidth --
            # the same tie pattern as shared_params.py, applied for a physical
            # (not merely illustrative) reason.
            ExprEdge(target_node="p4", target_param="sigma", expression="p3.sigma"),
        ],
    )


# --8<-- [end:build_graph]


# --8<-- [start:build_lmfit]
def build_lmfit_composite() -> tuple[lmfit.Model, lmfit.Parameters]:
    """Hand-built lmfit composite mirroring python/oracles/backends/_lmfit.py.

    Same loop structure as ``LmfitBackend.build``: one ``lmfit.Model`` per
    node (prefixed with the node id, which already matches ``_lmfit.py``'s
    ``f"p{i}_"`` convention here since the graph's own node ids are
    ``p0``..``p7``), summed with ``+``, ``.make_params(**guess)`` per node,
    then the tie applied via the same dotted-to-underscore regex translation
    ``_lmfit.py`` uses for ``expr_edges`` (its lines ~91-103).
    """
    composite: lmfit.Model | None = None
    params: lmfit.Parameters | None = None
    for pid in PEAK_ORDER:
        kind, _ = TRUE[pid]
        m = lmfit.Model(PEAK_FN[kind], prefix=f"{pid}_")
        composite = m if composite is None else composite + m
        pars = m.make_params(**GUESS[pid])
        pars[f"{pid}_amplitude"].set(min=0.0)
        pars[f"{pid}_sigma"].set(min=1e-3)
        if kind == "pseudo_voigt":
            pars[f"{pid}_fraction"].set(min=0.0, max=1.0)
        params = pars if params is None else params.update(pars) or params

    # PEAK_ORDER is non-empty, so the loop above always ran at least once --
    # both are genuinely never None here. `X.update(Y) or X` is runtime-safe
    # (dict.update always returns None, so `or` always falls through to the
    # just-mutated X) but a type checker can't verify that from the pattern
    # alone; asserting is the actual narrowing point, not a defensive check
    # against a real possibility.
    assert composite is not None
    assert params is not None

    bg_model = lmfit.Model(linear, prefix="bg_")
    composite = composite + bg_model
    bg_pars = bg_model.make_params(**BG_GUESS)
    params.update(bg_pars)

    # Apply the ExprEdge as an lmfit parameter expression, translating
    # spectrafit's dotted "node.param" syntax into lmfit's "node_param"
    # syntax -- the exact regex `_lmfit.py` applies to every expr_edge.
    expr_edge = {"target_node": "p4", "target_param": "sigma", "expression": "p3.sigma"}
    lmfit_target = f"{expr_edge['target_node']}_{expr_edge['target_param']}"
    lmfit_expr = re.sub(r"\b(p\d+)\.(\w+)\b", r"\1_\2", expr_edge["expression"])
    params[lmfit_target].set(expr=lmfit_expr)

    return composite, params


# --8<-- [end:build_lmfit]


# --8<-- [start:report]
def run_and_report(
    x: np.ndarray,
    y: np.ndarray,
    n_reps: int = 5,
) -> tuple[FitResult, ModelResult, float, float, float, float]:
    """Fit both backends ``n_reps`` times, print the side-by-side report.

    Returns ``(sf_result, lm_result, sf_median_time, lm_median_time, lm_r2,
    max_delta)`` -- everything the tie-verification step and the
    ``__main__`` plotting block need, so neither has to re-run either
    backend or recompute the per-parameter comparison.
    """
    data = MeasurementData(x=x.tolist(), y=y.tolist())

    sf_times: list[float] = []
    sf_result = fit(build_graph(), data)  # warm-up, untimed
    for _ in range(n_reps):
        start = time.perf_counter()
        sf_result = fit(build_graph(), data)
        sf_times.append(time.perf_counter() - start)
    sf_median_time = sorted(sf_times)[len(sf_times) // 2]

    lm_times: list[float] = []
    composite, params = build_lmfit_composite()
    lm_result = composite.fit(y, params, x=x)  # warm-up, untimed
    for _ in range(n_reps):
        _, fresh_params = build_lmfit_composite()
        start = time.perf_counter()
        lm_result = composite.fit(y, fresh_params, x=x)
        lm_times.append(time.perf_counter() - start)
    lm_median_time = sorted(lm_times)[len(lm_times) // 2]

    lm_best_fit = np.asarray(lm_result.best_fit, dtype=float)
    lm_chi2 = float(np.sum((y - lm_best_fit) ** 2))
    lm_n_iter = int(getattr(lm_result, "nfev", 0) or 0)

    print(f"{'':30s} {'spectrafit':>25s} {'lmfit':>25s}")
    print(f"{'success':30s} {sf_result.success!s:>25s} {lm_result.success!s:>25s}")
    print(f"{'chi2':30s} {sf_result.chi2:25.6f} {lm_chi2:25.6f}")
    print(
        f"{'n_iter (spectrafit) / nfev (lmfit)':30s} {sf_result.n_iter:25d} {lm_n_iter:25d}",
    )
    print(
        f"{'median wall time (ms)':30s} {sf_median_time * 1e3:25.3f} {lm_median_time * 1e3:25.3f}",
    )
    print()

    print(f"{'parameter':34s} {'spectrafit':>12s} {'lmfit':>12s} {'|delta|':>12s}")
    max_delta = 0.0
    for pid in PEAK_ORDER:
        kind, _ = TRUE[pid]
        names = list(
            PEAK_FN[kind].__code__.co_varnames[1 : PEAK_FN[kind].__code__.co_argcount],
        )
        for pname in names:
            sf_val = sf_result.parameters[f"{pid}.{pname}"].value
            lm_val = float(lm_result.params[f"{pid}_{pname}"].value)
            delta = abs(sf_val - lm_val)
            max_delta = max(max_delta, delta)
            label = f"{pid}.{pname} ({LABELS[pid]})"
            print(f"{label:34s} {sf_val:12.4f} {lm_val:12.4f} {delta:12.2e}")
    for bname in ("slope", "intercept"):
        sf_val = sf_result.parameters[f"bg.{bname}"].value
        lm_val = float(lm_result.params[f"bg_{bname}"].value)
        delta = abs(sf_val - lm_val)
        max_delta = max(max_delta, delta)
        print(f"{'bg.' + bname:34s} {sf_val:12.4f} {lm_val:12.4f} {delta:12.2e}")
    print()
    print(
        f"Largest single-parameter disagreement (spectrafit vs. lmfit): {max_delta:.4f}",
    )

    lm_ss_res = float(np.sum((y - lm_best_fit) ** 2))
    lm_ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    lm_r2 = 1.0 - lm_ss_res / lm_ss_tot

    return sf_result, lm_result, sf_median_time, lm_median_time, lm_r2, max_delta


sf_result, lm_result, sf_median_time, lm_median_time, lm_r2, max_delta = run_and_report(
    x,
    y,
)
# --8<-- [end:report]


# --8<-- [start:tie_verification]
def verify_tie_and_assertions(
    sf_result: FitResult,
    lm_result: ModelResult,
    lm_r2: float,
) -> float:
    """Assert both fits succeeded and the ``p4.sigma = p3.sigma`` tie holds exactly.

    A loose ``R2`` tolerance (``< 0.02``), deliberately -- see the module
    docstring's honesty note: 8 overlapping peaks with one tied linewidth is
    a harder, potentially locally-non-unique landscape than this gallery's
    smaller examples, so we check "compatible", not "identical" per parameter.

    Returns ``p3.sigma`` (== ``p4.sigma`` by the tie) for the plotting step.
    """
    sf_p3_sigma = sf_result.parameters["p3.sigma"].value
    sf_p4_sigma = sf_result.parameters["p4.sigma"].value
    print("Tie verification (spectrafit ExprEdge, p4.sigma = p3.sigma):")
    print(f"  p3.sigma = {sf_p3_sigma:.8f}")
    print(f"  p4.sigma = {sf_p4_sigma:.8f}")
    print(f"  Difference = {abs(sf_p3_sigma - sf_p4_sigma):.2e}")
    print()

    assert sf_result.success
    assert lm_result.success
    sf_r2 = sf_result.r_squared
    assert abs(sf_r2 - lm_r2) < 0.02, (
        f"Aggregate fit quality (R2) should be close even if individual overlapping "
        f"peak parameters are not: spectrafit R2={sf_r2:.6f}, lmfit R2={lm_r2:.6f}"
    )
    assert abs(sf_p3_sigma - sf_p4_sigma) < 1e-6

    return sf_p3_sigma


sf_p3_sigma = verify_tie_and_assertions(sf_result, lm_result, lm_r2)
# --8<-- [end:tie_verification]

if __name__ == "__main__":
    # Plot data + spectrafit's fitted curve with per-node components overlaid,
    # then annotate the tied doublet pair the same way shared_params.py does.
    best_fit = np.array(sf_result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        components=sf_result.components,
        title="8-peak overlapping spectrum: spectrafit vs. lmfit (one tied width)",
    )
    ax.text(
        0.02,
        0.98,
        (
            f"spectrafit: R2={sf_result.r_squared:.4f}, {sf_result.n_iter} iter, "
            f"{sf_median_time * 1e3:.2f} ms\n"
            f"lmfit:      R2={lm_r2:.4f}, {int(getattr(lm_result, 'nfev', 0) or 0)} nfev, "
            f"{lm_median_time * 1e3:.2f} ms\n"
            f"max |delta| across all 27 fitted params: {max_delta:.3f}"
        ),
        transform=ax.transAxes,
        fontsize=7.5,
        va="top",
        ha="left",
        family="monospace",
        bbox=ANNOTATION_BBOX,
    )

    p3_center = sf_result.parameters["p3.center"].value
    p4_center = sf_result.parameters["p4.center"].value
    p3_amp = sf_result.parameters["p3.amplitude"].value
    p4_amp = sf_result.parameters["p4.amplitude"].value
    for center, amplitude in ((p3_center, p3_amp), (p4_center, p4_amp)):
        span_height = 0.12 * amplitude
        ax.annotate(
            "",
            xy=(center + sf_p3_sigma, span_height),
            xytext=(center - sf_p3_sigma, span_height),
            arrowprops={"arrowstyle": "<->", "color": MUTED_COLOR, "lw": 1.2},
        )
    ax.annotate(
        "doublet: tied width",
        xy=((p3_center + p4_center) / 2, 0.12 * max(p3_amp, p4_amp)),
        xytext=(0, 18),
        textcoords="offset points",
        ha="center",
        fontsize=8,
        color=MUTED_COLOR,
    )

    fig.tight_layout()
    savefig(fig, "spectrafit_vs_lmfit_complex")
