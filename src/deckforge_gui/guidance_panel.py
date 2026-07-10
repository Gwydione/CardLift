"""Right-hand guidance panel -- contextual, short, collapsible."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_state import AppState

COLLAPSED_WIDTH = 28
EXPANDED_WIDTH = 260


class GuidancePanel(QWidget):
    """Collapses to a thin strip with an expand button rather than disappearing."""

    collapse_toggled = Signal(bool)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("guidancePanel")
        self.setStyleSheet("#guidancePanel { background: #20242c; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._full_page = self._build_full_page()
        self._strip = self._build_strip()
        self._stack.addWidget(self._full_page)
        self._stack.addWidget(self._strip)

        self.set_collapsed(False)

    def _build_full_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel("Guidance")
        title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #7f8794;"
        )
        header_row.addWidget(title)
        header_row.addStretch(1)

        collapse_btn = QToolButton()
        collapse_btn.setText("»")
        collapse_btn.setToolTip("Hide guidance panel")
        collapse_btn.setAutoRaise(True)
        collapse_btn.clicked.connect(lambda: self.collapse_toggled.emit(True))
        header_row.addWidget(collapse_btn)
        layout.addLayout(header_row)

        self._headline = QLabel()
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet("font-size: 14px; font-weight: 600; color: #e4e7ec;")
        layout.addWidget(self._headline)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setStyleSheet("font-size: 12px; color: #b4bac5;")
        layout.addWidget(self._body)

        layout.addStretch(1)
        return page

    def _build_strip(self) -> QWidget:
        strip = QWidget()
        layout = QVBoxLayout(strip)
        layout.setContentsMargins(4, 10, 4, 10)

        expand_btn = QToolButton()
        expand_btn.setText("«")
        expand_btn.setToolTip("Show guidance panel")
        expand_btn.setAutoRaise(True)
        expand_btn.clicked.connect(lambda: self.collapse_toggled.emit(False))
        layout.addWidget(expand_btn)
        layout.addStretch(1)
        return strip

    def set_collapsed(self, collapsed: bool) -> None:
        self._stack.setCurrentWidget(self._strip if collapsed else self._full_page)
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)

    def refresh(self) -> None:
        headline, body = self.state.guidance_text()
        self._headline.setText(headline)
        self._body.setText(body)
