"""Context toolbar shown above the workspace during Calibrate: Fit / Zoom / Pan.

No Select button, no Crosshair/Guides button -- alignment guides are always
on during calibration in this design, and there is nothing to select yet.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from .app_state import AppState

_MIN_ZOOM = 25
_MAX_ZOOM = 400
_ZOOM_STEP = 10

_TOOLBAR_STYLE = """
QPushButton#panButton {
    padding: 4px 12px;
    border-radius: 4px;
}
QPushButton#panButton:checked {
    background: #3d5afe;
    color: white;
    font-weight: 600;
}
"""


class CalibrateToolbar(QWidget):
    pan_toggled = Signal(bool)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._zoom_percent = 100
        self.setStyleSheet(_TOOLBAR_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(8)

        self._fit_btn = QPushButton("Fit")
        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_label = QLabel(f"{self._zoom_percent}%")
        self._zoom_label.setFixedWidth(44)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedWidth(28)
        self._pan_btn = QPushButton("Pan")
        self._pan_btn.setObjectName("panButton")
        self._pan_btn.setCheckable(True)

        for button in (self._fit_btn, self._zoom_out_btn, self._zoom_in_btn, self._pan_btn):
            button.setAutoDefault(False)

        layout.addWidget(self._fit_btn)
        layout.addWidget(_vline())
        layout.addWidget(self._zoom_out_btn)
        layout.addWidget(self._zoom_label)
        layout.addWidget(self._zoom_in_btn)
        layout.addWidget(_vline())
        layout.addWidget(self._pan_btn)
        layout.addStretch(1)

        self._fit_btn.clicked.connect(self._on_fit)
        self._zoom_out_btn.clicked.connect(self._on_zoom_out)
        self._zoom_in_btn.clicked.connect(self._on_zoom_in)
        self._pan_btn.toggled.connect(self.pan_toggled.emit)

    def sync_pan_button(self) -> None:
        self._pan_btn.blockSignals(True)
        self._pan_btn.setChecked(self.state.pan_mode)
        self._pan_btn.blockSignals(False)

    def _on_fit(self) -> None:
        self._zoom_percent = 100
        self._zoom_label.setText(f"{self._zoom_percent}%")

    def _on_zoom_in(self) -> None:
        self._zoom_percent = min(_MAX_ZOOM, self._zoom_percent + _ZOOM_STEP)
        self._zoom_label.setText(f"{self._zoom_percent}%")

    def _on_zoom_out(self) -> None:
        self._zoom_percent = max(_MIN_ZOOM, self._zoom_percent - _ZOOM_STEP)
        self._zoom_label.setText(f"{self._zoom_percent}%")


def _vline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line
