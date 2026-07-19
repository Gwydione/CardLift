"""Left workflow sidebar -- shows the full workflow at all times."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QPushButton, QVBoxLayout, QWidget

from .app_state import AppState, STEP_LABELS, WorkflowStep
from .theme import (
    ACCENT,
    BG_SIDEBAR,
    FONT_BODY_SM,
    FONT_CAPTION,
    TEXT_NAV,
    TEXT_NAV_HEADER,
    TEXT_NAV_MUTED,
)

# Small leading glyphs for top-level steps -- stand-ins for line icons until
# real icon assets exist. Calibrate's children use a tree bullet instead.
_STEP_ICONS: dict[WorkflowStep, str] = {
    WorkflowStep.DECK: "▤",  # deck / document stack
    WorkflowStep.FIND_CARDS: "⌕",  # search / locate
    WorkflowStep.CALIBRATE_CARDS: "◎",  # target / calibrate
    WorkflowStep.CALIBRATE_BACK: "◎",
    WorkflowStep.REVIEW_CARDS: "▦",  # grid / review
    WorkflowStep.EXPORT: "⤓",  # export arrow
}
_CHILD_BULLET = "+"

# A notch larger than the shared FONT_BODY_SM/FONT_CAPTION scale -- the
# sidebar sits on dark chrome and is read at a glance while navigating, so
# it gets its own slightly larger sizes rather than sharing the smaller
# workspace-body sizes verbatim.
_LEAF_FONT = FONT_BODY_SM + 1
_INDENTED_FONT = FONT_CAPTION + 2
_HEADER_FONT = FONT_CAPTION + 1

_LEAF_STYLE = f"""
QPushButton {{
    text-align: left;
    padding: 11px 14px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: {TEXT_NAV};
    font-size: {_LEAF_FONT}px;
}}
QPushButton:hover {{
    background: #29234a;
}}
QPushButton[current="true"] {{
    background: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton:disabled {{
    color: {TEXT_NAV_MUTED};
    background: transparent;
}}
QPushButton[indented="true"] {{
    padding-left: 32px;
    font-size: {_INDENTED_FONT}px;
}}
"""

_HEADER_STYLE = (
    f"QLabel {{ color: {TEXT_NAV_HEADER}; font-size: {_HEADER_FONT}px; font-weight: 700;"
    " letter-spacing: 1px; padding: 18px 14px 4px 14px; }}"
)


class Sidebar(QWidget):
    """Fixed-width workflow list. Emits step_selected when a leaf step is clicked."""

    step_selected = Signal(object)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#sidebar {{ background: {BG_SIDEBAR}; }}" + _LEAF_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 18, 10, 18)
        layout.setSpacing(4)

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
            is_reached = self.state.is_reached(step)
            label = STEP_LABELS[step]
            if button.property("indented"):
                glyph = _CHILD_BULLET
            else:
                glyph = "✓" if is_reached and not is_current else _STEP_ICONS[step]
            button.setText(f"{glyph}  {label}")
            button.setChecked(is_current)
            button.setEnabled(is_reached)
            button.setProperty("current", is_current)
            button.style().unpolish(button)
            button.style().polish(button)
