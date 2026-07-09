"""
measure.py - CLI-only calibration helper: converts pixel coordinates read
off a rendered preview/overlay image back into PDF points, and derives
suggested left/top/card_width/card_height/gap_x/gap_y values for a
profile.

This module is deliberately independent of pdf_renderer.py, cropper.py,
and exporter.py: it does no rendering or cropping, only arithmetic over
numbers the user already has (pixel coordinates read by eye off an image
they already generated with --preview/--overlay). Keeping it separate
means --measure can never touch the crop/export pipeline, and the
pixel<->point math can be unit tested without a PDF fixture.

THE INVERSE PROBLEM
--------------------
geometry.py's cell_box() computes a cell's box FROM known left/top/
card_width/card_height/gap. --measure runs that arithmetic backwards:
given one or two cells' actual pixel boxes (read off a rendered image)
plus which (row, col) each one is, solve for the grid parameters that
would produce them.

One measurement is enough to derive card_width/card_height (its own box
size) and left/top (back-solved using a known or assumed gap). A second
measurement in a different row and/or column lets gap_y and/or gap_x be
solved for directly, since the grid is linear:

    origin_x(row, col) = left + col * (card_width + gap_x)
    origin_y(row, col) = top  + row * (card_height + gap_y)

so for two measured cells A and B:

    gap_x = (originB_x - originA_x) / (colB - colA) - card_width   (colB != colA)
    gap_y = (originB_y - originA_y) / (rowB - rowA) - card_height  (rowB != rowA)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

CARD_SPEC_RE = re.compile(r"^r(\d+)c(\d+)$", re.IGNORECASE)

# Field order matches MeasuredGeometry's (left, top, card_width,
# card_height, gap_x, gap_y) so callers can zip() them together.
FRONT_FIELDS = ("left", "top", "card_width", "card_height", "gap_x", "gap_y")
BACK_FIELDS = (
    "back_left", "back_top", "back_card_width", "back_card_height",
    "back_gap_x", "back_gap_y",
)


class MeasureError(Exception):
    """Raised for malformed --card specs or measurements that don't make
    geometric sense (e.g. a pixel box with zero/negative size)."""


@dataclass(frozen=True)
class PixelBox:
    """A card's visible corners, in pixels, as read off a rendered image."""
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class CardMeasurement:
    row: int
    col: int
    box: PixelBox


def parse_card_measurement(spec: str) -> CardMeasurement:
    """Parses one --card argument, e.g. "r0c1:1000,420,1720,1360", into a
    CardMeasurement. The row/col part identifies which grid cell the box
    was measured on; the four numbers are pixel coordinates of that
    cell's top-left and bottom-right corners in the image measured from.
    """
    if ":" not in spec:
        raise MeasureError(
            f"--card '{spec}' is missing the ':' separating the cell "
            f"(e.g. 'r0c0') from its pixel box (e.g. '240,420,960,1360')"
        )
    cell_part, box_part = spec.split(":", 1)

    match = CARD_SPEC_RE.match(cell_part.strip())
    if not match:
        raise MeasureError(
            f"--card cell '{cell_part}' is not in 'rNcN' form, e.g. 'r0c0'"
        )
    row, col = int(match.group(1)), int(match.group(2))

    coords = box_part.split(",")
    if len(coords) != 4:
        raise MeasureError(
            f"--card box '{box_part}' must be 4 comma-separated pixel "
            f"values: x1,y1,x2,y2 (top-left corner, then bottom-right)"
        )
    try:
        x1, y1, x2, y2 = (float(c.strip()) for c in coords)
    except ValueError:
        raise MeasureError(f"--card box '{box_part}' contains a non-numeric value")

    if x2 <= x1 or y2 <= y1:
        raise MeasureError(
            f"--card '{spec}': box (x1,y1)-(x2,y2) must have x2>x1 and "
            f"y2>y1 (top-left corner first, then bottom-right corner)"
        )

    return CardMeasurement(row=row, col=col, box=PixelBox(x1, y1, x2, y2))


