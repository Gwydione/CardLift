import pytest

from deckforge_gui.app_state import GUIDANCE, STATUS, AppState, WorkflowStep
from deckforge_gui.calibrate_state import (
    CalibratedGeometry,
    CalibrateState,
    ClickOutcome,
    calibrate_guidance_text,
    calibrate_status_text,
    infer_second_cell,
    normalize_box,
    parse_human_cell_label,
    predicted_neighbor_box,
    suggested_grid,
    suggested_second_card_offset,
)
from deckforge_gui.find_cards_state import FindCardsState, PageRole, SharedBackStatus

CARDS = WorkflowStep.CALIBRATE_CARDS
BACK = WorkflowStep.CALIBRATE_BACK


def make_geometry(**overrides) -> CalibratedGeometry:
    data = dict(
        left=0.0, top=0.0, card_width=100.0, card_height=150.0,
        gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
    )
    data.update(overrides)
    return CalibratedGeometry(**data)


class TestNormalizeBox:
    def test_already_ordered_is_unchanged(self) -> None:
        assert normalize_box(10, 20, 110, 220) == (10, 20, 110, 220)

    def test_reversed_corners_are_reordered(self) -> None:
        assert normalize_box(110, 220, 10, 20) == (10, 20, 110, 220)

    def test_mixed_order_corners_are_reordered(self) -> None:
        assert normalize_box(10, 220, 110, 20) == (10, 20, 110, 220)


class TestParseHumanCellLabel:
    def test_parses_1_based_pair_into_0_based_row_col(self) -> None:
        assert parse_human_cell_label("2,1") == (1, 0)

    def test_parses_row_1_col_1_as_0_0(self) -> None:
        assert parse_human_cell_label("1,1") == (0, 0)

    def test_tolerates_surrounding_and_internal_whitespace(self) -> None:
        assert parse_human_cell_label(" 3 , 4 ") == (2, 3)

    def test_multi_digit_numbers(self) -> None:
        assert parse_human_cell_label("12,10") == (11, 9)

    def test_rejects_row_zero(self) -> None:
        assert parse_human_cell_label("0,1") is None

    def test_rejects_col_zero(self) -> None:
        assert parse_human_cell_label("1,0") is None

    def test_rejects_negative_numbers(self) -> None:
        assert parse_human_cell_label("-1,1") is None

    def test_rejects_developer_rnc_n_syntax(self) -> None:
        assert parse_human_cell_label("r1c0") is None

    def test_rejects_missing_comma(self) -> None:
        assert parse_human_cell_label("2 1") is None

    def test_rejects_non_numeric(self) -> None:
        assert parse_human_cell_label("a,b") is None

    def test_rejects_empty_string(self) -> None:
        assert parse_human_cell_label("") is None

    def test_rejects_extra_fields(self) -> None:
        assert parse_human_cell_label("2,1,3") is None


class TestInferSecondCell:
    def test_card_to_the_right_is_next_column_same_row(self) -> None:
        first = (0, 0, 200, 300)
        second = (220, 0, 420, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (0, 1)

    def test_card_below_is_next_row_same_column(self) -> None:
        first = (0, 0, 200, 300)
        second = (0, 310, 200, 610)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (1, 0)

    def test_overlapping_click_returns_none(self) -> None:
        first = (0, 0, 200, 300)
        second = (5, 5, 205, 305)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) is None

    def test_zero_cell_size_returns_none(self) -> None:
        first = (0, 0, 200, 300)
        second = (220, 0, 420, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=0, cell_height=310) is None

    def test_adjacent_diagonal_on_portrait_card(self) -> None:
        # card_height > card_width (e.g. solo_cards.json's real dimensions)
        # -- the raw vertical displacement of a one-cell diagonal move is
        # larger than the horizontal one, which is exactly what previously
        # made the column offset get silently discarded (see
        # CALIBRATION_GEOMETRY_INVESTIGATION.md).
        cw, ch = 174.58, 239.75
        first = (0.0, 0.0, cw, ch)
        second = (cw, ch, 2 * cw, 2 * ch)
        assert infer_second_cell(0, 0, first, second, cell_width=cw, cell_height=ch) == (1, 1)

    def test_far_diagonal_on_portrait_card(self) -> None:
        # Same aspect ratio, but several cells away on each axis -- both
        # offsets must still be derived independently, not just the
        # adjacent case.
        cw, ch = 174.58, 239.75
        first = (0.0, 0.0, cw, ch)
        second = (2 * cw, 3 * ch, 3 * cw, 4 * ch)
        assert infer_second_cell(0, 0, first, second, cell_width=cw, cell_height=ch) == (3, 2)

    def test_diagonal_on_landscape_card(self) -> None:
        # card_width > card_height -- the mirror-image failure mode: raw
        # horizontal displacement dominates, which previously discarded
        # the row offset instead of the column offset.
        cw, ch = 300.0, 150.0
        first = (0.0, 0.0, cw, ch)
        second = (cw, ch, 2 * cw, 2 * ch)
        assert infer_second_cell(0, 0, first, second, cell_width=cw, cell_height=ch) == (1, 1)

    def test_diagonal_on_square_card(self) -> None:
        # Raw dx and dy are exactly equal here, so the old "abs(dx) >=
        # abs(dy)" comparison would always resolve the tie in favor of the
        # column and drop the row -- this must derive both.
        cw, ch = 150.0, 150.0
        first = (0.0, 0.0, cw, ch)
        second = (cw, ch, 2 * cw, 2 * ch)
        assert infer_second_cell(0, 0, first, second, cell_width=cw, cell_height=ch) == (1, 1)

    def test_ambiguous_click_returns_none_regardless_of_aspect_ratio(self) -> None:
        # A near-identical click (well under one cell on either axis) must
        # still be treated as ambiguous, not misread as a diagonal move,
        # even on a strongly non-square card.
        first = (0.0, 0.0, 100.0, 300.0)
        second = (2.0, 2.0, 102.0, 302.0)
        assert infer_second_cell(0, 0, first, second, cell_width=100.0, cell_height=300.0) is None


