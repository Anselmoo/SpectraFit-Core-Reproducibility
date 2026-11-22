# bias-batches

Serialisation bias (gaussian, 97 points): every one of the 7 timed batches of the NumPy path (2000 evaluations each) and of the wheel path (200 each), with the per-evaluation values derived as measure_audit_bias.py derives them.

| item | value |
|---|---|
| command | `scripts/bias_batches.py --source <export> --out results/bias-batches` |
| start / end (UTC) | 2026-11-22T20:42:40Z / 2026-11-22T20:42:41Z |
| wall time | 0.9 s |
| load average (1, 5, 15 min) before / after | [0.0, 0.15, 0.47] / [0.0, 0.15, 0.47] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `ac585202fa931f37e5c683725ffedcd6252cc8ff` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': None, 'OPENBLAS_NUM_THREADS': None, 'MKL_NUM_THREADS': None, 'RAYON_NUM_THREADS': None} |
| status | ok |

Notes:

- script sha256 9ce59f94b1dbc81acc17028a0923b736b73dfb1ca2057edc22c4dc940aa6fbbc; upstream measure_audit_bias.py sha256 9f6cff2f8477e25cd666abc38164f2427552b3c952ee2ab8dd2527c31523f486
- timed: run on a quiet host; load and the /proc/stat cpu line before and after each side are in bias_batches.json (steal is the 8th field)

Files (SHA-256):

- `bias_batches.json` `8c3980d76b56aefcdb9e51ab5ba037402eb5b48caa41065544467fc920ba7964`

