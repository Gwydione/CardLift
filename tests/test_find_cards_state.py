from deckforge_gui.find_cards_state import (
    FindCardsState,
    PageRole,
    SharedBackStatus,
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


def test_only_one_page_may_hold_the_back_role():
    state = FindCardsState()
    state.set_role(5, PageRole.BACK)
    state.set_role(8, PageRole.BACK)
    assert state.back_page() == 8
    assert state.role_for_page(5) is None


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

    def test_toggling_back_moves_it_from_a_previous_page(self) -> None:
        state = FindCardsState()
        state.toggle_back(5)
        state.toggle_back(8)
        assert state.back_page() == 8
        assert state.role_for_page(5) is None

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
        assert "Shared Back: not yet decided." in text

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
        assert "Shared Back: not yet decided." in text

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
        assert "Shared Back: none." in text


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
