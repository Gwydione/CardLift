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
from .profile import DeckProfile, GridGeometry


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
    # How much extra zoom --inspect renders at, relative to the profile's
    # own render_scale, and how many points of surrounding page content it
    # leaves visible around the card.
    INSPECT_SCALE_MULTIPLIER = 3
    INSPECT_MARGIN_PT = 24.0

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

    # -- shared helpers ---------------------------------------------------

    def _geometry_for_page(self, page_num: int) -> GridGeometry:
        """The grid geometry that applies to a given 1-indexed page: the
        back grid for back_page, otherwise the front grid."""
        if page_num == self.profile.back_page:
            return self.profile.back_geometry()
        return self.profile.front_geometry()

    def _card_number_for(self, page_num: int, row: int, col: int) -> Optional[int]:
        """The global card number (matching front_NNN.png numbering) for
        (page_num, row, col), or None if page_num isn't a front page."""
        p = self.profile
        if not (p.first_front_page <= page_num <= p.last_front_page):
            return None
        page_offset = page_num - p.first_front_page
        return page_offset * p.rows * p.cols + row * p.cols + col + 1

    def _locate_card(self, card_number: int) -> tuple[int, int, int]:
        """Maps a 1-indexed front card number to (page_num, row, col)."""
        p = self.profile
        per_page = p.rows * p.cols
        total_pages = p.last_front_page - p.first_front_page + 1
        total_cards = per_page * total_pages
        if card_number < 1 or card_number > total_cards:
            raise ExportError(
                f"card {card_number} is out of range -- profile '{p.name}' "
                f"has {total_cards} front cards (pages {p.first_front_page}-"
                f"{p.last_front_page}, {p.rows}x{p.cols} grid per page)"
            )
        page_offset, local_index = divmod(card_number - 1, per_page)
        row, col = divmod(local_index, p.cols)
        return p.first_front_page + page_offset, row, col

    def _overlay_image(self, page_image: Image.Image, geometry: GridGeometry, page_num: int) -> Image.Image:
        return self.cropper.draw_calibration_overlay(
            page_image, geometry,
            card_number_fn=lambda row, col: self._card_number_for(page_num, row, col),
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

            overlay = self._overlay_image(page_image, geometry, page_num)
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

    # -- overlay ------------------------------------------------------

    def overlay(self, page_num: Optional[int] = None) -> Path:
        """Renders one page (default: first_front_page) with every crop
        rectangle drawn over it, labeled by row/col and card number, and
        writes it to preview/calibration_overlay.png. `page_num` can be
        any page in the profile, including back_page, to check its grid
        instead."""
        self.paths.ensure_dirs()
        if page_num is None:
            page_num = self.profile.first_front_page
        geometry = self._geometry_for_page(page_num)

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, self.profile.render_scale)
            overlay_img = self._overlay_image(page_image, geometry, page_num)

        overlay_path = self.paths.preview_dir / "calibration_overlay.png"
        overlay_img.save(overlay_path)
        return overlay_path

    # -- inspect ------------------------------------------------------

    def inspect(self, card_number: int) -> Path:
        """Exports a high-zoom inspection image of one front card (1-
        indexed, matching front_NNN.png numbering) to preview/, with the
        cell and trimmed-crop boundaries drawn and a margin of surrounding
        page content left visible."""
        self.paths.ensure_dirs()
        page_num, row, col = self._locate_card(card_number)
        geometry = self.profile.front_geometry()
        inspect_scale = self.profile.render_scale * self.INSPECT_SCALE_MULTIPLIER

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, inspect_scale)

        inspect_img = self.cropper.crop_inspect(
            page_image, geometry, row, col,
            scale=inspect_scale, margin_pt=self.INSPECT_MARGIN_PT,
        )
        inspect_path = self.paths.preview_dir / f"inspect_card{card_number:03d}.png"
        inspect_img.save(inspect_path)
        return inspect_path

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
