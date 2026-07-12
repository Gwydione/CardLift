from pathlib import Path

import pytest

from deckforge.pdf_renderer import PDFRenderError, PDFRenderer

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "Solo-cards-digital.pdf"


def test_page_size_matches_the_actual_page():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        width_pt, height_pt = renderer.page_size(2)
    assert width_pt == pytest.approx(595.276, abs=0.01)
    assert height_pt == pytest.approx(841.89, abs=0.01)


def test_page_size_is_consistent_across_pages_for_this_deck():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        assert renderer.page_size(2) == renderer.page_size(8)


def test_page_size_out_of_range_raises():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        with pytest.raises(PDFRenderError):
            renderer.page_size(99)


def test_page_size_reflects_rotation(tmp_path):
    import fitz

    rotated_pdf = tmp_path / "rotated.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=400).set_rotation(90)
    doc.save(rotated_pdf)
    doc.close()

    with PDFRenderer(rotated_pdf) as renderer:
        width_pt, height_pt = renderer.page_size(1)
    assert (width_pt, height_pt) == (400.0, 200.0)
