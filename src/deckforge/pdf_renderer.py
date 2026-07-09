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

    def render_page(self, page_number: int, scale: float) -> Image.Image:
        page_index = page_number - 1
        if page_index < 0 or page_index >= self._doc.page_count:
            raise PDFRenderError(
                f"page {page_number} is out of range for {self._path.name} "
                f"(it has {self._doc.page_count} pages)"
            )
        page = self._doc.load_page(page_index)
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> "PDFRenderer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
