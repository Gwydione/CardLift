"""Regression coverage for Card Inspection (docs/ui/UI_DECISIONS.md's
"Card Inspection" section) -- the milestone that replaced "Zoom/Pan" with
a workspace overlay letting a user look closer at one suggested card, with
next/previous navigation and include/exclude, without leaving Review
Cards. Kept deliberately narrow, mirroring test_export_workspace.py's
first-widget-test scope: covers exactly the properties the design
required -- the grid is never rebuilt by opening/closing the inspector
(the actual mechanism that preserves scroll position), high-fidelity
renders are on-demand and cached per page rather than pre-rendered for
the whole deck, next/previous clamps at the ends, and include/exclude
stays in sync with the grid -- not a general widget-coverage sweep."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from deckforge.pdf_renderer import PDFRenderError
from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrateState
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.review_state import ReviewCard, ReviewCardsState
from deckforge_gui.review_workspace import INSPECT_RENDER_SCALE, REVIEW_RENDER_SCALE, ReviewWorkspace, _CardTile

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "CardLift_Demo_Deck.pdf"

# Real, --preview-verified geometry from profiles/demo_deck.json (same
# constant test_export_workspace.py uses against this sample PDF) -- a 2x3
# grid on page 2, giving several same-page neighbors to navigate between.
FRONT_GEOMETRY = CalibratedGeometry(
    left=27.0, top=139.5, card_width=180.0, card_height=252.0,
    gap_x=9.0, gap_y=9.0, gap_x_derived=False, gap_y_derived=False,
)
FRONT_PAGE = 2


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def workspace(qapp: QApplication) -> ReviewWorkspace:
    return ReviewWorkspace(CalibrateState(), FindCardsState(), ReviewCardsState())


def _make_ready(workspace: ReviewWorkspace, front_page: int = FRONT_PAGE) -> None:
    workspace.find_cards_state._roles.clear()
    workspace.find_cards_state.set_role(front_page, PageRole.FRONT)
    workspace.find_cards_state.confirm_no_shared_back()
    workspace.calibrate_state.cards.reset()
    workspace.calibrate_state.back.reset()
    workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
    workspace.calibrate_state.cards.calibrated_page_num = front_page
    workspace.set_pdf(SAMPLE_PDF, 12)
    workspace.on_shown()  # runs _rebuild(), populating _card_list/_tiles


class _RenderCallSpy:
    """Wraps a bound render_page() method, recording every (page, scale)
    call -- lets tests assert the inspector's high-fidelity render is
    on-demand (never called before the inspector opens) and cached
    (never repeated for a page already rendered at that scale)."""

    def __init__(self, real_render_page) -> None:
        self._real = real_render_page
        self.calls: list[tuple[int, float]] = []

    def __call__(self, page_number: int, scale: float):
        self.calls.append((page_number, scale))
        return self._real(page_number, scale)


class TestLookCloserAffordance:
    """_CardTile now routes a click to one of two different signals
    depending on where on the tile it lands -- the existing
    toggle-inclusion click must be completely unaffected."""

    def _make_tile(self, included: bool = True) -> _CardTile:
        pixmap = QPixmap(150, 210)
        pixmap.fill(Qt.GlobalColor.white)
        return _CardTile(ReviewCard(2, 0, 0), pixmap, included=included)

    def test_clicking_the_look_closer_corner_requests_inspection_not_toggle(self, qapp: QApplication) -> None:
        tile = self._make_tile()
        toggled: list[ReviewCard] = []
        look_closer: list[ReviewCard] = []
        tile.toggled.connect(toggled.append)
        tile.look_closer_requested.connect(look_closer.append)

        corner = tile._look_closer_rect(tile.rect()).center()
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=corner)

        assert look_closer == [tile.card]
        assert toggled == []

    def test_clicking_elsewhere_on_the_tile_still_toggles_inclusion(self, qapp: QApplication) -> None:
        tile = self._make_tile()
        toggled: list[ReviewCard] = []
        look_closer: list[ReviewCard] = []
        tile.toggled.connect(toggled.append)
        tile.look_closer_requested.connect(look_closer.append)

        # Top-left corner: far from both the include/exclude badge
        # (top-right) and the look-closer affordance (bottom-right).
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))

        assert toggled == [tile.card]
        assert look_closer == []


class TestOpeningAndClosingTheInspector:
    def test_opening_shows_the_inspector_without_rebuilding_the_grid(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        tiles_before = workspace._tiles
        first_tile_before = next(iter(workspace._tiles.values()))
        card = workspace._card_list[0]

        workspace._on_look_closer_requested(card)

        assert workspace._inspector.isHidden() is False
        assert workspace._inspecting_index == 0
        # Same dict object, same tile instances -- _render_grid() was never
        # called, which is what actually guarantees the scroll position the
        # user opened from is still there when they close it.
        assert workspace._tiles is tiles_before
        assert next(iter(workspace._tiles.values())) is first_tile_before

    def test_closing_hides_the_inspector_and_still_does_not_rebuild(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        tiles_before = workspace._tiles
        card = workspace._card_list[0]
        workspace._on_look_closer_requested(card)

        workspace._close_inspector()

        assert workspace._inspector.isHidden() is True
        assert workspace._inspecting_index is None
        assert workspace._tiles is tiles_before

    def test_rebuild_defensively_closes_an_open_inspector(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])
        assert workspace._inspector.isHidden() is False

        workspace._rebuild()  # simulates navigating away and back

        assert workspace._inspector.isHidden() is True
        assert workspace._inspecting_index is None

    def test_look_closer_signal_for_a_card_no_longer_in_the_list_is_a_no_op(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(ReviewCard(999, 0, 0))
        assert workspace._inspecting_index is None
        assert workspace._inspector.isHidden() is True


class TestInspectorNavigation:
    def test_previous_is_disabled_on_the_first_card(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])
        assert workspace._inspector._prev_btn.isEnabled() is False
        assert workspace._inspector._next_btn.isEnabled() is True

    def test_next_is_disabled_on_the_last_card(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[-1])
        assert workspace._inspector._next_btn.isEnabled() is False
        assert workspace._inspector._prev_btn.isEnabled() is True

    def test_next_and_previous_step_one_card_at_a_time(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])

        workspace._inspect_next()
        assert workspace._inspecting_index == 1

        workspace._inspect_next()
        assert workspace._inspecting_index == 2

        workspace._inspect_previous()
        assert workspace._inspecting_index == 1

    def test_previous_and_next_do_not_wrap_around(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])
        workspace._inspect_previous()
        assert workspace._inspecting_index == 0

        workspace._on_look_closer_requested(workspace._card_list[-1])
        workspace._inspect_next()
        assert workspace._inspecting_index == len(workspace._card_list) - 1


class TestIncludeExcludeFromTheInspector:
    def test_toggling_from_the_inspector_updates_review_state_and_the_grid_tile(
        self, workspace: ReviewWorkspace,
    ) -> None:
        _make_ready(workspace)
        card = workspace._card_list[0]
        assert workspace.review_state.is_included(card) is True
        workspace._on_look_closer_requested(card)
        assert workspace._inspector._toggle_btn.text() == "Exclude this card"

        workspace._inspect_toggle_included()

        assert workspace.review_state.is_included(card) is False
        assert workspace._tiles[card]._included is False
        assert workspace._inspector._toggle_btn.text() == "Include this card"

    def test_toggling_back_from_the_inspector_re_includes_it(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        card = workspace._card_list[0]
        workspace._on_look_closer_requested(card)

        workspace._inspect_toggle_included()  # exclude
        workspace._inspect_toggle_included()  # re-include

        assert workspace.review_state.is_included(card) is True
        assert workspace._tiles[card]._included is True


class TestOnDemandCachedRendering:
    def test_inspect_scale_is_not_rendered_until_a_card_is_opened(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        spy = _RenderCallSpy(workspace._renderer.render_page)
        workspace._renderer.render_page = spy

        assert all(scale != INSPECT_RENDER_SCALE for _, scale in spy.calls)

        workspace._on_look_closer_requested(workspace._card_list[0])

        assert (FRONT_PAGE, INSPECT_RENDER_SCALE) in spy.calls

    def test_same_page_neighbors_reuse_the_cached_render(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        spy = _RenderCallSpy(workspace._renderer.render_page)
        workspace._renderer.render_page = spy

        first, second = workspace._card_list[0], workspace._card_list[1]
        assert first.page_num == second.page_num  # both on the 2x3 page-2 grid

        workspace._on_look_closer_requested(first)
        workspace._inspect_next()  # moves to `second`, same page

        inspect_calls = [c for c in spy.calls if c == (FRONT_PAGE, INSPECT_RENDER_SCALE)]
        assert len(inspect_calls) == 1, "the page should only be re-rendered at inspect scale once"

    def test_render_failure_falls_back_to_a_placeholder_without_raising(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)

        def _always_fail(page_number: int, scale: float):
            raise PDFRenderError("boom")

        workspace._renderer.render_page = _always_fail

        workspace._on_look_closer_requested(workspace._card_list[0])  # must not raise

        assert workspace._inspector.isHidden() is False

    def test_grid_render_scale_is_unaffected_by_inspection(self, workspace: ReviewWorkspace) -> None:
        # Sanity check that the two scales are actually different -- if
        # they were ever made equal, the "cached" test above would pass
        # for the wrong reason.
        assert INSPECT_RENDER_SCALE != REVIEW_RENDER_SCALE
