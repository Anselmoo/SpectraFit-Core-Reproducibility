# 07 fallback comparison: spectrafit (fallback build) vs scipy trf vs lmfit

Common case set: 156 cases (excluded: 4).
Tolerance mode `common` (ftol = xtol = gtol = 1e-8 where the backend has the test).

## Stationarity (stationary / n)

| backend | free | at bound | zero RSS |
|---|---|---|---|
| spectrafit | 128/139 | 17/17 | 0 |
| scipy-ls-trf | 137/148 | 6/8 | 0 |
| lmfit | 144/149 | 7/7 | 0 |

## RSS ratio RSS_backend / min over the three

| backend | median | p90 | max | at min (1e-6 rel) |
|---|---|---|---|---|
| spectrafit | 1 | 1.035 | 14.67 | 134/156 |
| scipy-ls-trf | 1 | 1 | 3.576 | 143/156 |
| lmfit | 1 | 1 | 1.76 | 152/156 |

| pair | median | < 1 | = 1 | > 1 |
|---|---|---|---|---|
| spectrafit/scipy-ls-trf | 1 | 7 | 135 | 14 |
| spectrafit/lmfit | 1 | 2 | 133 | 21 |

## Iterations and evaluations (median [p25, p75])

| backend | accepted steps | nfev | njev |
|---|---|---|---|
| spectrafit | 5 [4, 6] (n=156) | 6 [5, 7] (n=156) | 5 [4, 6] (n=156) |
| scipy-ls-trf | 5 [4, 10.25] (n=156) | 6 [5, 11.25] (n=156) | 6 [5, 11.25] (n=156) |
| lmfit | 95.5 [68.75, 106.5] (n=20) | 53 [21, 133.5] (n=156) | - |

## Success flag x stationary

| backend | flag | S+st | S+non-st | F+st | F+non-st |
|---|---|---|---|---|---|
| spectrafit | lib_success | 144 | 6 | 1 | 5 |
| spectrafit | harness_success | 144 | 6 | 1 | 5 |
| scipy-ls-trf | lib_success | 143 | 13 | 0 | 0 |
| scipy-ls-trf | harness_success | 143 | 13 | 0 | 0 |
| lmfit | lib_success | 151 | 5 | 0 | 0 |
| lmfit | harness_success | 151 | 5 | 0 | 0 |

## Same case set, split by category

| part | n | backend | free st/n | at-bound st/n | RSS ratio median | at min |
|---|---|---|---|---|---|---|
| robust | 6 | spectrafit | 0/6 | 0/0 | 1.027 | 0/6 |
| robust | 6 | scipy-ls-trf | 6/6 | 0/0 | 1 | 6/6 |
| robust | 6 | lmfit | 6/6 | 0/0 | 1 | 6/6 |
| optfn | 20 | spectrafit | 5/5 | 15/15 | 1.323 | 5/20 |
| optfn | 20 | scipy-ls-trf | 8/15 | 3/5 | 1.065 | 9/20 |
| optfn | 20 | lmfit | 15/15 | 5/5 | 1 | 17/20 |
| other | 130 | spectrafit | 123/128 | 2/2 | 1 | 129/130 |
| other | 130 | scipy-ls-trf | 123/127 | 3/3 | 1 | 128/130 |
| other | 130 | lmfit | 123/128 | 2/2 | 1 | 129/130 |

## Excluded cases

| case | category | reasons |
|---|---|---|
| TI-001 | tied | scipy-ls-trf: no end point (unsupported or raised) |
| TI-002 | tied | scipy-ls-trf: no end point (unsupported or raised) |
| TI-003 | tied | scipy-ls-trf: no end point (unsupported or raised) |
| TI-004 | tied | scipy-ls-trf: no end point (unsupported or raised) |

## Checks

- results.json vs capture: {'checked': True, 'n': 468, 'missing': 0, 'success_mismatch': 0, 'red_chi2_mismatch': 0}
- suite vs analysed phase RSS: {'spectrafit': {'n': 156, 'max_rel_diff': 0.0, 'max_rel_rss_recompute_vs_outcome_chi2': 5.30679190603952e-15}, 'scipy-ls-trf': {'n': 156, 'max_rel_diff': 0.0, 'max_rel_rss_recompute_vs_outcome_chi2': 4.388074608555589e-16}, 'lmfit': {'n': 156, 'max_rel_diff': 0.0, 'max_rel_rss_recompute_vs_outcome_chi2': 3.8933124006240785e-16}}
