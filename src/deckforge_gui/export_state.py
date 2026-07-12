"""Export state -- builds the exact, ordered, human-approved cell list
Export writes to disk, and gates whether Export is ready to run.

Deliberately free of any PySide6/PDF import, same family as
find_cards_state.py/calibrate_state.py/review_state.py: unit tested
without opening a window or a PDF.

WHY THIS DOESN'T BUILD A DeckProfile/CardLayout
--------------------------------------------------
See deckforge.cell_export's module docstring for the full reasoning: a
CardLayout means "a complete, regular rows x cols grid" and has no way to
omit a cell Review Cards excluded. build_export_plan() instead carries
review_state.included_cards() through verbatim -- Review Cards' approved
set is authoritative here, and nothing in this module re-derives or
re-suggests it.

REVIEW CARDS MUST STAY THE SOURCE OF TRUTH
---------------------------------------------
AppState.is_reached lets the sidebar route straight to Export once it has
been reached once (the same mechanism that already lets it route straight
to Review Cards -- see calibrate_state.py's cards_is_stale()/
back_is_stale() docstrings), so a user can revisit and change Calibrate,
then jump directly back to Export without passing back through Review
Cards again.

export_ready() below (used for the ordinary "is Fronts/Shared Back
calibrated, is at least one card included" gate, and for the guidance
panel/status bar) deliberately does NOT check whether review_state's
synced cell identities still match what Review Cards would compute right
now from the current calibrated geometry -- doing so needs a page-size
lookup, which needs an open PDFRenderer neither the guidance panel nor
the status bar has access to (see export_workspace.py and DEVELOPER.md's
"Export milestone" section for why this is an accepted, documented
narrowing rather than an oversight).

review_snapshot_is_current() is the separate, more precise check that
DOES catch that case (a page's suggested grid changed, or a front page
was added/removed, without invalidating the calibrated page itself) --
ExportWorkspace is the only caller, since it already owns a PDFRenderer
for the export operation itself and can perform this check with no new
infrastructure. When the snapshot is stale, ExportWorkspace blocks with
stale_review_guidance_text()/stale_review_status_text() rather than
running export_cells() against cards the human has not actually
confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from deckforge.cell_export import output_filenames
from deckforge.profile import GridGeometry

from .calibrate_state import CalibrationTarget
from .find_cards_state import SharedBackStatus
from .review_state import (
    ReviewCard,
    ReviewCardsState,
    build_review_cards,
    review_guidance_text,
    review_ready,
    review_status_text,
)

# Output resolution for the actual exported PNGs -- independent of
# CalibrateState.CALIBRATE_RENDER_SCALE (precision clicking) and
# review_workspace.REVIEW_RENDER_SCALE (cheap thumbnails), since this is
# the final deliverable image quality. Matches the CLI's own typical
# profile render_scale (README: "e.g. 4 ~ 288 DPI") -- these are the same
# kind of output.
EXPORT_RENDER_SCALE = 4.0


@dataclass(frozen=True)
class ExportPlan:
    """Exactly what Export will write: an ordered, already human-approved
    list of front cells, the geometry to crop them with, and the shared
    back (page + geometry), if any. Nothing here is re-derived at export
    time -- see deckforge.cell_export.export_cells(), which takes this
    shape apart and does no suggestion/inference of its own."""
    front_cells: tuple[ReviewCard, ...]
    front_geometry: GridGeometry
    back: Optional[tuple[int, GridGeometry]]

    @property
    def card_count(self) -> int:
        return len(self.front_cells)

    @property
    def has_back(self) -> bool:
        return self.back is not None


def predicted_output_filenames(plan: ExportPlan) -> list[str]:
    """The exact filenames this plan's Export run will write -- delegates
    to deckforge.cell_export.output_filenames(), the single source of
    truth for the naming convention, rather than re-deriving it. Used by
    existing_output_files() below for the pre-flight overwrite check."""
    return output_filenames(plan.card_count, plan.has_back)


def existing_output_files(destination: Path, plan: ExportPlan) -> list[str]:
    """Which of this plan's predicted output filenames already exist in
    destination -- a non-empty result means running Export now would
    silently overwrite them. Pure filesystem read, no writes; safe to
    call as many times as the destination folder changes."""
    return [name for name in predicted_output_filenames(plan) if (destination / name).exists()]


def build_export_plan(
    review_state: ReviewCardsState,
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
) -> ExportPlan:
    """Assembles the plan Export will run, straight from Review Cards'
    approved set. Callers must check export_ready() (and, in
    ExportWorkspace, review_snapshot_is_current()) first -- this performs
    no readiness validation of its own."""
    assert cards_target.geometry is not None
    front_geometry = cards_target.geometry.to_grid_geometry()
    back = None
    if shared_back_status is SharedBackStatus.ASSIGNED:
        assert back_target.geometry is not None and back_target.calibrated_page_num is not None
        back = (back_target.calibrated_page_num, back_target.geometry.to_grid_geometry())
    return ExportPlan(
        front_cells=tuple(review_state.included_cards()),
        front_geometry=front_geometry,
        back=back,
    )


def export_ready(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
) -> bool:
    """The ordinary Export gate: everything review_ready() requires, plus
    at least one included card. Does NOT detect a stale review snapshot
    (see this module's docstring) -- ExportWorkspace layers
    review_snapshot_is_current() on top of this for its own, more
    precise, gate."""
    if not review_ready(cards_target, back_target, shared_back_status):
        return False
    return review_state.included_count() > 0


def review_snapshot_is_current(
    review_state: ReviewCardsState,
    front_pages: Sequence[int],
    cards_target: CalibrationTarget,
    page_size_fn: Callable[[int], tuple[float, float]],
) -> bool:
    """Whether review_state's currently-synced cell identities still match
    what Review Cards would compute right now from the current Calibrate
    geometry and Select Card Pages' current front pages. False means
    something changed (Calibrate was redone on the same page, or a front
    page was added/removed) since review_state was last synced inside
    Review Cards' own on_shown() -- Export must not run against that
    stale approved set. Vacuously True if cards_target isn't complete;
    export_ready() already blocks on that separately."""
    if cards_target.geometry is None:
        return True
    current = build_review_cards(front_pages, cards_target.geometry, page_size_fn)
    return set(review_state.all_cards()) == set(current)


def export_guidance_text(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
) -> tuple[str, str]:
    if not review_ready(cards_target, back_target, shared_back_status):
        return review_guidance_text(cards_target, back_target, shared_back_status, review_state)
    total = review_state.included_count()
    if total == 0:
        return (
            "No cards are included.",
            "Go back to Review Cards and include at least one card before exporting.",
        )
    noun = "card" if total == 1 else "cards"
    back_clause = " and a shared back" if shared_back_status is SharedBackStatus.ASSIGNED else ""
    return (
        "Ready to export.",
        f"{total} {noun}{back_clause} ready to save as image files. Choose a "
        "destination folder, then export whenever you're ready.",
    )


def export_status_text(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
) -> str:
    if not review_ready(cards_target, back_target, shared_back_status):
        return review_status_text(cards_target, back_target, shared_back_status, review_state)
    total = review_state.included_count()
    if total == 0:
        return "No cards included — go back to Review Cards."
    noun = "card" if total == 1 else "cards"
    return f"Ready to export {total} {noun}."


def stale_review_guidance_text() -> tuple[str, str]:
    """Shown only by ExportWorkspace, when review_snapshot_is_current()
    is False -- see this module's docstring for why this check (and this
    message) doesn't also appear in the guidance panel or status bar."""
    return (
        "Your calibration changed.",
        "Something changed since you last reviewed your cards — go back to "
        "Review Cards to confirm them again before exporting.",
    )


def stale_review_status_text() -> str:
    return "Calibration changed since your last review — go back to Review Cards."
