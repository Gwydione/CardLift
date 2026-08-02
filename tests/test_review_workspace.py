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
from deckforge_gui.review_workspace import (
    INSPECT_MARGIN_PT,
    INSPECT_RENDER_SCALE,
    PAIRED_INSPECT_MARGIN_FLOOR_PT,
    REVIEW_RENDER_SCALE,
    ReviewWorkspace,
    _CardTile,
)

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


class _CropCallSpy:
    """Wraps a bound crop_card_with_margin() method, recording each call's
    (geometry, row, col) -- lets tests assert Card Inspection's paired-back
    rendering uses the *same* row/col as the front card, on the paired
    back's own (possibly different) geometry, without hand-verifying pixel
    output. margin_pt is recorded separately (rather than folded into
    `calls`) so existing (geometry, row, col) unpacking is unaffected."""

    def __init__(self, real_crop_card_with_margin) -> None:
        self._real = real_crop_card_with_margin
        self.calls: list[tuple] = []
        self.margins: list[float] = []

    def __call__(self, page_image, geometry, trim, row, col, margin_pt):
        self.calls.append((geometry, row, col))
        self.margins.append(margin_pt)
        return self._real(page_image, geometry, trim, row, col, margin_pt)


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


class TestLookCloserGlyphSwapsForPairedBacks:
    """Manual testing found a hover-only tooltip insufficient for
    discoverability -- the look-closer badge's *resting* glyph itself
    must signal "front and back" before any hover happens. is_paired
    swaps only the glyph drawn inside the existing badge; the circle,
    size, position, hover-intensify behavior, and click target are all
    unchanged (TestLookCloserAffordance above already covers click
    behavior generically -- the last test here confirms it stays
    identical for a Paired tile specifically)."""

    def _make_tile(self, is_paired: bool, included: bool = True) -> _CardTile:
        pixmap = QPixmap(150, 210)
        pixmap.fill(Qt.GlobalColor.white)
        return _CardTile(ReviewCard(2, 0, 0), pixmap, included=included, is_paired=is_paired)

    def test_paired_tile_draws_the_paired_cards_glyph(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=True)
        calls: list[str] = []
        original = _CardTile._draw_paired_cards_glyph

        def spy(painter, look_rect, color):
            calls.append("paired")
            original(painter, look_rect, color)

        _CardTile._draw_paired_cards_glyph = staticmethod(spy)
        try:
            tile.grab()
        finally:
            _CardTile._draw_paired_cards_glyph = staticmethod(original)
        assert calls == ["paired"]

    def test_front_only_and_shared_back_tile_draws_the_magnifying_glass(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=False)
        calls: list[str] = []
        original = _CardTile._draw_magnifying_glass_glyph

        def spy(painter, look_rect):
            calls.append("glass")
            original(painter, look_rect)

        _CardTile._draw_magnifying_glass_glyph = staticmethod(spy)
        try:
            tile.grab()
        finally:
            _CardTile._draw_magnifying_glass_glyph = staticmethod(original)
        assert calls == ["glass"]

    def test_paired_tile_never_draws_the_magnifying_glass(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=True)
        calls: list[str] = []
        original = _CardTile._draw_magnifying_glass_glyph

        def spy(painter, look_rect):
            calls.append("glass")
            original(painter, look_rect)

        _CardTile._draw_magnifying_glass_glyph = staticmethod(spy)
        try:
            tile.grab()
        finally:
            _CardTile._draw_magnifying_glass_glyph = staticmethod(original)
        assert calls == []

    def test_non_paired_tile_never_draws_the_paired_cards_glyph(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=False)
        calls: list[str] = []
        original = _CardTile._draw_paired_cards_glyph

        def spy(painter, look_rect, color):
            calls.append("paired")
            original(painter, look_rect, color)

        _CardTile._draw_paired_cards_glyph = staticmethod(spy)
        try:
            tile.grab()
        finally:
            _CardTile._draw_paired_cards_glyph = staticmethod(original)
        assert calls == []

    def test_paired_tooltip_explains_the_comparison(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=True)
        assert tile.toolTip() == "PDF page 2 — compare front and paired back, or toggle include/exclude"

    def test_non_paired_tooltip_wording_unchanged(self, qapp: QApplication) -> None:
        tile = self._make_tile(is_paired=False)
        assert tile.toolTip() == "PDF page 2 — look closer or toggle include/exclude"

    def test_click_behavior_unchanged_for_a_paired_tile(self, qapp: QApplication) -> None:
        """The glyph swap must not affect which click -- the look-closer
        corner vs. anywhere else -- fires which signal."""
        tile = self._make_tile(is_paired=True)
        toggled: list[ReviewCard] = []
        look_closer: list[ReviewCard] = []
        tile.toggled.connect(toggled.append)
        tile.look_closer_requested.connect(look_closer.append)

        corner = tile._look_closer_rect(tile.rect()).center()
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=corner)
        assert look_closer == [tile.card]
        assert toggled == []

        QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        assert toggled == [tile.card]
        assert look_closer == [tile.card]  # unchanged from the first click


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


