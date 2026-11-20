---
icon: lucide/git-compare
description: An XPS-style, 8-peak, three-lineshape spectrum with a tied spin-orbit doublet linewidth — spectrafit and lmfit converge to matching R-squared, honestly reported rather than overclaimed.
tags:
  - Benchmarking
  - Validation
---

# spectrafit vs. lmfit: a complex, 8-peak spectrum

!!! warning "Synthetic example"
    The 8-peak XPS-style spectrum below is built from local numpy formulas
    with known truth parameters — chosen so both backends' fits can be
    checked against a known answer, not a sweep proving spectrafit/lmfit
    agreement across arbitrary real spectra.

## Quick example

An XPS-style, 8-peak, three-lineshape spectrum with a tied spin-orbit
doublet linewidth, fit independently by spectrafit and by a hand-built
lmfit composite — the genuinely harder sibling of
[`spectrafit_vs_lmfit_moderate.md`](spectrafit_vs_lmfit_moderate.md).

Peak formulas shared by both backends (spectrafit's own convention: `amplitude`
is the peak height at `center`, never an integrated area):

```python
--8<-- "spectrafit_vs_lmfit_complex.py:formulas"
```

The same three local formulas back both backends' synthetic data below —
no built-in lmfit or spectrafit convenience function is used to generate
it, so both fits start from an identical, apples-to-apples ground truth.

```python
--8<-- "spectrafit_vs_lmfit_complex.py:data"
```

`p3` and `p4` are the two lines of one spin-orbit doublet, and physically
they must share the same natural linewidth — that's what the `ExprEdge`
tying `p4.sigma` to `p3.sigma` below is actually encoding, not just a
syntax demo of the mechanism from `shared_params.md`.

```python
--8<-- "spectrafit_vs_lmfit_complex.py:build_graph"
```

As in the moderate example, lmfit's built-in peak models normalize by area
rather than height, so the composite here is built by hand from the same
formulas above, with the tie re-expressed as an lmfit parameter expression
via the exact dotted-to-underscore translation the real oracle backend
uses.

```python
--8<-- "spectrafit_vs_lmfit_complex.py:build_lmfit"
```

With both backends fit from the same starting guess, the report below
compares chi2, iteration/evaluation counts, wall time, and all 27 fitted
parameters between the two independent solvers.

```python
--8<-- "spectrafit_vs_lmfit_complex.py:report"
```

Printed numbers alone can't distinguish "close because both converged
correctly" from "close by coincidence in a shallow, near-degenerate cost
surface" — so both the tie itself and the aggregate agreement are checked
in code, with a tolerance shaped by what this harder, overlapping problem
can actually guarantee.

```python
--8<-- "spectrafit_vs_lmfit_complex.py:tie_verification"
```

![8-peak overlapping spectrum fitted by both spectrafit and lmfit, with the tied doublet width annotated](_static/spectrafit_vs_lmfit_complex.png)

## Why this works

