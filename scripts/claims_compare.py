#!/usr/bin/env python3
"""Every claim of the archived ``claims-report.json`` next to the value of a new run.

For each claim id of either report: the statement (as written, never edited), the archived
observed value and pass or fail, the new observed value and pass or fail, and whether the value
changed. Claims computed from the stored timing measurement (``source`` ``measured-<version>``:
``results/timing/``) are not measured by a new run; they are listed as such, with the new run's
own value of a structural quantity where one exists (``--extra`` JSON: claim id -> value and note).

Writes ``<out>.json`` and ``<out>.md``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def short(v: object, n: int = 160) -> str:
    s = json.dumps(v, sort_keys=True, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--extra", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    old = {c["id"]: c for c in json.loads(args.old.read_text())}
    new = {c["id"]: c for c in json.loads(args.new.read_text())}
    extra = json.loads(args.extra.read_text()) if args.extra else {}
    rows = []
    for cid in [*old, *(k for k in new if k not in old)]:
        o, n = old.get(cid), new.get(cid)
        stored = (n or o)["source"] != "regenerated"
        row = {"id": cid, "statement": (n or o)["statement"], "source": (n or o)["source"],
               "archived": None if o is None else o["observed"], "archived_ok": None if o is None else o["ok"],
               "new": None if n is None else n["observed"], "new_ok": None if n is None else n["ok"]}
        if o is None:
            row["status"] = "new claim"
        elif n is None:
            row["status"] = "replaced (not in the new report)"
        elif stored:
            row["status"] = f"not measured in this run (stored timing, {row['source']})"
        else:
            row["status"] = "unchanged" if o["observed"] == n["observed"] else "changed"
        if cid in extra:
            row["this_run"] = extra[cid]
        rows.append(row)
    args.out.with_suffix(".json").write_text(json.dumps(rows, indent=1) + "\n")
    lines = ["| id | statement | archived (1.2.0) | ok | this run | ok | status |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        this = short(r["new"]) if r["new"] is not None else "–"
        if "this_run" in r:
            this += f"<br>this run: {short(r['this_run'])}"
        lines.append(f"| {r['id']} | {r['statement']} | {short(r['archived']) if r['archived'] is not None else '–'} | "
                     f"{r['archived_ok']} | {this} | {r['new_ok']} | {r['status']} |")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines += ["", "Counts: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
              f"Failing in this run: {', '.join(r['id'] for r in rows if r['new_ok'] is False) or 'none'}"]
    args.out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-2:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
