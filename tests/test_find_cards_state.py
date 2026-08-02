from deckforge_gui.find_cards_state import (
    BackMode,
    FindCardsState,
    PageRole,
    SharedBackStatus,
    back_summary_clause,
    continue_blocked_text,
    find_cards_status_text,
)


def test_default_state_has_no_roles():
    state = FindCardsState()
    assert state.current_page == 1
    assert state.front_page_count() == 0
    assert state.front_pages() == []
    assert state.back_page() is None
    assert state.role_for_page(1) is None
    assert state.shared_back_resolved() is False


def test_set_role_assigns_front():
    state = FindCardsState()
    state.set_role(3, PageRole.FRONT)
    assert state.role_for_page(3) is PageRole.FRONT
    assert state.front_pages() == [3]


def test_set_role_overwrites_existing_role_on_same_page():
    state = FindCardsState()
    state.set_role(2, PageRole.FRONT)
    state.set_role(2, PageRole.BACK)
    assert state.role_for_page(2) is PageRole.BACK
    assert state.front_pages() == []
    assert state.back_page() == 2


def test_front_pages_are_independent_across_pages():
    state = FindCardsState()
    state.set_role(2, PageRole.FRONT)
    state.set_role(5, PageRole.FRONT)
    assert state.front_page_count() == 2
    assert state.front_pages() == [2, 5]


def test_multiple_pages_may_hold_the_back_role():
    """Paired Back Pages needs several BACK pages at once -- BACK is now
    symmetric with FRONT rather than capped at a single page (see
    find_cards_state.py's "BACK ROLE: ANY NUMBER OF PAGES" docstring)."""
    state = FindCardsState()
    state.set_role(5, PageRole.BACK)
    state.set_role(8, PageRole.BACK)
    assert state.back_pages() == [5, 8]
    assert state.role_for_page(5) is PageRole.BACK
    assert state.role_for_page(8) is PageRole.BACK


def test_confirming_no_shared_back_is_a_no_op_while_a_back_page_is_assigned():
    state = FindCardsState()
    state.toggle_back(8)
    state.confirm_no_shared_back()
    assert state.back_confirmed_none is False
    assert state.back_page() == 8


def test_assigning_back_supersedes_a_prior_no_shared_back_confirmation():
    state = FindCardsState()
    state.confirm_no_shared_back()
    assert state.back_confirmed_none is True
    state.set_role(8, PageRole.BACK)
    assert state.back_confirmed_none is False
    assert state.back_page() == 8


def test_clear_role_removes_only_that_pages_role():
    state = FindCardsState()
    state.set_role(2, PageRole.FRONT)
    state.set_role(5, PageRole.BACK)
    state.clear_role(2)
    assert state.role_for_page(2) is None
    assert state.role_for_page(5) is PageRole.BACK
    assert state.front_page_count() == 0


def test_clear_role_on_unassigned_page_is_a_no_op():
    state = FindCardsState()
    state.clear_role(9)
    assert state.front_page_count() == 0


def test_clear_all_resets_roles_and_navigation():
    state = FindCardsState()
    state.set_role(2, PageRole.FRONT)
    state.set_role(5, PageRole.BACK)
    state.current_page = 5
    state.furthest_page_viewed = 5
    state.confirm_no_shared_back()
    state.clear_all()
    assert state.front_page_count() == 0
    assert state.back_page() is None
    assert state.back_confirmed_none is False
    assert state.current_page == 1
    assert state.furthest_page_viewed == 1


def test_current_page_is_mutable_navigation_state():
    state = FindCardsState()
    state.current_page = 4
    assert state.current_page == 4


