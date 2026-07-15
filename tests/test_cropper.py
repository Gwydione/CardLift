from PIL import Image

from deckforge.cropper import CardCropper
from deckforge.profile import GridGeometry, TrimValues

_ZERO_TRIM = TrimValues(0.0, 0.0, 0.0, 0.0)


def make_geometry(**overrides) -> GridGeometry:
    data = dict(left=10.0, top=20.0, card_width=100.0, card_height=150.0, gap_x=5.0, gap_y=8.0)
    data.update(overrides)
    return GridGeometry(**data)


class TestCropCardWithMargin:
    def test_region_includes_margin_on_every_side(self) -> None:
        geometry = make_geometry()
        page_image = Image.new("RGB", (1000, 1000), (0, 0, 0))
        cropper = CardCropper(render_scale=1.0)

        region, card_rect = cropper.crop_card_with_margin(page_image, geometry, _ZERO_TRIM, 0, 0, margin_pt=10.0)

        # Card box at scale 1.0 is (10, 20, 110, 170); with a 10pt margin
        # the region should be (0, 10, 120, 180) -- 10px larger on every side.
        assert region.size == (120, 170)
        assert card_rect == (10, 10, 110, 160)

    def test_margin_is_clamped_to_page_bounds(self) -> None:
        geometry = make_geometry(left=0.0, top=0.0)
        page_image = Image.new("RGB", (105, 155), (0, 0, 0))
        cropper = CardCropper(render_scale=1.0)

        region, card_rect = cropper.crop_card_with_margin(page_image, geometry, _ZERO_TRIM, 0, 0, margin_pt=10.0)

        # Card box is (0, 0, 100, 150); margin would go negative/past the
        # page on every side, so the region clamps to the page itself.
        assert region.size == (105, 155)
        assert card_rect == (0, 0, 100, 150)

    def test_render_scale_is_applied_to_both_card_and_margin(self) -> None:
        geometry = make_geometry(left=20.0, top=20.0, card_width=10.0, card_height=10.0, gap_x=0.0, gap_y=0.0)
        page_image = Image.new("RGB", (1000, 1000), (0, 0, 0))
        cropper = CardCropper(render_scale=2.0)

        region, card_rect = cropper.crop_card_with_margin(page_image, geometry, _ZERO_TRIM, 0, 0, margin_pt=5.0)

        # Card box at scale 2.0 is (40, 40, 60, 60); margin_pt=5 -> 10px,
        # well clear of the page edge, so nothing gets clamped.
        assert region.size == (40, 40)
        assert card_rect == (10, 10, 30, 30)

    def test_different_cells_crop_different_page_content(self) -> None:
        # A card_rect's position *within* its own cropped region is the
        # same for every unclamped cell (margin_px on every side) -- what
        # must differ is which part of the page each region actually came
        # from. Paint each cell a distinct color and confirm the returned
        # region's center pixel matches.
        geometry = make_geometry(gap_x=0.0, gap_y=0.0)
        page_image = Image.new("RGB", (1000, 1000), (255, 255, 255))
        for row, col, color in [(0, 0, (255, 0, 0)), (0, 1, (0, 255, 0))]:
            x0 = round(geometry.left + col * geometry.card_width)
            y0 = round(geometry.top + row * geometry.card_height)
            page_image.paste(color, (x0, y0, x0 + round(geometry.card_width), y0 + round(geometry.card_height)))
        cropper = CardCropper(render_scale=1.0)

        first_region, first_rect = cropper.crop_card_with_margin(page_image, geometry, _ZERO_TRIM, 0, 0, margin_pt=1.0)
        second_region, second_rect = cropper.crop_card_with_margin(page_image, geometry, _ZERO_TRIM, 0, 1, margin_pt=1.0)

        first_center = first_region.getpixel((first_rect[0] + 5, first_rect[1] + 5))
        second_center = second_region.getpixel((second_rect[0] + 5, second_rect[1] + 5))
        assert first_center == (255, 0, 0)
        assert second_center == (0, 255, 0)
