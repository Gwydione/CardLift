"""
profile.py - calibration profile schema, loading, and validation.

A DeckProfile describes, in PDF points (1/72 inch, the same coordinate
space PyMuPDF reports for a page at zoom=1.0), a fixed grid of cards on a
PDF page: where the grid starts, how big each card cell is, how much
space sits between cells, and how far to trim inward from each cell edge
before saving. Nothing here does any image analysis -- this module only
knows about numbers loaded from JSON.

WHY A DATACLASS INSTEAD OF A RAW DICT
--------------------------------------
Using a dataclass with named fields (instead of passing a dict around)
means every other module gets IDE autocomplete and type checking on
profile access, and profile.py is the single place that knows what a
valid profile looks like. If the profile schema grows later (e.g. to
support automatic calibration or per-page overrides), this is the only
file that needs to change shape.

FRONT/BACK GEOMETRY CAN DIFFER
-------------------------------
Some print-and-play decks lay out card fronts edge-to-edge (no gap) but
draw card backs smaller, centered in their cell with visible margin
(often because the back design has its own decorative border). To
support that without inventing a second profile file, every "back_*"
field is OPTIONAL and falls back to the matching front-grid field when
omitted. If your deck's back page uses the exact same grid as the
fronts, just leave the back_* fields out of the JSON entirely.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional


REQUIRED_KEYS = [
    "first_front_page",
    "last_front_page",
    "back_page",
    "rows",
    "cols",
    "left",
    "top",
    "card_width",
    "card_height",
    "gap_x",
    "gap_y",
    "trim_left",
    "trim_right",
    "trim_top",
    "trim_bottom",
    "render_scale",
]

# Optional keys: back-page geometry overrides, and the source PDF filename.
# `pdf_file` isn't in the brief's example profile, but a profile has to
# name its deck somehow to be reusable -- see README "Profiles" section.
OPTIONAL_KEYS = [
    "pdf_file",
    "back_left",
    "back_top",
    "back_card_width",
    "back_card_height",
    "back_gap_x",
    "back_gap_y",
]


@dataclass
class GridGeometry:
    """The grid parameters needed to compute one page's card cells."""
    left: float
    top: float
    card_width: float
    card_height: float
    gap_x: float
    gap_y: float


@dataclass
class DeckProfile:
    name: str
    pdf_file: Optional[str]

    first_front_page: int
    last_front_page: int
    back_page: int

    rows: int
    cols: int

    left: float
    top: float
    card_width: float
    card_height: float
    gap_x: float
    gap_y: float

    trim_left: float
    trim_right: float
    trim_top: float
    trim_bottom: float

    render_scale: float

    back_left: Optional[float] = None
    back_top: Optional[float] = None
    back_card_width: Optional[float] = None
    back_card_height: Optional[float] = None
    back_gap_x: Optional[float] = None
    back_gap_y: Optional[float] = None

    def front_geometry(self) -> GridGeometry:
        return GridGeometry(
            left=self.left,
            top=self.top,
            card_width=self.card_width,
            card_height=self.card_height,
            gap_x=self.gap_x,
            gap_y=self.gap_y,
        )

    def back_geometry(self) -> GridGeometry:
        """Back-page grid geometry, falling back to front-grid values for
        any back_* field left unset in the JSON."""
        return GridGeometry(
            left=self.back_left if self.back_left is not None else self.left,
            top=self.back_top if self.back_top is not None else self.top,
            card_width=self.back_card_width if self.back_card_width is not None else self.card_width,
            card_height=self.back_card_height if self.back_card_height is not None else self.card_height,
            gap_x=self.back_gap_x if self.back_gap_x is not None else self.gap_x,
            gap_y=self.back_gap_y if self.back_gap_y is not None else self.gap_y,
        )

    def uses_back_override(self) -> bool:
        return any(
            v is not None
            for v in (
                self.back_left, self.back_top,
                self.back_card_width, self.back_card_height,
                self.back_gap_x, self.back_gap_y,
            )
        )


class ProfileError(Exception):
    """Raised for missing/invalid profile files. Caught in cli.py so the
    tool exits with a clean message instead of a traceback."""


def load_profile(name: str, profiles_dir: Path) -> DeckProfile:
    path = profiles_dir / f"{name}.json"
    if not path.exists():
        raise ProfileError(f"profile '{name}' not found at {path}")

    with open(path, "r") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileError(f"profile '{name}' is not valid JSON: {e}") from e

    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ProfileError(
            f"profile '{name}' is missing required keys: {missing}"
        )

    unknown = [
        k for k in raw
        if k not in REQUIRED_KEYS and k not in OPTIONAL_KEYS and not k.startswith("_")
    ]
    if unknown:
        raise ProfileError(
            f"profile '{name}' has unrecognized keys: {unknown}. "
            f"(Keys starting with '_' are treated as comments and ignored.)"
        )

    if raw["card_width"] <= 0 or raw["card_height"] <= 0:
        raise ProfileError(
            "card_width and card_height must be positive point values. "
            "They are 0 (or missing), which means this profile hasn't been "
            "calibrated yet -- see README 'Calibrating a new deck'."
        )

    profile = DeckProfile(
        name=name,
        pdf_file=raw.get("pdf_file"),
        first_front_page=raw["first_front_page"],
        last_front_page=raw["last_front_page"],
        back_page=raw["back_page"],
        rows=raw["rows"],
        cols=raw["cols"],
        left=raw["left"],
        top=raw["top"],
        card_width=raw["card_width"],
        card_height=raw["card_height"],
        gap_x=raw["gap_x"],
        gap_y=raw["gap_y"],
        trim_left=raw["trim_left"],
        trim_right=raw["trim_right"],
        trim_top=raw["trim_top"],
        trim_bottom=raw["trim_bottom"],
        render_scale=raw["render_scale"],
        back_left=raw.get("back_left"),
        back_top=raw.get("back_top"),
        back_card_width=raw.get("back_card_width"),
        back_card_height=raw.get("back_card_height"),
        back_gap_x=raw.get("back_gap_x"),
        back_gap_y=raw.get("back_gap_y"),
    )
    return profile
