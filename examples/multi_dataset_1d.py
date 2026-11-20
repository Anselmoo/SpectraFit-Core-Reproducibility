"""Joint fit of two 1-D peaks sharing one line-broadening parameter.

Two Gaussian peaks are recorded at different positions and amplitudes, but the
instrument's line-broadening function is known to be identical across the two
measurements (shared ``sigma``). Instead of fitting each dataset on its own —
which would let the two independent line widths drift apart and would let each
fit see only half the evidence for ``sigma`` — we fit both datasets in a single
joint solve via :class:`~spectrafit_core.GlobalFitGraph`. The two peaks are
modeled as *local* replicas of one node (``local_nodes``, one replica per
dataset), and ``shared_local_params=["sigma"]`` ties the replicas' ``sigma``
together with a hard constraint (an ``ExprEdge``) for the duration of the
solve. Amplitude and center stay free per dataset; sigma is constrained by
*all* data points from *both* datasets at once.

Companion to ``multi_dataset_2d.py`` (four 2-D maps sharing center + width
instead of two 1-D peaks sharing width). See ``docs/tutorials/gallery/
multi_dataset.md`` for the full narrative and caveats.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from _plotting import plot_fit, savefig
from spectrafit_core import (
    FitResult,
    GlobalFitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)


# --8<-- [start:data]
def synthesize_shared_sigma_datasets() -> tuple[
    list[MeasurementData],
    list[tuple[float, float]],
    float,
]:
    """Synthesize two 1-D Gaussian datasets sharing one line-broadening sigma.

    Each dataset has its own (amplitude, center) truth but the same
    ``shared_sigma`` line width, plus independent Gaussian measurement noise.
    Returns ``(datasets, truth, shared_sigma)`` — ``truth`` is the
    ``(amplitude, center)`` pair used for each dataset, in dataset order.
    """
    x = np.linspace(0.0, 10.0, 150)
    shared_sigma = 0.5
    truth = [(2.0, 3.0), (3.5, 6.0)]  # (amplitude, center) per dataset
    rng = np.random.default_rng(0)

    datasets = [
        MeasurementData(
            x=x.tolist(),
            y=(
                a * np.exp(-0.5 * ((x - c) / shared_sigma) ** 2) + rng.normal(0, 0.01, x.size)
            ).tolist(),
        )
        for a, c in truth
    ]
    return datasets, truth, shared_sigma


datasets, truth, shared_sigma = synthesize_shared_sigma_datasets()
# --8<-- [end:data]


# --8<-- [start:build_graph]
def build_graph(n_slices: int) -> GlobalFitGraph:
    """Build a GlobalFitGraph: one local Gaussian peak replicated per dataset.

    ``global_nodes=[]`` and ``local_nodes=[<one peak>]`` means the peak is
    replicated once per dataset (``n_slices``). ``shared_local_params=["sigma"]``
    ties every replica's ``sigma`` to slice 0's value via a hard ``ExprEdge``,
    while ``amplitude`` and ``center`` stay free per dataset.
    """
    return GlobalFitGraph(
        global_nodes=[],
        local_nodes=[
            ModelNodeSpec(
                id="pk",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=5.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            ),
        ],
        n_slices=n_slices,
        shared_local_params=["sigma"],
    )


graph = build_graph(len(datasets))
# --8<-- [end:build_graph]


# --8<-- [start:fit]
def fit_datasets(graph: GlobalFitGraph, datasets: list[MeasurementData]) -> FitResult:
    """Run the joint solve: one residual vector spanning both datasets at once."""
    return graph.fit(datasets)


result = fit_datasets(graph, datasets)
# --8<-- [end:fit]


# --8<-- [start:report]
def report_result(
    result: FitResult,
    truth: list[tuple[float, float]],
    n_datasets: int,
) -> None:
    """Print success/R², per-dataset amplitude+center, and the shared-sigma tie drift.

    The tie drift (``|pk_s0.sigma - pk_s1.sigma|``) is expected to be 0.0 to
    machine precision — the engine enforces the ``shared_local_params`` tie as
    a hard ``ExprEdge`` constraint, not a soft penalty.
    """
    p = result.parameters
    print(f"Success: {result.success}")
    print(f"R²:      {result.r_squared:.6f}")
    print()
    print("Per-dataset amplitude and center:")
    for i, (a_true, c_true) in enumerate(truth):
        print(
            f"  slice {i}: amplitude = {p[f'pk_s{i}.amplitude'].value:.4f}"
            f" (true {a_true})"
            f"  center = {p[f'pk_s{i}.center'].value:.4f} (true {c_true})",
        )
    print()
    print("Shared sigma (identical across slices):")
    for i in range(n_datasets):
        print(f"  pk_s{i}.sigma = {p[f'pk_s{i}.sigma'].value:.6f}")
    drift = abs(p["pk_s0.sigma"].value - p["pk_s1.sigma"].value)
    print(f"  Tie drift     = {drift:.2e}")


report_result(result, truth, len(datasets))
# --8<-- [end:report]

if __name__ == "__main__":
    # Plot: one subplot per dataset (small multiples), each showing the raw
    # data overlaid with its jointly-fitted curve. `result.dataset_slices`
    # carries the per-dataset `best_fit` array in the same x-order as the
    # input, so no re-evaluation of the graph is needed.
    assert result.dataset_slices is not None
    fig, axes = plt.subplots(1, len(datasets), figsize=(11.0, 4.5), sharey=True)
    for i, (ds, sl, ax) in enumerate(
        zip(datasets, result.dataset_slices, axes, strict=False),
    ):
        a_true, c_true = truth[i]
        plot_fit(
            ds.x,
            ds.y,
            sl.best_fit,
            title=f"dataset {i}  (true a={a_true}, c={c_true})",
            ax=ax,
        )
    fig.suptitle("Joint fit: two 1-D peaks sharing one line width (sigma)")
    fig.tight_layout()
    out_path = savefig(fig, "multi_dataset_1d")
    print(f"\nSaved figure to {out_path}")
