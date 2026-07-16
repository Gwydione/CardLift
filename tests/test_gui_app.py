"""Regression coverage for the QToolTip theme fix in gui_app.py.

Windows can hand Qt a "system" tooltip palette where the background goes
dark (or black) without a matching change to the text color, producing an
unreadable dark-on-dark tooltip -- this is what clean-machine validation in
Windows Sandbox surfaced on the Review Cards card tile's hover tooltip.
gui_app._apply_tooltip_theme() fixes this app-wide (QSS + QPalette, not a
one-off on that single widget) rather than depending on whatever tooltip
palette the OS happens to hand Qt at runtime."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import gui_app  # noqa: E402
from deckforge_gui.theme import BG_CARD, TEXT_HEADING  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _luminance(color: QColor) -> float:
    """Relative luminance (WCAG-style, sRGB channels treated as linear for
    a coarse but sufficient contrast check -- not a full gamma-correct
    implementation)."""
    return 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()


def test_tooltip_style_defines_explicit_background_and_foreground() -> None:
    """The app stylesheet must name a QToolTip rule with its own background
    and color -- not rely on whatever the OS/Qt default palette supplies."""
    assert "QToolTip" in gui_app._TOOLTIP_STYLE
    assert f"background: {BG_CARD}" in gui_app._TOOLTIP_STYLE
    assert f"color: {TEXT_HEADING}" in gui_app._TOOLTIP_STYLE


def test_tooltip_style_colors_have_readable_contrast() -> None:
    """Guards against a future edit accidentally picking two close colors
    for QToolTip's own background/text -- the exact defect being fixed
    here, just self-inflicted instead of OS-inflicted."""
    bg = QColor(BG_CARD)
    fg = QColor(TEXT_HEADING)
    assert abs(_luminance(bg) - _luminance(fg)) > 100


def test_apply_tooltip_theme_sets_stylesheet_and_palette(qapp: QApplication) -> None:
    """Reproduces the Windows Sandbox failure mode directly: start from a
    hostile system tooltip palette (dark background, unchanged dark text --
    what a clean Windows install can hand Qt) and confirm
    _apply_tooltip_theme() overrides both the QSS *and* the QPalette roles,
    since a native tooltip paint path can source colors from either."""
    hostile = qapp.palette()
    hostile.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1e1e1e"))
    hostile.setColor(QPalette.ColorRole.ToolTipText, QColor("#000000"))
    qapp.setPalette(hostile)
    qapp.setStyleSheet("")

    gui_app._apply_tooltip_theme(qapp)

    assert gui_app._TOOLTIP_STYLE in qapp.styleSheet()
    palette = qapp.palette()
    assert palette.color(QPalette.ColorRole.ToolTipBase) == QColor(BG_CARD)
    assert palette.color(QPalette.ColorRole.ToolTipText) == QColor(TEXT_HEADING)
