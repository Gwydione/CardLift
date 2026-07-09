"""
cropper.py - crops individual card images out of a rendered page.

Separated from pdf_renderer.py (which only rasterizes pages) and from
geometry.py (which only computes boxes), so this module's one job is:
given a rendered page image and a profile, produce PIL Images for each
card cell.
"""

from __future__ import annotations

from typing import Iterator

from PIL import Image, ImageDraw

from .geometry import Box, cell_box, iter_grid_positions, trimmed_box
from .profile import DeckProfile, GridGeometry


class CardCropper:
    def __init__(self, profile: DeckProfile):
        self._profile = profile

    def trimmed_box_for(self, geometry: GridGeometry, row: int, col: int) -> Box:
        p = self._profile
        return trimmed_box(
            geometry, row, col,
            trim_left=p.trim_left, trim_top=p.trim_top,
            trim_right=p.trim_right, trim_bottom=p.trim_bottom,
        )

    def _card_pixel_size(self, geometry: GridGeometry) -> tuple[int, int]:
        """The fixed output size (in pixels) every card crop from this
        geometry must have, rounded once so all cards match exactly."""
        p = self._profile
        width_pt = geometry.card_width - p.trim_left - p.trim_right
        height_pt = geometry.card_height - p.trim_top - p.trim_bottom
        return round(width_pt * p.render_scale), round(height_pt * p.render_scale)

    def crop_card(self, page_image: Image.Image, geometry: GridGeometry, row: int, col: int) -> Image.Image:
        box = self.trimmed_box_for(geometry, row, col)
        width_px, height_px = self._card_pixel_size(geometry)
        box_px = box.to_pixels_fixed_size(self._profile.render_scale, width_px, height_px)
        return page_image.crop(box_px)

    def crop_all(self, page_image: Image.Image, geometry: GridGeometry) -> Iterator[tuple[int, int, Image.Image]]:
        """Yields (row, col, cropped_image) for every cell in reading order."""
        p = self._profile
        for row, col in iter_grid_positions(p.rows, p.cols):
            yield row, col, self.crop_card(page_image, geometry, row, col)

    def draw_calibration_overlay(self, page_image: Image.Image, geometry: GridGeometry) -> Image.Image:
        """Draws the raw cell (blue) and the trimmed/saved crop (red) for
        every card onto a copy of the page image, for visual calibration."""
        p = self._profile
        overlay = page_image.copy()
        draw = ImageDraw.Draw(overlay)
        scale = p.render_scale

        for row, col in iter_grid_positions(p.rows, p.cols):
            cell = cell_box(geometry, row, col)
            trimmed = self.trimmed_box_for(geometry, row, col)

            draw.rectangle(cell.to_pixels(scale), outline=(0, 100, 255), width=3)
            draw.rectangle(trimmed.to_pixels(scale), outline=(255, 0, 0), width=3)
            cell_px = cell.to_pixels(scale)
            draw.text((cell_px[0] + 6, cell_px[1] + 6), f"r{row}c{col}", fill=(0, 100, 255))

        return overlay
