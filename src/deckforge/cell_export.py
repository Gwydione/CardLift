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

PAIRED BACKS, AND WHY THIS MODULE STILL HAS NO BackMode CONCEPT
----------------------------------------------------------------------
`back` (one shared back page/geometry, at most one file) and
`paired_back` (one back page *per front cell*, each cropped at that
cell's own row/col on a separate, independently-calibrated geometry) are
just two different optional shapes `export_cells()` accepts -- this
module has no BackMode/SharedBackStatus enum of its own and never will,
since those are deckforge_gui concepts and this package does not depend
on deckforge_gui. Whichever back mode a deck actually uses is a decision
the caller (deckforge_gui.export_state) has already made by the time it
calls down here; this module only ever sees the resulting shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from PIL import Image

from .cropper import CardCropper
from .pdf_renderer import PDFRenderer
from .profile import GridGeometry, TrimValues

_ZERO_TRIM = TrimValues(0.0, 0.0, 0.0, 0.0)


def output_filenames(cell_count: int, has_back: bool, paired: bool = False) -> list[str]:
    """The exact filenames export_cells() will write for `cell_count`
    front cells -- the single source of truth for the naming convention,
    so a caller that needs to predict them (e.g. a pre-flight overwrite
    check) never has to duplicate this format string and risk it
    drifting from the one export_cells() itself uses.

    `paired=True` switches to the approved Paired Backs convention --
    "001_front.png", "001_back.png", "002_front.png", "002_back.png", ...
    -- so a front/back pair sorts adjacently in a file browser, instead
    of `has_back`'s single trailing "back.png" after every front_NNN.png.
    Mutually exclusive with `has_back` (a deck has exactly one back
    mode); `has_back` is ignored when `paired` is True."""
    assert not (has_back and paired), "has_back and paired are mutually exclusive"
    if paired:
        names: list[str] = []
        for i in range(1, cell_count + 1):
            names.append(f"{i:03d}_front.png")
            names.append(f"{i:03d}_back.png")
        return names
    names = [f"front_{i:03d}.png" for i in range(1, cell_count + 1)]
    if has_back:
        names.append("back.png")
    return names


def export_cells(
    renderer: PDFRenderer,
    render_scale: float,
    front_geometry: GridGeometry,
    cells: Sequence[tuple[int, int, int]],
    output_dir: Path,
    back: Optional[tuple[int, GridGeometry]] = None,
    paired_back: Optional[tuple[GridGeometry, Sequence[int]]] = None,
) -> list[Path]:
    """Exports exactly the given cells -- no more, no less -- plus
    whichever back shape the caller supplies, to output_dir.

    `cells` is an ordered sequence of (page_num, row, col), already
    filtered and ordered by the caller (e.g. a GUI's human-approved card
    list -- see deckforge_gui.export_state.build_export_plan()).
    front_NNN.png numbering (or, for Paired Backs, NNN_front.png/
    NNN_back.png numbering) follows this order exactly, 1-indexed --
    there is no re-sorting or re-grouping by page here, so the caller's
    order is authoritative.

    `back`, if given, is (page_num, geometry) for the one shared back
    card; omit it (None, the default) for a deck with no Shared Back --
    no back.png is written in that case.

    `paired_back`, if given, is (geometry, back_page_nums): one shared
    geometry -- Paired Backs, like Fronts, is one representative
    calibrated geometry reused for every back page, not a separate
    geometry per page -- plus a back page number per entry in `cells`,
    parallel-indexed to it. back_page_nums[i] is the back page holding
    the card paired with cells[i], cropped at cells[i]'s own (row, col):
    Front and Back are only guaranteed to share row/column topology, not
    geometry, so the cell index is the one thing safe to reuse as-is (see
    deckforge_gui.calibrate_state's paired_topology_mismatch()). Mutually
    exclusive with `back` -- a deck has exactly one back mode -- and
    switches output_filenames() to the NNN_front.png/NNN_back.png
    convention instead of appending one back.png.

    Each distinct page_num (front or back) is rendered at most once,
    cached internally by page number, regardless of how many cells on it
    are requested or what order they appear in `cells`/`paired_back` --
    callers are not required to pre-group or pre-sort by page for this to
    be efficient.
    """
    assert back is None or paired_back is None, "back and paired_back are mutually exclusive"
    if paired_back is not None:
        assert len(paired_back[1]) == len(cells), "paired_back's page list must match cells 1:1"

    output_dir.mkdir(parents=True, exist_ok=True)
    cropper = CardCropper(render_scale)
    page_cache: dict[int, Image.Image] = {}

    def rendered_page(page_num: int) -> Image.Image:
        image = page_cache.get(page_num)
        if image is None:
            image = renderer.render_page(page_num, render_scale)
            page_cache[page_num] = image
        return image

    def crop_and_save(page_image: Image.Image, geometry: GridGeometry, row: int, col: int, name: str) -> Path:
        card_img = cropper.crop_card(page_image, geometry, _ZERO_TRIM, row, col)
        out_path = output_dir / name
        card_img.save(out_path)
        return out_path

    written: list[Path] = []

    if paired_back is not None:
        back_geometry, back_page_nums = paired_back
        filenames = output_filenames(len(cells), has_back=False, paired=True)
        for i, ((page_num, row, col), back_page_num) in enumerate(zip(cells, back_page_nums)):
            written.append(crop_and_save(rendered_page(page_num), front_geometry, row, col, filenames[2 * i]))
            written.append(crop_and_save(rendered_page(back_page_num), back_geometry, row, col, filenames[2 * i + 1]))
        return written

    filenames = output_filenames(len(cells), back is not None)
    for name, (page_num, row, col) in zip(filenames, cells):
        written.append(crop_and_save(rendered_page(page_num), front_geometry, row, col, name))

    if back is not None:
        back_page_num, back_geometry = back
        written.append(crop_and_save(rendered_page(back_page_num), back_geometry, 0, 0, filenames[-1]))

    return written
