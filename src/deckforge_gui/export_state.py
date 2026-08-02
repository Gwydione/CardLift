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
from .find_cards_state import BackMode, FindCardsState, SharedBackStatus
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
    list of front cells, the geometry to crop them with, and whichever
    back shape applies, if any. Nothing here is re-derived at export
    time -- see deckforge.cell_export.export_cells(), which takes this
    shape apart and does no suggestion/inference of its own.

    `back` (Shared Back: one page + geometry) and `paired_back` (Paired
    Backs: one shared geometry -- like front_geometry, one representative
    calibrated geometry reused for every back page -- plus a back page
    number per entry in front_cells, parallel-indexed to it) are mutually
    exclusive, matching cell_export.export_cells()'s own `back`/
    `paired_back` parameters exactly -- this dataclass is deliberately
    shaped to be unpacked straight into that call, one mode-specific
    field alongside the ordinary front_cells/front_geometry every mode
    already shares, rather than a separate plan type per mode (ExportPlan
    is read uniformly by ExportWorkspace regardless of back mode; a type
    split would force an isinstance() branch there instead)."""
    front_cells: tuple[ReviewCard, ...]
    front_geometry: GridGeometry
    back: Optional[tuple[int, GridGeometry]] = None
    paired_back: Optional[tuple[GridGeometry, tuple[int, ...]]] = None

    def __post_init__(self) -> None:
        assert self.back is None or self.paired_back is None, "back and paired_back are mutually exclusive"

    @property
    def card_count(self) -> int:
        return len(self.front_cells)

    @property
    def has_back(self) -> bool:
        return self.back is not None

    @property
    def has_paired_back(self) -> bool:
        return self.paired_back is not None


def predicted_output_filenames(plan: ExportPlan) -> list[str]:
    """The exact filenames this plan's Export run will write -- delegates
    to deckforge.cell_export.output_filenames(), the single source of
    truth for the naming convention, rather than re-deriving it. Used by
    existing_output_files() below for the pre-flight overwrite check."""
    return output_filenames(plan.card_count, plan.has_back, paired=plan.has_paired_back)


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
    back_mode: BackMode = BackMode.SHARED,
    paired_back_target: Optional[CalibrationTarget] = None,
    find_cards_state: Optional[FindCardsState] = None,
) -> ExportPlan:
    """Assembles the plan Export will run, straight from Review Cards'
    approved set. Callers must check export_ready() (and, in
    ExportWorkspace, review_snapshot_is_current()) first -- this performs
    no readiness validation of its own, for PAIRED same as for the
    existing Front Only/Shared Back path below.

    `back_mode`/`paired_back_target`/`find_cards_state` default to
    values that reproduce today's Front Only/Shared Back behavior
    exactly when omitted -- a caller not yet passing them (as of Phase
    5B, ExportWorkspace itself) gets byte-identical plans to before.
    For back_mode PAIRED, `paired_back_target` and `find_cards_state`
    must both be given: the per-cell back page numbers are resolved via
    find_cards_state.paired_back_page_for(), reusing each front cell's
    own (row, col) on paired_back_target's geometry -- the same
    resolution deckforge_gui.review_workspace's Card Inspection already
    performs for a single card, just for every included cell at once.
    export_ready() is expected to have already confirmed the front/back
    page counts are balanced (so every included card resolves a real
    back page); the assertion below is a defensive check on that
    invariant, not a substitute for it."""
    assert cards_target.geometry is not None
    front_geometry = cards_target.geometry.to_grid_geometry()
    front_cells = tuple(review_state.included_cards())

    if back_mode is BackMode.PAIRED:
        assert paired_back_target is not None and paired_back_target.geometry is not None
        assert find_cards_state is not None
        back_geometry = paired_back_target.geometry.to_grid_geometry()
        back_pages = tuple(find_cards_state.paired_back_page_for(card.page_num) for card in front_cells)
        assert all(page is not None for page in back_pages), (
            "every included card must resolve to a paired back page -- export_ready() "
            "should have already required paired_page_counts_balanced()"
        )
        return ExportPlan(
            front_cells=front_cells,
            front_geometry=front_geometry,
            paired_back=(back_geometry, back_pages),
        )

    back = None
    if shared_back_status is SharedBackStatus.ASSIGNED:
        assert back_target.geometry is not None and back_target.calibrated_page_num is not None
        back = (back_target.calibrated_page_num, back_target.geometry.to_grid_geometry())
    return ExportPlan(
        front_cells=front_cells,
        front_geometry=front_geometry,
        back=back,
    )


def export_ready(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
    back_mode: BackMode = BackMode.SHARED,
    paired_back_target: Optional[CalibrationTarget] = None,
    paired_topology_ok: bool = True,
    find_cards_state: Optional[FindCardsState] = None,
) -> bool:
    """The ordinary Export gate: everything review_ready() requires, plus
    at least one included card, plus (PAIRED only) balanced front/back
    page counts. Does NOT detect a stale review snapshot (see this
    module's docstring) -- ExportWorkspace layers
    review_snapshot_is_current() on top of this for its own, more
    precise, gate.

    The balanced-counts requirement is deliberately stricter than
    review_ready()'s own PAIRED branch, which does not check it (Review
    Cards is a non-destructive, human-inspectable preview that can afford
    to show "no paired back could be found" for one card and let the
    user notice and fix it). Export writes real files to disk -- an
    unresolved pairing there means silently shipping a front image with
    no matching back, a mistake with no equivalent safety net once
    written, so Export refuses to run at all rather than risk it.

    `back_mode`/`paired_back_target`/`paired_topology_ok`/
    `find_cards_state` all default to values that reproduce today's
    Front Only/Shared Back gating exactly when omitted."""
    if not review_ready(cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok):
        return False
    if review_state.included_count() == 0:
        return False
    if back_mode is BackMode.PAIRED:
        if find_cards_state is None or not find_cards_state.paired_page_counts_balanced():
            return False
    return True


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


def _paired_counts_unbalanced(back_mode: BackMode, find_cards_state: Optional[FindCardsState]) -> bool:
    """Shared by export_guidance_text()/export_status_text(): True only
    when back_mode is PAIRED and the front/back page counts don't match
    (or find_cards_state wasn't given to check) -- the same condition
    export_ready() hard-gates on, so its explanatory text stays in sync
    with what actually blocks the Export action."""
    if back_mode is not BackMode.PAIRED:
        return False
    return find_cards_state is None or not find_cards_state.paired_page_counts_balanced()


def export_guidance_text(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
    back_mode: BackMode = BackMode.SHARED,
    paired_back_target: Optional[CalibrationTarget] = None,
    paired_topology_ok: bool = True,
    find_cards_state: Optional[FindCardsState] = None,
) -> tuple[str, str]:
    if not review_ready(cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok):
        return review_guidance_text(
            cards_target, back_target, shared_back_status, review_state, back_mode, paired_back_target, paired_topology_ok,
        )
    if _paired_counts_unbalanced(back_mode, find_cards_state):
        return (
            "Front and Back page counts don't match.",
            "Paired Backs needs one Back page for every Front page. Go back to "
            "Select Card Pages and even up the counts before exporting.",
        )
    total = review_state.included_count()
    if total == 0:
        return (
            "No cards are included.",
            "Go back to Review Cards and include at least one card before exporting.",
        )
    noun = "card" if total == 1 else "cards"
    if back_mode is BackMode.PAIRED:
        back_clause = " with a paired back for each"
    elif shared_back_status is SharedBackStatus.ASSIGNED:
        back_clause = " and a shared back"
    else:
        back_clause = ""
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
    back_mode: BackMode = BackMode.SHARED,
    paired_back_target: Optional[CalibrationTarget] = None,
    paired_topology_ok: bool = True,
    find_cards_state: Optional[FindCardsState] = None,
) -> str:
    if not review_ready(cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok):
        return review_status_text(
            cards_target, back_target, shared_back_status, review_state, back_mode, paired_back_target, paired_topology_ok,
        )
    if _paired_counts_unbalanced(back_mode, find_cards_state):
        return "Front and Back page counts don't match — go back to Select Card Pages."
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
