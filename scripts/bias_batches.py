"""Target bias-batches: the serialisation-bias measurement with every timed batch kept.

``reproducibility/figures/measure_audit_bias.py`` of the release times one residual
evaluation of the ``gaussian`` model on two paths (pure NumPy, and the wheel round trip
through ``_wheel_eval``) as 7 timed batches each and keeps only the minimum. Its record
(``audit_bias.json``) therefore holds the per-evaluation values but not the batches they
were taken from. This script repeats the same measurement on the same grid and parameters,
with the same batch sizes and repeats, in the same order (NumPy first, then the wheel),
stores every batch time of both sides, and derives the per-evaluation values with the
release script's own expressions.

The model, batch sizes and repeats are local variables of the release's ``_bias()``, so
they are restated here. Before measuring, the script checks that the release script still
contains these lines verbatim and stops if one is missing. The grid ``_X`` and the
parameters ``_params_for`` are imported from the release's
``tests/parity/test_kernel_parity.py``, as the release script imports them.

Host state is recorded as the timing chain records it (``bench/run_timing.sh``): the load
average and the aggregate ``cpu`` line of ``/proc/stat`` before and after each side (steal
is the 8th field), plus the busiest processes before the first and after the last batch.
The script holds the benchmark lock of the timing chain while it measures and stops if
another benchmark holds it.

Run (from the repository root, after the source export exists):
    uv run --locked --group audit python scripts/bias_batches.py --source <export dir> \
        --out results/bias-batches
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import subprocess
import sys
import timeit
from datetime import UTC, datetime
from pathlib import Path

UPSTREAM = Path("reproducibility") / "figures" / "measure_audit_bias.py"
PARITY = Path("tests") / "parity" / "test_kernel_parity.py"
LOCK = Path.home() / ".cache" / "terra-bench.lock"

# The measurement as _bias() of the release states it; each line must occur verbatim there.
KEY, N, N_W, REPEAT = "gaussian", 2000, 200, 7
UPSTREAM_LINES = (
    'key = "gaussian"',
    "n, n_w, repeat = 2000, 200, 7",
    "t_np = min(timeit.repeat(lambda: model.one(_X, params), number=n, repeat=repeat)) / n",
    "timeit.repeat(lambda: _wheel_eval(key, _X, params), number=n_w, repeat=repeat),",
    "/ n_w",
    '"numpy_us": t_np * 1e6,',
    '"wheel_us": t_wh * 1e6,',
    '"ratio": t_wh / t_np,',
)
CPU_FIELDS = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice")


def utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host_state() -> dict:
    """Load average and the aggregate cpu line of /proc/stat, as bench/run_timing.sh records them."""
    load = Path("/proc/loadavg").read_text().split()[:3]
    cpu = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    return {"utc": utc(), "load": [float(x) for x in load], "proc_stat_cpu": [int(x) for x in cpu]}


def busiest() -> list[str]:
    proc = subprocess.run(["ps", "-eo", "pid,nlwp,pcpu,rss,comm", "--sort=-pcpu"],
                          capture_output=True, text=True, check=False)
    return proc.stdout.splitlines()[:12]


def delta(a: dict, b: dict) -> dict[str, int]:
    return {k: y - x for k, x, y in zip(CPU_FIELDS, a["proc_stat_cpu"], b["proc_stat_cpu"], strict=False)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True, help="export of the pinned spectrafit-core tag")
    ap.add_argument("--reference", type=Path, default=Path("results/timing/audit_bias.json"),
                    help="audit_bias.json of record, shown next to this run")
    ap.add_argument("--out", type=Path, default=Path("results/bias-batches"))
    a = ap.parse_args()

    upstream = (a.source / UPSTREAM).read_text()
    missing = [ln for ln in UPSTREAM_LINES if ln not in upstream]
    if missing:
        print(json.dumps({"upstream_check": "FAILED", "missing_lines": missing}, indent=1))
        return 1

    # As the release script: the harness on the path, the parity test's grid and parameters.
    sys.path.insert(0, str(a.source / PARITY.parent))
    sys.path.append(str(a.source / "python"))
    from oracles.models import _wheel_eval, get_model
    from test_kernel_parity import _X, _params_for

    model = get_model(KEY)
    params = _params_for(KEY)

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"benchmark lock {LOCK} is held by another benchmark")
            return 3
        procs_before = busiest()
        s0 = host_state()
        numpy_batches = timeit.repeat(lambda: model.one(_X, params), number=N, repeat=REPEAT)
        s1 = host_state()
        wheel_batches = timeit.repeat(lambda: _wheel_eval(KEY, _X, params), number=N_W, repeat=REPEAT)
        s2 = host_state()
        procs_after = busiest()

    # The release script's expressions, applied to the stored batches.
    t_np = min(numpy_batches) / N
    t_wh = min(wheel_batches) / N_W
    derived = {"numpy_us": t_np * 1e6, "wheel_us": t_wh * 1e6, "ratio": t_wh / t_np, "n_points": int(_X.size)}

    reference = None
    if a.reference.exists():
        reference = {"file": a.reference.as_posix(), "sha256": sha256(a.reference),
                     "bias": json.loads(a.reference.read_text())["bias"]}
    a.out.mkdir(parents=True, exist_ok=True)
    rec = {
        "schema": "bias-batches/1",
        "model": KEY,
        "n_points": int(_X.size),
        "upstream": {"script": UPSTREAM.as_posix(), "sha256": sha256(a.source / UPSTREAM),
                     "parity_module": PARITY.as_posix(), "parity_module_sha256": sha256(a.source / PARITY),
                     "lines_checked": list(UPSTREAM_LINES)},
        "numpy": {"evaluations_per_batch": N, "repeat": REPEAT, "batch_s": numpy_batches,
                  "per_evaluation_us": [t / N * 1e6 for t in numpy_batches],
                  "host_start": s0, "host_end": s1, "proc_stat_cpu_delta": delta(s0, s1)},
        "wheel": {"evaluations_per_batch": N_W, "repeat": REPEAT, "batch_s": wheel_batches,
                  "per_evaluation_us": [t / N_W * 1e6 for t in wheel_batches],
                  "host_start": s1, "host_end": s2, "proc_stat_cpu_delta": delta(s1, s2)},
        "derived_as_release": derived,
        "reference": reference,
        "busiest_processes": {"before": procs_before, "after": procs_after},
        "host": {"node": platform.node(), "machine": platform.machine(), "python": platform.python_version(),
                 "threads": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                            "MKL_NUM_THREADS", "RAYON_NUM_THREADS")}},
    }
    (a.out / "bias_batches.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(f"numpy {derived['numpy_us']:.3f} us/eval, wheel {derived['wheel_us']:.3f} us/eval, "
          f"ratio {derived['ratio']:.2f}; wrote {a.out / 'bias_batches.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
