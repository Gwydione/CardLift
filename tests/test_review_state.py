from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrationTarget
from deckforge_gui.find_cards_state import SharedBackStatus
from deckforge_gui.review_state import (
    ReviewCard,
    ReviewCardsState,
    build_review_cards,
    review_guidance_text,
    review_ready,
    review_status_text,
)


def make_geometry(**overrides) -> CalibratedGeometry:
    data = dict(
        left=0.0, top=0.0, card_width=100.0, card_height=150.0,
        gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
    )
    data.update(overrides)
    return CalibratedGeometry(**data)


def complete_target(**geometry_overrides) -> CalibrationTarget:
    return CalibrationTarget(geometry=make_geometry(**geometry_overrides))


def incomplete_target() -> CalibrationTarget:
    return CalibrationTarget()


class TestBuildReviewCards:
    def test_enumerates_every_cell_in_reading_order(self) -> None:
        geo = make_geometry(card_width=100.0, card_height=150.0)
        cards = build_review_cards([2], geo, page_size_fn=lambda p: (300.0, 300.0))
        # 3x2 grid (cols=3 from 300pt width, rows=2 from 300pt height)
        assert cards == [
            ReviewCard(2, 0, 0), ReviewCard(2, 0, 1), ReviewCard(2, 0, 2),
            ReviewCard(2, 1, 0), ReviewCard(2, 1, 1), ReviewCard(2, 1, 2),
        ]

    def test_multiple_front_pages_are_concatenated_in_order(self) -> None:
        geo = make_geometry(card_width=300.0, card_height=300.0)  # 1x1 grid per page
        cards = build_review_cards([2, 3, 5], geo, page_size_fn=lambda p: (300.0, 300.0))
        assert [c.page_num for c in cards] == [2, 3, 5]

    def test_different_page_sizes_are_respected_per_page(self) -> None:
        geo = make_geometry(card_width=100.0, card_height=150.0)

        def page_size(page_num: int) -> tuple[float, float]:
            return (300.0, 150.0) if page_num == 2 else (200.0, 150.0)

        cards = build_review_cards([2, 3], geo, page_size_fn=page_size)
        page_2_cols = {c.col for c in cards if c.page_num == 2}
        page_3_cols = {c.col for c in cards if c.page_num == 3}
        assert page_2_cols == {0, 1, 2}
        assert page_3_cols == {0, 1}

    def test_card_bigger_than_the_page_yields_nothing(self) -> None:
        geo = make_geometry(card_width=5000.0, card_height=5000.0)
        cards = build_review_cards([2], geo, page_size_fn=lambda p: (300.0, 300.0))
        assert cards == []

    def test_no_front_pages_yields_nothing(self) -> None:
        geo = make_geometry()
        cards = build_review_cards([], geo, page_size_fn=lambda p: (300.0, 300.0))
        assert cards == []


class TestReviewCardsStateSync:
    def test_new_cards_default_to_included(self) -> None:
        state = ReviewCardsState()
        cards = [ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)]
        state.sync(cards)
        assert state.is_included(cards[0]) is True
        assert state.is_included(cards[1]) is True
        assert state.total_count() == 2
        assert state.included_count() == 2

    def test_toggling_a_card_excludes_it(self) -> None:
        state = ReviewCardsState()
        card = ReviewCard(2, 0, 0)
        state.sync([card])
        state.toggle(card)
        assert state.is_included(card) is False
        assert state.included_count() == 0
        state.toggle(card)
        assert state.is_included(card) is True

    def test_sync_preserves_existing_toggles_for_cards_still_present(self) -> None:
        state = ReviewCardsState()
        kept = ReviewCard(2, 0, 0)
        removed = ReviewCard(2, 0, 1)
        state.sync([kept, removed])
        state.toggle(removed)  # exclude it

        state.sync([kept, removed])  # re-sync with the same cards
        assert state.is_included(kept) is True
        assert state.is_included(removed) is False

    def test_sync_drops_cards_no_longer_suggested(self) -> None:
        state = ReviewCardsState()
        gone = ReviewCard(9, 0, 0)
        state.sync([gone])
        state.toggle(gone)

        state.sync([ReviewCard(2, 0, 0)])  # page 9 no longer a front page
        assert gone not in state.all_cards()
        assert state.total_count() == 1

    def test_sync_adds_newly_suggested_cards_as_included(self) -> None:
        state = ReviewCardsState()
        first = ReviewCard(2, 0, 0)
        state.sync([first])
        state.toggle(first)

        second = ReviewCard(3, 0, 0)
        state.sync([first, second])
        assert state.is_included(first) is False  # preserved
        assert state.is_included(second) is True  # new, defaults on

    def test_toggle_on_unknown_card_is_a_no_op(self) -> None:
        state = ReviewCardsState()
        state.toggle(ReviewCard(1, 0, 0))  # never synced
        assert state.total_count() == 0

    def test_included_cards_returns_only_included(self) -> None:
        state = ReviewCardsState()
        a, b = ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)
        state.sync([a, b])
        state.toggle(b)
        assert state.included_cards() == [a]

    def test_clear_empties_everything(self) -> None:
        state = ReviewCardsState()
        state.sync([ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)])
        state.clear()
        assert state.total_count() == 0
        assert state.all_cards() == []