class TestPairedBacksReachesReviewCards:
    """Regression coverage for a real gap found during Phase 3 manual
    verification: review_state.review_ready() had an unconditional "False
    for PAIRED" branch left over from Phase 2 (when paired-back calibration
    didn't exist), so Review Cards stayed permanently unreachable and
    showed a stale "isn't supported" message even after Phase 3 shipped
    real Paired Backs calibration. Fixed by making PAIRED ready once
    paired_back is complete and Front/Back grid topology matches -- Review
    Cards still shows front cards only (per-card pairing is Phase 4), but
    the back panel stays visible with an honest caption explaining that,
    rather than disappearing -- a silently-missing panel was itself a
    follow-up UX gap (a Paired deck looked identical to Front Only, with no
    indication backs existed but weren't reviewable yet)."""

    BACK_PAGE = 1  # distinct from FRONT_PAGE (2); both real pages in the sample PDF

    def test_blocked_while_paired_back_incomplete(self, workspace: ReviewWorkspace) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        # build_review_cards() looks up every marked FRONT page's real
        # page size (to enumerate its suggested cards), but never touches
        # a BACK page beyond whichever one is calibrated -- so both FRONT
        # pages must be real (in-range) pages, while the second BACK page
        # (purely for balancing the count) need not be.
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)  # balances the count; real page, never calibrated
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)  # balances the count; never calibrated/looked up
        assert find_cards.back_mode().name == "PAIRED"

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        # paired_back left incomplete.
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        assert workspace._scroll_area.isHidden() is True
        assert workspace._blocked_label.isHidden() is False
        assert "representative Back page" in workspace._blocked_label.text()
        assert "Paired Back hasn't been calibrated yet" in workspace._status_label.text()
        assert workspace._continue_btn.isEnabled() is False

    def test_blocked_with_clear_copy_when_topology_mismatched(self, workspace: ReviewWorkspace) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        # build_review_cards() looks up every marked FRONT page's real
        # page size (to enumerate its suggested cards), but never touches
        # a BACK page beyond whichever one is calibrated -- so both FRONT
        # pages must be real (in-range) pages, while the second BACK page
        # (purely for balancing the count) need not be.
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)  # balances the count; real page, never calibrated
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)  # balances the count; never calibrated/looked up

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY  # 2x3 on this sample page
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = CalibratedGeometry(
            left=0.0, top=0.0, card_width=400.0, card_height=500.0,
            gap_x=0.0, gap_y=0.0, gap_x_derived=True, gap_y_derived=True,
        )
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        assert workspace._scroll_area.isHidden() is True
        assert "grid" in workspace._status_label.text().lower()
        assert "match" in workspace._status_label.text().lower()
        assert workspace._continue_btn.isEnabled() is False

    def test_ready_shows_paired_backs_panel_with_honest_caption_no_crash(self, workspace: ReviewWorkspace) -> None:
        """The actual crash risk this fix closes: _render_back_panel()'s
        Shared Back branch asserts calibrate_state.back.geometry is not
        None, which is never true for Paired Backs (that target is
        calibrate_state.paired_back instead) -- calling that branch would
        raise AssertionError. The Paired Backs branch must be reached
        instead, with the panel visible (not hidden) and no thumbnail."""
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        # build_review_cards() looks up every marked FRONT page's real
        # page size (to enumerate its suggested cards), but never touches
        # a BACK page beyond whichever one is calibrated -- so both FRONT
        # pages must be real (in-range) pages, while the second BACK page
        # (purely for balancing the count) need not be.
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)  # balances the count; real page, never calibrated
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)  # balances the count; never calibrated/looked up

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = FRONT_GEOMETRY  # matching topology
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()  # must not raise

        assert workspace._blocked_label.isHidden() is True
        assert workspace._scroll_area.isHidden() is False
        assert len(workspace._card_list) > 0
        assert workspace._continue_btn.isEnabled() is True

        # The panel itself: visible, caption-only (no thumbnail), exact copy.
        assert workspace._back_panel.isHidden() is False
        assert workspace._back_thumb_label.isHidden() is True
        assert workspace._back_caption.text() == (
            "Paired Backs — click “look closer” on any card below to compare it with its paired back."
        )

    def test_front_only_panel_regression(self, workspace: ReviewWorkspace) -> None:
        """Approved decision 8: Front Only's own back-panel branch must
        remain exactly as it was, unaffected by the new Paired Backs
        branch alongside it."""
        _make_ready(workspace)
        assert workspace._back_panel.isHidden() is False
        assert workspace._back_thumb_label.isHidden() is True
        assert workspace._back_caption.text() == "This deck is Front Only."

    def test_shared_back_panel_regression(self, workspace: ReviewWorkspace) -> None:
        """Approved decision 8: Shared Back's own back-panel branch --
        thumbnail plus "Shared Back: page N" caption -- must remain
        exactly as it was, unaffected by the new Paired Backs branch
        alongside it."""
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        assert find_cards.back_mode().name == "SHARED"

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.back.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        assert workspace._back_panel.isHidden() is False
        assert workspace._back_thumb_label.isHidden() is False
        assert workspace._back_caption.text() == (
            f"Shared Back — from page {self.BACK_PAGE}, applied to every card below."
        )


