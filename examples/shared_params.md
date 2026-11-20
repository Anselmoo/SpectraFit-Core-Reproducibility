---
icon: lucide/link-2
description: Two overlapping peaks tied to an identical line width via an ExprEdge, with the shared width annotated on the plot.
tags:
  - Models
  - Solvers
---

# Shared Parameters Across Peaks

!!! warning "Synthetic example"
    The fixture below is two seeded, overlapping peaks with a known-truth
    shared width — chosen to demonstrate that `ExprEdge` and `Parameter.expr`
    produce numerically identical results, not a sweep proving parameter
    tying behaves well across arbitrary peak counts or overlap degrees.

## Quick example — using ExprEdge (graph-level)

You have multiple peaks in a single spectrum and want to enforce that some
parameters are identical across peaks — for example, two Lorentzian peaks
that must share the same line width ($\sigma$), or three multiplet lines
with identical broadening.

The script below builds and fits the `ExprEdge` form, verifies the tie
holds, then — in its "Equivalent form" section — re-solves the same problem
with `Parameter.expr` and asserts the two surfaces agree to within `1e-6`, so
both forms are demonstrated (and kept honest against each other) in one run
rather than only asserted in prose.

```python
--8<-- "shared_params.py:data"
```

Both peaks are generated from the same true `sigma`, because that is what
an instrument's broadening function would actually do — the fit below needs
to recover that shared width, not two independently-drifting ones. Encode
that physical constraint directly in the graph: two Gaussian nodes plus one
`ExprEdge` tying `peak2.sigma` to `peak1.sigma`.

```python
--8<-- "shared_params.py:build_graph_expr_edge"
```

Nothing mechanically new happens at fit time versus `fitting.md` — the same
default LM solver runs, it just re-evaluates and enforces the `ExprEdge` tie
on every iteration.

```python
--8<-- "shared_params.py:fit_execution_expr_edge"
```

Check both peaks' reported `sigma` in the output below: they should be
bit-for-bit equal, not merely close, since `peak2.sigma` is never
independently varied — it's derived from `peak1.sigma` every time.

```python
--8<-- "shared_params.py:result_inspection_expr_edge"
```

Printed values only show a handful of decimal places, which can hide a tie
that's "close enough to eyeball" but not actually enforced — so verify the
tie numerically against machine epsilon instead of trusting the printout.

```python
--8<-- "shared_params.py:tie_verification"
```

![Two Gaussian peaks with a matching shared-width annotation](_static/shared_params.png)

## Why this works

There are **two equivalent ways** to express a parameter tie — choose whichever reads most naturally in your code:

| Surface | How to declare | When to use |
|---|---|---|
| `ExprEdge` (graph-level) | Add an `ExprEdge` to `FitGraph.expr_edges` | When building or composing graphs programmatically; best for complex, multi-edge topologies. |
| `Parameter.expr` (per-param) | Set `expr="source_node.param"` on the target `Parameter` | When building a node inline and the tie is a simple identity; no separate edge list needed. |

Both surfaces compile to the **same** dependency-ordered tied-plan, so the fit result is **numerically identical** regardless of which surface you use. The LM-family solvers (`lm`, `trf`, `geodesic`, `dogleg`, `newton-cg`, `irls`) apply the tied-plan on every iteration. The `global` (differential-evolution) solver searches with the tied parameters held at their seed values and then applies the tie in its post-search LM refinement, so its **final result** is tie-correct. (`solver="varpro"` does not fit tied graphs at all — it rejects them; see the [Model Reference](../../reference/models/index.md#parameter-constraint-surfaces).) Setting the same target parameter via **both** surfaces simultaneously raises a `DuplicateExprTarget` error.

## What just happened

1. **Data creation** — we synthesized two overlapping Gaussians: peak1 at center=0 with amplitude=3, peak2 at center=2.5 with amplitude=2, both with $\sigma=0.6$.

2. **Graph definition** — we built a `FitGraph` with two `GAUSSIAN` nodes, plus one `ExprEdge`:
    - `expr_edges[0]` ties `peak2.sigma` to `peak1.sigma`, meaning throughout the fit, `peak2.sigma` is automatically updated to match `peak1.sigma`.
    - This reduces the degrees of freedom by 1 (peak1.sigma is a free variable; peak2.sigma is dependent).

3. **Fit execution** — the optimizer adjusts the 5 free variables (peak1 amplitude, center, sigma; peak2 amplitude, center) and the tie constraint is enforced at each iteration.

4. **Result inspection** — the `parameters` dict includes both `peak1.sigma` and `peak2.sigma`, but they are **numerically identical** because the tie is enforced. In the output above, both report ~0.6 (the true value).

5. **Tie verification** — we confirm that the difference between `peak1.sigma` and `peak2.sigma` is negligible (< 1e-14 machine epsilon).

## Equivalent form — using Parameter.expr (per-parameter)

The same tie can be declared entirely inside the target `Parameter` itself, without adding an `ExprEdge` to the graph. `build_graph_parameter_expr()` re-solves the same data with `expr="peak1.sigma"` set directly on `peak2.sigma`'s `Parameter` and no `expr_edges` at all; `fit_with_parameter_expr()` fits it, and `check_equivalence()` prints and asserts that the fit result is numerically identical to the `ExprEdge` form above.

```python
--8<-- "shared_params.py:build_graph_parameter_expr"
```

Re-solving with the other tying surface, rather than just asserting in
prose that the two are equivalent, is what turns "should be the same" into
a checked claim — the fit below runs independently against the same data.

```python
--8<-- "shared_params.py:fit_execution_parameter_expr"
```

The equivalence check proves the two surfaces are not just similar but
numerically interchangeable: same $\chi^2$, same tied `sigma`, to within
`1e-6` — so the choice between `ExprEdge` and `Parameter.expr` really is
just a matter of which reads more naturally for a given graph.

```python
--8<-- "shared_params.py:equivalence_check"
```

## Equivalence guarantee

`ExprEdge` and `Parameter.expr` are two syntax forms for the same constraint: both are compiled into the same dependency-ordered tied-plan that the solver evaluates on every iteration. The parity test `tests/parity/test_param_expr_surface_parity.py::test_param_expr_matches_expr_edge` asserts that recovered parameters and $\chi^2$ agree to `rel=1e-6` across the two surfaces.

**Do not use both at once.** Targeting the same parameter with both a `Parameter.expr` and a matching `ExprEdge` raises a `DuplicateExprTarget` error at compilation time.

## See also

- **Related examples**: [`fitting.md`](fitting.md) (basic single-fit), [`multi_dataset.md`](multi_dataset.md) (per-slice shared parameters).
- **Tests**: `tests/unit/spectrafit_core/test_fit.py::test_fit_accepts_expr_edges` (ExprEdge end-to-end), `tests/unit/spectrafit_core/test_fit.py::test_fit_honors_parameter_expr` (Parameter.expr end-to-end), `tests/parity/test_param_expr_surface_parity.py::test_param_expr_matches_expr_edge` (equivalence invariant).
- **API docs**: [`ExprEdge`][spectrafit_core.ExprEdge], [`FitGraph`][spectrafit_core.FitGraph], [`Parameter`][spectrafit_core.Parameter].
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`ExprEdge`, `Parameter.expr`, `tied parameters`, `LM`).
