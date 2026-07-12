"""Central workspaces, one per workflow step.

Deck, Select Card Pages, Calibrate (Fronts/Shared Back), and Review Cards
are real, PDF-driven workspaces. Export remains a placeholder for a later
milestone.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .app_state import AppState, WorkflowStep
from .calibrate_state import CalibrateState
from .calibrate_workspace import CalibrateWorkspace
from .deck_workspace import DeckWorkspace
from .find_cards_state import FindCardsState
from .find_cards_workspace import FindCardsWorkspace
from .review_state import ReviewCardsState
from .review_workspace import ReviewWorkspace
from .theme import (
    BG_WORKSPACE,
    FONT_BODY,
    FONT_H1,
    TEXT_BODY,
    TEXT_HEADING,
)


class PlaceholderWorkspace(QWidget):
    """Static title + subtitle, centered. Used for every step without a
    real workspace yet."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size: {FONT_H1}px; font-weight: 700; color: {TEXT_HEADING};"
            " background: transparent;"
        )
        layout.addWidget(heading)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)
        subtitle_label.setMaximumWidth(480)
        subtitle_label.setStyleSheet(
            f"font-size: {FONT_BODY}px; color: {TEXT_BODY}; background: transparent;"
        )
        layout.addWidget(subtitle_label)

    def set_pan_active(self, active: bool) -> None:
        """No-op: only Calibrate workspaces have a page to pan."""


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
        WorkflowStep.EXPORT: PlaceholderWorkspace(
            "Export", "Save your finished cards as image files."
        ),
    }
