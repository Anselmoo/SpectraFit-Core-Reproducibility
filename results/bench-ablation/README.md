# bench-ablation

Analytic (spectrafit) against finite-difference (spectrafit_fd) Jacobian, with every comparator, 160 cases.

| item | value |
|---|---|
| command | `python -m oracles.cli run --backends spectrafit,spectrafit_fd,lmfit,jax,scipy-ls-lm,scipy-ls-trf,scipy-ls-dogbox --reps 5 --mc 20` |
| start / end (UTC) | 2026-11-17T20:32:39Z / 2026-11-17T21:53:56Z |
| wall time | 4876.5 s |
| load average (1, 5, 15 min) before / after | [1.64, 1.18, 1.16] / [1.51, 1.41, 1.23] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `1c9fe699d489c89edde2d3e793c2fe04db5d8762` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '1'} |
| status | ok |

Notes:

- harness run directory (not copied, 2026-11-17_run_001): results.json sha256 206bd054480f4b313a0e14c28d3d85f1298c3016a749f2a0732fc34452b7156b

Files (SHA-256):

- `manifest.json` `5f007649cea3aaf689d4738c380bdf9df00da5225fd5a93df0e525e5b461d6f5`
- `per_case.json` `29ff0c25f22a2aec13b7339aa9c45ca790b781f5928ff448a0b8ccf8aa048b9d`
- `summary.json` `5e6e740d90b6c8a5935bc9807d386df8872e759cfcd573e0bc4e5cc202b42fdb`

