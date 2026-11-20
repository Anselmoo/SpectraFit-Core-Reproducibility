# interop-fe-l23

Fe L2,3 constrained model, one graph JSON file, fitted by SpectraFit-Core and by lmfit (the release's graph_to_lmfit.py translation).

| item | value |
|---|---|
| command | `reproducibility/interop/fe_l23_lmfit.py --out results/interop-fe-l23` |
| start / end (UTC) | 2026-11-20T16:20:25Z / 2026-11-20T16:20:37Z |
| wall time | 11.7 s |
| load average (1, 5, 15 min) before / after | [0.59, 0.74, 0.59] / [0.66, 0.75, 0.6] |
| host | terra (Linux-5.15.0-203-generic-x86_64-with-glibc2.35, 16 cores) |
| archive commit | `dc5bdd01a5f967b68a8bbdac6a564b673cef3188` (working tree modified) |
| Python | 3.13.13 |
| spectrafit-core | 0.1.3 |
| wheel SHA-256 | `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43` (uv.lock) |
| compiled extension SHA-256 | `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd` |
| thread caps | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'RAYON_NUM_THREADS': '1'} |
| status | ok |

Notes:

- upstream script sha256 021290dae088f74b2aabaad12ff2bc69ab5aa880053f6b5e25c37758aa8238c8; translator sha256 057bd9228b0a70f9741537ef2aa9bd172314ddbb5c52ab3911f107a46dd1316c; graph sha256 1b73d27c9aa218ef8339d4e96c00a79654ed4759dc337e16864ef43eb3d907be
- header.git_commit and header.git_dirty in fe_l23_lmfit.json are this archive's commit and state: the release export in .cache/work has no .git, so the script's git call resolves to the enclosing repository; the release commit is pins.toml [source]
- compared with the reference run of 20 Nov 2026 (cloud sandbox, Ubuntu 24.04.5, x86_64, same uv.lock and compiled extension): 12 of 20 quantities identical
- sfc.termination.success: identical (this run True, reference True)
- sfc.termination.message: identical (this run 'converged_ftol', reference 'converged_ftol')
- sfc.rss: identical (this run 22377890.07972057, reference 22377890.07972057)
- sfc.termination.nfev: identical (this run 90, reference 90)
- sfc.termination.njev: identical (this run 64, reference 64)
- sfc.stationarity.stationary: identical (this run True, reference True)
- sfc.stationarity.gn_decrease_rel: DIFFERS (this run 3.6171712122092596e-07, reference 3.6171712122110617e-07)
- sfc.stationarity.active: identical (this run {'l2_c.center': 'lower'}, reference {'l2_c.center': 'lower'})
- lmfit.termination.success: identical (this run True, reference True)
- lmfit.termination.message: identical (this run 'Fit succeeded.', reference 'Fit succeeded.')
- lmfit.rss: DIFFERS (this run 22377891.325548954, reference 22377892.949173372)
- lmfit.termination.nfev: DIFFERS (this run 4116, reference 3619)
- lmfit.stationarity.stationary: identical (this run True, reference True)
- lmfit.stationarity.gn_decrease_rel: DIFFERS (this run 4.3824083698809056e-07, reference 6.685595510085018e-07)
- lmfit.stationarity.active: identical (this run {'l2_c.center': 'lower'}, reference {'l2_c.center': 'lower'})
- comparison.rss_rel_diff: DIFFERS (this run 5.567228984648028e-08, reference 1.282271380536494e-07)
- comparison.param_rel_diff_max: DIFFERS (this run 0.0005492796410993442, reference 0.00041647585229427766)
- comparison.param_rel_diff_argmax: DIFFERS (this run 'l3_a.amplitude', reference 'l3_e.sigma')
- sfc.model_gap_lmfit_vs_engine (3 digits): DIFFERS (this run 4.6833141576503374e-17, reference 1.87e-16)
- lmfit.model_gap_lmfit_vs_engine (3 digits): identical (this run 1.8733269799123812e-16, reference 1.87e-16)

Files (SHA-256):

- `fe_l23_lmfit.json` `1278cad81cd0852a3763750380d5733655cdffe5373ce5d888b621fa9822f698`
- `fe_l23_side_by_side.txt` `74e63002e991f92562adb789ad7c7b850d2a58a9962be15e9d97b15ed939018c`
