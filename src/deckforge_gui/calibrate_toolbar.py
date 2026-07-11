"""Context toolbar shown above the workspace during Calibrate: Fit / Zoom / Pan.

No Select button, no Crosshair/Guides button -- alignment guides are always
on during calibration in this design, and there is nothing to select yet.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from .app_state import AppState
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    BG_CARD,
    BORDER_CARD,
    FONT_BODY_SM,
    TEXT_HEADING,
)

_TOOLBAR_STYLE = f"""
CalibrateToolbar {{
    background: {BG_CARD};
    border-bottom: 1px solid {BORDER_CARD};
}}
QPushButton {{
    padding: 5px 14px;
    border: 1px solid {BORDER_CARD};
    border-radius: 6px;
    background: {BG_CARD};
    color: {TEXT_HEADING};
    font-size: {FONT_BODY_SM}px;
}}
QPushButton:hover {{
    background: #f1effa;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: #e9e4fb;
}}
QPushButton#zoomStepButton {{
    padding: 5px 0px;
}}
QPushButton#panButton:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#panButton:checked:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#panButton:checked:pressed {{
    background: {ACCENT_PRESSED};
}}
"""


class CalibrateToolbar(QWidget):
    pan_toggled = Signal(bool)
    fit_clicked = Signal()
    zoom_in_clicked = Signal()
    zoom_out_clicked = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._zoom_percent = 100
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_TOOLBAR_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(8)

        self._fit_btn = QPushButton("Fit")
        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setObjectName("zoomStepButton")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_label = QLabel(f"{self._zoom_percent}%")
        self._zoom_label.setFixedWidth(44)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        self._zoom_label.setStyleSheet(f"color: {TEXT_HEADING}; font-size: {FONT_BODY_SM}px; border: none;")
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setObjectName("zoomStepButton")
        self._zoom_in_btn.setFixedWidth(28)
        self._pan_btn = QPushButton("Pan")
        self._pan_btn.setObjectName("panButton")
        self._pan_btn.setCheckable(True)

        for button in (self._fit_btn, self._zoom_out_btn, self._zoom_in_btn, self._pan_btn):
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self._fit_btn)
        layout.addWidget(_vline())
        layout.addWidget(self._zoom_out_btn)
        layout.addWidget(self._zoom_label)
        layout.addWidget(self._zoom_in_btn)
        layout.addWidget(_vline())
        layout.addWidget(self._pan_btn)
        layout.addStretch(1)

        self._fit_btn.clicked.connect(self.fit_clicked.emit)
        self._zoom_out_btn.clicked.connect(self.zoom_out_clicked.emit)
        self._zoom_in_btn.clicked.connect(self.zoom_in_clicked.emit)
        self._pan_btn.toggled.connect(self.pan_toggled.emit)

    def sync_pan_button(self) -> None:
        self._pan_btn.blockSignals(True)
        self._pan_btn.setChecked(self.state.pan_mode)
        self._pan_btn.blockSignals(False)

    def set_zoom_percent(self, percent: int) -> None:
        """Pushed by the active Calibrate workspace after any view change
        (load/fit/zoom/resize) -- this widget has no zoom state of its
        own, it only displays whatever the workspace reports."""
        self._zoom_percent = percent
        self._zoom_label.setText(f"{percent}%")


def _vline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line