class TestOnePageFrontOneBackPairedDeckReachesReviewCards:
    """Regression coverage for the BackMode design correction: a deck with
    exactly one Front page and one explicitly-Paired Back page must reach
    Review Cards' Paired gating (paired_back completeness + topology),
    not be silently treated as Shared Back -- proving Review Cards needed
    no code changes once find_cards_state.back_mode() itself was
    corrected, since _rebuild() already only ever asks back_mode()."""

    BACK_PAGE = 1

    def _mark_one_page_paired(self, workspace: ReviewWorkspace) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.mark_single_back_page_as_paired()
        assert find_cards.back_mode().name == "PAIRED"

    def test_blocked_while_paired_back_incomplete(self, workspace: ReviewWorkspace) -> None:
        self._mark_one_page_paired(workspace)
        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        assert workspace._scroll_area.isHidden() is True
        assert "representative Back page" in workspace._blocked_label.text()

    def test_ready_shows_paired_backs_panel_once_calibrated(self, workspace: ReviewWorkspace) -> None:
        self._mark_one_page_paired(workspace)
        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = FRONT_GEOMETRY  # matching topology
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()  # must not raise

        assert workspace._blocked_label.isHidden() is True
        assert workspace._scroll_area.isHidden() is False
        assert len(workspace._card_list) > 0
        assert workspace._back_panel.isHidden() is False
        assert workspace._back_thumb_label.isHidden() is True
        assert workspace._back_caption.text() == (
            "Paired Backs — click “look closer” on any card below to compare it with its paired back."
        )
        assert workspace._continue_btn.isEnabled() is True


