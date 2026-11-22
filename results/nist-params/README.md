# nist-params

NIST StRD, 22 datasets, Start 2, shipped tolerance: fitted parameter values of SpectraFit-Core and lmfit next to the certified values and standard deviations, fitted as the release's nist_table2.py fits them.

| item | value |
|---|---|
| command | `scripts/nist_params.py --source <export> --out results/nist-params` |
| start / end (UTC) | 2026-11-22T20:06:36Z / 2026-11-22T20:06:37Z |
| wall time | 1.1 s |
| load average (1, 5, 15 min) before / after | [0.2, 0.4, 0.43] / [0.26, 0.41, 0.43] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `b42714df60d7cc1d40791e4eff040b0f4294227b` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '1'} |
| status | ok |

Notes:

- results/nist_table2.json sha256 at run time fa958c4cdaf7b8253a8a0f029dc759d057fa2a15e1e9639ae7d13395395ae75b
- script sha256 f3ebaa0f3371aaccc5b6ef60d497ef4dce395ce224eccce62a1a41bdf07bda35; upstream nist_table2.py sha256 e6fe80473306525bffd404f5f32a034820a83d0944483de6d25d1bebb1b617ad
- guard: the worst LRE of both libraries, recomputed from the stored values with the release's worst_lre, equals the spectrafit_core and lmfit columns of results/nist_table2.json cell for cell; the script writes nist_params.json only if it does

Files (SHA-256):

- `nist_params.json` `bb55b21d10747104cc888ad115dd75c33cb60ae52bc6321e5bbd0b93ab413d19`

