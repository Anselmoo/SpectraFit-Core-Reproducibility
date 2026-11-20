"""Shared-model global fit: one Gaussian shape, per-slice amplitude.

Companion snippet for the "Alternative — stacked slices" section of
``docs/tutorials/gallery/3d_fitting.md``. Unlike the native N-D example in
that page (one ``gaussian_nd`` node fit jointly over a genuinely
N-dimensional coordinate space), this is a *shared-model* global fit: three
1-D datasets that share the same peak shape (``center``, ``sigma``) but each
have their own ``amplitude``. ``GlobalFitGraph`` with
``shared_local_params=["center", "sigma"]`` ties those two parameters across
all three slices while leaving ``amplitude`` free per slice, then fits all
three datasets in one joint solve.

Standalone runnable script (no plotting) -- run directly with
``python docs/tutorials/gallery/_snippets/stacked_slices.py``.
"""

import numpy as np
from spectrafit_core import (
    GlobalFitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)

# --8<-- [start:stacked_slices]
x = np.linspace(-1, 4, 120)
amps_true = [1.5, 2.5, 1.8]  # one per slice
rng = np.random.default_rng(42)
datasets = [
    MeasurementData(
        x=[[xi] for xi in x.tolist()],
        y=(a * np.exp(-0.5 * ((x - 1.5) / 0.5) ** 2) + rng.normal(0, 0.025, len(x))).tolist(),
    )
    for a in amps_true
]
graph = GlobalFitGraph(
    global_nodes=[],
    local_nodes=[
        ModelNodeSpec(
            id="peak",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.0),
                "center": Parameter(value=1.5),
                "sigma": Parameter(value=0.5, min=1e-6),
            },
        ),
    ],
    n_slices=len(amps_true),
    shared_local_params=["center", "sigma"],  # shared shape; amplitude stays per-slice
)
result = graph.fit(datasets)
print("shared center:", result.parameters["peak_s0.center"].value)
for i in range(len(amps_true)):
    print(f"  slice {i} amplitude:", result.parameters[f"peak_s{i}.amplitude"].value)
# --8<-- [end:stacked_slices]
