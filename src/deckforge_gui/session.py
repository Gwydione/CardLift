"""Deck session -- the PDF the user has loaded.

Deliberately free of any PySide6 import, same rationale as app_state.py:
this is the controller/session layer the GUI reads from, kept separate
from widget code and testable without opening a window. It reuses the
engine's PDFRenderer (open + page_count) rather than re-implementing PDF
validation -- this module's only job is translating that into a friendly
DeckLoadError at the GUI boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deckforge.pdf_renderer import PDFRenderError, PDFRenderer


class DeckLoadError(Exception):
    """Raised when a chosen file can't be used as a deck PDF."""


@dataclass
class DeckSession:
    pdf_path: Path | None = None
    page_count: int = 0

    @property
    def is_loaded(self) -> bool:
        return self.pdf_path is not None

    @property
    def filename(self) -> str:
        return self.pdf_path.name if self.pdf_path else ""

    def load_pdf(self, path: Path) -> None:
        """Validate and load a candidate PDF, or raise DeckLoadError.

        Leaves the session untouched on failure -- a rejected file never
        clears an already-loaded deck.
        """
        if path.suffix.lower() != ".pdf":
            raise DeckLoadError(
                f"'{path.name}' doesn't look like a PDF. Choose a .pdf file to continue."
            )
        try:
            with PDFRenderer(path) as renderer:
                page_count = renderer.page_count
        except PDFRenderError as exc:
            raise DeckLoadError(str(exc)) from exc
        except Exception as exc:
            raise DeckLoadError(
                f"CardLift couldn't open '{path.name}'. It may be corrupted or not a valid PDF."
            ) from exc

        self.pdf_path = path
        self.page_count = page_count

    def unload(self) -> None:
        """Clears the loaded PDF without replacing it with another one --
        used when a session (the Demo Deck) explicitly ends rather than
        being superseded by the next load_pdf() call."""
        self.pdf_path = None
        self.page_count = 0
