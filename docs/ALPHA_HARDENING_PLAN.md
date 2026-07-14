# Alpha Hardening — Design Review

Status: **review draft; §1 risk 3 (destination race on PDF switch) and
§1 risks 1, 2, and a newly found risk 4 (stale cross-deck export
completion) are all implemented and committed together (see
`docs/RELEASE_READINESS.md`'s Accomplished section) — risk 4 was found
while manually verifying risk 3's fix, and risks 1/2/4's fix was
deliberately reviewed as its own change before being folded into the
same commit as risk 3. §2 (safe shutdown during export) is also now
implemented, with its own regression tests (`tests/test_main_window.py`).
Everything else in this plan
has not been started.** Scope is deliberately
limited to six areas: export thread synchronization,
safe shutdown during export, regression testing, README accuracy, release
versioning, crash logging. Bugs found during manual alpha testing are
tracked separately (see `docs/RELEASE_READINESS.md`) and are not folded
into this plan's scope.

Each section: current state (traced from code), risks, smallest coherent
implementation, and a test plan.

---

## 1. Export thread synchronization

**Traced:** `deckforge_gui/export_workspace.py`. `_ExportWorker(QThread)` is
the only background thread in the codebase (verified — grepped `src/` for
`QThread`/`threading.`). `ExportWorkspace` owns exactly one `PDFRenderer`
(`self._renderer`), created in `set_pdf()`. `_on_export_clicked()` hands
that same renderer to the worker; `export_cells()` calls
`renderer.render_page()` on the worker thread for the whole export.

**Risks:**

1. **Cross-thread renderer access.** `ExportWorkspace.on_shown()` — called
   every time the user (re)navigates to the Export step via the sidebar,
   including while a worker is mid-run, since nothing currently blocks
   sidebar navigation during export — calls `_rebuild()`, which calls
   `review_snapshot_is_current(..., self._page_size)`. `self._page_size()`
   calls `self._renderer.page_size()`, which calls `fitz.Document.
   load_page()` on the GUI thread. If a worker is simultaneously calling
   `renderer.render_page()` (also `load_page()` + `get_pixmap()`) on the
   same `fitz.Document`, that's concurrent access to one PyMuPDF document
   from two threads with no lock. MuPDF is not documented as safe for
   unsynchronized concurrent use of a single document across threads —
   this is a real crash/corruption risk, not just a style concern.
   **Fixed:** `on_shown()` now returns early —
   skipping `_rebuild()` (and therefore this GUI-thread renderer call)
   entirely — whenever a worker for the currently-loaded PDF is still
   running. Side effect of the risk 2 fix below, not a separate change.
2. **Stale in-progress UI.** `_rebuild()` → `_show_ready()` unconditionally
   sets `self._export_btn.setEnabled(self._destination is not None)` and
   never checks `self._worker is not None`. Navigating away and back
   during an export hides the "Exporting…"/progress bar and makes the
   Export button look clickable again. `_on_export_clicked()`'s own
   `self._worker is not None` guard prevents an actual second dispatch,
   but the visible state lies to the user.
   **Fixed:** `on_shown()` checks `self._worker`
   before deciding whether to rebuild — guarded against a stale,
   already-finished worker reference left over from a since-abandoned PDF
   via the new `_pdf_generation` counter (see risk 4) — and leaves the
   in-progress UI untouched if a same-PDF worker is still active.
3. **Destination race on PDF switch — FIXED, see below.** `_close_renderer()`
   (called from `set_pdf()`) blocks the GUI thread on `self._worker.wait()`
   before tearing down the old renderer — correct in spirit, but
   `set_pdf()` also resets `self._destination = None` and `self._plan =
   None` as part of the same call, *before* the queued `succeeded`/`failed`
   signal from the just-finished worker is delivered. `_on_export_succeeded()`
   then reads `self._destination`, which is already `None` — the user sees
   "Exported 54 files to None." instead of the real folder, even though
   the files were written correctly.
4. **Stale cross-deck export completion.** Found while manually verifying
   risk 3's fix, not from tracing code up front. `set_pdf()` blocks on
   `self._worker.wait()` for the outgoing worker's thread to join, but
   never invalidates that worker's already-emitted `succeeded`/`finished`
   signals (already queued for cross-thread delivery) and never marks it
   as belonging to an abandoned PDF. If the user switches to a different
   deck while an export is running, and then brings *that* deck all the
   way to a genuinely ready-to-export state before the queued signals
   drain — ordinarily the very next event-loop turn, so the window is
   narrow but real, and easily wide enough to survive a few seconds of
   normal navigation — `_on_export_succeeded()` marks the new deck's
   Export as complete and shows the *old* deck's file count/destination
   message: a false "Export complete" for a deck that was never actually
   exported. Confirmed with a real `PDFRenderer`/`QThread`/`export_cells()`
   reproduction, not just reasoned about. Narrower than it first sounds:
   navigating straight to Export for a freshly-opened, not-yet-calibrated
   deck does *not* trigger this — `export_ready()` correctly blocks with a
   guidance message in that case regardless of this fix; the false
   completion only shows once the new deck is independently brought to
   "ready" while the old export's signals are still in flight.

**Smallest coherent implementation:**

- Guard `_rebuild()` (or `on_shown()`) with an early return when
  `self._worker is not None`: while a worker is active, leave the current
  "Exporting…" UI exactly as-is rather than rebuilding it. This removes
  the GUI-thread renderer call during an active export (fixes risk 1) and
  stops the button/progress UI from being clobbered (fixes risk 2) with
  one guard clause — no new state machine needed.
- Capture the destination path at dispatch time (e.g.
  `self._export_destination_snapshot = self._destination` set inside
  `_on_export_clicked()`) and have `_on_export_succeeded()` read that
  snapshot instead of `self._destination`. Fixes risk 3 without changing
  `_close_renderer()`'s existing (intentional) wait-before-close behavior.

  **Implemented, worker-centrically rather than via a dispatch-time
  snapshot attribute:** `_ExportWorker.succeeded` now carries the
  destination it actually wrote to as part of its signal payload
  (`Signal(list, Path)`, emitted as `self.succeeded.emit(written,
  self._destination)` from `run()`), and `_on_export_succeeded(written,
  destination)` uses that parameter instead of reading any
  `ExportWorkspace` instance attribute. Same guarantee as the snapshot
  approach above (the slot never re-reads workspace state that could have
  changed since dispatch) but the correct value lives on the one object
  that's guaranteed not to be mutated by a PDF switch — the worker itself
  — rather than a second copy on `ExportWorkspace`. Risks 1, 2, and 4
  below were fixed in the same commit as this one, after their own
  separate review. Regression test:
  `tests/test_export_workspace.py` (new — the suite's first widget-level
  test, see §3 below).

  **Implemented, for risks 1, 2, and 4:** a `self._pdf_generation`
  counter on `ExportWorkspace`, bumped on every `set_pdf()` call; each
  `_ExportWorker` is stamped with the generation at dispatch time.
  `_on_export_succeeded()`/`_on_export_failed()` compare
  `self.sender().pdf_generation` against the current generation and no-op
  on a mismatch, so a stale worker's payload can never touch
  `_export_complete`, the completion banner, or the result message (fixes
  risk 4); `set_pdf()` also resets `_export_complete` and a new
  `_completed_plan` snapshot directly, closing the window before the stale
  signal even arrives. `on_shown()` skips its rebuild entirely when a
  same-generation worker is still active (the `self._worker is not None
  and self._worker.pdf_generation == self._pdf_generation` check
  described under risks 1-2 above), leaving the in-progress UI untouched.
  Separately, `_completed_plan` is compared against the freshly rebuilt
  plan in `_show_ready()` so a legitimate completion banner survives an
  unrelated revisit (e.g. a trip to Review Cards and back) but clears
  itself if Review Cards changes what would actually be exported.
  Regression tests: `TestExportReentry` in `tests/test_export_workspace.py`
  (new) — drives a real worker/PDF/event-loop rather than a
  synthetic slot call, since this is fundamentally a signal-timing
  question. Reviewed as its own change before being committed
  alongside risk 3's already-verified fix. See
  `docs/RELEASE_READINESS.md`'s Accomplished section.

**Out of scope for this milestone:** making `_close_renderer()`
non-blocking, or supporting true export cancellation. Both are real
future improvements but are not needed to close the correctness/crash
risks above, and adding them now would broaden scope beyond what was
asked.

**Test plan:** see §3 (Regression testing) — this is the primary thing
that section's new tests are for.

---

## 2. Safe shutdown during export

**Traced:** `deckforge_gui/main_window.py` has no `closeEvent` override.
`gui_app.py` has no `QApplication.aboutToQuit` handler. Grepped the whole
repo for `closeEvent`/`aboutToQuit` — no hits anywhere.

**Risk:** If the window is closed (title-bar X, Alt+F4, taskbar close)
while `_ExportWorker` is running, Qt tears down the widget tree — which
owns the `QThread` as a child `QObject` — while `run()` is still executing
on a live OS thread. Destroying a running `QThread` is undefined behavior
in Qt; PySide6 typically prints `QThread: Destroyed while thread is still
running` and this is a well-known source of hard crashes/aborts, not a
recoverable warning. Even short of a hard crash, `export_cells()` writes
`front_NNN.png` files sequentially with no atomicity — an interrupted run
leaves a partial, unlabeled file set in the destination folder with
nothing telling the user the export didn't finish.

**First attempt, tried and rejected:** the first implementation made
`MainWindow.closeEvent()` call a new `ExportWorkspace.wait_for_export()`
that blocked the GUI thread on the live `QThread.wait()` until `run()`
returned, then accepted the close. Manual acceptance testing against a
real, large export then hit a real crash this design didn't predict.
Runtime diagnostics (thread IDs, signal-delivery order, and polling the
real Win32 `IsHungAppWindow()` API — the same check Task Manager/DWM use)
showed the actual mechanism: an unbounded, non-pumping `QThread.wait()`
call on the GUI thread leaves the real window in a genuine Windows-hung
state (`IsHungAppWindow()` → `True`) for the entire remaining export once
it runs past Windows' ~5 second hang-detection threshold — trivially true
for any real large export. A hung foreground window can be force-
terminated by the user or the OS, which is indistinguishable from a crash
and was the actual failure the manual test hit. None of the originally
listed hypotheses (queued-slot ordering, widget teardown races, double
renderer close, modal-dialog reentrancy) reproduced under a real
`QApplication.exec()` loop — the defect was the blocking wait itself, not
a race.

**Implemented (deferred, asynchronous close):** `ExportWorkspace` gained a
narrowly scoped `export_finished = Signal(bool)`, emitted from
`_on_export_worker_finished()` — i.e. strictly after whichever of
`_on_export_succeeded()`/`_on_export_failed()` applies has already run,
and only for the worker matching the current `_pdf_generation` (a stale
worker's completion never emits it, reusing `_is_stale_worker_signal()`).
`wait_for_export()` and its blocking `.wait()` are unchanged, but are no
longer called from `MainWindow.closeEvent()` at all — they still back
`_close_renderer()`'s PDF-switch-mid-export case, a much shorter,
pre-existing join outside this feature's scope.

`MainWindow.closeEvent(event)` is a no-op (default accept, unchanged) when
`export_workspace.is_exporting()` is `False` — which also covers the
automatic second close described below, since by then the worker is
already cleared. Otherwise it shows a `QMessageBox` — **Keep DeckForge
Open** (default and Escape button) vs. **Finish Export, Then Close** — via
`_confirm_quit_during_export()` (still its own method, same reason
`export_workspace._confirm_overwrite_if_needed()` is). "Keep DeckForge
Open" calls `event.ignore()` and does nothing else. "Finish Export, Then
Close" sets a `MainWindow._close_after_export` flag and calls
`event.ignore()` — never a blocking join — so the close is deferred, not
denied, and the GUI event loop keeps running normally for the rest of the
export. A repeat close attempt while that flag is already set is silently
ignored (no second dialog, no second pending request). Once
`export_finished` fires: `_on_export_finished_while_closing()` clears the
flag and, only on success, schedules `QTimer.singleShot(0, self.close)` —
a fresh close on the next event-loop turn, handled by the ordinary
"nothing exporting" branch above, so it needs no special-casing and no
second dialog. On failure, the flag is cleared and nothing else happens:
the window stays open and `_on_export_failed()`'s existing failure
message is what the user sees, rather than the failure being concealed by
quitting anyway. No cancellation support exists once "Finish Export, Then
Close" has been chosen — confirmed as an intentional alpha scope decision,
not an oversight.

**Second race, caught in review before this shipped:**
`_confirm_quit_during_export()`'s `QMessageBox.exec()` runs a real nested
event loop, so the export can finish — and `export_finished` can already
have fired, back while `_close_after_export` was still `False` — before
the user answers the dialog. Naively arming the deferred-close flag on
that stale assumption would wait forever on a signal that already came
and went. `closeEvent()` instead re-checks `is_exporting()` immediately
after `_confirm_quit_during_export()` returns `True`: if the export is
already done, it closes immediately via the ordinary no-export path
instead of deferring.

**Scope of the guarantee — read narrowly:** this covers *normal in-app
shutdown* (title-bar X, Alt+F4, taskbar close), all of which route through
`QMainWindow.closeEvent()`. It says nothing about, and does not claim
anything about, a forced process kill (Task Manager/`taskkill`), an OS
shutdown/logoff that terminates the process outside Qt's close machinery,
or a write failure mid-export (`export_cells()`'s existing
`except (OSError, PDFRenderError)` handling is unchanged) — none of those
are new risks introduced or claimed to be closed by this change, and true
export cancellation remains explicitly out of scope, unchanged from the
original plan.

**Regression tests:** `tests/test_main_window.py` drives a real
`QApplication.exec()` loop with a deliberately delayed `export_cells()`
pipeline (not a synthetic direct `closeEvent()` call, which cannot detect
an unresponsive GUI thread at all) —
`TestCloseEventNoActiveExport` (no export running: dialog never shown,
close proceeds normally), `TestKeepDeckForgeOpen` (Keep DeckForge Open
leaves the worker running and ignores the close; a worker left referenced
but no longer running, the exact race `is_exporting()` is defined
against, does not trigger the confirmation),
`TestDeferredCloseResponsiveness` (a periodic `QTimer` keeps ticking
throughout a real, multi-second delayed export — proving the GUI thread
was never blocked — and the window only actually closes, with the
`export_cells()` output file verified on disk, once that export finishes;
plus repeated close attempts while deferred do not stack dialogs or
closes), `TestExportFinishesWhileConfirmationDialogIsStillOpen` (the
second race above: an export that completes while the confirmation
dialog's own nested loop is still pumping events, before the user
answers it, closes immediately rather than arming a deferred close that
would never be released), `TestFailedExportDoesNotConcealFailureByQuitting`
(a failed export leaves the window open, clears the pending-close flag,
and shows the normal failure message), and `TestNoBlockingWaitDuringClose`
(asserts `QThread.wait()` is never called on the worker from
`closeEvent()` or the deferred path). Same real
`PDFRenderer`/`QThread`/`export_cells()` pattern as `TestExportReentry` in
`tests/test_export_workspace.py`, no `pytest-qt`.

---

## 3. Regression testing

**Traced:** `pytest -q` → 405 tests, all pass, 1.17s total. Every existing
test (including `tests/test_export_state.py` and
`tests/test_find_cards_workspace.py`) exercises pure functions/dataclasses
only — nothing instantiates a real `QWidget`/`QApplication`, drives a
`QThread`, or triggers a Qt signal. No `pytest-qt` (or equivalent) is
installed (`requirements-dev.txt` is just `-r requirements.txt` +
`pytest`).

**Partially addressed:** `tests/test_export_workspace.py` (new) is the
suite's first widget-level test — 478 tests total now (469 pre-existing +
9 new: 4 in `TestExportCompletionMessageUsesSignalPayload` + 5 in
`TestExportReentry`, both committed alongside the risk 1/2/3/4 fixes they
cover; see below).
`TestExportCompletionMessageUsesSignalPayload` covers the first bullet
below (§1 risk 3's fix) without `pytest-qt`: it instantiates
`ExportWorkspace` under `QT_QPA_PLATFORM=offscreen` and calls
`_on_export_succeeded()` directly with a synthetic signal payload, which
needed no `qtbot`/signal-waiting machinery since that fix is a pure
data-flow question (does the slot use its own argument or stale instance
state), not a timing one.

`TestExportReentry` (new) additionally covers the
second bullet below (`on_shown()` during an active export, plus the risk
4 cross-deck completion corruption) — and had to drive a *real*
`PDFRenderer`/`QThread`/`export_cells()` pipeline against
`sample_decks/Solo-cards-digital.pdf` to do it, manually draining the Qt
event loop (`QApplication.processEvents()` in a loop) rather than using
`pytest-qt`'s `qtbot.waitSignal()`. This is exactly the risk-1/2/4 root
cause made concrete: the bug is specifically about *when* a queued
cross-thread signal gets delivered relative to `set_pdf()`/`on_shown()`,
so a synthetic direct slot call (the pattern the first bullet's tests
use) cannot reproduce it — there has to be a real background thread and
a real event loop to race against. The worker failure and `closeEvent`
bullets below are still uncovered; now that a real (if `pytest-qt`-free)
worker/event-loop pattern exists in this file, a future pass can decide
whether to extend it or bring in `pytest-qt` for those instead.

**Risk:** every bug identified in §1 and §2 is a *widget/thread lifecycle*
bug — exactly the class of defect pure-function unit tests cannot catch
by construction. The current suite gives no signal on any of them, and
would give no signal if a future change reintroduced them.

**Smallest coherent implementation:**

- Add `pytest-qt` to `requirements-dev.txt` (dev-only, well-maintained,
  the standard tool for this exact job with PySide6 already a hard
  dependency — low incremental packaging cost, consistent with
  ENGINEERING_STANDARDS.md's dependency conservatism).
- Add `tests/test_export_workspace.py` covering only the behaviors this
  milestone touches (not a general GUI-coverage sweep):
  - Worker success → completion UI shown, message names the destination
    captured at dispatch time even if `self._destination` is mutated
    afterward (direct regression test for §1 risk 3). **Done** —
    `TestExportCompletionMessageUsesSignalPayload` in
    `tests/test_export_workspace.py`.
  - Worker failure → error message shown, controls re-enabled, no
    completion state.
  - `on_shown()`/`_rebuild()` while a worker is active does not touch the
    renderer and does not re-enable the Export button or hide the
    progress UI (regression test for §1 risks 1–2). **Done**
    — `TestExportReentry.test_revisiting_during_an_active_export_shows_progress_not_ready`
    in `tests/test_export_workspace.py`, using a real worker rather than a
    `threading.Event`-blocked fake, since the fix itself needed a real
    cross-thread signal to guard against. Also added, beyond this
    bullet's original scope: coverage for risk 4 (cross-deck stale
    completion) and for a completion banner correctly surviving vs.
    clearing across a revisit — see risk 4's fix note above.
  - `MainWindow.closeEvent` during an active export shows the
    confirmation path and never lets a running worker be destroyed
    (assert `wait()`/`is_exporting()` behavior rather than trying to
    catch the native Qt abort, which isn't practically observable from
    Python).
- Keep this list exact — it validates §1/§2's fixes, not a general
  "cover every workspace" initiative, per the instruction not to broaden
  scope.

---

## 4. README accuracy

**Traced:** `README.md` is entirely CLI-shaped (`extract.py`, "Where to
start" walks `--calibrate` → `--preview` → `--export` → `--contact-sheet`).
Its only two mentions of the GUI are line 237 (unrelated) and line 593,
under **Future work**:

> GUI (PySide6 desktop application), interactive calibration mode,
> drag-and-drop PDFs

All three of those are done. Commit history shows a complete PySide6
workflow (`gui_app.py` → Deck → Find Cards → Calibrate Fronts →
Calibrate Back → Review Cards → Export), interactive calibration already
has a CLI equivalent documented elsewhere in this same README
(`--calibrate`), and `deck_workspace.py` implements `setAcceptDrops` +
`dragEnterEvent`/`dropEvent` (drag-and-drop is live). The README's
"Future work" list is actively wrong about the state of the product, and
the GUI — the thing about to be alpha tested — is undiscoverable from the
project's front door.

**Risk:** for an alpha test, the README is the entry point. Anyone
(including future-you) following it as written lands on the CLI and never
finds `gui_app.py`.

**Smallest coherent implementation (docs-only):**

- Add a GUI "where to start" path (`pip install -r requirements-gui.txt`
  && `python gui_app.py`, one line pointing at the in-app guided
  workflow) — doesn't need to duplicate `docs/ui/*`, just needs to exist.
- Delete the stale "GUI / interactive calibration / drag-and-drop" bullet
  from **Future work** entirely (all three are shipped).
- Add one line in "Project Documentation" pointing at `docs/ui/*` for GUI
  detail, so the README stays the index rather than growing a second
  workflow write-up.

This is a mechanical, low-risk doc patch — flagged here for your review
rather than applied, per this review's scope.

---

## 5. Release versioning

**Traced:** `src/deckforge/__init__.py` has `__version__ = "0.1.0"` — the
CLI engine package only. `pyproject.toml` has no `[project]` table (no
`name`/`version` at all — the repo isn't currently pip-installable as a
package; `gui_app.py` reaches the engine via `sys.path.insert`, not an
install). Nothing in `deckforge_gui` carries a version. The GUI shows no
version anywhere — not the window title, not the top bar, no about box.
No `CHANGELOG`, no git tags (`git tag -l` is empty).

**Risk:** once alpha testing produces bug reports (from you, and later
others), there is no way to say which build a report came from. This gets
worse, not better, once crash logging (§6) exists — a crash log with no
version stamp is much less actionable.

**Smallest coherent implementation:**

- One new small module, e.g. `src/deckforge_gui/_version.py`:
  `VERSION = "0.1.0-alpha.1"`. Plain constant — no `importlib.metadata`
  plumbing, since the project isn't currently packaged/installed and
  adding a `[build-system]`/`[project]` table to make that work is a
  separate, bigger change than this milestone needs.
  `src/deckforge/__init__.py`'s existing `__version__` stays as the CLI
  engine's own version (already true today, not currently coupled to the
  GUI, and no evidence they need to move in lockstep for alpha).
- Surface it: append to `MainWindow`'s window title
  ("DeckForge — v0.1.0-alpha.1") — cheapest possible visibility, useful
  for screenshots/bug reports, and it's what crash log headers (§6) will
  also stamp.
- One line in `DEVELOPER.md` documenting the bump convention (bump the
  pre-release number each time a build goes out for alpha testing).

No packaging/build-system work, no `pip install` distribution changes —
that's a separate, larger initiative than "have a version string that
shows up in bug reports."

---

## 6. Crash logging

**Traced:** grepped `src/` for `logging`/`excepthook`/`traceback` — the
only hits are `deckforge/cli.py`'s existing `try/except Exception` blocks
that produce the README's documented friendly-error-plus-`Details:`
output (CLI-only, print-to-stdout, not a log file). `gui_app.py` has no
`sys.excepthook`, no `logging` configuration, no log directory. An
exception inside a Qt slot on the GUI thread is printed to stderr by
PySide6's default handling and the event loop continues; an exception
inside `_ExportWorker.run()` outside its narrow
`except (OSError, PDFRenderError)` is not caught at all inside the
thread — Python thread exceptions do not reliably reach `sys.excepthook`
across Qt/PySide versions, so today that case is effectively silent
(worker thread dies, `finished` still fires per Qt's lifecycle, but
neither `succeeded` nor `failed` is emitted, so the user sees the
progress bar vanish with no message).

**Risk:** during alpha testing, any uncaught exception is currently
invisible unless you're watching a terminal at the exact moment. This is
the single biggest lever for turning testing hours into fixable bugs, and
it's currently zero.

**Smallest coherent implementation** (local-only — no telemetry, no
network calls, per ENGINEERING_STANDARDS.md's Privacy section: "Users
should be able to trust that their PDFs remain on their own computer,"
which extends to not phoning home crash data either):

- Configure Python's stdlib `logging` once, at the very top of
  `gui_app.main()`, before `MainWindow()` is constructed: a
  `RotatingFileHandler` writing to a per-user local log directory (e.g.
  `Path(os.environ["LOCALAPPDATA"]) / "DeckForge" / "logs"` on Windows,
  the only platform this app currently targets — no new dependency for a
  single OS-appropriate path lookup). First line of every session logs
  the version string from §5.
- Install a `sys.excepthook` that logs any uncaught exception (full
  traceback) before falling through to the previous hook, so nothing
  currently visible in a dev console regresses.
- Widen `_ExportWorker.run()`'s try/except from
  `(OSError, PDFRenderError)` to a blanket `Exception`, logging the
  traceback via the new logger and still emitting `failed` with a
  friendly message either way. This is the one thread-boundary case a
  global `excepthook` cannot be relied on to catch, so it needs its own
  explicit handling regardless of the hook above.

**Explicitly deferred:** no in-app log viewer or "Open log folder"
button this milestone — the log existing and being inspectable by you on
disk is enough for alpha; a UI affordance for it is a reasonable later
addition once you know what testers actually need from it.

---

## Summary of what's proposed

Status per area, not "nothing implemented yet" anymore — see each area's
own section for exactly what landed vs. what's still only proposed.

| Area | Core fix | New files | Touches | Status |
|---|---|---|---|---|
| Export thread sync | guard `_rebuild()`/`on_shown()` during an active worker; carry destination + a `pdf_generation` stamp on the worker | — | `export_workspace.py` | Risks 1, 2, 3, 4 implemented |
| Safe shutdown | `closeEvent` confirmation + guaranteed `wait()` before teardown | `tests/test_main_window.py` | `main_window.py`, `export_workspace.py` | Implemented |
| Regression testing | `pytest-qt` + targeted widget/thread tests for the two fixes above | `tests/test_export_workspace.py`, `tests/test_main_window.py` | `requirements-dev.txt` | Risk 3 test done; risk 1/2/4 tests done; `closeEvent` tests done (no `pytest-qt` needed); worker-failure test not started |
| README accuracy | add GUI entry point, remove stale Future-work bullet | — | `README.md` | Implemented — see `docs/RELEASE_READINESS.md` |
| Release versioning | one version constant, shown in window title | `deckforge_gui/_version.py` | `main_window.py`, `DEVELOPER.md` | Not started |
| Crash logging | rotating local log file + excepthook + widened worker try/except | — | `gui_app.py`, `export_workspace.py` | Not started |

All six are additive/local edits to existing files (no architectural
change), consistent with ENGINEERING_STANDARDS.md's "smallest change that
solves the problem." Recommended sequencing: §1 and §2 first (they're the
actual correctness/crash risks and share code), §3 alongside them (proves
the fixes), §6 next (turns remaining alpha-testing crashes into
actionable reports), §5 and §4 last (lowest risk, most mechanical).

---

## Addendum: PDF drag-and-drop event handling (implemented, 2026-07-12)

Out of this plan's six-area scope (per the intro: manual-testing findings
are tracked in `docs/RELEASE_READINESS.md`, not folded in here) — recorded
as a short addendum, not a numbered section, so the table above still
maps 1:1 to the original six areas and "nothing implemented yet" still
describes that six-item plan accurately.

