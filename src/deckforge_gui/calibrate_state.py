"""Calibrate state -- precise per-card geometry, derived from two-corner
clicks on one representative page each for "Fronts" and "Shared Back".

Deliberately free of any PySide6 import, same rationale as app_state.py/
session.py/find_cards_state.py: this is the controller/session layer the
GUI reads from, unit tested without opening a window.

WHY THIS DOESN'T MIRROR THE CLI'S "COPY INTO PROFILE JSON" STEP
------------------------------------------------------------------
The CLI's --calibrate never writes a profile; it only prints/copies a
suggested patch for the user to paste into profiles/<name>.json by hand.
That model exposes JSON/profile-normalization concepts the GUI is
explicitly meant to hide (docs/ui/DESIGN_PRINCIPLES.md). There is also no
profile file at all yet at this point in the Phase II workflow. So this
module reuses the CLI's *math* (measure.derive_geometry(), the same
inverse-geometry solver, and the same click-pairing/neighbor-inference
logic from calibrate_ui.py) but stores the result directly in memory here
instead of formatting it as text for the user to copy. A future
profile-writing milestone reads from CalibrateState rather than asking
the user to retype numbers.

WHY THIS DOESN'T PRODUCE A CardLayout
------------------------------------------------------------------
profile.CardLayout needs rows/cols and a contiguous page range, neither
of which Calibrate determines (rows/cols is grid inference, explicitly
deferred; Find-Cards-marked pages may be non-contiguous). CalibrateState
only holds the GridGeometry-shaped subset (left/top/card_width/
card_height/gap_x/gap_y); a future milestone combines that with rows/cols
to build one or more CardLayout entries (README already documents
splitting a non-contiguous page range into multiple layouts with
identical geometry, so no engine change is needed for that later).

COORDINATE SPACE
-----------------
Measurements are stored in PDF points (this project's canonical
persistent coordinate space -- see find_cards_state.py), not pixels.
measure.derive_geometry() expects pixel-space PixelBox values and a
scale; a stored point is converted to "pixels" by multiplying by
render_scale immediately before calling it, and derive_geometry's own
division by that same scale recovers the original point exactly -- a
lossless round trip, not a re-measurement.

ONE SHARED LAYOUT
------------------
All Front Pages (see find_cards_state.FindCardsState.front_pages()) are
assumed to share one card grid: `cards` holds a single CalibrationTarget,
calibrated from whichever one Front Page the user chooses to click on (see
calibrate_workspace.py's page navigation, restricted to Front Pages for
that step). `back` is calibrated on the single page Select Card Pages
assigned as the Shared Back -- Calibrate never searches for it, only
measures it.

Absence of an assigned page is not, by itself, "no Shared Back": Select
Card Pages distinguishes CONFIRMED_NONE (an explicit answer) from
UNRESOLVED (not decided yet) via find_cards_state.SharedBackStatus, and
Calibrate must preserve that distinction rather than treating both as
"nothing to calibrate." See calibrate_guidance_text()/calibrate_status_text()
below and CalibrateWorkspace._update_continue_footer(), which is exactly
where an earlier revision collapsed the two.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from deckforge.measure import CardMeasurement, MeasureError, PixelBox, derive_geometry
from deckforge.profile import GridGeometry

from .app_state import GUIDANCE, STATUS, WorkflowStep
from .find_cards_state import SharedBackStatus

if TYPE_CHECKING:
    from .find_cards_state import FindCardsState

# Points-to-pixels scale pages are rendered at for Calibrate. Independent
# of any profile (none exists yet at this point in the workflow, same
# reasoning as find_cards_workspace.PREVIEW_RENDER_SCALE) -- chosen higher
# than Select Card Pages' since precise corner placement benefits from a sharper
# source image to zoom into.
CALIBRATE_RENDER_SCALE = 4.0

# Below this, in PDF points, two clicks are treated as the same point
# rather than a measured card (see record_click's REJECTED_DEGENERATE).
_MIN_BOX_POINTS = 1.0


def normalize_box(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
    """Orders two arbitrary corner points into (x1,y1,x2,y2) with x2>x1,
    y2>y1, so a click sequence that isn't perfectly upper-left-then-lower-
    right still produces a valid box."""
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def infer_second_cell(
    first_row: int, first_col: int,
    first_box: tuple[float, float, float, float],
    second_box: tuple[float, float, float, float],
    cell_width: float, cell_height: float,
) -> Optional[tuple[int, int]]:
    """Figures out a second measured card's (row, col) from where it sits
    relative to the first card, so the user doesn't have to label the
    common case of clicking a visibly-adjacent (or diagonal) card.

    Each axis is judged independently, normalized by that axis's own cell
    size (dx/cell_width, dy/cell_height) rather than comparing raw
    dx/dy magnitude -- a card is very rarely square, so raw displacement
    is not comparable across axes: a one-row-one-column diagonal move on a
    portrait card has a larger raw vertical displacement than horizontal
    (and the reverse on a landscape card), which previously caused the
    smaller raw axis to be silently discarded even when it represented a
    perfectly real cell offset (see CALIBRATION_GEOMETRY_INVESTIGATION.md).
    Normalizing first means both axes are compared in the same "cells
    moved" unit, so a genuine diagonal click yields nonzero offsets on
    both axes independently.

    Returns None only when neither axis rounds to a nonzero cell offset
    (the two clicks are essentially the same point) -- callers should fall
    back to asking. Unit-agnostic (works the same in points or pixels,
    since only ratios matter), so this needs no adaptation from
    calibrate_ui.py's pixel-space original."""
    if cell_width <= 0 or cell_height <= 0:
        return None
    fx1, fy1, fx2, fy2 = first_box
    sx1, sy1, sx2, sy2 = second_box
    dx = (sx1 + sx2) / 2 - (fx1 + fx2) / 2
    dy = (sy1 + sy2) / 2 - (fy1 + fy2) / 2
    col_offset = round(dx / cell_width)
    row_offset = round(dy / cell_height)
    if col_offset == 0 and row_offset == 0:
        return None
    return (first_row + row_offset, first_col + col_offset)


