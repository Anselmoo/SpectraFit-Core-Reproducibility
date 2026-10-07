#!/usr/bin/env python3
"""One point of the seed sweep: the release's own ``oracles.cli run``, at another seed.

spectrafit-core 0.1.2 ships no ``--seed`` and no ``--headline-only`` option. The
archived sweep (commit 0fd4b5d) used both, and they did exactly this in ``cli.run``::

    analyzed_ids = [featured_case(build_catalog(seed)).id] if headline_only else None
    report = build_report(..., seed=seed, analyzed_ids=analyzed_ids, ...)

The release's ``build_report`` still takes ``seed`` and ``analyzed_ids``. So this script
runs the release's ``cli.run`` function itself, unmodified, with the name
``build_report`` in its module bound to the same function plus those two arguments.
Everything else (backends, baseline, ``write_run``, ``audit.json``, ``run_audit``, the
resource line the drivers parse) is the release's code.

Run with the working directory and ``PYTHONPATH`` of an export of the release, as
``bench/seed_sweep.py`` does:

    PYTHONPATH=<export>/python python bench/_seed_point.py --seed 20260604 --reps 10 --mc 8
"""

from __future__ import annotations

import argparse
import functools
from pathlib import Path

import spectrafit_core

import oracles.cli as cli
from oracles.cases import build_catalog, featured_case


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--reps", type=int, required=True)
    ap.add_argument("--mc", type=int, required=True)
    args = ap.parse_args()

    # The compiled library must be the installed wheel, never a source tree on the path.
    if "site-packages" not in Path(spectrafit_core.__file__).parts:
        raise SystemExit(f"spectrafit_core imported from {spectrafit_core.__file__}, not from the wheel")

    analyzed_ids = [featured_case(build_catalog(args.seed)).id]  # == 0fd4b5d --headline-only
    cli.build_report = functools.partial(cli.build_report, seed=args.seed, analyzed_ids=analyzed_ids)
    print(f"seed={args.seed} reps={args.reps} mc={args.mc} analyzed_ids={analyzed_ids}", flush=True)
    # Every option passed explicitly: called as a function, typer's defaults are Option objects.
    cli.run(reps=args.reps, mc=args.mc, category="benchmark", backends=None, baseline=None)


if __name__ == "__main__":
    main()
