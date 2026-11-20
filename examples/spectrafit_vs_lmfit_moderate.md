---
icon: lucide/shield-check
description: Four overlapping peaks of mixed shape on a sloped background, fitted independently by spectrafit-core and a hand-built lmfit composite — agreeing to within 4e-6.
tags:
  - Benchmarking
  - Validation
---

# spectrafit vs. lmfit: a moderately complex spectrum

!!! warning "Synthetic example"
    The four-peak spectrum below is built from local numpy formulas with
    known truth parameters — chosen so both backends' fits can be checked
    against a known answer, not a sweep proving spectrafit/lmfit agreement
    across arbitrary real spectra.

## Quick example

Four overlapping peaks of mixed shape (two Gaussian, two Lorentzian) on a
sloped linear background, fitted independently by spectrafit's own `fit()`
and by a hand-built [lmfit](https://lmfit.github.io/lmfit-py/) composite —
an external, independently-implemented oracle rather than a second
spectrafit solver.

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:formulas"
```

These same raw numpy formulas back both backends' synthetic data below —
neither library's own peak-shape convenience function is used, so the
comparison starts from identical ground truth rather than two slightly
different definitions of "Gaussian".

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:data"
```

Nothing new here — build the graph the same way `fitting.md` does, just
with more nodes (4 peaks + a linear background instead of 1 peak +
constant).

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:build_graph"
```

lmfit's own `GaussianModel`/`LorentzianModel` normalize by area rather than
peak height, which would make a parameter-by-parameter comparison
meaningless — so the lmfit side is built by hand from the exact same numpy
formulas above, matching spectrafit's peak-height convention exactly.

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:build_lmfit"
```

With both backends fit on the same data from the same starting guesses,
what's being compared is chi2, wall time, and all 14 fitted parameters
side by side.

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:report"
```

A printed table invites eyeballing "close enough", which can hide a
systematic drift a numeric tolerance would catch — so agreement is asserted
in code (`1e-4` on every parameter and on chi2), not just left for a reader
to judge from the table above.

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:assertions"
```

![4-peak fit (2 Gaussian + 2 Lorentzian + linear background) compared between spectrafit and lmfit](_static/spectrafit_vs_lmfit_moderate.png)

## Why this works

**Why this example exists.** Every other script in this gallery cross-checks
spectrafit against *itself* — a different solver
([`varpro_vs_lm.md`](varpro_vs_lm.md)), a different parameter surface
([`shared_params.md`](shared_params.md)), a different dimensionality
([`3d_fitting.md`](3d_fitting.md)). This is the first tutorial in this
gallery to include [lmfit](https://lmfit.github.io/lmfit-py/) as an external
cross-check, not just spectrafit's own alternate solvers. lmfit is a
separate, independently-implemented least-squares package — its own
Levenberg-Marquardt driver, its own parameter bookkeeping — so agreement
with it is a genuinely independent oracle in a way agreement between two
spectrafit solvers is not. The project's own benchmark harness
(`python/oracles/`, see
[Benchmark engine](../../contributor-guide/benchmark-engine.md))
uses exactly this idea at scale, running spectrafit against lmfit and
jax/optimistix across a whole case catalog; this example distills that
pattern down to one hand-built, readable script.

**Why this scenario.** The gallery's other examples are deliberately simple
(one or two isolated peaks) so the mechanic being demonstrated stays
front-and-center. This one is intentionally more realistic: four
overlapping peaks of *mixed* shape (two Gaussian, two Lorentzian) sitting on
a sloped linear background — closer to what a real spectrum (XPS, Raman,
UV-Vis, ...) actually looks like than a single clean peak in flat noise.

## What just happened

1. **Data creation** — two Gaussian peaks and two Lorentzian peaks, spaced
   closely enough to overlap in their wings, on top of a sloped linear
   background. Both backends are handed the same deliberately-off-true
   starting guesses (a realistic "eyeballed from the plot" starting point,
   not the answer key), so the comparison is apples-to-apples.

2. **Backend 1: spectrafit's own `fit()`** — a 5-node `FitGraph` (4 peaks +
   one `ModelType.LINEAR` background node) built by `build_graph()`, fit
   with the default solver.

3. **Backend 2: a hand-built lmfit composite model** — following the exact
   pattern used by the project's own lmfit oracle backend
   (`python/oracles/backends/_lmfit.py`): one `lmfit.Model(fn, prefix=...)`
   per component, summed with `+`, each component's `.make_params(...)`
   merged into one `Parameters` object, then
   `composite.fit(y, params, x=x)`. The per-peak numpy formulas
   (`gaussian`, `lorentzian`, `linear_bg`) use the same convention as
   `python/oracles/models.py`: `amplitude` is the peak height at `center`
   (not the integrated area), Gaussian `sigma` is the standard deviation,
   and Lorentzian `sigma` is the half-width at half maximum (HWHM) — a bare
   hand-rolled lmfit model that matches spectrafit's own convention exactly,
   rather than lmfit's builtin `GaussianModel`/`LorentzianModel`, which
   normalize by area.

4. **Side-by-side report** — a printed table of `chi2` and measured
   wall-clock time per backend, then a second table comparing all 14 fitted
   parameters (`amplitude`/`center`/`sigma` across 4 peaks, plus the
   background's `slope` and `intercept`) side by side with their absolute
   difference.

5. **Agreement, asserted not just claimed** — the script asserts every
   fitted parameter agrees between backends to within `1e-4`, and `chi2`
   agrees to within `1e-4` too. In practice, on this problem, both land
   within about `4e-6` of each other — two independently-implemented
   optimizers converging on the same optimum from the same starting point.

## See also

- **Related examples**: [`varpro_vs_lm.md`](varpro_vs_lm.md) (spectrafit's
  own alternate-solver comparison), [`shared_params.md`](shared_params.md)
  (tied parameters), [`fitting.md`](fitting.md) (the simplest single-peak +
  background workflow this example builds on).
- **Reference**:
  [Benchmark engine](../../contributor-guide/benchmark-engine.md)
  (the full `python/oracles/` harness this script's lmfit pattern is drawn
  from), [Choosing a Solver](../../how-to/choosing-a-solver.md), the
  [Performance](../../performance/index.md) page (the project's own aggregate
  spectrafit-vs-lmfit speed and accuracy comparison across its full benchmark
  case catalog — the wall-clock numbers printed here are one small demo
  problem, not a general performance claim).
- **API docs**: [`FitGraph`][spectrafit_core.FitGraph], [`ModelNodeSpec`][spectrafit_core.ModelNodeSpec], [`Parameter`][spectrafit_core.Parameter], [`fit`][spectrafit_core.fit].
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`oracle`, `chi2`, `tied parameters`, `HWHM`, `XPS`).