class TestInferSecondCellHintAgreement:
    """suggested_second_card_offset()'s independent, page-bounds-based
    estimate cross-checks the click-derived rounding -- see
    CALIBRATION_GEOMETRY_INVESTIGATION.md's Doom Pilgrim case, where a
    genuine 2-column click rounds to 3 because the deck's real gap_x is
    ~27% of card_width. Agreement is treated as sufficient confidence for
    the automatic path, NOT as proof the result is correct -- these tests
    only cover conflict *detection*, not universal correctness."""

    def test_no_hint_preserves_pre_existing_behavior(self) -> None:
        # Same wide-gutter shape as Doom Pilgrim, reproduced with round
        # numbers: true offset is 2 columns, but round(260/100)=3.
        first = (0.0, 0.0, 100.0, 100.0)
        second = (260.0, 0.0, 360.0, 100.0)
        assert infer_second_cell(0, 0, first, second, cell_width=100.0, cell_height=100.0) == (0, 3)

    def test_agreement_on_column_axis_is_used_normally(self) -> None:
        first = (0.0, 0.0, 100.0, 100.0)
        second = (260.0, 0.0, 360.0, 100.0)  # round(260/100) = 3
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=3, hint_row_offset=None,
        ) == (0, 3)

    def test_disagreement_on_column_axis_returns_none(self) -> None:
        first = (0.0, 0.0, 100.0, 100.0)
        second = (260.0, 0.0, 360.0, 100.0)  # round(260/100) = 3, hint says 2
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=2, hint_row_offset=None,
        ) is None

    def test_disagreement_on_row_axis_returns_none(self) -> None:
        first = (0.0, 0.0, 100.0, 100.0)
        second = (0.0, 260.0, 100.0, 360.0)  # round(260/100) = 3, hint says 2
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=None, hint_row_offset=2,
        ) is None

    def test_disagreement_on_both_axes_returns_none(self) -> None:
        first = (0.0, 0.0, 100.0, 100.0)
        second = (260.0, 260.0, 360.0, 360.0)
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=2, hint_row_offset=2,
        ) is None

    def test_same_row_measurement_ignores_hint_on_the_untouched_row_axis(self) -> None:
        # row_offset is 0 here (same row) -- a general two-axis hint (e.g.
        # sized for a diagonal suggestion) may carry an unrelated nonzero
        # row_offset, which must never be treated as a conflict for a
        # click that never touched that axis.
        first = (0.0, 0.0, 100.0, 100.0)
        second = (200.0, 0.0, 300.0, 100.0)  # exact, same row, 2 columns over
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=2, hint_row_offset=3,  # row hint irrelevant here
        ) == (0, 2)

    def test_same_column_measurement_ignores_hint_on_the_untouched_column_axis(self) -> None:
        first = (0.0, 0.0, 100.0, 100.0)
        second = (0.0, 200.0, 100.0, 300.0)  # exact, same column, 2 rows down
        assert infer_second_cell(
            0, 0, first, second, cell_width=100.0, cell_height=100.0,
            hint_col_offset=5, hint_row_offset=2,  # column hint irrelevant here
        ) == (2, 0)

    def test_adjacent_diagonal_with_agreeing_hint_is_unaffected(self) -> None:
        cw, ch = 174.58, 239.75
        first = (0.0, 0.0, cw, ch)
        second = (cw, ch, 2 * cw, 2 * ch)
        assert infer_second_cell(
            0, 0, first, second, cell_width=cw, cell_height=ch,
            hint_col_offset=1, hint_row_offset=1,
        ) == (1, 1)


class TestPredictedNeighborBox:
    def test_right_neighbor_is_offset_by_width_plus_gap(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="right")
        assert box == (320, 200, 520, 500)

    def test_below_neighbor_is_offset_by_height_plus_gap(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="below")
        assert box == (100, 510, 300, 810)

    def test_cells_away_defaults_to_the_adjacent_cell(self) -> None:
        adjacent = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="right")
        explicit = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="right", cells_away=1)
        assert adjacent == explicit

    def test_right_neighbor_two_cells_away(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="right", cells_away=2)
        assert box == (540, 200, 740, 500)

    def test_below_neighbor_two_cells_away(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="below", cells_away=2)
        assert box == (100, 820, 300, 1120)


class TestSuggestedSecondCardOffset:
    """A wider baseline between the two calibration clicks sharply reduces
    how much ordinary click imprecision (or genuine tiny print
    non-uniformity) gets amplified once extrapolated across the grid --
    see CALIBRATION_GEOMETRY_INVESTIGATION.md, Effect B. This only decides
    where the "click here" hint is drawn; infer_second_cell() derives the
    click's real (row, col) from wherever the user actually clicks."""

    def test_small_card_on_a_large_page_suggests_a_farther_cell(self) -> None:
        col_offset, row_offset = suggested_second_card_offset(
            card_width=50.0, card_height=50.0,
            page_width_pt=300.0, page_height_pt=300.0,
            first_box=(0.0, 0.0, 50.0, 50.0),
        )
        assert col_offset > 1
        assert row_offset > 1

    def test_card_filling_the_page_still_suggests_at_least_one_cell_away(self) -> None:
        col_offset, row_offset = suggested_second_card_offset(
            card_width=300.0, card_height=300.0,
            page_width_pt=300.0, page_height_pt=300.0,
            first_box=(0.0, 0.0, 300.0, 300.0),
        )
        assert (col_offset, row_offset) == (1, 1)

    def test_offset_is_capped_for_a_tiny_card_on_a_huge_page(self) -> None:
        col_offset, row_offset = suggested_second_card_offset(
            card_width=10.0, card_height=10.0,
            page_width_pt=5000.0, page_height_pt=5000.0,
            first_box=(0.0, 0.0, 10.0, 10.0),
        )
        assert col_offset <= 6
        assert row_offset <= 6


