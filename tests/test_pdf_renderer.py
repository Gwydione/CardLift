from pathlib import Path

import pytest

from deckforge.pdf_renderer import PDFRenderError, PDFRenderer

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "CardLift_Demo_Deck.pdf"


def test_page_size_matches_the_actual_page():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        width_pt, height_pt = renderer.page_size(1)
    assert width_pt == pytest.approx(612.0, abs=0.01)
    assert height_pt == pytest.approx(792.0, abs=0.01)


def test_page_size_is_consistent_across_pages_for_this_deck():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        assert renderer.page_size(1) == renderer.page_size(3)


def test_page_size_out_of_range_raises():
    with PDFRenderer(SAMPLE_PDF) as renderer:
        with pytest.raises(PDFRenderError):
            renderer.page_size(99)


def test_missing_pdf_error_names_the_file_not_its_full_path(tmp_path):
    # Regression test for a privacy leak: this message is logged verbatim
    # by deckforge_gui (main_window.py, via DeckLoadError), whose stated
    # policy is to log filenames, never full paths -- a full tmp_path
    # here stands in for a real absolute path that could embed personal
    # folder names.
    missing = tmp_path / "some_users_private_folder" / "deck.pdf"

    with pytest.raises(PDFRenderError) as excinfo:
        PDFRenderer(missing)

    assert "deck.pdf" in str(excinfo.value)
    assert "some_users_private_folder" not in str(excinfo.value)
    assert str(missing) not in str(excinfo.value)


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
