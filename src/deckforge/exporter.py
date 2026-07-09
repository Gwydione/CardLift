"""
exporter.py - orchestrates preview / export / contact-sheet, wiring
together PDFRenderer, CardCropper, and build_contact_sheet.

This is the layer extract.py's CLI calls into. Keeping orchestration here
(rather than in cli.py) means the same operations could be driven by a
future GUI or test suite without going through argparse at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from .contact_sheet import build_contact_sheet
from .cropper import CardCropper
from .pdf_renderer import PDFRenderer
from .profile import DeckProfile


@dataclass
class DeckForgePaths:
    project_root: Path
    profiles_dir: Path
    sample_decks_dir: Path
    output_dir: Path
    preview_dir: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "DeckForgePaths":
        return cls(
            project_root=project_root,
            profiles_dir=project_root / "profiles",
            sample_decks_dir=project_root / "sample_decks",
            output_dir=project_root / "output",
            preview_dir=project_root / "preview",
        )

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(exist_ok=True)
        self.preview_dir.mkdir(exist_ok=True)


class ExportError(Exception):
    pass


class DeckExporter:
    def __init__(self, profile: DeckProfile, paths: DeckForgePaths):
        self.profile = profile
        self.paths = paths
        self.cropper = CardCropper(profile)

    def _find_pdf(self) -> Path:
        if not self.profile.pdf_file:
            raise ExportError(
                f"profile '{self.profile.name}' has no 'pdf_file' set, so "
                f"DeckForge doesn't know which PDF to open. Add a "
                f'"pdf_file": "your-deck.pdf" entry to the profile.'
            )
        candidate = self.paths.sample_decks_dir / self.profile.pdf_file
        if candidate.exists():
            return candidate
        candidate = self.paths.project_root / self.profile.pdf_file
        if candidate.exists():
            return candidate
        raise ExportError(
            f"could not find '{self.profile.pdf_file}'. Place it in "
            f"{self.paths.sample_decks_dir} (or the project root)."
        )

    # -- preview ------------------------------------------------------

    def preview(self) -> list[Path]:
        """Renders only first_front_page, crops its cards, and writes a
        calibration overlay + a page2-style preview contact sheet to
        preview/. Returns the list of files written."""
        self.paths.ensure_dirs()
        written: list[Path] = []

        with PDFRenderer(self._find_pdf()) as renderer:
            page_num = self.profile.first_front_page
            page_image = renderer.render_page(page_num, self.profile.render_scale)
            geometry = self.profile.front_geometry()

            overlay = self.cropper.draw_calibration_overlay(page_image, geometry)
            overlay_path = self.paths.preview_dir / "calibration_overlay.png"
            overlay.save(overlay_path)
            written.append(overlay_path)

            cards, labels = [], []
            for row, col, card_img in self.cropper.crop_all(page_image, geometry):
                cards.append(card_img)
                labels.append(f"r{row}c{col}")

            sheet = build_contact_sheet(cards, labels)
            sheet_path = self.paths.preview_dir / f"page{page_num}_preview.png"
            sheet.save(sheet_path)
            written.append(sheet_path)

        return written

    # -- export ---------------------------------------------------------

    def export(self) -> list[Path]:
        """Exports every front card (front_001.png, front_002.png, ...)
        and back.png to output/. Returns the list of files written."""
        self.paths.ensure_dirs()
        written: list[Path] = []
        expected_size: Optional[tuple[int, int]] = None

        with PDFRenderer(self._find_pdf()) as renderer:
            front_geometry = self.profile.front_geometry()
            card_index = 0
            for page_num in range(self.profile.first_front_page, self.profile.last_front_page + 1):
                page_image = renderer.render_page(page_num, self.profile.render_scale)
                for row, col, card_img in self.cropper.crop_all(page_image, front_geometry):
                    card_index += 1
                    if expected_size is None:
                        expected_size = card_img.size
                    elif card_img.size != expected_size:
                        raise ExportError(
                            f"card {card_index} (page {page_num}, r{row}c{col}) has "
                            f"size {card_img.size}, expected {expected_size}. All "
                            f"front cards must be identical dimensions."
                        )
                    out_path = self.paths.output_dir / f"front_{card_index:03d}.png"
                    card_img.save(out_path)
                    written.append(out_path)

            back_geometry = self.profile.back_geometry()
            back_page_image = renderer.render_page(self.profile.back_page, self.profile.render_scale)
            back_img = self.cropper.crop_card(back_page_image, back_geometry, 0, 0)
            back_path = self.paths.output_dir / "back.png"
            back_img.save(back_path)
            written.append(back_path)

        return written

    # -- contact sheet ---------------------------------------------------

    def contact_sheet(self) -> Path:
        """Builds a QA contact sheet from everything currently in
        output/ (front_*.png in order, then back.png)."""
        front_paths = sorted(self.paths.output_dir.glob("front_*.png"))
        back_path = self.paths.output_dir / "back.png"

        if not front_paths:
            raise ExportError("no exported cards found in output/. Run --export first.")

        images = [Image.open(p) for p in front_paths]
        labels = [p.stem.replace("front_", "") for p in front_paths]

        if back_path.exists():
            images.append(Image.open(back_path))
            labels.append("back")

        sheet = build_contact_sheet(images, labels)
        sheet_path = self.paths.preview_dir / "contact_sheet.png"
        sheet.save(sheet_path)
        return sheet_path