class TestReviewReady:
    def test_not_ready_when_fronts_not_calibrated(self) -> None:
        assert review_ready(incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED) is False

    def test_not_ready_when_shared_back_unresolved(self) -> None:
        assert review_ready(complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED) is False

    def test_not_ready_when_assigned_but_back_not_yet_calibrated(self) -> None:
        # A Shared Back page is assigned (status ASSIGNED) but Calibrate's
        # Shared Back step hasn't actually measured it yet -- reachable via
        # a sidebar jump after the assigned page changed and back_is_stale()
        # reset it, per MainWindow's Review-Cards-entry staleness check.
        assert review_ready(complete_target(), incomplete_target(), SharedBackStatus.ASSIGNED) is False

    def test_ready_when_calibrated_and_assigned(self) -> None:
        assert review_ready(complete_target(), complete_target(), SharedBackStatus.ASSIGNED) is True

    def test_ready_when_calibrated_and_confirmed_none(self) -> None:
        # CONFIRMED_NONE never needs back_target to be complete -- there's
        # nothing to calibrate for an explicit "no Shared Back" deck.
        assert review_ready(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE) is True


class TestReviewGuidanceAndStatusText:
    def test_blocked_when_fronts_not_calibrated(self) -> None:
        headline, body = review_guidance_text(
            incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED, ReviewCardsState(),
        )
        assert headline == "Fronts hasn't been calibrated yet."
        assert "Calibrate" in body
        status = review_status_text(incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED, ReviewCardsState())
        assert "Calibrate" in status

    def test_blocked_when_shared_back_unresolved(self) -> None:
        headline, body = review_guidance_text(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, ReviewCardsState(),
        )
        assert headline == "Shared Back hasn't been decided yet."
        assert "Select Card Pages" in body
        status = review_status_text(complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, ReviewCardsState())
        assert "Select Card Pages" in status

    def test_blocked_when_assigned_but_back_not_yet_calibrated(self) -> None:
        headline, body = review_guidance_text(
            complete_target(), incomplete_target(), SharedBackStatus.ASSIGNED, ReviewCardsState(),
        )
        assert headline == "Shared Back hasn't been calibrated yet."
        assert "Calibrate" in body
        status = review_status_text(complete_target(), incomplete_target(), SharedBackStatus.ASSIGNED, ReviewCardsState())
        assert "Calibrate" in status

    def test_empty_grid_state(self) -> None:
        state = ReviewCardsState()
        state.sync([])
        headline, body = review_guidance_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert "couldn't fit any cards" in headline.lower()
        assert "Calibrate" in body
        status = review_status_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert "go back to calibrate" in status.lower()

    def test_all_included_state_mentions_total_and_deselect(self) -> None:
        state = ReviewCardsState()
        state.sync([ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)])
        headline, body = review_guidance_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert headline == "Check your cards."
        assert "2 cards found" in body
        status = review_status_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert status == "2 of 2 cards included."

    def test_partially_included_state_reports_the_split(self) -> None:
        state = ReviewCardsState()
        a, b = ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)
        state.sync([a, b])
        state.toggle(b)
        _, body = review_guidance_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert "1 of 2 cards included" in body
        status = review_status_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert status == "1 of 2 cards included."

    def test_confirmed_none_shared_back_does_not_block(self) -> None:
        state = ReviewCardsState()
        state.sync([ReviewCard(2, 0, 0)])
        headline, _ = review_guidance_text(
            complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, state,
        )
        assert headline == "Check your cards."

    def test_singular_card_wording(self) -> None:
        state = ReviewCardsState()
        state.sync([ReviewCard(2, 0, 0)])
        _, body = review_guidance_text(complete_target(), complete_target(), SharedBackStatus.ASSIGNED, state)
        assert "1 card found" in body
