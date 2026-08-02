"""Regression coverage for CardLift v0.1.1-alpha's Pan Mode on-canvas
indicator (docs/ui/UI_DECISIONS.md "Pan Mode": the button highlight,
cursor change, and status-bar message were all already implemented, but
an Alpha tester still found it unclear whether Pan mode was active --
they all sit at the periphery of the window rather than on the canvas
itself, where the user is actually looking right before they click or
drag). _CalibrateCanvas._draw_pan_indicator() reinforces the same signal
(app_state.PAN_STATUS, already shown in the status bar) as a small badge
drawn directly on the canvas, visible only while pan_mode is active.

Checks pixel content rather than asserting on rendered text (font
substitution under QT_QPA_PLATFORM=offscreen can turn text into
unreadable glyph placeholders -- confirmed harmless and specific to that
headless environment, not a real rendering defect, but it means asserting
on legible glyphs here would be flaky). Counting ACCENT-colored pixels is
a stable, environment-independent proxy for "the badge is/isn't drawn"."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from deckforge_gui.app_state import WORKFLOW_ORDER, AppState
from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrateState
from deckforge_gui.calibrate_workspace import CalibrateWorkspace
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.sidebar import Sidebar
from deckforge_gui.theme import ACCENT
from deckforge_gui.workspaces import WorkflowStep

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "CardLift_Demo_Deck.pdf"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def workspace(qapp: QApplication) -> CalibrateWorkspace:
    ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_CARDS, AppState(), CalibrateState(), FindCardsState())
    ws.resize(400, 300)
    ws.show()
    qapp.processEvents()
    return ws


def _accent_pixel_count(img) -> int:
    target = QColor(ACCENT)
    count = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if abs(c.red() - target.red()) < 10 and abs(c.green() - target.green()) < 10 and abs(c.blue() - target.blue()) < 10:
                count += 1
    return count


class TestPanModeIndicator:
    def test_no_badge_when_pan_mode_inactive(self, qapp: QApplication, workspace: CalibrateWorkspace) -> None:
        workspace.app_state.pan_mode = False
        workspace._canvas.set_pan_active(False)
        qapp.processEvents()
        img = workspace._canvas.grab().toImage()
        assert _accent_pixel_count(img) == 0

    def test_badge_appears_when_pan_mode_active(self, qapp: QApplication, workspace: CalibrateWorkspace) -> None:
        workspace.app_state.pan_mode = True
        workspace._canvas.set_pan_active(True)
        qapp.processEvents()
        img = workspace._canvas.grab().toImage()
        assert _accent_pixel_count(img) > 0

    def test_badge_disappears_immediately_on_exit(self, qapp: QApplication, workspace: CalibrateWorkspace) -> None:
        workspace.app_state.pan_mode = True
        workspace._canvas.set_pan_active(True)
        qapp.processEvents()
        assert _accent_pixel_count(workspace._canvas.grab().toImage()) > 0

        workspace.app_state.pan_mode = False
        workspace._canvas.set_pan_active(False)
        qapp.processEvents()
        assert _accent_pixel_count(workspace._canvas.grab().toImage()) == 0

    def test_badge_draws_even_with_no_page_loaded(self, qapp: QApplication, workspace: CalibrateWorkspace) -> None:
        """Regression guard: an earlier draft only drew the badge inside
        the branch that requires a loaded pixmap/view, so the indicator
        silently failed to appear whenever Pan was toggled on a step with
        no page yet (e.g. Shared Back, UNRESOLVED) -- exactly the "user
        can't tell they're in Pan mode" defect this feature exists to fix."""
        assert workspace._pixmap is None
        assert workspace._view is None
        workspace.app_state.pan_mode = True
        workspace._canvas.set_pan_active(True)
        qapp.processEvents()
        img = workspace._canvas.grab().toImage()
        assert _accent_pixel_count(img) > 0


