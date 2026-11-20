#!/usr/bin/env bash
# Run every target of the archive once, serially, in a fixed order, with a record per target.
#
#   bash run-archive.sh [--only t1,t2,...] [-- <extra reproduce.py arguments>]
#
# Order and thread setting (one target at a time, nothing in parallel):
#   timing              bench/preflight.sh + bench/run_timing.sh: repetition ladder and 50-seed
#                       sweep of the release, library-default threading (26 to 48 h)
#   bench-tolerance     thread caps 1 (timed)
#   bench-ablation      thread caps 1 (timed)
#   gallery             library-default threading (its timings are not counted)
#   nist-both, usage, audit-stationarity, eels-far     thread caps 1 (untimed)
#   gate                stops the run until results/timing/ holds the new timing and pins.toml
#                       records its SHA-256 (bench/RUNBOOK.md steps 11 and 12); run again after
#   core, overview      thread caps 1 (untimed; core computes the claims from results/timing/)
#
# Environment:
#   PYTHON               interpreter command (default: uv run --locked --group benchmark --group audit python)
#   RESULTS_DIR          where run-log.tsv and progress.txt go and where the targets write
#                        (default: results; set it to <out>/results for a --dry-run --out <out>)
#   SPECTRAFIT_VERSION   the release measured by `timing` (default 0.1.3)
#   SPECTRAFIT_CHECKOUT  a SpectraFit-Core checkout with the release tag (`timing` only)
#   TIMING_ROOT          a fresh run root for the timing chain (`timing` only)
#
# Per target, results/run-log.tsv gets one row: target, start and end (UTC), duration (s),
# exit code, number of output files and the SHA-256 over their "sha256  path" lines;
# results/progress.txt gets one line when a target starts and one when it ends.
# A failing target is recorded and the next one runs, except `timing`: its failure stops the
# run (the timed targets after it need the same host conditions). The script exits non-zero at
# the end if any target failed, and with 3 at the gate. Resume: a target whose last row has exit
# code 0 and whose outputs still give the recorded SHA-256 is skipped.
set -u
cd "$(dirname "$0")" || exit 2
TARGETS=(timing bench-tolerance bench-ablation gallery nist-both usage audit-stationarity eels-far gate core overview)
PYTHON=${PYTHON:-"uv run --locked --group benchmark --group audit python"}
RESULTS_DIR=${RESULTS_DIR:-results}
export SPECTRAFIT_VERSION=${SPECTRAFIT_VERSION:-0.1.3}
THREAD_VARS=(OMP_NUM_THREADS OPENBLAS_NUM_THREADS MKL_NUM_THREADS RAYON_NUM_THREADS)
ONLY=""
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY=$2; shift 2 ;;
    --) shift; EXTRA=("$@"); break ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$RESULTS_DIR"
LOG="$RESULTS_DIR/run-log.tsv"
PROGRESS="$RESULTS_DIR/progress.txt"
[ -f "$LOG" ] || printf 'target\tstart_utc\tend_utc\tduration_s\texit_code\tn_files\toutputs_sha256\n' > "$LOG"
DRY=0
for a in ${EXTRA[@]+"${EXTRA[@]}"}; do [ "$a" = --dry-run ] && DRY=1; done

threads() {
  case "$1" in
    timing|gallery) unset "${THREAD_VARS[@]}" ;;
    *) for v in "${THREAD_VARS[@]}"; do export "$v=1"; done ;;
  esac
}

outputs() {
  local t=$1 base
  base=$(dirname "$RESULTS_DIR")
  case "$t" in
    timing)
      [ -n "${TIMING_ROOT:-}" ] && [ -d "$TIMING_ROOT" ] && {
        [ -f "$TIMING_ROOT/steps.jsonl" ] && echo "$TIMING_ROOT/steps.jsonl"
        for d in ladder seed-sweep; do [ -d "$TIMING_ROOT/$d" ] && find "$TIMING_ROOT/$d" -type f; done
      } ;;
    core)
      for f in nist_table2.json nist_table2_tol1e15.json nist_head_to_head.json eels_fe2o3.json \
               claims-report.json drift-report.json; do
        [ -f "$RESULTS_DIR/$f" ] && echo "$RESULTS_DIR/$f"
      done
      [ -d "$base/figures" ] && find "$base/figures" -type f ;;
    *) [ -d "$RESULTS_DIR/$t" ] && find "$RESULTS_DIR/$t" -type f ;;
  esac | LC_ALL=C sort
}

