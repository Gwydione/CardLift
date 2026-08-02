import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.find_cards_workspace import FindCardsView, FindCardsWorkspace, fit_scale

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "CardLift_Demo_Deck.pdf"
SAMPLE_PDF_PAGE_COUNT = 12


def test_fit_scale_downscales_to_fit_available_space():
    assert fit_scale(2000, 1000, 1000, 1000) == 0.5


def test_fit_scale_never_upscales_past_native_resolution():
    assert fit_scale(400, 300, 2000, 2000) == 1.0


def test_fit_scale_picks_the_more_constraining_axis():
    # Width would allow 0.5, height would allow 0.25 -- height wins.
    assert fit_scale(1000, 2000, 500, 500) == 0.25


def test_fit_scale_handles_degenerate_dimensions():
    assert fit_scale(0, 100, 500, 500) == 1.0
    assert fit_scale(100, 100, 0, 500) == 1.0


def test_view_fitting_centers_a_letterboxed_image():
    # Image narrower than the widget at its fit scale -- expect horizontal
    # centering (nonzero offset_x), no vertical letterboxing (offset_y 0).
    view = FindCardsView.fitting(image_w=400, image_h=800, widget_w=800, widget_h=800, render_scale=2.0)
    assert view.display_scale == 1.0
    assert view.offset_x == 200.0
    assert view.offset_y == 0.0


def test_image_rect_reflects_fit_scale_and_offsets():
    view = FindCardsView.fitting(image_w=400, image_h=800, widget_w=800, widget_h=800, render_scale=2.0)
    x, y, w, h = view.image_rect(400, 800)
    assert (x, y) == (view.offset_x, view.offset_y)
    assert (w, h) == (400 * view.display_scale, 800 * view.display_scale)


def test_image_rect_is_stable_across_a_resize():
    """A page's role badge is drawn relative to image_rect()'s origin, so
    it must land in the same visual spot on the page regardless of widget
    size -- resizing only changes display_scale/offsets, never where the
    image content itself sits within its own bounds."""
    small = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=600, widget_h=800, render_scale=2.0)
    large = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=1200, widget_h=1600, render_scale=2.0)

    small_x, small_y, small_w, small_h = small.image_rect(1200, 1600)
    large_x, large_y, large_w, large_h = large.image_rect(1200, 1600)

    # Both should fit exactly (no letterboxing at these proportions), just
    # at different absolute scales.
    assert small_w / small_h == large_w / large_h


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def workspace(qapp: QApplication) -> FindCardsWorkspace:
    ws = FindCardsWorkspace(FindCardsState())
    ws.resize(800, 600)
    ws.show()
    ws.set_pdf(SAMPLE_PDF, SAMPLE_PDF_PAGE_COUNT)
    qapp.processEvents()
    return ws


class TestBackToggleWording:
    """Approved decision 1 (Phase 2 brief): the per-page action is
    mode-neutral -- "Mark as Back", never "Set as Shared Back" -- with
    inverse wording once the current page already holds the role,
    mirroring review_workspace.py's Include/Exclude toggle pattern."""

    def test_default_wording_is_mark_as_back(self, workspace: FindCardsWorkspace) -> None:
        assert workspace._back_btn.text() == "Mark as Back"

    def test_inverse_wording_once_the_current_page_is_marked_back(self, workspace: FindCardsWorkspace) -> None:
        workspace._on_back_toggled()
        assert workspace._back_btn.text() == "Unmark as Back"

    def test_wording_reverts_once_unmarked(self, workspace: FindCardsWorkspace) -> None:
        workspace._on_back_toggled()
        workspace._on_back_toggled()
        assert workspace._back_btn.text() == "Mark as Back"

    def test_marked_wording_is_exactly_unmark_as_back_not_a_corrupted_variant(
        self, workspace: FindCardsWorkspace,
    ) -> None:
        """Manual verification reported the button reading "Jnmark as
        Back". Byte-level inspection of find_cards_workspace.py confirmed
        the source literal is the plain-ASCII "Unmark as Back" (0x55 'U'),
        with no homoglyph, invisible character, or custom font applied to
        this button -- i.e. a rendering artifact, not a copy typo. This
        assertion pins the exact string (Python string equality is
        codepoint-exact, so it already catches a homoglyph substitution)
        and additionally proves it's pure ASCII, so a future edit that
        silently introduces a look-alike Unicode character or truncates
        the leading "U" fails loudly here rather than only reappearing as
        a hard-to-diagnose rendering glitch."""
        workspace._on_back_toggled()
        text = workspace._back_btn.text()
        assert text == "Unmark as Back"
        assert text.encode("ascii") == b"Unmark as Back"


