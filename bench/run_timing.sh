#!/bin/bash
# usage: run_timing.sh <run-root> [--dry-run | --smoke | --from-step K]
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
# Recorded for every step (steps.jsonl) besides the load average: the aggregate `cpu`
# line of /proc/stat at its start and end, so the steal time of each step is the
# difference of the 8th field. Over the whole chain `vmstat -t 60` (vmstat.log: steal,
# swap in/out, run queue) and a per-minute sample of the busiest processes with their
# thread counts (threads.log) run in the background. Before the first rung the chain
# takes the host snapshot `before` and stops unless all six backends of the paper load.
#
# --smoke     the same chain on the smallest inputs (one ladder rung at --ladder 2, one
#             seed at --reps 2, no derived files), then `assemble.py build --partial`;
#             about 45 minutes on terra. Run it before the measurement, in its own root.
# --from-step K   resume a chain that stopped at step K: steps before K are not rerun,
#             their records in steps.jsonl are kept. The seed sweep skips seeds whose
#             point.json shows a successful run (bench/seed_sweep.py --skip-complete).
#
# Expects <run-root>/src to be a `git archive` export of the release (outside any git
# work tree, python/ holding only oracles/) and <run-root>/preflight.txt to exist.
# Progress: <run-root>/STATUS (one line), <run-root>/chain.log, <run-root>/steps.jsonl.
set -euo pipefail
T=$(realpath "${1:?run root}"); MODE=${2:-}; FROM=1
case "$MODE" in
  ""|--dry-run|--smoke) ;;
  --from-step) FROM=${3:?step number}; [[ "$FROM" =~ ^[0-9]+$ ]] || { echo "bad step $FROM"; exit 2; } ;;
  *) echo "unknown option $MODE"; exit 2 ;;
esac
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
EXPECTED_BACKENDS="jax lmfit scipy-ls-dogbox scipy-ls-lm scipy-ls-trf spectrafit"
CMDS=(
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r004 --ladder 4 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r010 --ladder 10 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r020 --ladder 20 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r050 --ladder 50 --mc 8"
  "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r100 --ladder 100 --mc 8"
  "$PY $W/bench/seed_sweep.py --src $SRC --out $T/seed-sweep --commit $COMMIT --seed-base 20260603 --seeds 50 --reps 10 --mc 8 --skip-complete"
  "rm -rf $T/post && mkdir $T/post && (cd $SRC && tar -cf - --exclude=./.spectrafit_reports .) | tar -xf - -C $T/post && cd $FIGS && PYTHONPATH=$T/post/python $PY extract_bench_summary.py $T/ladder/r100/rung_050/run --out $FIGS/bench_summary.json"
  "cd $FIGS && PYTHONPATH=$T/post/python $PY measure_param_agreement.py"
  "cd $FIGS && PYTHONPATH=$T/post/python $PY measure_audit_bias.py"
  "bash $W/bench/host_snapshot.sh after $PY > $T/host-after.txt"
)
NAMES=("ladder reps=4" "ladder reps=10" "ladder reps=20" "ladder reps=50" "ladder reps=100"
       "seed sweep 50x reps=10" "bench summary" "param agreement" "audit bias" "host snapshot after")

if [ "$MODE" = --smoke ]; then
  N=3
  CMDS=(
    "cd $SRC && $PY scripts/bench_ladder.py --out $T/ladder/r002 --ladder 2 --mc 8"
    "$PY $W/bench/seed_sweep.py --src $SRC --out $T/seed-sweep --commit $COMMIT --seed-base 20260603 --seeds 1 --reps 2 --mc 8 --skip-complete"
    "bash $W/bench/host_snapshot.sh after $PY > $T/host-after.txt"
  )
  NAMES=("smoke ladder reps=2" "smoke seed sweep 1x reps=2" "host snapshot after")
fi

if [ "$MODE" = --dry-run ]; then
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
cpustat() { head -1 /proc/stat | tr -s ' ' | cut -d' ' -f2- ; }  # user nice system idle iowait irq softirq steal guest guest_nice