digest() {
  local files
  files=$(outputs "$1")
  if [ -z "$files" ]; then echo "0 none"; return; fi
  echo "$(echo "$files" | wc -l) $(echo "$files" | xargs sha256sum | sha256sum | cut -d' ' -f1)"
}

run_timing() {
  : "${SPECTRAFIT_CHECKOUT:?set SPECTRAFIT_CHECKOUT to a SpectraFit-Core checkout with tag v$SPECTRAFIT_VERSION}"
  : "${TIMING_ROOT:?set TIMING_ROOT to a fresh run root for the timing chain}"
  bash bench/preflight.sh "$TIMING_ROOT" "$SPECTRAFIT_CHECKOUT" --allow-sessions && bash bench/run_timing.sh "$TIMING_ROOT"
}

# The new timing is in results/timing/ and pinned: provenance names the release, pins match.
gate_open() {
  $PYTHON - "$SPECTRAFIT_VERSION" <<'EOF'
import hashlib, json, sys, tomllib
from pathlib import Path
version = sys.argv[1]
prov = json.loads(Path("results/timing/provenance.json").read_text())
if f"spectrafit-core {version} " not in prov.get("what", ""):
    sys.exit(f"results/timing/ holds: {prov.get('what')}")
pins = tomllib.loads(Path("pins.toml").read_text())["timing_inputs"]
bad = [p for p, d in pins.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != d]
if bad:
    sys.exit("pins.toml [timing_inputs] does not match: " + ", ".join(bad))
EOF
}

failed=0
for t in "${TARGETS[@]}"; do
  if [ -n "$ONLY" ] && ! [[ ",$ONLY," == *",$t,"* ]]; then continue; fi
  if [ "$t" = gate ]; then
    if [ "$DRY" -eq 1 ]; then
      echo "$(date -u +%FT%TZ) gate skipped: dry run (no timing of record)" >> "$PROGRESS"
    elif ! gate_open; then
      echo "$(date -u +%FT%TZ) gate: stop until the new timing is assembled into results/timing/ and pinned (bench/RUNBOOK.md steps 11-12); then run again" >> "$PROGRESS"
      exit 3
    else
      echo "$(date -u +%FT%TZ) gate open: results/timing/ is spectrafit-core $SPECTRAFIT_VERSION and pinned" >> "$PROGRESS"
    fi
    continue
  fi
  last=$(awk -F'\t' -v t="$t" '$1 == t {row = $0} END {print row}' "$LOG")
  if [ -n "$last" ] && [ "$(echo "$last" | cut -f5)" = "0" ]; then
    read -r n d <<< "$(digest "$t")"
    if [ "$d" = "$(echo "$last" | cut -f7)" ] && [ "$n" = "$(echo "$last" | cut -f6)" ]; then
      echo "$(date -u +%FT%TZ) $t skipped: outputs match the recorded sha256" >> "$PROGRESS"
      continue
    fi
  fi
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  echo "$start $t started" >> "$PROGRESS"
  (
    threads "$t"
    case "$t" in
      timing) run_timing ;;
      *) $PYTHON reproduce.py --targets "$t" ${EXTRA[@]+"${EXTRA[@]}"} ;;
    esac
  )
  code=$?
  end=$(date -u +%FT%TZ); dur=$(( $(date +%s) - t0 ))
  read -r n d <<< "$(digest "$t")"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$t" "$start" "$end" "$dur" "$code" "$n" "$d" >> "$LOG"
  echo "$end $t finished: exit $code, ${dur} s, $n files" >> "$PROGRESS"
  if [ "$code" -ne 0 ]; then
    failed=1
    if [ "$t" = timing ]; then
      echo "$end stopped: the timing chain failed; the timed targets after it need the same host conditions" >> "$PROGRESS"
      exit 1
    fi
  fi
done
exit $failed
