"""Regression coverage for asynchronous deferred shutdown during an active
export (docs/ALPHA_HARDENING_PLAN.md §2). MainWindow.closeEvent() must
never block the GUI thread on a live _ExportWorker: it must stay fully
responsive, defer the actual close until export_workspace reports (via its
export_finished signal) that the worker has finished and its own
success/failure handling + cleanup are complete, and never let a failed
export be silently swallowed by quitting anyway.

An earlier version of this test file drove MainWindow.closeEvent() with a
synthetic, direct call and never entered a real QApplication.exec() loop.
That was blind to the actual failure mode: a blocking QThread.wait() call
inside closeEvent() froze the GUI thread with no message pumping for the
whole export, which Windows itself recognizes as a hung window
(IsHungAppWindow() during investigation) -- something a direct closeEvent()
call, with no real event loop running, can never exercise or detect. The
tests below drive a real app.exec() loop with a deliberately slow worker
pipeline so an unresponsive GUI thread would actually show up as a
regression (missed timer ticks, a closeEvent() call that doesn't return
until the export finishes, etc.).

Same underlying pipeline as tests/test_export_workspace.py's
TestExportReentry: a real PDFRenderer/QThread/export_cells() run against
the sample deck, under QT_QPA_PLATFORM=offscreen, no pytest-qt.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from deckforge_gui.calibrate_state import CalibratedGeometry
from deckforge_gui.find_cards_state import PageRole
from deckforge_gui.main_window import MainWindow
from deckforge_gui.review_state import build_review_cards
import deckforge_gui.export_workspace as export_workspace_mod

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "Solo-cards-digital.pdf"

# Same real, --preview-verified geometry test_export_workspace.py uses
# against this sample PDF.
FRONT_GEOMETRY = CalibratedGeometry(
    left=35.75, top=61.25, card_width=174.58, card_height=239.75,
    gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
)
FRONT_PAGE = 2

# Safety net for the app.exec()-driven tests: fails the test with a clear
# assertion (window still visible) instead of hanging CI forever if a
# regression stops the deferred close from ever firing.
WATCHDOG_MS = 8000


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def window(qapp: QApplication) -> MainWindow:
    return MainWindow()


def _prepare_export(window: MainWindow, tmp_path: Path) -> None:
    """Loads the sample deck and builds a real, dispatchable one-cell
    export plan -- trimmed to one cell so an undelayed run stays fast, and
    Shared Back confirmed absent so the expected output is exactly
    front_001.png with no back.png."""
    workspace = window.export_workspace
    workspace.set_pdf(SAMPLE_PDF, 12)
    workspace.find_cards_state.set_role(FRONT_PAGE, PageRole.FRONT)
    workspace.find_cards_state.confirm_no_shared_back()
    workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
    workspace.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
    cards = build_review_cards([FRONT_PAGE], FRONT_GEOMETRY, workspace._page_size)
    workspace.review_state.sync(cards)
    for extra_card in cards[1:]:
        workspace.review_state.toggle(extra_card)  # keep only the first cell included
    workspace.on_shown()  # builds self._plan via _rebuild()/_show_ready()
    workspace._destination = tmp_path
    workspace._export_btn.setEnabled(True)


def _dispatch_export(window: MainWindow, tmp_path: Path) -> None:
    _prepare_export(window, tmp_path)
    window.export_workspace._on_export_clicked()
    assert window.export_workspace._worker is not None


def _install_slow_export(monkeypatch, delay_s: float) -> None:
    """Stands in for a real large Doom-Pilgrim-sized export: a delay
    inside the worker's real call to export_cells(), long enough that a
    blocking wait() would visibly freeze the event loop, without needing
    an actual multi-minute PDF in the test suite."""
    real_export_cells = export_workspace_mod.export_cells

    def _slow(*args, **kwargs):
        time.sleep(delay_s)
        return real_export_cells(*args, **kwargs)

    monkeypatch.setattr(export_workspace_mod, "export_cells", _slow)


def _install_failing_export(monkeypatch, message: str = "disk is full") -> None:
    def _fail(*args, **kwargs):
        raise OSError(message)

    monkeypatch.setattr(export_workspace_mod, "export_cells", _fail)


def _drain_until_worker_done(qapp: QApplication, window: MainWindow, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while window.export_workspace._worker is not None:
        assert time.monotonic() < deadline, "background export worker did not finish in time"
        qapp.processEvents()
        time.sleep(0.01)


class TestCloseEventNoActiveExport:
    def test_close_with_no_export_running_closes_normally(self, window: MainWindow) -> None:
        assert window.export_workspace.is_exporting() is False
        called = []
        window._confirm_quit_during_export = lambda: called.append(True) or True  # type: ignore[method-assign]

        event = QCloseEvent()
        window.closeEvent(event)

        assert called == [], "the confirmation dialog must never appear when nothing is exporting"
        assert event.isAccepted() is True
        assert window._close_after_export is False


class TestKeepDeckForgeOpen:
    def test_keep_deckforge_open_ignores_the_close_and_leaves_the_export_running(
        self, qapp: QApplication, window: MainWindow, tmp_path: Path,
    ) -> None:
        _dispatch_export(window, tmp_path)
        assert window.export_workspace.is_exporting() is True
        window._confirm_quit_during_export = lambda: False  # type: ignore[method-assign]

        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted() is False
        assert window._close_after_export is False
        # "Keep DeckForge Open" means exactly that -- the export keeps
        # running, untouched.
        assert window.export_workspace._worker is not None
        assert window.export_workspace.is_exporting() is True

        _drain_until_worker_done(qapp, window)  # let it finish so it doesn't leak into other tests

    def test_worker_present_but_finished_does_not_trigger_the_warning(
        self, qapp: QApplication, window: MainWindow, tmp_path: Path,
    ) -> None:
        """Reproduces the brief window between run() returning and
        _on_export_worker_finished() (a queued cross-thread slot)
        resetting self._worker back to None: is_exporting() must key off
        isRunning(), not object presence, so closeEvent() must not show
        the confirmation dialog in this state."""
        _dispatch_export(window, tmp_path)
        workspace = window.export_workspace
        worker = workspace._worker
        assert worker is not None

        worker.wait()  # real join, direct from the test -- not from closeEvent()
        assert worker.isRunning() is False
        assert workspace._worker is worker  # still set, by construction

        assert workspace.is_exporting() is False

        called = []
        window._confirm_quit_during_export = lambda: called.append(True) or True  # type: ignore[method-assign]
        event = QCloseEvent()
        window.closeEvent(event)

        assert called == []
        assert event.isAccepted() is True

        _drain_until_worker_done(qapp, window)  # let the queued signals drain for a clean fixture teardown


class TestDeferredCloseResponsiveness:
    """The heart of the regression: closing during a real, deliberately
    slow export must never block the GUI thread. Driven through a real
    QApplication.exec() loop (not a synthetic direct closeEvent() call) so
    an unresponsive event loop would actually manifest as a test
    failure."""

    def test_wait_and_close_stays_responsive_and_closes_only_after_export_completes(
        self, monkeypatch, tmp_path: Path,
    ) -> None:
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        _install_slow_export(monkeypatch, delay_s=1.5)
        _dispatch_export(window, tmp_path)
        window._confirm_quit_during_export = lambda: True  # type: ignore[method-assign]

        tick_count = 0

        def _tick() -> None:
            nonlocal tick_count
            tick_count += 1

        ticker = QTimer()
        ticker.timeout.connect(_tick)
        ticker.start(20)  # only keeps firing if the event loop is actually pumping

        close_call_durations = []

        def _trigger_close() -> None:
            before = time.monotonic()
            window.close()
            close_call_durations.append(time.monotonic() - before)

        QTimer.singleShot(50, _trigger_close)
        QTimer.singleShot(WATCHDOG_MS, app.quit)

        app.exec()

        assert close_call_durations, "window.close() was never triggered"
        # closeEvent() itself must return essentially instantly -- it must
        # defer, never block, regardless of how long the export takes.
        assert close_call_durations[0] < 0.2, (
            f"closeEvent() took {close_call_durations[0]:.3f}s -- it must defer, not block on the worker"
        )
        # The event loop must have kept running normally for the ~1.5s the
        # export was in flight (20ms ticks => tens of them; a blocked GUI
        # thread would starve this near zero).
        assert tick_count > 30, f"only {tick_count} timer ticks fired while exporting -- the GUI thread was blocked"
        assert window.isVisible() is False, "the window must actually close once the export finishes"
        assert window.export_workspace._worker is None
        assert (tmp_path / "front_001.png").exists()
        assert sorted(p.name for p in tmp_path.iterdir()) == ["front_001.png"]

    def test_repeated_close_attempts_while_deferred_do_not_stack_dialogs_or_closes(
        self, monkeypatch, tmp_path: Path,
    ) -> None:
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        _install_slow_export(monkeypatch, delay_s=1.0)
        _dispatch_export(window, tmp_path)

        confirm_calls = []
        window._confirm_quit_during_export = lambda: confirm_calls.append(True) or True  # type: ignore[method-assign]

        QTimer.singleShot(50, window.close)
        QTimer.singleShot(150, window.close)   # impatient repeat while deferred
        QTimer.singleShot(250, window.close)   # and again
        QTimer.singleShot(WATCHDOG_MS, app.quit)

        app.exec()

        assert len(confirm_calls) == 1, "a repeat close attempt while a deferred close is pending must not re-prompt"
        assert window.isVisible() is False
        assert (tmp_path / "front_001.png").exists()


class TestExportFinishesWhileConfirmationDialogIsStillOpen:
    """_confirm_quit_during_export()'s QMessageBox.exec() runs a real
    nested event loop, so the export can finish -- and export_finished can
    already have fired, while _close_after_export was still False -- before
    the user answers the dialog. If closeEvent() naively armed the
    deferred-close flag on that stale assumption, it would wait forever on
    a signal that already came and went. It must instead notice the export
    is already done and close immediately, the same as the ordinary
    no-export path."""

    def test_export_completing_before_the_dialog_is_answered_closes_immediately(
        self, qapp: QApplication, tmp_path: Path,
    ) -> None:
        window = MainWindow()
        _dispatch_export(window, tmp_path)  # fast, undelayed export
        assert window.export_workspace.is_exporting() is True

        def _confirm_after_export_has_actually_finished() -> bool:
            # Stands in for a real QMessageBox.exec()'s nested loop running
            # long enough (the user taking a moment to read/click) that the
            # real, fast export completes before an answer is given.
            deadline = time.monotonic() + 5.0
            while window.export_workspace._worker is not None:
                assert time.monotonic() < deadline, "export did not finish in time for this race to be exercised"
                qapp.processEvents()
                time.sleep(0.01)
            return True  # the user finally clicks "Finish Export, Then Close"

        window._confirm_quit_during_export = _confirm_after_export_has_actually_finished  # type: ignore[method-assign]

        # closeEvent() calls _confirm_quit_during_export() internally --
        # by the time it returns True, the loop above has already driven
        # the real export to completion (the race precondition).
        event = QCloseEvent()
        window.closeEvent(event)

        assert window.export_workspace.is_exporting() is False  # confirms the race was actually exercised
        assert event.isAccepted() is True, "the export was already done -- this must close immediately, not defer"
        assert window._close_after_export is False, "a deferred close must never be armed for a signal that already fired"
        assert (tmp_path / "front_001.png").exists()


class TestFailedExportDoesNotConcealFailureByQuitting:
    def test_failed_export_clears_pending_close_and_leaves_window_open(
        self, monkeypatch, tmp_path: Path,
    ) -> None:
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        _install_failing_export(monkeypatch, "disk is full")
        _dispatch_export(window, tmp_path)
        window._confirm_quit_during_export = lambda: True  # type: ignore[method-assign]

        QTimer.singleShot(50, window.close)

        def _check_and_quit() -> None:
            assert window.isVisible() is True, "a failed export must leave DeckForge open, not quit silently"
            assert window._close_after_export is False, "the pending-close request must be cleared on failure"
            assert window.export_workspace._result_label.isVisible() is True
            assert "disk is full" in window.export_workspace._result_label.text()
            app.quit()

        QTimer.singleShot(600, _check_and_quit)
        QTimer.singleShot(WATCHDOG_MS, app.quit)

        app.exec()


class TestNoBlockingWaitDuringClose:
    def test_close_event_never_joins_the_worker_thread(self, monkeypatch, tmp_path: Path) -> None:
        from deckforge_gui.export_workspace import _ExportWorker

        qapp = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        _install_slow_export(monkeypatch, delay_s=1.0)
        _dispatch_export(window, tmp_path)
        window._confirm_quit_during_export = lambda: True  # type: ignore[method-assign]

        wait_calls = []
        real_wait = _ExportWorker.wait

        def _tracked_wait(self, *args, **kwargs):
            wait_calls.append(True)
            return real_wait(self, *args, **kwargs)

        monkeypatch.setattr(_ExportWorker, "wait", _tracked_wait)

        event = QCloseEvent()
        window.closeEvent(event)

        assert wait_calls == [], "closeEvent() must never call QThread.wait() on the worker directly"
        assert event.isAccepted() is False
        assert window._close_after_export is True

        _drain_until_worker_done(qapp, window)
        assert wait_calls == [], "the deferred close must still never have joined the worker directly"
