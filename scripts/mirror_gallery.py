#!/usr/bin/env python3
"""Mirror the spectrafit-core example gallery into ``examples/`` (#71).

The files of ``docs/tutorials/gallery/`` are read from a commit object of a
spectrafit-core checkout (``git ls-tree`` and ``git cat-file``), so the working
tree of that checkout and its uncommitted state do not matter. Each file is
written to ``examples/`` byte for byte, with its executable bit; nothing is
edited. ``examples/`` belongs to the mirror: files that are no longer in the
source are removed.

The manifest ``examples-manifest.json`` records

* the source: repository, ref, commit, commit time, folder and the git tree id
  of that folder at the commit;
* every file: path, SHA-256, git blob id, mode and role (``example`` and
  ``snippet`` are run by ``reproduce.py --examples``; ``helper`` is imported by
  the examples or used by the docs build and not run on its own;
  ``explanation`` is the Markdown page that explains an example);
* ``files_sha256``: the SHA-256 of the file table itself, so the manifest
  verifies itself (``tests/test_examples.py``).

The git tree id is recomputed from the written files and must equal the tree id
of the source folder at the commit; together with the blob ids this makes the
mirror verifiable against any repository that holds the same folder content,
including a public mirror whose commit ids differ.

    uv run --locked scripts/mirror_gallery.py --source ~/path/to/spectrafit-core \\
        --commit <rev> [--repository URL] [--ref NAME]

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EXAMPLES = HERE / "examples"
MANIFEST = HERE / "examples-manifest.json"
SOURCE_PATH = "docs/tutorials/gallery"
SCHEMA = "examples-manifest/1"
# File modes git stores for regular files. Symbolic links and submodules are refused.
FILE_MODES = {"100644", "100755"}
RUN_ROLES = ("example", "snippet")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_id(data: bytes) -> str:
    """Object id git gives a file with this content (SHA-1 object format)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def git_tree_id(files: dict[str, tuple[str, str]]) -> str:
    """Object id of the git tree holding ``{relative path: (mode, blob id)}``.

    Follows git's tree object format: entries ``<mode> <name>\\0<20-byte id>``,
    sorted by name with a sub-tree compared as ``name + "/"``; a sub-tree has mode
    ``40000``.
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


def role(rel: str) -> str:
    """Role of a gallery file, relative to the gallery folder."""
    path = Path(rel)
    if path.suffix == ".md":
        return "explanation"
    if path.suffix != ".py":
        return "asset"
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
    return out, tree


def write_mirror(files: dict[str, tuple[str, bytes]]) -> None:
    if EXAMPLES.exists():
        shutil.rmtree(EXAMPLES)
    for rel, (mode, data) in sorted(files.items()):
        dest = EXAMPLES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        dest.chmod(0o755 if mode == "100755" else 0o644)


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
    files, tree = read_source(source, commit)
    write_mirror(files)

    table = [{"path": f"examples/{rel}", "sha256": sha256_bytes(data), "git_blob": git_blob_id(data),
              "mode": mode, "role": role(rel)} for rel, (mode, data) in sorted(files.items())]
    rebuilt = git_tree_id({f["path"].removeprefix("examples/"): (f["mode"], f["git_blob"]) for f in table})
    if rebuilt != tree:
        raise SystemExit(f"the mirror hashes to tree {rebuilt}, the source folder is tree {tree}")
    library = pins["packages"]["spectrafit-core"]
    manifest = {
        "schema": SCHEMA,
        "description": "Example gallery of spectrafit-core, mirrored 1:1 from the folder below; "
                       "run as a smoke test by `reproduce.py --examples` (#71).",
        "source": {"repository": args.repository, "ref": args.ref or args.commit, "commit": commit,
                   "committed": committed, "path": SOURCE_PATH, "tree": tree},
        "library": {"spectrafit-core": library,
                    "note": "the examples run against the library pinned in pins.toml and uv.lock; "
                            + (f"the mirrored ref is the release tag of spectrafit-core {library}"
                               if (args.ref or args.commit) == f"v{library}" else
                               f"spectrafit-core {library} is provisional for this mirror until the pin "
                               "moves to the release the mirrored commit belongs to")},
        "run_roles": list(RUN_ROLES),
        "files": table,
        "files_sha256": files_digest(table),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"mirrored {len(table)} files from {SOURCE_PATH} @ {commit[:12]} (tree {tree[:12]}) into examples/")
    for f in table:
        print(f"  {f['sha256']}  {f['role']:<11s}  {f['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