class TestRecordClickSingleCard:
    def test_first_click_sets_pending(self) -> None:
        state = CalibrateState()
        outcome = state.record_click(CARDS, 10.0, 20.0)
        assert outcome is ClickOutcome.PENDING_SET
        assert state.cards.pending_point == (10.0, 20.0)
        assert state.cards.measurements == []

    def test_second_click_completes_first_measurement(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 10.0, 20.0)
        outcome = state.record_click(CARDS, 60.0, 120.0)
        assert outcome is ClickOutcome.MEASUREMENT_ADDED
        assert state.cards.pending_point is None
        assert len(state.cards.measurements) == 1
        m = state.cards.measurements[0]
        assert (m.row, m.col) == (0, 0)
        assert (m.x1, m.y1, m.x2, m.y2) == (10.0, 20.0, 60.0, 120.0)
        assert state.cards.geometry is None  # not complete yet -- optional 2nd card

    def test_degenerate_click_is_rejected_and_clears_pending(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 10.0, 20.0)
        outcome = state.record_click(CARDS, 10.2, 20.2)
        assert outcome is ClickOutcome.REJECTED_DEGENERATE
        assert state.cards.pending_point is None
        assert state.cards.measurements == []

    def test_finish_with_one_card_derives_geometry_with_zero_gap(self) -> None:
        state = CalibrateState(render_scale=4.0)
        state.record_click(CARDS, 10.0, 20.0)
        state.record_click(CARDS, 60.0, 120.0)
        outcome = state.finish_with_one_card(CARDS)
        assert outcome is ClickOutcome.COMPLETE
        geo = state.cards.geometry
        assert geo is not None
        assert geo.left == 10.0
        assert geo.top == 20.0
        assert geo.card_width == 50.0
        assert geo.card_height == 100.0
        assert geo.gap_x == 0.0
        assert geo.gap_y == 0.0
        assert geo.gap_x_derived is False
        assert geo.gap_y_derived is False
        assert state.cards.calibrated_page_num == state.cards.page_num

    def test_finish_with_one_card_is_a_no_op_without_a_measurement(self) -> None:
        state = CalibrateState()
        outcome = state.finish_with_one_card(CARDS)
        assert outcome is ClickOutcome.IGNORED_ALREADY_COMPLETE
        assert state.cards.geometry is None


class TestRecordClickTwoCards:
    def test_auto_inferred_neighbor_completes_calibration_with_gap(self) -> None:
        state = CalibrateState(render_scale=4.0)
        # First card: (0,0)-(100,100).
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        # Second card: directly adjacent to the right, no gap.
        outcome = state.record_click(CARDS, 100.0, 0.0)
        assert outcome is ClickOutcome.PENDING_SET
        outcome = state.record_click(CARDS, 200.0, 100.0)
        assert outcome is ClickOutcome.COMPLETE

        assert len(state.cards.measurements) == 2
        assert state.cards.measurements[1].row == 0
        assert state.cards.measurements[1].col == 1

        geo = state.cards.geometry
        assert geo is not None
        assert geo.card_width == 100.0
        assert geo.gap_x == 0.0
        assert geo.gap_x_derived is True
        assert geo.gap_y_derived is False  # only one row was ever measured

    def test_ambiguous_second_card_needs_a_cell_label(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 5.0, 5.0)  # nearly on top of the first card
        outcome = state.record_click(CARDS, 105.0, 105.0)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL
        assert len(state.cards.measurements) == 1  # not yet appended

        outcome = state.add_measurement_with_cell(CARDS, row=1, col=1)
        assert outcome is ClickOutcome.COMPLETE
        assert len(state.cards.measurements) == 2
        assert state.cards.measurements[1].row == 1
        assert state.cards.measurements[1].col == 1

    def test_clicks_after_completion_are_ignored(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)
        geometry_before = state.cards.geometry

        outcome = state.record_click(CARDS, 500.0, 500.0)
        assert outcome is ClickOutcome.IGNORED_ALREADY_COMPLETE
        assert state.cards.geometry is geometry_before
        assert state.cards.pending_point is None


class TestRecordClickHintConflict:
    """record_click()-level coverage for the hint-vs-click agreement
    check (see TestInferSecondCellHintAgreement for the pure-function
    cases) -- confirms the conflict actually routes through
    ClickOutcome.NEEDS_CELL_LABEL and resolves via the existing
    add_measurement_with_cell() clarification path, with no new
    workflow/dialog involved."""

    def test_far_diagonal_agreement_completes_automatically(self) -> None:
        # Zero gap, so both estimates are unambiguous and agree -- the
        # ordinary case, and it must stay a single automatic completion.
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 200.0, 300.0)
        outcome = state.record_click(
            CARDS, 400.0, 900.0, hint_col_offset=2, hint_row_offset=3,
        )
        assert outcome is ClickOutcome.PENDING_SET
        outcome = state.record_click(
            CARDS, 600.0, 1200.0, hint_col_offset=2, hint_row_offset=3,
        )
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (3, 2)

    def test_same_row_far_measurement_completes_despite_irrelevant_row_hint(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 200.0, 0.0, hint_col_offset=2, hint_row_offset=5)
        outcome = state.record_click(CARDS, 300.0, 100.0, hint_col_offset=2, hint_row_offset=5)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (0, 2)

    def test_same_column_far_measurement_completes_despite_irrelevant_column_hint(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 0.0, 200.0, hint_col_offset=5, hint_row_offset=2)
        outcome = state.record_click(CARDS, 100.0, 300.0, hint_col_offset=5, hint_row_offset=2)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (2, 0)

    def test_row_axis_conflict_needs_a_cell_label_and_resolves(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 0.0, 260.0, hint_col_offset=None, hint_row_offset=2)
        outcome = state.record_click(CARDS, 100.0, 360.0, hint_col_offset=None, hint_row_offset=2)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL
        assert len(state.cards.measurements) == 1

        outcome = state.add_measurement_with_cell(CARDS, row=2, col=0)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (2, 0)

    def test_both_axes_conflict_needs_a_cell_label_and_resolves(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 260.0, 260.0, hint_col_offset=2, hint_row_offset=2)
        outcome = state.record_click(CARDS, 360.0, 360.0, hint_col_offset=2, hint_row_offset=2)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL
        assert len(state.cards.measurements) == 1

        outcome = state.add_measurement_with_cell(CARDS, row=2, col=2)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (2, 2)


