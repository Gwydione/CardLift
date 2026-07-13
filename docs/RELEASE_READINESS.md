# Release Readiness Board

Living document tracking what's open, what's done, and what's top
priority before DeckForge's alpha ships. Updated as design review
findings and manual alpha-testing bugs come in — this is the single
place to check "are we ready yet."

Last updated: 2026-07-13.

---

## Top priorities before alpha release

Ranked by risk, not by discovery order.

| # | Item | Why it's top-priority | Status |
|---|---|---|---|
| 1 | **Calibration geometry robustness** (different calibration-click choices produce systematically different, sometimes-clipping grids) | Correctness of the core "click two corners, get a grid" promise — the product's central value proposition. Flagged by alpha testing as the current highest-priority issue. | Implemented — see `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` |
| 2 | Export thread synchronization (renderer race, stale in-progress UI, destination-message race, stale cross-deck completion) | Real crash/corruption risk during the app's core "write files to disk" action | Implemented — see `docs/ALPHA_HARDENING_PLAN.md` §1 |
| 3 | Safe shutdown during export | Closing the app mid-export can destroy a running `QThread` — known Qt crash pattern, plus silent partial file writes | Planned — §2 |
| 4 | Crash logging | Zero diagnostic trail today; every other bug found during alpha testing is harder to fix without this | Planned — §6 |
| 5 | Regression testing for the above | Confirms 2 & 3 are actually fixed and stay fixed | Planned — §3 |
| 6 | Release versioning | Bug reports currently can't be tied to a build | Implemented — see `docs/ALPHA_HARDENING_PLAN.md` §5 |
| 7 | README accuracy | Alpha testers' entry point currently hides the GUI entirely | Implemented — see below |

Full design review, risk tracing, and implementation plan for items 2-7:
`docs/ALPHA_HARDENING_PLAN.md`. Full calibration math trace, root-cause
analysis, and recommended fix for item 1: `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`.

---

## Open

_Calibration geometry follow-up (not yet implemented):_

