#!/usr/bin/env python3
"""Smoke run of the short usage code the archive documents, against the installed wheel.

* ``usage/quick_start.py``: the single-Gaussian quick start, the Python block of
  ``docs/getting-started/quickstart.md`` of spectrafit-core byte for byte. It runs unchanged as
  ``python usage/quick_start.py``; the values it prints are compared with the "Expected output"
  block of that page (``usage/expected.json``, relative tolerance per script).
* ``scripts/fig_eels.py``, constrained graph: the Fe L2,3 model with its four relationships
  (``fig_eels.TIES``, four ``bind()`` edges), fitted once from the default start with
  ``FitOptions(solver="lm")``. Checked: the fit returns, and each relationship holds at the
  endpoint to ``1e-9`` relative. The full ``fig_eels.py`` run is the ``core`` target.

Writes ``<out>/usage.json`` with exit code, wall time, stdout, the compared values and pass or
fail per check; exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EXPECTED = HERE / "usage" / "expected.json"
PARAM = re.compile(r"'([\w.]+)': ParameterResult\(value=([-+0-9.eE]+|nan|inf).*?stderr=([-+0-9.eE]+|nan|inf|None)\)")


def quick_start(spec: dict) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, "usage/quick_start.py"], cwd=HERE, capture_output=True, text=True,
                          check=False)
    wall = time.perf_counter() - t0
    out = proc.stdout.strip().splitlines()
    got: dict[str, float | None] = {}
    if proc.returncode == 0 and out:
        for key, value, stderr in PARAM.findall(proc.stdout):
            got[key] = float(value)
            got[f"{key}.stderr"] = None if stderr == "None" else float(stderr)
        try:
            got["r_squared"] = float(out[-1])
        except ValueError:
            got["r_squared"] = None
    compared = {}
    for key, want in spec["values"].items():
        have = got.get(key)
        ok = have is not None and abs(have - want) <= spec["rel_tol"] * abs(want)
        compared[key] = {"expected": want, "observed": have, "ok": ok,
                         "rel_diff": None if have is None else abs(have - want) / abs(want)}
    return {"script": "usage/quick_start.py", "exit_code": proc.returncode, "wall_s": round(wall, 3),
            "stdout": proc.stdout, "stderr_tail": proc.stderr.splitlines()[-20:], "rel_tol": spec["rel_tol"],
            "compared": compared, "ok": proc.returncode == 0 and all(c["ok"] for c in compared.values())}


def eels_constrained(spectrum: Path) -> dict:
    t0 = time.perf_counter()
    spec = importlib.util.spec_from_file_location("fig_eels", HERE / "scripts" / "fig_eels.py")
    fe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fe)
    from spectrafit_core import FitOptions, MeasurementData, fit

    x, y = fe.read_msa(spectrum)
    keep = (x >= fe.WINDOW_EV[0]) & (x <= fe.WINDOW_EV[1])
    r = fit(fe.graph("constrained"), MeasurementData(x=x[keep].tolist(), y=y[keep].tolist()), FitOptions(solver="lm"))
    p = {k: v.value for k, v in r.parameters.items()}
    checks = {}
    for expr, target in fe.TIES:
        want = p["step_l3.amplitude"] / 2 if expr == "step_l3.amplitude / 2" else p[expr]
        checks[f"{target} = {expr}"] = {"target": p[target], "expression": want,
                                         "ok": abs(p[target] - want) <= 1e-9 * max(abs(want), 1.0)}
    return {"script": "scripts/fig_eels.py graph('constrained')", "wall_s": round(time.perf_counter() - t0, 3),
            "n_relationships": len(fe.TIES), "success": bool(r.success), "message": r.message,
            "r_squared": r.r_squared, "step_l3_amplitude": p["step_l3.amplitude"], "relationships": checks,
            "ok": len(fe.TIES) == 4 and all(c["ok"] for c in checks.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--spectrum", type=Path, required=True)
    args = ap.parse_args()
    expected = json.loads(EXPECTED.read_text())
    import spectrafit_core

    checks = [quick_start(expected["scripts"]["usage/quick_start.py"]), eels_constrained(args.spectrum)]
    record = {"schema": "usage-smoke/1", "spectrafit_core": spectrafit_core.__version__,
              "expected_source": expected["source"], "checks": checks}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "usage.json").write_text(json.dumps(record, indent=1) + "\n")
    for c in checks:
        print(f"  {'ok' if c['ok'] else 'FAILED':7s} {c['script']}  {c['wall_s']:.1f} s")
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
