# terra with spectrafit-core 0.1.0: comparison run, not results of record

The NIST tables regenerated on terra with the **0.1.0** PyPI wheel, on
2026-10-04, before 0.1.1 existed. They are the baseline against which the 0.1.1
build was checked: the release workflow's 0.1.1 manylinux wheel, run on the same
host with the same scripts, gave **the same 108 cells** at both tolerances and
the same `nist_head_to_head.json` apart from the wall-clock `ms` fields. The
results of record in `results/` come from the published 0.1.1.

| | |
|---|---|
| Host | terra: AMD EPYC (with IBPB), 16 cores, Linux 5.15.0-187, glibc 2.35-0ubuntu3.15 (the `host` block in `nist_table2.json` has the details) |
| spectrafit-core | 0.1.0 PyPI wheel (`manylinux_2_28_x86_64`) |
| Comparators | lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1 (scipy-openblas) |
| Scripts | `reproducibility/figures/` of spectrafit-core at GitLab commit `121db213` (the path fix and the provenance block of 0.1.1; the fitting code is that of 0.1.0) |

Compared with the cloud-sandbox run in `../cloud-xeon/` (Linux x86-64, Intel
Xeon), spectrafit-core's columns are bit-identical while lmfit and SciPy move by
up to 1.6 significant figures; compared with macOS arm64 (`../macos-m1/`),
spectrafit-core's own columns differ in the last digits as well.
