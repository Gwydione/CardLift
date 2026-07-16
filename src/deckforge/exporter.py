"""
exporter.py - orchestrates preview / export / contact-sheet, wiring
together PDFRenderer, CardCropper, and build_contact_sheet.

This is the layer extract.py's CLI calls into. Keeping orchestration here
(rather than in cli.py) means the same operations could be driven by a
future GUI or test suite without going through argparse at all.

profile.layouts is the authoritative front-card representation: every
front-facing operation here (preview, export, overlay, inspect) walks
profile.layouts rather than any single flat geometry. resolve_page() is
the one place a page number is turned into "which layout, or the shared
back, or an unassigned-page error" -- --page, --overlay, --calibrate, and
--measure all go through it so that decision is made exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from .contact_sheet import build_contact_sheet
from .cropper import CardCropper
from .pdf_renderer import PDFRenderer
from .profile import CardLayout, DeckProfile, GridGeometry, TrimValues


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


@dataclass(frozen=True)
class PageResolution:
    """What a page number resolves to: either a front layout or the
    shared back, with the geometry/trim/grid-shape that applies to it and
    a human-readable label for calibration/measure output."""
    page_num: int
    is_back: bool
    layout: Optional[CardLayout]  # None when is_back
    geometry: GridGeometry
    trim: TrimValues
    rows: int
    cols: int
    label: str  # e.g. "front grid, page 3" or "front grid (Boss cards), page 8"


class DeckExporter:
    # How much extra zoom --inspect renders at, relative to the profile's
    # own render_scale, and how many points of surrounding page content it
    # leaves visible around the card.
    INSPECT_SCALE_MULTIPLIER = 3
    INSPECT_MARGIN_PT = 24.0

    def __init__(self, profile: DeckProfile, paths: DeckForgePaths):
        self.profile = profile
        self.paths = paths
        self.cropper = CardCropper(profile.render_scale)

    def _find_pdf(self) -> Path:
        if not self.profile.pdf_file:
            raise ExportError(
                f"profile '{self.profile.name}' has no 'pdf_file' set, so "
                f"CardLift doesn't know which PDF to open. Add a "
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

    # -- page/layout resolution --------------------------------------------

    def _layout_label(self, layout: CardLayout) -> str:
        """"front grid" for a single-layout profile (byte-identical to the
        pre-layouts wording); "front grid (name)" once a profile has more
        than one, so calibration/measure output can't be ambiguous about
        which layout is selected."""
        if len(self.profile.layouts) == 1:
            return "front grid"
        index = self.profile.layouts.index(layout)
        return f"front grid ({layout.display_name(index)})"

    def _assigned_pages_summary(self) -> str:
        ranges = [
            f"{l.first_page}" if l.first_page == l.last_page else f"{l.first_page}-{l.last_page}"
            for l in self.profile.layouts
        ]
        return ", ".join(ranges)

    def resolve_page(self, page_num: int) -> PageResolution:
        """Resolves a 1-indexed page number to the layout (or shared back)
        that applies to it. Raises ExportError with a friendly explanation
        if the page belongs to neither."""
        if page_num == self.profile.back_page:
            first_layout = self.profile.layouts[0]
            return PageResolution(
                page_num=page_num, is_back=True, layout=None,
                geometry=self.profile.back_geometry(), trim=self.profile.back_trim(),
                rows=first_layout.rows, cols=first_layout.cols,
                label=f"back grid, page {page_num}",
            )

        layout = self.profile.layout_for_page(page_num)
        if layout is None:
            raise ExportError(
                f"page {page_num} is not assigned to any layout or the shared "
                f"back page in profile '{self.profile.name}'. Assigned front "
                f"pages: {self._assigned_pages_summary()}; back page: "
                f"{self.profile.back_page}."
            )
        return PageResolution(
            page_num=page_num, is_back=False, layout=layout,
            geometry=layout.geometry(), trim=layout.trim(),
            rows=layout.rows, cols=layout.cols,
            label=f"{self._layout_label(layout)}, page {page_num}",
        )

    # -- continuous front-card numbering, across layouts in profile order --

    def _card_number_for(self, page_num: int, row: int, col: int) -> Optional[int]:
        """The global card number (matching front_NNN.png numbering) for
        (page_num, row, col), or None if page_num isn't a front page."""
        offset = 0
        for layout in self.profile.layouts:
            if layout.first_page <= page_num <= layout.last_page:
                page_offset = page_num - layout.first_page
                return offset + page_offset * layout.rows * layout.cols + row * layout.cols + col + 1
            offset += layout.card_count()
        return None

    def _locate_card(self, card_number: int) -> tuple[CardLayout, int, int, int]:
        """Maps a 1-indexed front card number to (layout, page_num, row, col)."""
        p = self.profile
        total_cards = sum(l.card_count() for l in p.layouts)
        if card_number < 1 or card_number > total_cards:
            raise ExportError(
                f"card {card_number} is out of range -- profile '{p.name}' "
                f"has {total_cards} front card(s) total across "
                f"{len(p.layouts)} layout(s)"
            )
        remaining = card_number
        for layout in p.layouts:
            per_page = layout.rows * layout.cols
            layout_total = layout.card_count()
            if remaining <= layout_total:
                page_offset, local_index = divmod(remaining - 1, per_page)
                row, col = divmod(local_index, layout.cols)
                return layout, layout.first_page + page_offset, row, col
            remaining -= layout_total
        raise ExportError(f"card {card_number} is out of range")  # unreachable

    def _overlay_image(self, page_image: Image.Image, resolution: PageResolution) -> Image.Image:
        return self.cropper.draw_calibration_overlay(
            page_image, resolution.geometry, resolution.trim, resolution.rows, resolution.cols,
            card_number_fn=lambda row, col: self._card_number_for(resolution.page_num, row, col),
        )

    # -- preview ------------------------------------------------------

    def preview(self) -> list[Path]:
        """Renders only the first page of the first layout, crops its
        cards, and writes a calibration overlay + a page2-style preview
        contact sheet to preview/. Returns the list of files written."""
        self.paths.ensure_dirs()
        written: list[Path] = []

        page_num = self.profile.layouts[0].first_page
        resolution = self.resolve_page(page_num)

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, self.profile.render_scale)

            overlay = self._overlay_image(page_image, resolution)
            overlay_path = self.paths.preview_dir / "calibration_overlay.png"
            overlay.save(overlay_path)
            written.append(overlay_path)

            cards, labels = [], []
            for row, col, card_img in self.cropper.crop_all(
                page_image, resolution.geometry, resolution.trim, resolution.rows, resolution.cols,
            ):
                cards.append(card_img)
                labels.append(f"r{row}c{col}")

            sheet = build_contact_sheet(cards, labels)
            sheet_path = self.paths.preview_dir / f"page{page_num}_preview.png"
            sheet.save(sheet_path)
            written.append(sheet_path)

        return written

    # -- overlay ------------------------------------------------------

    def overlay(self, page_num: Optional[int] = None) -> Path:
        """Renders one page (default: the first page of the first layout)
        with every crop rectangle drawn over it, labeled by row/col and
        card number, and writes it to preview/calibration_overlay.png.
        `page_num` can be any assigned front page or the shared back."""
        self.paths.ensure_dirs()
        if page_num is None:
            page_num = self.profile.layouts[0].first_page
        resolution = self.resolve_page(page_num)

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, self.profile.render_scale)
            overlay_img = self._overlay_image(page_image, resolution)

        overlay_path = self.paths.preview_dir / "calibration_overlay.png"
        overlay_img.save(overlay_path)
        return overlay_path

    # -- calibrate ------------------------------------------------------

    def render_calibration_page(self, page_num: Optional[int] = None) -> tuple[Image.Image, PageResolution]:
        """Renders one raw page (default: the first page of the first
        layout) at the profile's render_scale, for --calibrate to display
        and let the user click on. Unlike overlay(), no crop rectangles
        are drawn -- the calibration window draws its own from live
        clicks. Returns (page_image, resolution)."""
        if page_num is None:
            page_num = self.profile.layouts[0].first_page
        resolution = self.resolve_page(page_num)

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, self.profile.render_scale)

        return page_image, resolution

    # -- inspect ------------------------------------------------------

    def inspect(self, card_number: int) -> Path:
        """Exports a high-zoom inspection image of one front card (1-
        indexed, matching front_NNN.png numbering, continuous across
        layouts) to preview/, with the cell and trimmed-crop boundaries
        drawn and a margin of surrounding page content left visible."""
        self.paths.ensure_dirs()
        layout, page_num, row, col = self._locate_card(card_number)
        geometry = layout.geometry()
        trim = layout.trim()
        inspect_scale = self.profile.render_scale * self.INSPECT_SCALE_MULTIPLIER

        with PDFRenderer(self._find_pdf()) as renderer:
            page_image = renderer.render_page(page_num, inspect_scale)

        inspect_img = self.cropper.crop_inspect(
            page_image, geometry, trim, row, col,
            scale=inspect_scale, margin_pt=self.INSPECT_MARGIN_PT,
        )
        inspect_path = self.paths.preview_dir / f"inspect_card{card_number:03d}.png"
        inspect_img.save(inspect_path)
        return inspect_path

    # -- export ---------------------------------------------------------

    def export(self) -> list[Path]:
        """Exports every front card (front_001.png, front_002.png, ...,
        continuous across layouts in profile order) and back.png to
        output/. All cards within one layout must be identical pixel
        dimensions; different layouts may use different card sizes.
        Returns the list of files written."""
        self.paths.ensure_dirs()
        written: list[Path] = []

        with PDFRenderer(self._find_pdf()) as renderer:
            card_index = 0
            for layout in self.profile.layouts:
                geometry = layout.geometry()
                trim = layout.trim()
                expected_size: Optional[tuple[int, int]] = None

                for page_num in range(layout.first_page, layout.last_page + 1):
                    page_image = renderer.render_page(page_num, self.profile.render_scale)
                    for row, col, card_img in self.cropper.crop_all(page_image, geometry, trim, layout.rows, layout.cols):
                        card_index += 1
                        if expected_size is None:
                            expected_size = card_img.size
                        elif card_img.size != expected_size:
                            raise ExportError(
                                f"card {card_index} (page {page_num}, r{row}c{col}) in "
                                f"{self._layout_label(layout)} has size {card_img.size}, "
                                f"expected {expected_size}. All cards within one layout "
                                f"must be identical dimensions."
                            )
                        out_path = self.paths.output_dir / f"front_{card_index:03d}.png"
                        card_img.save(out_path)
                        written.append(out_path)

            back_geometry = self.profile.back_geometry()
            back_trim = self.profile.back_trim()
            back_page_image = renderer.render_page(self.profile.back_page, self.profile.render_scale)
            back_img = self.cropper.crop_card(back_page_image, back_geometry, back_trim, 0, 0)
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
