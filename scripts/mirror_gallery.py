#!/usr/bin/env python3
"""Mirror the Python files of the spectrafit-core example gallery into ``examples/``.

The files of ``docs/tutorials/gallery/`` are read from a commit object of a
spectrafit-core checkout (``git ls-tree`` and ``git cat-file``), so the working
tree of that checkout and its uncommitted state do not matter. Every Python file
(the examples, the helpers ``_plotting.py`` and ``_render.py``, ``_snippets/``) is
written to ``examples/`` byte for byte, with its executable bit; nothing is edited.
``examples/`` belongs to the mirror: files that are no longer in the source are
removed.

The Markdown pages of the gallery are not mirrored. They are pages of the
documentation site (front matter, attribute lists, snippet includes, images under
``_static/`` that are not in the folder) and do not render as pages outside it.
Instead the mirror step writes ``examples/README.md``: one entry per example, in
the order of the gallery index page, with the title and description taken
verbatim from the example's page, a link to the script and the figure the
``gallery`` target recorded (``results/gallery/figures/<script stem>.png``).

The manifest ``examples-manifest.json`` records

* the source: repository, ref, commit, commit time, folder and the git tree id
  of that folder at the commit;
* every mirrored file: path, SHA-256, git blob id, mode and role (``example`` and
  ``snippet`` are run by ``reproduce.py --examples``; ``helper`` is imported by
  the examples or used by the docs build and not run on its own);
* ``not_mirrored``: every file of the source folder that is deliberately left out,
  with its git blob id and the reason;
* ``generated``: ``examples/README.md`` with its SHA-256;
* ``files_sha256``: the SHA-256 of the file table itself, so the manifest
  verifies itself (``tests/test_examples.py``).

Each mirrored file is checked against its git blob id in the source commit, so the
mirror is verifiable file by file against any repository that holds the same
files, including a public mirror whose commit ids differ.

    uv run --locked scripts/mirror_gallery.py --source ~/path/to/spectrafit-core \\
        --commit <rev> [--repository URL] [--ref NAME]

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EXAMPLES = HERE / "examples"
MANIFEST = HERE / "examples-manifest.json"
README = EXAMPLES / "README.md"
SOURCE_PATH = "docs/tutorials/gallery"
SCHEMA = "examples-manifest/2"
# File modes git stores for regular files. Symbolic links and submodules are refused.
FILE_MODES = {"100644", "100755"}
RUN_ROLES = ("example", "snippet")
# The figure of each example, as the gallery target records it.
FIGURES = "results/gallery/figures"
DOCS_GALLERY_URL = "https://anselmoo.github.io/SpectraFit-Core/tutorials/gallery/"
NOT_MIRRORED_REASON = {
    ".md": "page of the documentation site (front matter, attribute lists, snippet includes, images "
           "under _static/ that are not in the folder); summarised in the generated examples/README.md",
}
# Scripts that need more than the folder; the note is printed under the entry.
ENTRY_NOTES = {
    "misspecified_model": "Not run by `reproduce.py --examples`: the script reads a measured spectrum from the "
                          "root of a spectrafit-core checkout, outside this folder. The `gallery` target runs it "
                          "with that spectrum copied from the release export (`--spectrum-dir`).",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_id(data: bytes) -> str:
    """Object id git gives a file with this content (SHA-1 object format)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def git_tree_id(files: dict[str, tuple[str, str]]) -> str:
    """Object id of the git tree holding ``{relative path: (mode, blob id)}``.

    Follows git's tree object format: entries ``<mode> <name>\\0<20-byte id>``,
    sorted by name with a sub-tree compared as ``name + "/"``; a sub-tree has mode
    ``40000``. Used to check the source listing against the folder's tree id.
    """
    direct: dict[str, tuple[str, str]] = {}
    nested: dict[str, dict[str, tuple[str, str]]] = {}
    for rel, entry in files.items():
        head, sep, tail = rel.partition("/")
        if sep:
            nested.setdefault(head, {})[tail] = entry
        else:
            direct[head] = entry
    entries = [(name, mode, oid) for name, (mode, oid) in direct.items()]
    entries += [(name, "40000", git_tree_id(sub)) for name, sub in nested.items()]
    entries.sort(key=lambda e: e[0] + "/" if e[1] == "40000" else e[0])
    body = b"".join(f"{mode} {name}".encode() + b"\0" + bytes.fromhex(oid) for name, mode, oid in entries)
    return hashlib.sha1(b"tree %d\0" % len(body) + body, usedforsecurity=False).hexdigest()


def mirrored(rel: str) -> bool:
    """Whether a gallery file (relative to the gallery folder) belongs to the mirror."""
    return Path(rel).suffix == ".py"


