"""3-D Gaussian fitting via the native ``gaussian_nd`` kernel.

This example demonstrates spectrafit_core's native N-dimensional fitting
path: a single ``gaussian_nd`` model node fit jointly across a genuinely
3-D coordinate space. As of SP-2, the dimensionality ``D`` is **inferred**
from the node's indexed ``center_0``/``center_1``/``center_2`` parameters
-- there is no separate dimension field or ``MeasurementData3D`` class. A
D-dimensional data point is simply a coordinate row of length ``D``, and
the compiler counts the ``center_<i>`` parameters supplied to work out
``D`` (here, three of them, so ``D=3``).

A synthetic 3-D Gaussian is sampled on an 8x8x8 coordinate grid (512
points total) with light Gaussian noise, then recovered with a single
joint least-squares solve over all three axes at once -- one simultaneous
fit, not three independent 1-D fits stitched together.

Because a genuinely 3-D scatter cloud is not directly renderable with
matplotlib, the fit is visualized through three 2-D projections: fixed-axis
slices through the *fitted* peak center, one each for the XY, XZ, and YZ
planes. Each panel overlays the observed data (as a heatmap) against the
recovered fit (as contour lines), so the model's agreement with the data
can be inspected plane-by-plane even though the underlying fit was never
decomposed into separate 2-D problems.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from _plotting import savefig
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# Colors chosen to match `_plotting.py`'s palette (`_DATA_COLOR` / `_FIT_COLOR`)
# so this script's custom projection panels read as part of the same gallery
# visual language, even though they use `imshow`/`contour` rather than
# `plot_fit`'s scatter+line view (see the module docstring in `_plotting.py`:
# `plot_fit` only ever draws a 2-D (x, y) *curve*, so a true axis-pair heatmap
# projection has to be drawn directly).
_DATA_CMAP = "viridis"
_FIT_COLOR = "#C44E52"


# --8<-- [start:data]
def _synthesize_3d_gaussian() -> tuple[
    np.ndarray,
    np.ndarray,
    tuple[float, ...],
    tuple[float, ...],
]:
    """Sample a noisy 3-D Gaussian on an 8x8x8 grid.

    Returns:
        ``(coords, y, center, sigma)`` where ``coords`` has shape ``(512, 3)``,
        ``y`` has shape ``(512,)``, and ``center``/``sigma`` are the true
        (planted) parameter values used to generate the data.
    """
    n = 8
    g = np.linspace(-5.0, 5.0, n)
    xx, yy, zz = np.meshgrid(g, g, g, indexing="ij")
    coords = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])  # (512, 3)

    amp, center, sigma = 6.0, (-1.5, 1.0, 0.5), (1.6, 2.1, 1.2)
    rng = np.random.default_rng(7)
    y = amp * np.exp(
        -((xx - center[0]) ** 2) / (2 * sigma[0] ** 2)
        - ((yy - center[1]) ** 2) / (2 * sigma[1] ** 2)
        - ((zz - center[2]) ** 2) / (2 * sigma[2] ** 2),
    ) + rng.normal(0.0, 0.05, xx.shape)

    return coords, y.ravel(), center, sigma


coords, y, true_center, true_sigma = _synthesize_3d_gaussian()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def _build_graph() -> FitGraph:
    """Build a single ``gaussian_nd`` node. D=3 is inferred from center_0..2.

    No dimension field is passed anywhere -- the compiler counts the
    ``center_<i>`` parameters supplied below and validates the full
    ``1 + 2*D`` parameter set is present.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN_ND,
                parameters={
                    "amplitude": Parameter(value=4.0),
                    "center_0": Parameter(value=-1.0),
                    "center_1": Parameter(value=0.5),
                    "center_2": Parameter(value=0.0),
                    "sigma_0": Parameter(value=1.0, min=1e-3),
                    "sigma_1": Parameter(value=1.0, min=1e-3),
                    "sigma_2": Parameter(value=1.0, min=1e-3),
                },
            ),
        ],
    )


# --8<-- [end:build_graph]