**What was fixed, in `deckforge_gui/deck_workspace.py`'s `_DropZone`:**

1. **`dragMoveEvent` now explicitly accepts the event.** Qt does not carry
   acceptance forward from `dragEnterEvent` — each `QDragMoveEvent`
   defaults to unaccepted and needs its own `acceptProposedAction()`, or
   Qt shows a "not allowed" cursor and `dropEvent` never fires. Verified
   directly against PySide6 (constructing a bare `QDragMoveEvent` and
   checking `isAccepted()` defaults to `False` even after a prior
   `dragEnterEvent` was accepted). This is general Qt behavior on every
   platform, not Windows- or OLE-specific.
2. **Child widgets now forward drag events to the drop zone.** The
   zone's icon/text/button children are stacked via `QVBoxLayout` and
   visually cover nearly the entire dashed frame. Unlike mouse events,
   Qt does not propagate ignored drag/drop events up the widget
   hierarchy — a child that doesn't handle them simply swallows them.
   `catch_drops_from()` installs an event filter on each child so
   `DragEnter`/`DragMove`/`DragLeave`/`Drop` are forwarded to the parent
   `_DropZone`, which is the documented Qt workaround for this. Without
   it, dropping on any of those children (most of the visible target)
   would silently do nothing.

Both are genuine, independently-reproducible Qt requirements, confirmed
against Qt Forum discussion of the same pattern, not workarounds for the
elevation issue below — they'd be necessary on any platform, elevated or
not.

**Separate finding — not an application defect:** during manual alpha
testing, drag-and-drop appeared completely broken when DeckForge was
launched from an elevated (Administrator) PowerShell. Root cause: Windows
blocks OLE drag-and-drop between processes at different integrity
levels — Explorer runs at the normal user's integrity level and cannot
supply drag data to a higher-integrity-level (elevated) target process.
This is Windows UIPI (User Interface Privilege Isolation) behavior, not a
DeckForge bug, and no code change addresses or should attempt to address
it. Running DeckForge from a normal, non-elevated PowerShell resolves it.
Manually verified 2026-07-12: dragging a real PDF from Explorer into a
non-elevated DeckForge works correctly with the event-handling fixes
above in place. Recorded here so a future elevated-process test session
isn't re-diagnosed as an application defect.
