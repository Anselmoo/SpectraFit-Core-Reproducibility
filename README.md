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
| timing data | the same tag, `reproducibility/` | SHA-256 in `pins.toml` |

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

**Taken from the release archive, verified by SHA-256, not re-measured**
(`results/archived/`)

| File | Article |
|---|---|
| `bench_summary.json` | Section 3.2, Figure 3 |
| `ladder.json` | five repetition depths |
| `sweep.json` | 50 seeds |
| `param_agreement.json` | 93 cases, 0.23 percentage points |
| `audit_bias.json` | serialisation bias, kernel parity |

The reason is cost and meaning, not convenience. The archived ladder took about
17 hours on a 16-core host (`terra`, AMD EPYC, Linux x86-64, 15 to 16 August 2026,
commit `990a4c7`). A wall-clock ratio measured on a laptop is a different
measurement, not a reproduction of that one. To measure one rung on the current
host and see it next to the archived value:

```bash
uv run --locked --group benchmark reproduce.py --benchmark --reps 4
```

The archived run at `--reps 4` took 77 minutes on 16 cores. The result is written
to `results/provenance.json` under `benchmark_on_this_host`; it never replaces the
archived files.

## What a run writes

```
results/
  nist_table2.json, nist_table2_tol1e15.json, nist_head_to_head.json   regenerated
  archived/            the five timing files, as shipped in the release
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
developer's laptop, and it runs nothing else during a measurement. The archived
timing benchmark was measured on terra on 15 and 16 August 2026, and the NIST
tables shipped since the 0.1.1 release were generated there too, so accuracy and speed come
from one machine.

- `host/` holds snapshots of terra before and after its package update (kernel,
  glibc, CPU, installed packages, tool versions); `results/provenance.json`
  records kernel, C library, CPU features and the BLAS/LAPACK loaded for every run.
- The timing benchmark is **not repeated**. The archived measurement is taken from
  the release and verified by SHA-256; `--benchmark` adds one rung measured with
  the release build, recorded next to the archived value for comparison only.
- The archived timing run was made at spectrafit-core commit `990a4c7`, on a branch
  that caps the number of functions the JAX backend keeps compiled (`compile_budget`
  64). The cap was not part of 0.1.0 or 0.1.1: without it the JAX backend runs out
  of memory mappings on terra (`vm.max_map_count` 65530), and a one-rung check with
  the 0.1.1 release aborted after 58 minutes (`LLVM ERROR: Unable to allocate
  section memory`). The cap was released in 0.1.2, which this repository pins, and
  it lives only in the JAX backend; the other five backends do not use it.
- The rung measured with the 0.1.2 release on terra (`results/provenance.json`,
  `benchmark_on_this_host`, run `2026-10-05_run_001`) next to the archived rung at the same
  `--reps 4`:

  | | cases | geometric-mean speed-up | harmonic-mean speed-up | largest \|Δr²\| | spectrafit-core wins | regressions |
  |---|---|---|---|---|---|---|
  | archived, `990a4c7`, 15 Aug 2026 | 151 | 15.97× | 13.11× | 1.28e-04 | 88.1 % | 0 |
  | 0.1.2 release | 160 | 16.24× | 13.33× | 1.29e-04 | 87.5 % | 0 |

  The case sets differ: the harness released in 0.1.2 generates 160 cases
  where the archived run had 151, so the two rows are compared, not
  equated. The article's timing numbers are the archived ones.
- `results/other-hosts/` keeps runs on other machines for comparison; they are not
  the results of record. Each has its own `README.md`.

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