def _plot_projections(
    grid: np.ndarray,
    data_cube: np.ndarray,
    fit_cube: np.ndarray,
    fitted_center: tuple[float, ...],
) -> plt.Figure:
    """Draw XY/XZ/YZ fixed-axis-slice projections through the fitted center.

    Each of the three panels fixes the *remaining* axis at the grid index
    closest to the fitted center along that axis, then shows the resulting
    8x8 plane: the observed data as a heatmap, the recovered fit as
    contour lines on top.

    Args:
        grid: The shared per-axis coordinate vector, shape ``(8,)``
            (identical along all 3 axes).
        data_cube: Observed data, reshaped back from the flat ``(512,)``
            array to shape ``(8, 8, 8)`` in the same (x, y, z) index order
            used to build the coords.
        fit_cube: Recovered fitted model, reshaped the same way as
            ``data_cube``.
        fitted_center: The fitted ``(center_0, center_1, center_2)``
            values, used to pick which slice index to display along each
            fixed axis.

    Returns:
        matplotlib.figure.Figure
    """
    idx = [int(np.argmin(np.abs(grid - c))) for c in fitted_center]
    ix, iy, iz = idx
    extent = (float(grid[0]), float(grid[-1]), float(grid[0]), float(grid[-1]))

    # (plane label, data slice, fit slice, x-label, y-label, fixed-axis note)
    planes = [
        (
            "XY",
            data_cube[:, :, iz].T,
            fit_cube[:, :, iz].T,
            "x",
            "y",
            f"z≈{grid[iz]:+.2f}",
        ),
        (
            "XZ",
            data_cube[:, iy, :].T,
            fit_cube[:, iy, :].T,
            "x",
            "z",
            f"y≈{grid[iy]:+.2f}",
        ),
        (
            "YZ",
            data_cube[ix, :, :].T,
            fit_cube[ix, :, :].T,
            "y",
            "z",
            f"x≈{grid[ix]:+.2f}",
        ),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 5.0))
    for ax, (label, data_slice, fit_slice, xlabel, ylabel, fixed_note) in zip(
        axes,
        planes,
        strict=True,
    ):
        im = ax.imshow(
            data_slice,
            origin="lower",
            extent=extent,
            cmap=_DATA_CMAP,
            aspect="equal",
        )
        ax.contour(
            grid,
            grid,
            fit_slice,
            colors=_FIT_COLOR,
            linewidths=1.4,
            levels=6,
        )
        ax.set_title(f"{label} projection ({fixed_note})")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="intensity")

    fig.suptitle("Data (heatmap) vs. fit (contour) — slices through the fitted center")
    fig.tight_layout()
    return fig


# --8<-- [start:fit]
def fit_and_report(
    coords: np.ndarray,
    y: np.ndarray,
    true_center: tuple[float, ...],
    true_sigma: tuple[float, ...],
) -> tuple[FitResult, list[float]]:
    """Run the joint 3-D least-squares solve and print the per-axis report.

    One simultaneous fit over all 512 points -- the executor strides the
    flat coordinate buffer by ``D=3`` and the analytic Jacobian covers every
    axis, so this is never decomposed into three independent 1-D fits.

    Returns:
        ``(result, fitted_center)`` -- the raw ``FitResult`` and the fitted
        ``[center_0, center_1, center_2]`` values (as a plain list), which
        the ``__main__`` plotting block needs to pick projection slices.
    """
    graph = _build_graph()
    data = MeasurementData(x=coords.tolist(), y=y.tolist())
    result = fit(graph, data)

    print(f"Success: {result.success}   R²: {result.r_squared:.6f}")
    p = {k: v.value for k, v in result.parameters.items()}
    fitted_center: list[float] = []
    for i in range(3):
        center_i = p[f"g.center_{i}"]
        fitted_center.append(center_i)
        print(
            f"  axis {i}: center={center_i:+.3f} (true {true_center[i]:+.1f}), "
            f"sigma={p[f'g.sigma_{i}']:.3f} (true {true_sigma[i]:.1f})",
        )

    return result, fitted_center


result, fitted_center = fit_and_report(coords, y, true_center, true_sigma)
# --8<-- [end:fit]


if __name__ == "__main__":
    # Reshape the flat (512,) data/fit arrays back to the (8, 8, 8) cube --
    # `coords`/`y` were raveled in the same C order the grid was built in
    # (`np.meshgrid(..., indexing="ij")` + `.ravel()`), so a plain `.reshape`
    # inverts it exactly, with axis 0 = x-index, axis 1 = y-index, axis 2 = z-index.
    n = 8
    grid = np.linspace(-5.0, 5.0, n)
    data_cube = y.reshape(n, n, n)
    fit_cube = np.array(result.best_fit).reshape(n, n, n)

    fig = _plot_projections(grid, data_cube, fit_cube, tuple(fitted_center))
    out_path = savefig(fig, "3d_fitting")
    print(f"\nSaved projections to: {out_path}")