class TestDoomPilgrimGridInferenceConflict:
    """End-to-end reproduction of the real Doom Pilgrim PDF's grid-
    inference bug (docs/CALIBRATION_GEOMETRY_INVESTIGATION.md): clicking
    the visually-correct upper-left (r0c0) and lower-right (r2c2) cards'
    crosshairs -- measured directly off "DP Pocket 20 pages for centered
    bothsided print.pdf" page 1, rendered at CALIBRATE_RENDER_SCALE=4.0,
    pixel coordinates divided by 4.0 -- infers (2,3) instead of (2,2)
    because the deck's real column gutter (~40.6pt) is ~27% of
    card_width (149.5pt), just over the 1/(2*2)=25% rounding-danger
    threshold for a 2-column offset. suggested_second_card_offset()'s
    independent page-bounds estimate still correctly predicts
    col_offset=2, so passing it into record_click() must surface the
    conflict instead of silently completing with the wrong grid."""

    FIRST_BOX = (31.5, 17.75, 181.0, 266.5)       # r0c0 crosshairs, PDF points
    SECOND_BOX = (411.75, 521.5, 561.25, 776.75)  # r2c2 crosshairs, PDF points
    PAGE_WIDTH_PT = 595.19
    PAGE_HEIGHT_PT = 792.00

    def _click_both_cards(self, state: CalibrateState, with_hint: bool) -> ClickOutcome:
        state.record_click(CARDS, self.FIRST_BOX[0], self.FIRST_BOX[1])
        state.record_click(CARDS, self.FIRST_BOX[2], self.FIRST_BOX[3])
        first = state.cards.measurements[0]
        hint_col_offset = hint_row_offset = None
        if with_hint:
            hint_col_offset, hint_row_offset = suggested_second_card_offset(
                first.x2 - first.x1, first.y2 - first.y1,
                self.PAGE_WIDTH_PT, self.PAGE_HEIGHT_PT, first.as_tuple(),
            )
        state.record_click(
            CARDS, self.SECOND_BOX[0], self.SECOND_BOX[1],
            hint_col_offset=hint_col_offset, hint_row_offset=hint_row_offset,
        )
        return state.record_click(
            CARDS, self.SECOND_BOX[2], self.SECOND_BOX[3],
            hint_col_offset=hint_col_offset, hint_row_offset=hint_row_offset,
        )

    def test_without_hint_reproduces_the_original_bug(self) -> None:
        """Documents the pre-fix behavior for contrast -- not the
        recommended path; the real GUI always supplies a hint once a
        page's size is known (see CalibrateWorkspace._hint_offsets_for_
        conflict_check())."""
        state = CalibrateState(render_scale=4.0)
        outcome = self._click_both_cards(state, with_hint=False)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (2, 3)
        rows, cols = suggested_grid(state.cards.geometry, self.PAGE_WIDTH_PT, self.PAGE_HEIGHT_PT)
        assert (rows, cols) == (3, 4)

    def test_with_hint_requests_cell_label_instead_of_guessing(self) -> None:
        state = CalibrateState(render_scale=4.0)
        outcome = self._click_both_cards(state, with_hint=True)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL
        assert len(state.cards.measurements) == 1  # second card not yet appended
        assert state.cards.geometry is None

    def test_clarifying_with_the_correct_cell_yields_a_3x3_grid(self) -> None:
        state = CalibrateState(render_scale=4.0)
        outcome = self._click_both_cards(state, with_hint=True)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL

        outcome = state.add_measurement_with_cell(CARDS, row=2, col=2)
        assert outcome is ClickOutcome.COMPLETE
        assert (state.cards.measurements[1].row, state.cards.measurements[1].col) == (2, 2)

        geo = state.cards.geometry
        assert geo is not None
        assert geo.gap_x == pytest.approx(40.625, abs=0.01)
        rows, cols = suggested_grid(geo, self.PAGE_WIDTH_PT, self.PAGE_HEIGHT_PT)
        assert (rows, cols) == (3, 3)

    def test_no_regression_to_ungauged_axis_warning_after_clarification(self) -> None:
        """Both axes were genuinely measured (different row AND column),
        so the completion text must stay free of the "wasn't measured"
        warning -- confirms the clarification path doesn't reintroduce
        Effect A from CALIBRATION_GEOMETRY_INVESTIGATION.md."""
        state = CalibrateState(render_scale=4.0)
        self._click_both_cards(state, with_hint=True)
        state.add_measurement_with_cell(CARDS, row=2, col=2)

        geo = state.cards.geometry
        assert geo.gap_x_derived is True
        assert geo.gap_y_derived is True

        page_size = (self.PAGE_WIDTH_PT, self.PAGE_HEIGHT_PT)
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=page_size)
        status = calibrate_status_text(CARDS, state.cards, page_size=page_size)
        assert "wasn't measured" not in body
        assert "wasn't measured" not in status


