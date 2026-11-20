"""Shared plotting convention for the ``docs/tutorials/gallery`` scripts.

This module is **gallery-internal tooling** — it is not part of the public
``spectrafit_core`` package and carries no API stability guarantee. It exists
so the sibling example scripts in this directory (``fitting.py``,
``3d_fitting.py``, ``multi_dataset_1d.py``, ``multi_dataset_2d.py``,
``shared_params.py``) share one visual language instead of each rolling its
own ad-hoc matplotlib calls.

Import it as a plain sibling module, e.g.::

    from _plotting import plot_fit, savefig

Dependency-light by design: matplotlib + numpy only (no seaborn, no
spectrafit_core import) so it stays trivially importable from any gallery
script.

Note on dimensionality: ``plot_fit`` only ever draws a 2-D (x, y) curve view.
For genuinely 3-D data (e.g. ``3d_fitting.py``), the caller is responsible
for first projecting or slicing down to a 2-D (x, y) representation (a
line-out, a marginal, a fixed-axis slice, ...) before calling ``plot_fit`` —
this helper does not do any 3-D plotting itself.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from numpy.typing import ArrayLike

# --------------------------------------------------------------------------
# Gallery-wide style
# --------------------------------------------------------------------------
# Folded in here (rather than a separate _style.py) to keep the gallery's
# dependency footprint to a single sibling import. Applied at import time so
# every script that does `from _plotting import plot_fit` picks it up for
# free, without an extra setup call.

FIGSIZE: tuple[float, float] = (7.0, 5.0)
"""Default figure size (inches) for a plot with no residuals subplot."""

FIGSIZE_WITH_RESIDUALS: tuple[float, float] = (7.0, 6.0)
"""Default figure size (inches) when a residuals subplot is added."""

SAVE_DPI: int = 150
"""Fixed DPI used by :func:`savefig` for all gallery full-size PNGs."""

THUMB_WIDTH_PX: int = 600
"""Target pixel width for gallery-index thumbnails.

The index (``docs/tutorials/gallery/index.md``) displays every thumbnail at
``width="300"`` (CSS px); this is 2x that, so the thumbnail is crisp on a
retina/HiDPI display instead of being upscaled by the browser.
"""

_DATA_COLOR = "#4C72B0"
_FIT_COLOR = "#C44E52"
_COMPONENT_COLORS = ("#55A868", "#8172B2", "#CCB974", "#64B5CD", "#DD8452")

_STATIC_DIR = Path(__file__).parent / "_static"

# --------------------------------------------------------------------------
# Light/dark theming
# --------------------------------------------------------------------------
# `_render.py` runs every gallery script twice, as two separate subprocesses
# (see its `render_all`) — once with this variable unset (light, the
# original/default behavior, feeding the full-size PNG every tutorial detail
# page embeds) and once with it set to "dark" (feeding only a thumbnail-sized
# dark-themed PNG for the gallery index's light/dark swap, mirroring
# `.sf-hero__media-img--light/--dark` in docs/stylesheets/pages/hero.css).
# A fresh subprocess per theme -- rather than mutating already-drawn artists
# in one process -- means rcParams-driven chrome (ticks, spines, grid,
# legend text, figure/axes background) AND any color a script hardcodes via
# `MUTED_COLOR` below both pick up the right palette for free; nothing here
# repaints a Line2D after the fact, and no plotted data trace ever changes
# hue between themes (only backgrounds and muted/reference-line grays do).
_THEME = os.environ.get("SPECTRAFIT_GALLERY_THEME", "light").strip().lower()
_DARK = _THEME == "dark"

MUTED_COLOR: str
"""Theme-aware gray for secondary/reference plot elements.