[`spectrafit_vs_lmfit_moderate.md`](spectrafit_vs_lmfit_moderate.md)
already cross-checks spectrafit against a hand-built [lmfit](https://lmfit.github.io/lmfit-py/)
composite on a moderately busy spectrum. This example goes further: an
8-peak, three-lineshape-family, overlapping spectrum with a linear background
and a physically-motivated tied linewidth — the kind of "real-world messy"
spectrum a single clean 2- or 4-peak demo never has to confront. It is the
genuinely harder sibling, not a repeat.

**The scenario.** An XPS-style core-level region built from eight overlapping
components:

| Node | Lineshape | Role |
|---|---|---|
| `p0` | Gaussian | dominant instrumental-broadening-limited peak |
| `p1`, `p2` | pseudo-Voigt | mixed Gaussian/Lorentzian chemical-state components |
| `p3`, `p4` | Lorentzian | one spin-orbit doublet — **same natural linewidth by physics** |
| `p5`, `p6` | Gaussian | shake-up satellites |
| `p7` | Lorentzian | trace / plasmon-loss tail |
| `bg` | Linear | slowly-varying background |

`p3` and `p4` are the two components of one spin-orbit doublet: physically,
they share the same natural (lifetime-broadened, Lorentzian) linewidth, so
`p4.sigma` is tied to `p3.sigma` via a graph-level `ExprEdge` — the same
mechanism documented in [`shared_params.md`](shared_params.md), applied here
for a physical reason rather than only as a syntax demo.

**Two independent fits, one dataset.** The same synthetic data is fitted
twice: once with `spectrafit_core.fit()` (Rust `"lm"` solver, the tied
linewidth enforced via `ExprEdge`), and once with a *hand-built* lmfit
composite that mirrors the real oracle backend at
`python/oracles/backends/_lmfit.py` — one `lmfit.Model(fn, prefix=...)` per
node summed with `+`, and the tie re-expressed as an lmfit parameter
expression via the exact dotted-to-underscore regex translation that backend
uses for `expr_edges` (`"p3.sigma"` → `"p3_sigma"`).

## What just happened

1. **Data creation** — eight overlapping peaks (three Gaussian, three
   Lorentzian, two pseudo-Voigt) plus a linear background, spanning a 16-unit
   window with peak spacing (1–1.5) comparable to peak width (0.4–0.65) — a
   genuinely overlapping, not just adjacent, spectrum.

2. **`build_graph()`** — an 8-node `FitGraph` plus one `ExprEdge` tying
   `p4.sigma` to `p3.sigma`, following exactly the pattern in
   `shared_params.py`.

3. **`build_lmfit_composite()`** — the independent oracle, built by hand from
   the *same* local peak formulas (never imported from spectrafit-core), so
   the two fits share a model but not an implementation. The tie is applied
   with `params["p4_sigma"].set(expr="p3_sigma")` after translating the
   dotted spectrafit expression through the same regex
   `python/oracles/backends/_lmfit.py` uses for every `expr_edges` entry.

4. **Side-by-side report** — success, chi2, iteration counts (`n_iter` for
   spectrafit, `nfev` for lmfit — the two solvers do not count "iterations"
   the same way, so only the wall-clock timing and chi2/$R^2$ are
   apples-to-apples), and every one of the 27 free parameters, spectrafit vs.
   lmfit, with their absolute difference.

5. **What was actually observed (read this before trusting any 8-peak tied
   fit's agreement in general).** On this particular scenario, from this
   particular starting guess, spectrafit's Rust `"lm"` solver and lmfit's
   SciPy `leastsq` wrapper converged to values agreeing to within **$2 \times 10^{-4}$ on
   every parameter** and matching $R^2$ to four decimal places — tighter
   agreement than the module docstring's caution would necessarily predict.
   That is not a general guarantee: overlapping peaks trade amplitude and
   width against their neighbors along near-degenerate directions of the
   cost surface, and a different noise draw, a different initial guess, or a
   different tied pair could easily land the two independent solvers in
   different corners of a shallow valley — close in chi2, not necessarily
   close in every individual parameter. The script's own assertions reflect
   that: a loose $R^2$-agreement check (`< 0.02`), not a tight per-parameter
   one, because a tight per-parameter assertion is not something either
   solver's local optimizer actually guarantees on a problem this
   overlapping. spectrafit was also markedly faster in wall-clock terms here
   (single-digit milliseconds vs. tens of milliseconds for lmfit's much
   higher function-evaluation count) — consistent with, but not a
   substitute for, the project's own aggregate speed comparison on the
   [Performance](../../performance/index.md) page.

6. **Tie verification** — `p4.sigma` and `p3.sigma` are asserted identical to
   machine precision on the spectrafit side (the `ExprEdge` contract, not a
   statistical claim), independent of however close or far the two backends
   land from each other on the rest of the parameter space.

## See also

- **Related examples**: [`spectrafit_vs_lmfit_moderate.md`](spectrafit_vs_lmfit_moderate.md)
  (the simpler lmfit cross-check this one builds on), [`shared_params.md`](shared_params.md)
  (the `ExprEdge` tied-parameter mechanism used here), [`confidence_intervals.md`](confidence_intervals.md)
  (turning `stderr` into a reportable uncertainty for a fit like this one).
- **Reference**: [Model Composition — DAG IR](../../explanation/model-composition-dag.md)
  (why spectrafit composes models as a DAG rather than lmfit's `model1 + model2`
  operator overloading), [Benchmark engine](../../contributor-guide/benchmark-engine.md)
  (the real lmfit oracle backend this script's `build_lmfit_composite()` mirrors).
- **API docs**: [`ExprEdge`][spectrafit_core.ExprEdge], [`FitGraph`][spectrafit_core.FitGraph], [`ModelNodeSpec`][spectrafit_core.ModelNodeSpec], [`Parameter`][spectrafit_core.Parameter], [`fit`][spectrafit_core.fit].
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`oracle`, `chi2`, `XPS`).
