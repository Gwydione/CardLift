#!/usr/bin/env python3
"""
DeckForge - gui_app.py

Launches the desktop application shell (Phase II prototype). Thin entry
point, same pattern as extract.py -- all logic lives in src/deckforge_gui/.

    pip install -r requirements-gui.txt
    python gui_app.py

This milestone is the application frame only: sidebar, top bar, context
toolbar, workspace, guidance panel, and status bar, wired together and
resizable. It does not call the PDF/calibration engine yet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from deckforge_gui.logging_setup import configure_logging  # noqa: E402
from deckforge_gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("DeckForge")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