class TestBackStepNeverMisrepresentsPairedBacksAsSharedBack:
    """Regression coverage for a real UX gap found during manual Phase 2
    verification: a Paired Backs deck was told "Continue to Shared Back"
    and, once on that step, "Shared Back hasn't been decided yet -- go
    back to Select Card Pages", even though the user correctly chose
    Paired Backs. Root cause: shared_back_status() collapses to
    UNRESOLVED for 2+ BACK pages (its own docstring warns it isn't
    meaningful once back_mode() is PAIRED), and nothing checked back_mode()
    first. Paired calibration itself is still not implemented -- this only
    covers that the workflow no longer contradicts the user's choice while
    it isn't."""

    def _paired_find_cards_state(self) -> FindCardsState:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(3, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)
        return find_cards

    def test_fronts_step_continue_button_is_mode_neutral(self, qapp: QApplication) -> None:
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_CARDS, AppState(), CalibrateState(), self._paired_find_cards_state(),
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.text() == "Continue to Back ›"
        assert "Shared Back" not in ws._continue_btn.text()

    def test_back_step_names_paired_backs_not_shared_back(self, qapp: QApplication) -> None:
        """Once Paired Back calibration is actually complete (Phase 3),
        the banner names Paired Backs, never Shared Back or "hasn't been
        decided"."""
        calibrate_state = CalibrateState()
        calibrate_state.record_click_on(calibrate_state.paired_back, 0.0, 0.0)
        calibrate_state.record_click_on(calibrate_state.paired_back, 100.0, 100.0)
        calibrate_state.finish_with_one_card_on(calibrate_state.paired_back)
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, self._paired_find_cards_state(),
        )
        ws._update_continue_footer(ws.current_target())
        banner = ws._completion_banner.text()
        assert "Shared Back" not in banner
        assert "hasn't been decided" not in banner
        assert "Paired Backs" in banner

    def test_back_step_continue_stays_disabled_for_paired(self, qapp: QApplication) -> None:
        """Gating is unchanged -- Paired was already effectively blocked
        (via the UNRESOLVED fallthrough) before this fix; only the wording
        and the misleading "back to Select Card Pages" button change."""
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), self._paired_find_cards_state(),
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False

    def test_back_step_hides_the_back_to_select_cards_button_for_paired(self, qapp: QApplication) -> None:
        """Showing "Back to Select Card Pages" for Paired Backs would imply
        the user needs to redo a decision they already made correctly."""
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), self._paired_find_cards_state(),
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._back_to_select_btn.isVisibleTo(ws) is False

    def test_back_step_page_label_names_paired_backs(self, qapp: QApplication) -> None:
        """Unlike Phase 2 (where the Back step had no real page to show for
        Paired Backs), Phase 3 makes the marked BACK-page set navigable --
        the page label shows a "Back page N of M" secondary line, the same
        way Fronts already shows "Front page N of M"."""
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), self._paired_find_cards_state(),
        )
        ws.on_shown()  # selects navigable[0] as the current page, no PDF needed for that
        ws._update_controls()
        assert "Back page 1 of 2" in ws._page_label.text()

    def test_genuinely_unresolved_case_is_unaffected(self, qapp: QApplication) -> None:
        """The pre-existing, genuinely-unresolved (zero BACK pages) case
        must still show its own message and its "back to Select Card
        Pages" button -- this fix must not suppress that for the case it
        was always correct for."""
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), find_cards)
        ws._update_continue_footer(ws.current_target())
        assert ws._back_to_select_btn.isVisibleTo(ws) is True
        assert "Back hasn't been decided" in ws._completion_banner.text()


class TestWorkspaceSelectsTargetByBackMode:
    """Approved decision 7: mode-aware target selection belongs in
    CalibrateWorkspace (current_target()), not CalibrateState.target_for()
    (which stays pure/FindCardsState-independent -- see
    CalibrateState.target_for()'s own docstring)."""

    def test_cards_step_always_resolves_cards(self, qapp: QApplication) -> None:
        calibrate_state = CalibrateState()
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.BACK)
        find_cards.set_role(3, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_CARDS, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.cards

    def test_back_step_resolves_back_target_for_shared_mode(self, qapp: QApplication) -> None:
        calibrate_state = CalibrateState()
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.back

    def test_back_step_resolves_paired_back_target_for_paired_mode(self, qapp: QApplication) -> None:
        calibrate_state = CalibrateState()
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(3, PageRole.BACK)
        find_cards.set_role(4, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.paired_back

    def test_back_step_resolves_back_target_for_none_mode(self, qapp: QApplication) -> None:
        calibrate_state = CalibrateState()
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.back

    def test_target_switches_live_as_back_pages_are_added(self, qapp: QApplication) -> None:
        """The same workspace instance must track back_mode() changing
        (e.g. a user adding a second BACK page while sitting on Select
        Card Pages, then navigating to Calibrate) rather than caching an
        answer from construction time."""
        calibrate_state = CalibrateState()
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.back

        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)
        find_cards.set_role(4, PageRole.BACK)
        assert ws.current_target() is calibrate_state.paired_back


class TestOnePageFrontOneBackPairedDeckRoutesCorrectly:
    """Regression coverage for the BackMode design correction: a deck with
    exactly one Front page and one explicitly-Paired Back page must route
    to full-grid calibration (paired_back), not the single-card Shared
    Back target -- proving Calibrate needed no code changes once
    find_cards_state.back_mode() itself was corrected, since
    current_target() already only ever asks back_mode()."""

    def _one_page_paired_find_cards(self) -> FindCardsState:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.BACK)
        find_cards.mark_single_back_page_as_paired()
        return find_cards

    def test_current_target_resolves_to_paired_back(self, qapp: QApplication) -> None:
        find_cards = self._one_page_paired_find_cards()
        calibrate_state = CalibrateState()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.paired_back
        assert ws.current_target() is not calibrate_state.back

    def test_navigable_pages_is_the_single_back_page(self, qapp: QApplication) -> None:
        find_cards = self._one_page_paired_find_cards()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), find_cards)
        assert ws._navigable_pages() == [2]

    def test_continue_blocked_until_complete_then_enabled(self, qapp: QApplication) -> None:
        find_cards = self._one_page_paired_find_cards()
        calibrate_state = CalibrateState()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False

        calibrate_state.record_click_on(calibrate_state.paired_back, 0.0, 0.0)
        calibrate_state.record_click_on(calibrate_state.paired_back, 100.0, 100.0)
        calibrate_state.finish_with_one_card_on(calibrate_state.paired_back)
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is True
        assert "Paired Backs calibration complete" in ws._completion_banner.text()


