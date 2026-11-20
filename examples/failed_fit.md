---
icon: lucide/triangle-alert
description: A fit that reports success=False and names the reason, and a worse one that reports success=True with a negative r-squared, because the degeneracy guard is deliberately narrow.
tags:
  - Validation
  - Solvers
---

# When a Fit Fails

!!! warning "Synthetic example"
    A single seeded Gaussian with light noise. The data here is deliberately
    easy — every failure on this page is caused by where the fit was told to
    start, not by a hard measurement. It demonstrates how failure is
    *reported*; it is not a survey of how often each failure mode occurs.

## Quick example

Three fits of the *same* data, from different starting guesses, show that
`success` alone is necessary but not sufficient — one reports
`success=False` with the reason named, one reports `success=True` with a
negative $r^2$, and one recovers the truth from that same bad guess.

```python
--8<-- "failed_fit.py:data"
```

```python
--8<-- "failed_fit.py:build_graph"
```

The three fits differ only in the initial guess handed to `build_graph()` and,
for the last one, in the solver. Nothing about the data or the model changes.

```python
--8<-- "failed_fit.py:three_fits"
```

```python
--8<-- "failed_fit.py:inspect"
```

![Left: three fitted curves over the same peak — the global solver traces it, both lm fits lie flat at zero. Right: the same two failures with the y-axis magnified 30x, showing they are different curves.](_static/failed_fit.png)

Printed output:

```text
case         success       r^2  amplitude  |A|/max|y|  message
reported       False   -0.5252    -0.0032      0.0011  degenerate_fit (r2=-5.252e-1 < 0, peak amplitude collapsed)
silent          True   -0.5250    -0.0820      0.0273  converged_ftol
recovered       True    0.9982     2.9977      0.9988  converged_ftol
```

## Why this works

**Every other page in this gallery ends `success=True`.** That is not what
fitting is like, and a reader who only ever sees converged examples learns
nothing about how this library reports trouble — or about where its reporting
stops.

| case | outcome |
|---|---|
| `reported` | `success=False`, and the message names the reason |
| `silent` | `success=True` with $r^2 = -0.53$ — worse than a flat line |
| `recovered` | `success=True`, truth recovered, from `silent`'s own bad guess |

**The middle row is why this page exists.** `success` is necessary but not
sufficient. Read `r_squared` and the recovered parameters as well.

### Why one failure is reported and the other is not

The demotion rule is in `crates/spectrafit-solver/src/postfit.rs`. When a fit
converges with $r^2 < 0$, it is turned into a failure **only if** some free
`.amplitude` or `.height` parameter has fallen below **1% of max |y|**:

```rust
(lk.ends_with(".amplitude") || lk.ends_with(".height"))
    && final_flat.get(k).is_some_and(|&v| v.abs() / y_max_abs < 1e-2)
```

That single threshold is the entire difference between the first two rows. The
`|A|/max|y|` column straddles it — `0.0011` against `0.0273` — while $r^2$ is
identical to three decimal places. The `silent` fit converged to a narrow
*negative* Gaussian sitting at $x \approx -2.7$, about 2.7% of the true peak
height: collapsed by any ordinary reading, but above the line the guard draws.

The guard is narrow on purpose — a broad "$r^2 < 0$ means failure" rule would
misreport legitimate fits of data whose baseline the model is not asked to
describe. The consequence is still worth knowing: **a converged fit can be
arbitrarily wrong and still report `success=True`.**

## What just happened

1. **`reported` — the guard fires.** Starting at `amplitude=50, center=-3.9,
   sigma=0.05`, the fit drove the amplitude to $-0.0032$, or 0.1% of max |y|.
   Below the 1% threshold with $r^2 < 0$, so it is demoted and the message says
   `degenerate_fit`.

2. **`silent` — the guard stays quiet.** From `amplitude=3.0, center=-3.9,
   sigma=0.8` the fit settled at $-0.082$, 2.7% of max |y|. It terminated
   normally at an end point verified as stationary, so the message is the
   ordinary `converged_ftol` and `success` is `True` — with the same negative
   $r^2$.

3. **`recovered` — a different solver, not a different guess.** Handing
   `silent`'s exact starting point to `FitOptions(solver="global")` recovers
   `amplitude=2.998, center=0.298, sigma=0.801` against a planted truth of
   `3.0, 0.3, 0.8`. Local solvers descend from where they start; a bad enough
   start is a solver choice, not a data problem.

## What to check on every fit

- **`result.success`** — necessary, not sufficient: it says the solver
  stopped on a convergence test at a stationary point, not that the model or
  the basin is the right one.
- **`result.r_squared`** — a negative value means the model is doing worse
  than a horizontal line through the mean, whatever `success` says.
- **`result.message`** — distinguishes `converged_ftol` from
  `max_iterations`, `no_improvement_possible` and `degenerate_fit`. No $r^2$
  rule promotes either soft condition: `max_iterations` is never a success,
  and `no_improvement_possible` is one only when the end point is verified as
  stationary.
- **The recovered parameters themselves** — a negative amplitude on a peak
  model, or a centre outside the measured range, is a wrong answer no scalar
  score will announce for you.

## See also

- **Related examples**: [`global_optimizer.md`](global_optimizer.md) (the
  recovery used here, in its own right),
  [`bounded_fitting.md`](bounded_fitting.md) (constraining parameters so a
  fit cannot wander into this basin at all).
- **API docs**: `FitResult.success`, `FitResult.message`,
  `FitResult.r_squared`, `FitOptions.solver`.
