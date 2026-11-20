# Analysis scripts taken over from the spectrafit-core verification

Copied byte for byte from the release-candidate verification of spectrafit-core 0.1.3, which is not
published, where they were written and run. Their definitions (thresholds, measures, rules) are
unchanged; each SHA-256 below equals the one of the source file.

| file here | SHA-256 |
|---|---|
| `audit/capture_run.py` | `3ea1caa3f172dfe77c400091ba5901bc95a3bd0c0bd3d1fe2427c9db3ec4fdc5` |
| `audit/stationarity.py` | `8ebcf18ca4b41c499caa8b813948724f1bac9ae698ad523554de8a90a617ba22` |
| `bench/ablation_summary.py` | `57c7c4b86838a349c0828c73ffec0f6e934ae729223313895e0ef382b479acb0` |
| `bench/common_tolerance.py` | `efb7a97cc14516ca3e5ca83b9986c70ac4274ad7fc77920a1c946ae3379ca697` |

`audit/stationarity.py` is the variant that constructs the spectrafit backend as `SpectraFitBackend(tolerances=tol)`,
the keyword the 0.1.3 harness requires; the earlier variant passed the tolerances positionally. Nothing else differs.
