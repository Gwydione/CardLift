"""Regression coverage for Demo Deck resource resolution
(deckforge_gui.main_window._resource_root / demo_deck_path()).

Traced in this session: the Demo Deck path used to be a module-level
constant computed once at import time via a source-checkout-only
Path(__file__) walk, which does not survive a PyInstaller frozen build
(sys.executable/__file__ semantics change, and bundled data in a
one-folder build commonly lives under PyInstaller's own bundle directory
-- e.g. _internal/ -- rather than beside the .exe). demo_deck_path() is
now a callable resolver, re-evaluated on every call, that checks
sys.frozen + sys._MEIPASS (set by PyInstaller's bootloader at runtime)
and falls back to the original repo-root walk otherwise -- so both modes
are testable here via monkeypatch, with no module reload required.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from deckforge_gui.main_window import MainWindow, _resource_root, demo_deck_path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = REPO_ROOT / "sample_decks" / "CardLift_Demo_Deck.pdf"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


class TestResourceRootSourceMode:
    def test_resolves_to_the_repo_root_when_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        assert _resource_root() == REPO_ROOT

    def test_demo_deck_path_points_at_the_real_bundled_pdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        assert demo_deck_path() == SAMPLE_PDF


class TestResourceRootFrozenMode:
    """Simulates PyInstaller's runtime bootloader attributes -- neither is
    ever set in normal source execution, so both must be monkeypatched."""

    def test_resolves_to_meipass_when_frozen(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert _resource_root() == tmp_path

    def test_demo_deck_path_is_meipass_relative_when_frozen(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert demo_deck_path() == tmp_path / "sample_decks" / "CardLift_Demo_Deck.pdf"

    def test_frozen_without_meipass_falls_back_to_source_resolution(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """sys.frozen could in principle be set without _MEIPASS (a
        non-PyInstaller freezer, or a bootloader detail changing) -- must
        not raise, must fall back to the repo-root walk rather than crash."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert _resource_root() == REPO_ROOT


class TestRealDemoDeckFileExists:
    def test_the_real_demo_deck_pdf_exists_in_source_checkout(self) -> None:
        assert SAMPLE_PDF.exists()


class TestOnDemoDeckRequestedSuccess:
    def test_loads_the_real_demo_deck_pdf(self, qapp: QApplication) -> None:
        window = MainWindow()
        window._on_demo_deck_requested()

        assert window.session.pdf_path == SAMPLE_PDF
        assert window.session.page_count > 0
        assert window._is_demo_session is True
        assert window.deck_workspace._error_label.isHidden() is True


class TestOnDemoDeckRequestedMissingFile:
    def test_shows_an_error_and_does_not_attempt_to_load_anything(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        missing_path = tmp_path / "CardLift_Demo_Deck.pdf"
        assert not missing_path.exists()
        monkeypatch.setattr(
            "deckforge_gui.main_window.demo_deck_path", lambda: missing_path,
        )

        window = MainWindow()
        window._on_demo_deck_requested()

        assert window.session.pdf_path is None, "a missing bundled file must never reach DeckSession.load_pdf()"
        assert window.deck_workspace._error_label.isHidden() is False
        assert "could not be found" in window.deck_workspace._error_label.text()
