"""Application-frame shell: top bar, sidebar, context toolbar, workspace,
guidance panel, status bar.

Wires the shell together against two plain-Python models: app_state.py
(navigation/pan/guidance-collapse) and session.py (the loaded PDF). Neither
imports PySide6 -- this file and the workspace widgets are the only layer
that knows about Qt.
"""

from __future__ import annotations

from pathlib import Path

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
from .find_cards_state import FindCardsState
from .guidance_panel import GuidancePanel
from .session import DeckLoadError, DeckSession
from .sidebar import Sidebar
from .theme import ACCENT, BG_TOPBAR, BG_WORKSPACE, BORDER_CARD, FONT_BODY_SM, TEXT_BODY, TEXT_NAV
from .workspaces import build_workspaces

SIDEBAR_WIDTH = 220
GUIDANCE_MIN_WINDOW_WIDTH = 860
_NO_TOOLBAR_INDEX = 0
_CALIBRATE_TOOLBAR_INDEX = 1


class TopBar(QWidget):
    """Minimal top bar: DeckForge branding + an overflow/settings placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#topBar {{ background: {BG_TOPBAR}; }}")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 10, 0)

        brand = QLabel("DeckForge")
        brand.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {ACCENT};")
        layout.addWidget(brand)
        layout.addStretch(1)

        overflow = QToolButton()
        overflow.setText("⋮")
        overflow.setToolTip("Settings")
        overflow.setAutoRaise(True)
        overflow.setStyleSheet(f"color: {TEXT_NAV}; font-size: 16px;")
        layout.addWidget(overflow)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DeckForge")
        self.resize(1200, 800)
        self.setMinimumSize(720, 480)

        self.state = AppState()
        self.session = DeckSession()
        self.find_cards_state = FindCardsState()

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
        self.toolbar_stack.setFixedHeight(44)
        center_layout.addWidget(self.toolbar_stack)

        self.calibrate_toolbar = CalibrateToolbar(self.state)
        self.calibrate_toolbar.pan_toggled.connect(self._on_pan_toggled)
        no_toolbar = QWidget()  # index 0: no toolbar for this step
        no_toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        no_toolbar.setStyleSheet(f"background: {BG_WORKSPACE};")
        self.toolbar_stack.addWidget(no_toolbar)
        self.toolbar_stack.addWidget(self.calibrate_toolbar)  # index 1: calibrate

        self.workspace_stack = QStackedWidget()
        center_layout.addWidget(self.workspace_stack, 1)

        self.workspaces = build_workspaces(self.state, self.find_cards_state)
        for step in WORKFLOW_ORDER:
            self.workspace_stack.addWidget(self.workspaces[step])

        self.deck_workspace = self.workspaces[WorkflowStep.DECK]
        self.deck_workspace.pdf_chosen.connect(self._on_pdf_chosen)
        self.find_cards_workspace = self.workspaces[WorkflowStep.FIND_CARDS]

        self.guidance_panel = GuidancePanel(self.state)
        self.guidance_panel.collapse_toggled.connect(self._on_guidance_collapse_toggled)
        body_layout.addWidget(self.guidance_panel)

        self.status_bar = self.statusBar()
        self.status_bar.setContentsMargins(18, 2, 18, 2)
        self.status_bar.setStyleSheet(
            f"QStatusBar {{ background: white; border-top: 1px solid {BORDER_CARD};"
            f" color: {TEXT_BODY}; font-size: {FONT_BODY_SM - 1}px; }}"
        )
        self._deck_status_label = QLabel()
        self.status_bar.addPermanentWidget(self._deck_status_label)
        self._update_deck_status_label()

        self._apply_step(WorkflowStep.DECK)
        self._update_guidance_visibility()

    def _on_step_selected(self, step: WorkflowStep) -> None:
        self.state.select_step(step)
        self._apply_step(step)

    def _on_pdf_chosen(self, path: Path) -> None:
        try:
            self.session.load_pdf(path)
        except DeckLoadError as exc:
            self.deck_workspace.show_error(str(exc))
            return
        self._update_deck_status_label()
        # A newly (or re-)loaded PDF invalidates any previous markers --
        # page N in a different PDF has no relationship to page N's marker
        # in the last one.
        self.find_cards_state.clear_all()
        self.find_cards_workspace.set_pdf(path, self.session.page_count)
        self._on_step_selected(WorkflowStep.FIND_CARDS)

    def _update_deck_status_label(self) -> None:
        if self.session.is_loaded:
            text = f"{self.session.filename}  •  {self.session.page_count} pages"
        else:
            text = "No PDF loaded"
        self._deck_status_label.setText(text)

    def _on_pan_toggled(self, active: bool) -> None:
        self.state.set_pan_mode(active)
        self._refresh_current_workspace()

    def _on_guidance_collapse_toggled(self, collapsed: bool) -> None:
        self.state.guidance_collapsed = collapsed
        self._update_guidance_visibility()

    def _apply_step(self, step: WorkflowStep) -> None:
        self.sidebar.refresh()
        self.workspace_stack.setCurrentIndex(WORKFLOW_ORDER.index(step))

        if step is WorkflowStep.DECK:
            self.deck_workspace.set_loaded(self.session.filename, self.session.page_count)

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
