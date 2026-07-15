"""Crash/diagnostic logging for the desktop app.

Configured once, at the very top of gui_app.main(), before MainWindow is
constructed. Local file only -- no network calls -- per
ENGINEERING_STANDARDS.md's privacy section. Windows-only path lookup since
that's the only platform this app currently targets.

PDF filenames and export destination folder names are logged at INFO with
just their name (not full path), since a full path can embed unrelated
personal info (e.g. other folder names in the tree).

Exception content is logged as-is, unredacted, for this alpha: both
uncaught-exception tracebacks (frame filenames include the full install
path) and caught-exception messages logged via _logger.exception/.warning
(e.g. OSError's str() includes the failing filename in full). On most
Windows setups the install path embeds the tester's Windows username (e.g.
C:\\Users\\<username>\\...). Review deckforge.log before sharing it publicly
(bug reports, forums, etc.) and strip that path segment if needed.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from deckforge import __version__

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_directory() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "DeckForge" / "logs"


def configure_logging() -> None:
    log_dir = log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "deckforge.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    logging.getLogger(__name__).info(
        "DeckForge v%s starting (%s, Python %s)",
        __version__, platform.platform(), platform.python_version(),
    )

    # Falls through to whatever hook was previously installed (the default
    # one prints to stderr) so nothing currently visible in a dev console
    # regresses -- this only adds the log file as an additional sink.
    previous_hook = sys.excepthook

    def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
        logging.getLogger(__name__).critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb),
        )
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _log_uncaught
