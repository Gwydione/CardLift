"""
cell_export.py - exports an explicit, pre-approved list of individual card
cells (page_num, row, col) to PNG files, plus one optional shared back.

This is a deliberately different entry point from exporter.DeckExporter.
DeckExporter.export() walks profile.layouts, and a CardLayout always means
"a complete, regular rows x cols grid" -- every cell in its page range is
exported, with no way to omit one (see CardCropper.crop_all() /
geometry.iter_grid_positions()). That is the right model for a
hand-authored CLI profile, but it cannot represent a GUI Review Cards step
where a human has already excluded specific over-suggested cells from an
otherwise regular grid: forcing that reviewed, possibly-sparse cell list
through a CardLayout would either silently re-include the excluded cells
or require teaching CardLayout/DeckProfile a new sparse-grid concept that
neither the CLI nor any hand-authored profile has ever needed.

export_cells() instead takes the exact ordered list of cells to export --
no notion of a "complete grid" at all -- and reuses PDFRenderer and
CardCropper, the same lower-level primitives DeckExporter itself is built
on, rather than duplicating page rendering or cropping. Nothing here
constructs or reads a DeckProfile/CardLayout.

Trim is always zero here, matching deckforge_gui's Calibrate model: the
two-corner click a user makes there already IS the exact crop box (see
deckforge_gui.calibrate_state.CalibratedGeometry's docstring), unlike the
CLI's eyeballed-pixel-coordinates flow that trim exists to nudge
afterward.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from PIL import Image

from .cropper import CardCropper
from .pdf_renderer import PDFRenderer
from .profile import GridGeometry, TrimValues

_ZERO_TRIM = TrimValues(0.0, 0.0, 0.0, 0.0)


def export_cells(
    renderer: PDFRenderer,
    render_scale: float,
    front_geometry: GridGeometry,
    cells: Sequence[tuple[int, int, int]],
    output_dir: Path,
    back: Optional[tuple[int, GridGeometry]] = None,
) -> list[Path]:
    """Exports exactly the given cells -- no more, no less -- plus one
    optional shared back, to output_dir.

    `cells` is an ordered sequence of (page_num, row, col), already
    filtered and ordered by the caller (e.g. a GUI's human-approved card
    list -- see deckforge_gui.export_state.build_export_plan()).
    front_NNN.png numbering follows this order exactly, 1-indexed -- there
    is no re-sorting or re-grouping by page here, so the caller's order is
    authoritative.

    `back`, if given, is (page_num, geometry) for the one shared back
    card; omit it entirely (None, the default) for a Deck with no Shared
    Back -- no back.png is written in that case.

    Each distinct page_num is rendered at most once, cached internally by
    page number, regardless of how many cells on it are requested or what
    order they appear in `cells` -- callers are not required to
    pre-group or pre-sort by page for this to be efficient.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cropper = CardCropper(render_scale)
    page_cache: dict[int, Image.Image] = {}

    def rendered_page(page_num: int) -> Image.Image:
        image = page_cache.get(page_num)
        if image is None:
            image = renderer.render_page(page_num, render_scale)
            page_cache[page_num] = image
        return image

    written: list[Path] = []
    for index, (page_num, row, col) in enumerate(cells, start=1):
        page_image = rendered_page(page_num)
        card_img = cropper.crop_card(page_image, front_geometry, _ZERO_TRIM, row, col)
        out_path = output_dir / f"front_{index:03d}.png"
        card_img.save(out_path)
        written.append(out_path)

    if back is not None:
        back_page_num, back_geometry = back
        back_image = rendered_page(back_page_num)
        back_card = cropper.crop_card(back_image, back_geometry, _ZERO_TRIM, 0, 0)
        back_path = output_dir / "back.png"
        back_card.save(back_path)
        written.append(back_path)

    return written
