from pathlib import Path

import pytest

from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrationTarget
from deckforge_gui.export_state import (
    ExportPlan,
    build_export_plan,
    existing_output_files,
    export_guidance_text,
    export_ready,
    export_status_text,
    predicted_output_filenames,
    review_snapshot_is_current,
    stale_review_guidance_text,
    stale_review_status_text,
)
from deckforge_gui.find_cards_state import BackMode, FindCardsState, PageRole, SharedBackStatus
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


class TestExistingOutputFiles:
    def _plan(self, card_count: int, has_back: bool):
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, i) for i in range(card_count)])
        back_status = SharedBackStatus.ASSIGNED if has_back else SharedBackStatus.CONFIRMED_NONE
        back_target = complete_target(page_num=9) if has_back else incomplete_target()
        return build_export_plan(review_state, complete_target(), back_target, back_status)

    def test_predicted_filenames_match_cell_export_convention(self) -> None:
        plan = self._plan(2, has_back=True)
        assert predicted_output_filenames(plan) == ["front_001.png", "front_002.png", "back.png"]

    def test_no_collisions_in_an_empty_folder(self, tmp_path: Path) -> None:
        plan = self._plan(2, has_back=False)
        assert existing_output_files(tmp_path, plan) == []

    def test_detects_a_colliding_front_file(self, tmp_path: Path) -> None:
        plan = self._plan(2, has_back=False)
        (tmp_path / "front_001.png").write_bytes(b"old")
        assert existing_output_files(tmp_path, plan) == ["front_001.png"]

    def test_detects_a_colliding_back_file(self, tmp_path: Path) -> None:
        plan = self._plan(1, has_back=True)
        (tmp_path / "back.png").write_bytes(b"old")
        assert existing_output_files(tmp_path, plan) == ["back.png"]

    def test_unrelated_files_are_not_flagged(self, tmp_path: Path) -> None:
        plan = self._plan(1, has_back=False)
        (tmp_path / "notes.txt").write_bytes(b"old")
        assert existing_output_files(tmp_path, plan) == []


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


def paired_find_cards_state(front_pages: list[int], back_pages: list[int]) -> FindCardsState:
    """A FindCardsState with the given Front/Back page markings -- 2+
    Back pages resolves back_mode() to PAIRED unambiguously (no need for
    the one-page mark_single_back_page_as_paired() override)."""
    state = FindCardsState()
    for page in front_pages:
        state.set_role(page, PageRole.FRONT)
    for page in back_pages:
        state.set_role(page, PageRole.BACK)
    return state


class TestExportPlanMutualExclusivity:
    def test_back_and_paired_back_together_is_rejected(self) -> None:
        with pytest.raises(AssertionError):
            ExportPlan(
                front_cells=(ReviewCard(2, 0, 0),),
                front_geometry=make_geometry().to_grid_geometry(),
                back=(9, make_geometry().to_grid_geometry()),
                paired_back=(make_geometry().to_grid_geometry(), (5,)),
            )

    def test_has_paired_back_reflects_the_paired_back_field(self) -> None:
        plan = ExportPlan(
            front_cells=(ReviewCard(2, 0, 0),),
            front_geometry=make_geometry().to_grid_geometry(),
            paired_back=(make_geometry().to_grid_geometry(), (5,)),
        )
        assert plan.has_paired_back is True
        assert plan.has_back is False


class TestBuildExportPlanPaired:
    def test_plan_resolves_a_back_page_per_front_cell(self) -> None:
        # Front pages [2, 3] pair (ordered-index) with Back pages [5, 6]:
        # page 2 -> page 5, page 3 -> page 6.
        find_cards = paired_find_cards_state([2, 3], [5, 6])
        review_state = ReviewCardsState()
        cell_2a, cell_2b, cell_3a = ReviewCard(2, 0, 0), ReviewCard(2, 0, 1), ReviewCard(3, 0, 0)
        review_state.sync([cell_2a, cell_2b, cell_3a])

        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED,
            back_mode=BackMode.PAIRED,
            paired_back_target=complete_target(page_num=5, card_width=222.0),
            find_cards_state=find_cards,
        )

        assert plan.has_back is False
        assert plan.has_paired_back is True
        back_geometry, back_pages = plan.paired_back
        assert back_geometry.card_width == 222.0
        assert back_pages == (5, 5, 6)  # both page-2 cells pair with page 5; the page-3 cell with page 6

    def test_plan_reuses_each_cells_own_row_and_col_implicitly(self) -> None:
        # paired_back only carries a page number per cell -- the (row,
        # col) itself comes straight from front_cells, so a caller
        # cropping this plan must reuse cells[i]'s own (row, col), never
        # (0, 0). Asserting the cell list and the page list line up 1:1
        # is what guarantees that. Two Back pages ([5, 6]) so back_mode()
        # resolves to PAIRED unambiguously (a single Back page is the
        # genuinely-ambiguous case -- see find_cards_state.py -- and
        # would need the explicit override this test isn't about).
        find_cards = paired_find_cards_state([2, 3], [5, 6])
        review_state = ReviewCardsState()
        cell = ReviewCard(2, 1, 2)
        review_state.sync([cell])

        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED,
            back_mode=BackMode.PAIRED,
            paired_back_target=complete_target(page_num=5),
            find_cards_state=find_cards,
        )
        assert plan.front_cells == (cell,)
        assert plan.paired_back[1] == (5,)  # front page 2 is index 0 -> back page 5

    def test_excluded_cards_are_not_in_the_plan_or_the_paired_back_list(self) -> None:
        find_cards = paired_find_cards_state([2, 3], [5, 6])
        review_state = ReviewCardsState()
        a, b = ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)
        review_state.sync([a, b])
        review_state.toggle(b)  # exclude b

        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED,
            back_mode=BackMode.PAIRED,
            paired_back_target=complete_target(page_num=5),
            find_cards_state=find_cards,
        )
        assert plan.front_cells == (a,)
        assert plan.paired_back[1] == (5,)  # exactly one entry, matching the one included cell

    def test_front_only_and_shared_back_plans_are_unaffected(self) -> None:
        # back_mode defaults to SHARED -- omitting it entirely (as
        # ExportWorkspace still does as of Phase 5B) must reproduce
        # exactly today's Front Only/Shared Back plan shape.
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        plan = build_export_plan(review_state, complete_target(), incomplete_target(), SharedBackStatus.CONFIRMED_NONE)
        assert plan.has_back is False
        assert plan.has_paired_back is False
        assert plan.paired_back is None


