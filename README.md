# SpectraFit-Core-Reproducibility

Results and figures of the SoftwareX article on `spectrafit-core`, regenerated from
the published release, with every number stated in the article checked against the
regenerated data.

This repository is a thin, pinned **consumer** of the release. It does not contain a
copy of the benchmark suite:

| What | Where it comes from | Pinned by |
|---|---|---|
| compiled library | PyPI wheel `spectrafit-core==0.1.2` | hash in `uv.lock` |
| comparators | lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1 | `pins.toml`, `uv.lock` |
| NIST fixtures, harness, figure scripts | GitHub `Anselmoo/SpectraFit-Core` at tag `v0.1.2` | commit hash in `pins.toml` |
| timing data | measured on terra with that wheel and the tag's harness, `results/timing/` | SHA-256 in `pins.toml [timing_inputs]` |

## Run it

```bash
uv run --locked reproduce.py                 # about 10 s after the first install
uv run --locked reproduce.py --check         # regenerate elsewhere and compare; writes nothing
uv run --locked reproduce.py --source ~/path/to/SpectraFit-Core   # reuse a checkout that has the tag
```

Requirements: `uv`, `git`, network access to PyPI and GitHub on the first run.
uv installs Python 3.13 if it is missing. A checkout passed with `--source` is only
read (`git archive` of the pinned commit); its working tree is never touched.

The script stops with a non-zero exit code if the environment differs from the
pins, if an archived input does not match its SHA-256, or if a number stated in
the article no longer holds on the data.

### Why not `uvx`?

`uvx spectrafit-core` cannot do this, for two reasons that are properties of the
0.1 releases:

1. the wheel declares no console entry point, so there is nothing for `uvx` to run;
2. the wheel contains only the `spectrafit_core` package. The harness (`oracles`),
   the NIST fixtures and the figure scripts are in the repository, not in the wheel.

`uv run --locked reproduce.py` is the equivalent that works: wheel from PyPI plus
the scripts from the tag.

## What is regenerated, and what is not

**Regenerated on every run**

| Output | Article | Upstream script |
|---|---|---|
| `results/nist_table2.json` | Table 1 | `nist_table2.py` |
| `results/nist_table2_tol1e15.json` | Section 4, rerun at 1e-15 | `nist_table2.py --tolerance 1e-15` |
| `results/nist_head_to_head.json` | data behind Figure 2 | `nist_head_to_head.py` |
| `figures/figure1_architecture.{pdf,png}` | Figure 1 | `fig_architecture.py` |
| `figures/figure2_nist.{pdf,png}` | Figure 2 | `fig_nist_dual.py` |
| `figures/figure3_benchmark.{pdf,png}` | Figure 3 | `fig_benchmark_profile.py` |

**Measured on terra with spectrafit-core 0.1.2, verified by SHA-256 on every run, not re-measured on every run**
(`results/timing/`)

| File | Article |
|---|---|
| `bench_summary.json` | Section 3.2, Figure 3 (160 cases × 6 backends, repetition depth 50) |
| `ladder/ladder.json` | five repetition depths |
| `seed-sweep/sweep.json` | 50 catalogue seeds |
| `param_agreement.json` | 94 cases, 0.74 percentage points |
| `audit_bias.json` | serialisation bias, kernel parity |

The measurement took 26 hours on terra (16 cores, 6 to 7 October 2026). A wall-clock ratio
measured on another machine is a different measurement, not a reproduction of this one,
so `reproduce.py` checks the stored files against `pins.toml` and recomputes every claim
from them instead of timing again. `results/timing/README.md` says how they were measured
and how the measurement differs from the archived one.

The timing measured by `bench/` in this repository:

| Script | What it does |
|---|---|
| `bench/run_timing.sh` | the detached chain: ladder, seed sweep, summary, agreement, bias; stops at the first failure |
| `bench/seed_sweep.py`, `bench/_seed_point.py` | seed sweep over the release harness. 0.1.2 has no `--seed` / `--headline-only`, so the release's `cli.run` is called with `seed=` and `analyzed_ids=` bound |
| `bench/assemble.py` | records host and configuration before the first rung; builds `results/timing/` (schema `bench-ladder/2`, `bench-seed-sweep/1`, `bench-provenance/2`) and checks it against the archived files |
| `bench/host_snapshot.sh` | host snapshot before and after |
| `bench/compare.py` | the comparison table below |

To measure again (about 26 h on 16 cores; the export of the tag goes to `<root>/src`, see
`results/timing/README.md`):

```bash
uv sync --locked --group benchmark --group audit
tmux new -d -s timing "bash bench/run_timing.sh <root>"
```

**The 151-case archive of the release** (`results/archived/`) is still verified by SHA-256
and copied on every run. It was measured before the first release (commits `990a4c7` and
`0fd4b5d`, 15 to 17 August 2026) and is superseded for the paper.

