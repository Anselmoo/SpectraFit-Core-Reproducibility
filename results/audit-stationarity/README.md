# audit-stationarity

Stationarity (Gauss-Newton measure) of every endpoint of spectrafit, scipy trf and lmfit at the common tolerance, 156 cases.

| item | value |
|---|---|
| command | `audit/capture_run.py -- run --tolerance-mode common --backends spectrafit,scipy-ls-trf,lmfit --reps 5 --mc 20; audit/stationarity.py` |
| start / end (UTC) | 2026-11-17T21:54:24Z / 2026-11-17T22:26:55Z |
| wall time | 1950.6 s |
| load average (1, 5, 15 min) before / after | [2.17, 1.6, 1.3] / [1.0, 1.0, 1.01] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `1c9fe699d489c89edde2d3e793c2fe04db5d8762` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '1'} |
| status | ok |

Notes:

- capture.jsonl sha256 5afb3c65b28fd5101a92050de16824d5eb2673b1572ec0906273348e3d55328b; results.json sha256 02fabc27bbb454651df3e0b282270c5acd2115a7d130161640b4a17cd847de27 (not copied)

Files (SHA-256):

- `table.json` `e62ab9973e223909b93ccbe36fc7e68fbf9bb0c90ff4b6e3df7d25aeca09f01c`
- `table.md` `ccead87788cbef5da986b584c500fc974f858824cdb16785ee953980881dc912`

