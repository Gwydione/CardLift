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
from deckforge_gui.find_cards_state import FindCardsState
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