Used for zero-lines, error bars, and annotation call-outs that must stay
readable on both a white (light) and a near-black (dark) figure background
-- never for an actual data or fit trace, whose color is meaningful and
must not change with theme.
"""
MUTED_COLOR = "0.75" if _DARK else "0.35"

# Close to the docs site's dark page background (~rgb(11, 12, 15), see
# docs/stylesheets/tokens/palette.css's [data-md-color-scheme="slate"]) but
# lifted a step so the figure still reads as its own panel rather than
# disappearing into the page. Foreground colors picked for >= 4.5:1 contrast
# against that background; data/fit colors above are untouched. Defined
# unconditionally (not just inside the `if _DARK:` block below) so
# ANNOTATION_BBOX can reference them regardless of which theme is active.
_fig_bg = "#16181d"
_fg = "#d8dade"
_grid = "#3c3f46"

_rc: dict[str, object] = {
    "figure.dpi": 100,
    "savefig.dpi": SAVE_DPI,
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "lines.linewidth": 1.8,
    "scatter.marker": "o",
}
if _DARK:
    _rc.update(
        {
            "figure.facecolor": _fig_bg,
            "savefig.facecolor": _fig_bg,
            "axes.facecolor": _fig_bg,
            "axes.edgecolor": _grid,
            "axes.labelcolor": _fg,
            "axes.titlecolor": _fg,
            "text.color": _fg,
            "xtick.color": _fg,
            "ytick.color": _fg,
            "grid.color": _grid,
            "legend.labelcolor": _fg,
        },
    )
plt.rcParams.update(_rc)

OUTLINE_COLOR: str
"""High-contrast marker-outline color (e.g. a ring drawn around flagged
data points). Unlike :data:`MUTED_COLOR` (deliberately de-emphasized), this
is meant to read as a strong accent against the figure background in
either theme -- black on light, near-white on dark.
"""
OUTLINE_COLOR = _fg if _DARK else "black"

ANNOTATION_BBOX: dict[str, object]
"""Theme-aware ``bbox=`` kwargs for the small monospace stats/readout boxes
several gallery scripts annotate directly onto their axes (fit-quality
numbers, solver comparisons, ...). A hardcoded white box is itself a
miniature instance of the dark-mode "white slab" problem this module's
theming exists to fix, so its facecolor tracks the same panel background
used everywhere else in the dark render instead of staying white.
"""
ANNOTATION_BBOX = {
    "boxstyle": "round",
    "facecolor": _fig_bg if _DARK else "white",
    "alpha": 0.85,
    "edgecolor": _grid if _DARK else "0.7",
}


def _iter_components(
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None,
) -> Iterable[tuple[str, ArrayLike]]:
    """Normalize the ``components`` argument to an iterable of (label, array).

    Accepts either a dict (``{"peak_1": y1, "peak_2": y2}``) or an iterable of
    ``(label, array)`` pairs — whichever reads more naturally at the call
    site (a dict is convenient when components come from a keyed structure
    like a fit graph's nodes; a list of pairs is convenient when order matters
    and labels are generated on the fly, e.g. ``[("peak", y1), ("bg", y2)]``).
    """
    if components is None:
        return []
    if isinstance(components, Mapping):
        return cast("list[tuple[str, ArrayLike]]", list(components.items()))
    return list(components)


def plot_fit(
    x: ArrayLike,
    y: ArrayLike,
    y_fit: ArrayLike,
    *,
    residuals: ArrayLike | None = None,
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None = None,
    title: str | None = None,
    ax: Axes | None = None,
) -> tuple[Figure, Axes]:
    """Plot data + fitted curve (+ optional residuals, + optional components).

    Args:
        x: The observed x data, drawn as a semi-transparent scatter.
        y: The observed y data, drawn as a semi-transparent scatter.
        y_fit: The fitted curve, drawn as a solid line on top of the data.
        residuals: If given, a residuals subplot is added below the main
            plot (shared x-axis), with a dashed zero line. Ignored (with no
            error) if ``ax`` is given — see below.
        components: Individual model components (e.g. per-peak
            contributions) overlaid as dashed lines, each with its own
            legend entry. Accepts either a ``dict`` or a list of
            ``(label, array)`` pairs.
        title: Main axes title.
        ax: If given, plot into this axes and return it as-is — no
            residuals subplot is created in this case, since the caller
            already owns the figure layout and is expected to place/size a
            residuals axes itself if it wants one. If ``None`` (the
            default), a new figure is created via ``plt.subplots`` (sized
            from :data:`FIGSIZE` / :data:`FIGSIZE_WITH_RESIDUALS`, adding a
            residuals row when ``residuals`` is given).

    Returns:
        The figure and the *main* axes (not the residuals axes). When
        ``ax`` was passed in, ``fig`` is ``ax.get_figure()`` — the return
        shape is always a 2-tuple regardless of whether a new figure was
        created, so callers do not need to special-case ``ax is None``.

    Note:
        This function only ever draws a 2-D (x, y) view. For 3-D data,
        project or slice to 2-D before calling this — see the module
        docstring.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    y_fit = np.asarray(y_fit)

    if ax is not None:
        _draw_main(ax, x, y, y_fit, components=components, title=title)
        # `Axes.get_figure()` is typed as `Figure | SubFigure | None`; in
        # practice an axes we were handed always has a real parent Figure.
        return cast("Figure", ax.get_figure()), ax

    if residuals is not None:
        fig, (ax_main, ax_res) = plt.subplots(
            2,
            1,
            figsize=FIGSIZE_WITH_RESIDUALS,
            sharex=True,
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
        )
        _draw_main(ax_main, x, y, y_fit, components=components, title=title)
        _draw_residuals(ax_res, x, residuals)
        ax_main.set_xlabel("")  # xlabel lives on the shared bottom axes
        return fig, ax_main

    fig, ax_main = plt.subplots(figsize=FIGSIZE)
    _draw_main(ax_main, x, y, y_fit, components=components, title=title)
    return fig, ax_main


