# bench-tolerance

160 cases x 6 backends at the default and at the common stopping tolerance.

| item | value |
|---|---|
| command | `bench/common_tolerance.py run --mode default|common --reps 5; analyse` |
| start / end (UTC) | 2026-11-17T20:02:16Z / 2026-11-17T20:32:38Z |
| wall time | 1821.6 s |
| load average (1, 5, 15 min) before / after | [1.64, 1.42, 1.42] / [1.64, 1.18, 1.16] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `1c9fe699d489c89edde2d3e793c2fe04db5d8762` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '1'} |
| status | ok |

Notes:

- records: default.json, common.json, summary.json, report.md

Files (SHA-256):

- `common.json` `a61afc44bf6f577a64565e0a0ac234670c4c430875b5b346ca28990b903fa34e`
- `default.json` `80188c9f966ac8f810300fb04a179fa9c60bd17b25115a97434d7aa2787e3094`
- `report.md` `7b28eea8f7ce379466187fff3c75a01c119a5de16be79079883a5e8c1098a4e5`
- `summary.json` `132a32c5d10ebad7a26f9d08694e3cd7cce39bd2b64cfce68854ab9a6a563680`

