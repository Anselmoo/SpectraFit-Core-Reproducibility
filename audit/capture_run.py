"""Run the benchmark harness unchanged and record each backend's raw end point.

Track F, package 07 fallback comparison (#93). The harness command is executed
in-process exactly as ``python -m oracles.cli run <args>`` would run it. The only
addition is an observer around each adapter's ``extract``: it writes, per fit,
the end-point parameters and the counters and flags the library itself reported
(``results.json`` carries neither nfev nor the raw library success flag). The
observer never changes the value ``extract`` returns.

    env -u VIRTUAL_ENV uv run --locked --no-sync python capture_run.py \
        --capture <dir>/capture.jsonl -- run --tolerance-mode common \
        --backends spectrafit,scipy-ls-trf,lmfit --reps 5 --mc 20

Fits of Monte-Carlo copies (case ids containing ``__mc``) are not recorded.
Every other fit is recorded with a per-(case, backend) sequence number; number 0
is the suite phase, later numbers are the analysed-case phase.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import sys
from pathlib import Path
from typing import Any

_SEQ: dict[tuple[str, str], int] = {}


def _num(v: Any) -> float | int | None:
    """JSON-safe number (non-finite -> None)."""
    if v is None:
        return None
    if isinstance(v, bool | int):
        return int(v)
    f = float(v)
    return f if math.isfinite(f) else None


def _raw_fields(backend: str, raw: Any) -> dict[str, Any]:
    """The library's own end-point report, by backend."""
    match backend:
        case "spectrafit":
            result, _best = raw
            return {
                "lib_success": bool(result.success),
                "message": str(result.message),
                "n_iter": _num(result.n_iter),
                "n_func_evals": _num(result.n_func_evals),
                "n_jac_evals": _num(result.n_jac_evals),
                "n_de_generations": _num(getattr(result, "n_de_generations", None)),
                "params": {k: _num(v.value) for k, v in result.parameters.items()},
            }
        case "lmfit":
            return {
                "lib_success": bool(raw.success),
                "message": str(raw.message),
                "ier": _num(getattr(raw, "ier", None)),
                "lmdif_message": getattr(raw, "lmdif_message", None),
                "method": str(getattr(raw, "method", "")),
                "nfev": _num(getattr(raw, "nfev", None)),
                "nit": _num(getattr(raw, "nit", None)),
                "params": {k: _num(p.value) for k, p in raw.params.items()},
            }
        case _:
            return {
                "lib_success": bool(raw.success),
                "message": str(getattr(raw, "message", "")),
                "status": _num(getattr(raw, "status", None)),
                "nfev": _num(getattr(raw, "nfev", None)),
                "njev": _num(getattr(raw, "njev", None)),
                "active_mask": [int(a) for a in getattr(raw, "active_mask", [])],
                "x": [_num(v) for v in raw.x],
            }


def install(capture: Path) -> None:
    """Wrap ``extract`` of the three adapters; append one JSON line per fit."""
    from oracles.backends._lmfit import LmfitBackend
    from oracles.backends._scipy_ls import ScipyLeastSquaresBackend
    from oracles.backends._spectrafit import SpectraFitBackend

    fh = capture.open("a", encoding="utf-8")

    for cls in (SpectraFitBackend, LmfitBackend, ScipyLeastSquaresBackend):
        original = cls.extract

        @functools.wraps(original)
        def extract(self: Any, raw: Any, case: Any, _orig: Any = original) -> Any:
            outcome = _orig(self, raw, case)
            if "__mc" not in case.id:
                key = (case.id, self.name)
                seq = _SEQ.get(key, 0)
                _SEQ[key] = seq + 1
                rec = {
                    "case": case.id,
                    "category": case.category,
                    "solver_hint": case.solver_hint,
                    "backend": self.name,
                    "seq": seq,
                    "outcome_success": bool(outcome.success),
                    "outcome_chi2": _num(outcome.chi2),
                    "outcome_reduced_chi2": _num(outcome.reduced_chi2),
                    "outcome_n_iter": _num(outcome.n_iter),
                    "outcome_params": {k: _num(v) for k, v in outcome.params.items()},
                    "best_fit": [_num(v) for v in outcome.best_fit],
                    "raw": _raw_fields(self.name, raw),
                }
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            return outcome

        cls.extract = extract


def main() -> int:
    """Install the observer, then hand the remaining arguments to ``oracles.cli``."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("cli_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cli_args = args.cli_args[1:] if args.cli_args[:1] == ["--"] else args.cli_args
    install(args.capture)
    from oracles.cli import main as cli_main

    return cli_main(cli_args)


if __name__ == "__main__":
    sys.exit(main())
