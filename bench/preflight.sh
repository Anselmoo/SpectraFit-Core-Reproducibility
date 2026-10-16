#!/bin/bash
# usage: preflight.sh <run-root> <SpectraFit-Core checkout> [--allow-sessions]
#
# Prepares <run-root> for bench/run_timing.sh and refuses to let a timing run start on a
# host or environment that would make it non-comparable. Writes <run-root>/preflight.txt
# (run_timing.sh requires it) with one PASS / WARN / FAIL line per check and the raw
# readings behind it, and exits 1 if any check FAILs.
#
#   1  this repository: clean working tree, uv.lock as committed, environment synced
#      from the lock (benchmark and audit groups)
#   2  the export: `git archive` of the pinned commit into <run-root>/src, python/
#      holding only oracles, every file identical to the export of the timing of record
#   3  the backends: all six of the paper load from the export with the PyPI wheel
#   4  the host: rebooted since the last package change, apt timers and
#      unattended-upgrades inactive, no running containers, no editor or agent
#      sessions (WARN only with --allow-sessions), load below 0.5 over three minutes,
#      20 GB free, vm.max_map_count, the benchmark lock free
#
# The checkout is only read (`git archive`); its working tree does not matter.
set -uo pipefail
T=$(realpath -m "${1:?run root}"); CORE=$(realpath "${2:?SpectraFit-Core checkout}")
ALLOW_SESSIONS=${3:-}
W=$(cd "$(dirname "$0")/.." && pwd)
PY=$W/.venv/bin/python
COMMIT=1e304188a7376caf128fcb432a16554ed44ad32a
EXPORT_PATHS="scripts/bench_ladder.py python/oracles reproducibility tests/parity crates Cargo.toml"
EXPECTED_BACKENDS="jax lmfit scipy-ls-dogbox scipy-ls-lm scipy-ls-trf spectrafit"
# The export of record: results/timing/ before the first new run, the archived copy after.
REFERENCE=$W/results/timing/provenance.json
[ -f "$W/results/timing-2026-10-06/provenance.json" ] && REFERENCE=$W/results/timing-2026-10-06/provenance.json
LOCK=$HOME/.cache/terra-bench.lock

mkdir -p "$T"
OUT=$T/preflight.txt
FAILS=0
: > "$OUT"
say()  { printf '%s\n' "$*" | tee -a "$OUT"; }
pass() { say "PASS  $*"; }
warn() { say "WARN  $*"; }
fail() { say "FAIL  $*"; FAILS=$((FAILS + 1)); }
raw()  { sed 's/^/      /' | tee -a "$OUT" >/dev/null; }

say "# preflight $(date -u +%FT%TZ) $(hostname) by $(id -un)"
say "# repository $W @ $(git -C "$W" rev-parse HEAD 2>/dev/null) ($(git -C "$W" rev-parse --abbrev-ref HEAD 2>/dev/null))"

# ---------------------------------------------------------------- 1 repository
if [ -z "$(git -C "$W" status --porcelain 2>/dev/null)" ]; then pass "working tree clean"
else fail "working tree not clean: commit or stash first"; git -C "$W" status --porcelain | raw; fi
if git -C "$W" diff --quiet HEAD -- uv.lock; then pass "uv.lock as committed ($(sha256sum "$W/uv.lock" | cut -c1-16))"
else fail "uv.lock differs from HEAD"; fi
if (cd "$W" && uv sync --locked --group benchmark --group audit) > "$T/uv-sync.log" 2>&1; then
  pass "environment synced from the lock (benchmark, audit)"
else fail "uv sync --locked failed (see $T/uv-sync.log)"; fi

# ---------------------------------------------------------------- 2 export
if [ -e "$T/src" ]; then
  fail "$T/src exists: use a fresh run root, an export is never reused"
else
  if git -C "$CORE" cat-file -e "$COMMIT^{commit}" 2>/dev/null; then
    mkdir -p "$T/src" && git -C "$CORE" archive "$COMMIT" $EXPORT_PATHS | tar -x -C "$T/src"
    if [ "$(ls "$T/src/python")" = oracles ]; then pass "export of $COMMIT in $T/src, python/ holds only oracles"
    else fail "python/ of the export holds $(ls "$T/src/python" | tr '\n' ' ')"; fi
  else
    fail "$CORE does not contain the pinned commit $COMMIT"
  fi