def role(rel: str) -> str:
    """Role of a mirrored gallery file, relative to the gallery folder."""
    path = Path(rel)
    if path.parts[0] == "_snippets":
        return "snippet"  # included verbatim into a page; a standalone script
    if path.name.startswith("_"):
        return "helper"  # _plotting.py (imported by the examples), _render.py (docs build)
    return "example"


def files_digest(files: list[dict]) -> str:
    """SHA-256 of the file table in ``sha256sum`` format, one line per file, sorted by path."""
    lines = "".join(f"{f['sha256']}  {f['path']}\n" for f in sorted(files, key=lambda f: f["path"]))
    return sha256_bytes(lines.encode())


def git(source: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(source), *args], capture_output=True, check=True).stdout


def read_source(source: Path, commit: str) -> tuple[dict[str, tuple[str, bytes]], str]:
    """``{path relative to the gallery: (mode, content)}`` and the folder's tree id at ``commit``."""
    tree = git(source, "rev-parse", "--verify", f"{commit}:{SOURCE_PATH}").decode().strip()
    listing = git(source, "ls-tree", "-r", "-z", "--full-tree", commit, "--", SOURCE_PATH)
    out: dict[str, tuple[str, bytes]] = {}
    for record in filter(None, listing.split(b"\0")):
        meta, _, path = record.decode().partition("\t")
        mode, kind, oid = meta.split()
        if kind != "blob" or mode not in FILE_MODES:
            raise SystemExit(f"{path}: {kind} with mode {mode} cannot be mirrored as a file")
        data = git(source, "cat-file", "blob", oid)
        if git_blob_id(data) != oid:
            raise SystemExit(f"{path}: content does not hash to its blob id {oid}")
        out[path.removeprefix(SOURCE_PATH + "/")] = (mode, data)
    rebuilt = git_tree_id({rel: (mode, git_blob_id(data)) for rel, (mode, data) in out.items()})
    if rebuilt != tree:
        raise SystemExit(f"the source listing hashes to tree {rebuilt}, the folder is tree {tree}")
    return out, tree


# --------------------------------------------------------------------------- README


def front_matter(page: str) -> dict[str, str]:
    """``key: value`` lines of a page's YAML front matter (single-line values only)."""
    match = re.match(r"---\n(.*?)\n---\n", page, re.DOTALL)
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" ") and value.strip():
            out[key.strip()] = value.strip()
    return out


def heading(line: str) -> str:
    """A Markdown heading without its marker and its ``{ ... }`` attribute list."""
    return re.sub(r"\s*\{[^}]*\}\s*$", "", line.lstrip("#").strip())


def index_order(index: str) -> list[str]:
    """Script stems in the order of the gallery index page (one per thumbnail)."""
    stems: list[str] = []
    for stem in re.findall(r"_static/([A-Za-z0-9_]+)-thumb-light\.png", index):
        if stem not in stems:
            stems.append(stem)
    return stems


def entry_text(stem: str, pages: dict[str, str]) -> tuple[str, str, str]:
    """Title, description and page name of one example, verbatim from its page.

    The example's own page ``<stem>.md`` gives its first heading and the front matter
    ``description``. A script without a page of its own is shown on the page that
    includes it (``--8<-- "<stem>.py:..."``); its title is the heading of the section
    that includes it, its description that page's ``description``.
    """
    if f"{stem}.md" in pages:
        page = pages[f"{stem}.md"]
        title = next(heading(ln) for ln in page.splitlines() if ln.startswith("# "))
        return title, front_matter(page)["description"], f"{stem}.md"
    for name, page in sorted(pages.items()):
        if f'--8<-- "{stem}.py' not in page:
            continue
        section = None
        for ln in page.splitlines():
            if ln.startswith("## "):
                section = heading(ln)
            if f'--8<-- "{stem}.py' in ln:
                break
        if section is None:
            raise SystemExit(f"{stem}.py is included by {name} outside a section")
        return section, front_matter(page)["description"], name
    raise SystemExit(f"{stem}.py: no page of the gallery describes it")


