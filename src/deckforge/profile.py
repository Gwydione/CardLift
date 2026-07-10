"""
profile.py - calibration profile schema, loading, and validation.

A DeckProfile describes, in PDF points (1/72 inch, the same coordinate
space PyMuPDF reports for a page at zoom=1.0), one or more fixed grids of
card fronts across page ranges of a PDF, plus one shared back page.
Nothing here does any image analysis -- this module only knows about
numbers loaded from JSON.

WHY A DATACLASS INSTEAD OF A RAW DICT
--------------------------------------
Using dataclasses with named fields (instead of passing dicts around)
means every other module gets IDE autocomplete and type checking on
profile access, and profile.py is the single place that knows what a
valid profile looks like.

LAYOUTS: ONE OR MORE FRONT-CARD GRIDS
--------------------------------------
`DeckProfile.layouts` is a list of `CardLayout` -- each one a rows x cols
grid tied to a *contiguous* page range (`first_page`..`last_page`). Most
decks need exactly one. A deck with more than one card size/shape (e.g.
a small "boss card" layout on different pages from the main deck) can
list several layouts, processed in profile order, each with its own
geometry and trim.

A profile written the old way -- flat `first_front_page`/`last_front_page`/
`rows`/`cols`/`left`/`top`/`card_width`/`card_height`/`gap_x`/`gap_y` fields
at the top level, no `"layouts"` key -- is still accepted and is normalized
into a single-element `layouts` list at load time. `profile.layouts` is the
one authoritative representation every downstream module (cropper.py,
exporter.py, cli.py, calibrate_ui.py) reads from; DeckProfile does not also
keep a parallel set of legacy scalar fields.

Only *contiguous* page ranges are supported per layout (`first_page` to
`last_page`, inclusive) -- there is no separate "pages" list. A deck with
a non-contiguous front-page assignment can express it today as two layout
entries with identical geometry, each covering a contiguous sub-range.
An explicit, non-contiguous page list is deferred to a future phase.

THE SHARED BACK IS DELIBERATELY NOT A LAYOUT
----------------------------------------------
`back_page` and the optional `back_*` geometry overrides describe DeckForge's
one shared card back and stay at the top level of the profile, never folded
into `layouts`. A `CardLayout` means "a grid of front cards on some pages";
blurring that to also mean "or possibly the shared back" would make every
reader of `profile.layouts` re-derive which entries are real fronts. A
`CardLayout` is never constructed for the back page.

TRIM SCOPE: ONE UNAVOIDABLE DISTINCTION
------------------------------------------
Each `CardLayout` carries its own `trim_left`/`trim_right`/`trim_top`/
`trim_bottom` for its front cards. The back page is not a layout, so it
still needs trim values from somewhere -- they come from the top-level
`trim_left`/`trim_right`/`trim_top`/`trim_bottom` fields, which stay
required at the top of every profile (see `DeckProfile.back_trim()`).

For a legacy (no `"layouts"` key) profile this is invisible: there's only
one layout, normalized from those same top-level trim fields, so the same
four numbers govern both the front cards and the back card, exactly as
before. For a profile that writes an explicit `"layouts"` list, the
top-level `trim_*` fields apply to the back page ONLY -- each layout's own
front trim is separate. This is the one place layouts-mode and legacy-mode
profiles behave differently, and it exists because Phase I deliberately
does not introduce a new back-trim schema (e.g. `back_trim_left`) or
otherwise redesign how the back is trimmed.

FRONT/BACK GEOMETRY CAN DIFFER
-------------------------------
Some print-and-play decks lay out card fronts edge-to-edge (no gap) but
draw card backs smaller, centered in their cell with visible margin. To
support that without inventing a second profile file, every "back_*"
geometry field is OPTIONAL and falls back -- field by field -- to the
first layout's geometry (`profile.layouts[0]`) when omitted. If a deck's
back page shares its (single) front grid exactly, just leave the back_*
fields out of the JSON entirely. Profiles with more than one layout that
need a distinct back geometry must set the back_* overrides explicitly;
there is no per-layout back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Keys required/optional at the top level of every profile, regardless of
# whether it uses the legacy flat front fields or an explicit "layouts" list.
COMMON_REQUIRED_KEYS = [
    "back_page",
    "render_scale",
    "trim_left",
    "trim_right",
    "trim_top",
    "trim_bottom",
]
COMMON_OPTIONAL_KEYS = [
    "pdf_file",
    "back_left",
    "back_top",
    "back_card_width",
    "back_card_height",
    "back_gap_x",
    "back_gap_y",
]

# The old flat front-grid fields. Present together (no "layouts" key) ->
# normalized into a single-element layouts list. Mixing these with
# "layouts" is a load error -- see load_profile().
LEGACY_FRONT_KEYS = [
    "first_front_page",
    "last_front_page",
    "rows",
    "cols",
    "left",
    "top",
    "card_width",
    "card_height",
    "gap_x",
    "gap_y",
]

# Keys required/optional inside each entry of an explicit "layouts" list.
LAYOUT_REQUIRED_KEYS = [
    "first_page",
    "last_page",
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
]
LAYOUT_OPTIONAL_KEYS = ["name"]


@dataclass
class GridGeometry:
    """The grid parameters needed to compute one page's card cells."""
    left: float
    top: float
    card_width: float
    card_height: float
    gap_x: float
    gap_y: float