def _draw_main(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    y_fit: np.ndarray,
    *,
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None,
    title: str | None,
) -> None:
    ax.scatter(x, y, s=18, alpha=0.45, color=_DATA_COLOR, label="data", zorder=2)
    ax.plot(x, y_fit, color=_FIT_COLOR, linestyle="-", label="fit", zorder=3)

    for i, (label, comp) in enumerate(_iter_components(components)):
        color = _COMPONENT_COLORS[i % len(_COMPONENT_COLORS)]
        ax.plot(
            x,
            np.asarray(comp),
            color=color,
            linestyle="--",
            linewidth=1.4,
            label=label,
            zorder=1,
        )

    if title:
        ax.set_title(title)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="best")


def _draw_residuals(ax: Axes, x: np.ndarray, residuals: ArrayLike) -> None:
    residuals = np.asarray(residuals)
    ax.axhline(0.0, color=MUTED_COLOR, linestyle="--", linewidth=1.0, zorder=1)
    ax.scatter(x, residuals, s=14, alpha=0.55, color=_DATA_COLOR, zorder=2)
    ax.set_xlabel("x")
    ax.set_ylabel("residuals")


def savefig(fig: Figure, name: str, *, static_dir: Path | str | None = None) -> Path:
    """Save ``fig`` for the gallery, theme-branched via ``SPECTRAFIT_GALLERY_THEME``.

    Every gallery script calls this exactly once with the same two
    arguments regardless of theme — the branching lives entirely here so no
    script needs to know or care which pass of ``_render.py`` it is in.

    Light (default, ``SPECTRAFIT_GALLERY_THEME`` unset): writes the
    full-size PNG to ``<static_dir>/<name>.png`` at :data:`SAVE_DPI`, exactly
    as before — this is the file every tutorial detail page embeds at native
    resolution. Also derives ``<static_dir>/<name>-thumb-light.png`` by
    downsizing that same PNG to :data:`THUMB_WIDTH_PX`, so the gallery
    index's thumbnail is pixel-identical to the full figure, just smaller.

    Dark (``SPECTRAFIT_GALLERY_THEME=dark``): nothing links to a full-size
    dark PNG (detail pages stay full-size/light-only), so this renders
    directly at thumbnail resolution — ``<static_dir>/<name>-thumb-dark.png``
    — instead of paying to rasterize a full-size asset nobody serves.

    Args:
        fig: The figure to save (e.g. the one returned by :func:`plot_fit`).
        name: File stem (no extension, no path separators).
        static_dir: Destination directory. Defaults to
            ``docs/tutorials/gallery/_static`` (created if it does not
            exist).

    Returns:
        The full-size path in the light pass; the dark-thumbnail path in
        the dark pass (there is no full-size dark file to point to).
    """
    out_dir = Path(static_dir) if static_dir is not None else _STATIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if _DARK:
        width_in, _height_in = fig.get_size_inches()
        dpi = max(1.0, THUMB_WIDTH_PX / float(width_in))
        out_path = out_dir / f"{name}-thumb-dark.png"
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
        # The dark pass renders straight at thumbnail size, so it never passes
        # through the resize branch of `_save_thumbnail` -- but it still needs
        # the same palette quantisation, or the index pays RGBA prices for half
        # its images. Re-encode in place.
        _quantise_in_place(out_path)
        return out_path

    out_path = out_dir / f"{name}.png"
    fig.savefig(out_path, dpi=SAVE_DPI, bbox_inches="tight")
    _save_thumbnail(out_path, out_dir / f"{name}-thumb-light.png")
    return out_path