class TestExportReadyPaired:
    def _balanced(self) -> FindCardsState:
        return paired_find_cards_state([2, 3], [5, 6])

    def _unbalanced(self) -> FindCardsState:
        # 3 Front pages vs. 2 Back pages -- both counts are 2+, so
        # back_mode() resolves to PAIRED unambiguously (not the
        # single-Back-page ambiguous case), and the mismatch is real.
        return paired_find_cards_state([2, 3, 4], [5, 6])

    def test_ready_when_paired_and_balanced(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            find_cards_state=self._balanced(),
        ) is True

    def test_not_ready_when_paired_and_unbalanced(self) -> None:
        # The hard gate export_ready() adds beyond review_ready(): Export
        # refuses to run at all rather than silently omit a back file for
        # some cards (see export_ready()'s docstring).
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            find_cards_state=self._unbalanced(),
        ) is False

    def test_not_ready_when_paired_back_not_calibrated(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=incomplete_target(),
            find_cards_state=self._balanced(),
        ) is False

    def test_not_ready_when_topology_mismatches(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        assert export_ready(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            paired_topology_ok=False, find_cards_state=self._balanced(),
        ) is False


class TestGuidanceAndStatusTextPaired:
    def test_unbalanced_counts_message(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        headline, body = export_guidance_text(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            find_cards_state=paired_find_cards_state([2, 3, 4], [5, 6]),
        )
        assert headline == "Front and Back page counts don't match."
        assert "Select Card Pages" in body
        status = export_status_text(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            find_cards_state=paired_find_cards_state([2, 3, 4], [5, 6]),
        )
        assert "don't match" in status

    def test_ready_message_mentions_paired_back(self) -> None:
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])
        headline, body = export_guidance_text(
            complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED, review_state,
            back_mode=BackMode.PAIRED, paired_back_target=complete_target(page_num=5),
            find_cards_state=paired_find_cards_state([2, 3], [5, 6]),
        )
        assert headline == "Ready to export."
        assert "paired back" in body
        assert "shared back" not in body


class TestPredictedOutputFilenamesPaired:
    def test_paired_plan_uses_the_paired_filename_convention(self) -> None:
        find_cards = paired_find_cards_state([2, 3], [5, 6])
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)])
        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), SharedBackStatus.UNRESOLVED,
            back_mode=BackMode.PAIRED,
            paired_back_target=complete_target(page_num=5),
            find_cards_state=find_cards,
        )
        assert predicted_output_filenames(plan) == [
            "001_front.png", "001_back.png", "002_front.png", "002_back.png",
        ]


class TestOnePageParedBackDeckExport:
    """One Front page + one Back page is the genuinely ambiguous case
    (see find_cards_state.py's "EXACTLY ONE BACK PAGE IS GENUINELY
    AMBIGUOUS"): back_mode() defaults to SHARED at that count unless the
    explicit mark_single_back_page_as_paired() override is set. Every
    other PAIRED test in this file uses 2+ Back pages, where the count
    alone already resolves to PAIRED -- this regression instead exercises
    the one-page-deck-explicitly-opted-into-Paired path end-to-end
    through Export, since that's the one case where a bug could silently
    fall back to being treated as Shared Back instead."""

    def _one_page_paired_find_cards(self) -> FindCardsState:
        state = FindCardsState()
        state.set_role(2, PageRole.FRONT)
        state.set_role(5, PageRole.BACK)
        state.mark_single_back_page_as_paired()
        assert state.back_mode() is BackMode.PAIRED
        assert state.paired_page_counts_balanced() is True
        return state

    def test_export_ready_is_true(self) -> None:
        find_cards = self._one_page_paired_find_cards()
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])

        assert export_ready(
            complete_target(), incomplete_target(), find_cards.shared_back_status(), review_state,
            back_mode=find_cards.back_mode(),
            paired_back_target=complete_target(page_num=5),
            find_cards_state=find_cards,
        ) is True

    def test_build_export_plan_produces_paired_back_not_shared_back(self) -> None:
        find_cards = self._one_page_paired_find_cards()
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])

        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), find_cards.shared_back_status(),
            back_mode=find_cards.back_mode(),
            paired_back_target=complete_target(page_num=5, card_width=222.0),
            find_cards_state=find_cards,
        )

        assert plan.has_paired_back is True
        assert plan.has_back is False
        assert plan.back is None
        back_geometry, back_pages = plan.paired_back
        assert back_geometry.card_width == 222.0
        assert back_pages == (5,)  # the single Back page resolves correctly

    def test_predicted_filenames_use_the_paired_convention(self) -> None:
        find_cards = self._one_page_paired_find_cards()
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])

        plan = build_export_plan(
            review_state, complete_target(), incomplete_target(), find_cards.shared_back_status(),
            back_mode=find_cards.back_mode(),
            paired_back_target=complete_target(page_num=5),
            find_cards_state=find_cards,
        )

        assert predicted_output_filenames(plan) == ["001_front.png", "001_back.png"]
