---
icon: lucide/scale
description: The same separable two-peak fit solved by both the VarPro and Levenberg-Marquardt solvers, converging to the identical optimum from a smaller nonlinear-only parameter space.
tags:
  - VarPro
  - Solvers
---

# VarPro vs. Levenberg-Marquardt

!!! warning "Synthetic example"
    The fixture below is a single seeded, separable two-peak graph with
    known-truth parameters — chosen to demonstrate that VarPro and LM
    converge to the identical optimum on a known answer, not a sweep
    proving this across arbitrary separable-graph shapes.

## Context

**When to use this pattern.** Your model graph is *separable* — the only
nonlinear parameters are shape parameters like `center`/`sigma`, and each
node's `amplitude` is purely linear, with no tied parameters or bound
constraints on the nonlinear side. This is exactly the shape
`FitOptions(solver="auto")` itself detects and routes to `"varpro"` (see
[Choosing a Solver](../../how-to/choosing-a-solver.md)). This example fits
the same two-peak graph with both `"lm"` and `"varpro"` to show they land on
the identical optimum, from a smaller nonlinear-only parameter space.

## Quick example

```python
--8<-- "varpro_vs_lm.py:data"
```

Build a graph over this data with no background node, no bounds, and no
tied parameters — each peak's only linear parameter is `amplitude`; `center`
and `sigma` are nonlinear. That keeps the graph *separable*, which is
exactly the precondition VarPro needs.

```python
--8<-- "varpro_vs_lm.py:build_graph"
```

`fit()` is called twice, once per solver, each time on a fresh `FitGraph`
from `build_graph()` rather than a reused object — that rules out any doubt
about shared mutable state biasing one solver's starting point against the
other's.

```python
--8<-- "varpro_vs_lm.py:run_solvers"
```

The two solvers take different optimization paths (six free parameters for
`lm`, four for `varpro`, with the two amplitudes solved analytically), so
exact bit-for-bit equality isn't the right bar — a `1e-4` tolerance on
`chi2` is what actually distinguishes "converged to the same optimum" from
"drifted to a different one".

```python
--8<-- "varpro_vs_lm.py:verify_agreement"
```

![Two-peak fit compared between the VarPro and Levenberg-Marquardt solvers](_static/varpro_vs_lm.png)

## What just happened

1. **Data creation** — two overlapping Gaussian peaks, no background node.
   Each peak's only linear parameter is its `amplitude`; `center` and `sigma`
   are the nonlinear shape parameters VarPro's outer optimizer works over.

2. **Two solver runs, same graph shape** — `run_solvers()` calls `fit()` once
   with `FitOptions(solver="lm")` and once with `FitOptions(solver="varpro")`,
   on a fresh `FitGraph` (from `build_graph()`) each time. `"lm"` optimizes
   all six free parameters together (2 peaks × 3 params); `"varpro"`
   optimizes only the four nonlinear ones (`center`, `sigma` per peak) and
   solves the two amplitudes analytically at every step.

3. **Same optimum, different path** — `verify_agreement()` asserts `chi2`
   matches between solvers to `1e-4`, and every fitted parameter agrees to
   within `1e-7` in practice. This is the actual guaranteed property:
   VarPro is not a different model, just a different (smaller) parameter
   space to search.

4. **Measured wall-clock time, honestly scoped** — `run_solvers()` reports the
   median of 9 timed reps per solver (after an untimed warm-up call) and
   plots both numbers without declaring a "winner". Whether VarPro or LM is
   faster in absolute terms depends on problem size, peak count, and
   hardware — on this small two-peak demo the two are comparable. The
   project's own aggregate speed comparison across its full benchmark case
   catalog lives on the [Performance](../../performance/index.md) page, not
   in this gallery script.

## See also

- **Related examples**: [`shared_params.md`](shared_params.md) (tied parameters — not supported
  under `"varpro"`), [`confidence_intervals.md`](confidence_intervals.md) (uncertainty reporting).
- **Reference**: [Choosing a Solver](../../how-to/choosing-a-solver.md),
  [Rust ↔ Python binding audit](../../reference/rust/binding-audit.md#solver-dispatch-cratesspectrafit-solversrcdispatchrs).
- **API docs**: [`FitOptions`][spectrafit_core.FitOptions], [`FitGraph`][spectrafit_core.FitGraph], [`ModelNodeSpec`][spectrafit_core.ModelNodeSpec], [`fit`][spectrafit_core.fit].
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`VarPro`, `tied parameters`, `LM`).
