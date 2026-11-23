# bias-series

The serialisation-bias measurement of bias-batches, run 1000 times, each in a fresh process pinned to CPU 2, with the host state before and after every run.

| item | value |
|---|---|
| command | `scripts/bias_series.py --source <export> --n 1000 --out results/bias-series` |
| start / end (UTC) | 2026-11-23T07:24:00Z / 2026-11-23T07:37:31Z |
| wall time | 810.9 s |
| load average (1, 5, 15 min) before / after | [0.0, 0.03, 0.0] / [1.01, 0.98, 0.64] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `de80dfd0a8a1f03d90e9598d8ffee6363e94b5f7` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': None, 'OPENBLAS_NUM_THREADS': None, 'MKL_NUM_THREADS': None, 'RAYON_NUM_THREADS': None} |
| status | ok |

Notes:

- script sha256 063bb570587aab4ec51dc52c257f9e9e59506df8977a7d46d38135fcb89e35c5; bias_batches.py sha256 9ce59f94b1dbc81acc17028a0923b736b73dfb1ca2057edc22c4dc940aa6fbbc; upstream measure_audit_bias.py sha256 9f6cff2f8477e25cd666abc38164f2427552b3c952ee2ab8dd2527c31523f486
- 1000 of 1000 runs completed; failed runs: none

Files (SHA-256):

- `bias_series.json` `d72e8843fa5b99770c546de7e6d491d0b87edceb74e2d31dc1c880b8d079b594`
- `runs.jsonl` `b254283ab0c6321f4eb1e5d129db7c08d468b76e134c16bdcf4404e587c41491`