def render_readme(files: dict[str, tuple[str, bytes]], ref: str, commit: str, library: str) -> str:
    pages = {rel: data.decode() for rel, (_, data) in files.items() if rel.endswith(".md") and "/" not in rel}
    stems = index_order(pages["index.md"])
    scripts = {Path(rel).stem for rel in files if mirrored(rel) and role(rel) == "example"}
    missing = scripts - set(stems)
    if missing:
        raise SystemExit(f"examples without a thumbnail on the index page: {sorted(missing)}")
    lines = [
        "# Examples",
        "",
        "<!-- Generated by scripts/mirror_gallery.py from the gallery pages of spectrafit-core; do not edit. -->",
        "",
        ("This folder holds the Python files of the example gallery of spectrafit-core, copied byte for byte "
         f"from `{SOURCE_PATH}/` (`examples-manifest.json` records every file). "
         f"The scripts are those of spectrafit-core release {library} (tag `{ref}`, commit `{commit[:8]}`) and "
         "may differ in later releases; the figures are the ones the `gallery` target of this repository "
         "recorded from them. "
         "`uv run --locked reproduce.py --examples` runs them against the pinned wheel. "
         f"The rendered gallery with the full explanations is on the [documentation site]({DOCS_GALLERY_URL})."),
        "",
    ]
    for stem in stems:
        title, description, page = entry_text(stem, pages)
        lines += [
            f"## {title}",
            "",
            description,
            "",
            f"Script: [`{stem}.py`]({stem}.py) · page in the source: `{SOURCE_PATH}/{page}`",
            "",
            f"![{stem}](../{FIGURES}/{stem}.png)",
            "",
        ]
        if stem in ENTRY_NOTES:
            lines += [ENTRY_NOTES[stem], ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- mirror


def write_mirror(files: dict[str, tuple[str, bytes]], readme: str) -> None:
    if EXAMPLES.exists():
        shutil.rmtree(EXAMPLES)
    for rel, (mode, data) in sorted(files.items()):
        dest = EXAMPLES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        dest.chmod(0o755 if mode == "100755" else 0o644)
    README.write_text(readme)


def main() -> int:
    pins = tomllib.loads((HERE / "pins.toml").read_text())
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True, help="spectrafit-core checkout that holds --commit")
    ap.add_argument("--commit", required=True, help="commit, tag or branch to mirror from")
    ap.add_argument("--repository", default=pins["source"]["repository"],
                    help="repository URL recorded in the manifest (default: pins.toml [source])")
    ap.add_argument("--ref", default=None, help="branch or tag name recorded in the manifest (default: --commit)")
    args = ap.parse_args()

    source = args.source.expanduser().resolve()
    commit = git(source, "rev-parse", "--verify", f"{args.commit}^{{commit}}").decode().strip()
    committed = git(source, "show", "-s", "--format=%cI", commit).decode().strip()
    ref = args.ref or args.commit
    found, tree = read_source(source, commit)
    keep = {rel: v for rel, v in found.items() if mirrored(rel)}
    library = pins["packages"]["spectrafit-core"]
    readme = render_readme(found, ref, commit, library)
    write_mirror(keep, readme)

    table = [{"path": f"examples/{rel}", "sha256": sha256_bytes(data), "git_blob": git_blob_id(data),
              "mode": mode, "role": role(rel)} for rel, (mode, data) in sorted(keep.items())]
    left_out = []
    for rel, (_, data) in sorted(found.items()):
        if mirrored(rel):
            continue
        reason = NOT_MIRRORED_REASON.get(Path(rel).suffix)
        if reason is None:
            raise SystemExit(f"{rel}: neither mirrored nor given a reason to leave it out")
        left_out.append({"path": f"{SOURCE_PATH}/{rel}", "git_blob": git_blob_id(data), "reason": reason})
    manifest = {
        "schema": SCHEMA,
        "description": "Python files of the example gallery of spectrafit-core, mirrored byte for byte from the "
                       "folder below; run as a smoke test by `reproduce.py --examples`.",
        "source": {"repository": args.repository, "ref": ref, "commit": commit,
                   "committed": committed, "path": SOURCE_PATH, "tree": tree},
        "library": {"spectrafit-core": library,
                    "note": "the examples run against the library pinned in pins.toml and uv.lock; "
                            + (f"the mirrored ref is the release tag of spectrafit-core {library}"
                               if ref == f"v{library}" else
                               f"spectrafit-core {library} is provisional for this mirror until the pin "
                               "moves to the release the mirrored commit belongs to")},
        "run_roles": list(RUN_ROLES),
        "files": table,
        "not_mirrored": left_out,
        "generated": {"path": "examples/README.md", "sha256": sha256_bytes(readme.encode()),
                      "from": "the gallery pages at the source commit, by scripts/mirror_gallery.py"},
        "files_sha256": files_digest(table),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"mirrored {len(table)} files from {SOURCE_PATH} @ {commit[:12]} (tree {tree[:12]}) into examples/; "
          f"{len(left_out)} left out; examples/README.md generated")
    for f in table:
        print(f"  {f['sha256']}  {f['role']:<8s}  {f['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
