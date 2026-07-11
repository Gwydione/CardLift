from deckforge_gui.app_state import GUIDANCE, STATUS, AppState, WorkflowStep
from deckforge_gui.calibrate_state import (
    CalibrateState,
    ClickOutcome,
    calibrate_guidance_text,
    calibrate_status_text,
    infer_second_cell,
    normalize_box,
    predicted_neighbor_box,
)
from deckforge_gui.find_cards_state import FindCardsState, PageRole, SharedBackStatus

CARDS = WorkflowStep.CALIBRATE_CARDS
BACK = WorkflowStep.CALIBRATE_BACK


class TestNormalizeBox:
    def test_already_ordered_is_unchanged(self) -> None:
        assert normalize_box(10, 20, 110, 220) == (10, 20, 110, 220)

    def test_reversed_corners_are_reordered(self) -> None:
        assert normalize_box(110, 220, 10, 20) == (10, 20, 110, 220)

    def test_mixed_order_corners_are_reordered(self) -> None:
        assert normalize_box(10, 220, 110, 20) == (10, 20, 110, 220)


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


class TestPredictedNeighborBox:
    def test_right_neighbor_is_offset_by_width_plus_gap(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="right")
        assert box == (320, 200, 520, 500)

    def test_below_neighbor_is_offset_by_height_plus_gap(self) -> None:
        box = predicted_neighbor_box((100, 200, 300, 500), card_width=200, card_height=300, gap_x=20, gap_y=10, direction="below")
        assert box == (100, 510, 300, 810)


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
