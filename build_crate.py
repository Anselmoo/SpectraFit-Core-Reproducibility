#!/usr/bin/env python3
"""Write ``ro-crate-metadata.json`` (RO-Crate 1.1) for this folder.

The crate is the machine-readable half of the FAIR description: what each file
is, which release of the software produced it, on which host, and under which
licence it may be reused. ``reproduce.py`` calls this after every run; it can
also be run on its own. Standard library only.

    python build_crate.py
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = tomllib.loads((HERE / "pins.toml").read_text())
CRATE_NAME = "ro-crate-metadata.json"
CHECKSUMS_NAME = "checksums.sha256"
SKIP_DIRS = {".git", ".cache", ".venv", "__pycache__"}
SKIP_FILES = {CRATE_NAME, CHECKSUMS_NAME, ".DS_Store"}

AUTHOR_ID = "https://orcid.org/0000-0003-4543-4833"
SOFTWARE_ID = f"https://doi.org/{PINS['software']['doi']}"
MIT_ID = "https://spdx.org/licenses/MIT"
MANIFEST_LICENCE_ID = "#licence-manifest"
NIST_ID = "https://www.itl.nist.gov/div898/strd/nls/nls_main.shtml"
RUN_ID = "#regeneration"

DESCRIPTIONS = {
    "reproduce.py": "Entry point. Regenerates results/ and figures/ from the pinned release and "
                    "checks every number the paper states.",
    "build_crate.py": "Writes this RO-Crate metadata document.",
    "pins.toml": "The release, the comparator versions and the SHA-256 of the archived inputs "
                 "that the paper is pinned to.",
    "pyproject.toml": "Environment definition for `uv run --locked reproduce.py`.",
    "uv.lock": "Hash-pinned resolution of the environment, including the spectrafit-core wheel.",
    "README.md": "What this repository is, how to rerun it, and what is regenerated versus archived.",
    "LICENSE": "MIT licence of this repository.",
    "CITATION.cff": "How to cite this repository.",
    ".gitignore": "Paths git ignores (environment and caches).",
    ".no-dep-upgrade": "Marker: the host's update scripts never upgrade this repository's lock-file.",
    "host/terra-before-update.txt": "Snapshot of the host of record before its package update.",
    "host/terra-after-update.txt": "Snapshot of the host of record after its package update, with the update record.",
    "results/other-hosts/cloud-xeon/README.md": "Labels the cloud-sandbox run kept for comparison; not results of record.",
    "results/nist_table2.json": "Table 1: agreement with the NIST StRD certified values at the "
                                "shipped tolerance 1e-12. Regenerated.",
    "results/nist_table2_tol1e15.json": "The NIST comparison at tolerance 1e-15. Regenerated.",
    "results/nist_head_to_head.json": "Per-dataset observations, fitted curves and residuals for "
                                      "spectrafit-core and lmfit; the data behind Figure 2. Regenerated.",
    "results/claims-report.json": "Every number the paper states, recomputed from the data, with pass/fail.",
    "results/drift-report.json": "Cell-by-cell difference between the regenerated Table 1 and the "
                                 "copy archived in the release.",
    "results/provenance.json": "Release commit, host, package versions and script hashes of the run "
                               "that wrote results/ and figures/.",
    "results/archived/bench_summary.json": "Timing of 151 cases on six backends at the deepest "
                                           "repetition depth. Taken from the release; not re-measured.",
    "results/archived/ladder.json": "Headline speedup at five repetition depths. Taken from the release.",
    "results/archived/sweep.json": "Headline speedup over 50 independent seeds. Taken from the release.",
    "results/archived/param_agreement.json": "Cross-backend parameter agreement. Taken from the release.",
    "results/archived/audit_bias.json": "Serialisation-bias measurement and kernel parity. Taken from the release.",
    "results/release-archive/nist_table2.json": "Table 1 as archived in the v0.1.0 release, kept for the drift report.",
    "results/release-archive/nist_table2_tol1e15.json": "The 1e-15 run as archived in the v0.1.0 release.",
    "results/release-archive/nist_head_to_head.json": "The Figure 2 data as archived in the v0.1.0 release.",
    "figures/figure1_architecture.pdf": "Figure 1, vector.",
    "figures/figure1_architecture.png": "Figure 1, raster.",
    "figures/figure2_nist.pdf": "Figure 2, vector. Drawn from results/nist_head_to_head.json.",
    "figures/figure2_nist.png": "Figure 2, raster.",
    "figures/figure3_benchmark.pdf": "Figure 3, vector. Drawn from results/archived/bench_summary.json.",
    "figures/figure3_benchmark.png": "Figure 3, raster.",
}
FORMATS = {".json": "application/json", ".pdf": "application/pdf", ".png": "image/png",
           ".py": "text/x-python", ".toml": "application/toml", ".md": "text/markdown",
           ".txt": "text/plain", ".cff": "application/x-yaml", ".lock": "application/toml"}
REGENERATED = ["results/nist_table2.json", "results/nist_table2_tol1e15.json", "results/nist_head_to_head.json",
               "figures/figure1_architecture.pdf", "figures/figure1_architecture.png",
               "figures/figure2_nist.pdf", "figures/figure2_nist.png",
               "figures/figure3_benchmark.pdf", "figures/figure3_benchmark.png"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files() -> list[str]:
    out = []
    for path in sorted(HERE.rglob("*")):
        rel = path.relative_to(HERE)
        if path.is_file() and not SKIP_DIRS & set(rel.parts) and rel.name not in SKIP_FILES:
            out.append(rel.as_posix())
    return out


def file_entity(rel: str) -> dict:
    path = HERE / rel
    entity: dict = {"@id": rel, "@type": "File", "contentSize": path.stat().st_size, "sha256": sha256(path)}
    if path.suffix in FORMATS:
        entity["encodingFormat"] = FORMATS[path.suffix]
    if rel in DESCRIPTIONS:
        entity["description"] = DESCRIPTIONS[rel]
    if rel.startswith("results/nist_") or rel.startswith("results/release-archive/"):
        entity["isBasedOn"] = {"@id": NIST_ID}
    return entity


def crate() -> dict:
    src, sw = PINS["source"], PINS["software"]
    prov_path = HERE / "results" / "provenance.json"
    prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    env = prov.get("environment", {})
    parts = files()
    graph: list[dict] = [
        {"@id": CRATE_NAME, "@type": "CreativeWork",
         "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"}, "about": {"@id": "./"}},
        {
            "@id": "./",
            "@type": "Dataset",
            "name": f"SpectraFit-Core-Reproducibility: results and figures of the SoftwareX article on {sw['name']} {sw['version']}",
            "description": (
                f"Everything the paper reports, regenerated from the public release of {sw['name']} "
                f"{sw['version']}: the compiled library from the PyPI wheel, the benchmark harness and "
                f"the figure scripts from the repository at tag {src['tag']}. The NIST comparison and "
                "all three figures are regenerated on every run. The wall-clock benchmark is taken "
                "from the release archive, verified by SHA-256, and not re-measured. Each number in "
                "the prose is recomputed from these files in results/claims-report.json."
            ),
            "datePublished": prov.get("generated_utc", "")[:10] or None,
            "author": {"@id": AUTHOR_ID},
            "license": {"@id": MANIFEST_LICENCE_ID},
            "isBasedOn": [{"@id": SOFTWARE_ID}, {"@id": NIST_ID}],
            "hasPart": [{"@id": rel} for rel in [*parts, CHECKSUMS_NAME]],
        },
        {"@id": AUTHOR_ID, "@type": "Person", "name": "Anselm W. Hahn",
         "affiliation": "Max Planck Institute for Chemical Energy Conversion"},
        {
            "@id": SOFTWARE_ID,
            "@type": "SoftwareSourceCode",
            "name": sw["name"],
            "version": sw["version"],
            "identifier": f"https://doi.org/{sw['doi']}",
            "codeRepository": src["repository"].removesuffix(".git"),
            "license": {"@id": MIT_ID},
            "description": f"Release {src['tag']}, commit {src['commit']}. Installed as: {sw['wheel']}.",
        },
        {"@id": NIST_ID, "@type": "Dataset",
         "name": "NIST Statistical Reference Datasets (StRD): Nonlinear Regression",
         "description": "Certified parameter values and standard deviations. The data files ship with "
                        "the software release; this folder holds only the agreement computed from them."},
        {"@id": MANIFEST_LICENCE_ID, "@type": "CreativeWork",
         "name": "MIT",
         "description": "Code, results and figures are MIT-licensed, as the spectrafit-core release is."},
        {"@id": MIT_ID, "@type": "CreativeWork", "name": "MIT License", "identifier": "MIT"},
    ]
    if prov:
        graph.append({
            "@id": RUN_ID,
            "@type": "CreateAction",
            "name": "Regeneration of results and figures",
            "endTime": prov["generated_utc"],
            "agent": {"@id": AUTHOR_ID},
            "instrument": [{"@id": "reproduce.py"}, {"@id": SOFTWARE_ID}],
            "object": [{"@id": r} for r in parts if r.startswith("results/archived/")],
            "result": [{"@id": r} for r in REGENERATED if r in parts],
            "description": (
                f"`{prov['command'].strip()}` on {env.get('platform')} ({env.get('cpu')}, "
                f"{env.get('cores')} cores), Python {env.get('python')}; "
                + ", ".join(f"{k} {v}" for k, v in env.get("packages", {}).items()) + "."
            ),
        })
    graph += [file_entity(rel) for rel in parts]
    graph.append({"@id": CHECKSUMS_NAME, "@type": "File",
                  "description": "SHA-256 of every other file in this folder, including this crate. Written "
                                 "after this document, so no digest of it appears here."})
    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


def main() -> None:
    (HERE / CRATE_NAME).write_text(json.dumps(crate(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {CRATE_NAME}")


if __name__ == "__main__":
    main()
