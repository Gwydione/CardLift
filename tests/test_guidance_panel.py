"""Regression coverage for GuidancePanel's EXPORT branch (Phase 5C
follow-up): _guidance_text() used to call export_guidance_text() with only
its original 4 positional arguments, so a Paired Backs deck's real
back_mode/paired_back_target/find_cards_state were never threaded through
-- the panel evaluated every deck as if back_mode defaulted to SHARED,
same class of bug ExportWorkspace itself had before Phase 5C. The fix
mirrors the WorkflowStep.REVIEW_CARDS branch immediately above it in
guidance_panel.py, which already threads this same context and already
documents why paired_topology_ok is left at its default (True): the real
page-size-dependent comparison needs an open PDFRenderer, which only
ExportWorkspace/ReviewWorkspace have, not this panel.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from deckforge_gui.app_state import AppState, WorkflowStep
from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrateState, CalibrationTarget
from deckforge_gui.export_state import export_guidance_text
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.guidance_panel import GuidancePanel
from deckforge_gui.review_state import ReviewCard, ReviewCardsState


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


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


def make_panel(qapp: QApplication) -> GuidancePanel:
    state = AppState(current_step=WorkflowStep.EXPORT)
    return GuidancePanel(state, CalibrateState(), FindCardsState(), ReviewCardsState())


class TestExportGuidancePaired:
    def _paired_find_cards(self, front_pages: list[int], back_pages: list[int]) -> FindCardsState:
        """2+ Back pages resolves back_mode() to PAIRED unambiguously --
        see find_cards_state.py's "EXACTLY ONE BACK PAGE IS GENUINELY
        AMBIGUOUS" for why a single Back page would need the explicit
        mark_single_back_page_as_paired() override instead."""
        state = FindCardsState()
        for page in front_pages:
            state.set_role(page, PageRole.FRONT)
        for page in back_pages:
            state.set_role(page, PageRole.BACK)
        return state

    def test_ready_paired_export_guidance_is_accurate(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state = self._paired_find_cards([2, 3], [5, 6])
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.calibrate_state.paired_back = complete_target(page_num=5)
        panel.review_cards_state.sync([ReviewCard(2, 0, 0)])

        headline, body = panel._guidance_text()

        assert headline == "Ready to export."
        assert "paired back" in body
        assert "shared back" not in body

    def test_incomplete_paired_calibration_is_described_accurately(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state = self._paired_find_cards([2, 3], [5, 6])
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.calibrate_state.paired_back = incomplete_target()  # never calibrated
        panel.review_cards_state.sync([ReviewCard(2, 0, 0)])

        headline, body = panel._guidance_text()

        assert headline == "Paired Back hasn't been calibrated yet."
        assert "Calibrate" in body

    def test_topology_mismatch_wording_is_accurate_at_the_wired_call_shape(self, qapp: QApplication) -> None:
        """GuidancePanel itself cannot detect a real topology mismatch --
        that needs an open PDFRenderer to compare both pages' actual
        point sizes, which only ExportWorkspace (or ReviewWorkspace) has;
        see guidance_panel.py's EXPORT branch comment and export_state.
        export_ready()'s docstring for this same accepted, documented
        narrowing already established for Review Cards' own guidance
        wiring. What this proves instead: calling export_guidance_text()
        with the *exact* argument shape guidance_panel.py's EXPORT branch
        now uses (back_mode, paired_back_target, find_cards_state), plus
        the one additional piece of information a renderer-equipped
        caller (ExportWorkspace) would supply -- paired_topology_ok=False
        -- correctly describes the mismatch. If ExportWorkspace's real
        detection ever flows through this same call shape, the wording
        is already correct; nothing about it needs re-deriving here."""
        cards_target = complete_target(page_num=2)
        paired_back_target = complete_target(page_num=5)
        find_cards = self._paired_find_cards([2, 3], [5, 6])
        review_state = ReviewCardsState()
        review_state.sync([ReviewCard(2, 0, 0)])

        headline, body = export_guidance_text(
            cards_target, CalibrationTarget(), find_cards.shared_back_status(), review_state,
            back_mode=find_cards.back_mode(),
            paired_back_target=paired_back_target,
            paired_topology_ok=False,
            find_cards_state=find_cards,
        )

        assert headline == "Front and Back grids don't match."
        assert "Calibrate" in body

    def test_one_page_paired_deck_guidance_is_accurate(self, qapp: QApplication) -> None:
        """The genuinely ambiguous one-Front-page/one-Back-page case,
        explicitly opted into Paired -- regression coverage matching the
        one already added for build_export_plan() in Phase 5B, now
        proven through GuidancePanel's real wiring too."""
        panel = make_panel(qapp)
        find_cards = FindCardsState()
        find_cards.set_role(2, PageRole.FRONT)
        find_cards.set_role(5, PageRole.BACK)
        find_cards.mark_single_back_page_as_paired()
        panel.find_cards_state = find_cards
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.calibrate_state.paired_back = complete_target(page_num=5)
        panel.review_cards_state.sync([ReviewCard(2, 0, 0)])

        headline, body = panel._guidance_text()

        assert headline == "Ready to export."
        assert "paired back" in body


class TestExportGuidanceFrontOnlyAndSharedBackUnchanged:
    """The whole point of this fix is additive -- Front Only and Shared
    Back must produce byte-identical guidance to before, since their
    back_mode()/paired_back_target values were already correct and the
    new parameters were only ever missing for PAIRED."""

    def test_front_only_no_cards_included(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state.confirm_no_shared_back()
        panel.calibrate_state.cards = complete_target(page_num=2)
        card = ReviewCard(2, 0, 0)
        panel.review_cards_state.sync([card])
        panel.review_cards_state.toggle(card)  # exclude the only card

        headline, body = panel._guidance_text()

        assert headline == "No cards are included."
        assert "Review Cards" in body

    def test_front_only_ready(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state.confirm_no_shared_back()
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.review_cards_state.sync([ReviewCard(2, 0, 0), ReviewCard(2, 0, 1)])

        headline, body = panel._guidance_text()

        assert headline == "Ready to export."
        assert "2 cards" in body
        assert "shared back" not in body
        assert "paired back" not in body

    def test_shared_back_ready(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state.set_role(2, PageRole.FRONT)
        panel.find_cards_state.set_role(9, PageRole.BACK)
        assert panel.find_cards_state.back_mode().name == "SHARED"
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.calibrate_state.back = complete_target(page_num=9)
        panel.review_cards_state.sync([ReviewCard(2, 0, 0)])

        headline, body = panel._guidance_text()

        assert headline == "Ready to export."
        assert "shared back" in body
        assert "paired back" not in body

    def test_shared_back_not_yet_calibrated(self, qapp: QApplication) -> None:
        panel = make_panel(qapp)
        panel.find_cards_state.set_role(2, PageRole.FRONT)
        panel.find_cards_state.set_role(9, PageRole.BACK)
        panel.calibrate_state.cards = complete_target(page_num=2)
        panel.calibrate_state.back = incomplete_target()
        panel.review_cards_state.sync([ReviewCard(2, 0, 0)])

        headline, body = panel._guidance_text()

        assert headline == "Shared Back hasn't been calibrated yet."
