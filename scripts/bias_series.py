"""Target bias-series: the serialisation-bias measurement of bias-batches, repeated N times.

Runs ``scripts/bias_batches.py`` N times (default 1000), each time in a fresh process with
the same interpreter, pinned to CPU 2 with ``taskset -c 2``. ``bias_batches.py`` is run
unchanged: it checks the release script's lines, holds the benchmark lock of the timing
chain while it measures, and derives the per-evaluation values with the release script's
own expressions (``derived_as_release``: minimum of 7 batches per side).

Per run, one JSON line is appended to ``runs.jsonl`` as soon as the run ends: run index,
UTC start, exit code, wall time, ``numpy_us``, ``wheel_us`` and ``ratio`` as
``bias_batches.py`` derives them, the 7 batch times of both sides, and the host state before
and after the run: load average, the aggregate ``cpu`` line of ``/proc/stat`` (steal is the
8th field), ``scaling_cur_freq`` and ``scaling_governor`` of CPU 2 (null where the host has
no cpufreq interface), and the summed utime+stime of every process named ``claude``
(from ``/proc/<pid>/stat``). ``--resume`` continues after the last complete line.

At the end ``bias_series.json`` (schema ``bias-series/1``) holds the summary of the runs that
completed: median, 5th and 95th percentile, minimum and maximum of ``numpy_us``,
``wheel_us`` and ``ratio``; the median of runs 1-100 and of the last 100 runs; the CPU
seconds of the ``claude`` processes during the runs; the maximum load and steal fraction;
the frequency range and the governor. The values of ``results/timing/audit_bias.json`` and
``results/bias-batches/bias_batches.json`` are copied next to it, with their SHA-256, for
reference. ``README.md`` and ``run.json`` are written through ``scripts/run_record.py``.

Run (from the repository root, after the source export exists):
    uv run --locked --group audit python scripts/bias_series.py --source <export dir> \
        --n 1000 --out results/bias-series
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import run_record

BIAS_SCRIPT = HERE / "scripts" / "bias_batches.py"
UPSTREAM = Path("reproducibility") / "figures" / "measure_audit_bias.py"
AUDIT_BIAS = HERE / "results" / "timing" / "audit_bias.json"
BIAS_BATCHES = HERE / "results" / "bias-batches" / "bias_batches.json"
CPU = 2
CPUFREQ = Path(f"/sys/devices/system/cpu/cpu{CPU}/cpufreq")
CLK_TCK = os.sysconf("SC_CLK_TCK")
QUANTITIES = ("numpy_us", "wheel_us", "ratio")
DRIFT_WINDOW = 100


def utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def claude_cpu_s() -> dict[str, float]:
    """utime+stime in seconds of every process whose name (comm) is ``claude``, by pid."""
    out = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        stat = read(d / "stat")
        if stat is None:
            continue
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        if comm != "claude":
            continue
        fields = stat[stat.rindex(")") + 2:].split()  # fields from the 3rd (state) on
        out[d.name] = (int(fields[11]) + int(fields[12])) / CLK_TCK  # 14th and 15th field
    return out


def host_state() -> dict:
    freq = read(CPUFREQ / "scaling_cur_freq")
    claude = claude_cpu_s()
    return {
        "utc": utc(),
        "load": [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]],
        "proc_stat_cpu": [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]],
        "cpu2_scaling_cur_freq_khz": int(freq) if freq else None,
        "cpu2_scaling_governor": read(CPUFREQ / "scaling_governor"),
        "claude_cpu_s": {"sum": round(sum(claude.values()), 2), "by_pid": claude},
    }


def steal_fraction(before: dict, after: dict) -> float | None:
    """Steal share of the aggregate CPU time between two /proc/stat cpu lines (fields 1-8)."""
    d = [b - a for a, b in zip(before["proc_stat_cpu"][:8], after["proc_stat_cpu"][:8], strict=True)]
    return d[7] / sum(d) if sum(d) > 0 else None


def claude_delta(before: dict, after: dict) -> float:
    """CPU seconds the claude processes used during a run (processes started meanwhile count in full)."""
    b, a = before["claude_cpu_s"]["by_pid"], after["claude_cpu_s"]["by_pid"]
    return sum(v - b.get(pid, 0.0) for pid, v in a.items())


def one_run(index: int, source: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="bias-series-") as tmp:
        before = host_state()
        t0 = time.perf_counter()
        proc = subprocess.run(
            ["taskset", "-c", str(CPU), sys.executable, str(BIAS_SCRIPT), "--source", str(source),
             "--reference", str(AUDIT_BIAS), "--out", tmp],
            cwd=source / UPSTREAM.parent, capture_output=True, text=True, check=False)
        wall = time.perf_counter() - t0
        after = host_state()
        rec = {"run": index, "start_utc": before["utc"], "returncode": proc.returncode, "wall_s": round(wall, 3)}
        out = Path(tmp) / "bias_batches.json"
        if proc.returncode == 0 and out.exists():
            b = json.loads(out.read_text())
            rec |= {k: b["derived_as_release"][k] for k in QUANTITIES}
            rec |= {"numpy_batch_s": b["numpy"]["batch_s"], "wheel_batch_s": b["wheel"]["batch_s"]}
        else:
            rec["output_tail"] = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
        rec |= {"host_before": before, "host_after": after,
                "steal_fraction": steal_fraction(before, after),
                "claude_cpu_s_during_run": round(claude_delta(before, after), 2)}
        return rec


def complete_lines(path: Path) -> list[dict]:
    """The complete JSON lines of runs.jsonl; a partial last line is dropped from the file."""
    if not path.exists():
        return []
    raw = path.read_text()
    runs, keep = [], 0
    for line in raw.splitlines(keepends=True):
        if not line.endswith("\n"):
            break
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            break
        keep += len(line)
    if keep != len(raw):
        path.write_text(raw[:keep])
    return runs


def stats(values: list[float]) -> dict:
    v = np.asarray(values, dtype=float)
    return {"median": float(np.median(v)), "p5": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95)),
            "min": float(v.min()), "max": float(v.max())}


def reference(path: Path, key: str) -> dict | None:
    if not path.exists():
        return None
    return {"file": path.relative_to(HERE).as_posix(), "sha256": sha256(path),
            "values": {k: json.loads(path.read_text())[key][k] for k in (*QUANTITIES, "n_points")}}


def summary(runs: list[dict], n: int) -> dict:
    ok = [r for r in runs if r["returncode"] == 0 and "ratio" in r]
    first, last = ok[:DRIFT_WINDOW], ok[-DRIFT_WINDOW:]
    states = [s for r in runs for s in (r["host_before"], r["host_after"])]
    freqs = [s["cpu2_scaling_cur_freq_khz"] for s in states if s["cpu2_scaling_cur_freq_khz"] is not None]
    steals = [r["steal_fraction"] for r in runs if r["steal_fraction"] is not None]
    return {
        "schema": "bias-series/1",
        "n": n,
        "n_completed": len(ok),
        "n_failed": len(runs) - len(ok),
        "failed_runs": [r["run"] for r in runs if r not in ok],
        "cpu": CPU,
        "percentiles": "numpy.percentile, linear interpolation",
        "stats": {k: stats([r[k] for r in ok]) for k in QUANTITIES} if ok else None,
        "drift": {f"median_runs_1_{DRIFT_WINDOW}": {k: float(np.median([r[k] for r in first])) for k in QUANTITIES},
                  f"median_last_{DRIFT_WINDOW}": {k: float(np.median([r[k] for r in last])) for k in QUANTITIES},
                  "last_runs": [last[0]["run"], last[-1]["run"]]} if ok else None,
        "host": {
            "first_start_utc": runs[0]["start_utc"] if runs else None,
            "last_end_utc": runs[-1]["host_after"]["utc"] if runs else None,
            "claude_cpu_s_during_runs": round(sum(r["claude_cpu_s_during_run"] for r in runs), 2),
            "max_load_1min": max(s["load"][0] for s in states) if states else None,
            "max_steal_fraction": max(steals) if steals else None,
            "cpu2_scaling_cur_freq_khz": [min(freqs), max(freqs)] if freqs else None,
            "cpu2_scaling_governor": sorted({s["cpu2_scaling_governor"] for s in states
                                             if s["cpu2_scaling_governor"] is not None}) or None,
        },
        "bias_batches_script_sha256": sha256(BIAS_SCRIPT),
        "reference": {"audit_bias": reference(AUDIT_BIAS, "bias"),
                      "bias_batches": reference(BIAS_BATCHES, "derived_as_release")},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True, help="export of the pinned spectrafit-core tag")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--out", type=Path, default=Path("results/bias-series"))
    ap.add_argument("--resume", action="store_true", help="continue after the last complete line of runs.jsonl")
    a = ap.parse_args()
    source, out = a.source.resolve(), a.out.resolve()
    runs_path = out / "runs.jsonl"

    runs = complete_lines(runs_path)
    if runs and not a.resume:
        print(f"{runs_path} already holds {len(runs)} runs; pass --resume to continue")
        return 2
    command = f"scripts/bias_series.py --source <export> --n {a.n} --out {a.out.as_posix()}"
    with run_record.Run(out, "bias-series", command,
                        f"The serialisation-bias measurement of bias-batches, run {a.n} times, each in a "
                        f"fresh process pinned to CPU {CPU}, with the host state before and after every run.") as r:
        r.notes.append(f"script sha256 {sha256(Path(__file__))}; bias_batches.py sha256 {sha256(BIAS_SCRIPT)}; "
                       f"upstream measure_audit_bias.py sha256 {sha256(source / UPSTREAM)}")
        if runs:
            r.notes.append(f"resumed after run {runs[-1]['run']}; start time and wall time above are those "
                           f"of the resumed part")
        t0, start = time.perf_counter(), len(runs)
        with runs_path.open("a") as fh:
            for i in range(len(runs) + 1, a.n + 1):
                rec = one_run(i, source)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                runs.append(rec)
                status = (f"ratio {rec['ratio']:.2f}" if "ratio" in rec else f"FAILED (exit {rec['returncode']})")
                print(f"run {i}/{a.n}: {rec['wall_s']:.2f} s, {status}", flush=True)
        executed, elapsed = len(runs) - start, time.perf_counter() - t0
        rec = summary(runs, a.n)
        (out / "bias_series.json").write_text(json.dumps(rec, indent=1) + "\n")
        r.notes.append(f"{rec['n_completed']} of {a.n} runs completed; failed runs: {rec['failed_runs'] or 'none'}")
    if executed:
        per_run = elapsed / executed
        print(f"{per_run:.2f} s per run; extrapolated wall time for N=1000: {per_run * 1000:.0f} s "
              f"({per_run * 1000 / 3600:.2f} h)")
    return 0 if rec["n_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