class TestPairedInspectMarginFormula:
    """_paired_inspect_margin_pt() derives the reduced side-by-side margin
    from the tighter geometry's own gap, rather than a blind fixed value,
    so it's guaranteed to never reach a neighboring cell regardless of a
    given deck's spacing. Tested directly against GridGeometry rather than
    through a full workspace, since this is pure arithmetic."""

    def _grid(self, gap: float) -> "GridGeometry":
        return CalibratedGeometry(
            left=27.0, top=139.5, card_width=180.0, card_height=252.0,
            gap_x=gap, gap_y=gap, gap_x_derived=False, gap_y_derived=False,
        ).to_grid_geometry()

    def test_wide_gap_clamps_to_the_existing_constant(self) -> None:
        wide = self._grid(gap=60.0)  # half the gap (30) exceeds INSPECT_MARGIN_PT
        assert ReviewWorkspace._paired_inspect_margin_pt(wide, wide) == INSPECT_MARGIN_PT

    def test_moderate_gap_uses_half_the_tighter_gap(self) -> None:
        moderate = self._grid(gap=20.0)  # half (10) sits between the floor and the cap
        assert ReviewWorkspace._paired_inspect_margin_pt(moderate, moderate) == 10.0

    def test_tight_gap_clamps_to_the_floor(self) -> None:
        tight = self._grid(gap=2.0)  # half (1.0) would otherwise round to almost nothing
        assert ReviewWorkspace._paired_inspect_margin_pt(tight, tight) == PAIRED_INSPECT_MARGIN_FLOOR_PT

    def test_uses_the_tighter_of_front_and_back_gaps(self) -> None:
        loose_front = self._grid(gap=60.0)
        tight_back = self._grid(gap=6.0)  # half (3.0) is below the floor
        assert ReviewWorkspace._paired_inspect_margin_pt(loose_front, tight_back) == PAIRED_INSPECT_MARGIN_FLOOR_PT
        # Order must not matter -- the tighter geometry governs either way.
        assert ReviewWorkspace._paired_inspect_margin_pt(tight_back, loose_front) == PAIRED_INSPECT_MARGIN_FLOOR_PT


