import pytest

from deckforge.measure import (
    BACK_FIELDS,
    FRONT_FIELDS,
    CardMeasurement,
    MeasureError,
    PixelBox,
    derive_geometry,
    format_suggested_patch,
    parse_card_measurement,
)


class TestParseCardMeasurement:
    def test_parses_cell_and_box(self) -> None:
        m = parse_card_measurement("r0c1:1000,420,1720,1360")
        assert m == CardMeasurement(row=0, col=1, box=PixelBox(1000, 420, 1720, 1360))

    def test_uppercase_cell_is_accepted(self) -> None:
        m = parse_card_measurement("R2C3:0,0,10,10")
        assert (m.row, m.col) == (2, 3)

    def test_missing_colon_raises(self) -> None:
        with pytest.raises(MeasureError, match="missing the ':'"):
            parse_card_measurement("r0c0 240,420,960,1360")

    def test_malformed_cell_raises(self) -> None:
        with pytest.raises(MeasureError, match="rNcN"):
            parse_card_measurement("row0col0:240,420,960,1360")

    def test_wrong_number_of_coords_raises(self) -> None:
        with pytest.raises(MeasureError, match="4 comma-separated"):
            parse_card_measurement("r0c0:240,420,960")

    def test_non_numeric_coord_raises(self) -> None:
        with pytest.raises(MeasureError, match="non-numeric"):
            parse_card_measurement("r0c0:240,420,960,abc")

    def test_zero_width_box_raises(self) -> None:
        with pytest.raises(MeasureError, match="x2>x1"):
            parse_card_measurement("r0c0:240,420,240,1360")

    def test_reversed_corners_raises(self) -> None:
        with pytest.raises(MeasureError, match="x2>x1"):
            parse_card_measurement("r0c0:960,1360,240,420")


class TestDeriveGeometrySingleMeasurement:
    def test_origin_cell_derives_left_top_size_directly(self) -> None:
        # scale=4: px(240,420)-(960,1360) -> pt(60,105)-(240,340)
        m = CardMeasurement(row=0, col=0, box=PixelBox(240, 420, 960, 1360))
        result = derive_geometry([m], scale=4.0)
        assert result.left == pytest.approx(60.0)
        assert result.top == pytest.approx(105.0)
        assert result.card_width == pytest.approx(180.0)
        assert result.card_height == pytest.approx(235.0)
        assert result.gap_x is None
        assert result.gap_y is None
        assert result.warnings == ()

    def test_non_origin_cell_uses_fallback_gap_to_back_solve_left_top(self) -> None:
        # card 100x100pt at scale 1, gap 10pt, measuring r1c2 should give
        # left/top for r0c0 once the known gap is subtracted back out.
        m = CardMeasurement(row=1, col=2, box=PixelBox(x1=330, y1=110, x2=430, y2=210))
        result = derive_geometry([m], scale=1.0, fallback_gap_x=10.0, fallback_gap_y=10.0)
        assert result.card_width == pytest.approx(100.0)
        assert result.card_height == pytest.approx(100.0)
        # origin_x(row=1,col=2) = left + 2*(100+10) = 330  ->  left = 110
        assert result.left == pytest.approx(110.0)
        # origin_y(row=1,col=2) = top  + 1*(100+10) = 110  ->  top = 0
        assert result.top == pytest.approx(0.0)

    def test_zero_scale_raises(self) -> None:
        m = CardMeasurement(row=0, col=0, box=PixelBox(0, 0, 10, 10))
        with pytest.raises(MeasureError, match="render_scale must be positive"):
            derive_geometry([m], scale=0.0)

    def test_no_measurements_raises(self) -> None:
        with pytest.raises(MeasureError, match="at least one"):
            derive_geometry([], scale=4.0)

    def test_more_than_two_measurements_raises(self) -> None:
        box = PixelBox(0, 0, 10, 10)
        measurements = [
            CardMeasurement(0, 0, box),
            CardMeasurement(0, 1, box),
            CardMeasurement(0, 2, box),
        ]
        with pytest.raises(MeasureError, match="at most 2"):
            derive_geometry(measurements, scale=4.0)


