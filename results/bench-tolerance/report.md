# Common-tolerance preview: speed-up of spectrafit per comparator

- default: tolerances None, reps 5, wall 15.1 min, spectrafit-core 0.1.3 (None), host terra
- common: tolerances {'ftol': 1e-08, 'xtol': 1e-08, 'gtol': 1e-08}, reps 5, wall 15.2 min, spectrafit-core 0.1.3 (None), host terra

| mode | comparator | scope | cases | n | geomean | median |
|---|---|---|---|---|---|---|
| default | jax | all | all_cases | 136 | 4.48 | 4.38 |
| default | jax | all | like_for_like | 122 | 4.67 | 4.42 |
| default | jax | without_optfn | all_cases | 136 | 4.48 | 4.38 |
| default | jax | without_optfn | like_for_like | 122 | 4.67 | 4.42 |
| default | lmfit | all | all_cases | 160 | 14.1 | 13.5 |
| default | lmfit | all | like_for_like | 136 | 13.4 | 13 |
| default | lmfit | without_optfn | all_cases | 140 | 12.9 | 12.9 |
| default | lmfit | without_optfn | like_for_like | 131 | 13.2 | 13 |
| default | scipy-ls-dogbox | all | all_cases | 156 | 6.34 | 9.51 |
| default | scipy-ls-dogbox | all | like_for_like | 135 | 7.46 | 9.79 |
| default | scipy-ls-dogbox | without_optfn | all_cases | 136 | 10.3 | 10.1 |
| default | scipy-ls-dogbox | without_optfn | like_for_like | 126 | 9.91 | 10.1 |
| default | scipy-ls-lm | all | all_cases | 156 | 6.25 | 8.68 |
| default | scipy-ls-lm | all | like_for_like | 132 | 8.13 | 9.23 |
| default | scipy-ls-lm | without_optfn | all_cases | 136 | 9.83 | 9.32 |
| default | scipy-ls-lm | without_optfn | like_for_like | 127 | 9.46 | 9.36 |
| default | scipy-ls-trf | all | all_cases | 156 | 7.65 | 10.9 |
| default | scipy-ls-trf | all | like_for_like | 135 | 9.43 | 11.1 |
| default | scipy-ls-trf | without_optfn | all_cases | 136 | 12 | 11.3 |
| default | scipy-ls-trf | without_optfn | like_for_like | 127 | 11.8 | 11.4 |
| common | jax | all | all_cases | 136 | 4.43 | 4.25 |
| common | jax | all | like_for_like | 122 | 4.62 | 4.53 |
| common | jax | without_optfn | all_cases | 136 | 4.43 | 4.25 |
| common | jax | without_optfn | like_for_like | 122 | 4.62 | 4.53 |
| common | lmfit | all | all_cases | 160 | 14.2 | 13.6 |
| common | lmfit | all | like_for_like | 137 | 13.7 | 13.2 |
| common | lmfit | without_optfn | all_cases | 140 | 13 | 13.1 |
| common | lmfit | without_optfn | like_for_like | 132 | 13.4 | 13.1 |
| common | scipy-ls-dogbox | all | all_cases | 156 | 6.43 | 9.8 |
| common | scipy-ls-dogbox | all | like_for_like | 135 | 7.62 | 10.1 |
| common | scipy-ls-dogbox | without_optfn | all_cases | 136 | 10.4 | 10.4 |
| common | scipy-ls-dogbox | without_optfn | like_for_like | 126 | 10.1 | 10.4 |
| common | scipy-ls-lm | all | all_cases | 156 | 6.37 | 8.84 |
| common | scipy-ls-lm | all | like_for_like | 132 | 8.31 | 9.74 |
| common | scipy-ls-lm | without_optfn | all_cases | 136 | 9.97 | 9.83 |
| common | scipy-ls-lm | without_optfn | like_for_like | 127 | 9.67 | 10 |
| common | scipy-ls-trf | all | all_cases | 156 | 7.67 | 11 |
| common | scipy-ls-trf | all | like_for_like | 135 | 9.53 | 11.4 |
| common | scipy-ls-trf | without_optfn | all_cases | 136 | 12 | 11.7 |
| common | scipy-ls-trf | without_optfn | like_for_like | 127 | 11.9 | 11.8 |

## Termination reasons per backend and mode

| mode | backend | reason | n |
|---|---|---|---|
| default | jax | optimistix._solution.RESULTS<> | 130 |
| default | jax | optimistix._solution.RESULTS<The maximum number of steps was reached in the nonlinear solv | 6 |
| default | lmfit | Fit succeeded. | 139 |
| default | lmfit | Fit succeeded. Could not estimate error-bars. | 1 |
| default | lmfit | Optimization terminated successfully. | 20 |
| default | scipy-ls-dogbox | status=0: The maximum number of function evaluations is exceeded. | 2 |
| default | scipy-ls-dogbox | status=1: `gtol` termination condition is satisfied. | 7 |
| default | scipy-ls-dogbox | status=2: `ftol` termination condition is satisfied. | 139 |
| default | scipy-ls-dogbox | status=3: `xtol` termination condition is satisfied. | 5 |
| default | scipy-ls-dogbox | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 3 |
| default | scipy-ls-lm | status=0: The maximum number of function evaluations is exceeded. | 3 |
| default | scipy-ls-lm | status=1: `gtol` termination condition is satisfied. | 3 |
| default | scipy-ls-lm | status=2: `ftol` termination condition is satisfied. | 145 |
| default | scipy-ls-lm | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 5 |
| default | scipy-ls-trf | status=1: `gtol` termination condition is satisfied. | 6 |
| default | scipy-ls-trf | status=2: `ftol` termination condition is satisfied. | 146 |
| default | scipy-ls-trf | status=3: `xtol` termination condition is satisfied. | 2 |
| default | scipy-ls-trf | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 2 |
| default | spectrafit | converged_ftol | 160 |
| common | jax | optimistix._solution.RESULTS<> | 130 |
| common | jax | optimistix._solution.RESULTS<The maximum number of steps was reached in the nonlinear solv | 6 |
| common | lmfit | Fit succeeded. | 132 |
| common | lmfit | Fit succeeded. Could not estimate error-bars. | 1 |
| common | lmfit | One or more variable did not affect the fit. | 7 |
| common | lmfit | Optimization terminated successfully. | 20 |
| common | scipy-ls-dogbox | status=0: The maximum number of function evaluations is exceeded. | 2 |
| common | scipy-ls-dogbox | status=1: `gtol` termination condition is satisfied. | 7 |
| common | scipy-ls-dogbox | status=2: `ftol` termination condition is satisfied. | 139 |
| common | scipy-ls-dogbox | status=3: `xtol` termination condition is satisfied. | 5 |
| common | scipy-ls-dogbox | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 3 |
| common | scipy-ls-lm | status=0: The maximum number of function evaluations is exceeded. | 3 |
| common | scipy-ls-lm | status=1: `gtol` termination condition is satisfied. | 3 |
| common | scipy-ls-lm | status=2: `ftol` termination condition is satisfied. | 145 |
| common | scipy-ls-lm | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 5 |
| common | scipy-ls-trf | status=1: `gtol` termination condition is satisfied. | 6 |
| common | scipy-ls-trf | status=2: `ftol` termination condition is satisfied. | 146 |
| common | scipy-ls-trf | status=3: `xtol` termination condition is satisfied. | 2 |
| common | scipy-ls-trf | status=4: Both `ftol` and `xtol` termination conditions are satisfied. | 2 |
| common | spectrafit | converged_ftol | 160 |
