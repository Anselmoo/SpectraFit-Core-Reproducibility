---
icon: lucide/weight
description: Passing known per-point uncertainty as sigma so the fit weights points by their actual reliability instead of treating every point as equally trustworthy.
tags:
  - Uncertainty
  - Models
---

# Sigma-Weighted Fitting

!!! warning "Synthetic example"
    The fixture below is a single seeded peak with a known, deliberately
    heteroscedastic per-point uncertainty profile — chosen to demonstrate
    that supplying `sigma` changes both the fit and the covariance formula
    used, not a sweep proving this across real measurement-noise models.

## Quick example

Per-point measurement uncertainty is known and heteroscedastic — noise that
scales with the signal itself, as in counting statistics. Pass it as `sigma`
on `MeasurementData` so the fit weights each point by its actual reliability
instead of trusting every point equally.

```python
--8<-- "weighted_fitting.py:data"
```

`sigma_i = sqrt(signal_i) * NOISE_SCALE` mimics counting statistics: the
low-signal baseline is comparatively quiet, the high-signal peak apex is
comparatively noisy. The same peak-plus-background graph is fit against
both variants of the data below.

```python
--8<-- "weighted_fitting.py:build_graph"
```

The only difference between the two `fit()` calls is whether `sigma` is
attached to `MeasurementData` — `data_unweighted` omits it entirely, so
every point is treated as equally reliable regardless of where it sits on
the signal-scaled noise curve.

```python
--8<-- "weighted_fitting.py:fit_both"
```

Comparing both fits against the *true* noiseless model — not just against
the noisy data — is what turns "weighting should help" into a checked
number: the mean absolute deviation from truth in the low-signal baseline
region, where the weighted fit's trust in those quieter points should show
up as a tighter fit.

```python
--8<-- "weighted_fitting.py:compare"
```

![Sigma-weighted vs. unweighted fits under signal-scaled noise, with true per-point error bars](_static/weighted_fitting.png)

## Why this works

**Distinct from `confidence_intervals.md`**: that page derives *output*
uncertainty (`stderr` → a confidence interval) from the Jacobian, always
under uniform per-point weighting. This example supplies *input* per-point
uncertainty that changes both what the solver minimizes and which of two
covariance formulas it uses to report `stderr`. [Solver — Post-fit
statistics](../../explanation/solver-selection.md#post-fit-statistics)
documents both paths: without `sigma`, $\mathrm{cov} = (J^T J)^{-1} \cdot (\chi^2 / \mathrm{dof})$ — a
scale-from-residuals estimate assuming uniform reliability; with `sigma`,
$\mathrm{cov} = (J_w^T J_w)^{-1}$ where $J_w[i, :] = J[i, :] / \sigma_i$ — the Jacobian itself
is weighted by each point's uncertainty before the covariance is formed.
Note that the *reported* `chi2` is always the same unweighted sum-of-squares
either way — `sigma` changes the optimization and the `stderr` formula, not
how `chi2` is reported. Both covariance formulas are still the same
Jacobian-based **linear approximation around the fitted optimum** that
[Confidence Intervals](confidence_intervals.md) flags — weighting by `sigma`
changes which quadratic form is estimated, not whether it's still only a
local approximation, and `stderr` can still be `None` under either path if
the (weighted) Jacobian is ill-conditioned.

## What just happened

1. **Data creation** — a Gaussian peak on a constant background, with noise
   whose standard deviation scales as `sqrt(signal)` — quiet baseline,
   noisier peak apex.

2. **Two fits, one graph shape** — `fit_both()` calls `fit()` once with
   `sigma=None` (uniform weighting) and once with the true per-point `sigma`
   attached to `MeasurementData`.

3. **Weighted fit tracks the low-noise region more tightly** — measured
   against the true noiseless model, the weighted fit's mean absolute error
   in the baseline region is smaller than the unweighted fit's on this
   seeded example, since it correctly discounts the noisier high-signal
   points instead of pulling toward them as if they were equally reliable.

4. **Different `stderr`, same `chi2` reporting convention** — the two fits'
   `amplitude.stderr` differ because they come from the two distinct
   covariance formulas described above; the printed `chi2` for both is the
   same unweighted sum-of-squares convention regardless of `sigma`.

## See also

- **Related examples**: [`confidence_intervals.md`](confidence_intervals.md)
  (turning `stderr` into a 95% CI, always under uniform weighting),
  [`fitting.md`](fitting.md) (the unweighted baseline case).
- **Reference**: [Solver — Post-fit
  statistics](../../explanation/solver-selection.md#post-fit-statistics).
- **API docs**: [`MeasurementData`][spectrafit_core.MeasurementData], [`FitResult`][spectrafit_core.FitResult], [`ParameterResult`][spectrafit_core.ParameterResult].
