---
icon: lucide/ruler
description: Turning each fitted parameter's stderr into a 95% confidence interval, annotated directly on the plot.
tags:
  - Uncertainty
  - Models
---

# Parameter Confidence Intervals

!!! warning "Synthetic example"
    The fixture below is a single seeded Gaussian peak with known truth
    parameters — chosen so the reported 95% confidence interval can be
    checked against a known answer, not a sweep proving Wald-interval
    coverage holds generally across noise levels or parameter regimes.

## Context

**When to use this pattern.** A point estimate and its `stderr` are useful,
but reporting a 95% confidence interval is usually what a downstream
consumer (a paper, a report, a decision) actually needs. This example turns
every fitted parameter's `stderr` into a 95% confidence interval using the
standard normal ("Wald") approximation, and annotates it directly on the
plot for the two parameters most people care about — a peak's `center` and
`amplitude`.

## Quick example

```python
--8<-- "confidence_intervals.py:data"
```

Nothing new here versus [`fitting.md`](fitting.md) — same peak-plus-background shape.

```python
--8<-- "confidence_intervals.py:build_graph"
```

Same solver, same call shape as `fitting.md` too — the interesting part
starts once `result.parameters` is in hand.

```python
--8<-- "confidence_intervals.py:fit_execution"
```

`stderr` alone is a $1\sigma$ standard error, not an interval — it needs scaling
by the standard normal's two-sided 95% critical value ($Z_{95} \approx 1.96$) to
become a Wald confidence interval, and that scaling is a linear
approximation around the fitted optimum, not an exact bound.

```python
--8<-- "confidence_intervals.py:confidence_intervals"
```

![Single-peak fit annotated with 95% parameter confidence intervals](_static/confidence_intervals.png)

## What just happened

1. **Fit as usual** — a single Gaussian peak plus a constant background,
   the same shape as [Single-Dataset Fitting](fitting.md).

2. **From `stderr` to a 95% CI** — for each free parameter,
   $ci_{95} = \text{value} \pm 1.959964 \cdot \text{stderr}$ (`1.959964` is the two-sided 95%
   critical value of the standard normal distribution). This is a **linear
   approximation** around the fitted optimum: it assumes the parameter's
   sampling distribution is well described by a normal distribution with the
   reported variance. That holds well for well-determined, close-to-linear
   problems like this one, but can understate or misshape the true interval
   for a strongly nonlinear or poorly-determined parameter.

3. **`stderr` can be `None`.** It is derived from the Jacobian at the fitted
   optimum, and that derivation is refused rather than returning a bogus
   number when the Jacobian is empty, rank-deficient, or otherwise
   ill-conditioned (overlapping/redundant peaks, or a parameter that barely
   moves the model, are the usual causes) — `ParameterResult.stderr` is
   `None` in that case, not a step this tutorial's pattern can silently skip
   over. Check for `None` before computing a CI from it on real,
   more-degenerate data than this example's clean single peak.

4. **Not covered here: profile-likelihood intervals.** A tighter alternative
   traces the actual $\chi^2$ surface as one parameter is stepped away from its
   optimum, rather than assuming a local quadratic (normal) shape around it.
   That capability is not yet demonstrated by a gallery tutorial — this
   example is scoped to the `stderr`-based Wald interval, which is what
   `FitResult` exposes directly.

5. **Visual reporting** — the fitted curve is plotted as usual, with the
   peak apex's `center` and `amplitude` 95% CIs drawn as error-bar whiskers
   and printed on the plot, alongside a full table (all four free
   parameters) printed to stdout.

## See also

- **Related examples**: [`fitting.md`](fitting.md) (the base single-peak pattern),
  [`varpro_vs_lm.md`](varpro_vs_lm.md) (solver comparison on a separable fit).
- **Reference**: [Solver — Post-fit statistics](../../explanation/solver-selection.md#post-fit-statistics)
  for how `stderr` and `covariance` are derived.
- **API docs**: [`FitResult`][spectrafit_core.FitResult], [`ParameterResult`][spectrafit_core.ParameterResult].
