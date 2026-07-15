"""Application-frame shell: top bar, sidebar, context toolbar, workspace,
guidance panel, status bar.

Wires the shell together against two plain-Python models: app_state.py
(navigation/pan/guidance-collapse) and session.py (the loaded PDF). Neither
imports PySide6 -- this file and the workspace widgets are the only layer
that knows about Qt.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from deckforge import __version__

from .app_state import AppState, WORKFLOW_ORDER, WorkflowStep, CALIBRATE_STEPS
from .calibrate_state import CalibrateState, calibrate_status_text
from .calibrate_toolbar import CalibrateToolbar
from .calibrate_workspace import CalibrateWorkspace
from .export_state import export_status_text
from .find_cards_state import FindCardsState, find_cards_status_text
from .guidance_panel import GuidancePanel
from .review_state import ReviewCardsState, review_status_text
from .session import DeckLoadError, DeckSession
from .sidebar import Sidebar
from .theme import (
    ACCENT,
    BG_TOPBAR,
    BG_WORKSPACE,
    BORDER_CARD,
    FONT_BODY_SM,
    FONT_CAPTION,
    TEXT_BODY,
    TEXT_CAPTION_MUTED,
    TEXT_NAV,
)
from .workspaces import build_workspaces

_logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 220
GUIDANCE_MIN_WINDOW_WIDTH = 860
_NO_TOOLBAR_INDEX = 0
_CALIBRATE_TOOLBAR_INDEX = 1

# Assumes a source checkout (src/deckforge_gui/main_window.py two levels
# under the repo root) -- the same assumption gui_app.py's own docstring
# already makes ("pip install -r requirements-gui.txt / python
# gui_app.py"), since there is no packaging/bundling step in this repo
# yet. Revisit this path once real packaging exists.
DEMO_DECK_PATH = Path(__file__).resolve().parents[2] / "docs" / "ui" / "DeckForge_Demo_Deck.pdf"


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

        version = QLabel(f"v{__version__}")
        version.setStyleSheet(f"font-size: {FONT_CAPTION}px; color: {TEXT_CAPTION_MUTED}; margin-left: 8px;")
        layout.addWidget(version)

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
        self.setWindowTitle(f"DeckForge v{__version__}")
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
        self.deck_workspace.demo_deck_requested.connect(self._on_demo_deck_requested)
        # True only while the *currently loaded* deck is the bundled Demo
        # Deck -- set exclusively by _on_demo_deck_requested(), cleared by
        # every ordinary _on_pdf_chosen() call (a real PDF supersedes it
        # immediately) and by _end_demo_session() itself. Read in exactly
        # one place (_on_start_new_deck()) -- deliberately not threaded
        # into find_cards_state/calibrate_state/review_cards_state/
        # export_state, none of which need to know or behave differently
        # for the Demo Deck (see docs/ui/DEMO_DECK.md: "no special Demo
        # mode").
        self._is_demo_session = False
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
        self.export_workspace = self.workspaces[WorkflowStep.EXPORT]
        self.export_workspace.back_to_review_clicked.connect(self._on_export_back_to_review)
        self.export_workspace.start_new_deck_clicked.connect(self._on_start_new_deck)
        self.export_workspace.export_finished.connect(self._on_export_finished_while_closing)
        # True exactly while a "Finish Export, Then Close" close is
        # pending -- see closeEvent()/_on_export_finished_while_closing().
        self._close_after_export = False

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
        _logger.info("Step changed: %s", step.name)
        self.state.select_step(step)
        self._apply_step(step)

    def _on_demo_deck_requested(self) -> None:
        if not DEMO_DECK_PATH.exists():
            # Defensive only -- expected to be unreachable in a normal
            # source checkout; guards against a future packaging change
            # that moves or omits the bundled asset.
            _logger.warning("Demo Deck asset not found at %s", DEMO_DECK_PATH)
            self.deck_workspace.show_error("The bundled Demo Deck could not be found.")
            return
        self._on_pdf_chosen(DEMO_DECK_PATH, is_demo=True)

    def _on_pdf_chosen(self, path: Path, is_demo: bool = False) -> None:
        try:
            self.session.load_pdf(path)
        except DeckLoadError as exc:
            _logger.warning("Failed to load PDF %s: %s", path.name, exc)
            self.deck_workspace.show_error(str(exc))
            return
        _logger.info("PDF loaded: %s (%d pages)", path.name, self.session.page_count)
        self._is_demo_session = is_demo
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
        self.export_workspace.set_pdf(path, self.session.page_count)
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

    def _on_export_back_to_review(self) -> None:
        self._on_step_selected(WorkflowStep.REVIEW_CARDS)

    def _on_start_new_deck(self) -> None:
        # Reuses the Deck page's existing PDF-(re)load reset: dropping or
        # choosing a PDF there already clears find_cards_state/
        # calibrate_state/review_cards_state via _on_pdf_chosen -- no
        # separate app-wide "start over" reset needed here.
        #
        # The Demo Deck is the one exception: DEMO_DECK.md's "quiet
        # handoff" means that session should actually end (a clean Deck
        # screen, not the Demo Deck still shown as "Loaded") rather than
        # linger until the user happens to pick a new PDF -- see
        # _end_demo_session(). An ordinary deck's session deliberately
        # keeps lingering as-is; that behavior is unchanged.
        if self._is_demo_session:
            self._end_demo_session()
        else:
            self._on_step_selected(WorkflowStep.DECK)

    def _end_demo_session(self) -> None:
        """Ends the Demo Deck session: returns every piece of session
        state to its just-launched-app shape (in place -- see
        AppState.reset_to_start()'s docstring for why these are mutated
        rather than replaced) and shows a one-shot acknowledgment on the
        Deck screen. Deliberately does not touch any Calibrate/Review/
        Export widget's own cached PDFRenderer -- AppState.furthest_step
        resetting to DECK already makes them unreachable via the sidebar
        until a new PDF is loaded, at which point set_pdf() replaces
        those renderers the same way it always does."""
        self._is_demo_session = False
        self.session.unload()
        self.find_cards_state.clear_all()
        self.calibrate_state.reset_all()
        self.review_cards_state.clear()
        self.state.reset_to_start()
        self._update_deck_status_label()
        self._on_step_selected(WorkflowStep.DECK)
        self.deck_workspace.show_demo_completed()

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
        # Checked on Review Cards' and Export's own entry too, not just
        # Calibrate's -- AppState.is_reached lets the sidebar route
        # straight to either without passing back through Calibrate
        # first, so a Calibrate target that went stale since it was last
        # shown (a Front Page role changed, or the Shared Back page was
        # reassigned) must still be caught here rather than trusted
        # as-is. This is structural staleness (the calibrated page no
        # longer holds the role it was calibrated for); a *content*
        # staleness -- the same page recalibrated differently, or a front
        # page added without touching the calibrated one -- is instead
        # caught by ExportWorkspace itself via export_state.
        # review_snapshot_is_current(), since only it has an open
        # PDFRenderer to check page sizes with (see export_workspace.py's
        # module docstring).
        stale_steps = (WorkflowStep.CALIBRATE_CARDS, WorkflowStep.REVIEW_CARDS, WorkflowStep.EXPORT)
        if step in stale_steps and self.calibrate_state.cards_is_stale(self.find_cards_state):
            self.calibrate_state.cards.reset()
        back_stale_steps = (WorkflowStep.CALIBRATE_BACK, WorkflowStep.REVIEW_CARDS, WorkflowStep.EXPORT)
        if step in back_stale_steps and self.calibrate_state.back_is_stale(self.find_cards_state):
            self.calibrate_state.back.reset()
        if is_calibrate:
            self.calibrate_toolbar.sync_pan_button()
            self.workspaces[step].on_shown()
        if step is WorkflowStep.REVIEW_CARDS:
            self.review_workspace.on_shown()
        if step is WorkflowStep.EXPORT:
            self.export_workspace.on_shown()

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
        if step is WorkflowStep.EXPORT:
            return export_status_text(
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

    def closeEvent(self, event: QCloseEvent) -> None:
        # export_workspace.is_exporting() reflects the live QThread's
        # actual running state directly -- it doesn't matter whether Export
        # is the step currently shown (self.state.current_step): a worker
        # is only ever created for, and always belongs to, whatever PDF is
        # currently loaded (set_pdf() blocks on any prior worker before a
        # new one can start -- see export_workspace.py's _pdf_generation
        # docstring), so there is never an orphaned worker for a deck that
        # isn't the one on screen.
        #
        # This never blocks: a live export is never joined here (that was
        # the earlier, rejected design -- an unbounded QThread.wait() on
        # the GUI thread leaves the real window Windows-hung for the whole
        # remaining export, confirmed via IsHungAppWindow() during
        # investigation). "Finish Export, Then Close" instead ignores this
        # close and records a pending request; _on_export_finished_while_
        # closing() -- driven by export_workspace's own post-cleanup
        # export_finished signal, not by polling -- issues the real close
        # once the export actually finishes.
        #
        # Scope note: this only guarantees a clean shutdown for normal
        # in-app close (title-bar X, Alt+F4, taskbar close), which all
        # route through this override. It does not, and cannot, make the
        # export atomic against a forced process kill (Task Manager),
        # system shutdown/logoff, or a mid-write OSError -- none of those
        # go through Qt's close machinery at all, and true export
        # cancellation remains explicitly out of scope (see
        # docs/ALPHA_HARDENING_PLAN.md §2).
        if not self.export_workspace.is_exporting():
            # Covers both ordinary close-with-nothing-running, and the
            # second, automatic close request _on_export_finished_while_
            # closing() issues after a successful deferred export -- by
            # then the worker is already cleared, so this accepts it
            # immediately with no dialog.
            _logger.info("Application closing")
            return
        if self._close_after_export:
            # A deferred close is already pending from an earlier "Finish
            # Export, Then Close" -- an impatient repeat close attempt (X
            # again, Alt+F4 again) must not stack another confirmation
            # dialog or another pending request, just keep waiting quietly.
            event.ignore()
            return
        if self._confirm_quit_during_export():
            # _confirm_quit_during_export()'s QMessageBox.exec() runs a
            # real nested event loop -- the export can finish (and
            # export_finished can already have fired, back while
            # _close_after_export was still False, so it will never fire
            # again for this worker) before the user answers it. Re-check
            # is_exporting() with fresh eyes rather than trusting the
            # snapshot from the top of this method: if the export is
            # already done, close immediately via the ordinary no-export
            # path instead of deferring on a signal that has already come
            # and gone, which would otherwise leave the close pending
            # forever (until some later, unrelated close attempt).
            if self.export_workspace.is_exporting():
                _logger.info("Close deferred until export finishes")
                self._close_after_export = True
                event.ignore()
            else:
                _logger.info("Application closing")
                return
        else:
            event.ignore()

    def _on_export_finished_while_closing(self, succeeded: bool) -> None:
        """The export_workspace.export_finished consumer: fires once, right
        after export_workspace's own success/failure handling and worker
        cleanup (_on_export_worker_finished) have completed for the
        worker a pending deferred close was waiting on. A no-op unless
        that close is actually pending, so this is safe to leave connected
        unconditionally rather than wiring/unwiring it per-export."""
        if not self._close_after_export:
            return
        self._close_after_export = False
        if succeeded:
            # Not self.close() directly: this runs from inside the queued
            # signal delivery for export_finished, and scheduling the real
            # close for the next event-loop turn (rather than re-entering
            # Qt's close machinery from within this slot) keeps the second
            # close attempt an ordinary, fresh one -- handled by the
            # `not is_exporting()` branch above like any other close.
            QTimer.singleShot(0, self.close)
        # Failure: leave the pending request cleared and the window open --
        # export_workspace's own _on_export_failed() has already shown the
        # failure state; quitting anyway would silently conceal it.

    def _confirm_quit_during_export(self) -> bool:
        """Shows the export-in-progress close confirmation. Returns True if
        the user chose to finish the export and then close, False if they
        chose to keep the app open. A separate method (not inlined into
        closeEvent()) so tests can drive the decision directly rather than
        simulating a QMessageBox click, the same reason
        export_workspace.py's _confirm_overwrite_if_needed() is its own
        method.

        The wording is deliberate: it tells the user up front that this is
        a one-way choice (no cancellation exists once it's made -- see
        closeEvent()/_on_export_finished_while_closing()) and that
        choosing it does not freeze the application, since that freeze --
        not the crash it was mistaken for -- was the actual defect this
        replaced (see docs/ALPHA_HARDENING_PLAN.md §2)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Export in progress")
        box.setText(
            "An export is still in progress.\n\n"
            "DeckForge can remain open, or it can finish the export and "
            "then close automatically once it's done. The application "
            "stays fully responsive the whole time the export is "
            "finishing."
        )
        keep_open_btn = box.addButton("Keep DeckForge Open", QMessageBox.ButtonRole.RejectRole)
        finish_close_btn = box.addButton("Finish Export, Then Close", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(keep_open_btn)
        box.setEscapeButton(keep_open_btn)
        box.exec()
        return box.clickedButton() is finish_close_btn