def _save_thumbnail(src: Path, dest: Path) -> None:
    """Downsize the just-rendered ``src`` PNG to :data:`THUMB_WIDTH_PX` wide.

    Resizes the real rendered PNG rather than re-rendering at a lower DPI,
    so the thumbnail is guaranteed to be the same picture as the full-size
    figure the tutorial detail page shows, not a separately-drawn one that
    could drift from it.

    Written as a 256-colour palette PNG. Serving a light AND a dark thumbnail
    doubles the index's image requests -- a ``display:none`` image is still
    fetched -- so an RGBA pair came out ~9% HEAVIER than the single full-size
    set it replaced, which would have defeated the point of shrinking them.
    Measured over all 32 thumbnails: RGBA 1793 KiB, lossless RGB re-encode 2366
    KiB (matplotlib's own encoder beats Pillow's here), 256-colour palette 708
    KiB against a 1638 KiB baseline -- a 57% cut, and the only option that pays
    for the dark variant instead of merely affording it.

    Quantisation is confined to THUMBNAILS. The full-resolution figure each
    tutorial page embeds is untouched and lossless: a thumbnail is a 300px
    navigational affordance, the detail figure is the scientific content. The
    error is edge-only -- mean per-channel delta 1.66 of 255, concentrated in
    anti-aliased curve edges -- and unlike a hue inversion it does not
    systematically shift a colour, so a red residual stays red.
    """
    from PIL import Image

    with Image.open(src) as im:
        if im.width <= THUMB_WIDTH_PX:
            small = im.copy()
        else:
            ratio = THUMB_WIDTH_PX / im.width
            target_size = (THUMB_WIDTH_PX, max(1, round(im.height * ratio)))
            small = im.resize(target_size, Image.LANCZOS)
        # Flatten onto the figure's own background before quantising: a palette
        # PNG carries no alpha channel, and dropping it unflattened would turn
        # transparent margins black.
        if small.mode in ("RGBA", "LA", "P"):
            small = small.convert("RGB")
        quantised = small.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        quantised.save(dest, optimize=True)


def _quantise_in_place(path: Path) -> None:
    """Re-encode an already-written thumbnail as a 256-colour palette PNG."""
    from PIL import Image

    with Image.open(path) as im:
        flat = im.convert("RGB")
        quantised = flat.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    quantised.save(path, optimize=True)
