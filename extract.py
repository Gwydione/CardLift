#!/usr/bin/env python3
"""
DeckForge - extract.py

Thin entry point. All logic lives in src/deckforge/. Run with:

    python extract.py --profile solo_cards --preview
    python extract.py --profile solo_cards --export
    python extract.py --profile solo_cards --contact-sheet

See README.md for setup, calibration workflow, and command details.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from deckforge.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
