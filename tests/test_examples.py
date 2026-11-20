"""The examples mirror (#71): byte identity, the self-verifying manifest, the smoke run.

Run in the pinned environment:

    uv run --locked --group audit pytest tests/

``SPECTRAFIT_CORE_SOURCE`` may name a spectrafit-core checkout that holds the
recorded commit; the mirror is then also compared with that commit object file by
file. Without it, identity with the recorded commit rests on the git tree id of
the source folder, which the manifest records and which is recomputed here from
the mirrored bytes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
EXAMPLES = HERE / "examples"
MANIFEST_PATH = HERE / "examples-manifest.json"
SMOKE = HERE / ".cache" / "check" / "results" / "examples-smoke.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mirror = _load("mirror_gallery", HERE / "scripts" / "mirror_gallery.py")
MANIFEST = json.loads(MANIFEST_PATH.read_text())
FILES = {f["path"]: f for f in MANIFEST["files"]}
RUNNABLE = [f["path"] for f in MANIFEST["files"] if f["role"] in MANIFEST["run_roles"]]


def _on_disk() -> set[str]:
    return {p.relative_to(HERE).as_posix() for p in EXAMPLES.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


# --------------------------------------------------------------------------- git object format


def test_git_tree_id_matches_git(tmp_path: Path) -> None:
    """The tree-id computation agrees with git itself on a nested folder with an executable file."""
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    contents = {"a.py": b"print(1)\n", "a-b.md": b"# x\n", "sub/c.py": b"", "sub.txt": b"z"}
    for rel, data in contents.items():
        (repo / rel).write_bytes(data)
    (repo / "a.py").chmod(0o755)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    want = subprocess.run(["git", "-C", str(repo), "write-tree"], capture_output=True, text=True,
                          check=True).stdout.strip()
    got = mirror.git_tree_id({rel: ("100755" if rel == "a.py" else "100644", mirror.git_blob_id(data))
                              for rel, data in contents.items()})
    assert got == want


# --------------------------------------------------------------------------- manifest


def test_manifest_verifies_itself() -> None:
    assert MANIFEST["schema"] == mirror.SCHEMA
    assert MANIFEST["files_sha256"] == mirror.files_digest(MANIFEST["files"])


def test_manifest_lists_exactly_the_mirrored_files() -> None:
    assert set(FILES) == _on_disk()


@pytest.mark.parametrize("rel", sorted(FILES))
def test_file_matches_manifest(rel: str) -> None:
    data = (HERE / rel).read_bytes()
    entry = FILES[rel]
    assert mirror.sha256_bytes(data) == entry["sha256"]
    assert mirror.git_blob_id(data) == entry["git_blob"]
    assert entry["role"] == mirror.role(rel.removeprefix("examples/"))


def test_manifest_records_the_pinned_library() -> None:
    import tomllib

    pins = tomllib.loads((HERE / "pins.toml").read_text())
    assert MANIFEST["library"]["spectrafit-core"] == pins["packages"]["spectrafit-core"]


# --------------------------------------------------------------------------- byte identity


def test_mirror_hashes_to_the_source_tree() -> None:
    """The mirrored bytes form exactly the recorded git tree of the source folder."""
    entries = {rel.removeprefix("examples/"): (f["mode"], mirror.git_blob_id((HERE / rel).read_bytes()))
               for rel, f in FILES.items()}
    assert mirror.git_tree_id(entries) == MANIFEST["source"]["tree"]


@pytest.mark.skipif(not os.environ.get("SPECTRAFIT_CORE_SOURCE"),
                    reason="SPECTRAFIT_CORE_SOURCE (a spectrafit-core checkout) is not set")
def test_mirror_is_byte_identical_to_the_source_commit() -> None:
    source = Path(os.environ["SPECTRAFIT_CORE_SOURCE"]).expanduser()
    files, tree = mirror.read_source(source, MANIFEST["source"]["commit"])
    assert tree == MANIFEST["source"]["tree"]
    assert {f"examples/{rel}" for rel in files} == set(FILES)
    for rel, (mode, data) in files.items():
        assert (EXAMPLES / rel).read_bytes() == data, rel
        assert FILES[f"examples/{rel}"]["mode"] == mode, rel


# --------------------------------------------------------------------------- smoke run


@pytest.fixture(scope="module")
def smoke() -> dict:
    """One run of the harness target; ``--check`` keeps its output in .cache/."""
    proc = subprocess.run([sys.executable, str(HERE / "reproduce.py"), "--examples", "--check"],
                          cwd=HERE, capture_output=True, text=True, check=False)
    assert SMOKE.exists(), proc.stdout + proc.stderr
    return json.loads(SMOKE.read_text()) | {"_exit": proc.returncode, "_log": proc.stdout + proc.stderr}


def test_smoke_covers_every_runnable_file(smoke: dict) -> None:
    assert [s["path"] for s in smoke["scripts"]] == RUNNABLE
    assert smoke["source"]["commit"] == MANIFEST["source"]["commit"]


@pytest.mark.parametrize("rel", RUNNABLE)
def test_example_exits_zero(smoke: dict, rel: str) -> None:
    entry = next(s for s in smoke["scripts"] if s["path"] == rel)
    if entry["status"] == "skipped":
        pytest.skip(entry["skip_reason"])
    assert not entry["timed_out"], f"{rel} exceeded {smoke['timeout_s']} s"
    assert entry["exit_code"] == 0, entry.get("stderr_tail")


def test_harness_exit_code_reflects_the_scripts(smoke: dict) -> None:
    failed = [s for s in smoke["scripts"] if s["status"] == "failed"]
    assert smoke["_exit"] == (1 if failed else 0), smoke["_log"]