@dataclass(frozen=True)
class TrimValues:
    """Inward crop applied after grid positioning, in points. See
    geometry.trimmed_box(), which takes these same four values."""
    left: float
    right: float
    top: float
    bottom: float


@dataclass(frozen=True)
class CardLayout:
    """One rows x cols grid of card fronts across a contiguous page range.

    Immutable and self-contained: everything needed to find and crop this
    layout's cards lives on the layout itself, so exporter.py never needs
    to reach back into DeckProfile for front-card geometry or trim.
    """
    first_page: int
    last_page: int
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
    name: Optional[str] = None

    def geometry(self) -> GridGeometry:
        return GridGeometry(
            left=self.left,
            top=self.top,
            card_width=self.card_width,
            card_height=self.card_height,
            gap_x=self.gap_x,
            gap_y=self.gap_y,
        )

    def trim(self) -> TrimValues:
        return TrimValues(
            left=self.trim_left, right=self.trim_right,
            top=self.trim_top, bottom=self.trim_bottom,
        )

    def card_count(self) -> int:
        return (self.last_page - self.first_page + 1) * self.rows * self.cols

    def display_name(self, index: int) -> str:
        """A human-readable identifier for this layout: its own `name` if
        given, otherwise its 1-indexed position among the profile's
        layouts (`index` is 0-indexed)."""
        return self.name if self.name else f"layout {index + 1}"


