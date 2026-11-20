# Timing of record: spectrafit-core 0.1.2 on terra, 160 cases (run 2)

The timing benchmark of the paper, measured on terra from 16 October 2026 20:39 UTC to
17 October 2026 22:54 UTC (26 h 15 min). It repeats the first measurement with
0.1.2 (`../timing-2026-10-06/`, run 1) with the same library, harness, comparators,
depths, `--mc` and seeds, by the chain of this repository at commit `3ab6ca6`, which in
addition records the steal time and the host once a minute.

- **the compiled library:** the published PyPI wheel `spectrafit-core==0.1.2`,
  hash-pinned in `uv.lock`. No source build, no target-cpu flags.
- **the harness:** v0.1.2 at commit `1e304188a7376caf128fcb432a16554ed44ad32a`,
  exported with `git archive` outside any git work tree, as in run 1. The preflight
  compared the export file by file with the export of run 1 (464 files, identical).
- **the comparators at their locked versions:** lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1,
  JAX and jaxlib 0.11.0, optimistix 0.1.0, Python 3.13.13.
- **library defaults only:** thread variables, `XLA_FLAGS`, `JAX_PLATFORMS` and
  `SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET` unset; JAX compile budget 64 (the 0.1.2
  default); `vm.max_map_count` 65530.

Nothing was tuned on a result.

## How it was run

`bench/preflight.sh` checked the repository, the export, the six backends and the host
and wrote `preflight.txt` (0 FAIL). `bench/run_timing.sh` then ran in a detached tmux
session, started with a delay of 300 s so that the session which started it could end
first. Before the run the host was updated and rebooted (kernel 5.15.0-198), and the
apt timers and unattended-upgrades were stopped and masked and the kernel and C library
packages held until the run had finished (`bench/RUNBOOK.md`). Every step exited 0.

| step | command | wall time |
|---|---|---|
| 0 | backends check, `bench/assemble.py capture`, host snapshot before | seconds |
| 1–5 | the release's `scripts/bench_ladder.py --ladder R --mc 8`, unmodified, once per R = 4, 10, 20, 50, 100 | 71, 91, 125, 226, 393 min |
| 6 | `bench/seed_sweep.py`: seeds 20260603…20260652, `--reps 10`, `--mc 8`, headline-only | 11.2 h |
| 7 | the release's `extract_bench_summary.py` on the reps-100 run | seconds |
| 8 | the release's `measure_param_agreement.py` | seconds |
| 9 | the release's `measure_audit_bias.py` | seconds |
| 10 | host snapshot after | seconds |

**Steal time.** The aggregate `cpu` line of `/proc/stat` was read at the start and end
of every step and every seed point; the steal fraction is the difference of its 8th
field over the difference of all fields. It was 0.013 % to 0.017 % for each ladder
rung and the seed sweep, and 0.015 % over the whole run. `vmstat` (once a minute,
1 576 rows) shows no steal, no swap activity and a run queue of at most 16.

`provenance.json` records every step with its command, start, end, exit code, load
average and `/proc/stat` reading, the steal fraction per rung and per seed, the
preflight readings, and the SHA-256 of every exported file and of the drivers in
`bench/`. `host/before.txt` and `host/after.txt` are full host snapshots (kernel,
glibc, CPU, clock source, swap, transparent huge pages, CPU frequency, pressure,
services, sessions, held packages, installed packages, the wheel's digest).
`host/vmstat.log.gz` and `host/threads.log.gz` are the per-minute records.

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
host/                                    snapshots before and after, per-minute vmstat and thread records
```

## Run 2 against run 1

The two runs agree to the second significant figure on every headline number
(`bench/compare.py`, table in the top-level `README.md`): geometric mean 16.71 against
16.75, harmonic mean 13.75 against 13.75, seed sweep 16.19 ± 0.36 against 16.30 ± 0.41.
`param_agreement.json` is byte-identical. The differences between the runs:

1. **Host:** kernel 5.15.0-198 instead of 187 (updated and rebooted before the run).
   glibc, Python and the benchmark environment are unchanged. The NIST tables
   regenerated after the update are numerically identical to the stored ones; only the
   kernel string in their host record differs.
2. **Host frozen:** no unattended upgrade ran during run 2 (in run 1 one ran during two
   seed points, item 7 of `../timing-2026-10-06/README.md`).
3. **Records added:** steal time per step and per seed, per-minute `vmstat` and thread
   records, preflight and full host snapshots.

**The lowest seed.** Seed 20260636 has the lowest harmonic mean of the sweep in both
runs (10.42 in run 1, 10.41 in run 2; geometric mean 16.01 and 15.99). One case causes
it: on this catalogue draw spectrafit-core needs 258 ms (run 1: 263 ms) for the complex
case CX-008, against 74 ms for lmfit, a speedup of 0.29. Without CX-008 the seed's
harmonic mean is 13.38 and 13.41. Steal and `vmstat` show nothing in the minutes of
this seed; it is a property of the drawn data.

## Differences from the archived 151-case measurement

Items 1 to 3, 5, 6 and 8 of `../timing-2026-10-06/README.md` apply unchanged: 160
instead of 151 cases, the 0.1.2 wheel, the v0.1.2 harness, the schema-2 records built
by `bench/assemble.py`, the seed-sweep driver, and a lock file that differs from the
committed one only in the version of this repository.

## Idle host

A VS Code Remote-SSH server with GitHub Copilot ran on terra throughout, idle (at most
2 % of one core of sixteen; listed in `host/before.txt`), as in run 1, whose snapshot
lists only the busiest processes. An SSH login with an idle shell stayed open. No other
login took place during the run.
