---
icon: lucide/chart-scatter
description: Two 1-D peaks fitted jointly with one shared line width, and four 2-D maps fitted jointly with a shared peak center and width.
tags:
  - Uncertainty
  - Solvers
---

# Multi-Dataset Joint Fitting

!!! warning "Scope of these examples"
    All examples below are **synthetic and illustrative**:
    each uses a single seeded geometry (one model type, one grid size, one noise level,
    one random seed) chosen to demonstrate the mechanism, not to characterise accuracy
    across problem sizes, model families, or noise regimes. They show that the joint
    solve runs and that the shared-parameter ties are enforced within a solve. They are
    not measured data and are not a sweep that proves general accuracy.

You have N related spectra that share one identical model and want to solve
them jointly instead of independently — shared parameters end up
constrained by *all* the data at once, rather than just the one dataset
they happen to sit in.

## 1-D example: local peaks with a shared line width

Two Gaussian peaks are recorded at different positions and amplitudes, but the
instrument's line-broadening function is known to be identical across measurements
(shared `sigma`). We fit both datasets jointly and recover the per-dataset amplitude
and center while the shared `sigma` is constrained by all data.

```python
--8<-- "multi_dataset_1d.py:data"
```

Building N independent `FitGraph`s here would fit each dataset's `sigma`
against only its own points, letting the two widths drift apart even though
the instrument's broadening is physically identical for both. Instead, use
`local_nodes` to replicate one peak per dataset plus `shared_local_params`
to tie `sigma` across the replicas before any fitting happens.

```python
--8<-- "multi_dataset_1d.py:build_graph"
```

The payoff of a joint solve over N separate fits: `sigma` is now
constrained by every data point from both datasets at once, not half of
them, so the shared estimate is more precise than either single-dataset fit
could produce on its own.

```python
--8<-- "multi_dataset_1d.py:fit"
```

A near-zero shared-parameter drift here isn't a coincidence to be pleased
about — it's the `ExprEdge` tie being enforced exactly, every iteration, so
the two `sigma` values were never actually free to disagree.

```python
--8<-- "multi_dataset_1d.py:report"
```

![Two panels of a jointly-fitted 1-D peak sharing one line width](_static/multi_dataset_1d.png)

### What just happened

1. **Local nodes, shared params** — `local_nodes` are replicated once per dataset
   (here: `pk_s0` and `pk_s1`). By default every replica's parameters are
   independent. `shared_local_params=["sigma"]` adds an `ExprEdge` tie so
   `pk_s1.sigma` is constrained to equal `pk_s0.sigma`, reducing the degrees of
   freedom by one.

2. **Joint solve** — `graph.fit(datasets)` concatenates the residuals of both
   datasets into one vector and minimizes a single objective. Both datasets
   contribute to `sigma`'s estimate; per-dataset amplitude and center vary freely.

3. **Tie holds exactly within this solve** — the reported drift is 0.0 (machine
   precision). The engine enforces each shared-parameter tie as a hard constraint
   (an `ExprEdge`) so that, within a given fit, the tied parameters take an
   identical value throughout the solve. This is how the constraint is implemented,
   not a claim about all possible problem geometries or solvers.

## 2-D multi-spectrum example: four different maps sharing center and width

An illustrative 2-D multi-spectrum case (synthetic, one geometry): N 2-D
`gaussian2d` spectra that differ only in amplitude are fitted jointly. The shared
peak center and widths are constrained by *all four maps at once*; each map
contributes its own amplitude. This demonstrates the mechanism (SP-3) in one
representative seeded instance — not a sweep across geometries or noise levels.

```python
--8<-- "multi_dataset_2d.py:data"
```

Same pattern as the 1-D case, scaled up: four replicas of one `gaussian2d`
node, this time with `shared_local_params` tying all four shape parameters
(`center_x`, `center_y`, `sigma_x`, `sigma_y`) at once, leaving only
`amplitude` free per map.

```python
--8<-- "multi_dataset_2d.py:build_graph"
```

The joint solve now spans 1600 data points across all four maps but only 8
free parameters — the shared shape sees four times the evidence a single
map's fit would.

```python
--8<-- "multi_dataset_2d.py:fit"
```

Same tie guarantee as before, just across four shared parameters instead of
one: each drift below is 0.0 because the constraint is hard, not
approximate.

```python
--8<-- "multi_dataset_2d.py:report"
```

![2x2 grid of jointly-fitted 2-D map line-outs sharing center and width](_static/multi_dataset_2d.png)

### What just happened

1. **Four 2-D spectra** — each is a 20×20 `gaussian2d` map with the same peak
   center and widths but a different amplitude. The true parameters are
   `center_x = −1.0`, `center_y = 1.5`, `sigma_x = 1.2`, `sigma_y = 0.9`.

2. **Shared shape, free amplitude** — `shared_local_params` ties
   `center_x`, `center_y`, `sigma_x`, `sigma_y` across all four dataset replicas.
   Each replica's `amplitude` remains free.

3. **One joint solve** — the optimizer minimizes a residual vector of length
   4 × 400 = 1600 data points simultaneously, with 4 (shared shape) + 4
   (per-slice amplitudes) = 8 free parameters.

4. **Tie drift is 0.0 in this run** — within this solve the shared parameters are
   identical across slices (not approximately equal), because the engine enforces
   each tie as a hard constraint (`ExprEdge`), not a soft penalty. The printed
   drift of 0.0 is a property of how the constraint is implemented, reported for
   the specific geometry shown above.

## Why this works

One simultaneous joint solve is strictly better than N independent fits:
shared parameters are constrained by *all* data points at once, giving a
more precise estimate and ensuring consistency.

Typical use cases: temperature-dependent measurements sharing a peak position; a
series of samples sharing a calibrated instrument response; spatial maps sharing
center and width but varying amplitude per location.

**Contrast with `shared_params.md`** (which ties parameters across
*peaks within one spectrum*; this file ties parameters across *datasets*).

!!! note "Benchmark UI status"
    The corresponding `global_fit` contract field is now
    rendered in the production web UI as a "global-fit-showcase" panel within the
    Evidence destination's "Native showcases" section. The capability lives in the
    fitting engine (`GlobalFitGraph`) and is exercised by tests, and the benchmark
    showcase is displayed alongside other native multi-dataset fitting demonstrations.

## Honest naming note

This capability was previously misnamed `time_resolved` in the benchmark contract.
That name implied a time axis, but the mechanism is a general shared-model
multi-spectrum joint fit: time is just one incidental axis interpretation. The
contract field was renamed `global_fit` (classes `GlobalFit` / `GlobalFitSlice`,
axis fields `dataset_axis` / `coord` / `axis_label`) in schema version 1.6.

## See also

- **Related examples**: [`fitting.md`](fitting.md) (single dataset, single peak),
  [`shared_params.md`](shared_params.md) (per-peak parameter ties within one spectrum),
  [`3d_fitting.md`](3d_fitting.md) (2-D Gaussian maps).
- **Tests**:
  `tests/unit/spectrafit_core/test_global_fit.py::test_global_fit_graph_shared_local_param_across_slices`
  (1-D shared sigma),
  `tests/unit/spectrafit_core/test_global_fit.py::test_global_fit_several_2d_spectra_shared_model_recovers_and_ties`
  (2-D multi-spectrum proof).
- **API docs**: [`GlobalFitGraph`][spectrafit_core.GlobalFitGraph], [`GlobalFitGraph.fit`][spectrafit_core.GlobalFitGraph.fit], [`GlobalFitGraph.fit_all_slices`][spectrafit_core.GlobalFitGraph.fit_all_slices].
