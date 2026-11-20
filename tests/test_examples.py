"""The examples mirror: per-file identity, the self-verifying manifest, the README, the smoke run.

Run in the pinned environment:

    uv run --locked --group audit pytest tests/

``SPECTRAFIT_CORE_SOURCE`` may name a spectrafit-core checkout that holds the
recorded commit; the mirror is then also compared with that commit object file by
file, and the README is generated again from it and compared. Without it, identity
with the recorded commit rests on the SHA-256 and git blob id of every file, which
the manifest records and which are recomputed here from the mirrored bytes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
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
GENERATED = MANIFEST["generated"]
README = HERE / GENERATED["path"]


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
    assert set(FILES) | {GENERATED["path"]} == _on_disk()


def test_only_python_files_are_mirrored() -> None:
    assert all(rel.endswith(".py") for rel in FILES)
    assert all(not mirror.mirrored(Path(f["path"]).name) and f["reason"] for f in MANIFEST["not_mirrored"])


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


# --------------------------------------------------------------------------- source commit


@pytest.mark.skipif(not os.environ.get("SPECTRAFIT_CORE_SOURCE"),
                    reason="SPECTRAFIT_CORE_SOURCE (a spectrafit-core checkout) is not set")
def test_mirror_matches_the_source_commit_file_by_file() -> None:
    source = Path(os.environ["SPECTRAFIT_CORE_SOURCE"]).expanduser()
    files, tree = mirror.read_source(source, MANIFEST["source"]["commit"])
    assert tree == MANIFEST["source"]["tree"]
    kept = {rel: v for rel, v in files.items() if mirror.mirrored(rel)}
    assert {f"examples/{rel}" for rel in kept} == set(FILES)
    for rel, (mode, data) in kept.items():
        assert (EXAMPLES / rel).read_bytes() == data, rel
        assert FILES[f"examples/{rel}"]["mode"] == mode, rel
    left_out = {f"{mirror.SOURCE_PATH}/{rel}": mirror.git_blob_id(data)
                for rel, (_, data) in files.items() if not mirror.mirrored(rel)}
    assert {f["path"]: f["git_blob"] for f in MANIFEST["not_mirrored"]} == left_out
    readme = mirror.render_readme(files, MANIFEST["source"]["ref"], MANIFEST["source"]["commit"],
                                  MANIFEST["library"]["spectrafit-core"])
    assert README.read_text() == readme


# --------------------------------------------------------------------------- generated README


def test_readme_is_the_generated_one() -> None:
    assert mirror.sha256_bytes(README.read_bytes()) == GENERATED["sha256"]


def test_every_figure_linked_in_the_readme_exists() -> None:
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", README.read_text())
    assert links
    missing = [link for link in links if not (README.parent / link).resolve().is_file()]
    assert not missing


def test_readme_has_one_entry_per_example() -> None:
    scripts = re.findall(r"Script: \[`([^`]+)`\]", README.read_text())
    examples = sorted(Path(rel).name for rel, f in FILES.items() if f["role"] == "example")
    assert sorted(scripts) == examples
    assert all((EXAMPLES / s).is_file() for s in scripts)


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