class TestPairedBackNavigationAndClickHandling:
    """Approved decision 3/objective 1: Paired Backs' representative page
    is chosen from the full marked BACK-page set (like Fronts), and reuses
    the same two-corner-click + optional second-card machinery -- routed
    through current_target(), not a hardcoded target."""

    def _paired_ws(self) -> tuple[CalibrateWorkspace, FindCardsState]:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(8, PageRole.BACK)
        find_cards.set_role(9, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), find_cards)
        return ws, find_cards

    def test_navigable_pages_are_the_full_back_page_set(self, qapp: QApplication) -> None:
        ws, _ = self._paired_ws()
        assert ws._navigable_pages() == [8, 9]

    def test_on_shown_selects_the_first_back_page(self, qapp: QApplication) -> None:
        ws, _ = self._paired_ws()
        ws.on_shown()
        assert ws.current_target().page_num == 8

    def test_start_over_resets_paired_back_not_shared_back(self, qapp: QApplication) -> None:
        ws, _ = self._paired_ws()
        calibrate_state = ws.calibrate_state
        ws.on_shown()
        calibrate_state.record_click_on(calibrate_state.paired_back, 0.0, 0.0)
        calibrate_state.record_click_on(calibrate_state.paired_back, 100.0, 100.0)
        calibrate_state.finish_with_one_card_on(calibrate_state.paired_back)
        assert calibrate_state.paired_back.is_complete is True
        ws._on_start_over()
        assert calibrate_state.paired_back.is_complete is False
        assert calibrate_state.back.is_complete is False  # untouched