def predicted_neighbor_box(
    first_box: tuple[float, float, float, float], card_width: float, card_height: float,
    gap_x: float, gap_y: float, direction: str, cells_away: int = 1,
) -> tuple[float, float, float, float]:
    """Guesses where a horizontally- or vertically-offset card would be,
    `cells_away` cells from the first, in the same coordinate space as
    `first_box`, using the just-measured card size and a gap (0.0 before a
    second card fixes it). Only ever used to draw a "click here" hint -- if
    the guess is wrong the user simply clicks somewhere else instead.

    `cells_away` defaults to 1 (the immediately adjacent cell) for
    backward compatibility, but callers choosing where to draw the hint
    should generally prefer a larger value -- see
    suggested_second_card_offset()'s docstring for why."""
    x1, y1, x2, y2 = first_box
    if direction == "right":
        nx1 = x2 + gap_x + (cells_away - 1) * (card_width + gap_x)
        return (nx1, y1, nx1 + card_width, y2)
    if direction == "below":
        ny1 = y2 + gap_y + (cells_away - 1) * (card_height + gap_y)
        return (x1, ny1, x2, ny1 + card_height)
    raise ValueError(f"direction must be 'right' or 'below', got {direction!r}")


class ClickOutcome(Enum):
    """What record_click() just did, so the workspace widget knows how to
    react (redraw, prompt for a cell label, show a warning, ...)."""
    PENDING_SET = "pending_set"
    REJECTED_DEGENERATE = "rejected_degenerate"
    NEEDS_CELL_LABEL = "needs_cell_label"
    MEASUREMENT_ADDED = "measurement_added"
    COMPLETE = "complete"
    IGNORED_ALREADY_COMPLETE = "ignored_already_complete"


@dataclass(frozen=True)
class PointMeasurement:
    """One measured card corner-pair, in PDF points."""
    row: int
    col: int
    x1: float
    y1: float
    x2: float
    y2: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass(frozen=True)
class CalibratedGeometry:
    """The GridGeometry-shaped result of a completed calibration, in PDF
    points. Not a profile.GridGeometry instance itself, to avoid
    importing profile.py's schema machinery for a shape this small --
    a future profile-building milestone is the natural place to convert
    this into one."""
    left: float
    top: float
    card_width: float
    card_height: float
    gap_x: float
    gap_y: float
    gap_x_derived: bool
    gap_y_derived: bool
    warnings: tuple[str, ...] = ()

    def to_grid_geometry(self) -> GridGeometry:
        """Converts to profile.py's GridGeometry shape -- the one place
        this happens, so review_workspace.py and export_state.py (the two
        callers that need to hand a calibrated geometry to engine code
        that knows nothing about Calibrate/Qt) share a single conversion
        instead of each keeping their own copy."""
        return GridGeometry(
            left=self.left, top=self.top,
            card_width=self.card_width, card_height=self.card_height,
            gap_x=self.gap_x, gap_y=self.gap_y,
        )


