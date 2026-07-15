"""Regression coverage for the "Exported N files to None" bug:
ExportWorkspace._on_export_succeeded() must report the destination the
background worker actually wrote to (carried by _ExportWorker.succeeded's
signal payload), not self._destination -- which set_pdf() resets to None
if the user switches PDFs while a worker is still running, and which
could just as easily point at a *different*, newly-chosen destination by
the time the slot fires.

This is the first widget-level test in the suite (see
docs/RELEASE_READINESS.md's "No widget/thread-level regression tests"
open item) -- kept deliberately narrow: it calls the slot directly with a
synthetic signal payload, no real QThread/export pipeline involved, so it
needs no PDF fixture or real export plan.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrateState
from deckforge_gui.export_workspace import ExportWorkspace
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.review_state import ReviewCardsState, build_review_cards

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "Solo-cards-digital.pdf"

# Real, --preview-verified geometry from profiles/solo_cards.json (same
# constant test_cell_export.py uses against this sample PDF), so the
# reentry tests below exercise a real PDFRenderer/QThread/export_cells()
# pipeline rather than a synthetic one.
FRONT_GEOMETRY = CalibratedGeometry(
    left=35.75, top=61.25, card_width=174.58, card_height=239.75,
    gap_x=0.0, gap_y=0.0, gap_x_derived=False, gap_y_derived=False,
)
FRONT_PAGE = 2


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def workspace(qapp: QApplication) -> ExportWorkspace:
    return ExportWorkspace(CalibrateState(), FindCardsState(), ReviewCardsState())


def _make_ready(workspace: ExportWorkspace, front_page: int = FRONT_PAGE) -> None:
    """Wires calibrate_state/find_cards_state/review_state into a fully
    export_ready() configuration against whatever PDF is currently loaded
    on `workspace` -- real calibrated geometry, one front page, Shared
    Back explicitly confirmed absent, and review_state synced from a real
    page-size lookup. Trims the synced grid down to its first cell only,
    so the real background export a reentry test triggers stays fast."""
    workspace.find_cards_state._roles.clear()
    workspace.find_cards_state.set_role(front_page, PageRole.FRONT)
    workspace.find_cards_state.confirm_no_shared_back()
    workspace.calibrate_state.cards.reset()
    workspace.calibrate_state.back.reset()
    workspace.calibrate_state.cards.geometry = FRONT_GEOMETRY
    workspace.calibrate_state.cards.calibrated_page_num = front_page
    cards = build_review_cards([front_page], FRONT_GEOMETRY, workspace._page_size)
    workspace.review_state.sync(cards)
    for extra_card in cards[1:]:
        workspace.review_state.toggle(extra_card)  # keep only the first cell included


def _drain_until_worker_done(qapp: QApplication, workspace: ExportWorkspace, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while workspace._worker is not None:
        assert time.monotonic() < deadline, "background export worker did not finish in time"
        qapp.processEvents()
        time.sleep(0.01)


class TestExportCompletionMessageUsesSignalPayload:
    def test_uses_the_destination_carried_by_the_signal_not_self_destination(
        self, workspace: ExportWorkspace,
    ) -> None:
        """self._destination is a stale/different value at slot time (as it
        would be after set_pdf() reset it) -- the message must still show
        the destination the worker actually wrote to."""
        workspace._destination = Path("stale") / "unrelated" / "path"

        workspace._on_export_succeeded(["front_001.png", "back.png"], Path("real") / "destination")

        text = workspace._result_label.text()
        assert str(Path("real") / "destination") in text
        assert "stale" not in text

    def test_reports_correctly_even_when_self_destination_is_none(
        self, workspace: ExportWorkspace,
    ) -> None:
        """The exact repro: self._destination is None (set_pdf() was called
        mid-export), which must no longer produce "...to None."."""
        workspace._destination = None

        workspace._on_export_succeeded(["front_001.png"], Path("real") / "destination")

        text = workspace._result_label.text()
        assert "None" not in text
        assert str(Path("real") / "destination") in text

    def test_message_counts_and_pluralizes_correctly(self, workspace: ExportWorkspace) -> None:
        destination = Path("some") / "folder"

        workspace._on_export_succeeded(["front_001.png"], destination)
        assert workspace._result_label.text() == f"Exported 1 file to {destination}."

        workspace._on_export_succeeded(["front_001.png", "front_002.png", "back.png"], destination)
        assert workspace._result_label.text() == f"Exported 3 files to {destination}."

    def test_marks_export_complete(self, workspace: ExportWorkspace) -> None:
        assert workspace._export_complete is False
        workspace._on_export_succeeded(["front_001.png"], Path("dest"))
        assert workspace._export_complete is True


class TestExportFailureLogging:
    """Regression coverage for a privacy leak: _on_export_failed() used to
    re-log the worker's raw exception message via _logger.warning(), which
    can be an arbitrary OSError whose str() embeds the full destination
    path -- e.g. a failed write partway through export. The in-app message
    is allowed to show the user their own path; the persistent log file is
    not (see logging_setup.py's privacy stance and pdf_renderer.py's
    matching fix for the equivalent PDF-load-failure leak)."""

    def test_failure_message_is_shown_to_the_user_but_not_logged(
        self, workspace: ExportWorkspace, caplog: pytest.LogCaptureFixture,
    ) -> None:
        sensitive_message = "[Errno 13] Permission denied: 'C:\\Users\\someone\\private_project\\front_001.png'"

        with caplog.at_level("WARNING"):
            workspace._on_export_failed(sensitive_message)

        assert sensitive_message in workspace._result_label.text()
        assert not any(sensitive_message in record.getMessage() for record in caplog.records)
        assert not any("private_project" in record.getMessage() for record in caplog.records)


class TestExportReentry:
    """Regression coverage for the Export re-entry bug found while manually
    verifying the destination-message fix above: starting an export, then
    navigating elsewhere and back (optionally via a different PDF) before
    it finishes, left the workspace showing a wrong state -- a stale
    completion from an abandoned PDF, a "ready" panel with Export
    re-enabled over a worker still writing files, or a completion banner
    silently discarded on a plain revisit. These drive a real
    PDFRenderer/QThread/export_cells() pipeline (see _make_ready()/
    _drain_until_worker_done() above) because the bug is specifically
    about the timing of real cross-thread signal delivery relative to
    set_pdf()/on_shown() -- a synthetic slot call, like the tests above
    use, can't reproduce that race."""

    def test_revisiting_during_an_active_export_shows_progress_not_ready(
        self, qapp: QApplication, workspace: ExportWorkspace, tmp_path: Path,
    ) -> None:
        workspace.set_pdf(SAMPLE_PDF, 12)
        _make_ready(workspace)
        workspace.on_shown()
        workspace._destination = tmp_path
        workspace._export_btn.setEnabled(True)

        workspace._on_export_clicked()
        assert workspace._worker is not None

        # Simulate navigating to another step and straight back to Export
        # while the background export is still running.
        workspace.on_shown()

        assert workspace._worker is not None, "on_shown() must not have raced/blocked on the worker"
        assert workspace._exporting_label.isHidden() is False
        assert workspace._progress_bar.isHidden() is False
        assert workspace._export_btn.isHidden() is True or workspace._export_btn.isEnabled() is False
        assert workspace._export_complete is False

        _drain_until_worker_done(qapp, workspace)
        assert workspace._export_complete is True

    def test_revisiting_after_completion_with_nothing_changed_keeps_completion(
        self, qapp: QApplication, workspace: ExportWorkspace, tmp_path: Path,
    ) -> None:
        workspace.set_pdf(SAMPLE_PDF, 12)
        _make_ready(workspace)
        workspace.on_shown()
        workspace._destination = tmp_path
        workspace._export_btn.setEnabled(True)

        workspace._on_export_clicked()
        _drain_until_worker_done(qapp, workspace)
        assert workspace._export_complete is True

        # Navigate away and straight back -- nothing about the deck changed.
        workspace.on_shown()

        assert workspace._export_complete is True
        assert workspace._heading.text() == "Export complete."
        assert workspace._completion_row.isHidden() is False

    def test_revisiting_after_completion_restores_destination_message(
        self, qapp: QApplication, workspace: ExportWorkspace, tmp_path: Path,
    ) -> None:
        """Regression test: on_shown() unconditionally hides _result_label
        before rebuilding (so a stale prior message never bleeds into a
        different deck's view -- see the switch-mid-export test below),
        and only _show_ready() restoring the exact message _completed_
        result_message stored back -- never recomputing it -- brings the
        "Exported N files to <destination>." confirmation back into view
        on a plain revisit."""
        workspace.set_pdf(SAMPLE_PDF, 12)
        _make_ready(workspace)
        workspace.on_shown()
        workspace._destination = tmp_path
        workspace._export_btn.setEnabled(True)

        workspace._on_export_clicked()
        _drain_until_worker_done(qapp, workspace)
        assert workspace._export_complete is True
        expected_message = workspace._result_label.text()
        assert str(tmp_path) in expected_message

        # Navigate away and straight back -- nothing about the deck changed.
        workspace.on_shown()

        assert workspace._heading.text() == "Export complete."
        assert workspace._result_label.isHidden() is False
        assert workspace._result_label.text() == expected_message

    def test_changing_review_cards_after_completion_clears_it_on_revisit(
        self, qapp: QApplication, workspace: ExportWorkspace, tmp_path: Path,
    ) -> None:
        workspace.set_pdf(SAMPLE_PDF, 12)
        _make_ready(workspace)
        workspace.on_shown()
        workspace._destination = tmp_path
        workspace._export_btn.setEnabled(True)

        workspace._on_export_clicked()
        _drain_until_worker_done(qapp, workspace)
        assert workspace._export_complete is True

        # Include the previously-excluded card back in -- the completed
        # plan (1 card) no longer matches what Export would run now (2).
        for card in workspace.review_state.all_cards():
            if not workspace.review_state.is_included(card):
                workspace.review_state.toggle(card)

        workspace.on_shown()

        assert workspace._export_complete is False
        assert workspace._heading.text() == "Export your cards."
        assert workspace._completion_row.isHidden() is True

    def test_switching_pdfs_mid_export_does_not_corrupt_the_new_decks_export_ui(
        self, qapp: QApplication, workspace: ExportWorkspace, tmp_path: Path,
    ) -> None:
        """The exact reported repro: start exporting a deck, immediately
        open a different deck (set_pdf()) while it's still running, then
        navigate straight to Export for the new deck -- before draining
        the event loop, and again after. Neither point may show the old
        deck's completion state, and neither point may show the old deck's
        in-progress ("Exporting...") state either -- the new deck has not
        started an export at all."""
        workspace.set_pdf(SAMPLE_PDF, 12)
        _make_ready(workspace)
        workspace.on_shown()
        workspace._destination = tmp_path
        workspace._export_btn.setEnabled(True)

        workspace._on_export_clicked()
        assert workspace._worker is not None

        # "Open a different deck" -- set_pdf() blocks until the old
        # worker's thread joins, but its succeeded/finished signals are
        # still queued for delivery once we're back in the event loop.
        workspace.set_pdf(SAMPLE_PDF, 12)
        assert workspace._destination is None
        assert workspace._plan is None

        # Reconfigure state the way MainWindow._on_pdf_chosen() does for a
        # newly (re)loaded deck, then go straight to Export -- before the
        # stale worker's queued signals have had a chance to drain.
        _make_ready(workspace)
        workspace.on_shown()

        assert workspace._export_complete is False
        assert workspace._heading.text() == "Export your cards."
        assert workspace._completion_row.isHidden() is True
        assert workspace._result_label.text() == ""
        # The abandoned deck's "Exporting..."/progress-bar state must not
        # bleed into the new deck's ready panel, even before the stale
        # worker's finished signal has had a chance to drain and hide them
        # itself -- _show_ready() must hide them unconditionally.
        assert workspace._exporting_label.isHidden() is True
        assert workspace._progress_bar.isHidden() is True

        # Now let the stale worker's queued succeeded/finished signals
        # actually fire -- they must be recognized as belonging to a PDF
        # this workspace has since switched away from.
        _drain_until_worker_done(qapp, workspace)

        assert workspace._export_complete is False
        assert workspace._heading.text() == "Export your cards."
        assert workspace._completion_row.isHidden() is True
        assert workspace._destination_label.isHidden() is False
        assert workspace._choose_folder_btn.isHidden() is False
        assert workspace._result_label.text() == ""
        assert workspace._exporting_label.isHidden() is True
        assert workspace._progress_bar.isHidden() is True
        assert workspace._plan is not None  # the new deck's own plan, rebuilt by on_shown()
