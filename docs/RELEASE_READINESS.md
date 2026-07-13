# Release Readiness Board

Living document tracking what's open, what's done, and what's top
priority before DeckForge's alpha ships. Updated as design review
findings and manual alpha-testing bugs come in — this is the single
place to check "are we ready yet."

Last updated: 2026-07-12.

---

## Top priorities before alpha release

Ranked by risk, not by discovery order.

| # | Item | Why it's top-priority | Status |
|---|---|---|---|
| 1 | **Calibration geometry robustness** (different calibration-click choices produce systematically different, sometimes-clipping grids) | Correctness of the core "click two corners, get a grid" promise — the product's central value proposition. Flagged by alpha testing as the current highest-priority issue. | Implemented — see `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` |
| 2 | Export thread synchronization (renderer race, stale in-progress UI, destination-message race) | Real crash/corruption risk during the app's core "write files to disk" action | Planned — see `docs/ALPHA_HARDENING_PLAN.md` §1 |
| 3 | Safe shutdown during export | Closing the app mid-export can destroy a running `QThread` — known Qt crash pattern, plus silent partial file writes | Planned — §2 |
| 4 | Crash logging | Zero diagnostic trail today; every other bug found during alpha testing is harder to fix without this | Planned — §6 |
| 5 | Regression testing for the above | Confirms 2 & 3 are actually fixed and stay fixed | Planned — §3 |
| 6 | Release versioning | Bug reports currently can't be tied to a build | Planned — §5 |
| 7 | README accuracy | Alpha testers' entry point currently hides the GUI entirely | Planned — §4 |

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

- [ ] Export workspace can read/write its `PDFRenderer` from the GUI
      thread while `_ExportWorker` is rendering on a background thread
      (navigate away from Export and back mid-export). — plan §1
- [ ] Re-entering the Export step mid-export re-enables the Export
      button and hides the progress UI (internally guarded against a
      real double-dispatch, but visually misleading). — plan §1
- [ ] Switching PDFs mid-export shows "Exported N files to None." — the
      files land correctly, only the completion message is wrong. — plan §1
- [ ] No `closeEvent` handling: quitting the app while an export is
      running can destroy a live `QThread` (crash risk) and leaves
      partial files on disk with no warning. — plan §2
- [ ] No widget/thread-level regression tests exist for any of the above
      — current suite (405 tests) is 100% pure-function/dataclass level. — plan §3
- [ ] README.md documents only the CLI; the PySide6 GUI (`gui_app.py`)
      is misfiled under "Future work" as not-yet-built, along with
      drag-and-drop PDFs and interactive calibration — both also
      already shipped. — plan §4
- [ ] No version identity for the GUI anywhere (window title, about box,
      etc.) — CLI engine has `__version__ = "0.1.0"`, GUI has nothing. — plan §5
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
- **Cell-label prompt now uses human numbering.** The clarification
  dialog above asked for the ambiguous card's cell in internal 0-based
  `r2c2` form, confusing during manual validation. Now asks for a plain
  1-based `"row,col"` pair (e.g. `2,1`) and states the first card's
  row/column for reference; internal storage stays 0-based -- see
  DEVELOPER.md's "Cell-label prompt uses human, not internal, numbering."
- 469 passing unit tests across engine + GUI state/logic layers.

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
