# Alpha Hardening — Design Review

Status: **review draft, nothing in this document has been implemented.**
Scope is deliberately limited to six areas: export thread synchronization,
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
2. **Stale in-progress UI.** `_rebuild()` → `_show_ready()` unconditionally
   sets `self._export_btn.setEnabled(self._destination is not None)` and
   never checks `self._worker is not None`. Navigating away and back
   during an export hides the "Exporting…"/progress bar and makes the
   Export button look clickable again. `_on_export_clicked()`'s own
   `self._worker is not None` guard prevents an actual second dispatch,
   but the visible state lies to the user.
3. **Destination race on PDF switch.** `_close_renderer()` (called from
   `set_pdf()`) blocks the GUI thread on `self._worker.wait()` before
   tearing down the old renderer — correct in spirit, but `set_pdf()` also
   resets `self._destination = None` and `self._plan = None` as part of
   the same call, *before* the queued `succeeded`/`failed` signal from the
   just-finished worker is delivered. `_on_export_succeeded()` then reads
   `self._destination`, which is already `None` — the user sees "Exported
   54 files to None." instead of the real folder, even though the files
   were written correctly.

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

**Smallest coherent implementation:**

- Add two small methods to `ExportWorkspace`: `is_exporting() -> bool`
  (`self._worker is not None`) and reuse the existing wait-for-worker
  logic already in `_close_renderer()` (extract it to a
  `wait_for_export()` method so both call sites share it).
- Override `MainWindow.closeEvent(event)`: if
  `self.export_workspace.is_exporting()`, show a blocking `QMessageBox`
  ("An export is still in progress. Quit now? Files being written may be
  incomplete." — Wait / Quit Anyway). "Wait" calls `event.ignore()` and
  does nothing else (user stays in the app, worker keeps running,
  re-close is always available). "Quit Anyway" calls
  `export_workspace.wait_for_export()` (same blocking `.wait()` pattern
  already used for the PDF-switch case) and then `event.accept()`.
- This guarantees the `QThread` is always fully finished before its
  owning widgets are destroyed — the crash is eliminated — and the user
  is told honestly when files might be incomplete, instead of silent
  corruption. No cancellation support is added; not needed to close the
  crash risk, and `export_cells()` has no interrupt hook to cancel into
  without an engine-layer change, which is out of scope here.

**Test plan:** see §3.

---

## 3. Regression testing

**Traced:** `pytest -q` → 405 tests, all pass, 1.17s total. Every existing
test (including `tests/test_export_state.py` and
`tests/test_find_cards_workspace.py`) exercises pure functions/dataclasses
only — nothing instantiates a real `QWidget`/`QApplication`, drives a
`QThread`, or triggers a Qt signal. No `pytest-qt` (or equivalent) is
installed (`requirements-dev.txt` is just `-r requirements.txt` +
`pytest`).

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
    afterward (direct regression test for §1 risk 3).
  - Worker failure → error message shown, controls re-enabled, no
    completion state.
  - `on_shown()`/`_rebuild()` while a worker is active does not touch the
    renderer and does not re-enable the Export button or hide the
    progress UI (regression test for §1 risks 1–2). A fake/stubbed
    `export_cells` that blocks on a `threading.Event` gives the test a
    deterministic window in which to assert this.
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

## Summary of what's proposed (nothing implemented yet)

| Area | Core fix | New files | Touches |
|---|---|---|---|
| Export thread sync | guard `_rebuild()` during an active worker; snapshot destination at dispatch | — | `export_workspace.py` |
| Safe shutdown | `closeEvent` confirmation + guaranteed `wait()` before teardown | — | `main_window.py`, `export_workspace.py` |
| Regression testing | `pytest-qt` + targeted widget/thread tests for the two fixes above | `tests/test_export_workspace.py` | `requirements-dev.txt` |
| README accuracy | add GUI entry point, remove stale Future-work bullet | — | `README.md` |
| Release versioning | one version constant, shown in window title | `deckforge_gui/_version.py` | `main_window.py`, `DEVELOPER.md` |
| Crash logging | rotating local log file + excepthook + widened worker try/except | — | `gui_app.py`, `export_workspace.py` |

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
