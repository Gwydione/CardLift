#!/usr/bin/env python3
"""
DeckForge - gui_app.py

Launches the desktop application. Thin entry point, same pattern as
extract.py -- all logic lives in src/deckforge_gui/.

    pip install -r requirements-gui.txt
    python gui_app.py

Runs the full six-step guided workflow (Deck, Select Card Pages,
Calibrate Fronts, Calibrate Back, Review Cards, Export) against the
real PDF/calibration engine in src/deckforge/, backed by local crash
logging (see src/deckforge_gui/logging_setup.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from deckforge_gui.logging_setup import configure_logging  # noqa: E402
from deckforge_gui.main_window import MainWindow  # noqa: E402
from deckforge_gui.theme import BG_CARD, BORDER_CARD, TEXT_HEADING  # noqa: E402

# Qt's native tooltip styling is unset by default, so on Windows dark mode
# it can inherit a near-black background with no matching text color change
# (invisible black-on-black text). Style tooltips with DeckForge's own light
# card palette so they're never dependent on OS theme rendering.
_TOOLTIP_STYLE = f"""
QToolTip {{
    background: {BG_CARD};
    color: {TEXT_HEADING};
    border: 1px solid {BORDER_CARD};
    padding: 4px 8px;
}}
"""


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("DeckForge")
    app.setStyleSheet(_TOOLTIP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
