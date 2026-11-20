---
icon: lucide/scan-search
description: A model that is simply wrong, fitted to real measured data — r-squared climbs to 0.97 and AIC falls by 551 while the residual stays structured at every step.
tags:
  - Validation
  - Models
---

# A Wrong Model with a Good $r^2$

!!! info "Real measured data, redistributable under ODbL"
    This page fits
    `reproducibility/spectra/eelsdb-fe2o3-l23/DspecTi3wqG.msa`, the Fe
    $L_{2,3}$ edge of $\text{Fe}_2\text{O}_3$, from the
    [EELS Database](https://eelsdb.eu/spectra/iron-oxide-2/). The data is
    published under the **Open Data Commons Open Database License (ODbL)**,
    which permits redistribution with attribution — so the spectrum ships with
    this repository and **you can refit it yourself**. Credit is due to the
    EELS Data Base and to the contributor, Qiang Xu. Cite Ewels P, Sikora T,
    Serin V, Ewels CP, Lajaunie L. A Complete Overhaul of the Electron
    Energy-Loss Spectroscopy and X-Ray Absorption Spectroscopy Database:
    eelsdb.eu. *Microscopy and Microanalysis.* 2016;22(3):717-724.
    [doi:10.1017/S1431927616000179](https://doi.org/10.1017/S1431927616000179).
    The ODbL applies to the data; this repository's code stays MIT. Full notice:
    that directory's `README.md`.

## Quick example

**Every other page in this gallery fits data the model can actually
describe.** This one deliberately does not, using a real measurement rather
than a synthetic fixture, because the effect it demonstrates is a property
of real spectra.

```python
--8<-- "misspecified_model.py:data"
```

The window spans the L3 white line at 710.75 eV and the shoulder below it,
stopping short of the L2 edge near 723 eV so the comparison stays about one
absorption region. Intensities are raw detector counts, not normalised.

```python
--8<-- "misspecified_model.py:ladder"
```

A *run* is a maximal stretch of same-signed residuals. Independent noise around
a correct model gives about $2 n_+ n_- / n + 1$ runs; far fewer means the signs
arrive in long stretches — the curve sits systematically above the data in one
place and below it in another.

```python
--8<-- "misspecified_model.py:runs_test"
```

![Three fits of the same Fe L3 window of iron oxide, top row, with residuals below each. The fitted curve visibly improves left to right while every residual panel keeps an oscillating systematic shape.](_static/misspecified_model.png)

## Why this works

Each other page in this gallery therefore ends with a high $r^2$ that means
what it appears to mean. Three models of the same L3 window, in increasing
order of elaboration, are compared here instead. Watch two scalar
goodness-of-fit scores and one property of the residual disagree completely:

| model | $r^2$ | AIC | runs | expected | $z$ |
|---|---:|---:|---:|---:|---:|
| 1 Gaussian | 0.65723 | 4087.3 | 9 | 120.4 | $-14.5$ |
| 2 Gaussians | 0.93153 | 3705.2 | 15 | 120.8 | $-13.7$ |
| 3 Voigts | 0.96773 | 3535.9 | 16 | 121.5 | $-13.6$ |

$r^2$ climbs to 0.97. AIC falls by 551. **Both say "better" at every rung. The
runs test says "still the wrong model" at every rung, including the last — and
unlike $r^2$, it barely moves.**

## What just happened

1. **One Gaussian ($r^2 = 0.657$)** — captures the white line and nothing else.
   The shoulder below it and the decay above are missed entirely and the
   residual carries both whole. Not a subtle failure; included as the baseline.

2. **Two Gaussians ($r^2 = 0.932$)** — now the shoulder has a component too, and
   the fit looks convincing at a glance. The residual has shrunk substantially
   but kept its shape: the same oscillation across the white line, because a
   Gaussian cannot produce the line's wings.

3. **Three Voigts ($r^2 = 0.968$)** — a defensible model, and by both scalar
   scores an excellent one. Yet the residual still oscillates through the white
   line at $z = -13.6$, statistically indistinguishable from rung 1's $-14.5$.
   The remaining structure is real, and there are two independent reasons for
   it. An Fe L3 edge carries **multiplet structure** that no small number of
   independent symmetric components reproduces. And a core-loss edge sits on a
   **decaying background** from lower-energy excitations that none of these
   three models includes at all.

**The residual amplitude falls at every rung. The residual *shape* does not.**
That distinction is invisible to $r^2$ and to AIC, both of which reduce the
residual to a single number and discard the ordering that carries the evidence.

!!! warning "What the runs test does and does not license"
    The test assumes independent residuals. This spectrum is heavily
    oversampled — 0.05 eV channels against a 0.3 eV instrumental resolution, so
    roughly six channels per resolvable feature — and genuinely correlated
    measurement noise would also depress the run count. Read a large negative
    $z$ as strong corroboration of what the residual panel already shows, not
    as a calibrated p-value. The claim here is "the residual is not noise", not
    a significance level.

## What to do about it

- **Plot the residual. Always.** Every conclusion on this page comes from the
  bottom row of the figure; the top row alone would have been persuasive and
  wrong.
- **Prefer a diagnostic that uses residual *order*** — a runs test, a
  Durbin-Watson statistic, an autocorrelation — over one that does not.
  $r^2$, $\chi^2_\text{red}$, AIC and BIC are all order-blind.
- **Do not fix structure by adding components.** Rungs 2 and 3 do exactly that
  and the structure survives both. A residual that keeps its shape while
  shrinking is telling you the *form* is wrong, not that the count is too low.
- **Ask what the model is missing, not how many peaks it needs.** Here the
  honest next step is a background term and a multiplet-aware line shape, not a
  fourth Voigt.
- **Let AIC/BIC rank models you already believe**, rather than certify that any
  of them is right. Rung 3 wins the AIC comparison decisively and is still
  rejected by the residual.

## See also

- **Related examples**: [`failed_fit.md`](failed_fit.md) (the other way to be
  misled — a converged fit reporting `success=True` with a negative $r^2$),
  [`confidence_intervals.md`](confidence_intervals.md) (uncertainties on
  parameters that assume the model is correct to begin with).
- **API docs**: `FitResult.residuals`, `FitResult.r_squared`, `FitResult.aic`,
  `FitResult.bic`.
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`residual`, `AIC`, `BIC`).
