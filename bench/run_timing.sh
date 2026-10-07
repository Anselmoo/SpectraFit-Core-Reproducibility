#!/bin/bash
# usage: run_timing.sh <run-root> [--dry-run]
#
# The full timing measurement of spectrafit-core 0.1.2 on terra, as one detached chain:
#   1-5  repetition ladder, --reps 4 10 20 50 100, --mc 8: the release's own
#        scripts/bench_ladder.py, unmodified, one invocation per depth
#   6    seed sweep, seeds 20260603..20260652, --reps 10, --mc 8, headline-only
#        (bench/seed_sweep.py)
#   7    bench_summary.json from the deepest rung (release's extract_bench_summary.py)
#   8    param_agreement.json (release's measure_param_agreement.py)
#   9    audit_bias.json (release's measure_audit_bias.py)
#   10   host snapshot after
# The first non-zero exit stops the chain; nothing is retried or skipped.
#
# Expects <run-root>/src to be a `git archive` export of the release (outside any git
# work tree, python/ holding only oracles/) and <run-root>/preflight.txt to exist.
# Progress: <run-root>/STATUS (one line), <run-root>/chain.log, <run-root>/steps.jsonl.
set -euo pipefail
T=$(realpath "${1:?run root}"); DRY=${2:-}
W=$(cd "$(dirname "$0")/.." && pwd)
PY=$W/.venv/bin/python
SRC=$T/src
COMMIT=1e304188a7376caf128fcb432a16554ed44ad32a
N=10
LOCK=$HOME/.cache/terra-bench.lock

# Library defaults only: nothing that changes how the backends thread or compile.
unset OMP_NUM_THREADS OPENBLAS_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS \
      VECLIB_MAXIMUM_THREADS RAYON_NUM_THREADS XLA_FLAGS JAX_PLATFORMS \
      SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET
export MPLBACKEND=Agg

FIGS=$T/post/reproducibility/figures
CMDS=(
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r004 --ladder 4 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r010 --ladder 10 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r020 --ladder 20 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r050 --ladder 50 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r100 --ladder 100 --mc 8"
  "$PY $W/bench/seed_sweep.py --src $SRC --out $T/seed-sweep --commit $COMMIT --seed-base 20260603 --seeds 50 --reps 10 --mc 8"
  "rm -rf $T/post && mkdir $T/post && (cd $SRC && tar -cf - --exclude=./.spectrafit_reports .) | tar -xf - -C $T/post && cd $FIGS && PYTHONPATH=$T/post/python $PY extract_bench_summary.py $T/ladder/r100/rung_050/run --out $FIGS/bench_summary.json"
  "cd $FIGS && PYTHONPATH=$T/post/python $PY measure_param_agreement.py"
  "cd $FIGS && PYTHONPATH=$T/post/python $PY measure_audit_bias.py"
  "bash $W/bench/host_snapshot.sh after $PY > $T/host-after.txt"
)
NAMES=("ladder reps=4" "ladder reps=10" "ladder reps=20" "ladder reps=50" "ladder reps=100"
       "seed sweep 50x reps=10" "bench summary" "param agreement" "audit bias" "host snapshot after")

if [ "$DRY" = --dry-run ]; then
  for k in $(seq 1 $N); do printf 'STEP %d/%d %s\n  %s\n' "$k" "$N" "${NAMES[$k-1]}" "${CMDS[$k-1]}"; done
  exit 0
fi

test -f "$T/preflight.txt" || { echo "no $T/preflight.txt"; exit 2; }
git -C "$SRC" rev-parse 2>/dev/null && { echo "$SRC is inside a git work tree"; exit 2; }
test "$(ls "$SRC/python")" = oracles || { echo "$SRC/python must hold only oracles"; exit 2; }
mkdir -p "$(dirname "$LOCK")" "$T/logs"
exec 9>"$LOCK"
flock -n 9 || { echo "FAILED lock $LOCK held by another benchmark $(date -Is)" > "$T/STATUS"; exit 3; }

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >> "$T/chain.log"; }
load() { cut -d' ' -f1-3 /proc/loadavg; }

log "chain start pid=$$ src=$SRC commit=$COMMIT py=$PY"
echo "STEP 0/$N capture RUNNING since $(date -Is)" > "$T/STATUS"
if ! (cd "$SRC" && PYTHONPATH=$SRC/python "$PY" "$W/bench/assemble.py" capture "$T") >> "$T/logs/step00.log" 2>&1; then
  echo "FAILED step 0/$N capture $(date -Is) (see logs/step00.log)" > "$T/STATUS"; log "capture failed"; exit 1
fi
log "step 0/$N capture done: $(tail -1 "$T/logs/step00.log")"
for k in $(seq 1 $N); do
  name=${NAMES[$k-1]}; cmd=${CMDS[$k-1]}
  t0=$(date -u +%FT%TZ); l0=$(load)
  echo "STEP $k/$N $name RUNNING since $(date -Is)" > "$T/STATUS"
  log "step $k/$N start  [$name] load=$l0"
  log "  $cmd"
  set +e
  bash -c "$cmd" >> "$T/logs/step$(printf %02d "$k").log" 2>&1
  rc=$?
  set -e
  t1=$(date -u +%FT%TZ); l1=$(load)
  log "step $k/$N end    [$name] rc=$rc load=$l1"
  printf '{"step": %d, "name": "%s", "cmd": "%s", "started_utc": "%s", "finished_utc": "%s", "rc": %d, "load_start": [%s], "load_end": [%s]}\n' \
    "$k" "$name" "${cmd//\"/\\\"}" "$t0" "$t1" "$rc" "${l0// /, }" "${l1// /, }" >> "$T/steps.jsonl"
  if [ "$rc" -ne 0 ]; then
    echo "FAILED step $k/$N $name rc=$rc $(date -Is) (see logs/step$(printf %02d "$k").log)" > "$T/STATUS"
    log "chain stopped at step $k"
    exit "$rc"
  fi
done
echo "DONE $(date -Is)" > "$T/STATUS"
log "chain done"
