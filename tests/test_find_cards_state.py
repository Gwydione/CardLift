from deckforge_gui.find_cards_state import FindCardsState


def test_default_state_has_no_markers():
    state = FindCardsState()
    assert state.current_page == 1
    assert state.marked_page_count() == 0
    assert state.marked_pages() == []
    assert state.marker_for_page(1) is None


def test_set_marker_records_page_and_point():
    state = FindCardsState()
    state.set_marker(3, 120.5, 200.0)
    marker = state.marker_for_page(3)
    assert marker is not None
    assert marker.page_num == 3
    assert marker.x == 120.5
    assert marker.y == 200.0


def test_set_marker_replaces_existing_marker_on_same_page():
    state = FindCardsState()
    state.set_marker(2, 10.0, 10.0)
    state.set_marker(2, 50.0, 60.0)
    marker = state.marker_for_page(2)
    assert marker.x == 50.0
    assert marker.y == 60.0
    assert state.marked_page_count() == 1


def test_markers_on_different_pages_are_independent():
    state = FindCardsState()
    state.set_marker(2, 10.0, 10.0)
    state.set_marker(5, 40.0, 45.0)
    assert state.marked_page_count() == 2
    assert state.marked_pages() == [2, 5]
    assert state.marker_for_page(2).x == 10.0
    assert state.marker_for_page(5).x == 40.0


def test_clear_page_removes_only_that_pages_marker():
    state = FindCardsState()
    state.set_marker(2, 10.0, 10.0)
    state.set_marker(5, 40.0, 45.0)
    state.clear_page(2)
    assert state.marker_for_page(2) is None
    assert state.marker_for_page(5) is not None
    assert state.marked_page_count() == 1


def test_clear_page_on_unmarked_page_is_a_no_op():
    state = FindCardsState()
    state.clear_page(9)
    assert state.marked_page_count() == 0


def test_clear_all_removes_every_marker():
    state = FindCardsState()
    state.set_marker(2, 10.0, 10.0)
    state.set_marker(5, 40.0, 45.0)
    state.clear_all()
    assert state.marked_page_count() == 0
    assert state.marked_pages() == []


def test_current_page_is_mutable_navigation_state():
    state = FindCardsState()
    state.current_page = 4
    assert state.current_page == 4
