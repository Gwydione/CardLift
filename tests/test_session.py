from pathlib import Path

import pytest

from deckforge_gui.session import DeckLoadError, DeckSession

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "CardLift_Demo_Deck.pdf"


def test_not_loaded_by_default():
    session = DeckSession()
    assert not session.is_loaded
    assert session.filename == ""
    assert session.page_count == 0


def test_load_valid_pdf_sets_filename_and_page_count():
    session = DeckSession()
    session.load_pdf(SAMPLE_PDF)
    assert session.is_loaded
    assert session.filename == "CardLift_Demo_Deck.pdf"
    assert session.page_count == 3


def test_rejects_non_pdf_extension(tmp_path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello")
    session = DeckSession()
    with pytest.raises(DeckLoadError):
        session.load_pdf(bogus)
    assert not session.is_loaded


def test_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.pdf"
    session = DeckSession()
    with pytest.raises(DeckLoadError):
        session.load_pdf(missing)
    assert not session.is_loaded


def test_rejects_corrupt_pdf(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"not a real pdf")
    session = DeckSession()
    with pytest.raises(DeckLoadError):
        session.load_pdf(fake)
    assert not session.is_loaded


def test_rejected_file_does_not_clear_a_previously_loaded_deck(tmp_path):
    session = DeckSession()
    session.load_pdf(SAMPLE_PDF)
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello")
    with pytest.raises(DeckLoadError):
        session.load_pdf(bogus)
    assert session.is_loaded
    assert session.filename == "CardLift_Demo_Deck.pdf"
