# Timing of record: spectrafit-core 0.1.3 on terra, 160 cases

The timing benchmark of release 1.3.0 of this archive, measured on terra from
16 November 2026 17:17 UTC to 17 November 2026 20:02 UTC (26 h 45 min), by the
`timing` target of `run-archive.sh` (`bench/preflight.sh`, then `bench/run_timing.sh`).
The previous timing of record, spectrafit-core 0.1.2 of 16 to 17 October 2026, is kept
unchanged in `../timing-0.1.2-2026-10-16/`.

- **Host:** terra, AMD EPYC Processor (with IBPB), 16 cores, 31.3 GB RAM, no swap,
  Linux 5.15.0-203-generic, glibc 2.35-0ubuntu3.18, clock source kvm-clock,
  `vm.max_map_count` 65530. No package update and no reboot before the run.
- **The compiled library:** spectrafit-core 0.1.3, the published PyPI wheel
  `spectrafit_core-0.1.3-cp313-cp313-manylinux_2_28_x86_64.whl`, SHA-256
  `0d909b5faf1b5f47cbfb81b074b6ee0f44a523c6daf8303c8f2d4e1c878f6e43`, hash-pinned in
  `uv.lock` (`pins.toml [packages]`, `[timing]`); compiled extension `_core` SHA-256
  `2e672905bbbf9e592a68df47f4342e811f028063cc4dc144e787cd83ff021ebd`. No source build.
- **The harness:** v0.1.3, tag `v0.1.3` at commit `952c5c954eed2e0e36224ddf2f9859086d36fad7`,
  exported with `git archive` (`scripts/bench_ladder.py python/oracles reproducibility
  tests/parity crates Cargo.toml`); `python/` of the export holds only `oracles`, so the
  wheel is imported.
- **The comparators at their locked versions:** lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1,
  JAX and jaxlib 0.11.0, optimistix 0.1.0, Python 3.13.13, BLAS scipy-openblas
  0.3.33.112.0.
- **Depths and seeds:** ladder `--reps 4,10,20,50,100` (effective 2, 5, 10, 25, 50),
  `--mc 8`, catalogue seed 20260603; seed sweep seeds 20260603…20260652, `--reps 10`
  (effective 5), `--mc 8`, headline-only. The same as for 0.1.2.

## Threading policy

`run-archive.sh` sets the thread variables per target and records them as
`thread_setting` in each target's `run.json`.

| target | threads | counted |
|---|---|---|
| `timing` (this directory: ladder and seed sweep) | library defaults: `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `RAYON_NUM_THREADS`, `XLA_FLAGS` and `JAX_PLATFORMS` unset | yes |
| `bench-tolerance` (`../bench-tolerance/`) | caps 1: `OMP/OPENBLAS/MKL/RAYON_NUM_THREADS=1` | yes |
| `bench-ablation` (`../bench-ablation/`) | caps 1 | yes |
| `gallery` (`../gallery/`) | library defaults | no |

All targets ran one at a time; nothing ran in parallel with a timed target.

## Host freeze

Before the run, the apt timers `apt-daily.timer` and `apt-daily-upgrade.timer` and
`unattended-upgrades.service` were stopped and masked; `man-db.timer` and
`update-notifier-download.timer` were stopped; and these packages were held
(`apt-mark hold`): libc-bin, libc6, linux-headers-5.15.0-202,
linux-headers-5.15.0-202-generic, linux-headers-5.15.0-203,
linux-headers-5.15.0-203-generic, linux-headers-generic, linux-image-5.15.0-202-generic,
linux-image-5.15.0-203-generic, linux-image-generic, linux-modules-5.15.0-202-generic,
linux-modules-5.15.0-203-generic, linux-modules-extra-5.15.0-202-generic,
linux-modules-extra-5.15.0-203-generic. No container was running. The preflight
(`provenance.json`, `preflight`) reported 0 failing checks; its one WARN lists the
agent sessions that were present (also in `host/before.txt` and `host/after.txt`).

## How it was run

| step | command | wall time |
|---|---|---|
| 0 | `bench/preflight.sh`: repository, export, six backends, host; host snapshot before | minutes |
| 1–5 | the release's `scripts/bench_ladder.py --ladder R --mc 8`, unmodified, once per R = 4, 10, 20, 50, 100 | 74, 94, 129, 231, 399 min |
| 6 | `bench/seed_sweep.py`: seeds 20260603…20260652, `--reps 10`, `--mc 8`, headline-only | 11.3 h |
| 7 | the release's `extract_bench_summary.py` on the reps-100 run | seconds |
| 8 | the release's `measure_param_agreement.py` | seconds |
| 9 | the release's `measure_audit_bias.py` | seconds |
| 10 | host snapshot after | seconds |

Every step exited 0. `bench/assemble.py build` assembled this directory on
19 November 2026 (5 rungs, 50 seeds, 0 problems).

**Steal time.** From the aggregate `cpu` line of `/proc/stat` at the start and end of
every step: 0.014 % to 0.021 % per ladder rung and for the seed sweep, 0.017 % over the
whole run. `host/vmstat.log.gz` (once a minute, 1 605 rows) shows no steal, no swap
activity and a run queue of at most 16.

**Log.** `../run-log.tsv` and `../progress.txt` record every target with its start, end,
exit code and the SHA-256 over its output files.

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
bench_summary.json                       Figure 3, the bench- claims and agree-02
param_agreement.json                     agree-01
audit_bias.json                          bias-01, bias-02
provenance.json                          every step with command, times, exit code, load, steal; preflight
host/                                    snapshots before and after, per-minute vmstat and thread records
```
