---
icon: lucide/shield-alert
description: A handful of corrupted spike points down-weighted automatically by irls:bisquare, instead of dragging a plain least-squares fit off the true peak.
tags:
  - Uncertainty
  - Solvers
---

# Robust Fitting Against Outliers

!!! warning "Synthetic example"
    The fixture below is a single seeded peak with a handful of
    deliberately injected spike outliers — chosen to demonstrate IRLS
    down-weighting on a known-truth case, not a sweep proving robustness
    across outlier fraction, magnitude, or real detector-glitch statistics.

## Quick example

A handful of corrupted or spiked data points — detector glitches, cosmic-ray
hits — shouldn't be allowed to drag a plain least-squares fit off the true
peak. `"irls"` / `"irls:bisquare"` / `"irls:cauchy"` down-weight points with
large residuals automatically instead of treating every point as equally
trustworthy.

```python
--8<-- "robust_fitting.py:data"
```

Four of 150 points (about 2.7%) have a spike of 2.5-4.0 in absolute
y-units added to their true value — 0.83-1.33x the true peak amplitude of
3.0 — at random positions and random sign: spikes, not ordinary
measurement noise. The same clean-peak graph shape is fit against
this spiked data by both solvers below.

```python
--8<-- "robust_fitting.py:build_graph"
```

`"lm"` sees every residual as equally informative, including the four
spikes; `"irls:bisquare"` re-weights points with large residuals down
across its iterations instead.

```python
--8<-- "robust_fitting.py:fit_both"
```

Reporting the recovered `amplitude`/`center` error against the known
planted ground truth — not just an eyeballed curve — turns "IRLS looks more
robust" into a checked number.

```python
--8<-- "robust_fitting.py:compare"
```

![Outlier-robust fitting: plain lm vs. irls:bisquare, spikes marked](_static/robust_fitting.png)

## Why this works

**Distinct from everything else in the gallery**: this is the only
outlier-robustness example. It is real and tested —
`tests/unit/spectrafit_core/test_irls_weights.py` exercises every IRLS
weight variant end-to-end against a spiked fit, pinning that each
`FitOptions.solver` string actually reaches its underlying weight function
rather than silently falling through to plain LM. [Choosing a
Solver](../../how-to/choosing-a-solver.md) recommends `"irls:bisquare"`
(Tukey bisquare weights) once "more than roughly 5-10% of points are
corrupted" — heavier contamination than plain `"irls"`'s Huber weights are
tuned for.

## What just happened

1. **Data creation** — a clean Gaussian peak (`amplitude=3.0`,
   `center=0.3`) with light noise, then four spike outliers injected at
   random positions.

2. **Two fits, one graph shape** — `fit_both()` fits the identical spiked
   data with `FitOptions(solver="lm")` and `FitOptions(solver="irls:bisquare")`.

3. **`"lm"` is visibly pulled toward the spikes** — its recovered amplitude
   and center land measurably farther from the planted ground truth than
   `"irls:bisquare"`'s, asserted numerically rather than only shown on the
   plot.

4. **`"irls:bisquare"` recovers closer to truth** — down-weighting the
   spikes' residuals across iterations keeps the fit anchored to the true
   peak shape instead of the corrupted points.

## See also

- **Related examples**: [`bounded_fitting.md`](bounded_fitting.md) (a
  different solver-choice axis: active bounds, not outliers),
  [`global_optimizer.md`](global_optimizer.md) (poor initial guesses /
  multi-modality, a third distinct solver-choice axis).
- **Tests**: `tests/unit/spectrafit_core/test_irls_weights.py::test_irls_weight_string_reaches_each_variant`.
- **API docs**: [`FitOptions`][spectrafit_core.FitOptions].
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`IRLS`, `residual`, `LM`).