class TestPairedBackCardInspection:
    """Phase 4: Card Inspection extended for Paired Backs -- the inspected
    front and its paired back appear side by side, resolved via
    find_cards_state.paired_back_page_for() and cropped at the same
    row/col on calibrate_state.paired_back's own, independently
    calibrated geometry (Front and Back are only guaranteed to share
    row/column topology, not margins/card size/gaps -- see
    docs/design/MULTIPLE_BACK_MODES.md's Initial Assumptions)."""

    BACK_PAGE = 1

    def _one_page_paired(self, workspace: ReviewWorkspace, back_geometry: CalibratedGeometry = FRONT_GEOMETRY) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.mark_single_back_page_as_paired()

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = back_geometry
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

    def test_paired_back_resolution_shows_both_images(self, workspace: ReviewWorkspace) -> None:
        self._one_page_paired(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])
        assert workspace._inspector._back_image_label.isHidden() is False
        assert workspace._inspector._back_pixmap is not None
        assert workspace._inspector._crop_caption.text() == (
            "Front (left) and its paired back (right). The area inside each outline is what CardLift will export."
        )

    def test_grid_tiles_are_wired_as_paired(self, workspace: ReviewWorkspace) -> None:
        """_render_grid() must thread back_mode() into every tile it
        builds, not just the ones opened via the inspector -- the glyph
        swap has to be visible on every card at rest, not only on demand."""
        self._one_page_paired(workspace)
        assert len(workspace._tiles) > 0
        for tile in workspace._tiles.values():
            assert tile._is_paired is True

    def test_same_row_and_column_used_for_the_paired_back(self, workspace: ReviewWorkspace) -> None:
        """The core correctness guarantee: the back crop must come from
        the *same* (row, col) as the front, on the paired back's own
        geometry -- not the front's geometry reused, and not always
        (0, 0)."""
        # Deliberately different origin from FRONT_GEOMETRY, so a bug that
        # accidentally reused the front's geometry for the back crop
        # would produce a different (and therefore caught) call.
        back_geometry = CalibratedGeometry(
            left=50.0, top=60.0, card_width=180.0, card_height=252.0,
            gap_x=9.0, gap_y=9.0, gap_x_derived=True, gap_y_derived=True,
        )
        self._one_page_paired(workspace, back_geometry=back_geometry)
        spy = _CropCallSpy(workspace._inspect_cropper.crop_card_with_margin)
        workspace._inspect_cropper.crop_card_with_margin = spy

        # A card other than (0, 0), so "always crops the corner cell"
        # would also be caught.
        card = next(c for c in workspace._card_list if (c.row, c.col) != (0, 0))
        workspace._on_look_closer_requested(card)

        assert len(spy.calls) == 2
        front_geom, front_row, front_col = spy.calls[0]
        back_geom, back_row, back_col = spy.calls[1]
        assert (front_row, front_col) == (card.row, card.col)
        assert (back_row, back_col) == (card.row, card.col)
        assert front_geom == workspace._grid_geometry
        assert back_geom == back_geometry.to_grid_geometry()
        assert front_geom != back_geom  # genuinely independent geometries

    def test_one_page_paired_deck(self, workspace: ReviewWorkspace) -> None:
        self._one_page_paired(workspace)
        assert workspace.find_cards_state.back_mode().name == "PAIRED"
        assert workspace.find_cards_state.front_page_count() == 1
        assert len(workspace.find_cards_state.back_pages()) == 1
        card = workspace._card_list[0]
        pixmap, ok = workspace._render_paired_back_inspect_pixmap(card)
        assert ok is True
        assert pixmap is not None

    def test_multi_page_paired_deck_resolves_a_different_back_per_front_page(self, workspace: ReviewWorkspace) -> None:
        """Two Front pages, two Back pages -- the second Back page is
        deliberately a page number outside the real 3-page sample PDF, so
        this single scenario also proves the per-front-page resolution is
        genuinely independent (front page 2 gets a real, renderable back;
        front page 3 gets one that fails to render) rather than always
        reusing whichever back page resolved first."""
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)  # out of range for the real sample PDF
        assert find_cards.back_mode().name == "PAIRED"

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        card_on_page_2 = next(c for c in workspace._card_list if c.page_num == FRONT_PAGE)
        card_on_page_3 = next(c for c in workspace._card_list if c.page_num == 3)

        assert find_cards.paired_back_page_for(FRONT_PAGE) == self.BACK_PAGE
        assert find_cards.paired_back_page_for(3) == 4

        _, ok_2 = workspace._render_paired_back_inspect_pixmap(card_on_page_2)
        _, ok_3 = workspace._render_paired_back_inspect_pixmap(card_on_page_3)
        assert ok_2 is True   # page 1 is real -- renders successfully
        assert ok_3 is False  # page 4 doesn't exist -- graceful fallback

    def test_missing_pair_fallback_when_counts_unbalanced(self, workspace: ReviewWorkspace) -> None:
        """paired_back_page_for() itself returns None (the front page's
        index has no corresponding Back page) -- a different failure mode
        than an unrenderable page number, and one review_ready() does not
        itself prevent reaching (see review_state.review_ready()'s PAIRED
        branch, which does not check paired_page_counts_balanced())."""
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)
        find_cards.set_role(self.BACK_PAGE, PageRole.BACK)
        find_cards.mark_single_back_page_as_paired()
        assert find_cards.paired_page_counts_balanced() is False

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.paired_back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.paired_back.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.paired_back.calibrated_page_num = self.BACK_PAGE
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()  # must not raise despite the mismatch

        card_on_page_3 = next(c for c in workspace._card_list if c.page_num == 3)
        assert find_cards.paired_back_page_for(3) is None

        pixmap, ok = workspace._render_paired_back_inspect_pixmap(card_on_page_3)
        assert ok is False
        assert pixmap is not None  # an honest placeholder, not None/a crash

        workspace._on_look_closer_requested(card_on_page_3)  # must not raise
        assert workspace._inspector._back_image_label.isHidden() is False
        assert "No paired back could be found" in workspace._inspector._crop_caption.text()

    def test_front_and_back_receive_the_same_reduced_margin(self, workspace: ReviewWorkspace) -> None:
        """The margin passed to crop_card_with_margin() must be identical
        for both the front and back crop -- an asymmetric margin would
        make the two previews look inconsistently framed, undermining the
        side-by-side comparison this feature exists for. FRONT_GEOMETRY's
        gap is 9.0 and this back geometry's is 6.0, so the *combined*
        tightest gap (6.0) governs both, halved (3.0) and floored to
        PAIRED_INSPECT_MARGIN_FLOOR_PT."""
        back_geometry = CalibratedGeometry(
            left=50.0, top=60.0, card_width=180.0, card_height=252.0,
            gap_x=6.0, gap_y=6.0, gap_x_derived=True, gap_y_derived=True,
        )
        self._one_page_paired(workspace, back_geometry=back_geometry)
        spy = _CropCallSpy(workspace._inspect_cropper.crop_card_with_margin)
        workspace._inspect_cropper.crop_card_with_margin = spy

        workspace._on_look_closer_requested(workspace._card_list[0])

        assert len(spy.margins) == 2
        front_margin, back_margin = spy.margins
        assert front_margin == back_margin == PAIRED_INSPECT_MARGIN_FLOOR_PT

    def test_next_previous_updates_both_previews(self, workspace: ReviewWorkspace) -> None:
        """Advancing the logical card must re-render both sides -- not
        just the front, leaving a stale back preview behind."""
        self._one_page_paired(workspace)
        spy = _CropCallSpy(workspace._inspect_cropper.crop_card_with_margin)
        workspace._inspect_cropper.crop_card_with_margin = spy

        workspace._on_look_closer_requested(workspace._card_list[0])
        assert len(spy.calls) == 2  # one front, one back
        first_card = workspace._card_list[0]
        assert (spy.calls[0][1], spy.calls[0][2]) == (first_card.row, first_card.col)
        assert (spy.calls[1][1], spy.calls[1][2]) == (first_card.row, first_card.col)

        workspace._inspect_next()
        assert len(spy.calls) == 4  # a fresh front+back pair, not reused
        second_card = workspace._card_list[1]
        assert (spy.calls[2][1], spy.calls[2][2]) == (second_card.row, second_card.col)
        assert (spy.calls[3][1], spy.calls[3][2]) == (second_card.row, second_card.col)
        assert second_card.row != first_card.row or second_card.col != first_card.col


