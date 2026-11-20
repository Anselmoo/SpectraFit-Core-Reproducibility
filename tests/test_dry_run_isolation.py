"""A dry run names its release candidate and package index at run time only.

``scripts/dry_run_env.py`` installs a release candidate of spectrafit-core from a package
index that is passed in the environment of one run. The published environment files must
never carry that index or a pre-release of spectrafit-core: ``pyproject.toml`` and
``uv.lock`` are checked for an index table, for the URL forms of a GitLab or other private
package index, and for a pre-release version (``aN``, ``bN``, ``rcN``, ``.devN``) of
spectrafit-core.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PRERELEASE = re.compile(r"\d(a|b|rc)\d+|\.dev\d+", re.IGNORECASE)
INDEX_URL = re.compile(r"/api/v4/(projects|groups)/[^\s\"']*/packages/pypi|gitlab\.|/packages/pypi/simple",
                       re.IGNORECASE)


def test_pyproject_names_no_index_and_no_prerelease() -> None:
    text = (HERE / "pyproject.toml").read_text()
    data = tomllib.loads(text)
    uv = data.get("tool", {}).get("uv", {})
    assert "index" not in uv and "index-url" not in uv and "extra-index-url" not in uv
    assert "sources" not in uv
    assert not INDEX_URL.search(text)
    specs = [*data["project"]["dependencies"], *(d for g in data.get("dependency-groups", {}).values() for d in g)]
    for spec in specs:
        if spec.lower().startswith("spectrafit-core"):
            assert not PRERELEASE.search(spec), spec


def test_lock_resolves_spectrafit_core_from_pypi_as_a_release() -> None:
    text = (HERE / "uv.lock").read_text()
    assert not INDEX_URL.search(text)
    lock = tomllib.loads(text)
    pkgs = [p for p in lock["package"] if p["name"] == "spectrafit-core"]
    assert pkgs
    for p in pkgs:
        assert not PRERELEASE.search(p["version"]), p["version"]
        assert p["source"] == {"registry": "https://pypi.org/simple"}, p["source"]
        for wheel in p.get("wheels", []):
            assert wheel["url"].startswith("https://files.pythonhosted.org/"), wheel["url"]
    for p in lock["package"]:
        registry = p.get("source", {}).get("registry")
        assert registry in (None, "https://pypi.org/simple"), (p["name"], registry)