class TestToggleFront:
    def test_toggling_an_unassigned_page_marks_it_front(self) -> None:
        state = FindCardsState()
        state.toggle_front(3)
        assert state.role_for_page(3) is PageRole.FRONT

    def test_toggling_a_front_page_again_clears_it(self) -> None:
        state = FindCardsState()
        state.toggle_front(3)
        state.toggle_front(3)
        assert state.role_for_page(3) is None

    def test_toggling_front_on_a_back_page_replaces_its_role(self) -> None:
        state = FindCardsState()
        state.toggle_back(3)
        state.toggle_front(3)
        assert state.role_for_page(3) is PageRole.FRONT
        assert state.back_page() is None


class TestToggleBack:
    def test_toggling_an_unassigned_page_marks_it_back(self) -> None:
        state = FindCardsState()
        state.toggle_back(8)
        assert state.back_page() == 8

    def test_toggling_a_back_page_again_clears_it(self) -> None:
        state = FindCardsState()
        state.toggle_back(8)
        state.toggle_back(8)
        assert state.back_page() is None

    def test_toggling_a_second_back_page_does_not_evict_the_first(self) -> None:
        state = FindCardsState()
        state.toggle_back(5)
        state.toggle_back(8)
        assert state.back_pages() == [5, 8]
        assert state.role_for_page(5) is PageRole.BACK
        assert state.role_for_page(8) is PageRole.BACK

    def test_toggling_back_on_a_front_page_replaces_its_role(self) -> None:
        """The mirror of TestToggleFront's
        test_toggling_front_on_a_back_page_replaces_its_role -- the same
        mutual-exclusivity invariant ("a page cannot be both Front and
        Shared Back") must hold in both assignment directions."""
        state = FindCardsState()
        state.toggle_front(3)
        state.toggle_back(3)
        assert state.role_for_page(3) is PageRole.BACK
        assert state.front_pages() == []


class TestBackPages:
    def test_empty_by_default(self) -> None:
        state = FindCardsState()
        assert state.back_pages() == []

    def test_returns_all_back_role_pages_sorted(self) -> None:
        state = FindCardsState()
        state.set_role(8, PageRole.BACK)
        state.set_role(5, PageRole.BACK)
        assert state.back_pages() == [5, 8]

    def test_back_page_returns_none_when_two_or_more_are_assigned(self) -> None:
        """back_page() only makes sense for the single-shared-back case --
        once Paired Back Pages is in play there is no single 'the' back
        page, so it must return None rather than an arbitrary one."""
        state = FindCardsState()
        state.set_role(5, PageRole.BACK)
        state.set_role(8, PageRole.BACK)
        assert state.back_page() is None


class TestBackMode:
    def test_none_with_no_back_pages(self) -> None:
        state = FindCardsState()
        assert state.back_mode() is BackMode.NONE

    def test_none_regardless_of_confirmed_none_or_unresolved(self) -> None:
        """back_mode() doesn't distinguish confirmed-none from
        not-yet-decided -- that distinction stays shared_back_status()'s
        job."""
        state = FindCardsState()
        assert state.back_mode() is BackMode.NONE
        state.confirm_no_shared_back()
        assert state.back_mode() is BackMode.NONE

    def test_shared_with_exactly_one_back_page(self) -> None:
        state = FindCardsState()
        state.set_role(8, PageRole.BACK)
        assert state.back_mode() is BackMode.SHARED

    def test_paired_with_two_back_pages(self) -> None:
        state = FindCardsState()
        state.set_role(5, PageRole.BACK)
        state.set_role(8, PageRole.BACK)
        assert state.back_mode() is BackMode.PAIRED

    def test_paired_with_more_than_two_back_pages(self) -> None:
        state = FindCardsState()
        for page in (2, 4, 6, 8):
            state.set_role(page, PageRole.BACK)
        assert state.back_mode() is BackMode.PAIRED


