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

from deckforge_gui.app_state import AppState
from deckforge_gui.calibrate_state import CalibrateState
from deckforge_gui.calibrate_workspace import CalibrateWorkspace
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.theme import ACCENT
from deckforge_gui.workspaces import WorkflowStep


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
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), self._paired_find_cards_state(),
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
        ws = CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, AppState(), CalibrateState(), self._paired_find_cards_state(),
        )
        ws._update_controls()
        assert ws._page_label.text() == "Paired Backs calibration not yet available"

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
