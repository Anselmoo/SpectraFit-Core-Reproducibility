"""Target nist-params: parameter values of SpectraFit-Core and lmfit on the NIST StRD problems.

Fits every NIST StRD problem of the release's audit registry from Start 2 at the shipped
tolerance, once with SpectraFit-Core and once with lmfit (leastsq), exactly as
``reproducibility/figures/nist_table2.py`` of the release does, and stores the fitted
parameter values of both libraries next to the certified values and certified standard
deviations. ``results/nist_table2.json`` stores per-parameter values for neither library,
so statements that compare the two libraries parameter by parameter cannot be derived
from it.

Guard: the worst log relative error (LRE) recomputed from the stored values must equal the
spectrafit_core and lmfit columns of ``results/nist_table2.json`` cell for cell. If a cell
differs, the values do not belong to Table 1 of the article; the script exits non-zero and
writes nothing.

Run (from the repository root, after the source export exists):
    uv run --locked python scripts/nist_params.py --source <export dir> --out results/nist-params
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True, help="export of the pinned spectrafit-core tag")
    ap.add_argument("--table", type=Path, default=Path("results/nist_table2.json"))
    ap.add_argument("--out", type=Path, default=Path("results/nist-params"))
    a = ap.parse_args()

    # the installed wheel provides spectrafit_core; the export provides the harness and the NIST fixtures
    sys.path.insert(0, str(a.source / "reproducibility" / "figures"))
    sys.path.append(str(a.source / "python"))
    import nist_table2 as nt
    from oracles.audit.nist import _RECIPES

    table = {d["name"]: d["columns"] for d in json.loads(a.table.read_text())["datasets"]}
    rows, mismatch = {}, []
    for recipe in _RECIPES:
        name = recipe.name
        v_sfc, se_sfc = nt.fit_spectrafit(recipe)
        v_lm = nt.fit_lmfit(recipe)
        fx = importlib.import_module(f"oracles.nist_strd.{name.lower()}")
        rows[name] = {
            "certified": {k: {"value": v[0], "sd": v[1]} for k, v in fx.CERTIFIED.items()},
            "spectrafit_core": {"values": v_sfc, "stderr": se_sfc},
            "lmfit": {"values": v_lm},
        }
        for col, vals in (("spectrafit_core", v_sfc), ("lmfit", v_lm)):
            want = table[name][col]
            got = nt.worst_lre(vals, recipe)
            if want is not None and got != want:
                mismatch.append({"dataset": name, "column": col, "table": want, "recomputed": got})
    if mismatch:
        print(json.dumps({"guard": "FAILED", "mismatch": mismatch}, indent=1))
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    rec = {
        "schema": "nist-params/1",
        "start": nt.START,
        "tolerance": nt.TOL,
        "max_iterations": nt.MAX_IT,
        "host": {"node": platform.node(), "machine": platform.machine(), "python": platform.python_version()},
        "guard": "worst LRE of both libraries recomputed from these values equals results/nist_table2.json cell for cell",
        "datasets": rows,
    }
    (a.out / "nist_params.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(f"guard passed for {len(rows)} datasets; wrote {a.out / 'nist_params.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
