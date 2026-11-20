---
icon: lucide/box
description: A genuinely 3-D Gaussian recovered in one joint solve, viewed through three fixed-axis slice projections.
tags:
  - Models
  - Solvers
---

# N-Dimensional (≥3-D) Fitting

!!! warning "Synthetic examples"
    All examples below are **synthetic and illustrative** — a single seeded
    geometry each, chosen to demonstrate the mechanism, not measured data and not a
    sweep that proves accuracy across all problem sizes, models, or noise levels.

## Native N-D example — one 3-D Gaussian

You have a genuinely N-dimensional dataset — spectral intensity over
`(x, y, z)` coordinates, or `(kx, ky, kz, energy)` — and want to fit **one
model jointly across all dimensions** (e.g. a trivariate Gaussian).

```python
--8<-- "3d_fitting.py:data"
```

With a genuinely 3-D coordinate cloud in hand, the model needs one node
whose parameters are *indexed* per axis (`center_0..center_2`,
`sigma_0..sigma_2`) rather than three separate `center`/`sigma` params —
that's what lets the compiler infer `D=3` from the parameters supplied
instead of you declaring a dimension anywhere.

```python
--8<-- "3d_fitting.py:build_graph"
```

"D is inferred" matters at solve time too: this is one simultaneous
least-squares problem over all 512 points, with the executor striding the
flat coordinate buffer by `D` and the analytic Jacobian covering every
axis at once — not three independent 1-D fits stitched together.

```python
--8<-- "3d_fitting.py:fit"
```

![Data vs. fit heatmap/contour projections for a native 3-D Gaussian](_static/3d_fitting.png)

## Why this works

As of SP-2, spectrafit fits this **natively**: the parametric `gaussian_nd`
kernel handles any dimensionality `D`, and the dimensionality is
**inferred** from the node's indexed `center_<i>` parameters. No
`MeasurementData3D` class is needed — a D-dimensional point is just a
coordinate row of length `D`.

!!! note "Shared-model global fit"
    If instead you have *several datasets sharing one model* (e.g. spectra at different
    conditions, each with its own amplitude but a shared peak shape), that is a
    **shared-model global fit** — use `GlobalFitGraph`; see the "Stacked slices"
    alternative below and [`multi_dataset.md`](multi_dataset.md).

## Arbitrary N (demonstrated at 3-D and 5-D)

`gaussian_nd` is not capped at 3-D. Give it `center_0..center_4` / `sigma_0..sigma_4`
and a 5-D coordinate grid, and it fits a 5-D Gaussian the same way — the kernel and the
solver are *structurally* dimensionality-general (the kernel sums over all `D` axes; the
executor strides by `D`), so there is no dimension-specific code path that caps `N`.
That structural generality is **demonstrated at 3-D and 5-D** by the Rust solver tests
(`run_gaussian_nd_recovery` at `d=3` and `d=5`); higher `N` follows from the same code
path but is not separately accuracy-tested here. The only practical limit is that an
N-D grid has `points = size**N`, so keep per-axis resolution modest at high `N`.

## What just happened

1. **Data** — a synthetic 3-D Gaussian sampled with light noise ($\sigma=0.05$).
2. **Graph** — a single `gaussian_nd` node. Its parameters are **indexed**
   (`center_0..center_{D-1}`, `sigma_0..sigma_{D-1}`, plus `amplitude`); the compiler
   counts the `center_<i>` parameters to infer `D=3` and validates the full
   `1 + 2D` set is present (a missing `center_i` raises a clear error).
3. **Fit** — one simultaneous least-squares solve over all 512 points. The executor
   strides the flat coordinate buffer by `D`, and the analytic Jacobian covers every
   axis. The planted center/$\sigma$ are recovered to within a few percent.

## Performance note

The N-D path evaluates the model **per point** (the optimized batched fast-path is
1-D-only), so very large N-D grids (`size**N` points) are heavier than a 1-D fit of
the same point count. For volumetric data, keep the per-axis resolution modest, or
down-sample before fitting.

## Alternative — stacked slices (different parameters per slice)

If your "third dimension" is really an **index over datasets that share a model but
differ per slice** (e.g. a Gaussian whose amplitude changes from slice to slice while
center/$\sigma$ stay fixed), that is a *shared-model global fit*, not a single N-D kernel.
Use `GlobalFitGraph` with `shared_local_params`:

```python
--8<-- "_snippets/stacked_slices.py:stacked_slices"
```

The two patterns answer different questions: **native N-D** fits *one* model over an
N-dimensional coordinate space; **stacked slices** fits *one shared model* across many
lower-dimensional datasets with per-slice free parameters.

## See also

- **Related examples**: [`multi_dataset.md`](multi_dataset.md) (shared-model multi-spectrum
  global fit), [`shared_params.md`](shared_params.md) (tied parameters within one spectrum),
  [`fitting.md`](fitting.md) (single-dataset fit).
- **Tests**: `tests/unit/spectrafit_core/test_fit_nd.py` (native 3-D `gaussian_nd`
  round-trip), `tests/unit/spectrafit_core/test_global_fit.py` (GlobalFitGraph).
- **API docs**: `ModelType.GAUSSIAN_ND`, [`FitGraph`][spectrafit_core.FitGraph], [`GlobalFitGraph`][spectrafit_core.GlobalFitGraph].