class TestPairedBackPageFor:
    def _paired_state(self) -> FindCardsState:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            state.set_role(page, PageRole.BACK)
        return state

    def test_pairs_by_sorted_index(self) -> None:
        state = self._paired_state()
        assert state.paired_back_page_for(1) == 4
        assert state.paired_back_page_for(2) == 5
        assert state.paired_back_page_for(3) == 6

    def test_pairing_follows_sorted_order_even_when_marked_out_of_order(self) -> None:
        """Pairing is by sorted-list position, not literal page-number
        arithmetic or marking order (approved design decision)."""
        state = FindCardsState()
        state.set_role(3, PageRole.FRONT)
        state.set_role(1, PageRole.FRONT)
        state.set_role(2, PageRole.FRONT)
        state.set_role(6, PageRole.BACK)
        state.set_role(4, PageRole.BACK)
        state.set_role(5, PageRole.BACK)
        assert state.paired_back_page_for(1) == 4
        assert state.paired_back_page_for(2) == 5
        assert state.paired_back_page_for(3) == 6

    def test_none_when_not_a_front_page(self) -> None:
        state = self._paired_state()
        assert state.paired_back_page_for(99) is None

    def test_none_when_mode_is_shared_not_paired(self) -> None:
        state = FindCardsState()
        state.set_role(1, PageRole.FRONT)
        state.set_role(4, PageRole.BACK)
        assert state.paired_back_page_for(1) is None

    def test_none_when_mode_is_none(self) -> None:
        state = FindCardsState()
        state.set_role(1, PageRole.FRONT)
        assert state.paired_back_page_for(1) is None

    def test_none_for_a_front_page_beyond_the_shorter_back_list(self) -> None:
        """Unbalanced page counts: the third front page has no
        corresponding back page at index 2."""
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            state.set_role(page, PageRole.BACK)
        assert state.paired_back_page_for(1) == 4
        assert state.paired_back_page_for(2) == 5
        assert state.paired_back_page_for(3) is None