class TestSharedBackIsSingleCardOnly:
    """Shared Back only ever needs one representative card's rectangle --
    unlike Cards, it has no optional second-card spacing measurement."""

    def test_back_target_does_not_allow_a_second_measurement(self) -> None:
        state = CalibrateState()
        assert state.back.allows_second_measurement is False
        assert state.cards.allows_second_measurement is True

    def test_second_corner_click_completes_calibration_immediately(self) -> None:
        state = CalibrateState(render_scale=4.0)
        state.back.page_num = 8
        outcome = state.record_click(BACK, 10.0, 20.0)
        assert outcome is ClickOutcome.PENDING_SET
        outcome = state.record_click(BACK, 60.0, 120.0)
        assert outcome is ClickOutcome.COMPLETE

        geo = state.back.geometry
        assert geo is not None
        assert geo.card_width == 50.0
        assert geo.card_height == 100.0
        assert geo.gap_x == 0.0
        assert geo.gap_y == 0.0
        assert len(state.back.measurements) == 1

    def test_clicks_after_completion_are_ignored_with_no_second_card_prompt(self) -> None:
        state = CalibrateState()
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)
        geometry_before = state.back.geometry

        outcome = state.record_click(BACK, 500.0, 500.0)
        assert outcome is ClickOutcome.IGNORED_ALREADY_COMPLETE
        assert state.back.geometry is geometry_before

    def test_finish_with_one_card_is_harmless_since_back_already_completed(self) -> None:
        # Shared Back's UI never shows a "Finish with one card" button (it's
        # already complete after one card), but calling this directly is
        # still safe: it just re-derives the same, already-set geometry.
        state = CalibrateState()
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)
        geometry_before = state.back.geometry
        outcome = state.finish_with_one_card(BACK)
        assert outcome is ClickOutcome.COMPLETE
        assert state.back.geometry == geometry_before


class TestCardsAndBackAreIndependent:
    def test_measuring_cards_does_not_touch_back(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)

        assert state.cards.is_complete
        assert not state.back.is_complete
        assert state.back.measurements == []


class TestStartOverAndReset:
    def test_start_over_clears_measurements_but_keeps_page(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)

        state.start_over(CARDS)
        assert state.cards.measurements == []
        assert state.cards.geometry is None
        assert state.cards.calibrated_page_num is None
        assert state.cards.page_num == 3  # view/page preserved

    def test_reset_all_clears_both_targets(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)  # completes on its own -- Shared Back needs only one card

        state.reset_all()
        assert not state.cards.is_complete
        assert not state.back.is_complete


class TestCardsIsStale:
    def test_not_stale_before_any_calibration(self) -> None:
        state = CalibrateState()
        find_cards = FindCardsState()
        assert state.cards_is_stale(find_cards) is False

    def test_not_stale_while_calibrated_page_still_a_front_page(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)

        find_cards = FindCardsState()
        find_cards.set_role(3, PageRole.FRONT)
        assert state.cards_is_stale(find_cards) is False

    def test_stale_once_the_calibrated_page_is_no_longer_a_front_page(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)

        find_cards = FindCardsState()  # page 3 never marked Front (or was cleared)
        assert state.cards_is_stale(find_cards) is True

    def test_marking_a_different_page_front_does_not_make_cards_stale(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)

        find_cards = FindCardsState()
        find_cards.set_role(3, PageRole.FRONT)
        find_cards.set_role(7, PageRole.FRONT)
        assert state.cards_is_stale(find_cards) is False


class TestBackIsStale:
    def test_not_stale_before_any_calibration(self) -> None:
        state = CalibrateState()
        find_cards = FindCardsState()
        assert state.back_is_stale(find_cards) is False

    def test_not_stale_while_calibrated_page_still_the_assigned_back(self) -> None:
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)

        find_cards = FindCardsState()
        find_cards.set_role(8, PageRole.BACK)
        assert state.back_is_stale(find_cards) is False

    def test_stale_once_the_shared_back_is_reassigned_to_a_different_page(self) -> None:
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)

        find_cards = FindCardsState()
        find_cards.set_role(9, PageRole.BACK)  # moved off page 8
        assert state.back_is_stale(find_cards) is True

    def test_stale_once_no_shared_back_is_confirmed(self) -> None:
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)

        find_cards = FindCardsState()
        find_cards.confirm_no_shared_back()
        assert state.back_is_stale(find_cards) is True