- [ ] The CLI's own `--calibrate` window (`src/deckforge/calibrate_ui.py`)
      has the same structural issues as items now fixed in the GUI (see
      `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s "Recommended smallest
      coherent change" and its grid-inference-conflict addendum,
      including its own separate `infer_second_cell()` with the identical
      `round(dx/cell_width)` wrong-cell-count exposure) — it's a separate
      Tkinter port, not shared code, so none of these fixes were applied
      to it. Its cell-label prompt (`_prompt_cell_label()`) also still
      asks for the internal 0-based `rNcN` form the GUI's dialog moved
      away from (see DEVELOPER.md's "Cell-label prompt uses human, not
      internal, numbering"). Not currently prioritized: the CLI engine is
      documented as stable and this alpha's testing surface is the GUI.

_Design review findings (not yet implemented):_

- [ ] No `closeEvent` handling: quitting the app while an export is
      running can destroy a live `QThread` (crash risk) and leaves
      partial files on disk with no warning. — plan §2
- [ ] No widget/thread-level regression tests exist for `closeEvent`
      above — `tests/test_export_workspace.py` (new, see Accomplished) is
      the suite's first widget-level test; it covers the completion
      message fix and the export thread-sync fixes (see Accomplished),
      but not `closeEvent`. — plan §3
- [ ] No crash/error logging anywhere in the GUI — an uncaught exception
      (especially inside the export worker thread) is currently
      invisible outside a live terminal. — plan §6

_Bugs found during manual alpha testing:_

- [x] Drag-and-drop appeared completely broken when DeckForge was
      launched from an elevated (Administrator) PowerShell. Traced to
      Windows UIPI blocking OLE drag-and-drop from Explorer (normal
      integrity level) into an elevated target process — not a DeckForge
      defect. Resolved by running DeckForge from a normal, non-elevated
      PowerShell; manually verified with a real PDF from Explorer. See
      `docs/ALPHA_HARDENING_PLAN.md`'s addendum.
- [x] Calibrating a real 3×3 deck ("DP Pocket 20 pages for centered
      bothsided print.pdf") by clicking the upper-left and lower-right
      cards produced 12 suggested cells (3×4) instead of 9 (3×3). Traced
      to `infer_second_cell()` silently mislabeling the second card as
      `(2,3)` instead of `(2,2)` — the deck's real column gutter (~27% of
      card_width) tips `round(dx/card_width)` past its rounding boundary.
      A distinct failure mode from item 1's Effects A/B (a wrong *cell*,
      not a wrong *gap*) — see `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s
      addendum. Fixed by cross-checking the click against the
      already-computed, independent second-card hint and asking for
      clarification (existing `NEEDS_CELL_LABEL` prompt) on disagreement,
      rather than a new tuned threshold.

---

## Accomplished

- Full Phase II GUI workflow complete: Deck → Find Cards → Calibrate
  Fronts → Calibrate Back → Review Cards → Export, PySide6 desktop app
  (`gui_app.py`), drag-and-drop PDF loading, interactive calibration
  with zoom/pan/crosshair.
- Select Card Pages workflow and Shared Back state model.
- Reviewed-card export workflow (human-approved cell list → PNG files),
  with `deckforge.cell_export.export_cells()` as the engine primitive
  and `export_state.py` as the pure planning/gating layer.
- Branding document (icon/identity) drafted.
- Drag-and-drop event handling hardened (`deck_workspace.py`'s
  `_DropZone`): `dragMoveEvent` now explicitly accepts each move event
  (Qt doesn't carry acceptance forward from `dragEnterEvent`), and the
  drop zone's icon/text/button children now forward drag events to the
  zone via an event filter (Qt doesn't propagate ignored drag events up
  the widget hierarchy the way it does mouse events). Both are genuine
  Qt requirements, independent of the elevation finding above — see
  `docs/ALPHA_HARDENING_PLAN.md`'s addendum.
- CLI engine (`extract.py` + `src/deckforge/`) stable: manual
  calibration, multi-layout profiles, `--measure`/`--calibrate`/
  `--overlay`/`--inspect`, friendly CLI error handling.
- **Calibration geometry robustness (GUI)** — see
  `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s "Recommended smallest
  coherent change": an unmeasured axis's silent 0.0-gap fallback is now
  surfaced in the completion banner/guidance/status text
  (`ungauged_axis_warning()`), gated so a genuine one-row/one-column/
  single-card deck never sees a spurious warning; the second-card hint
  now suggests a farther, not adjacent, cell (`suggested_second_card_offset()`)
  to reduce click-noise amplification; and Calibrate's corner-click
  guidance now names a consistent cutting-guide-or-edge reference point.
- **Alpha Polish: Shared Back experience.** "Set as Shared Back" no
  longer reads as disabled (visible border + normal text color on its
  idle state); a blocked Continue click now shows an inline message
  next to Continue instead of failing silently; the "Confirm there's no
  Shared Back" action is now a visible chip instead of small link text.
  State model unchanged -- see DEVELOPER.md's "Alpha Polish: Shared Back
  discoverability."
- **Alpha Polish: export overwrite confirmation.** Export now checks the
  chosen destination folder for filename collisions before writing, and
  blocks with a confirmation dialog (Cancel is the default/safe choice)
  instead of silently overwriting existing files. See DEVELOPER.md's
  "Alpha Polish: export overwrite confirmation."
- **Grid-inference conflict detection (Doom Pilgrim).** A second-card
  click that disagrees with the already-computed, independent
  second-card hint now asks for clarification instead of silently
  completing with a wrong cell — see
  `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s addendum. This is
  conflict *detection*, not a guarantee against every theoretically
  ambiguous grid: agreement between the click and the hint is treated as
  sufficient confidence to proceed automatically, not as proof of
  correctness.
- **Release versioning (GUI version identity).** `deckforge.__version__`
  (now `0.1.0-alpha`) is the single authoritative version constant; the
  GUI had no version display anywhere. `MainWindow`'s window title and a
  new muted `TopBar` label both import and display it directly, so bug
  reports/screenshots can be tied to a build. See `docs/ALPHA_HARDENING_PLAN.md`
  §5 and DEVELOPER.md's "Git Workflow" for the bump convention.
- **Cell-label prompt now uses human numbering.** The clarification
  dialog above asked for the ambiguous card's cell in internal 0-based
  `r2c2` form, confusing during manual validation. Now asks for a plain
  1-based `"row,col"` pair (e.g. `2,1`) and states the first card's
  row/column for reference; internal storage stays 0-based -- see
  DEVELOPER.md's "Cell-label prompt uses human, not internal, numbering."
- **README rewritten as a GUI-first product landing page.** README.md
  previously documented only the CLI, with the PySide6 GUI, drag-and-drop
  PDFs, and interactive calibration all misfiled under "Future work" even
  though all three had already shipped. Rewritten around the actual
  six-step GUI workflow (Deck → Select Card Pages → Fronts → Shared Back
  → Review Cards → Export) with a new "Current Status" section (Windows
  alpha, under active development) and a placeholder Screenshots section.
  The CLI's full profile-JSON/grid-math/command reference (~470 lines)
  moved out to the new `docs/CLI_REFERENCE.md` rather than being
  incrementally edited in place, keeping README readable as a landing
  page; `DEVELOPER.md`'s project-structure tree and architecture
  rationale were dropped from README rather than duplicated. See plan §4.
- **Fixed "Exported N files to None."** Switching PDFs mid-export
  (`ExportWorkspace.set_pdf()`) reset `self._destination` to `None`
  before the still-running background worker's completion handler
  (`_on_export_succeeded`) read it to build the message — files landed
  correctly, only the message was wrong. Fixed worker-centrically:
  `_ExportWorker.succeeded` now carries the destination it actually wrote
  to as part of its signal payload (`Signal(list, Path)`), so the slot
  never re-reads mutable workspace state after the background operation
  finishes. `tests/test_export_workspace.py` (new) covers this directly —
  the suite's first widget-level test. See plan §1.
- **Hardened export state across navigation (plan §1 risks 1, 2, 4).**
  Found while manually verifying the destination-message fix above, then
  reviewed as its own change before landing in the same commit. A
  `self._pdf_generation` counter on `ExportWorkspace`, bumped on every
  `set_pdf()` call and stamped onto each `_ExportWorker` at dispatch
  time, gives every place that handles a worker's signal (or decides
  whether to rebuild) a way to tell "this describes the deck currently on
  screen" from "this is a stale signal/UI state left over from an
  abandoned PDF":
  - `on_shown()` now leaves an active same-generation worker's
    in-progress UI untouched instead of rebuilding over it — closes both
    the cross-thread `PDFRenderer` access during an active export (risk
    1) and the stale "Exporting…"/progress-bar state after a revisit
    (risk 2).
  - `_on_export_succeeded()`/`_on_export_failed()` no-op on a
    generation mismatch, so a worker whose PDF was abandoned via
    `set_pdf()` can never mark a *different*, later deck's Export as
    complete or show its file count/destination (risk 4).
  - A legitimate completion (`_completed_plan`/`_completed_result_message`)
    is restored verbatim on a plain revisit, but clears itself if what
    Review Cards would actually export has changed since — so the
    completion banner never survives a config change, and never leaks
    from one deck to another via `set_pdf()`.
  `TestExportReentry` in `tests/test_export_workspace.py` drives a real
  `PDFRenderer`/`QThread`/`export_cells()` pipeline (not a synthetic slot
  call) to cover all four scenarios. See plan §1.
- 478 passing unit tests across engine + GUI state/logic layers (469
  pre-existing + 9 new in `tests/test_export_workspace.py`, the suite's
  first widget-level tests — see the two bullets above).

---

## Explicitly out of scope for this hardening milestone

Carried over from `docs/ALPHA_HARDENING_PLAN.md` so scope doesn't creep:

- True export cancellation (no interrupt hook in `cell_export.py` today).
- Making PDF-switch-during-export non-blocking.
- In-app crash-log viewer / "open log folder" affordance.
- Packaging/distribution (`pip install`-able build, `[project]` table).
- Anything not in the six focus areas above — new bugs found during
  manual testing go in **Open** as their own items, not folded into the
  hardening plan's scope.

---

## How to update this board

- New manual-testing bug → add a line under **Open → Bugs found during
  manual alpha testing**, one bullet, plain description.
- Hardening item implemented → move its bullet from **Open** to
  **Accomplished** and check the box in the priorities table.
- Re-scope only with an explicit decision — don't silently expand what
  "alpha hardening" covers.
