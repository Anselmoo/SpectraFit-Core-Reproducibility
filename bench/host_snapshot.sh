#!/bin/bash
# usage: host_snapshot.sh <label> <python>
# Prints a snapshot of the host to stdout, in the same sections as host/terra-*.txt,
# plus what matters to a timing run: load, other processes, the thread/XLA/budget
# variables, the apt timers, and the installed spectrafit-core wheel. Since release 1.2.0
# also: the /proc/stat cpu line (steal), the clock source behind perf_counter, swap,
# transparent huge pages, the kernel command line, running services and containers,
# editor/agent sessions, held packages, and a one-shot top (ps pcpu is a lifetime average).
set -uo pipefail
LABEL=${1:?label}; PY=${2:?python}
sec() { printf '\n===== %s =====\n' "$1"; }

echo "# terra host snapshot: $LABEL"
echo "# taken $(date -u +%FT%TZ) by $(id -un)@$(hostname)"
sec "uname -a";                 uname -a
sec "lsb_release -a";           lsb_release -a 2>/dev/null
sec "ldd --version";            ldd --version | head -1
sec "libc6 / libm"
dpkg-query -W -f='${Package} ${Version}\n' libc-bin libc6 libgcc-s1 libgfortran5 libstdc++6 2>/dev/null
sha256sum /lib/x86_64-linux-gnu/libm.so.6 /lib/x86_64-linux-gnu/libc.so.6
sec "lscpu";                    lscpu
sec "cpu flags (cpu0)";         grep -m1 '^flags' /proc/cpuinfo
sec "vm.max_map_count";         cat /proc/sys/vm/max_map_count
sec "ulimit -a";                ulimit -a
sec "free -h";                  free -h
sec "df -h";                    df -h / "$HOME"
sec "uptime / loadavg";         uptime; cat /proc/loadavg
sec "processes (top 20 by cpu)"; ps -eo pid,etimes,pcpu,pmem,comm --sort=-pcpu | head -21
sec "tmux sessions";            tmux ls 2>&1
sec "thread / XLA / budget variables (empty = unset)"
for v in OMP_NUM_THREADS OPENBLAS_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS \
         VECLIB_MAXIMUM_THREADS RAYON_NUM_THREADS XLA_FLAGS JAX_PLATFORMS \
         SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET; do
  printf '%s=%s\n' "$v" "${!v-}"
done
sec "apt timers";               systemctl list-timers 'apt-daily*' --all --no-pager 2>&1
sec "unattended-upgrades";      systemctl is-enabled unattended-upgrades 2>&1; systemctl is-active unattended-upgrades 2>&1
sec "tool versions"
uv --version; "$PY" -V; (rustc --version 2>/dev/null || echo "rustc absent"); git --version
sec "python packages (benchmark environment)"
"$PY" - <<'EOF'
import importlib.metadata as md, hashlib, pathlib
for p in ["spectrafit-core", "lmfit", "scipy", "numpy", "jax", "jaxlib", "optimistix", "pytest", "matplotlib"]:
    print(p, md.version(p))
d = md.distribution("spectrafit-core")
rec = pathlib.Path(d._path) / "RECORD"
print("spectrafit-core RECORD sha256", hashlib.sha256(rec.read_bytes()).hexdigest())
so = next(f for f in d.files if str(f).endswith(".so"))
print("spectrafit-core", so, hashlib.sha256(pathlib.Path(d.locate_file(so)).read_bytes()).hexdigest())
EOF
sec "/proc/stat cpu (user nice system idle iowait irq softirq steal guest guest_nice)"; head -1 /proc/stat
sec "clocksource";              cat /sys/devices/system/clocksource/clocksource0/current_clocksource \
                                    /sys/devices/system/clocksource/clocksource0/available_clocksource 2>&1
sec "swap";                     swapon --show 2>&1; cat /proc/sys/vm/swappiness
sec "transparent huge pages";   cat /sys/kernel/mm/transparent_hugepage/enabled /sys/kernel/mm/transparent_hugepage/defrag 2>&1
sec "kernel command line";      cat /proc/cmdline
sec "cpu frequency (empty in a guest without cpufreq)"
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>&1
sec "pressure (cpu, memory, io)"; for r in cpu memory io; do echo "$r: $(head -1 /proc/pressure/$r 2>&1)"; done
sec "top -bn1 (current load, not lifetime averages)"; top -bn1 | head -25
sec "running services";         systemctl list-units --type=service --state=running --no-pager --no-legend 2>&1
sec "containers";               (docker ps --format '{{.Names}} {{.Image}} {{.Status}}' 2>&1 || echo "docker absent")
sec "editor / agent / node sessions"; pgrep -af 'vscode-server|claude|copilot|node' 2>&1 || echo "none"
sec "held packages";            apt-mark showhold 2>&1 || echo "none"
sec "reboot-required";          cat /var/run/reboot-required 2>/dev/null || echo "none"
sec "dpkg-query -W (all packages)"; dpkg-query -W
