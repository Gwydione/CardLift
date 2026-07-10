"""Application-frame shell: top bar, sidebar, context toolbar, workspace,
guidance panel, status bar.

This milestone only wires the shell together against AppState. No engine
calls -- see app_state.py for the pure navigation/state model this window
reads from and dispatches into. A future controller/session layer replaces
how AppState gets mutated, not how these widgets talk to it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_state import AppState, WORKFLOW_ORDER, WorkflowStep, CALIBRATE_STEPS
from .calibrate_toolbar import CalibrateToolbar
from .guidance_panel import GuidancePanel
from .sidebar import Sidebar
from .workspaces import build_workspaces

SIDEBAR_WIDTH = 200
GUIDANCE_MIN_WINDOW_WIDTH = 860
_NO_TOOLBAR_INDEX = 0
_CALIBRATE_TOOLBAR_INDEX = 1


class TopBar(QWidget):
    """Minimal top bar: DeckForge branding + an overflow/settings placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setStyleSheet("#topBar { background: #181b21; }")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)

        brand = QLabel("DeckForge")
        brand.setStyleSheet("font-size: 15px; font-weight: 600; color: #e4e7ec;")
        layout.addWidget(brand)
        layout.addStretch(1)

        overflow = QToolButton()
        overflow.setText("⋮")
        overflow.setToolTip("Settings")
        overflow.setAutoRaise(True)
        layout.addWidget(overflow)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DeckForge")
        self.resize(1200, 800)
        self.setMinimumSize(720, 480)

        self.state = AppState()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.top_bar = TopBar()
        outer.addWidget(self.top_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        outer.addWidget(body, 1)

        self.sidebar = Sidebar(self.state)
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
        self.sidebar.step_selected.connect(self._on_step_selected)
        body_layout.addWidget(self.sidebar)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        body_layout.addWidget(center, 1)

        self.toolbar_stack = QStackedWidget()
        self.toolbar_stack.setFixedHeight(38)
        center_layout.addWidget(self.toolbar_stack)

        self.calibrate_toolbar = CalibrateToolbar(self.state)
        self.calibrate_toolbar.pan_toggled.connect(self._on_pan_toggled)
        self.toolbar_stack.addWidget(QWidget())  # index 0: no toolbar for this step
        self.toolbar_stack.addWidget(self.calibrate_toolbar)  # index 1: calibrate

        self.workspace_stack = QStackedWidget()
        center_layout.addWidget(self.workspace_stack, 1)

        self.workspaces = build_workspaces(self.state)
        for step in WORKFLOW_ORDER:
            self.workspace_stack.addWidget(self.workspaces[step])

        self.guidance_panel = GuidancePanel(self.state)
        self.guidance_panel.collapse_toggled.connect(self._on_guidance_collapse_toggled)
        body_layout.addWidget(self.guidance_panel)

        self.status_bar = self.statusBar()

        self._apply_step(WorkflowStep.DECK)
        self._update_guidance_visibility()

    def _on_step_selected(self, step: WorkflowStep) -> None:
        self.state.select_step(step)
        self._apply_step(step)

    def _on_pan_toggled(self, active: bool) -> None:
        self.state.set_pan_mode(active)
        self._refresh_current_workspace()

    def _on_guidance_collapse_toggled(self, collapsed: bool) -> None:
        self.state.guidance_collapsed = collapsed
        self._update_guidance_visibility()

    def _apply_step(self, step: WorkflowStep) -> None:
        self.sidebar.refresh()
        self.workspace_stack.setCurrentIndex(WORKFLOW_ORDER.index(step))

        is_calibrate = step in CALIBRATE_STEPS
        self.toolbar_stack.setCurrentIndex(
            _CALIBRATE_TOOLBAR_INDEX if is_calibrate else _NO_TOOLBAR_INDEX
        )
        if is_calibrate:
            self.calibrate_toolbar.sync_pan_button()

        self._refresh_current_workspace()
        self.guidance_panel.refresh()

    def _refresh_current_workspace(self) -> None:
        workspace = self.workspaces[self.state.current_step]
        workspace.set_pan_active(self.state.pan_mode)
        self.status_bar.showMessage(self.state.status_text())

    def _update_guidance_visibility(self) -> None:
        collapsed = self.state.guidance_collapsed or self.width() < GUIDANCE_MIN_WINDOW_WIDTH
        self.guidance_panel.set_collapsed(collapsed)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_guidance_visibility()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.state.pan_mode:
            self.state.exit_pan_mode()
            self.calibrate_toolbar.sync_pan_button()
            self._refresh_current_workspace()
            return
        super().keyPressEvent(event)