# How much slack, in points, a near-boundary cell is still allowed to be
# "cut off" by and still count as a real card in suggested_grid() below.
# Biases the suggestion toward one card too many (a one-click fix in
# Review Cards) rather than one too few (silently missing, and much
# easier to overlook) when a page's margins leave the grid right at its
# edge -- see DEVELOPER.md's "Suggested grid size" for the boundary-
# sensitivity analysis this constant exists to cover.
GRID_FIT_TOLERANCE_PT = 2.0


def suggested_grid(
    geometry: CalibratedGeometry,
    page_width_pt: float,
    page_height_pt: float,
    tolerance_pt: float = GRID_FIT_TOLERANCE_PT,
) -> tuple[int, int]:
    """How many (rows, cols) of `geometry`-sized cells fit on a page of the
    given point-dimensions, repeating the calibrated card's pitch (its
    size plus gap) outward from its (left, top) origin.

    This is a STARTING SUGGESTION for Review Cards to confirm or correct,
    never a final answer trusted unreviewed -- nothing here is exported
    until a human has looked at every suggested card as a rendered image.
    That's what keeps this consistent with README's "manual calibration
    only, no automatic edge detection" philosophy: the guess is never
    silent, only ever a starting point.
    """
    cols = _fit_count(page_width_pt, geometry.left, geometry.card_width, geometry.gap_x, tolerance_pt)
    rows = _fit_count(page_height_pt, geometry.top, geometry.card_height, geometry.gap_y, tolerance_pt)
    return (rows, cols)


def _fit_count(page_extent_pt: float, origin_pt: float, card_size_pt: float, gap_pt: float, tolerance_pt: float) -> int:
    if card_size_pt <= 0:
        return 0
    pitch = card_size_pt + gap_pt
    count = math.floor((page_extent_pt - origin_pt + gap_pt + tolerance_pt) / pitch)
    return max(count, 0)


# How far the suggested second-card hint reaches at most, in cells. Caps
# the offset so an unusually small card on a large page doesn't suggest a
# cell dozens of columns away -- still clickable, but a hint that far
# outside the default Fit-to-Window view stops being a usable visual cue.
_MAX_SUGGESTED_OFFSET = 6


def suggested_second_card_offset(
    card_width: float, card_height: float,
    page_width_pt: float, page_height_pt: float,
    first_box: tuple[float, float, float, float],
) -> tuple[int, int]:
    """(col_offset, row_offset) cells away from the first measured card to
    hint the second click at.

    A short baseline -- the immediately adjacent cell, which is all the
    hint used to ever suggest -- divides the gap estimate's denominator by
    1, so ordinary click-precision noise (or genuine tiny print
    non-uniformity) gets fully amplified once extrapolated across the rest
    of the grid. A farther second card divides that same noise by a larger
    denominator instead, sharply reducing it (see
    CALIBRATION_GEOMETRY_INVESTIGATION.md, Effect B). This only changes
    where the *hint* is drawn -- infer_second_cell() already derives the
    click's real (row, col) from wherever the user actually clicks, not
    from this guess, so a wrong estimate here is harmless.

    Uses gap=0 as a rough a-priori estimate of how many cells fit, the
    same assumption predicted_neighbor_box() already makes before a gap is
    known -- exactness doesn't matter for a hint's placement."""
    x1, y1, _, _ = first_box
    cols = _fit_count(page_width_pt, x1, card_width, 0.0, GRID_FIT_TOLERANCE_PT)
    rows = _fit_count(page_height_pt, y1, card_height, 0.0, GRID_FIT_TOLERANCE_PT)
    col_offset = min(max(cols - 1, 1), _MAX_SUGGESTED_OFFSET)
    row_offset = min(max(rows - 1, 1), _MAX_SUGGESTED_OFFSET)
    return (col_offset, row_offset)


