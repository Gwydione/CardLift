import pytest

from deckforge.geometry import Box, GeometryError, cell_box, iter_grid_positions, trimmed_box
from deckforge.profile import GridGeometry


@pytest.fixture
def geometry() -> GridGeometry:
    return GridGeometry(
        left=10.0,
        top=20.0,
        card_width=100.0,
        card_height=150.0,
        gap_x=5.0,
        gap_y=8.0,
    )


class TestCellBox:
    def test_origin_cell(self, geometry: GridGeometry) -> None:
        box = cell_box(geometry, row=0, col=0)
        assert box == Box(x0=10.0, y0=20.0, x1=110.0, y1=170.0)

    def test_offset_cell_advances_by_card_size_plus_gap(self, geometry: GridGeometry) -> None:
        box = cell_box(geometry, row=1, col=2)
        assert box == Box(
            x0=10.0 + 2 * (100.0 + 5.0),
            y0=20.0 + 1 * (150.0 + 8.0),
            x1=10.0 + 2 * (100.0 + 5.0) + 100.0,
            y1=20.0 + 1 * (150.0 + 8.0) + 150.0,
        )

    def test_zero_gap_cells_are_edge_to_edge(self) -> None:
        edge_to_edge = GridGeometry(
            left=0.0, top=0.0, card_width=50.0, card_height=50.0, gap_x=0.0, gap_y=0.0,
        )
        first = cell_box(edge_to_edge, row=0, col=0)
        second = cell_box(edge_to_edge, row=0, col=1)
        assert second.x0 == first.x1


class TestTrimmedBox:
    def test_trim_shrinks_box_inward_from_each_side(self, geometry: GridGeometry) -> None:
        box = trimmed_box(geometry, row=0, col=0, trim_left=1, trim_top=2, trim_right=3, trim_bottom=4)
        assert box == Box(x0=11.0, y0=22.0, x1=107.0, y1=166.0)

    def test_zero_trim_matches_cell_box(self, geometry: GridGeometry) -> None:
        trimmed = trimmed_box(geometry, row=0, col=0, trim_left=0, trim_top=0, trim_right=0, trim_bottom=0)
        assert trimmed == cell_box(geometry, row=0, col=0)

    def test_trim_collapsing_width_raises(self, geometry: GridGeometry) -> None:
        with pytest.raises(GeometryError):
            trimmed_box(geometry, row=0, col=0, trim_left=60, trim_top=0, trim_right=60, trim_bottom=0)

    def test_trim_collapsing_height_raises(self, geometry: GridGeometry) -> None:
        with pytest.raises(GeometryError):
            trimmed_box(geometry, row=0, col=0, trim_left=0, trim_top=100, trim_right=0, trim_bottom=100)

    def test_error_message_names_the_offending_cell(self, geometry: GridGeometry) -> None:
        with pytest.raises(GeometryError, match=r"row=1, col=2"):
            trimmed_box(geometry, row=1, col=2, trim_left=0, trim_top=0, trim_right=200, trim_bottom=0)


class TestBoxPixelConversion:
    def test_to_pixels_scales_and_rounds(self) -> None:
        box = Box(x0=1.1, y0=2.4, x1=10.6, y1=20.5)
        assert box.to_pixels(scale=2.0) == (2, 5, 21, 41)

    def test_to_pixels_fixed_size_forces_exact_dimensions(self) -> None:
        # x0 and x1 fall on opposite sides of a rounding boundary at this
        # scale; to_pixels() alone would round them independently and
        # produce a card 1px narrower than a neighbor with the same width.
        box = Box(x0=10.335, y0=0.0, x1=10.335 + 43.7, y1=50.0)
        width_px = round(43.7 * 4)
        height_px = round(50.0 * 4)
        x0, y0, x1, y1 = box.to_pixels_fixed_size(scale=4.0, width_px=width_px, height_px=height_px)
        assert (x1 - x0, y1 - y0) == (width_px, height_px)

    def test_to_pixels_fixed_size_reuses_size_for_every_card(self, geometry: GridGeometry) -> None:
        width_px = round(geometry.card_width * 3)
        height_px = round(geometry.card_height * 3)
        sizes = set()
        for row, col in iter_grid_positions(rows=2, cols=3):
            box = cell_box(geometry, row, col)
            x0, y0, x1, y1 = box.to_pixels_fixed_size(scale=3.0, width_px=width_px, height_px=height_px)
            sizes.add((x1 - x0, y1 - y0))
        assert sizes == {(width_px, height_px)}


class TestIterGridPositions:
    def test_reading_order(self) -> None:
        assert list(iter_grid_positions(rows=2, cols=3)) == [
            (0, 0), (0, 1), (0, 2),
            (1, 0), (1, 1), (1, 2),
        ]

    def test_empty_grid(self) -> None:
        assert list(iter_grid_positions(rows=0, cols=0)) == []