class TestGuidanceAndStatusText:
    def test_empty_state_matches_static_guidance(self) -> None:
        state = CalibrateState()
        assert calibrate_guidance_text(CARDS, state.cards) == GUIDANCE[CARDS]
        assert calibrate_status_text(CARDS, state.cards) == STATUS[CARDS]

    def test_pending_point_prompts_for_opposite_corner(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 10.0, 10.0)
        _, body = calibrate_guidance_text(CARDS, state.cards)
        assert "opposite corner" in body
        assert "opposite corner" in calibrate_status_text(CARDS, state.cards)

    def test_one_measurement_suggests_a_second_card(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        headline, _ = calibrate_guidance_text(CARDS, state.cards)
        assert "optional" in headline.lower()

    def test_complete_state_mentions_start_over(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)
        headline, body = calibrate_guidance_text(CARDS, state.cards, front_page_count=6)
        assert headline == "Fronts calibration complete"
        assert "Start Over" in body
        assert "Calibrated" in calibrate_status_text(CARDS, state.cards, front_page_count=6)

    def test_complete_state_reports_representative_page_and_front_count(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)
        _, body = calibrate_guidance_text(CARDS, state.cards, front_page_count=6)
        assert "page 3" in body
        assert "6" in body
        assert "page 3" in calibrate_status_text(CARDS, state.cards, front_page_count=6)
        assert "6" in calibrate_status_text(CARDS, state.cards, front_page_count=6)

    def test_complete_back_state_mentions_shared_back_scope(self) -> None:
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        outcome = state.record_click(BACK, 100.0, 100.0)
        assert outcome is ClickOutcome.COMPLETE  # one card is a complete Shared Back calibration
        headline, body = calibrate_guidance_text(BACK, state.back, front_page_count=6)
        assert headline == "Shared Back calibration complete"
        assert "shared back" in body.lower()
        assert "6" in body
        assert "Start Over" in body
        status = calibrate_status_text(BACK, state.back, front_page_count=6)
        assert "Calibrated" in status
        assert "shared back" in status.lower()


class TestBackConfirmedNoneGuidanceAndStatus:
    """SharedBackStatus.CONFIRMED_NONE represents a Deck where Select Card
    Pages recorded an explicit "no Shared Back" -- Calibrate has nothing to
    measure and should say so rather than prompting for a corner click."""

    def test_guidance_explains_there_is_nothing_to_calibrate(self) -> None:
        state = CalibrateState()
        headline, body = calibrate_guidance_text(
            BACK, state.back, shared_back_status=SharedBackStatus.CONFIRMED_NONE,
        )
        assert headline == "This deck has no Shared Back."
        assert "Review Cards" in body

    def test_status_explains_there_is_nothing_to_calibrate(self) -> None:
        state = CalibrateState()
        status = calibrate_status_text(BACK, state.back, shared_back_status=SharedBackStatus.CONFIRMED_NONE)
        assert "no Shared Back" in status

    def test_shared_back_status_is_ignored_for_the_cards_step(self) -> None:
        state = CalibrateState()
        assert (
            calibrate_guidance_text(CARDS, state.cards, shared_back_status=SharedBackStatus.CONFIRMED_NONE)
            == GUIDANCE[CARDS]
        )


class TestBackUnresolvedGuidanceAndStatus:
    """SharedBackStatus.UNRESOLVED must never be treated like
    CONFIRMED_NONE -- Calibrate has not been told there's no Shared Back,
    only that nothing is currently assigned, and those are different
    facts (see calibrate_state.py's "ONE SHARED LAYOUT" docstring)."""

    def test_guidance_does_not_claim_there_is_no_shared_back(self) -> None:
        state = CalibrateState()
        headline, body = calibrate_guidance_text(
            BACK, state.back, shared_back_status=SharedBackStatus.UNRESOLVED,
        )
        assert headline != "This deck has no Shared Back."
        assert "hasn't been decided" in headline
        assert "Select Card Pages" in body

    def test_status_points_back_to_select_card_pages_not_review_cards(self) -> None:
        state = CalibrateState()
        status = calibrate_status_text(BACK, state.back, shared_back_status=SharedBackStatus.UNRESOLVED)
        assert status == "Shared Back hasn't been decided yet — go back to Select Card Pages to resolve it."
        assert "Review Cards" not in status

    def test_shared_back_status_is_ignored_for_the_cards_step(self) -> None:
        state = CalibrateState()
        assert (
            calibrate_guidance_text(CARDS, state.cards, shared_back_status=SharedBackStatus.UNRESOLVED)
            == GUIDANCE[CARDS]
        )


class TestUnresolvedSharedBackReachedViaSidebar:
    """Regression test for a real navigation path, not just an edge case:
    AppState.is_reached is a one-way ratchet (furthest_step only grows), so
    once Calibrate > Shared Back has been visited, the sidebar entry for it
    stays enabled even after the user goes back to Select Card Pages and
    un-assigns the Shared Back page -- leaving the decision genuinely
    unresolved rather than confirmed-none. Calibrate must not silently
    treat "no page currently assigned" as "no Shared Back" in that case."""

    def test_sidebar_still_permits_reentry_after_the_back_page_is_cleared(self) -> None:
        app_state = AppState()
        app_state.select_step(WorkflowStep.FIND_CARDS)
        app_state.select_step(WorkflowStep.CALIBRATE_CARDS)
        app_state.select_step(WorkflowStep.CALIBRATE_BACK)
        app_state.select_step(WorkflowStep.REVIEW_CARDS)

        # The user goes back to Select Card Pages -- is_reached for every
        # earlier step (including Shared Back) does not regress.
        app_state.select_step(WorkflowStep.FIND_CARDS)
        assert app_state.is_reached(WorkflowStep.CALIBRATE_BACK) is True

        find_cards = FindCardsState()
        find_cards.toggle_front(2)
        find_cards.toggle_back(8)
        assert find_cards.shared_back_status() is SharedBackStatus.ASSIGNED

        calibrate = CalibrateState()
        calibrate.back.page_num = 8
        calibrate.record_click(BACK, 0.0, 0.0)
        calibrate.record_click(BACK, 100.0, 100.0)
        assert calibrate.back.is_complete is True

        # The user un-assigns the back page (e.g. realizing it's the wrong
        # page) without reassigning it or confirming "no Shared Back" --
        # genuinely unresolved, not confirmed-none.
        find_cards.toggle_back(8)
        assert find_cards.shared_back_status() is SharedBackStatus.UNRESOLVED

        # The user clicks "Shared Back" directly in the sidebar (still
        # enabled per is_reached above). MainWindow._apply_step would
        # detect the now-stale calibration and reset it before the step is
        # shown -- exercised here directly against CalibrateState.
        assert calibrate.back_is_stale(find_cards) is True
        calibrate.back.reset()

        headline, _ = calibrate_guidance_text(
            BACK, calibrate.back, shared_back_status=find_cards.shared_back_status(),
        )
        assert headline != "This deck has no Shared Back."

        status = calibrate_status_text(BACK, calibrate.back, shared_back_status=find_cards.shared_back_status())
        assert status == "Shared Back hasn't been decided yet — go back to Select Card Pages to resolve it."


class TestSuggestedGrid:
    """suggested_grid() is a STARTING SUGGESTION for Review Cards, biased
    toward over- rather than under-suggesting near a boundary -- see the
    module docstring on GRID_FIT_TOLERANCE_PT for why that direction was
    chosen (a phantom card is a one-click fix; a silently missing one is
    not)."""

    def test_cols_and_rows_fit_the_page(self) -> None:
        geo = make_geometry(left=0.0, top=0.0, card_width=100.0, card_height=150.0)
        assert suggested_grid(geo, page_width_pt=300.0, page_height_pt=450.0) == (3, 3)

    def test_margin_reduces_the_count(self) -> None:
        geo = make_geometry(left=50.0, top=0.0, card_width=100.0, card_height=150.0)
        rows, cols = suggested_grid(geo, page_width_pt=300.0, page_height_pt=450.0)
        assert cols == 2  # 50 + 2*100 = 250 fits; a 3rd would need 350

    def test_tolerance_rescues_a_near_miss(self) -> None:
        geo = make_geometry(card_width=100.0, card_height=150.0)
        # Page is 1pt short of a full 3rd column -- the 2pt default
        # tolerance still suggests it rather than silently dropping it.
        _, cols = suggested_grid(geo, page_width_pt=299.0, page_height_pt=450.0)
        assert cols == 3

    def test_without_tolerance_the_near_miss_is_excluded(self) -> None:
        geo = make_geometry(card_width=100.0, card_height=150.0)
        _, cols = suggested_grid(geo, page_width_pt=299.0, page_height_pt=450.0, tolerance_pt=0.0)
        assert cols == 2

    def test_gap_is_accounted_for(self) -> None:
        geo = make_geometry(card_width=100.0, card_height=150.0, gap_x=10.0, gap_y=10.0)
        # 3 cards + 2 gaps = 300 + 20 = 320; 3 cards + 2 gaps tall = 450 + 20 = 470
        assert suggested_grid(geo, page_width_pt=320.0, page_height_pt=470.0) == (3, 3)

    def test_zero_card_size_is_safe(self) -> None:
        geo = make_geometry(card_width=0.0, card_height=0.0)
        assert suggested_grid(geo, 300.0, 450.0) == (0, 0)

    def test_card_larger_than_page_suggests_nothing(self) -> None:
        geo = make_geometry(card_width=5000.0, card_height=5000.0)
        assert suggested_grid(geo, 300.0, 450.0) == (0, 0)

    def test_matches_the_real_solo_cards_profile(self) -> None:
        # profiles/solo_cards.json's actual calibrated values against the
        # real A4 page (595.276 x 841.89pt, confirmed via PyMuPDF) -- ties
        # this formula to a real deck already verified correct via
        # --preview, not only synthetic numbers.
        geo = make_geometry(left=35.75, top=61.25, card_width=174.58, card_height=239.75)
        assert suggested_grid(geo, page_width_pt=595.276, page_height_pt=841.89) == (3, 3)


class TestGridClauseInCompletionText:
    """The suggested-grid mention in Calibrate's completion text is purely
    informational ('Here's what DeckForge thinks it found') -- Review
    Cards, not Calibrate, is where the count is actually confirmed or
    corrected. See DEVELOPER.md's "Suggested grid size" section."""

    def _complete_cards_state(self) -> CalibrateState:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.finish_with_one_card(CARDS)
        return state

    def test_guidance_and_status_mention_the_suggested_grid_when_page_size_given(self) -> None:
        state = self._complete_cards_state()
        _, body = calibrate_guidance_text(CARDS, state.cards, front_page_count=6, page_size=(300.0, 300.0))
        assert "3×3 grid" in body
        status = calibrate_status_text(CARDS, state.cards, front_page_count=6, page_size=(300.0, 300.0))
        assert "3×3 grid" in status

    def test_no_grid_clause_without_a_page_size(self) -> None:
        state = self._complete_cards_state()
        _, body = calibrate_guidance_text(CARDS, state.cards, front_page_count=6)
        assert "grid" not in body.lower()
        assert "grid" not in calibrate_status_text(CARDS, state.cards, front_page_count=6).lower()

    def test_no_grid_clause_for_a_degenerate_zero_suggestion(self) -> None:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 5000.0, 5000.0)  # measured "card" bigger than the page
        state.finish_with_one_card(CARDS)
        _, body = calibrate_guidance_text(CARDS, state.cards, front_page_count=1, page_size=(300.0, 300.0))
        assert "grid" not in body.lower()

    def test_grid_clause_never_appears_for_shared_back(self) -> None:
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)
        _, body = calibrate_guidance_text(BACK, state.back, front_page_count=6, page_size=(300.0, 300.0))
        assert "grid" not in body.lower()
        status = calibrate_status_text(BACK, state.back, front_page_count=6, page_size=(300.0, 300.0))
        assert "grid" not in status.lower()

    def test_no_grid_clause_before_calibration_completes(self) -> None:
        state = CalibrateState()
        state.record_click(CARDS, 0.0, 0.0)  # pending, not complete
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "grid" not in body.lower()