@dataclass
class CalibrationTarget:
    """Cards or Shared Back, calibrated independently. Shared Back sets
    allows_second_measurement=False: a shared back is one representative
    card's rectangle, not a grid, so the optional second-card spacing
    measurement Cards supports (deriving gap_x/gap_y) doesn't apply --
    the target completes as soon as its one card is measured."""
    page_num: Optional[int] = None
    pending_point: Optional[tuple[float, float]] = None
    measurements: list[PointMeasurement] = field(default_factory=list)
    geometry: Optional[CalibratedGeometry] = None
    calibrated_page_num: Optional[int] = None
    allows_second_measurement: bool = True
    _pending_second_box: Optional[tuple[float, float, float, float]] = field(default=None, repr=False)

    @property
    def is_complete(self) -> bool:
        return self.geometry is not None

    def reset(self) -> None:
        """Clears in-progress and completed measurements. Deliberately
        leaves page_num untouched -- the CLI's Start Over keeps the
        current view/page too."""
        self.pending_point = None
        self._pending_second_box = None
        self.measurements = []
        self.geometry = None
        self.calibrated_page_num = None


@dataclass
class CalibrateState:
    render_scale: float = CALIBRATE_RENDER_SCALE
    cards: CalibrationTarget = field(default_factory=CalibrationTarget)
    back: CalibrationTarget = field(default_factory=lambda: CalibrationTarget(allows_second_measurement=False))

    def target_for(self, step: WorkflowStep) -> CalibrationTarget:
        return self.back if step is WorkflowStep.CALIBRATE_BACK else self.cards

    def reset_all(self) -> None:
        """A new/replacement PDF was loaded -- page numbers from a
        different PDF have no relationship to these, same reasoning
        MainWindow already applies to FindCardsState."""
        self.cards.reset()
        self.back.reset()

    def cards_is_stale(self, find_cards_state: "FindCardsState") -> bool:
        """True if Cards (Fronts) was calibrated from a page that is no
        longer a Front Page in Select Card Pages (the user went back and
        changed its role) -- the geometry no longer corresponds to a
        confirmed front page. Marking additional front pages does not
        make an existing calibration stale."""
        page = self.cards.calibrated_page_num
        if page is None:
            return False
        return page not in find_cards_state.front_pages()

    def back_is_stale(self, find_cards_state: "FindCardsState") -> bool:
        """True if Shared Back was calibrated from a page that is no
        longer the Deck's assigned Shared Back page -- either the user
        reassigned it to a different page, or cleared it entirely (back to
        unresolved, or confirmed no shared back)."""
        page = self.back.calibrated_page_num
        if page is None:
            return False
        return page != find_cards_state.back_page()

    # -- click handling ---------------------------------------------------

    def record_click(self, step: WorkflowStep, x_pt: float, y_pt: float) -> ClickOutcome:
        target = self.target_for(step)
        if target.is_complete or len(target.measurements) >= 2:
            return ClickOutcome.IGNORED_ALREADY_COMPLETE

        if target.pending_point is None:
            target.pending_point = (x_pt, y_pt)
            return ClickOutcome.PENDING_SET

        box = normalize_box(target.pending_point[0], target.pending_point[1], x_pt, y_pt)
        target.pending_point = None
        x1, y1, x2, y2 = box
        if (x2 - x1) < _MIN_BOX_POINTS or (y2 - y1) < _MIN_BOX_POINTS:
            return ClickOutcome.REJECTED_DEGENERATE

        if not target.measurements:
            target.measurements.append(PointMeasurement(0, 0, x1, y1, x2, y2))
            if not target.allows_second_measurement:
                self._finalize(target)
                return ClickOutcome.COMPLETE
            return ClickOutcome.MEASUREMENT_ADDED

        first = target.measurements[0]
        cell_width = first.x2 - first.x1
        cell_height = first.y2 - first.y1
        cell = infer_second_cell(first.row, first.col, first.as_tuple(), box, cell_width, cell_height)
        if cell is None:
            target._pending_second_box = box
            return ClickOutcome.NEEDS_CELL_LABEL

        row, col = cell
        target.measurements.append(PointMeasurement(row, col, x1, y1, x2, y2))
        self._finalize(target)
        return ClickOutcome.COMPLETE

    def cancel_ambiguous_second_card(self, step: WorkflowStep) -> None:
        """Abandons a NEEDS_CELL_LABEL click (e.g. the user dismissed the
        cell-label prompt) without touching the first, already-completed
        measurement -- unlike start_over(), which clears everything."""
        self.target_for(step)._pending_second_box = None

    def add_measurement_with_cell(self, step: WorkflowStep, row: int, col: int) -> ClickOutcome:
        """Resolves a NEEDS_CELL_LABEL outcome once the caller has an
        explicit row/col (e.g. from a user prompt)."""
        target = self.target_for(step)
        if target._pending_second_box is None:
            return ClickOutcome.IGNORED_ALREADY_COMPLETE
        x1, y1, x2, y2 = target._pending_second_box
        target._pending_second_box = None
        target.measurements.append(PointMeasurement(row, col, x1, y1, x2, y2))
        self._finalize(target)
        return ClickOutcome.COMPLETE

    def finish_with_one_card(self, step: WorkflowStep) -> ClickOutcome:
        """User declined to measure a second card -- derives geometry
        from the single measurement (gap assumed 0.0/edge-to-edge)."""
        target = self.target_for(step)
        if len(target.measurements) != 1:
            return ClickOutcome.IGNORED_ALREADY_COMPLETE
        target._pending_second_box = None
        self._finalize(target)
        return ClickOutcome.COMPLETE

    def start_over(self, step: WorkflowStep) -> None:
        self.target_for(step).reset()

    def _finalize(self, target: CalibrationTarget) -> None:
        pixel_measurements: Sequence[CardMeasurement] = [
            CardMeasurement(
                row=m.row, col=m.col,
                box=PixelBox(
                    m.x1 * self.render_scale, m.y1 * self.render_scale,
                    m.x2 * self.render_scale, m.y2 * self.render_scale,
                ),
            )
            for m in target.measurements
        ]
        try:
            result = derive_geometry(pixel_measurements, scale=self.render_scale)
        except MeasureError:
            # Only reachable if measurements somehow ended up empty --
            # record_click/finish_with_one_card never call _finalize
            # without at least one measurement present.
            return
        target.geometry = CalibratedGeometry(
            left=result.left, top=result.top,
            card_width=result.card_width, card_height=result.card_height,
            gap_x=result.gap_x if result.gap_x is not None else 0.0,
            gap_y=result.gap_y if result.gap_y is not None else 0.0,
            gap_x_derived=result.gap_x is not None,
            gap_y_derived=result.gap_y is not None,
            warnings=result.warnings,
        )
        target.calibrated_page_num = target.page_num


