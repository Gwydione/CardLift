"""Placeholder central workspaces, one per workflow step.

These stand in for the future PDF-driven views (deck picker, card finder,
calibration canvas, review grid, export summary). None of them talk to the
extraction engine yet -- this milestone only validates the application
shell.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .app_state import AppState, WorkflowStep
from .deck_workspace import DeckWorkspace
from .find_cards_state import FindCardsState
from .find_cards_workspace import FindCardsWorkspace
from .theme import (
    BG_CARD,
    BG_WORKSPACE,
    BORDER_CARD,
    FONT_BODY,
    FONT_BODY_SM,
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
        """No-op: only the calibrate workspace has a page to pan."""


class CalibrateWorkspace(QWidget):
    """Placeholder page canvas that demonstrates the Pan cursor/drag story."""

    def __init__(self, state: AppState, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._dragging = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self._page = QLabel("Page preview\n(placeholder)")
        self._page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page.setFixedSize(460, 630)
        self._page.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 8px;"
            f" color: {TEXT_BODY}; font-size: {FONT_BODY_SM}px;"
        )
        layout.addWidget(self._page, 0, Qt.AlignmentFlag.AlignCenter)

        caption = QLabel(subtitle)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True)
        caption.setMaximumWidth(460)
        caption.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {TEXT_BODY}; background: transparent;"
        )
        layout.addWidget(caption)

    def set_pan_active(self, active: bool) -> None:
        cursor = Qt.CursorShape.OpenHandCursor if active else Qt.CursorShape.ArrowCursor
        self._page.setCursor(cursor)
        if not active:
            self._dragging = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.state.pan_mode:
            self._dragging = True
            self._page.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            self._page.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


def build_workspaces(state: AppState, find_cards_state: FindCardsState) -> dict[WorkflowStep, QWidget]:
    """One workspace instance per workflow step, in WORKFLOW_ORDER."""
    return {
        WorkflowStep.DECK: DeckWorkspace(),
        WorkflowStep.FIND_CARDS: FindCardsWorkspace(find_cards_state),
        WorkflowStep.CALIBRATE_CARDS: CalibrateWorkspace(
            state, "Click the upper-left corner of a card to begin."
        ),
        WorkflowStep.CALIBRATE_BACK: CalibrateWorkspace(
            state, "Click the upper-left corner of the shared card back."
        ),
        WorkflowStep.REVIEW_CARDS: PlaceholderWorkspace(
            "Review Cards", "Look over every card before exporting your deck."
        ),
        WorkflowStep.EXPORT: PlaceholderWorkspace(
            "Export", "Save your finished cards as image files."
        ),
    }