@dataclass(frozen=True)
class MeasuredGeometry:
    left: float
    top: float
    card_width: float
    card_height: float
    gap_x: Optional[float]
    gap_y: Optional[float]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def derive_geometry(
    measurements: Sequence[CardMeasurement],
    scale: float,
    fallback_gap_x: float = 0.0,
    fallback_gap_y: float = 0.0,
) -> MeasuredGeometry:
    """Derives left/top/card_width/card_height (and gap_x/gap_y, if two
    measurements pin them down) from one or two CardMeasurements.

    `scale` is the profile's render_scale (points-to-pixels) used to
    render the image the pixel coordinates were read from. `fallback_gap_x`
    / `fallback_gap_y` are used to back-solve left/top when only one
    measurement is given and it isn't row 0 / col 0 (where gap doesn't
    matter) -- pass the profile's current gap so the result is exact if
    that's already correct, or 0.0 if it isn't known yet.
    """
    if not measurements:
        raise MeasureError("--measure needs at least one --card measurement")
    if len(measurements) > 2:
        raise MeasureError(
            f"--measure takes at most 2 --card points (one to size a cell, "
            f"a second in a different row/col to derive gap); got "
            f"{len(measurements)}"
        )
    if scale <= 0:
        raise MeasureError(f"render_scale must be positive, got {scale}")

    def to_points(box: PixelBox) -> tuple[float, float, float, float]:
        return (box.x1 / scale, box.y1 / scale, box.x2 / scale, box.y2 / scale)

    a = measurements[0]
    ax0, ay0, ax1, ay1 = to_points(a.box)
    card_width = ax1 - ax0
    card_height = ay1 - ay0

    warnings: list[str] = []
    gap_x: Optional[float] = None
    gap_y: Optional[float] = None

    if len(measurements) == 2:
        b = measurements[1]
        bx0, by0, bx1, by1 = to_points(b.box)

        if b.row == a.row and b.col == a.col:
            warnings.append(
                f"both --card points are r{a.row}c{a.col} -- a second "
                f"point only helps if it's a different row and/or column"
            )

        size_tolerance_pt = 2.0
        if abs((bx1 - bx0) - card_width) > size_tolerance_pt or abs((by1 - by0) - card_height) > size_tolerance_pt:
            warnings.append(
                f"r{a.row}c{a.col} and r{b.row}c{b.col} measured different "
                f"card sizes (>{size_tolerance_pt}pt apart) -- double-check "
                f"the pixel coordinates, or the grid isn't uniform"
            )

        if b.col != a.col:
            gap_x = (bx0 - ax0) / (b.col - a.col) - card_width
        if b.row != a.row:
            gap_y = (by0 - ay0) / (b.row - a.row) - card_height

    effective_gap_x = gap_x if gap_x is not None else fallback_gap_x
    effective_gap_y = gap_y if gap_y is not None else fallback_gap_y

    left = ax0 - a.col * (card_width + effective_gap_x)
    top = ay0 - a.row * (card_height + effective_gap_y)

    return MeasuredGeometry(
        left=left, top=top,
        card_width=card_width, card_height=card_height,
        gap_x=gap_x, gap_y=gap_y,
        warnings=tuple(warnings),
    )


def format_suggested_patch(
    measured: MeasuredGeometry,
    current: Mapping[str, float],
    field_names: Sequence[str] = FRONT_FIELDS,
) -> str:
    """Formats a human-readable "old -> new" patch listing for the six
    grid fields, ready to copy into a profile JSON file by hand. Fields
    that couldn't be derived (gap_x/gap_y from a single measurement) are
    listed as unchanged, with a note explaining how to derive them."""
    new_values = (
        measured.left, measured.top,
        measured.card_width, measured.card_height,
        measured.gap_x, measured.gap_y,
    )
    lines = []
    for name, new_value in zip(field_names, new_values):
        old_value = current.get(name, 0.0)
        if new_value is None:
            lines.append(
                f'  "{name}": {old_value:.3f}  (unchanged -- not enough '
                f"points to derive; add a second --card in a different "
                f"row/col)"
            )
        else:
            lines.append(f'  "{name}": {old_value:.3f} -> {new_value:.3f}')
    return "\n".join(lines)
