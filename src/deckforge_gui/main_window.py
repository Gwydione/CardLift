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
from .calibrate_state import CalibrateState, calibrate_status_text
from .calibrate_toolbar import CalibrateToolbar
from .calibrate_workspace import CalibrateWorkspace
from .find_cards_state import FindCardsState, find_cards_status_text
from .guidance_panel import GuidancePanel
from .review_state import ReviewCardsState, review_status_text
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
        self.calibrate_state = CalibrateState()
        self.review_cards_state = ReviewCardsState()

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
        self.calibrate_toolbar.fit_clicked.connect(self._on_fit_clicked)
        self.calibrate_toolbar.zoom_in_clicked.connect(self._on_zoom_in_clicked)
        self.calibrate_toolbar.zoom_out_clicked.connect(self._on_zoom_out_clicked)
        no_toolbar = QWidget()  # index 0: no toolbar for this step
        no_toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        no_toolbar.setStyleSheet(f"background: {BG_WORKSPACE};")
        self.toolbar_stack.addWidget(no_toolbar)
        self.toolbar_stack.addWidget(self.calibrate_toolbar)  # index 1: calibrate

        self.workspace_stack = QStackedWidget()
        center_layout.addWidget(self.workspace_stack, 1)

        self.workspaces = build_workspaces(
            self.state, self.find_cards_state, self.calibrate_state, self.review_cards_state,
        )
        for step in WORKFLOW_ORDER:
            self.workspace_stack.addWidget(self.workspaces[step])

        self.deck_workspace = self.workspaces[WorkflowStep.DECK]
        self.deck_workspace.pdf_chosen.connect(self._on_pdf_chosen)
        self.find_cards_workspace = self.workspaces[WorkflowStep.FIND_CARDS]
        self.find_cards_workspace.continue_clicked.connect(self._on_find_cards_continue)
        self.find_cards_workspace.state_changed.connect(self._on_workspace_state_changed)
        self.calibrate_cards_workspace = self.workspaces[WorkflowStep.CALIBRATE_CARDS]
        self.calibrate_cards_workspace.continue_clicked.connect(self._on_cards_continue)
        self.calibrate_back_workspace = self.workspaces[WorkflowStep.CALIBRATE_BACK]
        self.calibrate_back_workspace.continue_clicked.connect(self._on_back_continue)
        self.calibrate_back_workspace.back_to_select_cards_clicked.connect(self._on_back_to_select_cards)
        for calibrate_workspace in (self.calibrate_cards_workspace, self.calibrate_back_workspace):
            calibrate_workspace.zoom_changed.connect(self.calibrate_toolbar.set_zoom_percent)
            calibrate_workspace.calibration_changed.connect(self._on_workspace_state_changed)
        self.review_workspace = self.workspaces[WorkflowStep.REVIEW_CARDS]
        self.review_workspace.continue_clicked.connect(self._on_review_continue)
        self.review_workspace.back_to_calibrate_clicked.connect(self._on_review_back_to_calibrate)
        self.review_workspace.state_changed.connect(self._on_workspace_state_changed)

        self.guidance_panel = GuidancePanel(
            self.state, self.calibrate_state, self.find_cards_state, self.review_cards_state,
        )
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
        # A newly (or re-)loaded PDF invalidates any previous markers/
        # calibration -- page N in a different PDF has no relationship to
        # page N's marker or measured geometry in the last one.
        self.find_cards_state.clear_all()
        self.calibrate_state.reset_all()
        self.review_cards_state.clear()
        self.find_cards_workspace.set_pdf(path, self.session.page_count)
        self.calibrate_cards_workspace.set_pdf(path, self.session.page_count)
        self.calibrate_back_workspace.set_pdf(path, self.session.page_count)
        self.review_workspace.set_pdf(path, self.session.page_count)
        self._on_step_selected(WorkflowStep.FIND_CARDS)

    def _on_find_cards_continue(self) -> None:
        self._on_step_selected(WorkflowStep.CALIBRATE_CARDS)

    def _on_cards_continue(self) -> None:
        self._on_step_selected(WorkflowStep.CALIBRATE_BACK)

    def _on_back_continue(self) -> None:
        self._on_step_selected(WorkflowStep.REVIEW_CARDS)

    def _on_back_to_select_cards(self) -> None:
        self._on_step_selected(WorkflowStep.FIND_CARDS)

    def _on_review_continue(self) -> None:
        self._on_step_selected(WorkflowStep.EXPORT)

    def _on_review_back_to_calibrate(self) -> None:
        self._on_step_selected(WorkflowStep.CALIBRATE_BACK)

    def _update_deck_status_label(self) -> None:
        if self.session.is_loaded:
            text = f"{self.session.filename}  •  {self.session.page_count} pages"
        else:
            text = "No PDF loaded"
        self._deck_status_label.setText(text)

    def _on_pan_toggled(self, active: bool) -> None:
        self.state.set_pan_mode(active)
        self._refresh_current_workspace()

    def _on_fit_clicked(self) -> None:
        self._active_calibrate_workspace().fit_to_window()

    def _on_zoom_in_clicked(self) -> None:
        self._active_calibrate_workspace().zoom_in()

    def _on_zoom_out_clicked(self) -> None:
        self._active_calibrate_workspace().zoom_out()

    def _active_calibrate_workspace(self) -> CalibrateWorkspace:
        return self.workspaces[self.state.current_step]

    def _on_workspace_state_changed(self) -> None:
        """Shared handler for any signal meaning 'something this workspace
        owns changed in a way the status bar/guidance panel should
        reflect' -- calibration progress, a Select Card Pages role toggle,
        or a Review Cards include/exclude toggle all funnel here rather
        than each getting its own identical two-line method."""
        self.guidance_panel.refresh()
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
        # Checked on Review Cards' own entry too, not just Calibrate's --
        # AppState.is_reached lets the sidebar route straight to Review
        # Cards without passing back through Calibrate first, so a
        # Calibrate target that went stale since it was last shown (a
        # Front Page role changed, or the Shared Back page was
        # reassigned) must still be caught here rather than trusted as-is.
        if step in (WorkflowStep.CALIBRATE_CARDS, WorkflowStep.REVIEW_CARDS) and self.calibrate_state.cards_is_stale(self.find_cards_state):
            self.calibrate_state.cards.reset()
        if step in (WorkflowStep.CALIBRATE_BACK, WorkflowStep.REVIEW_CARDS) and self.calibrate_state.back_is_stale(self.find_cards_state):
            self.calibrate_state.back.reset()
        if is_calibrate:
            self.calibrate_toolbar.sync_pan_button()
            self.workspaces[step].on_shown()
        if step is WorkflowStep.REVIEW_CARDS:
            self.review_workspace.on_shown()

        self._refresh_current_workspace()
        self.guidance_panel.refresh()

    def _refresh_current_workspace(self) -> None:
        workspace = self.workspaces[self.state.current_step]
        workspace.set_pan_active(self.state.pan_mode)
        self.status_bar.showMessage(self._status_text())

    def _status_text(self) -> str:
        step = self.state.current_step
        if step is WorkflowStep.FIND_CARDS:
            return find_cards_status_text(self.find_cards_state, self.session.page_count)
        if step in CALIBRATE_STEPS and not self.state.pan_mode:
            return calibrate_status_text(
                step,
                self.calibrate_state.target_for(step),
                self.find_cards_state.front_page_count(),
                self.find_cards_state.shared_back_status(),
                self.workspaces[step].grid_page_size(),
            )
        if step is WorkflowStep.REVIEW_CARDS:
            return review_status_text(
                self.calibrate_state.cards,
                self.calibrate_state.back,
                self.find_cards_state.shared_back_status(),
                self.review_cards_state,
            )
        return self.state.status_text()

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
