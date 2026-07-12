"""Review Cards state -- the last checkpoint before Export.

Deliberately free of any PySide6/PDF import, same rationale as every other
*_state.py module: this is the controller layer the GUI reads from, unit
tested without opening a window or a PDF. `build_review_cards()` takes a
page-size lookup as an injected function rather than opening a
PDFRenderer itself, for the same reason.

WHY THIS DOESN'T BUILD A CardLayout
------------------------------------
Unlike a future Export milestone (which will need profile.CardLayout --
rows/cols tied to a *contiguous* page range, per profile.py), Review Cards
only ever needs to crop and display individual (page, row, col) cells. It
never groups Select Card Pages' front_pages() into contiguous runs or
constructs a CardLayout, because nothing here requires one -- that
grouping is deferred to whichever future milestone actually writes a
DeckProfile.

THE SUGGESTION IS NEVER THE ANSWER
------------------------------------
build_review_cards() calls calibrate_state.suggested_grid() once per Front
Page to guess how many cards are on it. That guess is frequently wrong by
design on a page that isn't a full grid (e.g. a deck whose card count
isn't a multiple of rows*cols will have a partly-filled last page) --
ReviewCardsState.included exists precisely so a human, not the formula,
has the final say on which suggested cells are real cards. Nothing here
is ever treated as final without a pass through this state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from deckforge.geometry import iter_grid_positions

from .calibrate_state import CalibratedGeometry, CalibrationTarget, suggested_grid
from .find_cards_state import SharedBackStatus


@dataclass(frozen=True)
class ReviewCard:
    """One suggested card: a specific (row, col) cell on a specific Front
    Page. Identity only, not image data -- ReviewCardsState tracks
    inclusion keyed by this; the workspace crops/renders the actual image
    on demand rather than this module holding pixels."""
    page_num: int
    row: int
    col: int


def build_review_cards(
    front_pages: Sequence[int],
    geometry: CalibratedGeometry,
    page_size_fn: Callable[[int], tuple[float, float]],
) -> list[ReviewCard]:
    """Every suggested card across all Front Pages, in reading order
    (page, then row, then column, matching iter_grid_positions() and the
    numbering a future Export would use)."""
    cards: list[ReviewCard] = []
    for page_num in front_pages:
        page_width_pt, page_height_pt = page_size_fn(page_num)
        rows, cols = suggested_grid(geometry, page_width_pt, page_height_pt)
        for row, col in iter_grid_positions(rows, cols):
            cards.append(ReviewCard(page_num, row, col))
    return cards


@dataclass
class ReviewCardsState:
    """Which suggested cards the user has confirmed vs. excluded. Keyed by
    ReviewCard rather than a plain list/count so a toggle on one page's
    card never has to know about any other page's cards."""
    included: dict[ReviewCard, bool] = field(default_factory=dict)

    def clear(self) -> None:
        """A new/replacement PDF was loaded -- page numbers from a
        different PDF have no relationship to these, same reasoning
        FindCardsState.clear_all()/CalibrateState.reset_all() already
        apply for their own state."""
        self.included = {}

    def sync(self, cards: Sequence[ReviewCard]) -> None:
        """Reconciles `included` with the current suggested-card list:
        keeps the existing yes/no for any card still present (so paging
        around, or a change elsewhere on the deck, doesn't reset every
        other card's toggle), defaults newly-appeared cards to included,
        and drops cards no longer suggested (a Front Page was removed, or
        Calibrate was redone). Safe to call every time Review Cards is
        shown -- a no-op if the suggested list hasn't changed."""
        self.included = {card: self.included.get(card, True) for card in cards}

    def toggle(self, card: ReviewCard) -> None:
        if card in self.included:
            self.included[card] = not self.included[card]

    def is_included(self, card: ReviewCard) -> bool:
        return self.included.get(card, True)

    def all_cards(self) -> list[ReviewCard]:
        return list(self.included.keys())

    def included_cards(self) -> list[ReviewCard]:
        return [card for card, included in self.included.items() if included]

    def included_count(self) -> int:
        return sum(1 for included in self.included.values() if included)

    def total_count(self) -> int:
        return len(self.included)


def review_ready(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
) -> bool:
    """Whether Review Cards has enough from Calibrate to show anything.
    False means: Fronts hasn't been calibrated yet; the Shared Back
    question is still unresolved; or a Shared Back page IS assigned but
    hasn't actually been calibrated yet. That last case is reachable even
    though Calibrate's own Continue is gated on it, because
    AppState.is_reached lets the sidebar route straight to Review Cards --
    and MainWindow re-checks back_is_stale() on Review Cards' own entry
    (the Shared Back page could have been reassigned to a different page
    since it was last calibrated, resetting it back to incomplete while
    shared_back_status stays ASSIGNED)."""
    if not cards_target.is_complete:
        return False
    if shared_back_status is SharedBackStatus.UNRESOLVED:
        return False
    if shared_back_status is SharedBackStatus.ASSIGNED and not back_target.is_complete:
        return False
    return True


def review_guidance_text(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
) -> tuple[str, str]:
    if not cards_target.is_complete:
        return (
            "Fronts hasn't been calibrated yet.",
            "Go back to Calibrate and measure a front card before reviewing cards.",
        )
    if shared_back_status is SharedBackStatus.UNRESOLVED:
        return (
            "Shared Back hasn't been decided yet.",
            "Go back to Select Card Pages and either choose a Shared Back "
            "page or confirm this deck has none.",
        )
    if shared_back_status is SharedBackStatus.ASSIGNED and not back_target.is_complete:
        return (
            "Shared Back hasn't been calibrated yet.",
            "Go back to Calibrate and measure the shared back design before reviewing cards.",
        )
    total = review_state.total_count()
    if total == 0:
        return (
            "DeckForge couldn't fit any cards.",
            "The calibrated card doesn't fit on the page. Go back to "
            "Calibrate and check your measurement.",
        )
    noun = "card" if total == 1 else "cards"
    included = review_state.included_count()
    if included == total:
        return (
            "Check your cards.",
            f"{total} {noun} found. Deselect any that aren't real cards "
            "(e.g. blank space on a partly-filled page), then continue to Export.",
        )
    return (
        "Check your cards.",
        f"{included} of {total} {noun} included — continue to Export whenever you're ready.",
    )


def review_status_text(
    cards_target: CalibrationTarget,
    back_target: CalibrationTarget,
    shared_back_status: SharedBackStatus,
    review_state: ReviewCardsState,
) -> str:
    if not cards_target.is_complete:
        return "Fronts hasn't been calibrated yet — go back to Calibrate."
    if shared_back_status is SharedBackStatus.UNRESOLVED:
        return "Shared Back hasn't been decided yet — go back to Select Card Pages."
    if shared_back_status is SharedBackStatus.ASSIGNED and not back_target.is_complete:
        return "Shared Back hasn't been calibrated yet — go back to Calibrate."
    total = review_state.total_count()
    if total == 0:
        return "No cards fit the calibrated page — go back to Calibrate and check your measurement."
    included = review_state.included_count()
    noun = "card" if total == 1 else "cards"
    return f"{included} of {total} {noun} included."
