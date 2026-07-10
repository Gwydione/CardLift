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


class PlaceholderWorkspace(QWidget):
    """Static title + subtitle, centered. Used for every non-calibrate step."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 22px; font-weight: 600; color: #d5d9e0;")
        layout.addWidget(heading)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)
        subtitle_label.setMaximumWidth(420)
        subtitle_label.setStyleSheet("font-size: 13px; color: #7f8794;")
        layout.addWidget(subtitle_label)

    def set_pan_active(self, active: bool) -> None:
        """No-op: only the calibrate workspace has a page to pan."""


class CalibrateWorkspace(QWidget):
    """Placeholder page canvas that demonstrates the Pan cursor/drag story."""

    def __init__(self, state: AppState, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self._page = QLabel("Page preview\n(placeholder)")
        self._page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page.setFixedSize(420, 580)
        self._page.setStyleSheet(
            "background: #2a2f3a; border: 1px solid #444b59;"
            " color: #6b7280; font-size: 13px;"
        )
        layout.addWidget(self._page, 0, Qt.AlignmentFlag.AlignCenter)

        caption = QLabel(subtitle)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True)
        caption.setMaximumWidth(420)
        caption.setStyleSheet("font-size: 12px; color: #7f8794;")
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


def build_workspaces(state: AppState) -> dict[WorkflowStep, QWidget]:
    """One workspace instance per workflow step, in WORKFLOW_ORDER."""
    return {
        WorkflowStep.DECK: PlaceholderWorkspace(
            "Deck", "Bring in a print-and-play PDF to start a new deck."
        ),
        WorkflowStep.FIND_CARDS: PlaceholderWorkspace(
            "Find Cards", "DeckForge will help you point out where the cards are."
        ),
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
