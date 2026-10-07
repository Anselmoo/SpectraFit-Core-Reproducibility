# Archived timing (151 cases): superseded for the paper

These five files are the timing archive shipped in the spectrafit-core release
(`reproducibility/` at tag `v0.1.2`, identical in 0.1.0 and 0.1.1). `reproduce.py`
copies them here on every run after checking their SHA-256 against
`pins.toml [archived_inputs]`.

They were measured on terra on 15 to 17 August 2026, before the first release:

- the ladder and the summary at commit `990a4c7`;
- the seed sweep at commit `0fd4b5d`.

Both commits are on branch `fix/jax-compile-budget-max-map-count`, which is in no
release. The case catalogue then had 151 cases; the released harness generates 160.

**The paper no longer uses them.** Its timing numbers, Figure 3 and the claims in
`results/claims-report.json` come from `results/timing/`, measured with the published
0.1.2 wheel and the v0.1.2 harness. The two are compared in the README at the top of this
repository.

| File | What |
|---|---|
| `bench_summary.json` | 151 cases × 6 backends at repetition depth 50 (run `2026-08-16_run_037`) |
| `ladder.json` | five repetition depths, schema `bench-ladder/2` |
| `sweep.json` | 50 catalogue seeds, schema `bench-seed-sweep/1` |
| `param_agreement.json` | cross-backend parameter agreement, from `bench_summary.json` |
| `audit_bias.json` | serialisation bias and kernel parity. The file names no host; it was first committed on 17 August 2026 (spectrafit-core `0bf1bef`). |