@dataclass
class DeckProfile:
    name: str
    pdf_file: Optional[str]

    layouts: list[CardLayout]
    back_page: int
    render_scale: float

    trim_left: float
    trim_right: float
    trim_top: float
    trim_bottom: float

    back_left: Optional[float] = None
    back_top: Optional[float] = None
    back_card_width: Optional[float] = None
    back_card_height: Optional[float] = None
    back_gap_x: Optional[float] = None
    back_gap_y: Optional[float] = None

    def back_geometry(self) -> GridGeometry:
        """Back-page grid geometry, falling back -- field by field -- to
        the first layout's geometry for any back_* field left unset."""
        fallback = self.layouts[0].geometry()
        return GridGeometry(
            left=self.back_left if self.back_left is not None else fallback.left,
            top=self.back_top if self.back_top is not None else fallback.top,
            card_width=self.back_card_width if self.back_card_width is not None else fallback.card_width,
            card_height=self.back_card_height if self.back_card_height is not None else fallback.card_height,
            gap_x=self.back_gap_x if self.back_gap_x is not None else fallback.gap_x,
            gap_y=self.back_gap_y if self.back_gap_y is not None else fallback.gap_y,
        )

    def back_trim(self) -> TrimValues:
        """Trim for the shared back page. Always the top-level trim_*
        fields -- see this module's docstring ("TRIM SCOPE") for why the
        back doesn't get its own back_trim_* schema."""
        return TrimValues(
            left=self.trim_left, right=self.trim_right,
            top=self.trim_top, bottom=self.trim_bottom,
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

    def layout_for_page(self, page_num: int) -> Optional[CardLayout]:
        """The layout whose front-page range includes page_num, or None
        if no layout claims it (it may still be the shared back page --
        callers that care about that should check back_page too)."""
        for layout in self.layouts:
            if layout.first_page <= page_num <= layout.last_page:
                return layout
        return None


class ProfileError(Exception):
    """Raised for missing/invalid profile files. Caught in cli.py so the
    tool exits with a clean message instead of a traceback."""


def _is_comment_key(key: str) -> bool:
    return key.startswith("_")


def _check_card_size(card_width: float, card_height: float, where: str) -> None:
    if card_width <= 0 or card_height <= 0:
        raise ProfileError(
            f"{where} card_width and card_height must be positive point values. "
            f"They are 0 (or missing), which means this profile hasn't been "
            f"calibrated yet -- see README 'Calibrating a new deck'."
        )


def _parse_layout(raw_layout: dict, index: int, profile_name: str) -> CardLayout:
    where = f"profile '{profile_name}' layout {index + 1}"

    if not isinstance(raw_layout, dict):
        raise ProfileError(f"{where} must be a JSON object")

    missing = [k for k in LAYOUT_REQUIRED_KEYS if k not in raw_layout]
    if missing:
        raise ProfileError(f"{where} is missing required keys: {missing}")

    unknown = [
        k for k in raw_layout
        if k not in LAYOUT_REQUIRED_KEYS and k not in LAYOUT_OPTIONAL_KEYS and not _is_comment_key(k)
    ]
    if unknown:
        raise ProfileError(
            f"{where} has unrecognized keys: {unknown}. "
            f"(Keys starting with '_' are treated as comments and ignored.)"
        )

    _check_card_size(raw_layout["card_width"], raw_layout["card_height"], where=f"{where}:")

    first_page = raw_layout["first_page"]
    last_page = raw_layout["last_page"]
    if last_page < first_page:
        raise ProfileError(
            f"{where} has first_page ({first_page}) greater than last_page "
            f"({last_page}) -- only contiguous page ranges are supported."
        )

    return CardLayout(
        first_page=first_page,
        last_page=last_page,
        rows=raw_layout["rows"],
        cols=raw_layout["cols"],
        left=raw_layout["left"],
        top=raw_layout["top"],
        card_width=raw_layout["card_width"],
        card_height=raw_layout["card_height"],
        gap_x=raw_layout["gap_x"],
        gap_y=raw_layout["gap_y"],
        trim_left=raw_layout["trim_left"],
        trim_right=raw_layout["trim_right"],
        trim_top=raw_layout["trim_top"],
        trim_bottom=raw_layout["trim_bottom"],
        name=raw_layout.get("name"),
    )


def _validate_no_overlaps(layouts: list[CardLayout], profile_name: str) -> None:
    for i in range(len(layouts)):
        for j in range(i + 1, len(layouts)):
            a, b = layouts[i], layouts[j]
            overlap_start = max(a.first_page, b.first_page)
            overlap_end = min(a.last_page, b.last_page)
            if overlap_start <= overlap_end:
                raise ProfileError(
                    f"profile '{profile_name}' has overlapping layout page ranges: "
                    f"{a.display_name(i)} (pages {a.first_page}-{a.last_page}) and "
                    f"{b.display_name(j)} (pages {b.first_page}-{b.last_page}) both "
                    f"include page {overlap_start}. Each page must belong to at most "
                    f"one layout."
                )


def _validate_back_page_no_overlap(layouts: list[CardLayout], back_page: int, profile_name: str) -> None:
    for i, layout in enumerate(layouts):
        if layout.first_page <= back_page <= layout.last_page:
            raise ProfileError(
                f"profile '{profile_name}' back_page ({back_page}) falls inside "
                f"{layout.display_name(i)}'s front page range "
                f"({layout.first_page}-{layout.last_page}). back_page must not "
                f"overlap any layout's front pages."
            )


def load_profile(name: str, profiles_dir: Path) -> DeckProfile:
    path = profiles_dir / f"{name}.json"
    if not path.exists():
        raise ProfileError(f"profile '{name}' not found at {path}")

    with open(path, "r") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileError(f"profile '{name}' is not valid JSON: {e}") from e

    has_layouts = "layouts" in raw
    legacy_keys_present = [k for k in LEGACY_FRONT_KEYS if k in raw]
    has_legacy_front = bool(legacy_keys_present)

    if has_layouts and has_legacy_front:
        raise ProfileError(
            f"profile '{name}' has both 'layouts' and legacy front-grid keys "
            f"{legacy_keys_present} -- use one or the other. Remove the legacy "
            f"fields if using 'layouts', or remove 'layouts' if using the "
            f"legacy flat fields."
        )
    if not has_layouts and not has_legacy_front:
        raise ProfileError(
            f"profile '{name}' is missing required keys: must include either "
            f"a 'layouts' list or the legacy fields {LEGACY_FRONT_KEYS}"
        )

    missing_common = [k for k in COMMON_REQUIRED_KEYS if k not in raw]
    if missing_common:
        raise ProfileError(
            f"profile '{name}' is missing required keys: {missing_common}"
        )

    allowed_top_level = set(COMMON_REQUIRED_KEYS) | set(COMMON_OPTIONAL_KEYS)
    allowed_top_level |= {"layouts"} if has_layouts else set(LEGACY_FRONT_KEYS)
    unknown = [
        k for k in raw
        if k not in allowed_top_level and not _is_comment_key(k)
    ]
    if unknown:
        raise ProfileError(
            f"profile '{name}' has unrecognized keys: {unknown}. "
            f"(Keys starting with '_' are treated as comments and ignored.)"
        )

    if has_layouts:
        raw_layouts = raw["layouts"]
        if not isinstance(raw_layouts, list) or not raw_layouts:
            raise ProfileError(
                f"profile '{name}' 'layouts' must include at least one layout"
            )
        layouts = [
            _parse_layout(raw_layout, i, name) for i, raw_layout in enumerate(raw_layouts)
        ]
    else:
        missing_legacy = [k for k in LEGACY_FRONT_KEYS if k not in raw]
        if missing_legacy:
            raise ProfileError(
                f"profile '{name}' is missing required keys: {missing_legacy}"
            )
        _check_card_size(raw["card_width"], raw["card_height"], where=f"profile '{name}':")
        layouts = [
            CardLayout(
                first_page=raw["first_front_page"],
                last_page=raw["last_front_page"],
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
                name=None,
            )
        ]

    _validate_no_overlaps(layouts, name)
    _validate_back_page_no_overlap(layouts, raw["back_page"], name)

    return DeckProfile(
        name=name,
        pdf_file=raw.get("pdf_file"),
        layouts=layouts,
        back_page=raw["back_page"],
        render_scale=raw["render_scale"],
        trim_left=raw["trim_left"],
        trim_right=raw["trim_right"],
        trim_top=raw["trim_top"],
        trim_bottom=raw["trim_bottom"],
        back_left=raw.get("back_left"),
        back_top=raw.get("back_top"),
        back_card_width=raw.get("back_card_width"),
        back_card_height=raw.get("back_card_height"),
        back_gap_x=raw.get("back_gap_x"),
        back_gap_y=raw.get("back_gap_y"),
    )