class TestDeckSummaryWording:
    """Approved decision 2: deck summary copy must distinguish Shared Back
    from Paired Backs, sourced from find_cards_state.back_summary_clause()
    rather than the workspace re-deriving back_mode() itself."""

    def test_one_back_page_produces_shared_back_copy(self, workspace: FindCardsWorkspace) -> None:
        workspace.state.set_role(1, PageRole.FRONT)
        workspace.state.set_role(2, PageRole.BACK)
        workspace._refresh()
        assert workspace._back_summary_label.text() == "Shared Back: page 2."

    def test_two_or_more_back_pages_produce_paired_backs_copy(self, workspace: FindCardsWorkspace) -> None:
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        assert workspace._back_summary_label.text() == "Paired Backs: 3 pages each."


class TestContinueValidationForPairedBacks:
    """Approved decision 3: Continue must be blocked while Paired Backs'
    Front/Back page counts don't match, with a clear explanation, and
    become available once they do (plus every other existing
    requirement)."""

    def test_matched_paired_counts_allow_continue(self, workspace: FindCardsWorkspace) -> None:
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        assert workspace._continue_btn.isEnabled() is True

    def test_mismatched_paired_counts_block_continue(self, workspace: FindCardsWorkspace) -> None:
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        assert workspace._continue_btn.isEnabled() is False
        assert "mark 1 more Back page to continue" in workspace._back_summary_label.text()

    def test_continue_click_is_a_no_op_while_mismatched(self, workspace: FindCardsWorkspace) -> None:
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        emitted: list[bool] = []
        workspace.continue_clicked.connect(lambda: emitted.append(True))
        workspace._on_continue_clicked()
        assert emitted == []

    def test_resolving_the_mismatch_reenables_continue(self, workspace: FindCardsWorkspace) -> None:
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        assert workspace._continue_btn.isEnabled() is False
        workspace.state.set_role(6, PageRole.BACK)
        workspace._refresh()
        assert workspace._continue_btn.isEnabled() is True

    def test_matched_paired_counts_actually_advance_on_click(self, workspace: FindCardsWorkspace) -> None:
        """Regression test: shared_back_resolved() is scoped to the zero/
        one-BACK-page decision only and is always False once back_mode()
        is PAIRED (back_page() returns None for 2+ pages) -- gating
        _on_continue_clicked() on it alone silently swallowed a click on a
        fully valid, balanced Paired Backs deck instead of advancing.
        Verified against the enabled button too, not just the click
        outcome, since the button being enabled while the click does
        nothing was exactly the bug."""
        for page in (1, 2, 3):
            workspace.state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            workspace.state.set_role(page, PageRole.BACK)
        workspace._refresh()
        assert workspace._continue_btn.isEnabled() is True
        emitted: list[bool] = []
        workspace.continue_clicked.connect(lambda: emitted.append(True))
        workspace._on_continue_clicked()
        assert emitted == [True]


class TestPairedModeSuppressesNoBackPrompt:
    """Approved decision 4: the "confirm there's no Back" prompt must not
    appear for Paired Back decks, while the genuine unresolved/confirmed
    zero-back cases behave exactly as before."""

    def test_confirm_button_hidden_once_paired(self, workspace: FindCardsWorkspace) -> None:
        workspace.state.set_role(1, PageRole.FRONT)
        workspace.state.set_role(4, PageRole.BACK)
        workspace.state.set_role(5, PageRole.BACK)
        workspace.state.note_page_viewed(SAMPLE_PDF_PAGE_COUNT)
        workspace.state.note_continue_attempted()
        workspace._refresh()
        assert workspace._confirm_no_back_btn.isVisibleTo(workspace) is False

    def test_confirm_button_still_shown_for_genuine_unresolved_case(self, workspace: FindCardsWorkspace) -> None:
        workspace.state.set_role(1, PageRole.FRONT)
        workspace.state.note_page_viewed(SAMPLE_PDF_PAGE_COUNT)
        workspace._refresh()
        assert workspace._confirm_no_back_btn.isVisibleTo(workspace) is True

    def test_confirming_no_back_still_works_unchanged(self, workspace: FindCardsWorkspace) -> None:
        workspace.state.set_role(1, PageRole.FRONT)
        workspace.state.note_page_viewed(SAMPLE_PDF_PAGE_COUNT)
        workspace._refresh()
        workspace._on_confirm_no_back()
        assert workspace._back_summary_label.text() == "Front Only — no Back Pages."
        assert workspace._confirm_no_back_btn.isVisibleTo(workspace) is False