class TestDeriveGeometryTwoMeasurements:
    def test_horizontal_pair_derives_gap_x_only(self) -> None:
        # scale 1: card 100x100pt, gap_x 10pt, left=0 top=0
        a = CardMeasurement(0, 0, PixelBox(0, 0, 100, 100))
        b = CardMeasurement(0, 1, PixelBox(110, 0, 210, 100))
        result = derive_geometry([a, b], scale=1.0)
        assert result.gap_x == pytest.approx(10.0)
        assert result.gap_y is None
        assert result.left == pytest.approx(0.0)
        assert result.top == pytest.approx(0.0)

    def test_vertical_pair_derives_gap_y_only(self) -> None:
        a = CardMeasurement(0, 0, PixelBox(0, 0, 100, 100))
        b = CardMeasurement(1, 0, PixelBox(0, 115, 100, 215))
        result = derive_geometry([a, b], scale=1.0)
        assert result.gap_y == pytest.approx(15.0)
        assert result.gap_x is None

    def test_diagonal_pair_derives_both_gaps(self) -> None:
        a = CardMeasurement(0, 0, PixelBox(0, 0, 100, 100))
        b = CardMeasurement(1, 1, PixelBox(110, 120, 210, 220))
        result = derive_geometry([a, b], scale=1.0)
        assert result.gap_x == pytest.approx(10.0)
        assert result.gap_y == pytest.approx(20.0)

    def test_order_of_points_does_not_matter(self) -> None:
        a = CardMeasurement(0, 1, PixelBox(110, 0, 210, 100))
        b = CardMeasurement(0, 0, PixelBox(0, 0, 100, 100))
        result = derive_geometry([a, b], scale=1.0)
        assert result.gap_x == pytest.approx(10.0)
        # left/top are still back-solved from whichever point was first
        assert result.left == pytest.approx(110.0 - 1 * (100.0 + 10.0))

    def test_duplicate_cell_warns(self) -> None:
        box = PixelBox(0, 0, 100, 100)
        result = derive_geometry(
            [CardMeasurement(0, 0, box), CardMeasurement(0, 0, box)], scale=1.0,
        )
        assert any("a second" in w for w in result.warnings)
        assert result.gap_x is None
        assert result.gap_y is None

    def test_mismatched_card_size_warns(self) -> None:
        a = CardMeasurement(0, 0, PixelBox(0, 0, 100, 100))
        b = CardMeasurement(0, 1, PixelBox(110, 0, 220, 106))  # 10pt taller
        result = derive_geometry([a, b], scale=1.0)
        assert any("different card sizes" in w for w in result.warnings)


class TestFormatSuggestedPatch:
    def test_shows_old_to_new_for_derived_fields(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        result = derive_geometry([m], scale=1.0)
        current = dict(zip(FRONT_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = format_suggested_patch(result, current, FRONT_FIELDS)
        assert '"left": 0.000 -> 0.000' in text
        assert '"card_width": 0.000 -> 100.000' in text
        assert '"card_height": 0.000 -> 200.000' in text

    def test_undetermined_gap_marked_unchanged(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        result = derive_geometry([m], scale=1.0)
        current = dict(zip(FRONT_FIELDS, (0.0, 0.0, 0.0, 0.0, 5.0, 5.0)))
        text = format_suggested_patch(result, current, FRONT_FIELDS)
        assert '"gap_x": 5.000  (unchanged' in text
        assert '"gap_y": 5.000  (unchanged' in text

    def test_back_field_names_used_when_requested(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        result = derive_geometry([m], scale=1.0)
        current = dict(zip(BACK_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = format_suggested_patch(result, current, BACK_FIELDS)
        assert '"back_card_width": 0.000 -> 100.000' in text
        assert '"back_gap_x"' in text and '"back_gap_y"' in text