To measure one rung on the current host and see it next to the measured value:

```bash
uv run --locked --group benchmark reproduce.py --benchmark --reps 4
```

The measured rung at `--reps 4` took 70 minutes on terra. The result is written to
`results/provenance.json` under `benchmark_on_this_host`; it never replaces the stored files.

## What a run writes

```
results/
  nist_table2.json, nist_table2_tol1e15.json, nist_head_to_head.json   regenerated
  timing/              the timing of record, measured with 0.1.2 (ladder, seed sweep,
                       summary, agreement, bias, host snapshots, provenance)
  archived/            the 151-case timing files as shipped in the release (superseded)
  release-archive/     the three NIST files as shipped in the release
  claims-report.json   every number the article states, recomputed, with pass/fail
  drift-report.json    regenerated Table 1 against the release's archived copy
  provenance.json      repository commit, host (kernel, C library, CPU flags,
                       BLAS/LAPACK built and loaded), versions, script hashes
figures/               three figures, PDF and PNG
ro-crate-metadata.json RO-Crate 1.1 description of this repository
checksums.sha256       SHA-256 of every file above
```

Every number stated in the article has an entry in `results/claims-report.json`;
the run fails when one no longer holds. Three values that legitimately differ between
hosts (the platform, the number of datasets that improve at 1e-15, the largest
drift) are read from the data rather than stated as constants.

`--check` compares result files without their wall-clock fields (`ms` in
`nist_head_to_head.json`), which change on every run. It is a same-platform test.
On a different operating system or CPU the last digits of the fits differ, so
`--check` reports a difference there; the criterion across platforms is
`claims-report.json`.

## Where the results are produced

The results of record are produced on **terra**, a dedicated 16-core Linux
machine (AMD EPYC, Ubuntu 22.04) that is independent of the machines on which
spectrafit-core is developed and tested: it is not a CI runner and not a
developer's laptop, and it runs no other benchmark during a measurement (see
`results/timing/README.md` for what else was present). The timing of record was
measured on terra on 6 and 7 October 2026, and the NIST tables shipped since the 0.1.1
release were generated there too, so accuracy and speed come from one machine.

- `host/` holds snapshots of terra before and after its package update (kernel,
  glibc, CPU, installed packages, tool versions); `results/provenance.json`
  records kernel, C library, CPU features and the BLAS/LAPACK loaded for every run,
  and `results/timing/host/` holds snapshots taken before and after the timing
  measurement.
- The timing of record (`results/timing/`) was measured on terra with the published
  0.1.2 wheel and the v0.1.2 harness, from 6 October 2026 07:24 UTC to 7 October
  09:30 UTC, at the repetition depths, `--mc` and seeds of the archived run.
- The JAX backend runs with the compile budget of 0.1.2 (64, its default). Without the
  budget the JAX backend runs out of memory mappings on terra (`vm.max_map_count`
  65530): a one-rung check with the 0.1.1 release aborted after 58 minutes (`LLVM
  ERROR: Unable to allocate section memory`).
- `results/other-hosts/` keeps runs on other machines for comparison; they are not
  the results of record. Each has its own `README.md`.

## Timing: archive against measurement

The archived timing (151 cases, pre-release commit `990a4c7`, August 2026) next to
the measurement of record (160 cases, release 0.1.2, October 2026), computed the same
way by `bench/compare.py`:

| | 151 cases, `990a4c7`, Aug 2026 (archived) | 160 cases, 0.1.2, Oct 2026 (of record) |
|---|---|---|
| cases | 151 | 160 |
| categories | 9 | 10 |
| geometric-mean speed-up vs lmfit | 16.45 | 16.75 |
| harmonic-mean speed-up vs lmfit | 13.78 | 13.75 |
| largest \|Δr²\| | 1.28e-04 | 1.29e-04 |
| spectrafit-core win rate (gate) | 88.1 % | 87.5 % |
| regressions | 0 | 0 |
| fastest backend on | 131 of 151 | 140 of 160 |
| categories where it is not fastest | optfn | optfn |
| headline without optfn | 15.14 | 15.71 |
| factor vs jax | 4.94 | 5.30 |
| factor vs scipy-ls-lm | 6.25 | 7.07 |
| factor vs scipy-ls-trf | 7.92 | 8.96 |
| factor vs scipy-ls-dogbox | 6.49 | 7.50 |
| category complex | 23.99 (35) | 24.84 (35) |
| category easy | 12.72 (20) | 14.37 (20) |
| category edge | 14.34 (20) | 16.33 (20) |
| category fixed | 10.03 (4) | 12.14 (4) |
| category lineshapes | 8.85 (24) | 10.07 (27) |
| category optfn | 28.32 (20) | 26.29 (20) |
| category reality | 17.87 (16) | 19.58 (16) |
| category robust | — | 5.64 (6) |
| category scaling | 16.31 (8) | 17.42 (8) |
| category tied | 14.12 (4) | 14.91 (4) |
| depth 2 (--reps 4) | 15.97 | 16.33 |
| depth 5 (--reps 10) | 15.78 | 16.31 |
| depth 10 (--reps 20) | 16.16 | 16.46 |
| depth 25 (--reps 50) | 16.36 | 16.50 |
| depth 50 (--reps 100) | 16.45 | 16.75 |
| seeds | 50 | 50 |
| seed mean ± sd | 15.95 ± 0.38 | 16.30 ± 0.41 |
| seed range | 15.08 to 16.67 | 15.54 to 17.55 |
| agreement: cases on all six / with truth | 127 / 124 | 136 / 131 |
| agreement: well-conditioned cases | 93 | 94 |
| agreement: max cross-backend spread | 0.23 pp | 0.74 pp |
| agreement: excluded stratum | 31 | 37 |
| bias: wheel per evaluation | 74.9 µs | 139.2 µs |
| bias: NumPy per evaluation | 2.97 µs | 6.72 µs |
| bias: ratio | 25.3 | 20.7 |
| parity: kernels / exact / largest | 35 / 23 / 4.59e-07 | 35 / 23 / 4.59e-07 |

