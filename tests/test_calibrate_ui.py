import pytest

from deckforge.calibrate_ui import (
    build_result_text,
    display_scale,
    infer_second_cell,
    normalize_box,
    parse_cell_label,
    predicted_neighbor_box,
)
from deckforge.measure import BACK_FIELDS, FRONT_FIELDS, CardMeasurement, MeasureError, PixelBox


class TestDisplayScale:
    def test_image_larger_than_max_is_shrunk(self) -> None:
        assert display_scale(2600, 3400, 1300, 850) == pytest.approx(0.25)

    def test_image_smaller_than_max_is_not_upscaled(self) -> None:
        assert display_scale(400, 300, 1300, 850) == 1.0

    def test_width_or_height_can_independently_bind(self) -> None:
        # width binds tighter than height
        assert display_scale(2600, 100, 1300, 850) == pytest.approx(0.5)


class TestNormalizeBox:
    def test_already_ordered_is_unchanged(self) -> None:
        assert normalize_box(10, 20, 110, 220) == (10, 20, 110, 220)

    def test_reversed_corners_are_reordered(self) -> None:
        assert normalize_box(110, 220, 10, 20) == (10, 20, 110, 220)

    def test_mixed_order_corners_are_reordered(self) -> None:
        # e.g. lower-left then upper-right
        assert normalize_box(10, 220, 110, 20) == (10, 20, 110, 220)


class TestParseCellLabel:
    def test_parses_row_col(self) -> None:
        assert parse_cell_label("r1c2") == (1, 2)

    def test_uppercase_accepted(self) -> None:
        assert parse_cell_label("R0C3") == (0, 3)

    def test_malformed_label_raises(self) -> None:
        with pytest.raises(MeasureError, match="rNcN"):
            parse_cell_label("row1col2")


class TestPredictedNeighborBox:
    def test_right_neighbor_is_offset_by_width_plus_gap(self) -> None:
        box = predicted_neighbor_box(
            PixelBox(100, 200, 300, 500), card_width=200, card_height=300,
            gap_x=20, gap_y=10, direction="right",
        )
        assert box == PixelBox(320, 200, 520, 500)

    def test_below_neighbor_is_offset_by_height_plus_gap(self) -> None:
        box = predicted_neighbor_box(
            PixelBox(100, 200, 300, 500), card_width=200, card_height=300,
            gap_x=20, gap_y=10, direction="below",
        )
        assert box == PixelBox(100, 510, 300, 810)

    def test_invalid_direction_raises(self) -> None:
        with pytest.raises(ValueError):
            predicted_neighbor_box(
                PixelBox(0, 0, 10, 10), card_width=10, card_height=10,
                gap_x=0, gap_y=0, direction="up",
            )


class TestInferSecondCell:
    def test_card_to_the_right_is_next_column_same_row(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(220, 0, 420, 300)  # one cell-width+gap to the right
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (0, 1)

    def test_card_below_is_next_row_same_column(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(0, 310, 200, 610)  # one cell-height+gap down
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (1, 0)

    def test_two_cells_over_is_recognized(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(440, 0, 640, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (0, 2)

    def test_overlapping_click_returns_none(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(5, 5, 205, 305)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) is None

    def test_zero_cell_size_returns_none(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(220, 0, 420, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=0, cell_height=310) is None


class TestBuildResultText:
    def test_includes_patch_and_no_mutation_notice(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        current = dict(zip(FRONT_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = build_result_text(
            profile_name="solo_cards", page_num=1, is_back=False,
            measurements=[m], current=current, field_names=FRONT_FIELDS,
            scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
        )
        assert "Measured 1 card(s)" in text
        assert '"card_width": 0.000 -> 100.000' in text
        assert "was NOT modified" in text

    def test_uses_back_field_names(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        current = dict(zip(BACK_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = build_result_text(
            profile_name="solo_cards", page_num=5, is_back=True,
            measurements=[m], current=current, field_names=BACK_FIELDS,
            scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
        )
        assert '"back_card_width"' in text

    def test_raises_measure_error_for_no_measurements(self) -> None:
        with pytest.raises(MeasureError):
            build_result_text(
                profile_name="solo_cards", page_num=1, is_back=False,
                measurements=[], current={}, field_names=FRONT_FIELDS,
                scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
            )