class TestPairedPageCountsBalanced:
    def test_true_when_not_paired(self) -> None:
        state = FindCardsState()
        assert state.paired_page_counts_balanced() is True
        state.set_role(1, PageRole.FRONT)
        state.set_role(2, PageRole.BACK)
        assert state.paired_page_counts_balanced() is True

    def test_true_when_paired_counts_match(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            state.set_role(page, PageRole.BACK)
        assert state.paired_page_counts_balanced() is True

    def test_false_when_paired_counts_differ(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            state.set_role(page, PageRole.BACK)
        assert state.paired_page_counts_balanced() is False


class TestConfirmNoSharedBackWithPairedPages:
    def test_is_a_no_op_while_paired_back_pages_are_assigned(self) -> None:
        """confirm_no_shared_back()'s guard must check the full back-page
        set, not just back_page() (which also returns None for Paired
        mode) -- otherwise this could incorrectly mark 'no back' while
        Paired Back pages are actively assigned."""
        state = FindCardsState()
        state.set_role(1, PageRole.FRONT)
        state.set_role(4, PageRole.BACK)
        state.set_role(5, PageRole.BACK)
        state.confirm_no_shared_back()
        assert state.back_confirmed_none is False
        assert state.back_mode() is BackMode.PAIRED


class TestSharedBackStatus:
    def test_unresolved_before_any_decision(self) -> None:
        state = FindCardsState()
        assert state.shared_back_status() is SharedBackStatus.UNRESOLVED

    def test_assigned_once_a_back_page_is_set(self) -> None:
        state = FindCardsState()
        state.toggle_back(8)
        assert state.shared_back_status() is SharedBackStatus.ASSIGNED

    def test_confirmed_none_once_explicitly_confirmed(self) -> None:
        state = FindCardsState()
        state.confirm_no_shared_back()
        assert state.shared_back_status() is SharedBackStatus.CONFIRMED_NONE

    def test_clearing_the_assigned_back_page_returns_to_unresolved_not_confirmed_none(self) -> None:
        """The exact scenario the previous boolean-only model got wrong:
        removing an assigned back page must land back on UNRESOLVED, never
        silently become equivalent to CONFIRMED_NONE."""
        state = FindCardsState()
        state.toggle_back(8)
        state.toggle_back(8)
        assert state.shared_back_status() is SharedBackStatus.UNRESOLVED


class TestSharedBackResolution:
    def test_unresolved_before_any_decision(self) -> None:
        state = FindCardsState()
        assert state.shared_back_resolved() is False

    def test_resolved_once_a_back_page_is_assigned(self) -> None:
        state = FindCardsState()
        state.toggle_back(8)
        assert state.shared_back_resolved() is True

    def test_resolved_once_no_shared_back_is_confirmed(self) -> None:
        state = FindCardsState()
        state.confirm_no_shared_back()
        assert state.shared_back_resolved() is True

    def test_clearing_the_only_back_page_returns_to_unresolved(self) -> None:
        state = FindCardsState()
        state.toggle_back(8)
        state.toggle_back(8)
        assert state.shared_back_resolved() is False


class TestShouldPromptSharedBack:
    def test_no_prompt_before_any_front_page_is_marked(self) -> None:
        state = FindCardsState()
        state.note_page_viewed(10)
        assert state.should_prompt_shared_back(page_count=10) is False

    def test_no_prompt_before_the_last_page_is_reached(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_page_viewed(5)
        assert state.should_prompt_shared_back(page_count=10) is False

    def test_prompts_once_the_last_page_is_reached(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_page_viewed(10)
        assert state.should_prompt_shared_back(page_count=10) is True

    def test_no_prompt_once_a_back_page_is_assigned(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.toggle_back(10)
        state.note_page_viewed(10)
        assert state.should_prompt_shared_back(page_count=10) is False

    def test_no_prompt_once_no_shared_back_is_confirmed(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_page_viewed(10)
        state.confirm_no_shared_back()
        assert state.should_prompt_shared_back(page_count=10) is False

    def test_fallback_trigger_fires_on_continue_attempt_before_the_last_page(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_page_viewed(3)  # nowhere near the last page
        assert state.should_prompt_shared_back(page_count=10) is False
        state.note_continue_attempted()
        assert state.should_prompt_shared_back(page_count=10) is True

    def test_confirming_no_shared_back_clears_the_fallback_flag(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_continue_attempted()
        state.confirm_no_shared_back()
        assert state.continue_attempted is False

    def test_never_prompts_once_back_mode_is_paired(self) -> None:
        """Marking two or more BACK pages is itself an explicit answer --
        there is nothing left for the 'confirm no Shared Back' prompt to
        ask, even at the last page or after a blocked Continue attempt."""
        state = FindCardsState()
        state.toggle_front(1)
        state.toggle_back(4)
        state.toggle_back(5)
        state.note_page_viewed(10)
        state.note_continue_attempted()
        assert state.should_prompt_shared_back(page_count=10) is False


class TestBackSummaryClause:
    """back_summary_clause() is the single source find_cards_status_text()
    and FindCardsWorkspace._refresh_deck_summary() both build on -- see
    approved decision 2 (docs given in the Phase 2 brief): deck-level
    terminology must distinguish an unresolved no-back decision, Front
    Only, Shared Back, and Paired Backs."""

    def test_unresolved(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        assert back_summary_clause(state) == "Back: not yet decided"

    def test_front_only_confirmed_none(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.confirm_no_shared_back()
        assert back_summary_clause(state) == "Front Only — no Back Pages"

    def test_shared_back(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.toggle_back(8)
        assert back_summary_clause(state) == "Shared Back: page 8"

    def test_paired_backs_balanced(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            state.set_role(page, PageRole.BACK)
        assert back_summary_clause(state) == "Paired Backs: 3 pages each"

    def test_paired_backs_mismatched_more_fronts(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            state.set_role(page, PageRole.BACK)
        assert back_summary_clause(state) == "Paired Backs: 3 Front / 2 Back — mark 1 more Back page to continue"

    def test_paired_backs_mismatched_more_backs(self) -> None:
        state = FindCardsState()
        state.set_role(1, PageRole.FRONT)
        for page in (4, 5, 6):
            state.set_role(page, PageRole.BACK)
        assert back_summary_clause(state) == "Paired Backs: 1 Front / 3 Back — mark 2 more Front pages to continue"


class TestFindCardsStatusText:
    def test_no_pdf_loaded(self) -> None:
        state = FindCardsState()
        assert find_cards_status_text(state, page_count=0) == "Ready — open a PDF to begin."

    def test_no_front_pages_marked_yet(self) -> None:
        state = FindCardsState()
        text = find_cards_status_text(state, page_count=10)
        assert "mark at least one" in text.lower()

    def test_front_pages_marked_back_unresolved(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        text = find_cards_status_text(state, page_count=10)
        assert "1 front page marked" in text
        assert "Back: not yet decided." in text

    def test_unresolved_wording_does_not_depend_on_prompt_timing(self) -> None:
        """The Deck Summary's inline confirm CTA appears only once
        should_prompt_shared_back() is true, but that's a separate timing
        concern from the underlying fact -- the status text says "not yet
        decided" for SharedBackStatus.UNRESOLVED regardless of whether the
        last page has been reached yet (see find_cards_workspace.py's
        _refresh_deck_summary(), which uses the same wording)."""
        state = FindCardsState()
        state.toggle_front(2)
        state.note_page_viewed(10)  # would also trigger should_prompt_shared_back
        text = find_cards_status_text(state, page_count=10)
        assert "Back: not yet decided." in text

    def test_back_page_assigned(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.toggle_back(8)
        text = find_cards_status_text(state, page_count=10)
        assert "Shared Back: page 8." in text

    def test_back_confirmed_none(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.confirm_no_shared_back()
        text = find_cards_status_text(state, page_count=10)
        assert "Front Only — no Back Pages." in text

    def test_paired_backs_balanced(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5, 6):
            state.set_role(page, PageRole.BACK)
        text = find_cards_status_text(state, page_count=10)
        assert "Paired Backs: 3 pages each." in text

    def test_paired_backs_mismatched(self) -> None:
        state = FindCardsState()
        for page in (1, 2, 3):
            state.set_role(page, PageRole.FRONT)
        for page in (4, 5):
            state.set_role(page, PageRole.BACK)
        text = find_cards_status_text(state, page_count=10)
        assert "Paired Backs: 3 Front / 2 Back — mark 1 more Back page to continue." in text


class TestContinueBlockedText:
    def test_none_before_any_continue_attempt(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        assert continue_blocked_text(state) is None

    def test_message_shown_after_a_blocked_continue_attempt(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_continue_attempted()
        text = continue_blocked_text(state)
        assert text == "Choose a Shared Back or confirm that this deck has no Shared Back before continuing."

    def test_none_once_a_back_page_is_assigned_after_a_blocked_attempt(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_continue_attempted()
        state.toggle_back(8)
        assert continue_blocked_text(state) is None

    def test_none_once_no_shared_back_is_confirmed_after_a_blocked_attempt(self) -> None:
        state = FindCardsState()
        state.toggle_front(2)
        state.note_continue_attempted()
        state.confirm_no_shared_back()
        assert continue_blocked_text(state) is None


class TestReachedLastPage:
    def test_false_with_no_pages(self) -> None:
        state = FindCardsState()
        assert state.reached_last_page(page_count=0) is False

    def test_true_once_furthest_page_viewed_reaches_the_count(self) -> None:
        state = FindCardsState()
        state.note_page_viewed(10)
        assert state.reached_last_page(page_count=10) is True

    def test_furthest_page_viewed_is_monotonic(self) -> None:
        state = FindCardsState()
        state.note_page_viewed(8)
        state.note_page_viewed(3)  # navigating back doesn't regress it
        assert state.furthest_page_viewed == 8
