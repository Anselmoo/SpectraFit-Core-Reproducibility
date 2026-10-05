# Apple M1 Pro, macOS arm64: comparison runs, not results of record

Two regenerations of the NIST tables with spectrafit-core **0.1.0**, made on
2026-10-03 to find out why the tables v0.1.0 archived differ from what Linux
hosts produce. They are kept for comparison; the results of record are in
`results/` and were produced on terra.

| | |
|---|---|
| Host | Apple M1 Pro, macOS 27.0.1 (arm64), CPython 3.13.12 |
| spectrafit-core | 0.1.0 PyPI wheel (`macosx_11_0_arm64`, universal2) |
| Comparators | lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1, matplotlib 3.11.2 |
| Sources | release v0.1.0 (tag commit `0c5d366e`), scripts run unmodified |

- `pypi-wheel-accelerate/`: NumPy and SciPy from their `macosx_14_0_arm64`
  wheels, which use Apple's **Accelerate** for BLAS/LAPACK.
- `openblas-variant/`: the same, but NumPy and SciPy from their
  `macosx_11_0`/`macosx_12_0` wheels, which bundle **scipy-openblas**.

A local `maturin --release` build of the v0.1.0 sources on the same machine
(with NumPy 2.5.3 from the release's own lock file) gave the same 108 cells as
`pypi-wheel-accelerate/`. Two runs in each environment were identical.

**What these runs establish.** Against the tables v0.1.0 archived (made on an
unrecorded macOS arm64 machine), `pypi-wheel-accelerate/` agrees bit for bit in
88 of the 108 cells of `nist_table2.json`: every spectrafit-core, standard
error, lmfit and SciPy `lm` cell. `nist_head_to_head.json` agrees apart from the
wall-clock `ms` fields. The 20 remaining cells are all SciPy `trf`, which calls
LAPACK on every step; Accelerate and OpenBLAS each give a different set of
values, and neither reproduces the archive's, so the LAPACK the archive was made
with is not known.

These files were written by the v0.1.0 generator and therefore carry no `host`
block; this README is their host record.
