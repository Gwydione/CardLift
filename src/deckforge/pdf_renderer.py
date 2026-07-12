"""
pdf_renderer.py - turns PDF pages into Pillow images.

This is the ONLY module that touches PyMuPDF (fitz). Keeping PDF I/O
isolated here means everything downstream (geometry, cropping, contact
sheets) works purely with Pillow images and point/pixel numbers, and
could be reused unchanged if DeckForge ever swaps rendering backends.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


class PDFRenderError(Exception):
    """Raised for missing files or out-of-range page numbers."""


class PDFRenderer:
    """Renders pages of a single PDF file to Pillow images at a given
    points-to-pixels scale. Page numbers here are 1-indexed, matching how
    humans count PDF pages (and how profiles express first_front_page /
    last_front_page / back_page)."""

    def __init__(self, pdf_path: Path):
        if not pdf_path.exists():
            raise PDFRenderError(f"PDF not found: {pdf_path}")
        self._path = pdf_path
        self._doc = fitz.open(pdf_path)

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def _load_page_checked(self, page_number: int):
        page_index = page_number - 1
        if page_index < 0 or page_index >= self._doc.page_count:
            raise PDFRenderError(
                f"page {page_number} is out of range for {self._path.name} "
                f"(it has {self._doc.page_count} pages)"
            )
        return self._doc.load_page(page_index)

    def render_page(self, page_number: int, scale: float) -> Image.Image:
        page = self._load_page_checked(page_number)
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    def page_size(self, page_number: int) -> tuple[float, float]:
        """(width_pt, height_pt) of one page -- e.g. for grid-fit math that
        needs the page's own dimensions alongside a calibrated card size.
        `page.rect` already reflects the page's /Rotate entry, so a
        rotated page reports its displayed (not raw MediaBox) extent."""
        page = self._load_page_checked(page_number)
        return (page.rect.width, page.rect.height)

    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> "PDFRenderer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