fi
if [ -d "$T/src" ] && [ -f "$REFERENCE" ]; then
  diffs=$("$PY" - "$T/src" "$REFERENCE" <<'EOF'
import hashlib, json, sys
from pathlib import Path
src, ref = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())["source"]["export_files_sha256"]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
now = {str(p.relative_to(src)): sha(p) for p in sorted(src.rglob("*"))
       if p.is_file() and ".spectrafit_reports" not in p.parts and "__pycache__" not in p.parts}
bad = sorted(set(now) ^ set(ref)) + sorted(k for k in set(now) & set(ref) if now[k] != ref[k])
print(len(now), len(bad)); [print(b) for b in bad[:20]]
EOF
)
  n=$(echo "$diffs" | head -1 | cut -d' ' -f1); nbad=$(echo "$diffs" | head -1 | cut -d' ' -f2)
  if [ "$nbad" = 0 ]; then pass "export identical to the export of record ($n files, $(basename "$(dirname "$REFERENCE")"))"
  else fail "export differs from the export of record in $nbad files"; echo "$diffs" | tail -n +2 | raw; fi
fi

# ---------------------------------------------------------------- 3 backends
if [ -d "$T/src/python" ]; then
  got=$(cd "$T/src" && PYTHONPATH=$T/src/python "$PY" -c "
import spectrafit_core, pathlib
assert 'site-packages' in pathlib.Path(spectrafit_core.__file__).parts, spectrafit_core.__file__
from oracles.backends import get_backends
print(' '.join(sorted(b.name for b in get_backends())))" 2>"$T/backends.err")
  if [ "$got" = "$EXPECTED_BACKENDS" ]; then pass "six backends load, spectrafit_core from the wheel: $got"
  else fail "backends [$got], expected [$EXPECTED_BACKENDS]"; raw < "$T/backends.err"; fi
fi

# ---------------------------------------------------------------- 4 host
say "      kernel $(uname -r), up $(uptime -p), clocksource $(cat /sys/devices/system/clocksource/clocksource0/current_clocksource 2>/dev/null)"
say "      /proc/stat $(head -1 /proc/stat)"
if [ -e /var/run/reboot-required ]; then fail "reboot required: update and reboot before measuring"
else pass "no reboot pending"; fi
for unit in apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service; do
  st=$(systemctl is-active "$unit" 2>/dev/null)
  if [ "$st" = active ]; then fail "$unit is active (stop or mask it for the run)"; else pass "$unit $st"; fi
done
if command -v docker >/dev/null 2>&1; then
  c=$(docker ps -q 2>/dev/null | wc -l)
  if [ "$c" = 0 ]; then pass "no running containers"; else fail "$c running containers"; docker ps 2>&1 | raw; fi
fi
sessions=$(pgrep -af 'vscode-server|copilot|claude|node ' 2>/dev/null | grep -v pgrep | cut -c1-140)
if [ -z "$sessions" ]; then pass "no editor or agent sessions"
elif [ "$ALLOW_SESSIONS" = --allow-sessions ]; then warn "sessions present; they must end before the chain starts"; echo "$sessions" | raw
else fail "editor or agent sessions present (--allow-sessions to only warn)"; echo "$sessions" | raw; fi
say "      load readings, 1 min apart"
for i in 1 2 3; do say "      $(date -u +%T) $(cat /proc/loadavg)"; [ $i -lt 3 ] && sleep 60; done
l1=$(cut -d' ' -f1 /proc/loadavg)
if awk "BEGIN{exit !($l1 < 0.5)}"; then pass "load $l1 < 0.5"; else fail "load $l1 >= 0.5"; fi
free_gb=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9)
if [ "$free_gb" -ge 20 ]; then pass "$free_gb GB free"; else fail "only $free_gb GB free"; fi
mmc=$(cat /proc/sys/vm/max_map_count)
if [ "$mmc" -ge 65530 ]; then pass "vm.max_map_count $mmc"; else fail "vm.max_map_count $mmc < 65530"; fi
mkdir -p "$(dirname "$LOCK")"
if ( flock -n 9 ) 9>"$LOCK"; then pass "benchmark lock free"; else fail "benchmark lock $LOCK held"; fi
env | grep -E '^(OMP|OPENBLAS|MKL|NUMEXPR|VECLIB|RAYON)_|^XLA_FLAGS|^JAX_PLATFORMS|^SPECTRAFIT_BENCH' | raw
say "      held packages: $(apt-mark showhold 2>/dev/null | tr '\n' ' ')"

say "# $FAILS failing check(s)"
exit $((FAILS > 0))
