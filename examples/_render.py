"""Pre-render all gallery example scripts to regenerate their ``_static/*.png``.

Run before ``zensical build`` so the docs site always ships thumbnails that
match the scripts currently checked in (rather than stale PNGs from a
previous edit). Wired into ``poe docs_build`` (see ``pyproject.toml``):

    uv run --group docs python docs/tutorials/gallery/_render.py
    uv run --group docs zensical build --clean

Each gallery script (``fitting.py``, ``3d_fitting.py``, ``multi_dataset_1d.py``,
``multi_dataset_2d.py``, ``shared_params.py``, ``varpro_vs_lm.py``,
``confidence_intervals.py``, ``spectrafit_vs_lmfit_moderate.py``,
``spectrafit_vs_lmfit_complex.py``, ``fixed_params.py``, ``weighted_fitting.py``,
``bounded_fitting.py``, ``robust_fitting.py``, ``global_optimizer.py``,
``failed_fit.py``, ``misspecified_model.py``) is a
standalone, runnable example guarded by
``if __name__ == "__main__":`` for its plotting/``savefig`` step, and
each already writes to ``docs/tutorials/gallery/_static/<name>.png`` via the
shared ``_plotting.savefig`` helper. Rather than importing and refactoring
each script to expose a common entry function (invasive: two of the five run
top-level fit/print code unconditionally, only guarding the plot), this
just re-executes each script the same way a contributor would from the
command line: ``python <script>.py``, run as a subprocess with this
directory as the working directory so the scripts' own
``from _plotting import ...`` sibling import resolves.

:func:`render_all` runs each script TWICE — once with no theme override
(light; writes the full-size PNG above plus a ``<name>-thumb-light.png``)
and once with ``SPECTRAFIT_GALLERY_THEME=dark`` (writes only
``<name>-thumb-dark.png``) — see ``_plotting.py`` for why this needs a
second subprocess rather than an in-process repaint. The gallery index
(``index.md``) swaps between the two thumbnails via CSS, the same
``[data-md-color-scheme]`` pattern ``docs/stylesheets/pages/hero.css``
already uses for the homepage hero art; tutorial detail pages are
unaffected and keep embedding the full-size light PNG only.

``_snippets/stacked_slices.py`` is a different contract: its own docstring
calls it a "standalone runnable script (no plotting)", and it is included
verbatim into ``3d_fitting.md`` via an ``--8<--`` snippet include rather than
a gallery card. It has top-level code (no ``__main__`` guard) and writes no
PNG, so it cannot go through :func:`render_all`'s "ran, then assert the PNG
landed" contract. :func:`run_snippets` runs it the same way -- a subprocess
with this directory as ``cwd`` so ``spectrafit_core`` still resolves via
``PYTHON_SRC`` -- but only asserts a zero exit, which is the only honest
claim: that the published script still runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

GALLERY_DIR = Path(__file__).parent

#: `<repo>/python`, the directory holding the `spectrafit_core` package.
#:
#: Each script below runs with `cwd=GALLERY_DIR` so its `from _plotting import ...`
#: sibling import resolves — but that also breaks a RELATIVE `PYTHONPATH`. CI sets
#: `PYTHONPATH=python`, which resolves from the repo root and becomes
#: `docs/tutorials/gallery/python` (nonexistent) once cwd changes, so every script
#: dies with `ModuleNotFoundError: No module named 'spectrafit_core'`.
#:
#: This is latent whenever the extension is provided by an editable install with
#: an ABSOLUTE `.pth` (as `maturin develop` used to leave in `.venv`), since the
#: module is then importable from any cwd. `.gitlab/65-docs.yml` instead pulls the
#: extension from `build:ext:dev` as an artifact, with no `.pth` to paper over a
#: relative `PYTHONPATH`, which is why this needs resolving explicitly.
#:
#: Resolving to an absolute path here fixes it for CI and for anyone running this
#: script by hand from a directory other than the repo root.
PYTHON_SRC = (GALLERY_DIR.parents[2] / "python").resolve()

# Order matches the gallery's markdown pages (fitting -> 3d -> multi_dataset
# 1d/2d -> shared_params -> varpro_vs_lm -> confidence_intervals -> the two
# spectrafit-vs-lmfit tiers -> fixed_params -> weighted_fitting ->
# bounded_fitting -> robust_fitting -> global_optimizer -> failed_fit ->
# misspecified_model); not load-bearing, just readable in log output.
SCRIPTS: tuple[str, ...] = (
    "fitting.py",
    "3d_fitting.py",
    "multi_dataset_1d.py",
    "multi_dataset_2d.py",
    "shared_params.py",
    "varpro_vs_lm.py",
    "confidence_intervals.py",
    "spectrafit_vs_lmfit_moderate.py",
    "spectrafit_vs_lmfit_complex.py",
    "fixed_params.py",
    "weighted_fitting.py",
    "bounded_fitting.py",
    "robust_fitting.py",
    "global_optimizer.py",
    "failed_fit.py",
    "misspecified_model.py",
)

#: Companion snippet scripts included verbatim into a gallery page (via
#: mkdocs' ``--8<--`` snippet include) rather than rendered as their own
#: gallery card. They have no ``if __name__ == "__main__":`` plotting guard
#: and write no PNG, so they are run for their exit status only -- see
#: `run_snippets`.
SNIPPET_SCRIPTS: tuple[str, ...] = ("_snippets/stacked_slices.py",)


def render_all(scripts: tuple[str, ...] = SCRIPTS) -> list[Path]:
    """Run each gallery script as ``__main__`` TWICE, returning the light PNG paths.

    Each script is re-executed as a fresh subprocess under two different
    values of ``SPECTRAFIT_GALLERY_THEME`` (see ``_plotting.py``):

    1. Unset (light, the original/default pass) — writes the full-size
       ``<name>.png`` every tutorial detail page embeds, plus a
       ``<name>-thumb-light.png`` derived from it for the gallery index.
    2. ``"dark"`` — writes only ``<name>-thumb-dark.png``, the dark half of
       the gallery index's light/dark swap (mirrors
       ``.sf-hero__media-img--light/--dark`` in
       ``docs/stylesheets/pages/hero.css``).

    A second full subprocess run (rather than re-rendering the same figure
    object in-process) is what lets each script's own hardcoded colors
    (`MUTED_COLOR`, imported per-script) and every rcParams-driven default
    (ticks, spines, grid, legend text, figure/axes background) pick up the
    right theme — nothing here repaints an already-drawn artist after the
    fact.

    Raises:
        subprocess.CalledProcessError: if any script exits non-zero.
        FileNotFoundError: if an expected PNG is missing after its pass.
    """
    written: list[Path] = []
    static_dir = GALLERY_DIR / "_static"
    for script in scripts:
        script_path = GALLERY_DIR / script
        stem = script_path.stem

        # Prepend the ABSOLUTE python/ dir — see PYTHON_SRC. Prepend rather than
        # replace so an inherited PYTHONPATH (e.g. a contributor's own entries)
        # still applies.
        env = dict(os.environ)
        inherited = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{PYTHON_SRC}{os.pathsep}{inherited}" if inherited else str(PYTHON_SRC)
        env.pop("SPECTRAFIT_GALLERY_THEME", None)  # light is the default; be explicit

        print(f"[gallery] rendering {script} ...")
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=GALLERY_DIR,
            check=True,
            env=env,
        )
        png_path = static_dir / f"{stem}.png"
        thumb_light_path = static_dir / f"{stem}-thumb-light.png"
        for expected in (png_path, thumb_light_path):
            if not expected.exists():
                msg = f"{script} ran but did not write expected {expected}"
                raise FileNotFoundError(msg)
        written.append(png_path)
        print(f"[gallery]   -> {png_path}")
        print(f"[gallery]   -> {thumb_light_path}")

        print(f"[gallery] rendering {script} (dark thumbnail) ...")
        dark_env = dict(env)
        dark_env["SPECTRAFIT_GALLERY_THEME"] = "dark"
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=GALLERY_DIR,
            check=True,
            env=dark_env,
        )
        thumb_dark_path = static_dir / f"{stem}-thumb-dark.png"
        if not thumb_dark_path.exists():
            msg = f"{script} (dark) ran but did not write expected {thumb_dark_path}"
            raise FileNotFoundError(msg)
        print(f"[gallery]   -> {thumb_dark_path}")
    return written


def run_snippets(scripts: tuple[str, ...] = SNIPPET_SCRIPTS) -> None:
    """Run each companion snippet script, asserting only that it still exits zero.

    Unlike `render_all`, these scripts produce no PNG (no plotting, no
    ``__main__`` guard) -- they exist to be included verbatim into a gallery
    page's prose, so the only claim this function can honestly check is that
    the published script still runs.

    Raises:
        subprocess.CalledProcessError: if any script exits non-zero.
    """
    for script in scripts:
        script_path = GALLERY_DIR / script
        print(f"[gallery] running snippet {script} ...")
        env = dict(os.environ)
        inherited = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{PYTHON_SRC}{os.pathsep}{inherited}" if inherited else str(PYTHON_SRC)
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=GALLERY_DIR,
            check=True,
            env=env,
        )
        print(f"[gallery]   -> {script} OK")


def main() -> None:
    """Render every gallery script, run every companion snippet, and report."""
    written = render_all()
    print(f"\n[gallery] wrote {len(written)} PNG(s) to {GALLERY_DIR / '_static'}")
    run_snippets()
    print(f"[gallery] ran {len(SNIPPET_SCRIPTS)} companion snippet(s)")


if __name__ == "__main__":
    main()