# -- guidance/status text, state-aware (see app_state.py's static GUIDANCE/
# STATUS for the base case reused below) --------------------------------


def _grid_clause(target: CalibrationTarget, page_size: Optional[tuple[float, float]]) -> str:
    """' Looks like a RxC grid per page.' once a page size is available to
    suggest one from -- purely descriptive, never a question or a gate
    (Review Cards, not Calibrate, is where the user actually confirms or
    corrects the count). Empty string if there's nothing sensible to say
    (no page size yet, or a degenerate 0-card suggestion, e.g. from a
    mis-measured card larger than the page)."""
    if page_size is None or target.geometry is None:
        return ""
    page_width_pt, page_height_pt = page_size
    rows, cols = suggested_grid(target.geometry, page_width_pt, page_height_pt)
    if rows <= 0 or cols <= 0:
        return ""
    return f" Looks like a {rows}×{cols} grid per page."


def ungauged_axis_warning(target: CalibrationTarget, page_size: Optional[tuple[float, float]]) -> str:
    """Explains, in Calibrate's own completion text, when a spacing axis
    was never actually measured and is silently assumed edge-to-edge (see
    CALIBRATION_GEOMETRY_INVESTIGATION.md, Effect A -- `gap_x_derived`/
    `gap_y_derived` already existed and were already computed but nothing
    read them). Only fires when the axis actually matters: a deck with a
    single row or single column never uses that axis's spacing at all
    (its row/col index is always 0, so the fallback gap is never
    multiplied by anything), so warning about it there would be noise, not
    help -- reuses the same suggested_grid() estimate _grid_clause() above
    already computes for the grid-size note."""
    if page_size is None or target.geometry is None:
        return ""
    geometry = target.geometry
    if geometry.gap_x_derived and geometry.gap_y_derived:
        return ""
    page_width_pt, page_height_pt = page_size
    rows, cols = suggested_grid(geometry, page_width_pt, page_height_pt)
    missing_axes = []
    if not geometry.gap_x_derived and cols > 1:
        missing_axes.append("columns")
    if not geometry.gap_y_derived and rows > 1:
        missing_axes.append("rows")
    if not missing_axes:
        return ""
    axes_text = " and ".join(missing_axes)
    return (
        f" Spacing between {axes_text} wasn't measured, so DeckForge "
        "assumed cards sit edge-to-edge. If cards look clipped in Review "
        "Cards, click Start Over and measure a second card farther away "
        "instead of finishing with one."
    )