The two columns are compared, not equated. The case sets differ, and so do the
library build and the harness version: 0.1.2 adds three line-shape cases and the six
`robust` cases. Two rows moved by more than the case set alone explains:

- **The serialisation bias** (`audit_bias.json`) is measured by the same script. The
  release's `measure_audit_bias.py` equals the one that wrote the archived file
  (spectrafit-core `0bf1bef`) apart from comments and its repository-depth fix. Both
  terms roughly doubled: 74.9 → 139.2 µs through the wheel and 2.97 → 6.72 µs in
  plain NumPy, so the ratio fell from 25 to 21. Two independent readings with 0.1.2
  on terra agree (139.2 µs). The archived file names no host. The cause is not
  established; the paper uses the 0.1.2 value.
- **The largest cross-backend spread** of the parameter agreement rose from 0.23 to
  0.74 percentage points on 94 well-conditioned cases (93 before).

Every number the article states is recomputed from `results/timing/` in
`results/claims-report.json`.

## FAIR

| | How |
|---|---|
| Findable | software DOI `10.5281/zenodo.23043544`; tag and commit in `pins.toml`; `ro-crate-metadata.json` lists every file with size, digest and description |
| Accessible | wheel from PyPI, source from GitHub, both by open protocols; no credentials |
| Interoperable | JSON results, PDF and PNG figures, RO-Crate 1.1 metadata |
| Reusable | MIT licence (`LICENSE`); `provenance.json` records host, versions and script hashes; `uv.lock` fixes the environment; `checksums.sha256` verifies with `sha256sum -c`; `CITATION.cff` |

Each GitHub release of this repository is archived on Zenodo, which assigns it a DOI
of its own; `CITATION.cff` says how to cite it together with the spectrafit-core release.

## spectrafit-core 0.1.0, 0.1.1 and why this repository is pinned to 0.1.2

Two defects of the 0.1.0 release surfaced when its results were regenerated, and
both are fixed in 0.1.1:

1. **The archived NIST tables were not what other hosts produce.** 0.1.0 shipped
   tables made on macOS arm64 that recorded no host. Regenerated on Linux x86-64,
   38 of the 108 cells of Table 1 differed by 0.05 significant figures or more. The
   difference is a property of the platform, not of the code: the same release
   reproduces the archived spectrafit-core, standard-error, lmfit and SciPy `lm`
   columns bit for bit on an Apple M1 (`results/other-hosts/macos-m1/`). 0.1.1
   ships tables made on terra, the host of record of this repository, with a
   `host` block naming the platform, C library, CPU features and BLAS/LAPACK; the
   macOS tables are kept in the release under
   `reproducibility/figures/comparison/macos-arm64/`.
2. **Three figure scripts looked for the repository root one directory too high**
   (`fig_architecture.py`, `extract_bench_summary.py`, `measure_audit_bias.py`), so
   Figures 1 and 2 could not be redrawn from a plain checkout of the 0.1.0 tag. In
   0.1.1 they find it, and `reproduce.py` runs the release's scripts in the
   release's own layout, unmodified.

With 0.1.1, `results/drift-report.json` compares the regenerated Table 1 with the
copy archived in the release; on the host of record the two agree in every cell.

0.1.2 changes only the benchmark harness and the version metadata: it releases
the JAX compile budget described above, so `--benchmark` completes on terra. The
library sources and every file under `reproducibility/` (NIST tables and timing
archives) are identical to 0.1.1.
