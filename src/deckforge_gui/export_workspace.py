"""Export workspace -- the final workflow step: writes the human-approved
cards from Review Cards to PNG files in a folder the user chooses.

WHY THIS OWNS ITS OWN PDFRenderer, AND CALLS deckforge.cell_export
DIRECTLY (NOT DeckExporter)
----------------------------------------------------------------------
Same reasoning as review_workspace.py: this workspace already has the
user's actual PDF (whatever path they chose), and deckforge.exporter.
DeckExporter is CLI-shaped -- it discovers the PDF via profile.pdf_file
and always writes to a fixed output/ folder, neither of which applies
here. deckforge.cell_export.export_cells() is the engine primitive built
for exactly this case: an explicit, ordered list of cells (not a
CardLayout's complete grid) written to a caller-chosen folder -- see its
module docstring for why a CardLayout can't represent Review Cards'
excluded cells at all.

WHY THE STALE-SNAPSHOT CHECK LIVES HERE, NOT IN THE GUIDANCE PANEL/STATUS
BAR
----------------------------------------------------------------------
export_state.review_snapshot_is_current() needs a page-size lookup, which
needs an open PDFRenderer. This workspace already has one (for the export
operation itself); GuidancePanel and MainWindow's status bar do not, and
giving them one would mean threading a workspace reference into
GuidancePanel, breaking its "reads only plain state" boundary for a
single edge case. So export_state.export_ready() (used by the guidance
panel and status bar) intentionally does not perform this check -- only
this workspace's own _rebuild() does, via review_snapshot_is_current().
This means that one narrow scenario -- Calibrate was redone on the same
page (or a front page was added) after Export was first reached, and the
user jumps directly back to Export via the sidebar without revisiting
Review Cards -- can show "Ready to export" in the guidance panel/status
bar while this workspace correctly blocks and explains why. The
guidance/status text being slightly optimistic in that one case is an
accepted, documented limitation (see DEVELOPER.md's "Export milestone"):
what matters is that the actual Export action -- the thing that writes
files to disk -- never runs against an unconfirmed cell set, and that
guarantee holds regardless.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deckforge.cell_export import export_cells
from deckforge.pdf_renderer import PDFRenderer
from deckforge.profile import GridGeometry

from .calibrate_state import CalibrateState, CalibrationTarget
from .export_state import (
    EXPORT_RENDER_SCALE,
    ExportPlan,
    build_export_plan,
    existing_output_files,
    export_guidance_text,
    export_ready,
    export_status_text,
    review_snapshot_is_current,
    stale_review_guidance_text,
    stale_review_status_text,
)
from .find_cards_state import FindCardsState, SharedBackStatus
from .review_state import ReviewCardsState
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    BG_CARD,
    BG_WORKSPACE,
    BORDER_CARD,
    ERROR_TEXT,
    FONT_BODY,
    FONT_BODY_SM,
    FONT_CAPTION,
    FONT_H2,
    TEXT_BODY,
    TEXT_CAPTION_MUTED,
    TEXT_HEADING,
)

_CONTROL_BUTTON_STYLE = f"""
QPushButton {{
    padding: 6px 14px;
    border: 1px solid {BORDER_CARD};
    border-radius: 6px;
    background: {BG_CARD};
    color: {TEXT_HEADING};
    font-size: {FONT_BODY_SM}px;
}}
QPushButton:hover {{ background: #f1effa; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #e9e4fb; }}
QPushButton:disabled {{ color: {TEXT_CAPTION_MUTED}; background: {BG_WORKSPACE}; }}
"""

_PRIMARY_BUTTON_STYLE = f"""
QPushButton {{
    padding: 10px 22px;
    border: none;
    border-radius: 6px;
    background: {ACCENT};
    color: white;
    font-size: {FONT_BODY}px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton:disabled {{ background: #cfc9e8; color: #f4f2fb; }}
"""

_logger = logging.getLogger(__name__)

_PROGRESS_STYLE = f"""
QProgressBar {{
    border: 1px solid {BORDER_CARD};
    border-radius: 4px;
    background: {BG_CARD};
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}
"""


class _ExportWorker(QThread):
    """Runs export_cells() off the GUI thread so the window stays
    responsive (and an indeterminate progress bar can actually animate)
    while a large deck is being written to disk. A thin runner only --
    all the real work stays in deckforge.cell_export.export_cells(),
    called exactly as ExportWorkspace._on_export_clicked() used to call
    it inline; nothing about the export itself changes."""

    # Carries the destination the worker actually wrote to, not just the
    # written-files list -- ExportWorkspace._on_export_succeeded must not
    # re-read self._destination after the fact, since a user who switches
    # PDFs (set_pdf()) while this worker is still running resets that
    # instance attribute out from under it (see "N files to None" fix).
    succeeded = Signal(list, Path)
    failed = Signal(str)

    def __init__(
        self,
        renderer: PDFRenderer,
        render_scale: float,
        front_geometry: GridGeometry,
        cells: list[tuple[int, int, int]],
        destination: Path,
        back: Optional[tuple[int, GridGeometry]],
        pdf_generation: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._renderer = renderer
        self._render_scale = render_scale
        self._front_geometry = front_geometry
        self._cells = cells
        self._destination = destination
        self._back = back
        # Stamped with ExportWorkspace._pdf_generation at dispatch time --
        # set_pdf() bumps that counter on every (re)load, so a completion
        # signal that arrives after the user has already switched to a
        # different PDF can be told apart from one for the PDF still
        # loaded, regardless of how long this worker was already running
        # (see ExportWorkspace._is_stale_worker_signal()).
        self.pdf_generation = pdf_generation

    def run(self) -> None:
        try:
            written = export_cells(
                self._renderer, self._render_scale, self._front_geometry,
                self._cells, self._destination, back=self._back,
            )
        except Exception as exc:
            # Blanket, not just (OSError, PDFRenderError): this is a thread
            # boundary sys.excepthook cannot be relied on to substitute for
            # -- without this, an unexpected exception here leaves the
            # worker dead with neither succeeded nor failed emitted, so the
            # user just watches the progress bar vanish with no message.
            _logger.exception("Export raised an exception")
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(written, self._destination)


class ExportWorkspace(QWidget):
    """Central Export workspace: summary, destination folder, Export
    action, and a completion/error message -- no per-card grid, since
    Review Cards already is that checkpoint."""

    back_to_review_clicked = Signal()
    start_new_deck_clicked = Signal()
    # Emitted once per dispatched export, exactly when _on_export_worker_
    # finished() (this workspace's own cleanup) has finished running for
    # that export's worker -- i.e. strictly after whichever of
    # _on_export_succeeded()/_on_export_failed() applies has already run.
    # carries True for success, False for failure. MainWindow's deferred
    # close (see closeEvent()) is the only consumer: it waits for this
    # signal instead of joining the worker thread directly, so it never has
    # to duplicate _is_stale_worker_signal()'s generation bookkeeping (a
    # stale worker's finished signal, from a PDF the user has since switched
    # away from, does not emit this at all -- see _on_export_worker_
    # finished()).
    export_finished = Signal(bool)

    def __init__(
        self,
        calibrate_state: CalibrateState,
        find_cards_state: FindCardsState,
        review_state: ReviewCardsState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.calibrate_state = calibrate_state
        self.find_cards_state = find_cards_state
        self.review_state = review_state

        self._renderer: Optional[PDFRenderer] = None
        self._destination: Optional[Path] = None
        self._plan: Optional[ExportPlan] = None
        self._worker: Optional[_ExportWorker] = None
        self._export_complete = False
        # The plan that was actually exported when _export_complete last
        # became True -- _show_ready() compares this against the freshly
        # rebuilt plan so a completion banner never survives a config
        # change (e.g. toggling a card back in Review Cards) that makes it
        # describe a plan that's no longer the one on screen.
        self._completed_plan: Optional[ExportPlan] = None
        # The result message shown when that export completed -- restored
        # verbatim (never recomputed) whenever _show_ready() decides the
        # completion banner still legitimately applies, so re-entering the
        # Export step doesn't silently drop the "Exported N files to
        # <destination>." confirmation that _on_export_succeeded() showed.
        self._completed_result_message: Optional[str] = None
        # Set by _on_export_succeeded()/_on_export_failed() for the current
        # (non-stale) dispatched worker only -- read by _on_export_worker_
        # finished() when it emits export_finished, so that signal always
        # reflects the outcome of the run it's reporting on.
        self._last_export_succeeded = False
        # Ownership model: an export operation belongs to the deck that was
        # loaded when it began, for as long as it runs -- never to whatever
        # deck happens to be loaded by the time its results arrive.
        # _pdf_generation is that ownership epoch, bumped on every
        # set_pdf(); each _ExportWorker is stamped with it at dispatch time
        # and carries that stamp for its whole life. Every place that would
        # otherwise trust "a worker exists" or "a worker's signal fired" as
        # meaning "this describes the deck on screen" must instead compare
        # generations -- see on_shown()'s guard and
        # _is_stale_worker_signal(), which are this invariant's two
        # enforcement points.
        self._pdf_generation = 0

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.setSpacing(14)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        # -- blocked-state message (not ready, or a stale snapshot) --------
        self._blocked_label = QLabel("")
        self._blocked_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._blocked_label.setWordWrap(True)
        self._blocked_label.setMaximumWidth(480)
        self._blocked_label.setStyleSheet(
            f"font-size: {FONT_BODY}px; color: {TEXT_BODY}; background: transparent;"
        )
        self._blocked_label.setVisible(False)
        outer.addWidget(self._blocked_label, 0, Qt.AlignmentFlag.AlignHCenter)

        # -- ready panel: summary + destination + Export -------------------
        self._ready_panel = QWidget()
        ready_layout = QVBoxLayout(self._ready_panel)
        ready_layout.setContentsMargins(0, 0, 0, 0)
        ready_layout.setSpacing(14)
        ready_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._heading = QLabel("Export your cards.")
        self._heading.setStyleSheet(
            f"font-size: {FONT_H2}px; font-weight: 700; color: {TEXT_HEADING}; background: transparent;"
        )
        ready_layout.addWidget(self._heading)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            f"font-size: {FONT_BODY}px; color: {TEXT_BODY}; background: transparent;"
        )
        ready_layout.addWidget(self._summary_label)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(10)
        self._destination_label = QLabel("No destination folder chosen.")
        self._destination_label.setWordWrap(True)
        self._destination_label.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {TEXT_BODY}; background: transparent;"
        )
        dest_row.addWidget(self._destination_label, 1)
        self._choose_folder_btn = QPushButton("Choose Folder…")
        self._choose_folder_btn.setAutoDefault(False)
        self._choose_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._choose_folder_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._choose_folder_btn.clicked.connect(self._choose_destination)
        dest_row.addWidget(self._choose_folder_btn)
        ready_layout.addLayout(dest_row)

        self._export_btn = QPushButton("Export")
        self._export_btn.setAutoDefault(False)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export_clicked)
        ready_layout.addWidget(self._export_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._exporting_label = QLabel("")
        self._exporting_label.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {TEXT_BODY}; background: transparent;"
        )
        self._exporting_label.setVisible(False)
        ready_layout.addWidget(self._exporting_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate -- no per-file granularity to report
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setMaximumWidth(280)
        self._progress_bar.setStyleSheet(_PROGRESS_STYLE)
        self._progress_bar.setVisible(False)
        ready_layout.addWidget(self._progress_bar, 0, Qt.AlignmentFlag.AlignLeft)

        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {ACCENT}; font-weight: 600; background: transparent;"
        )
        self._result_label.setVisible(False)
        ready_layout.addWidget(self._result_label)

        completion_row = QHBoxLayout()
        completion_row.setSpacing(10)
        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setAutoDefault(False)
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._open_folder_btn.clicked.connect(self._open_destination_folder)
        completion_row.addWidget(self._open_folder_btn)
        self._start_new_deck_btn = QPushButton("Start New Deck")
        self._start_new_deck_btn.setAutoDefault(False)
        self._start_new_deck_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_new_deck_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self._start_new_deck_btn.clicked.connect(self.start_new_deck_clicked.emit)
        completion_row.addWidget(self._start_new_deck_btn)
        completion_row.addStretch(1)
        self._completion_row = QWidget()
        self._completion_row.setLayout(completion_row)
        self._completion_row.setVisible(False)
        ready_layout.addWidget(self._completion_row)

        outer.addWidget(self._ready_panel)
        outer.addStretch(1)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        outer.addWidget(self._status_label)

        footer = QHBoxLayout()
        self._back_to_review_btn = QPushButton("‹ Back to Review Cards")
        self._back_to_review_btn.setAutoDefault(False)
        self._back_to_review_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_to_review_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._back_to_review_btn.clicked.connect(self.back_to_review_clicked.emit)
        footer.addWidget(self._back_to_review_btn)
        footer.addStretch(1)
        outer.addLayout(footer)

    # -- PDF loading -------------------------------------------------------

    def set_pdf(self, pdf_path: Path, page_count: int) -> None:
        # Bumped before _close_renderer() waits on any still-running worker,
        # so that worker's succeeded/failed signal -- already queued for
        # delivery once we're back in the event loop -- is recognizable as
        # stale by the time it arrives (see _is_stale_worker_signal()).
        self._pdf_generation += 1
        self._close_renderer()
        self._renderer = PDFRenderer(pdf_path)
        self._destination = None
        self._plan = None
        # A completed export (or one in whatever state _export_complete was
        # in) belongs to the PDF that was just replaced -- never carry it
        # forward to describe this new one, even if this new plan later
        # happens to look identical.
        self._export_complete = False
        self._completed_plan = None
        self._completed_result_message = None

    def is_exporting(self) -> bool:
        """True only while a background export is actually live -- checks
        the underlying QThread's real running state (isRunning()), not
        just "a worker object exists": self._worker is only cleared back
        to None from _on_export_worker_finished(), a queued cross-thread
        slot, so there is a brief window after run() returns where a
        finished-but-not-yet-running worker object is still referenced.
        Callers (MainWindow.closeEvent()) must not treat that window as
        "still exporting"."""
        return self._worker is not None and self._worker.isRunning()

    def wait_for_export(self) -> None:
        """Blocks the calling (GUI) thread until the live export worker's
        run() has returned -- the same join _close_renderer() already used
        for the PDF-switch-mid-export case, now shared rather than
        duplicated. A no-op when is_exporting() is False, so it's safe to
        call unconditionally.

        Not used by MainWindow.closeEvent() -- an unbounded join on the GUI
        thread leaves the real window Windows-hung for however long the
        export takes (confirmed via IsHungAppWindow() during
        investigation). closeEvent()'s deferred close instead waits on
        export_finished, which fires from the GUI thread's own event loop
        once the worker is actually done, never blocking it. This method
        still only fits the PDF-switch-mid-export case, where a
        genuinely brief join is acceptable."""
        if self.is_exporting():
            self._worker.wait()

    def _close_renderer(self) -> None:
        # A new PDF was chosen while a background export was still running
        # (e.g. via the sidebar, mid-export) -- wait for it to finish
        # before the renderer it's reading from is closed out from under
        # it, rather than racing a close against PyMuPDF calls on another
        # thread.
        self.wait_for_export()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    # -- shared-app-frame hooks ---------------------------------------------

    def on_shown(self) -> None:
        self._result_label.setVisible(False)
        if self._worker is not None and self._worker.pdf_generation == self._pdf_generation:
            # An export for this same PDF is still running in the
            # background -- leave the in-progress UI (_on_export_clicked()
            # set it up) alone rather than rebuilding the ready panel over
            # it, which would re-enable Export and hide the progress bar
            # out from under a worker that's still writing files.
            # _on_export_succeeded()/_on_export_worker_finished() will
            # update the view normally once it finishes, same as if Export
            # had stayed the visible page the whole time. A self._worker
            # from a previous generation (set_pdf() was called since it was
            # dispatched, but its finished signal hasn't drained yet) is
            # not this case -- fall through to the normal rebuild below.
            return
        self._rebuild()

    def set_pan_active(self, active: bool) -> None:
        """No-op: Export has no page to pan -- it's not a Calibrate step."""

    # -- building the view ---------------------------------------------------

    def _page_size(self, page_num: int) -> tuple[float, float]:
        assert self._renderer is not None
        return self._renderer.page_size(page_num)

    def _rebuild(self) -> None:
        cards_target = self.calibrate_state.cards
        back_target = self.calibrate_state.back
        shared_back_status = self.find_cards_state.shared_back_status()

        if not export_ready(cards_target, back_target, shared_back_status, self.review_state):
            self._show_blocked(
                export_guidance_text(cards_target, back_target, shared_back_status, self.review_state)[1],
                export_status_text(cards_target, back_target, shared_back_status, self.review_state),
            )
            return

        if self._renderer is None:
            # Defensive only -- Export is unreachable before a PDF is
            # loaded (is_reached(EXPORT) requires having passed through
            # Review Cards, which requires a loaded PDF).
            self._show_blocked("Load a PDF to continue.", "No PDF loaded.")
            return

        front_pages = self.find_cards_state.front_pages()
        if not review_snapshot_is_current(self.review_state, front_pages, cards_target, self._page_size):
            headline, body = stale_review_guidance_text()
            self._show_blocked(body, stale_review_status_text())
            return

        self._show_ready(cards_target, back_target, shared_back_status)

    def _show_blocked(self, body: str, status: str) -> None:
        self._ready_panel.setVisible(False)
        self._blocked_label.setText(body)
        self._blocked_label.setVisible(True)
        self._status_label.setText(status)

    def _show_ready(
        self,
        cards_target: CalibrationTarget,
        back_target: CalibrationTarget,
        shared_back_status: SharedBackStatus,
    ) -> None:
        self._blocked_label.setVisible(False)
        self._ready_panel.setVisible(True)
        # Only reachable when on_shown()'s guard has already established
        # there's no active same-generation worker (see _pdf_generation) --
        # so any "Exporting..."/progress-bar state still visible here is
        # necessarily left over from an abandoned PDF's worker whose
        # finished signal hasn't drained yet, and must not bleed into this
        # (possibly different) deck's ready panel.
        self._exporting_label.setVisible(False)
        self._progress_bar.setVisible(False)

        self._plan = build_export_plan(self.review_state, cards_target, back_target, shared_back_status)
        if self._export_complete and self._plan != self._completed_plan:
            # Something changed (e.g. a card toggled back in Review Cards)
            # since the export that completed -- the completion banner
            # would otherwise describe a plan no longer shown below it.
            self._export_complete = False
        elif self._export_complete:
            # Legitimate re-entry (e.g. a trip to Review Cards and back
            # with nothing changed) -- restore the exact message shown when
            # the export finished rather than leaving it hidden (on_shown()
            # unconditionally hides _result_label) or recomputing it.
            self._show_result(self._completed_result_message, is_error=False)
        noun = "card" if self._plan.card_count == 1 else "cards"
        back_clause = " plus a shared back" if self._plan.has_back else " (this deck has no Shared Back)"
        self._summary_label.setText(f"{self._plan.card_count} {noun}{back_clause}, saved as individual PNG files.")

        self._update_destination_label()
        self._apply_completion_visibility()
        if not self._export_complete:
            self._export_btn.setEnabled(self._destination is not None)
        self._status_label.setText(
            export_status_text(cards_target, back_target, shared_back_status, self.review_state)
        )

    def _apply_completion_visibility(self) -> None:
        """Switches the ready panel between "about to export" (destination
        picker + Export button) and "just finished" (Open Folder + Start
        New Deck) -- see this module's docstring family for why Export has
        no per-card grid of its own to also toggle."""
        self._heading.setText("Export complete." if self._export_complete else "Export your cards.")
        self._destination_label.setVisible(not self._export_complete)
        self._choose_folder_btn.setVisible(not self._export_complete)
        self._export_btn.setVisible(not self._export_complete)
        self._completion_row.setVisible(self._export_complete)
        self._back_to_review_btn.setVisible(not self._export_complete)

    def _update_destination_label(self) -> None:
        if self._destination is None:
            self._destination_label.setText("No destination folder chosen.")
        else:
            self._destination_label.setText(f"Destination: {self._destination}")

    # -- interaction -----------------------------------------------------

    def _choose_destination(self) -> None:
        path_str = QFileDialog.getExistingDirectory(self, "Choose a folder for your exported cards", str(Path.home()))
        if not path_str:
            return
        self._destination = Path(path_str)
        self._result_label.setVisible(False)
        self._update_destination_label()
        self._export_btn.setEnabled(self._plan is not None)

    def _confirm_overwrite_if_needed(self) -> bool:
        """True if it's safe to proceed with export -- either nothing in
        the destination would be overwritten, or the user explicitly chose
        to overwrite anyway. Cancel is both the default button (Enter) and
        the escape button (Esc / closing the dialog), so an accidental
        dismissal never overwrites existing files."""
        assert self._plan is not None and self._destination is not None
        existing = existing_output_files(self._destination, self._plan)
        if not existing:
            return True

        noun = "file" if len(existing) == 1 else "files"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Overwrite existing files?")
        box.setText(f"This folder already has {len(existing)} {noun} this export would overwrite.")
        box.setInformativeText("Choose a different folder, or continue to overwrite them.")
        overwrite_btn = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.setEscapeButton(cancel_btn)
        box.exec()
        return box.clickedButton() is overwrite_btn

    def _on_export_clicked(self) -> None:
        # self._worker is not None guards against a double dispatch --
        # belt-and-suspenders alongside the button itself being disabled
        # for the whole time a worker is running.
        if self._plan is None or self._destination is None or self._renderer is None or self._worker is not None:
            return

        if not self._confirm_overwrite_if_needed():
            return

        cells = [(c.page_num, c.row, c.col) for c in self._plan.front_cells]

        self._result_label.setVisible(False)
        self._export_btn.setEnabled(False)
        self._choose_folder_btn.setEnabled(False)
        noun = "card" if self._plan.card_count == 1 else "cards"
        self._exporting_label.setText(f"Exporting {self._plan.card_count} {noun}…")
        self._exporting_label.setVisible(True)
        self._progress_bar.setVisible(True)

        self._worker = _ExportWorker(
            self._renderer, EXPORT_RENDER_SCALE, self._plan.front_geometry,
            cells, self._destination, self._plan.back,
            pdf_generation=self._pdf_generation, parent=self,
        )
        _logger.info(
            "Export started: %d cards -> %s", self._plan.card_count, self._destination.name,
        )
        self._worker.succeeded.connect(self._on_export_succeeded)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.finished.connect(self._on_export_worker_finished)
        self._worker.start()

    def _is_stale_worker_signal(self) -> bool:
        """True if the worker whose signal is currently being handled was
        dispatched for a PDF the user has since switched away from via
        set_pdf() -- that worker's succeeded/failed payload describes a
        deck that's no longer loaded and must not touch _export_complete,
        the completion banner, or the result message. self.sender() is the
        _ExportWorker that emitted the signal being handled, valid for a
        queued cross-thread connection same as a direct one."""
        worker = self.sender()
        return isinstance(worker, _ExportWorker) and worker.pdf_generation != self._pdf_generation

    def _on_export_succeeded(self, written: list, destination: Path) -> None:
        if self._is_stale_worker_signal():
            return
        # destination is the worker's own snapshot, not self._destination --
        # see _ExportWorker.succeeded's docstring comment for why re-reading
        # the live instance attribute here would be wrong.
        plural = "s" if len(written) != 1 else ""
        message = f"Exported {len(written)} file{plural} to {destination}."
        # Destination is already logged at export start (_on_export_clicked)
        # and doesn't change mid-export, so it's not repeated here.
        _logger.info("Export succeeded: %d files", len(written))
        self._show_result(message, is_error=False)
        self._export_complete = True
        self._completed_plan = self._plan
        self._completed_result_message = message
        self._last_export_succeeded = True
        self._apply_completion_visibility()

    def _on_export_failed(self, message: str) -> None:
        if self._is_stale_worker_signal():
            return
        _logger.warning("Export failed: %s", message)
        self._show_result(f"Couldn't finish exporting: {message}", is_error=True)
        self._last_export_succeeded = False

    def _on_export_worker_finished(self) -> None:
        # Runs after _on_export_succeeded/_on_export_failed either way --
        # QThread.finished always follows run() returning, regardless of
        # which signal it emitted first.
        is_current = not self._is_stale_worker_signal()
        self._exporting_label.setVisible(False)
        self._progress_bar.setVisible(False)
        self._choose_folder_btn.setEnabled(True)
        if not self._export_complete:
            self._export_btn.setEnabled(self._destination is not None)
        self._worker = None
        if is_current:
            # A stale worker (pdf_generation from a PDF the user has since
            # switched away from) never reaches here as "current" -- no
            # deferred close is ever waiting on it, since MainWindow only
            # ever observes is_exporting() for the worker matching today's
            # PDF.
            self.export_finished.emit(self._last_export_succeeded)

    def _open_destination_folder(self) -> None:
        if self._destination is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._destination)))

    def _show_result(self, message: str, is_error: bool) -> None:
        color = ERROR_TEXT if is_error else ACCENT
        self._result_label.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {color}; font-weight: 600; background: transparent;"
        )
        self._result_label.setText(message)
        self._result_label.setVisible(True)
