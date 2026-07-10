import json
from pathlib import Path

import pytest
from PIL import Image

from deckforge.cli import format_export_summary, friendly_error, main
from deckforge.exporter import ExportError
from deckforge.geometry import GeometryError
from deckforge.measure import MeasureError
from deckforge.pdf_renderer import PDFRenderError
from deckforge.profile import ProfileError


def write_profile(profiles_dir: Path, name: str, data: dict) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / f"{name}.json").write_text(json.dumps(data))


class TestFriendlyError:
    def test_profile_not_found_gets_plain_language_and_details(self) -> None:
        msg = friendly_error(ProfileError("profile 'x' not found at /a/b/x.json"))
        assert "can't find that profile" in msg
        assert "Next step:" in msg
        assert "Details: profile 'x' not found at /a/b/x.json" in msg

    def test_invalid_json_gets_plain_language(self) -> None:
        msg = friendly_error(ProfileError("profile 'x' is not valid JSON: Expecting ',' delimiter"))
        assert "isn't valid JSON" in msg
        assert "Details:" in msg

    def test_missing_keys_gets_plain_language(self) -> None:
        msg = friendly_error(ProfileError("profile 'x' is missing required keys: ['card_width']"))
        assert "missing information" in msg

    def test_pdf_not_found_gets_plain_language(self) -> None:
        msg = friendly_error(PDFRenderError("PDF not found: /a/deck.pdf"))
        assert "can't find the source PDF" in msg

    def test_page_out_of_range_gets_plain_language(self) -> None:
        msg = friendly_error(PDFRenderError("page 99 is out of range for deck.pdf (it has 8 pages)"))
        assert "doesn't exist in this PDF" in msg

    def test_geometry_error_gets_plain_language(self) -> None:
        msg = friendly_error(GeometryError("trim values collapse card (row=0, col=0) to a zero/negative size box"))
        assert "leave nothing to crop" in msg

    def test_measure_error_gets_plain_language(self) -> None:
        msg = friendly_error(MeasureError("--card 'bad' is missing the ':' separating..."))
        assert "couldn't understand" in msg

    def test_export_error_unknown_pdf_file_gets_plain_language(self) -> None:
        msg = friendly_error(ExportError("profile 'x' has no 'pdf_file' set, so DeckForge doesn't know which PDF to open."))
        assert "doesn't say which PDF" in msg

    def test_unrecognized_exception_falls_back_gracefully(self) -> None:
        msg = friendly_error(ProfileError("some brand new message shape"))
        assert "Details: some brand new message shape" in msg


class TestFormatExportSummary:
    def test_reports_counts_location_and_next_step(self, tmp_path: Path) -> None:
        for i in range(1, 4):
            Image.new("RGB", (300, 400)).save(tmp_path / f"front_{i:03d}.png")
        Image.new("RGB", (300, 400)).save(tmp_path / "back.png")
        written = sorted(tmp_path.glob("front_*.png")) + [tmp_path / "back.png"]

        summary = format_export_summary(written, tmp_path)
        assert "3 card fronts" in summary
        assert "300x400px" in summary
        assert "1 back design" in summary
        assert str(tmp_path) in summary
        assert "PlayingCards.io" in summary
        assert "Tabletop Simulator" in summary
        assert "--contact-sheet" in summary

    def test_singular_card_wording(self, tmp_path: Path) -> None:
        Image.new("RGB", (10, 10)).save(tmp_path / "front_001.png")
        written = [tmp_path / "front_001.png"]
        summary = format_export_summary(written, tmp_path)
        assert "1 card front " in summary or "1 card front at" in summary
        assert "card fronts" not in summary


class TestMainEndToEnd:
    def test_missing_profile_exits_nonzero_with_friendly_hint(self, capsys) -> None:
        code = main(["--profile", "does_not_exist_xyz", "--preview"])
        assert code == 1
        err = capsys.readouterr().err
        assert "can't find that profile" in err
        assert "Next step:" in err
        assert "Details:" in err

    def test_missing_mode_flag_suggests_calibrate(self, capsys) -> None:
        with pytest.raises(SystemExit):
            main(["--profile", "does_not_exist_xyz"])
        err = capsys.readouterr().err
        assert "--calibrate" in err
        assert "New to DeckForge" in err
