from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrationTarget
from deckforge_gui.export_state import (
    build_export_plan,
    export_guidance_text,
    export_ready,
    export_status_text,
    review_snapshot_is_current,
    stale_review_guidance_text,
    stale_review_status_text,
)
from deckforge_gui.find_cards_state import SharedBackStatus
from deckforge_gui.review_state import ReviewCard, ReviewCardsState


def make_geometry(**overrides) -> CalibratedGeometry:
    data = dict(
        left=0.0, top=0.0, card_width=100.0, card_height=150.0,
        gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
    )
    data.update(overrides)
    return CalibratedGeometry(**data)


def complete_target(page_num=2, **geometry_overrides) -> CalibrationTarget:
    return CalibrationTarget(geometry=make_geometry(**geometry_overrides), calibrated_page_num=page_num)


def incomplete_target() -> CalibrationTarget:
    return CalibrationTarget()


class TestBuildExportPlan:
    def test_plan_carries_only_included_cells_in_order(self) -> None:
        review_state = ReviewCardsState()
        a, b, c = ReviewCard(2, 0, 0), ReviewCard(2, 0, 1), ReviewCard(2, 0, 2)
        review_state.sync([a, b, c])
        review_state.toggle(b)  # exclude b

        plan = build_export_plan(review_state, complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE)
        assert plan.front_cells == (a, c)
        assert plan.card_count == 2

    def test_plan_includes_back_when_assigned(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        back = complete_target(page_num=9, card_width=200.0)

        plan = build_export_plan(review_state, complete_target(), back, SharedBackStatus.ASSIGNED)
        assert plan.has_back is True
        back_page, back_geometry = plan.back
        assert back_page == 9
        assert back_geometry.card_width == 200.0

    def test_plan_omits_back_when_confirmed_none(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])

        plan = build_export_plan(review_state, complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE)
        assert plan.has_back is False
        assert plan.back is None

    def test_plan_geometry_matches_calibrated_geometry(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        cards = complete_target(left=12.5, top=7.0, card_width=90.0, card_height=140.0, gap_x=1.0, gap_y=2.0)

        plan = build_export_plan(review_state, cards, incomplete_target(), SharedBackStatus.CONFIRMED_NONE)
        assert plan.front_geometry.left == 12.5
        assert plan.front_geometry.top == 7.0
        assert plan.front_geometry.card_width == 90.0
        assert plan.front_geometry.card_height == 140.0
        assert plan.front_geometry.gap_x == 1.0
        assert plan.front_geometry.gap_y == 2.0


class TestExportReady:
    def test_not_ready_when_review_not_ready(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED, review_state) is False

    def test_not_ready_when_no_cards_included(self) -> None:
        review_state = ReviewCardsState()
        card = ReviewCard(2, 0, 0)
        review_state.sync([card])
        review_state.toggle(card)  # exclude the only card
        assert export_ready(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state) is False

    def test_ready_when_calibrated_and_cards_included(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state) is True


class TestReviewSnapshotIsCurrent:
    def _page_size(self, page_num: int) -> tuple[float, float]:
        return (300.0, 300.0)  # fits a 3x3 grid of 100x150... actually see per-test geometry

    def test_current_when_nothing_changed(self) -> None:
        cards = complete_target(card_width=100.0, card_height=150.0)
        review_state = ReviewCardsState()

        def page_size(page_num: int) -> tuple[float, float]:
            return (300.0, 300.0)  # 3 cols x 2 rows

        from deckforge_gui.review_state import build_review_cards
        current = build_review_cards([2], cards.geometry, page_size)
        review_state.sync(current)

        assert review_snapshot_is_current(review_state, [2], cards, page_size) is True

    def test_stale_after_recalibration_changes_suggested_grid(self) -> None:
        review_state = ReviewCardsState()

        def page_size(page_num: int) -> tuple[float, float]:
            return (300.0, 300.0)

        from deckforge_gui.review_state import build_review_cards
        original = complete_target(card_width=100.0, card_height=150.0)
        review_state.sync(build_review_cards([2], original.geometry, page_size))

        # Same page recalibrated with a different card size -> a
        # different suggested grid, but calibrated_page_num unchanged so
        # cards_is_stale() (a different, structural check) would not
        # catch this.
        recalibrated = complete_target(card_width=140.0, card_height=150.0)
        assert review_snapshot_is_current(review_state, [2], recalibrated, page_size) is False

    def test_stale_when_a_front_page_is_added(self) -> None:
        review_state = ReviewCardsState()

        def page_size(page_num: int) -> tuple[float, float]:
            return (300.0, 300.0)

        from deckforge_gui.review_state import build_review_cards
        cards = complete_target(card_width=100.0, card_height=150.0)
        review_state.sync(build_review_cards([2], cards.geometry, page_size))

        # A second front page was added in Select Card Pages, but Review
        # Cards was never revisited to sync it in.
        assert review_snapshot_is_current(review_state, [2, 3], cards, page_size) is False

    def test_vacuously_current_when_not_calibrated(self) -> None:
        review_state = ReviewCardsState()
        assert review_snapshot_is_current(review_state, [2], incomplete_target(), self._page_size) is True


class TestGuidanceAndStatusText:
    def test_delegates_to_review_text_when_not_ready(self) -> None:
        review_state = ReviewCardsState()
        headline, body = export_guidance_text(incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED, review_state)
        assert headline == "Fronts hasn't been calibrated yet."
        status = export_status_text(incomplete_target(), complete_target(), SharedBackStatus.ASSIGNED, review_state)
        assert "Calibrate" in status

    def test_no_cards_included_message(self) -> None:
        review_state = ReviewCardsState()
        card = ReviewCard(2, 0, 0)
        review_state.sync([card])
        review_state.toggle(card)
        headline, body = export_guidance_text(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state)
        assert headline == "No cards are included."
        assert "Review Cards" in body
        assert export_status_text(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state) == \
            "No cards included — go back to Review Cards."

    def test_ready_message_mentions_count(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)])
        headline, body = export_guidance_text(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state)
        assert headline == "Ready to export."
        assert "2 cards" in body
        assert "shared back" not in body
        assert export_status_text(complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE, review_state) == "Ready to export 2 cards."

    def test_ready_message_mentions_shared_back_when_assigned(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        _, body = export_guidance_text(complete_target(), complete_target(page_num=9), SharedBackStatus.ASSIGNED, review_state)
        assert "shared back" in body

    def test_stale_guidance_and_status_wording(self) -> None:
        headline, body = stale_review_guidance_text()
        assert headline == "Your calibration changed."
        assert "Review Cards" in body
        assert "Review Cards" in stale_review_status_text()
