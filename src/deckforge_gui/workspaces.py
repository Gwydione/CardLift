"""Central workspaces, one per workflow step.

Deck, Select Card Pages, Calibrate (Fronts/Shared Back), Review Cards, and
Export are all real, PDF-driven workspaces.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .app_state import AppState, WorkflowStep
from .calibrate_state import CalibrateState
from .calibrate_workspace import CalibrateWorkspace
from .deck_workspace import DeckWorkspace
from .export_workspace import ExportWorkspace
from .find_cards_state import FindCardsState
from .find_cards_workspace import FindCardsWorkspace
from .review_state import ReviewCardsState
from .review_workspace import ReviewWorkspace


def build_workspaces(
    state: AppState,
    find_cards_state: FindCardsState,
    calibrate_state: CalibrateState,
    review_cards_state: ReviewCardsState,
) -> dict[WorkflowStep, QWidget]:
    """One workspace instance per workflow step, in WORKFLOW_ORDER."""
    return {
        WorkflowStep.DECK: DeckWorkspace(),
        WorkflowStep.FIND_CARDS: FindCardsWorkspace(find_cards_state),
        WorkflowStep.CALIBRATE_CARDS: CalibrateWorkspace(
            WorkflowStep.CALIBRATE_CARDS, state, calibrate_state, find_cards_state,
        ),
        WorkflowStep.CALIBRATE_BACK: CalibrateWorkspace(
            WorkflowStep.CALIBRATE_BACK, state, calibrate_state, find_cards_state,
        ),
        WorkflowStep.REVIEW_CARDS: ReviewWorkspace(calibrate_state, find_cards_state, review_cards_state),
        WorkflowStep.EXPORT: ExportWorkspace(calibrate_state, find_cards_state, review_cards_state),
    }