class TestPairedTopologyGating:
    """Approved objective 5: Continue must block with clear, actionable
    copy when Front and Paired Back suggest different grid topology, and
    unblock once both agree (or once Fronts hasn't been calibrated at all,
    since there's nothing yet to compare -- Paired Back's Continue never
    waited on Fronts either way, same as Shared Back's doesn't)."""

    def _paired_ws(self) -> CalibrateWorkspace:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(8, PageRole.BACK)
        find_cards.set_role(9, PageRole.BACK)
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), find_cards)
        ws.set_pdf(SAMPLE_PDF, 12)
        return ws

    def test_continue_blocked_while_paired_back_incomplete(self, qapp: QApplication) -> None:
        ws = self._paired_ws()
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False
        assert ws._completion_banner.isVisibleTo(ws) is False

    def test_continue_enabled_once_matching_topology_and_complete(self, qapp: QApplication) -> None:
        ws = self._paired_ws()
        calibrate_state = ws.calibrate_state
        matching_geometry = CalibratedGeometry(
            left=27.0, top=139.5, card_width=180.0, card_height=252.0,
            gap_x=9.0, gap_y=9.0, gap_x_derived=True, gap_y_derived=True,
        )
        calibrate_state.cards.calibrated_page_num = 1
        calibrate_state.cards.geometry = matching_geometry
        calibrate_state.paired_back.calibrated_page_num = 2
        calibrate_state.paired_back.geometry = matching_geometry
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is True
        assert "Paired Backs calibration complete" in ws._completion_banner.text()

    def test_continue_blocked_when_topology_differs(self, qapp: QApplication) -> None:
        ws = self._paired_ws()
        calibrate_state = ws.calibrate_state
        calibrate_state.cards.calibrated_page_num = 1
        calibrate_state.cards.geometry = CalibratedGeometry(
            left=27.0, top=139.5, card_width=180.0, card_height=252.0,
            gap_x=9.0, gap_y=9.0, gap_x_derived=True, gap_y_derived=True,
        )
        # Much larger cards on the Back page -- fewer cells fit, a
        # different suggested grid shape than the Front page's.
        calibrate_state.paired_back.calibrated_page_num = 2
        calibrate_state.paired_back.geometry = CalibratedGeometry(
            left=0.0, top=0.0, card_width=400.0, card_height=500.0,
            gap_x=0.0, gap_y=0.0, gap_x_derived=True, gap_y_derived=True,
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False
        banner = ws._completion_banner.text()
        assert "grid" in banner.lower()
        assert "match" in banner.lower()
        assert "×" in banner  # names both shapes, not just "they differ"

    def test_continue_enabled_when_fronts_not_yet_calibrated(self, qapp: QApplication) -> None:
        """No topology to compare yet -- Paired Back alone being complete
        is enough, exactly as Fronts' own Continue never waits on Back."""
        ws = self._paired_ws()
        calibrate_state = ws.calibrate_state
        calibrate_state.paired_back.calibrated_page_num = 2
        calibrate_state.paired_back.geometry = CalibratedGeometry(
            left=27.0, top=139.5, card_width=180.0, card_height=252.0,
            gap_x=9.0, gap_y=9.0, gap_x_derived=True, gap_y_derived=True,
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is True

    def test_continue_blocked_when_paired_page_counts_unbalanced(self, qapp: QApplication) -> None:
        """Defensive check: Select Card Pages already blocks reaching here
        unbalanced, but AppState.is_reached's one-way ratchet lets the
        sidebar jump back into Calibrate after counts change there without
        revisiting Continue -- this must still block, with the route back
        to Select Card Pages shown."""
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(3, PageRole.FRONT)
        find_cards.set_role(8, PageRole.BACK)
        find_cards.set_role(9, PageRole.BACK)
        assert find_cards.paired_page_counts_balanced() is False
        calibrate_state = CalibrateState()
        calibrate_state.paired_back.calibrated_page_num = 2
        calibrate_state.paired_back.geometry = CalibratedGeometry(
            left=0.0, top=0.0, card_width=100.0, card_height=150.0,
            gap_x=0.0, gap_y=0.0, gap_x_derived=True, gap_y_derived=True,
        )
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False
        assert ws._back_to_select_btn.isVisibleTo(ws) is True
        assert "counts" in ws._completion_banner.text().lower()


class TestFrontOnlyAndSharedBackRemainUnchanged:
    """Approved decision 8: existing Shared Back and Front Only behavior
    must remain unchanged by the Paired Backs addition."""

    def test_front_only_confirmed_none_still_unblocks_continue(self, qapp: QApplication) -> None:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.confirm_no_shared_back()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), find_cards)
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is True
        assert "Front Only" in ws._completion_banner.text()

    def test_shared_back_still_requires_its_own_calibration(self, qapp: QApplication) -> None:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(8, PageRole.BACK)
        calibrate_state = CalibrateState()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is False  # not yet calibrated

        calibrate_state.back.calibrated_page_num = 8
        calibrate_state.back.geometry = CalibratedGeometry(
            left=0.0, top=0.0, card_width=100.0, card_height=150.0,
            gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
        )
        ws._update_continue_footer(ws.current_target())
        assert ws._continue_btn.isEnabled() is True
        assert "Shared Back calibration complete" in ws._completion_banner.text()

    def test_shared_back_target_is_used_not_paired_back(self, qapp: QApplication) -> None:
        find_cards = FindCardsState()
        find_cards.set_role(1, PageRole.FRONT)
        find_cards.set_role(8, PageRole.BACK)
        calibrate_state = CalibrateState()
        ws = CalibrateWorkspace(WorkflowStep.CALIBRATE_BACK, AppState(), calibrate_state, find_cards)
        assert ws.current_target() is calibrate_state.back
        assert ws.current_target() is not calibrate_state.paired_back


class TestNoNewWorkflowStepOrSidebarEntry:
    """Approved decision 4: Paired Backs must not add a new WorkflowStep
    or sidebar entry -- it entirely reuses the existing Back step/slot."""

    def test_workflow_step_enum_unchanged(self) -> None:
        assert {s.name for s in WorkflowStep} == {
            "DECK", "FIND_CARDS", "CALIBRATE_CARDS", "CALIBRATE_BACK", "REVIEW_CARDS", "EXPORT",
        }

    def test_workflow_order_length_unchanged(self) -> None:
        assert len(WORKFLOW_ORDER) == 6

    def test_sidebar_still_has_exactly_six_leaves(self, qapp: QApplication) -> None:
        sidebar = Sidebar(AppState())
        assert len(sidebar._buttons) == 6
        assert set(sidebar._buttons.keys()) == set(WorkflowStep)

    def test_sidebar_back_label_still_mode_neutral(self, qapp: QApplication) -> None:
        """The Back step's sidebar label stays "Back" regardless of
        BackMode -- Paired Backs reuses the exact same leaf, it does not
        relabel it or add a sibling entry."""
        from deckforge_gui.app_state import STEP_LABELS
        assert STEP_LABELS[WorkflowStep.CALIBRATE_BACK] == "Back"
