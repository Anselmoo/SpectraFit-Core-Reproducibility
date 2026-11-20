---
icon: lucide/lock
description: Holding a background level fixed at a value known from an independent measurement, instead of fitting it.
tags:
  - Models
  - Solvers
---

# Holding a Parameter Fixed

!!! warning "Synthetic example"
    The fixture below is a single seeded peak with one parameter's "known"
    value baked in by construction — chosen to demonstrate the `vary=False`
    mechanism, not a sweep proving fixed-parameter fits behave well across
    real independently-measured calibration scenarios.

## Quick example

You already know a parameter's value from an independent measurement — a
background level read off a blank/dark scan, or an instrument-broadening
$\sigma$ from a calibration standard — and want to hold it fixed instead of
asking this same noisy dataset to estimate it too. Set `vary=False` on that
`Parameter`, with no `expr`.

```python
--8<-- "fixed_params.py:data"
```

`TRUE_BACKGROUND` stands in for a level measured independently of this
dataset — known exactly, not something to estimate from the same noisy
points. Build two graphs against the same data: one pins `bg.c` at that
known value, the other leaves it free to compare against.

```python
--8<-- "fixed_params.py:build_graph"
```

Both graphs are fit against the identical `(x, y)` — the only difference
between the two calls below is `bg.c`'s `vary` flag.

```python
--8<-- "fixed_params.py:fit_both"
```

Two facts are guaranteed by the mechanism itself, not just this one seeded
example: fixing `bg.c` removes it from the free-parameter vector, so
`dof = n_points - n_free` is exactly one higher in the fixed run, and its
`stderr` is `None` there since a fixed parameter was never part of the
optimization the covariance matrix describes.

```python
--8<-- "fixed_params.py:compare"
```

![Peak + background fit with the background held fixed at a known value](_static/fixed_params.png)

## Why this works

**Distinct from `shared_params.md`**: that page ties one parameter's value
*to another fitted parameter* via `expr`. This example fixes a parameter *to
a known constant*, with no `expr` involved at all. `Parameter`'s own
docstring calls out `vary` as "whether the solver may adjust this
parameter" — `vary=False` excludes it from the free set entirely for the
whole fit, regardless of how close or far its constructed `value` is from
any other parameter.

## What just happened

1. **Data creation** — a single Gaussian peak on top of a background level
   (`TRUE_BACKGROUND = 0.35`) known exactly, as if measured from a blank scan.

2. **Two graphs, one dataset** — `build_graph(fix_background=True)` constructs
   `bg.c` as `Parameter(value=TRUE_BACKGROUND, vary=False)`; the free variant
   uses the same starting value with `vary=True` (the default).

3. **dof differs by exactly one** — fixing `bg.c` removes it from the
   optimizer's free set, so the fixed run's `dof` is one higher than the
   free run's.

4. **`stderr` is absent for the fixed parameter** — `ParameterResult.stderr`
   for `bg.c` is `None` in the fixed run, since it was never part of the
   covariance matrix the solver estimated.

5. **Tighter peak-parameter uncertainty** — with a correctly-known fixed
   background, the peak's `amplitude`/`sigma` `stderr` come out tighter than
   the free run's on this example, matching the expected direction (removing
   a genuinely-correlated nuisance parameter from the free set cannot
   increase the remaining parameters' Fisher information) — the exact margin
   is specific to this one seeded example, not a general accuracy claim.

## See also

- **Related examples**: [`shared_params.md`](shared_params.md) (tying a
  parameter to another fitted parameter via `expr`, not a constant),
  [`confidence_intervals.md`](confidence_intervals.md) (turning `stderr`
  into a reported confidence interval).
- **Reference**: `python/spectrafit_core/parameters.py` (`Parameter.vary`
  docstring).
- **API docs**: [`Parameter`][spectrafit_core.Parameter], [`ParameterResult`][spectrafit_core.ParameterResult], [`FitGraph`][spectrafit_core.FitGraph], [`FitResult`][spectrafit_core.FitResult].