# Background recorders for the whole chain; stopped when this script exits.
vmstat -t -n 60 >> "$T/vmstat.log" 2>&1 &
VMSTAT_PID=$!
( while sleep 60; do
    { echo "## $(date -u +%FT%TZ)"; ps -eo pid,nlwp,pcpu,rss,comm --sort=-pcpu | head -12; } >> "$T/threads.log"
  done ) &
THREADS_PID=$!
trap 'kill $VMSTAT_PID $THREADS_PID 2>/dev/null' EXIT

log "chain start pid=$$ src=$SRC commit=$COMMIT py=$PY mode=${MODE:-full} from_step=$FROM"
if [ "$FROM" -le 1 ]; then
  echo "STEP 0/$N capture RUNNING since $(date -Is)" > "$T/STATUS"
  if ! (cd "$SRC" && PYTHONPATH=$SRC/python "$PY" "$W/bench/assemble.py" capture "$T") >> "$T/logs/step00.log" 2>&1; then
    echo "FAILED step 0/$N capture $(date -Is) (see logs/step00.log)" > "$T/STATUS"; log "capture failed"; exit 1
  fi
  log "step 0/$N capture done: $(tail -1 "$T/logs/step00.log")"
  # All six backends of the paper must load: a missing optional backend is dropped
  # silently by the harness, and a missing baseline turns every speedup into 1.0.
  got=$("$PY" -c "import json,sys; print(' '.join(sorted(json.load(open(sys.argv[1]))['probe']['backends'])))" "$T/capture.json")
  if [ "$got" != "$EXPECTED_BACKENDS" ]; then
    echo "FAILED step 0/$N backends: got [$got], expected [$EXPECTED_BACKENDS] $(date -Is)" > "$T/STATUS"
    log "backends $got != $EXPECTED_BACKENDS"; exit 1
  fi
  log "step 0/$N backends: $got"
  bash "$W/bench/host_snapshot.sh" before "$PY" > "$T/host-before.txt" 2>&1
  log "step 0/$N host snapshot before written"
else
  test -f "$T/capture.json" || { echo "--from-step $FROM needs $T/capture.json"; exit 2; }
fi
for k in $(seq 1 $N); do
  name=${NAMES[$k-1]}; cmd=${CMDS[$k-1]}
  if [ "$k" -lt "$FROM" ]; then log "step $k/$N skipped (--from-step $FROM)"; continue; fi
  t0=$(date -u +%FT%TZ); l0=$(load); c0=$(cpustat)
  echo "STEP $k/$N $name RUNNING since $(date -Is)" > "$T/STATUS"
  log "step $k/$N start  [$name] load=$l0"
  log "  $cmd"
  set +e
  bash -c "$cmd" >> "$T/logs/step$(printf %02d "$k").log" 2>&1
  rc=$?
  set -e
  t1=$(date -u +%FT%TZ); l1=$(load); c1=$(cpustat)
  log "step $k/$N end    [$name] rc=$rc load=$l1"
  printf '{"step": %d, "name": "%s", "cmd": "%s", "started_utc": "%s", "finished_utc": "%s", "rc": %d, "load_start": [%s], "load_end": [%s], "proc_stat_cpu_start": [%s], "proc_stat_cpu_end": [%s]}\n' \
    "$k" "$name" "${cmd//\"/\\\"}" "$t0" "$t1" "$rc" "${l0// /, }" "${l1// /, }" "${c0// /, }" "${c1// /, }" >> "$T/steps.jsonl"
  if [ "$rc" -ne 0 ]; then
    echo "FAILED step $k/$N $name rc=$rc $(date -Is) (see logs/step$(printf %02d "$k").log)" > "$T/STATUS"
    log "chain stopped at step $k"
    exit "$rc"
  fi
done
if [ "$MODE" = --smoke ]; then
  if "$PY" "$W/bench/assemble.py" build "$T" "$T/assembled" --partial >> "$T/logs/assemble.log" 2>&1; then
    log "smoke: assemble build --partial passed"
  else
    echo "FAILED smoke assemble $(date -Is) (see logs/assemble.log)" > "$T/STATUS"; log "smoke assemble failed"; exit 1
  fi
fi
echo "DONE $(date -Is)" > "$T/STATUS"
log "chain done"
