from deckforge_gui.app_state import (
    PAN_STATUS,
    STATUS,
    WORKFLOW_ORDER,
    AppState,
    WorkflowStep,
)


def test_default_state_starts_on_deck():
    state = AppState()
    assert state.current_step is WorkflowStep.DECK
    assert state.furthest_step is WorkflowStep.DECK
    assert state.pan_mode is False
    assert state.guidance_collapsed is False


def test_select_step_advances_furthest():
    state = AppState()
    state.select_step(WorkflowStep.CALIBRATE_CARDS)
    assert state.current_step is WorkflowStep.CALIBRATE_CARDS
    assert state.furthest_step is WorkflowStep.CALIBRATE_CARDS


def test_select_step_backward_does_not_regress_furthest():
    state = AppState()
    state.select_step(WorkflowStep.EXPORT)
    state.select_step(WorkflowStep.DECK)
    assert state.current_step is WorkflowStep.DECK
    assert state.furthest_step is WorkflowStep.EXPORT


def test_is_reached_reflects_furthest_progress():
    state = AppState()
    state.select_step(WorkflowStep.CALIBRATE_CARDS)
    assert state.is_reached(WorkflowStep.DECK)
    assert state.is_reached(WorkflowStep.FIND_CARDS)
    assert state.is_reached(WorkflowStep.CALIBRATE_CARDS)
    assert not state.is_reached(WorkflowStep.CALIBRATE_BACK)
    assert not state.is_reached(WorkflowStep.EXPORT)


def test_all_workflow_steps_reachable_in_order():
    state = AppState()
    for step in WORKFLOW_ORDER:
        state.select_step(step)
        assert state.is_reached(step)


def test_pan_mode_toggle_and_exit():
    state = AppState()
    state.select_step(WorkflowStep.CALIBRATE_CARDS)
    assert state.toggle_pan_mode() is True
    assert state.pan_mode is True
    state.exit_pan_mode()
    assert state.pan_mode is False


def test_leaving_calibrate_step_clears_pan_mode():
    state = AppState()
    state.select_step(WorkflowStep.CALIBRATE_CARDS)
    state.set_pan_mode(True)
    state.select_step(WorkflowStep.REVIEW_CARDS)
    assert state.pan_mode is False


def test_status_text_normal_vs_pan_mode():
    state = AppState()
    state.select_step(WorkflowStep.CALIBRATE_CARDS)
    assert state.status_text() == STATUS[WorkflowStep.CALIBRATE_CARDS]
    state.set_pan_mode(True)
    assert state.status_text() == PAN_STATUS


def test_pan_mode_never_affects_status_outside_calibrate():
    state = AppState()
    state.select_step(WorkflowStep.DECK)
    state.pan_mode = True  # not reachable via UI outside calibrate, but guard the pure function anyway
    assert state.status_text() == STATUS[WorkflowStep.DECK]


def test_guidance_collapsed_toggle():
    state = AppState()
    assert state.toggle_guidance_collapsed() is True
    assert state.guidance_collapsed is True
    assert state.toggle_guidance_collapsed() is False
    assert state.guidance_collapsed is False


def test_guidance_text_present_for_every_step():
    state = AppState()
    for step in WORKFLOW_ORDER:
        state.select_step(step)
        headline, body = state.guidance_text()
        assert headline
        assert body
