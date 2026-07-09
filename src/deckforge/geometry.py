"""
geometry.py - the manual-calibration grid math, and nothing else.

No PDF or image code lives here on purpose: these are pure functions over
numbers, which makes the core "where is card (row, col)?" logic trivial
to unit test and to reuse for automatic calibration later (an auto
calibrator would just need to produce a GridGeometry + trim values and
everything below keeps working unmodified).

------------------------------------------------------------------
THE MATH
------------------------------------------------------------------
For a grid with `rows` x `cols` cards, each cell's un-trimmed bounding
box in PDF points is:

    x0 = left + col * (card_width + gap_x)
    y0 = top  + row * (card_height + gap_y)
    x1 = x0 + card_width
    y1 = y0 + card_height

`left`/`top` is the top-left corner of card (row=0, col=0). `gap_x` /
`gap_y` is the empty space between adjacent cells (0 if cards are printed
edge-to-edge with no visible margin between them).

A trim is then subtracted inward from each side independently:

    x0 += trim_left
    y0 += trim_top
    x1 -= trim_right
    y1 -= trim_bottom

Trim exists so you can shave off a shared border or cut-line WITHOUT
touching card_width/card_height, which would shift the spacing of every
other card in the grid at the same time.
------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass

from .profile import GridGeometry


class GeometryError(Exception):
    pass


@dataclass(frozen=True)
class Box:
    """A crop box in PDF points."""
    x0: float
    y0: float
    x1: float
    y1: float

    def to_pixels(self, scale: float) -> tuple[int, int, int, int]:
        return (
            round(self.x0 * scale),
            round(self.y0 * scale),
            round(self.x1 * scale),
            round(self.y1 * scale),
        )

    def to_pixels_fixed_size(self, scale: float, width_px: int, height_px: int) -> tuple[int, int, int, int]:
        """Like to_pixels, but forces the box to an exact pixel width/
        height instead of rounding x1/y1 independently from x0/y0.

        Rounding x0 and x1 separately can make two cards that are the
        same size in points differ by 1px in pixels, purely from where
        their fractional-point offset happens to fall (e.g. col 0 starts
        at a whole-point boundary and rounds cleanly, col 1 starts at
        x.34pt and rounds the opposite way at its far edge). Since every
        card in the grid must come out pixel-identical, we round only the
        origin and then add a size that was rounded once, up front, and
        reused for every card.
        """
        x0_px = round(self.x0 * scale)
        y0_px = round(self.y0 * scale)
        return (x0_px, y0_px, x0_px + width_px, y0_px + height_px)


def cell_box(geometry: GridGeometry, row: int, col: int) -> Box:
    """Un-trimmed cell bounding box, in points."""
    x0 = geometry.left + col * (geometry.card_width + geometry.gap_x)
    y0 = geometry.top + row * (geometry.card_height + geometry.gap_y)
    x1 = x0 + geometry.card_width
    y1 = y0 + geometry.card_height
    return Box(x0, y0, x1, y1)


def trimmed_box(
    geometry: GridGeometry,
    row: int,
    col: int,
    trim_left: float,
    trim_top: float,
    trim_right: float,
    trim_bottom: float,
) -> Box:
    """Final crop box (post-trim), in points."""
    cell = cell_box(geometry, row, col)
    box = Box(
        x0=cell.x0 + trim_left,
        y0=cell.y0 + trim_top,
        x1=cell.x1 - trim_right,
        y1=cell.y1 - trim_bottom,
    )
    if box.x1 <= box.x0 or box.y1 <= box.y0:
        raise GeometryError(
            f"trim values collapse card (row={row}, col={col}) to a "
            f"zero/negative size box -- reduce trim_left/trim_right/"
            f"trim_top/trim_bottom"
        )
    return box


def iter_grid_positions(rows: int, cols: int):
    """Yields (row, col) in reading order: left-to-right, top-to-bottom."""
    for row in range(rows):
        for col in range(cols):
            yield row, col