class TestFrontOnlyAndSharedBackInspectorRegression:
    """Approved scope: Front Only and Shared Back's inspector behavior
    must be exactly what it was before Card Inspection learned about
    Paired Backs -- single image, no second slot, unchanged caption."""

    def test_front_only_inspector_has_no_back_image(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        workspace._on_look_closer_requested(workspace._card_list[0])
        assert workspace._inspector._back_image_label.isHidden() is True
        assert workspace._inspector._back_pixmap is None
        assert workspace._inspector._crop_caption.text() == (
            "The area inside the outline is what CardLift will export."
        )

    def test_front_only_still_uses_the_full_inspect_margin(self, workspace: ReviewWorkspace) -> None:
        """The reduced Paired Backs margin must never leak into Front
        Only's single-image inspection -- FRONT_GEOMETRY's own gap (9.0)
        would otherwise clamp the margin down from INSPECT_MARGIN_PT."""
        _make_ready(workspace)
        spy = _CropCallSpy(workspace._inspect_cropper.crop_card_with_margin)
        workspace._inspect_cropper.crop_card_with_margin = spy

        workspace._on_look_closer_requested(workspace._card_list[0])

        assert spy.margins == [INSPECT_MARGIN_PT]

    def test_front_only_grid_tiles_are_not_wired_as_paired(self, workspace: ReviewWorkspace) -> None:
        _make_ready(workspace)
        assert len(workspace._tiles) > 0
        for tile in workspace._tiles.values():
            assert tile._is_paired is False

    def test_shared_back_inspector_has_no_back_image(self, workspace: ReviewWorkspace) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(1, PageRole.BACK)
        assert find_cards.back_mode().name == "SHARED"

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.back.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.back.calibrated_page_num = 1
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        workspace._on_look_closer_requested(workspace._card_list[0])
        assert workspace._inspector._back_image_label.isHidden() is True
        assert workspace._inspector._back_pixmap is None
        assert workspace._inspector._crop_caption.text() == (
            "The area inside the outline is what CardLift will export."
        )

    def test_shared_back_still_uses_the_full_inspect_margin(self, workspace: ReviewWorkspace) -> None:
        find_cards = workspace.find_cards_state
        find_cards._roles.clear()
        find_cards.set_role(FRONT_PAGE, PageRole.FRONT)
        find_cards.set_role(1, PageRole.BACK)
        assert find_cards.back_mode().name == "SHARED"

        workspace.calibrate_state.cards.reset()
        workspace.calibrate_state.back.reset()
        workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        workspace.calibrate_state.back.geometry = FRONT_GEOMETRY
        workspace.calibrate_state.back.calibrated_page_num = 1
        workspace.set_pdf(SAMPLE_PDF, 12)
        workspace.on_shown()

        spy = _CropCallSpy(workspace._inspect_cropper.crop_card_with_margin)
        workspace._inspect_cropper.crop_card_with_margin = spy

        workspace._on_look_closer_requested(workspace._card_list[0])

        assert spy.margins == [INSPECT_MARGIN_PT]
