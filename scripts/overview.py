#!/usr/bin/env python3
"""The overview report of the archive: ``overview.html`` and ``overview.pdf`` from the results of one run.

Generated from the files the other targets wrote; nothing in it is typed by hand. Every figure is
drawn here from a data file of the run, and every section names its data files. The HTML and the
PDF are rendered from one content list, so they hold the same captions, tables and figures.

Sections, in this order:

1. How the results are generated: every target with its command, inputs, output files and
   SHA-256; the archive commit, the wheel and its SHA-256.
2. NIST StRD: both certified starts, 22 datasets x 4 implementations (least accurate parameter,
   significant figures), and the rerun at 1e-15.
3. Benchmark: speed-up at the default and at the common stopping tolerance, the Jacobian ablation
   (analytic against finite-difference), and the benchmark figure.
4. Stationarity audit: summary counts and the table per case.
5. Bounded Fe L2,3 fit, 500 far starts, free and constrained model: the table per model and solver,
   reported success against verified stationary, the cumulative distribution of endpoint RSS with
   line D, the profile of ``step_l3.amplitude`` for both models, and the condition numbers and held
   components of the best stationary fits.
6. Gallery: per script the fits with parameters, success and stationarity, and its figures.

A section whose target did not run says so instead of showing numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MM = 1 / 25.4
A4 = (210 * MM, 297 * MM)
COLORS = {"ink": "#111111", "muted": "#4d4d4d", "rule": "#7a7a7a", "grid": "#d9d9d9", "fill": "#f2f2f2",
          "s1": "#0072b2", "s2": "#d55e00", "s3": "#008060", "s4": "#a8558a", "s5": "#b07800", "s6": "#2f8ac4",
          "bad": "#d55e00"}
ARM_COLORS = {"spectrafit": COLORS["s1"], "scipy-trf": COLORS["s2"], "lmfit-default": COLORS["s3"],
              "lmfit-common": COLORS["s4"]}
ARM_NAMES = {"spectrafit": "SpectraFit-Core (lm)", "scipy-trf": "SciPy trf", "lmfit-default": "lmfit leastsq",
             "lmfit-common": "lmfit leastsq, common tol."}
plt.style.use(HERE / "overview.mplstyle")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def fmt(v, digits: int = 4) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            return str(v)
        if v != 0 and (abs(v) >= 1e5 or abs(v) < 1e-3):
            return f"{v:.{digits - 1}e}".replace("-", "−")
        return f"{v:.{digits}g}".replace("-", "−")
    return str(v)


class Report:
    """A list of blocks: ("h", text), ("p", text), ("table", header, rows, note), ("fig", key, caption)."""

    def __init__(self, results: Path, out: Path) -> None:
        self.results, self.out = results, out
        self.blocks: list[tuple] = []
        self.figs: dict[str, callable] = {}

    def h(self, text: str) -> None:
        self.blocks.append(("h", text))

    def p(self, text: str) -> None:
        self.blocks.append(("p", text))

    def data(self, *paths: str) -> None:
        files = [p for p in paths if (self.results / p).exists()]
        if files:
            self.blocks.append(("data", files))

    def table(self, header: list[str], rows: list[list], note: str = "") -> None:
        self.blocks.append(("table", header, [[fmt(c) for c in r] for r in rows], note))

    def fig(self, key: str, draw, caption: str, size_mm: tuple[float, float]) -> None:
        self.figs[key] = (draw, size_mm)
        self.blocks.append(("fig", key, caption))

    # ---------------------------------------------------------------- rendering

    def save_figures(self) -> None:
        figdir = self.out / "figures"
        figdir.mkdir(parents=True, exist_ok=True)
        for key, (draw, (w, h)) in self.figs.items():
            fig = plt.figure(figsize=(w * MM, h * MM), layout="constrained")
            draw(fig)
            for ext in ("png", "pdf", "svg"):
                fig.savefig(figdir / f"{key}.{ext}", dpi=300 if ext == "png" else None)
            plt.close(fig)

    def html(self, title: str) -> str:
        parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
                 f"content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title><style>"
                 ":root{--ink:#111;--muted:#4d4d4d;--rule:#d9d9d9;--fill:#f2f2f2;--bg:#fff}"
                 "@media (prefers-color-scheme:dark){:root:not([data-theme='light']){--ink:#ececec;--muted:#b0b0b0;"
                 "--rule:#3a3a3a;--fill:#222;--bg:#161616}}"
                 "body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Arial,'Liberation Sans',"
                 "'Nimbus Sans',sans-serif}main{max-width:980px;margin:0 auto;padding:24px 16px 64px}"
                 "h1{font-size:22px;font-weight:600;margin:0 0 4px}h2{font-size:17px;font-weight:600;margin:36px 0 8px;"
                 "border-top:1px solid var(--rule);padding-top:16px}p{margin:6px 0;max-width:820px}"
                 ".data{font-size:13px;color:var(--muted)}.data a{color:inherit}"
                 ".tw{overflow-x:auto;margin:8px 0}table{border-collapse:collapse;font-size:12.5px;"
                 "font-variant-numeric:tabular-nums}th,td{padding:3px 8px;border-bottom:1px solid var(--rule);"
                 "text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}"
                 "th{font-weight:600;background:var(--fill)}.note{font-size:12.5px;color:var(--muted)}"
                 "figure{margin:12px 0}figure img{max-width:100%;height:auto;background:#fff;"
                 "border:1px solid var(--rule)}figcaption{font-size:13px;color:var(--muted);max-width:820px}"
                 "</style></head><body><main>", f"<h1>{html.escape(title)}</h1>"]
        for b in self.blocks:
            match b[0]:
                case "h":
                    parts.append(f"<h2>{html.escape(b[1])}</h2>")
                case "p":
                    parts.append(f"<p>{html.escape(b[1])}</p>")
                case "data":
                    links = ", ".join(f"<a href='../{html.escape(f)}'><code>{html.escape(f)}</code></a>" for f in b[1])
                    parts.append(f"<p class='data'>Data: {links}</p>")
                case "table":
                    head = "".join(f"<th>{html.escape(c)}</th>" for c in b[1])
                    body = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in b[2])
                    parts.append(f"<div class='tw'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")
                    if b[3]:
                        parts.append(f"<p class='note'>{html.escape(b[3])}</p>")
                case "fig":
                    parts.append(f"<figure><img src='figures/{b[1]}.png' alt='{html.escape(b[2])}'>"
                                 f"<figcaption>{html.escape(b[2])} Vector: <a href='figures/{b[1]}.pdf'>PDF</a>, "
                                 f"<a href='figures/{b[1]}.svg'>SVG</a>.</figcaption></figure>")
        parts.append("</main></body></html>")
        return "".join(parts)

    def pdf(self, path: Path, title: str) -> None:
        """The same blocks on A4 pages: text and tables as text, figures redrawn as vector."""
        left, right, top, bottom = 18 * MM / A4[0], 1 - 18 * MM / A4[0], 1 - 18 * MM / A4[1], 16 * MM / A4[1]
        line = 4.2 * MM / A4[1]
        with PdfPages(path, metadata={"Title": title, "Creator": "scripts/overview.py"}) as pdf:
            state = {"fig": None, "y": top}

            def new_page():
                if state["fig"] is not None:
                    pdf.savefig(state["fig"])
                    plt.close(state["fig"])
                state["fig"] = plt.figure(figsize=A4)
                state["y"] = top

            def need(h):
                if state["fig"] is None or state["y"] - h < bottom:
                    new_page()

            def text(s, size=8.0, weight="normal", color=COLORS["ink"], family="sans-serif", width=110):
                import textwrap
                for ln in textwrap.wrap(s, width) or [""]:
                    need(line * size / 8)
                    state["fig"].text(left, state["y"], ln, fontsize=size, weight=weight, color=color,
                                      family=family, va="top")
                    state["y"] -= line * size / 8

            new_page()
            text(title, size=13, weight="bold")
            state["y"] -= line
            for b in self.blocks:
                match b[0]:
                    case "h":
                        state["y"] -= line
                        text(b[1], size=10.5, weight="bold")
                    case "p":
                        text(b[1])
                    case "data":
                        text("Data: " + ", ".join(b[1]), size=7, color=COLORS["muted"], width=140)
                    case "table":
                        widths = [max(len(str(c)) for c in col) for col in zip(b[1], *b[2])]
                        total = sum(widths) + 2 * len(widths)
                        size = max(4.2, min(7.0, 7.0 * 118 / max(total, 1)))
                        fmt_row = lambda r: "  ".join(str(c).rjust(w) if i else str(c).ljust(w)  # noqa: E731
                                                      for i, (c, w) in enumerate(zip(r, widths)))
                        text(fmt_row(b[1]), size=size, weight="bold", family="monospace", width=400)
                        for r in b[2]:
                            text(fmt_row(r), size=size, family="monospace", width=400)
                        if b[3]:
                            text(b[3], size=7, color=COLORS["muted"])
                        state["y"] -= line * 0.5
                    case "fig":
                        draw, (w, h) = self.figs[b[1]]
                        hh = h * MM / A4[1]
                        need(hh + 3 * line)
                        ax_rect = [left, state["y"] - hh, w * MM / A4[0], hh]
                        sub = state["fig"].add_axes(ax_rect)
                        sub.axis("off")
                        sf = state["fig"].add_subfigure(state["fig"].add_gridspec(1, 1)[0])
                        sf.set_facecolor("none")
                        sub.remove()
                        sf.bbox_relative.p0 = (ax_rect[0], ax_rect[1])
                        sf.bbox_relative.p1 = (ax_rect[0] + ax_rect[2], ax_rect[1] + ax_rect[3])
                        draw(sf)
                        state["y"] -= hh + line * 0.5
                        text(b[2], size=7, color=COLORS["muted"])
                        state["y"] -= line * 0.5
            pdf.savefig(state["fig"])
            plt.close(state["fig"])


# --------------------------------------------------------------------------- sections

TARGET_INPUTS = {
    "core": "release export: reproducibility/figures/nist_*.py, NIST fixtures, figure scripts; results/timing/; "
            "scripts/fig_eels.py with the EELSDB spectrum",
    "nist-both": "release export: reproducibility/figures/nist_table2.py and NIST fixtures",
    "usage": "usage/quick_start.py, usage/expected.json, scripts/fig_eels.py",
    "gallery": "examples/ (mirror, examples-manifest.json)",
    "eels-far": "scripts/fig_eels.py, scripts/eels_far_starts.py, the EELSDB spectrum",
    "bench-tolerance": "harness oracles of the release, bench/common_tolerance.py",
    "bench-ablation": "harness oracles of the release, bench/ablation_summary.py",
    "audit-stationarity": "harness oracles of the release, audit/capture_run.py, audit/stationarity.py",
}


def section_how(r: Report, archive: dict) -> None:
    r.h("1. How the results are generated")
    runs = {}
    for t in TARGET_INPUTS:
        rec = load(r.results / ("core-run.json" if t == "core" else f"{t}/run.json"))
        if rec:
            runs[t] = rec
    env = next(iter(runs.values()))["environment"] if runs else {}
    w = env.get("spectrafit_core", {})
    r.p("Every number below is computed by the harness of this archive (reproduce.py) from the installed "
        "spectrafit-core wheel; each target writes its own folder under results/ with a README.md and a run.json "
        "that record the command, the start and end time, the load, the host, the Python, the wheel and its "
        "SHA-256, and the SHA-256 of every file it wrote. This report is generated from those files.")
    r.table(["item", "value"], [
        ["archive commit", archive.get("commit")], ["archive working tree modified", archive.get("dirty")],
        ["spectrafit-core", w.get("version")], ["wheel SHA-256", w.get("wheel_sha256")],
        ["compiled extension SHA-256", (w.get("core_extension") or {}).get("sha256")],
        ["host", f"{env.get('host')} ({env.get('platform')}, {env.get('cores')} cores)"],
        ["Python", env.get("python")], ["NumPy, SciPy, lmfit", ", ".join(f"{k} {v}" for k, v in
                                                                        (env.get("packages") or {}).items())],
        ["thread caps", ", ".join(f"{k}={v}" for k, v in (env.get("threads") or {}).items())]])
    rows = []
    for t, rec in runs.items():
        files = rec.get("files_sha256", {})
        if t == "core":
            outs = [(n, sha256(r.results / n)) for n in ("nist_table2.json", "nist_table2_tol1e15.json",
                                                         "nist_head_to_head.json", "eels_fe2o3.json",
                                                         "claims-report.json") if (r.results / n).exists()]
        else:
            outs = [(f"{t}/{k}", v) for k, v in files.items() if not k.startswith("figures/")]
        for i, (name, digest) in enumerate(outs or [("–", None)]):
            rows.append([t if i == 0 else "", rec["command"] if i == 0 else "", TARGET_INPUTS[t] if i == 0 else "",
                         name, (digest or "–")[:16], f"{rec['wall_s']:.0f} s" if i == 0 else ""])
    r.table(["target", "command", "input", "output file", "SHA-256 (first 16)", "wall"], rows,
            "Full digests: run.json of each target and checksums.sha256 of the run.")


def section_nist(r: Report) -> None:
    r.h("2. NIST StRD: both certified starts")
    both = load(r.results / "nist-both" / "nist_table2_both.json")
    if not both:
        r.p("Target nist-both did not run.")
        return
    impls = both["implementations"]
    cells = {(c["dataset"], c["start"], c["implementation"]): c for c in both["cells"]}
    datasets = list(dict.fromkeys(c["dataset"] for c in both["cells"]))
    r.p("Significant figures of agreement of the least accurate parameter with NIST's certified values "
        "(log-relative error, capped at 15), from Start 1 and from Start 2, at ftol = xtol = gtol = "
        f"{both['tolerance']['ftol']:g}. Start 2 is the table of the article; Start 1 lies farther from the solution.")
    r.data("nist-both/nist_table2_both.json")
    header = ["dataset"] + [f"{s[-1]}: {i.replace('_core', '').replace('_', ' ')}" for s in both["starts"] for i in impls]
    rows = []
    for d in datasets:
        row = [d]
        for s in both["starts"]:
            for i in impls:
                c = cells.get((d, s, i))
                row.append(None if c is None or c.get("param_lre_min") is None else round(c["param_lre_min"], 2))
        rows.append(row)
    r.table(header, rows, "1/2 = Start 1/Start 2. – = no result.")
    r.table(["start", "implementation", "least accurate (sig. figs)", "dataset", "parameter", "not converged"],
            [[s["start"], s["implementation"], round(s["worst_param_lre"], 2) if s.get("worst_param_lre") is not None
              else None, s.get("dataset"), s.get("parameter"), ", ".join(f"{x['dataset']} ({x['termination'].split(':')[0]})" for x in s.get("not_converged") or []) or "–"]
             for s in both["summary"]])
    t12, t15 = load(r.results / "nist_table2.json"), load(r.results / "nist_table2_tol1e15.json")
    if t12 and t15:
        a = {d["name"]: d["columns"]["spectrafit_core"] for d in t12["datasets"]}
        b = {d["name"]: d["columns"]["spectrafit_core"] for d in t15["datasets"]}
        r.p("Rerun at 1e-15 (Start 2): spectrafit-core's least accurate parameter at the shipped tolerance 1e-12 "
            "and at 1e-15.")
        r.data("nist_table2.json", "nist_table2_tol1e15.json")
        r.table(["dataset", "1e-12", "1e-15", "change"],
                [[n, round(a[n], 2), round(b[n], 2), round(b[n] - a[n], 2)] for n in a])


def timing_flag(r: Report, target: str) -> None:
    rec = load(r.results / target / "run.json") or {}
    flag = rec.get("timing_flag")
    if flag:
        reason, decision = flag["reason"], flag.get("decision", "")
        r.p(f"Timing of this run: {flag['status']}. {reason[:1].upper()}{reason[1:]}. "
            f"{decision[:1].upper()}{decision[1:]}".strip())


def section_bench(r: Report) -> None:
    r.h("3. Benchmark: default and common tolerance, Jacobian ablation")
    tol = load(r.results / "bench-tolerance" / "summary.json")
    if tol:
        r.p("Speed-up of SpectraFit-Core against each comparator over the 160 cases: comparator time divided by "
            "SpectraFit-Core time per case, aggregated as the geometric mean and the median; 'like for like' keeps "
            "the cases on which both reach the same RSS within 1e-6 relative. Default = each library's own stopping "
            "tolerances; common = ftol = xtol = gtol = 1e-8 for every backend.")
        r.data("bench-tolerance/summary.json", "bench-tolerance/report.md", "bench-tolerance/default.json",
               "bench-tolerance/common.json")
        timing_flag(r, "bench-tolerance")
        rows = []
        for comp in tol["default"]:
            row = [comp]
            for mode in ("default", "common"):
                for k in ("all/all_cases", "all/like_for_like", "without_optfn/all_cases"):
                    v = tol[mode][comp][k]
                    row += [None if v["geomean"] is None else round(v["geomean"], 2), v["n"]]
            rows.append(row)
        r.table(["comparator", "default: all", "n", "like for like", "n", "without optfn", "n",
                 "common: all", "n", "like for like", "n", "without optfn", "n"], rows, "Geometric means.")
    else:
        r.p("Target bench-tolerance did not run.")
    abl = load(r.results / "bench-ablation" / "summary.json")
    if abl:
        r.p("Jacobian ablation: SpectraFit-Core with its analytic Jacobians (spectrafit) and with forced "
            "finite-difference Jacobians (spectrafit_fd), each against every comparator, like-for-like cases only "
            f"(same RSS within 1e-6 relative), {abl['n_cases']} cases.")
        r.data("bench-ablation/summary.json", "bench-ablation/per_case.json", "bench-ablation/manifest.json")
        timing_flag(r, "bench-ablation")
        r.table(["pair", "like-for-like cases", "geomean speed-up", "median speed-up"],
                [[k.replace("_vs_", " vs "), v["like_for_like_cases"], None if v["geomean_speedup"] is None
                  else round(v["geomean_speedup"], 2), None if v["median_speedup"] is None
                  else round(v["median_speedup"], 2)] for k, v in abl["pairs"].items()])
        r.table(["backend", "median of per-case median time (ms)"],
                [[b, round(v, 3)] for b, v in abl["median_med_ms"].items()])
    else:
        r.p("Target bench-ablation did not run.")
    fig3 = r.results.parent / "figures" / "figure3_benchmark.png"
    if fig3.exists():
        img = plt.imread(fig3)

        def draw(fig, img=img):
            ax = fig.add_subplot()
            ax.imshow(img)
            ax.axis("off")
        own = load(r.results / "timing" / "provenance.json")
        timing = own or load(ROOT / "results" / "timing" / "provenance.json") or {}
        source = timing.get("source") or {}
        where = ("results/timing/ of this run" if own
                 else "the stored results/timing/ of the archive (this run measured no timing)")
        r.fig("benchmark_profile", draw, "The benchmark figure (Figure 3 of the article), regenerated by the core "
              f"target from {where}: {timing.get('what', 'timing record not found')} (tag {source.get('tag', '?')}, "
              f"commit {str(source.get('commit', '?'))[:10]}); it is not drawn from the runs of this section.",
              (174, 174 * img.shape[0] / img.shape[1]))


def section_audit(r: Report) -> None:
    r.h("4. Stationarity audit of the benchmark endpoints")
    t = load(r.results / "audit-stationarity" / "table.json")
    if not t:
        r.p("Target audit-stationarity did not run.")
        return
    d = t["definitions"]
    r.p(f"Every endpoint of SpectraFit-Core, SciPy trf and lmfit at the common tolerance, {t['all']['n_cases']} cases. "
        f"Stationary: Gauss-Newton predicted decrease over the components not held, divided by RSS, at most "
        f"{d['GN_TOL']:g}; central-difference Jacobian, step {d['H_REL']:g} max(|theta|, {d['THETA_FLOOR']:g}); active "
        f"bound by the {d['AT_BOUND_REL']:g} rule. {len(t['excluded'])} cases excluded (reasons in table.json).")
    r.data("audit-stationarity/table.json", "audit-stationarity/table.md")
    rows = []
    for b, s in t["all"]["stationary"].items():
        sx = t["all"]["success_x_stationary"][b]["lib_success"]
        rows.append([b, f"{s['free']['stationary']}/{s['free']['n']}", f"{s['at_bound']['stationary']}/{s['at_bound']['n']}",
                     sx.get("success=True/stationary=True"), sx.get("success=True/stationary=False"),
                     sx.get("success=False/stationary=True"), sx.get("success=False/stationary=False")])
    r.table(["backend", "stationary, interior", "stationary, at a bound", "success & stationary",
             "success, not stationary", "no success, stationary", "neither"], rows,
            "success = the library's own success flag.")
    r.table(["pair", "cases", "median RSS ratio", "< 1", "= 1", "> 1"],
            [[k, v["n"], v["median"], v["lt1"], v["eq1"], v["gt1"]] for k, v in t["all"]["pairwise"].items()],
            "RSS ratio first/second; = 1 within 1e-6 relative.")
    rows = []
    for c in t["cases"]:
        row = [c["case"], c["category"]]
        for b in ("spectrafit", "scipy-ls-trf", "lmfit"):
            e = c["endpoints"].get(b) or {}
            row += [e.get("stationary"), e.get("gn_decrease_rel"), e.get("lib_success")]
        rows.append(row)
    r.table(["case", "category", "SFC stat.", "SFC GN", "SFC success", "trf stat.", "trf GN", "trf success",
             "lmfit stat.", "lmfit GN", "lmfit success"], rows)


def section_eels(r: Report) -> None:
    r.h("5. Bounded Fe L2,3 fit from 500 far starts")
    far = load(r.results / "eels-far" / "eels_far.json")
    summ = load(r.results / "eels-far" / "summary.json")
    if not far or not summ:
        r.p("Target eels-far did not run.")
        return
    dfn = summ["definitions"]
    r.p(f"The fit of scripts/fig_eels.py (Fe L2,3 edge of Fe2O3, 700 to 735 eV) from {dfn['n_starts']} far starts "
        f"(numpy default_rng([{dfn['seed']}, {dfn['stream']}]), fig_eels.sample_start), the same starts for the free "
        "model (34 free parameters) and the constrained model (four relationships, 30 free). Stationary: Gauss-Newton "
        f"measure at most {dfn['gn_tol']:g} within the bounds. Best known minimum: RSS "
        f"{dfn['best_known']['free']:.10g} (free), {dfn['best_known']['constrained']:.10g} (constrained); reaching it = "
        f"within {dfn['best_rel']:g} relative. D = {dfn['D_free']:.10g}, the RSS of the free fit from the default start.")
    r.data("eels-far/summary.json", "eels-far/eels_far.json")
    rows = []
    for model, per in summ["summary"].items():
        for arm, v in per.items():
            sp = v["step_l3_amplitude_stationary"] or {}
            rows.append([model, ARM_NAMES[arm], v["n"], v["stationary"], v["reported_success"],
                         v["reaching_best_known"], v.get("below_D_stationary", "–"),
                         f"{v['endpoints_with_amplitude_at_0']}/{v['amplitudes_at_0']}",
                         sp.get("q25"), sp.get("median"), sp.get("q75"), v["lowest_stationary_rss"]])
    r.table(["model", "solver", "fits", "stationary", "reported success", "best known", "below D, stationary",
             "amplitudes at 0 (fits/amplitudes)", "step_l3 q25", "median", "q75", "lowest stationary RSS"], rows,
            "step_l3 quartiles over the stationary endpoints.")
    fits = far["fits"]
    models = list(summ["summary"])
    arms = list(next(iter(summ["summary"].values())))

    def draw_success(fig):
        axs = fig.subplots(1, len(models), squeeze=False)[0]
        cells = [(True, True), (True, False), (False, True), (False, False)]
        labels = ["success, stationary", "success, not stationary", "no success, stationary", "neither"]
        for ax, model in zip(axs, models):
            m = np.zeros((4, len(arms)))
            for j, arm in enumerate(arms):
                sel = [f for f in fits if f["model"] == model and f["arm"] == arm and f["ok"]]
                for i, (s, st) in enumerate(cells):
                    m[i, j] = sum(bool(f.get("success")) == s and f["stationary"] == st for f in sel)
            ax.imshow(m, cmap="Greys", vmin=0, vmax=dfn["n_starts"] * 1.6, aspect="auto")
            for j in range(len(arms)):
                if m[1, j]:
                    ax.add_patch(plt.Rectangle((j - 0.5, 0.5), 1, 1, color=COLORS["bad"],
                                               alpha=0.15 + 0.85 * m[1, j] / dfn["n_starts"], lw=0))
            for i in range(4):
                for j in range(len(arms)):
                    ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=6, color=COLORS["ink"],
                            weight="bold" if i == 1 and m[i, j] else "normal")
            ax.set_xticks(range(len(arms)), [ARM_NAMES[a].replace(", ", ",\n") for a in arms], fontsize=5.5)
            ax.set_yticks(range(4), labels if ax is axs[0] else [""] * 4)
            ax.tick_params(length=0, which="both")
            ax.minorticks_off()
            ax.set_title(f"{model} model", fontsize=7)
            for s in ax.spines.values():
                s.set_visible(False)
    r.fig("eels_success_vs_stationary", draw_success, "Reported success against verified stationary endpoint, "
          f"counts of {dfn['n_starts']} fits per solver and model; the second row (success reported at an endpoint "
          "that is not stationary) in red.", (174, 62))

    def draw_ecdf(fig):
        axs = fig.subplots(1, len(models), squeeze=False)[0]
        for ax, model in zip(axs, models):
            for arm in arms:
                v = np.sort([f["rss"] for f in fits if f["model"] == model and f["arm"] == arm and f["ok"]])
                if v.size:
                    ax.step(np.r_[v[0], v], np.r_[0, np.arange(1, v.size + 1) / dfn["n_starts"]], where="post",
                            color=ARM_COLORS[arm], lw=1, label=ARM_NAMES[arm])
            ax.set_xscale("log")
            best = dfn["best_known"][model]
            for val, name in ([(dfn["D_free"], "D")] if model == "free" else []) + [(best, "best known")]:
                ax.axvline(val, color=COLORS["rule"], lw=0.5, ls=(0, (3, 2)))
                ax.text(val, 1.01, f" {name}", fontsize=5.5, color=COLORS["muted"], rotation=90, va="bottom", ha="center")
            ax.set_xlabel("Endpoint RSS (log)")
            ax.set_ylabel(f"Share of {dfn['n_starts']} fits")
            ax.set_ylim(0, 1)
            ax.set_title(f"{model} model", fontsize=7, pad=14)
        axs[-1].legend(loc="lower right", fontsize=5.5)
    r.fig("eels_rss_cdf", draw_ecdf, "Cumulative share of the fits that end below a given RSS, per solver; line D is "
          "the RSS of the free fit from the default start, line 'best known' the lowest stationary minimum known.",
          (174, 66))
    best_rel, d_cut = dfn["best_rel"], dfn["D_free"] * (1 - 1e-6)

    def outcome(f, model):
        if f["rss"] <= dfn["best_known"][model] * (1 + best_rel):
            return 0
        if model == "free" and f["stationary"] and f["rss"] < d_cut:
            return 1
        return 2 if f["stationary"] else 3

    out_labels = {"free": ["best known minimum", "stationary, below D", "stationary, other", "not stationary"],
                  "constrained": ["best known minimum", "", "stationary, other", "not stationary"]}

    def draw_best(fig):
        axs = fig.subplots(1, len(models), squeeze=False)[0]
        for ax, model in zip(axs, models):
            rows = [i for i in range(4) if out_labels[model][i]]
            m = np.zeros((len(rows), 2 * len(arms)))
            for j, arm in enumerate(arms):
                for f in fits:
                    if f["model"] == model and f["arm"] == arm and f["ok"]:
                        m[rows.index(outcome(f, model)), 2 * j + (0 if f.get("success") else 1)] += 1
            ax.imshow(m, cmap="Greys", vmin=0, vmax=dfn["n_starts"] * 1.6, aspect="auto")
            for i in range(len(rows)):
                for k in range(2 * len(arms)):
                    ax.text(k, i, int(m[i, k]), ha="center", va="center", fontsize=5.5, color=COLORS["ink"])
            ax.set_xticks(range(2 * len(arms)), ["success", "no success"] * len(arms), fontsize=5, rotation=90)
            for j, arm in enumerate(arms):
                ax.text(2 * j + 0.5, -0.6, ARM_NAMES[arm].replace(" (lm)", "\n(lm)").replace(", ", ",\n"),
                        ha="center", va="bottom", fontsize=5)
                if j:
                    ax.axvline(2 * j - 0.5, color=COLORS["rule"], lw=0.5)
            ax.set_yticks(range(len(rows)), [out_labels[model][i] for i in rows] if ax is axs[0] or model != models[0]
                          else [""] * len(rows))
            ax.tick_params(length=0, which="both")
            ax.minorticks_off()
            ax.set_title(f"{model} model", fontsize=7, pad=30)
            for s in ax.spines.values():
                s.set_visible(False)
    r.fig("eels_success_vs_best", draw_best, "Reported success against the endpoint reached, counts of "
          f"{dfn['n_starts']} fits per solver and model. Best known minimum: RSS within {best_rel:g} relative of "
          f"{dfn['best_known']['free']:.10g} (free) or {dfn['best_known']['constrained']:.10g} (constrained); "
          f"below D: stationary with RSS below D = {dfn['D_free']:.10g} by more than 1e-6 relative and not at the "
          "best known minimum (free model only, the ablation's M1 threshold).", (174, 78))
    eels = load(r.results / "eels_fe2o3.json")
    if eels and eels.get("profiles"):
        prof = eels["profiles"]

        def draw_profile(fig):
            axs = fig.subplots(1, 2, squeeze=False)[0]
            for ax, model, color in zip(axs, ("free", "constrained"), (COLORS["s1"], COLORS["s3"])):
                p = prof[model]
                pts = sorted((q["a"], q["rss"]) for q in p["points"] if q.get("rss") is not None)
                a, s = np.array(pts).T
                ax.plot(a, s - p["global_minimum"]["rss"], color=color, lw=1, marker="o", ms=1.5)
                for lev, ls in (("68", (0, (1, 1))), ("95", (0, (3, 2)))):
                    iv = p["intervals"].get(lev) or {}
                    for k in ("lower", "upper"):
                        x = iv.get(f"{k}_bisected", iv.get(k))
                        if x is not None:
                            ax.axvline(x, color=COLORS["rule"], lw=0.5, ls=ls)
                ax.set_xlabel("step_l3.amplitude (counts)")
                ax.set_ylabel("RSS − RSS_min")
                ax.set_title(f"{model} model", fontsize=7)
        r.fig("eels_profile", draw_profile, "Profile of step_l3.amplitude: the lowest RSS at each fixed value with every "
              "other parameter free (fig_eels.py protocol), minus the lowest RSS of the model; dotted and dashed lines: "
              "ends of the 68 % and 95 % intervals.", (174, 62))
        r.data("eels_fe2o3.json")
        r.table(["model", "level", "lower", "upper", "closed", "boundary affected"],
                [[m, lev, iv.get("lower_bisected", iv.get("lower")), iv.get("upper_bisected", iv.get("upper")),
                  iv.get("closed"), iv.get("boundary_affected")] for m in ("free", "constrained")
                 for lev, iv in prof[m]["intervals"].items()])
    rows = []
    for model, b in (summ.get("best_stationary") or {}).items():
        if b:
            rows.append([model, ARM_NAMES[b["arm"]], b["start"], b["rss"], b["step_l3_amplitude"], b["gn"],
                         b["condition_number_j"], b["condition_number_jtj"], ", ".join(b["held"]) or "none"])
    r.p("Lowest-RSS stationary endpoint per model over all solvers: condition numbers of the central-difference "
        "Jacobian J over the free parameters and of J^T J, and the components held at a bound.")
    r.table(["model", "solver", "start", "RSS", "step_l3", "GN", "cond(J)", "cond(J^T J)", "held"], rows)
    if eels and eels.get("condition_number"):
        kappa, bound = eels["condition_number"], eels.get("at_bound") or {}
        r.p("The reported fits of scripts/fig_eels.py (SpectraFit-Core lm; free fit from the start with the lower "
            "RSS, constrained fit from the default start): condition numbers as the wheel reports them "
            "(FitResult.condition_number is cond(J^T J); cond(J) is its square root) and the components at a "
            "bound by the 1e-4 rule of fig_eels.py.")
        r.data("eels_fe2o3.json")
        r.table(["model", "start", "RSS", "step_l3", "stderr", "cond(J)", "cond(J^T J)", "at a bound"],
                [[m, eels[m].get("start", "default"), eels[m].get("rss"), (eels[m].get("step_l3") or {}).get("value"),
                  (eels[m].get("step_l3") or {}).get("stderr"), kappa[m]["j"], kappa[m]["jtj"],
                  ", ".join(f"{k} ({v})" for k, v in (bound.get(m) or {}).items()) or "none"]
                 for m in ("free", "constrained") if m in kappa])


def section_gallery(r: Report) -> None:
    r.h("6. Example gallery")
    g = load(r.results / "gallery" / "gallery.json")
    if not g:
        r.p("Target gallery did not run.")
        return
    r.p(f"Every script of examples/ (the gallery of spectrafit-core, git tree {g['source']['tree'][:12]}), run "
        f"unchanged with the installed wheel; {g['counts']['ok']} ran, {g['counts']['failed']} failed. Drift check "
        f"against the source: {'equal' if g['drift_check']['equal'] else 'DIFFERS'}. Per fit: solver, success, "
        "stationarity (Gauss-Newton measure, the definitions of section 4), RSS and parameters with standard errors; "
        "joint fits of several datasets have no stationarity value.")
    r.data("gallery/gallery.json")
    for s in g["scripts"]:
        rows = []
        for i, f in enumerate(s["fits"]):
            st = f.get("stationarity") or {}
            params = "; ".join(f"{k} {fmt(v['value'])} ± {fmt(v['stderr'], 2)}" for k, v in
                               (f.get("parameters") or {}).items() if v.get("vary"))
            rows.append([i + 1, f.get("call"), f.get("solver"), f.get("success"),
                         st.get("stationary") if st.get("computed") else "n/a", st.get("gn_decrease_rel"),
                         st.get("rss"), f.get("condition_number_jtj"), f"{f.get('wall_s', 0) * 1e3:.1f} ms",
                         params[:160] + ("…" if len(params) > 160 else "")])
        r.p(f"{s['path']}: {s['status']}, {s['wall_s']:.1f} s, {len(s['fits'])} fits.")
        if rows:
            r.table(["fit", "call", "solver", "success", "stationary", "GN", "RSS", "cond(J^T J)", "time",
                     "free parameters (value ± stderr)"], rows)
        for name in s["figures"][:2]:
            png = r.results / "gallery" / "figures" / name
            if png.exists():
                img = plt.imread(png)

                def draw(fig, img=img):
                    ax = fig.add_subplot()
                    ax.imshow(img)
                    ax.axis("off")
                key = "gallery_" + Path(name).stem
                r.fig(key, draw, f"{name}, rendered by {s['path']} with the installed wheel.",
                      (120, 120 * img.shape[0] / img.shape[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    archive = {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    r = Report(args.results, args.out)
    section_how(r, archive)
    section_nist(r)
    section_bench(r)
    section_audit(r)
    section_eels(r)
    section_gallery(r)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    title = f"SpectraFit-Core reproducibility archive: overview of the results ({stamp})"
    r.save_figures()
    (args.out / "overview.html").write_text(r.html(title))
    r.pdf(args.out / "overview.pdf", title)
    print(f"overview: {sum(b[0] == 'h' for b in r.blocks)} sections, {len(r.figs)} figures, "
          f"{sum(b[0] == 'table' for b in r.blocks)} tables -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