class TestUngaugedAxisWarning:
    """Effect A from CALIBRATION_GEOMETRY_INVESTIGATION.md: an axis that
    was never actually measured is silently assumed edge-to-edge
    (gap = 0.0). gap_x_derived/gap_y_derived already tracked which axis
    was real vs. defaulted -- this surfaces that fact in the completion
    text, but only when the axis in question actually has more than one
    cell (a 1-row or 1-column deck never uses that axis's spacing, so
    warning about it would be noise)."""

    def _finish_with_one_card(self, x2: float, y2: float) -> CalibrateState:
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, x2, y2)
        state.finish_with_one_card(CARDS)
        return state

    def test_one_card_finish_on_a_multi_row_multi_col_grid_warns_about_both(self) -> None:
        state = self._finish_with_one_card(100.0, 100.0)
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "columns" in body
        assert "rows" in body
        assert "Start Over" in body
        status = calibrate_status_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "columns" in status and "rows" in status

    def test_same_row_measurement_only_warns_about_rows(self) -> None:
        # Second card directly to the right -- derives gap_x, leaves gap_y
        # (rows) defaulted.
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 100.0, 0.0)
        state.record_click(CARDS, 200.0, 100.0)
        assert state.cards.geometry.gap_x_derived is True
        assert state.cards.geometry.gap_y_derived is False

        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "rows" in body
        assert "columns" not in body

    def test_same_column_measurement_only_warns_about_columns(self) -> None:
        # Second card directly below -- derives gap_y, leaves gap_x
        # (columns) defaulted.
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 0.0, 100.0)
        state.record_click(CARDS, 100.0, 200.0)
        assert state.cards.geometry.gap_x_derived is False
        assert state.cards.geometry.gap_y_derived is True

        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "columns" in body
        assert "rows" not in body

    def test_near_identical_second_click_needs_a_cell_label(self) -> None:
        # A click too close to the first to resolve on either axis (well
        # under one cell of displacement) still can't be auto-inferred and
        # must fall back to asking -- see TestRecordClickTwoCards'
        # test_ambiguous_second_card_needs_a_cell_label for the same case
        # exercised directly against record_click().
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, 100.0, 100.0)
        state.record_click(CARDS, 5.0, 5.0)
        outcome = state.record_click(CARDS, 105.0, 105.0)
        assert outcome is ClickOutcome.NEEDS_CELL_LABEL
        outcome = state.add_measurement_with_cell(CARDS, row=1, col=1)
        assert outcome is ClickOutcome.COMPLETE
        assert state.cards.geometry.gap_x_derived is True
        assert state.cards.geometry.gap_y_derived is True

        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "wasn't measured" not in body
        status = calibrate_status_text(CARDS, state.cards, page_size=(300.0, 300.0))
        assert "wasn't measured" not in status

    def test_genuine_diagonal_measurement_is_auto_inferred_and_warns_about_neither(self) -> None:
        # Regression test for the actual reported bug: a real diagonal
        # second-card click (a full cell away on both axes, on a portrait
        # card -- i.e. exactly the "click a farther diagonal card" guidance
        # the app itself gives) must be auto-inferred directly (no
        # NEEDS_CELL_LABEL round-trip) and must derive both gap_x and
        # gap_y, not silently default one of them to 0.0.
        cw, ch = 174.58, 239.75
        state = CalibrateState()
        state.cards.page_num = 3
        state.record_click(CARDS, 0.0, 0.0)
        state.record_click(CARDS, cw, ch)
        gap_x, gap_y = 2.0, 3.0
        second_x0 = cw + gap_x
        second_y0 = ch + gap_y
        state.record_click(CARDS, second_x0, second_y0)
        outcome = state.record_click(CARDS, second_x0 + cw, second_y0 + ch)

        assert outcome is ClickOutcome.COMPLETE
        assert state.cards.measurements[1].row == 1
        assert state.cards.measurements[1].col == 1
        geometry = state.cards.geometry
        assert geometry.gap_x_derived is True
        assert geometry.gap_y_derived is True
        assert geometry.gap_x == pytest.approx(gap_x)
        assert geometry.gap_y == pytest.approx(gap_y)

        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(1000.0, 1000.0))
        assert "wasn't measured" not in body
        status = calibrate_status_text(CARDS, state.cards, page_size=(1000.0, 1000.0))
        assert "wasn't measured" not in status

    def test_single_row_layout_does_not_warn_about_rows(self) -> None:
        # 50pt-wide cards on a 300pt-wide page (several columns), but only
        # 100pt tall on a 100pt-tall page (exactly one row).
        state = self._finish_with_one_card(50.0, 100.0)
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(300.0, 100.0))
        assert "columns" in body
        assert "rows" not in body

    def test_single_column_layout_does_not_warn_about_columns(self) -> None:
        state = self._finish_with_one_card(100.0, 50.0)
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(100.0, 300.0))
        assert "rows" in body
        assert "columns" not in body

    def test_single_card_layout_warns_about_neither(self) -> None:
        # Card fills the whole page -- there's no second cell on either
        # axis, so an unmeasured gap is correct, not a defaulted guess.
        state = self._finish_with_one_card(100.0, 100.0)
        _, body = calibrate_guidance_text(CARDS, state.cards, page_size=(100.0, 100.0))
        assert "wasn't measured" not in body

    def test_no_warning_without_a_page_size(self) -> None:
        state = self._finish_with_one_card(100.0, 100.0)
        _, body = calibrate_guidance_text(CARDS, state.cards)
        assert "wasn't measured" not in body

    def test_no_warning_for_shared_back(self) -> None:
        # Shared Back is a single representative card, not a grid -- no
        # spacing concept applies, so it must never show this warning.
        state = CalibrateState()
        state.back.page_num = 8
        state.record_click(BACK, 0.0, 0.0)
        state.record_click(BACK, 100.0, 100.0)
        _, body = calibrate_guidance_text(BACK, state.back, page_size=(300.0, 300.0))
        assert "wasn't measured" not in body
