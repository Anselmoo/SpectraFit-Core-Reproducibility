# Timing of record: spectrafit-core 0.1.2 on terra, 160 cases

The timing benchmark of the paper, measured on terra from 6 October 2026 07:24 UTC to
7 October 2026 09:30 UTC (26 h). It used:

- **the compiled library:** the published PyPI wheel `spectrafit-core==0.1.2`,
  hash-pinned in `uv.lock`. No source build, no target-cpu flags.
- **the harness:** v0.1.2 at commit `1e304188a7376caf128fcb432a16554ed44ad32a`.
  - It was exported with `git archive`, as the paths `scripts/bench_ladder.py`,
    `python/oracles`, `reproducibility`, `tests/parity`, `crates` and `Cargo.toml`.
  - The export lies outside any git work tree, and its `python/` holds only `oracles`.
    The wheel is therefore what gets imported; every step checked that.
- **the comparators at their locked versions:** lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1,
  JAX and jaxlib 0.11.0, optimistix 0.1.0, Python 3.13.13.
- **library defaults only:**
  - all thread variables and `XLA_FLAGS`, `JAX_PLATFORMS` and
    `SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET` were unset;
  - the JAX compile budget was 64, the 0.1.2 default;
  - `vm.max_map_count` was 65530.

Nothing was tuned on a result. The depths, `--mc` and the seeds are those of the archived
run, read from its records.

## How it was run

`bench/run_timing.sh` ran in a detached tmux session. It held the host's benchmark lock
(`~/.cache/terra-bench.lock`) and stopped at the first non-zero exit. Every step exited 0.

| step | command | wall time |
|---|---|---|
| 0 | `bench/assemble.py capture`: host fields, catalogue fingerprint, backend support | seconds |
| 1–5 | the release's `scripts/bench_ladder.py --ladder R --mc 8`, unmodified, once per R = 4, 10, 20, 50, 100 | 70, 90, 123, 225, 393 min |
| 6 | `bench/seed_sweep.py`: seeds 20260603…20260652, `--reps 10`, `--mc 8`, headline-only | 11.1 h |
| 7 | the release's `extract_bench_summary.py` on the reps-100 run (`2026-10-07_run_005`) | seconds |
| 8 | the release's `measure_param_agreement.py` | seconds |
| 9 | the release's `measure_audit_bias.py` | seconds |
| 10 | host snapshot after | seconds |

`provenance.json` records:

- every step with its command, start, end, exit code and the load average before and
  after;
- the preflight readings;
- the SHA-256 of every exported file and of the drivers in `bench/`.

`host/before.txt` and `host/after.txt` are full host snapshots: kernel, glibc, CPU, the
installed packages, the wheel's digest and the apt timers.

## Layout

```
ladder/ladder.json                       bench-ladder/2: environment, methodology, config, five rungs
ladder/rungs/rung_{002,005,010,025,050}/ one directory per repetition depth (effective reps)
seed-sweep/sweep.json                    bench-seed-sweep/1: the same blocks, fifty seeds
seed-sweep/rungs/seed_<seed>/            one directory per catalogue seed
  manifest.json, trust.json              as the harness wrote them
  provenance.json                        bench-provenance/2 record of that run
  results.json.gz, audit.json.gz         the full payloads, gzip without name or timestamp;
                                         provenance.json lists the SHA-256 of the uncompressed files
  run.log                                console output of the run
bench_summary.json                       Figure 3 and the bench- claims
param_agreement.json                     agree-01
audit_bias.json                          bias-01, bias-02
```

## Differences from the archived 151-case measurement

The archived measurement is in `results/archived/` (ladder at `990a4c7`, sweep at
`0fd4b5d`, 15 to 17 August 2026). The following differences could not be avoided:

1. **Catalogue: 160 cases instead of 151.** The `lineshapes` category has 27 cases
   instead of 24, and the `robust` category (6 cases) is new. The catalogue fingerprints
   therefore differ.
2. **Library:** the 0.1.2 PyPI wheel instead of a 0.1.0 build of commit `990a4c7`.
3. **Harness:** v0.1.2 instead of the unreleased commits.
   - `Backend.solver_settings()` was removed in 0.1.2, so `config.solvers.<backend>`
     carries only `version`. The archive's `library`, `algorithm`, `bounds`, `stopping`
     and `runtime` are null here; they are listed in `provenance.json`
     (`null_fields`) and are not copied from the archive.
   - The `methodology` block is the archive's text. Each sentence was checked against the
     v0.1.2 code.
4. **Host:** kernel 5.15.0-187 instead of 186; glibc 2.35-0ubuntu3.15 instead of 3.14,
   with the libm machine code unchanged (see `host/terra-after-update.txt` at the top of
   this repository).
5. **Ladder records:**
   - The release's `bench_ladder.py` writes schema `bench-ladder/1` and was run once per
     depth, so that a failure stops the chain. `bench/assemble.py` builds the schema-2
     records from its output.
   - `environment.git` names the export's commit, because the export has no `.git` and
     the driver recorded an empty commit.
   - The thread variables, CPU flags and cgroup fields come from step 0.
   - The load averages come from the chain's own readings.
   - `params.catalog_fingerprint_sha256` was added to the ladder records; the archive
     has it on the sweep only.
6. **Seed sweep:** the archive's driver (`scripts/bench_ladder.py --seeds 50
   --headline-only` at `0fd4b5d`) calls `oracles.cli run --seed --headline-only`, and
   0.1.2 has neither option.
   - `bench/_seed_point.py` runs the release's `cli.run` itself, with `build_report`
     bound to `seed=` and `analyzed_ids=[featured_case(build_catalog(seed)).id]`. That is
     exactly what `--headline-only` did at `0fd4b5d`.
   - The fingerprint function is copied from `0fd4b5d`.
   - The sweep stops at the first failing seed instead of running the rest.
7. **Unattended upgrades during the sweep.** On 7 October 00:26–00:30 UTC, the host's
   unattended-upgrades installed `sg3-utils`, `sg3-utils-udev`, `libfreetype` and the
   kernel package 5.15.0-198 (installed only; the running kernel stayed 5.15.0-187).
   - glibc/libm, Python and the benchmark environment were not touched.
   - Two seed points overlapped those minutes:
     - 20260611: 00:16–00:30 UTC, 825 s, load 1.48 → 3.26;
     - 20260612: 00:30–00:43 UTC, 785 s, started at load 3.26.
   - Both are kept as measured. No ladder rung overlapped.
8. **Lock file:** `provenance.json` records the SHA-256 of `uv.lock` as it was during the
   measurement (`f4c9540f…`). The lock committed with this release differs from it in one
   line only, the version of this repository itself (1.0.0 → 1.1.0); every package pin
   and hash is the same.
9. **Idle host:** the Claude Code session that started the chain and a VS Code server
   ran on terra throughout, idle. They are listed in `provenance.json` (`preflight`).
