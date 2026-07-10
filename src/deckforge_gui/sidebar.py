"""Left workflow sidebar -- shows the full workflow at all times."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QPushButton, QVBoxLayout, QWidget

from .app_state import AppState, STEP_LABELS, WorkflowStep

_LEAF_STYLE = """
QPushButton {
    text-align: left;
    padding: 8px 10px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: #c4c9d4;
    font-size: 13px;
}
QPushButton:hover {
    background: #2b3038;
}
QPushButton[current="true"] {
    background: #3d5afe;
    color: white;
    font-weight: 600;
}
QPushButton[muted="true"] {
    color: #5b6270;
}
QPushButton[indented="true"] {
    padding-left: 26px;
}
"""

_HEADER_STYLE = (
    "color: #7f8794; font-size: 11px; font-weight: 700;"
    " letter-spacing: 1px; padding: 12px 10px 2px 10px;"
)


class Sidebar(QWidget):
    """Fixed-width workflow list. Emits step_selected when a leaf step is clicked."""

    step_selected = Signal(object)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("sidebar")
        self.setStyleSheet("#sidebar { background: #20242c; }" + _LEAF_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(2)

        self._buttons: dict[WorkflowStep, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        def add_leaf(step: WorkflowStep, indented: bool = False) -> None:
            button = QPushButton(STEP_LABELS[step])
            button.setCheckable(True)
            button.setProperty("indented", indented)
            button.clicked.connect(lambda _checked=False, s=step: self.step_selected.emit(s))
            self._group.addButton(button)
            self._buttons[step] = button
            layout.addWidget(button)

        add_leaf(WorkflowStep.DECK)
        add_leaf(WorkflowStep.FIND_CARDS)

        header = QLabel("Calibrate")
        header.setStyleSheet(_HEADER_STYLE)
        layout.addWidget(header)

        add_leaf(WorkflowStep.CALIBRATE_CARDS, indented=True)
        add_leaf(WorkflowStep.CALIBRATE_BACK, indented=True)

        add_leaf(WorkflowStep.REVIEW_CARDS)
        add_leaf(WorkflowStep.EXPORT)

        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        for step, button in self._buttons.items():
            is_current = step is self.state.current_step
            is_muted = not self.state.is_reached(step) and not is_current
            button.setChecked(is_current)
            button.setProperty("current", is_current)
            button.setProperty("muted", is_muted)
            button.style().unpolish(button)
            button.style().polish(button)