def calibrate_guidance_text(
    step: WorkflowStep,
    target: CalibrationTarget,
    front_page_count: int = 0,
    shared_back_status: SharedBackStatus = SharedBackStatus.ASSIGNED,
    page_size: Optional[tuple[float, float]] = None,
) -> tuple[str, str]:
    if step is WorkflowStep.CALIBRATE_BACK and shared_back_status is not SharedBackStatus.ASSIGNED:
        if shared_back_status is SharedBackStatus.CONFIRMED_NONE:
            return (
                "This deck has no Shared Back.",
                "Select Card Pages recorded that this deck has no Shared Back "
                "— there's nothing to calibrate here. Continue to Review Cards "
                "whenever you're ready.",
            )
        # UNRESOLVED -- Calibrate must not guess or default to "none"; the
        # decision belongs to Select Card Pages.
        return (
            "Shared Back hasn't been decided yet.",
            "Go back to Select Card Pages and either choose a Shared Back "
            "page or confirm this deck has none — Calibrate can't continue "
            "until that's decided.",
        )
    subject = "back design" if step is WorkflowStep.CALIBRATE_BACK else "card"
    if target.is_complete:
        if step is WorkflowStep.CALIBRATE_CARDS:
            return (
                "Fronts calibration complete",
                f"Calibrated using page {target.calibrated_page_num}. This "
                f"geometry applies to all {front_page_count} selected "
                "front pages — click Start Over if you'd like to "
                f"remeasure it.{_grid_clause(target, page_size)}"
                f"{ungauged_axis_warning(target, page_size)}",
            )
        return (
            "Shared Back calibration complete",
            f"Calibrated using page {target.calibrated_page_num}. This back "
            f"design will be applied as the shared back for all "
            f"{front_page_count} selected front pages — click Start "
            "Over if you'd like to remeasure it.",
        )
    if target.pending_point is not None:
        return (
            "Click the diagonally opposite corner.",
            f"Click the opposite corner of the same {subject} — the corner "
            "diagonally across from your first click (e.g. the lower-right "
            "corner if you started at the upper-left), using the same "
            "cutting guide or edge you used for the first corner.",
        )
    if target.measurements:
        return (
            "Capture spacing? (optional)",
            f"To capture spacing, click a neighboring {subject} — choosing "
            "one farther away, not just the next one over, gives more "
            "accurate results. Otherwise, click Finish with one card.",
        )
    return GUIDANCE[step]


def calibrate_status_text(
    step: WorkflowStep,
    target: CalibrationTarget,
    front_page_count: int = 0,
    shared_back_status: SharedBackStatus = SharedBackStatus.ASSIGNED,
    page_size: Optional[tuple[float, float]] = None,
) -> str:
    if step is WorkflowStep.CALIBRATE_BACK and shared_back_status is not SharedBackStatus.ASSIGNED:
        if shared_back_status is SharedBackStatus.CONFIRMED_NONE:
            return "This deck has no Shared Back — nothing to calibrate. Continue to Review Cards."
        return "Shared Back hasn't been decided yet — go back to Select Card Pages to resolve it."
    subject = "back design" if step is WorkflowStep.CALIBRATE_BACK else "card"
    if target.is_complete:
        if step is WorkflowStep.CALIBRATE_CARDS:
            return (
                f"Calibrated from page {target.calibrated_page_num} — "
                f"applies to all {front_page_count} front pages. "
                f"Click Start Over to remeasure.{_grid_clause(target, page_size)}"
                f"{ungauged_axis_warning(target, page_size)}"
            )
        return (
            f"Calibrated from page {target.calibrated_page_num} — applied "
            f"as the shared back for all {front_page_count} front "
            "pages. Click Start Over to remeasure."
        )
    if target.pending_point is not None:
        return (
            f"Click the opposite corner of the same {subject} — diagonally "
            "across, using the same cutting guide or edge as before."
        )
    if target.measurements:
        return "1 card measured — click a farther neighbor's first corner for more accurate spacing, or click Finish with one card."
    return STATUS[step]
