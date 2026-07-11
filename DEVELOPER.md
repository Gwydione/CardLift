# DeckForge Developer Handbook

This document exists so that you (or anyone else) can come back to
DeckForge after weeks away and be productive again in five minutes,
without having to re-derive how the project is organized or how to run
it. If you're looking for _what DeckForge is_ and _how the calibration
model works conceptually_, see [README.md](README.md) — this file is
about the mechanics of working on the code.

## Security and Network Access

The core DeckForge workflow is local-first and must not require network access. Do not add telemetry, uploads, update checks, licensing calls, or other outbound communication without an explicit product decision, clear user disclosure, and documentation.

## First Five Minutes

The fastest path back to a working mental model after time away. Do
these in order; each one is also covered in more depth further down.

1. **Open PowerShell** in the project folder:
   ```powershell
   cd C:\Users\adodg\OneDrive\Documents\deckforge
   ```
2. **Activate the virtual environment:**
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
   Confirm your prompt now shows a `(.venv)` prefix.
3. **Run the test suite** to confirm the project still works:
   ```powershell
   pytest
   ```
4. **Reorient yourself** on what happened last:
   ```powershell
   git status
   git log --oneline -10
   ```
5. **Skim `profiles/solo_cards.json`** and re-read README's "How the
   grid math works" if the `left`/`top`/`trim_*` fields don't
   immediately make sense — this is the part that's easiest to forget.
   `solo_cards.json` uses the legacy flat-field form; see README
   "Profiles" for the `layouts`-list form a multi-grid deck would use
   instead, and `DeckProfile.layouts` (always populated, either way) is
   what downstream code actually reads.
6. **Run a sanity-check command** against the sample deck to see
   DeckForge actually do something before you start changing code:
   ```powershell
   python extract.py --profile solo_cards --preview
   ```
   Then open `preview/calibration_overlay.png` to see the current
   calibration.

At that point you're caught up — pick up wherever you left off, or see
"Typical Development Workflow" below for the normal cycle.

## Getting Started

**Open the project**

```powershell
cd C:\Users\adodg\OneDrive\Documents\deckforge
```

There's nothing to "launch" — DeckForge is a CLI tool, not a server. You
work on it in an editor and run `extract.py` from a terminal.

**Activate the virtual environment**

A venv already exists at `.venv/`. Activate it per-session:

```powershell
.venv\Scripts\Activate.ps1
```

(If you're in Git Bash instead of PowerShell: `source .venv/Scripts/activate`.)

You'll know it worked because your prompt gets a `(.venv)` prefix. Do
this every time you open a new terminal to work on DeckForge — nothing
below (`pytest`, `python extract.py ...`) will find the right
dependencies without it.

**Installing dependencies**

Only needed the first time, or after `requirements.txt` /
`requirements-dev.txt` change:

```powershell
pip install -r requirements-dev.txt
```

This pulls in runtime deps (`PyMuPDF`, `Pillow`) plus `pytest` for
testing. Use `requirements.txt` alone only if you specifically want a
runtime-only install with no test tooling.

**Running the full test suite**

```powershell
pytest
```

`pyproject.toml` already points pytest at `src/` and `tests/`, so this
works from the project root with no extra flags. Run it now, before
touching anything, to confirm your environment is healthy.

**GUI (Phase II)**

A PySide6 desktop application lives in `src/deckforge_gui/`, separate
from the CLI/engine package. The Tkinter `--calibrate` window in
`src/deckforge/calibrate_ui.py` is unaffected and still the real
calibration tool.

```powershell
pip install -r requirements-gui.txt
python gui_app.py
```

`requirements-gui.txt` layers PySide6 on top of `requirements.txt`, kept
separate so CLI-only installs don't need a GUI toolkit.

Two plain-Python models back the widgets, both free of any PySide6
import so they're unit tested directly without opening a window:

- `app_state.py` — navigation/pan/guidance-collapse state
  (`tests/test_app_state.py`).
- `session.py` — the loaded PDF (`DeckSession`/`DeckLoadError`;
  `tests/test_session.py`). It reuses the engine's `PDFRenderer` (open +
  `page_count`) rather than re-implementing PDF validation — its only
  job is turning a rejected file into a friendly `DeckLoadError` at the
  GUI boundary.

**Welcome Experience milestone.** The first real workflow: launch → open
a PDF on the Deck page (drag-and-drop onto the dashed drop zone, or the
"Choose PDF" button) → DeckForge reads the page count via `PDFRenderer`
→ the Deck step is marked complete and the app auto-advances to Find
Cards. `deck_workspace.py` (`DeckWorkspace`) owns the drop
zone/click-to-browse/error-display UI but never decides whether a file
is a valid PDF -- that's `DeckSession.load_pdf`'s job; `main_window.py`
wires the two together. `theme.py` centralizes the color palette (dark
navigation chrome, light PDF workspace, purple accent) so widgets don't
each hardcode hex values. Find Cards, Calibrate, Review Cards, and
Export are still placeholders -- this milestone only wires the Deck →
Find Cards step.

**Responsive Deck workspace.** `DeckWorkspace` no longer fixes the drop
zone, margins, and type scale to constant pixel sizes -- at moderate
window sizes the page looks the same as before, but on a large monitor the
drop zone, heading, and whitespace all grow instead of leaving the page
looking like a small dialog stranded in a mostly-empty workspace (see
DESIGN_PRINCIPLES.md's "The PDF is the workspace"). `_apply_responsive_metrics`
recomputes every scaled size from a single `t` (`theme.responsive_t()`,
0 at `_COMPACT_WIDTH` and below, 1 at `_SPACIOUS_WIDTH` and above) on
every `resizeEvent`/`showEvent`, so growth is continuous rather than a
hard breakpoint jump; each metric's minimum matches the old fixed value,
so nothing changes below `_COMPACT_WIDTH`. `theme.lerp()`/`clamp()`/
`responsive_t()` are generic enough that a future workspace needing the
same "scale with available width" behavior can reuse them instead of
duplicating the math.

**Find Cards milestone.** The documented workflow order is Deck -> Find
Cards -> Calibrate -> Review Cards -> Export (docs/ui/UI*DECISIONS.md),
so Find Cards runs \_before* any calibration profile exists. It is
deliberately a coarse, page-level scoping step, not detection or
calibration: there is no automatic card-detection algorithm anywhere in
DeckForge (README's MVP is manual-calibration-only), and Calibrate's own
two-corner-click flow (the CLI's `--calibrate`, via
`measure.derive_geometry()`) already owns deriving precise card geometry
later -- redoing that work here would just be duplication.

`find_cards_state.py` is the pure-Python model (no PySide6 import, unit
tested in `tests/test_find_cards_state.py`, same pattern as
`app_state.py`/`session.py`): `FindCardsState` holds at most one
`PageMarker` per page, storing it in **PDF points** -- the same canonical
page coordinate space `profile.py`/`geometry.py` already use everywhere --
rather than rendered-image or widget pixels, so a marker stays correct
across a window resize or a future zoom/pan change. A point, not a
rectangle: Calibrate will re-derive the actual card box from scratch via
its own corner clicks, so a coarser region here would add nothing
Calibrate can't already produce more precisely itself.

`find_cards_workspace.py` (`FindCardsWorkspace`) renders the current page
via the engine's `PDFRenderer` at a fixed `PREVIEW_RENDER_SCALE` (no
profile/render_scale exists yet at this point in the workflow), fits it to
the canvas without upscaling, and lets the user click to place/replace
that page's marker. `FindCardsView` is the pure (no Qt-widget-instance
dependency) coordinate transform between PDF points and widget pixels,
recomputed on every paint -- unit tested directly in
`tests/test_find_cards_workspace.py`, including that the same stored point
lands on the same relative spot on the page at any widget size. Page
navigation (Previous/Next) and "Clear this page" are local to the
workspace; there is no app-wide Start Over feature yet for Find Cards
state to participate in. Loading a (new or replacement) PDF via
`MainWindow._on_pdf_chosen` clears any previous markers, since a marker's
page number has no relationship to the same page number in a different
PDF.

Out of scope for this milestone, deferred to later ones: inferring
rows/cols or precise crop geometry from a marker, selecting/moving/
resizing individual card rectangles (Edit Cards is a separate, later
concern), and any app-wide reset/Start Over feature.

**Calibrate milestone.** The first milestone where precise geometry is
established: two-corner-click measurement of one representative "Cards"
(front) page plus a freely-navigated "Shared Back" page, reusing the
CLI's calibration math (`measure.derive_geometry()`, the same
inverse-geometry solver `--calibrate`/`--measure` use) and click
semantics (corner normalization, auto-inferred neighbor cell, optional
second-card gap measurement) rather than re-deriving any of it.

`calibrate_state.py` is the pure-Python model (no PySide6 import, unit
tested in `tests/test_calibrate_state.py`): `CalibrateState` holds two
independent `CalibrationTarget`s (`cards`/`back`), each with its own
pending click, measurements, and derived `CalibratedGeometry`.
`record_click()` is a small state machine returning a `ClickOutcome`
(`PENDING_SET`/`MEASUREMENT_ADDED`/`REJECTED_DEGENERATE`/
`NEEDS_CELL_LABEL`/`COMPLETE`/`IGNORED_ALREADY_COMPLETE`) rather than
touching Qt directly, mirroring `CalibrationWindow`'s transitions exactly
but as directly-testable data. Measurements are stored in **PDF points**
(not pixels, per the project's coordinate-storage rule) -- pixel space
is reconstructed only for the moment `derive_geometry()` needs it
(`point * render_scale`, a lossless round trip, not a re-measurement).

**Shared Back is single-card only.** Cards supports an optional second-
card measurement to derive `gap_x`/`gap_y` for a printed grid, but Shared
Back is one representative card's rectangle, not a grid -- there's no
neighboring back to space against. `CalibrationTarget.allows_second_
measurement` (`True` for `cards`, `False` for `back`) is the one switch
`record_click()` checks: when it's `False`, the target finalizes as soon
as its single card's second corner is clicked, so Shared Back never shows
neighbor suggestions or a "Finish with one card" button -- both are
already gated on `not target.is_complete`, so completing one click
earlier hides them for free rather than needing a step-specific branch in
`calibrate_workspace.py`. `calibrate_guidance_text()`/
`calibrate_status_text()`'s completion copy for Shared Back names the
representative page and states the result will be applied as the shared
back for every selected front-card page, mirroring how Cards' completion
copy names its scope (see "Presenting one shared geometry" below).

Deliberately **not** reused from the CLI: the "copy suggested patch,
paste into profiles/\*.json by hand" model. That step exposes JSON/
profile-normalization concepts `docs/ui/DESIGN_PRINCIPLES.md` says the
GUI should hide, and Phase II has no profile file at all yet. Derived
geometry is instead held directly in `CalibrateState` -- a future
profile-building milestone reads from it rather than the user retyping
numbers. Relatedly, `CalibrateState` never constructs a `profile.
CardLayout` (rows/cols and page-range enumeration stay out of scope, same
as Find Cards) -- it only holds the `GridGeometry`-shaped subset a future
milestone would combine with rows/cols to build one.

Cards and Shared Back have different page-navigation sources:
`CalibrateWorkspace._navigable_pages()` restricts Cards to
`find_cards_state.marked_pages()` (one shared geometry is assumed to
apply to every marked page) but lets Shared Back page through the whole
PDF freely, defaulting to the last page (the common convention for a
shared back), since no earlier step identifies which page it is.
Leaving a page mid-measurement (a pending click, or one measurement not
yet finished) discards that in-progress state -- it only makes sense on
the page it was clicked on. `CalibrateState.cards_is_stale()` is a
pull-based check (not a signal) comparing `calibrated_page_num` against
Find Cards' current markers, run by `MainWindow` whenever the user
navigates into the Cards step, so unmarking the page a calibration came
from resets it without coupling the two state classes together.

`view_transform.py` is a straight port of `calibrate_ui.py`'s
`ViewTransform` (and its pure sibling functions -- `wheel_direction`,
`is_pan_gesture`, `pan_active`, `recompute_view_for_resize`) into
`deckforge_gui`, not an import: `calibrate_ui.py` imports `tkinter` at
module scope, so importing anything from it would make Tkinter a hard
dependency of the PySide6 app. It's shared GUI infrastructure rather than
Calibrate-only code, since Preview/Edit Cards will need the same
zoom/pan/fit foundation. `CalibrateWorkspace` (`calibrate_workspace.py`)
draws the page and every overlay (measured box, pending marker, neighbor
suggestions, always-on guide lines) with immediate-mode `QPainter` in one
`paintEvent`, the same pattern `find_cards_workspace.py` established,
rather than `calibrate_ui.py`'s Tkinter canvas-item approach.

The CLI's step-numbered wizard chrome ("Step 1 of 3") is intentionally
not carried over -- the guidance panel and status bar already have a
proven multi-cue pattern for "what's happening right now" (see Pan mode),
so `calibrate_guidance_text()`/`calibrate_status_text()` make that text
state-aware (pending corner / one card measured / calibrated) instead of
introducing a step counter. The underlying state machine is identical;
only the presentation differs.

**Presenting one shared geometry, not per-page calibration.** Cards
calibration produces a single geometry from one representative marked
page, applied to every page Find Cards selected -- but early wording
("Calibrated.", "Page 3 (2 of 6 marked)") read as though each page still
needed its own calibration, especially with page navigation still
available afterward. `calibrate_guidance_text()`/`calibrate_status_text()`
now take a `marked_page_count` (threaded from `FindCardsState` through
`CalibrateWorkspace`, `GuidancePanel`, and `MainWindow._status_text()`) so
the completion message names the representative page and states that the
result applies to all selected front-card pages. Separately,
`CalibrateWorkspace._page_label_text()` grounds page navigation in the
original PDF's numbering ("PDF page 3 of 8") as the primary line, with the
front-card-relative position ("Front card page 2 of 6") as a visually
lighter secondary line -- rather than replacing PDF page numbers with a
filtered sequence, which made pages excluded by Find Cards (e.g. the
shared back) feel like they'd been dropped rather than simply out of
scope for this step. Shared Back keeps just the PDF-page line, since it
navigates the whole PDF rather than a marked subset.

## Common Commands

All commands go through `extract.py` and require `--profile <name>`
(the JSON file in `profiles/`, without `.json`). Everything below
assumes the venv is activated. Full flag reference: `python extract.py --help`.

### `--preview`

```powershell
python extract.py --profile solo_cards --preview
```

Renders `first_front_page` only, crops its cards, and writes
`preview/calibration_overlay.png` (blue = raw grid cell, red = the
actual saved crop) plus a per-page contact sheet
(`preview/page{N}_preview.png`). **Use this first, and most often** —
it's the main calibration loop: change a value in the profile JSON, run
`--preview`, look at the overlay, repeat.

### `--overlay`

```powershell
python extract.py --profile solo_cards --overlay
python extract.py --profile solo_cards --overlay --page 8
```

Same blue/red overlay as `--preview`, but for one page only, without
re-cropping everything or rebuilding a contact sheet. Use this to check
a specific page fast — most usefully the back page (`--page` with the
profile's `back_page` number), which `--preview` doesn't cover.

### `--inspect CARD_NUM`

```powershell
python extract.py --profile solo_cards --inspect 1
# → preview/inspect_card001.png
```

Exports one card at high zoom with the raw cell and trimmed crop drawn
on it, plus surrounding page context. `CARD_NUM` is 1-indexed, matching
`front_NNN.png` numbering. Use this when the full-page overlay is too
small to tell whether a trim is off by a couple of points, or to
recheck one specific card (e.g. the last on a page, in case of
cumulative drift).

### `--calibrate`

```powershell
python extract.py --profile solo_cards --calibrate
python extract.py --profile solo_cards --calibrate --page 8
```

Opens an interactive window on the rendered page: click a card's
upper-left then lower-right corner (and optionally a neighboring card,
to derive gap too), and it shows a "Copy Calibration Settings" button
plus, tucked behind an optional "Technical Details" toggle, the same
old→new patch that `--measure` prints. **This is the recommended
starting point for calibrating a brand-new deck** — no pixel-reading by
hand. It never writes to the profile itself; you paste the values in
yourself. Use it instead of `--measure` unless you're scripting or
already have pixel coordinates from another tool.

The window supports mouse-wheel zoom (anchored under the pointer), a
persistent **Pan** toggle button, Spacebar+left-drag or middle-drag pan,
"Fit to Window"/"100%" view buttons, and a **Crosshair** toggle that
draws full-canvas guide lines through the pointer — see README's "Zooming
and panning for precise clicks" and "Crosshair". These only change what's
on screen; every
click is converted from canvas (screen) pixels to rendered-image pixels
exactly once, at the point of the click, via `ViewTransform` in
`calibrate_ui.py`, so the same corner clicked at any zoom/pan/window-size
produces the same measurement. Mouse-wheel input is normalized to a
`-1`/`0`/`+1` direction (`wheel_direction()`) instead of trusting the raw
`event.delta` magnitude, since Windows and macOS report wildly different
scales for the same physical scroll — this is the one place that needs to
reason about platform differences, and it's a pure function rather than a
`sys.platform` branch. All of this — `ViewTransform`, the wheel-direction
normalization, and the pan-vs-click gesture decision
(`is_pan_gesture()`) — is plain Python with no Tkinter dependency, unit
tested in `test_calibrate_ui.py` without opening a window.

**Pan mode.** `is_pan_gesture(button, space_held, pan_mode)` is the single
decision point for whether a left press pans or clicks — it accounts for
persistent Pan mode (the button), temporary Spacebar hold, and the
always-pan middle button. `CalibrationWindow._pan_mode` is only turned off
by clicking Pan again or Escape (`pan_mode_after_escape()`); losing focus
or releasing Spacebar clears _temporary_ pan state only
(`cleared_temporary_pan_state()`), leaving a deliberately-selected Pan
mode alone. Pan mode changes only how the page is viewed, never a
calibration value — clicking Pan on/off, panning, or zooming never
touches `self.measurements`.

**Crosshair.** A discoverable calibration aid, on by default, toggled by
the **Crosshair** button next to Pan (same sunken/raised button treatment
as Pan). While enabled and the pointer is over the canvas, two reusable
canvas line items — one horizontal, one vertical, created lazily on first
`<Motion>` and moved/hidden/shown afterward rather than recreated every
event — are drawn through the pointer, spanning the full canvas. They
live entirely in canvas space (`crosshair_display_position()` returns a
canvas (x, y) or `None`) and are deliberately **not** added to
`self._overlay_ids`, so `_redraw_overlays()` never deletes them; instead
`_raise_crosshair()` runs after every image/overlay redraw to keep them
on top of newly (re)created items. `crosshair_display_position()` and
`coordinate_readout_position()` (for the small "X 1234 Y 5678" readout
next to the zoom percentage, in rendered-image pixels) both fold in
`pan_active()` — true for persistent Pan mode, a temporary Spacebar hold,
or an active pan drag — so every caller (pointer motion, leaving the
canvas, a resize, a pan-mode change) asks one function "where, if
anywhere" instead of re-deriving the visibility rule. `Start Over` and
`Escape` route the toggle's value through identity functions
(`crosshair_enabled_after_reset()`, `crosshair_enabled_after_escape()`)
purely so that invariant — neither ever touches the Crosshair preference
— has a named, unit-tested home, matching `pan_mode_after_escape()`'s
existing style. Like the rest of this section, none of it touches
`self.measurements` or any image-space calibration math.

**Responsive viewport.** The canvas is laid out with Tkinter grid
row/column weights so it expands to fill whatever space the window is
given, instead of being capped at a fixed pixel size — `MAX_DISPLAY_WIDTH`
/ `MAX_DISPLAY_HEIGHT` now only seed the window's _initial_ size. The
canvas's `<Configure>` event (fired on resize/maximize) is debounced
(`RESIZE_DEBOUNCE_MS`) and ignores degenerate sizes below
`MIN_VIEWPORT_DIM`, so a window-border drag doesn't repeatedly re-crop the
full-resolution source image, and the first render never happens against
a placeholder 1×1 canvas. `recompute_view_for_resize()` is the single pure
function deciding what happens to the view on resize: in Fit-to-Window
mode it recalculates the fit for the new canvas size
(`CalibrationWindow._fit_mode`, set by "Fit to Window" and cleared by
"100%"/manual zoom); otherwise it preserves scale and keeps the image
point at the old viewport's center under the new viewport's center
(`ViewTransform.recentered_for_resize()`) before clamping. Like the rest
of `ViewTransform`, these are unit tested without opening a window.

### `--measure`

```powershell
python extract.py --profile solo_cards --measure --card r0c0:240,420,960,1360
python extract.py --profile solo_cards --measure \
  --card r0c0:240,420,960,1360 --card r0c1:1000,420,1720,1360
```

The non-interactive sibling of `--calibrate`: give it pixel coordinates
you already read off a rendered `--preview`/`--overlay` image (e.g. in
an image viewer with a coordinate readout), and it converts them into a
suggested `left`/`top`/`card_width`/`card_height`/`gap_x`/`gap_y` patch.
Pure arithmetic — it never renders, crops, or touches the profile. Use
it when you're doing calibration headless/scripted, or already have
coordinates on hand and don't want to open the interactive window.

### `--export`

```powershell
python extract.py --profile solo_cards --export
# → output/front_001.png ... output/front_NNN.png, output/back.png
```

The real deal: exports every card front across
`[first_front_page, last_front_page]` plus the back, to `output/`. Run
this once a profile is calibrated (red boxes in the overlay sit exactly
on card edges) and you actually want the images — e.g. to import into
PlayingCards.io or Tabletop Simulator.

### `--contact-sheet`

```powershell
python extract.py --profile solo_cards --contact-sheet
# → preview/contact_sheet.png
```

Builds one tiled, labeled QA image from everything currently in
`output/` (every exported front, in order, plus the back). Use this
right after `--export` to eyeball the _entire_ deck at once before
importing it anywhere — catches things a single-card inspect would
miss, like one page's grid drifting relative to the others.

## Typical Development Workflow

1. Pull latest changes (once this repo has a remote — not yet applicable).
2. Activate the virtual environment (`.venv\Scripts\Activate.ps1`).
3. Run the test suite (`pytest`) to confirm you're starting from a clean baseline.
4. Implement the feature or fix, in small increments.
5. Run the test suite again — don't let a broken test linger while you keep coding.
6. Test manually: run the relevant `extract.py` command(s) against
   `sample_decks/Solo-cards-digital.pdf` (or another real PDF) and look
   at the actual output/preview images. DeckForge is an image tool —
   passing tests don't guarantee the crop looks right.
7. Commit (see "Git Workflow" below).
8. Repeat from step 4 for the next increment.

## Git Workflow

- **`git status`** — run this constantly, especially before anything
  destructive. It's the cheapest way to know what you're about to
  commit (or about to lose).
- **`git add .`** — stage everything you've changed. Fine for this
  project's size, but check `git status` output first if you've been
  experimenting with throwaway files (e.g. scratch PDFs or output
  images) you don't want committed.
- **`git commit`** — commit once a change is a coherent, working unit
  (a passing test suite, a working command). Write a message that says
  _why_, not just _what_ — the diff already shows what changed.
- **`git log --oneline`** — use this to reorient yourself at the start
  of a session, or to check whether a change you're about to make
  duplicates something already done. This project's existing log
  (`git log --oneline`) is a good model for commit message style —
  short, milestone-based, present tense.

## Project Structure

```
DeckForge/
├── extract.py              # CLI entry point — thin, delegates to src/deckforge
├── gui_app.py               # GUI entry point — thin, delegates to src/deckforge_gui (Phase II prototype)
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt     # Runtime + test dependencies (pytest)
├── requirements-gui.txt     # Runtime + PySide6, for the GUI shell prototype
├── pyproject.toml           # pytest config (test paths, src layout)
├── README.md                 # Product/conceptual docs: what DeckForge is, grid math, calibration model
├── DEVELOPER.md              # This file — day-to-day mechanics of working on the repo
├── profiles/                 # One JSON calibration file per deck (e.g. solo_cards.json)
├── sample_decks/              # Source PDFs live here (e.g. Solo-cards-digital.pdf)
├── output/                    # --export writes front_NNN.png / back.png here
├── preview/                    # --preview/--overlay/--inspect/--contact-sheet write here
├── src/deckforge/
│   ├── profile.py             # DeckProfile: schema, JSON loading, validation (layouts list + legacy normalization -- see README "Profiles")
│   ├── pdf_renderer.py         # PyMuPDF page → Pillow image (only file that imports fitz)
│   ├── geometry.py             # Pure grid math: cell box → trimmed box → pixels (no I/O)
│   ├── cropper.py              # CardCropper: renders + geometry → cropped card images
│   ├── contact_sheet.py         # Tiles a list of images into a labeled QA sheet
│   ├── exporter.py              # DeckExporter: orchestrates preview/export/overlay/inspect/contact-sheet
│   ├── measure.py               # --measure: pixel coords → suggested profile patch (no rendering)
│   ├── calibrate_ui.py          # --calibrate: interactive click-to-measure window
│   └── cli.py                   # argparse wiring — the only file that knows about CLI flags
├── src/deckforge_gui/            # PySide6 desktop app (Phase II)
│   ├── app_state.py              # Pure navigation/state model — no PySide6 import, unit tested directly
│   ├── session.py                # Pure DeckSession/DeckLoadError model — loaded PDF, via engine's PDFRenderer
│   ├── theme.py                  # Shared color palette (dark nav chrome, light PDF workspace, purple accent)
│   ├── main_window.py            # MainWindow: assembles top bar/sidebar/toolbar/workspace/guidance/status bar
│   ├── sidebar.py                # Fixed-width workflow sidebar
│   ├── guidance_panel.py         # Collapsible right-hand guidance panel
│   ├── calibrate_toolbar.py      # Fit/Zoom/Pan toolbar shown above the Calibrate workspace
│   ├── calibrate_state.py        # Pure CalibrateState/CalibrationTarget model -- two-corner-click geometry, in PDF points
│   ├── calibrate_workspace.py    # Calibrate page (Cards/Shared Back): PDF canvas, click handling, zoom/pan, overlays
│   ├── view_transform.py         # Ported ViewTransform + pure zoom/pan/fit math (from calibrate_ui.py), shared GUI infra
│   ├── deck_workspace.py         # Deck page: drag-and-drop/click-to-browse PDF drop zone
│   ├── find_cards_state.py       # Pure FindCardsState/PageMarker model -- coarse per-page markers, in PDF points
│   ├── find_cards_workspace.py   # Find Cards page: PDF page-by-page preview + marker placement
│   └── workspaces.py             # Central workspace per workflow step (placeholders past Calibrate)
└── tests/                        # pytest suite, mirrors the src/deckforge module split
```

The module split is deliberate and worth preserving: each file has one
job, so a future change (a new PDF backend, an auto-calibrator, a new
export target) should only ever touch one or two files. See README's
"Why split this way" for the reasoning — read it before restructuring
anything in `src/deckforge/`.

## CLI Output Conventions (`cli.py`)

`cli.py` carries two presentation conventions on top of parsing args —
both are UI-only and don't touch `exporter.py`/`geometry.py`/etc.:

- **"Next:" nudges.** Every successful command ends with a line
  suggesting the next command in the calibrate → preview → export →
  contact-sheet chain (e.g. `--preview` suggests `--export` once the
  overlay looks right). If you add a new mode flag, give it one too —
  say what a first-time user would naturally do with the output.
- **`friendly_error()`.** Every raised `ProfileError` / `PDFRenderError`
  / `ExportError` / `GeometryError` / `MeasureError` is caught in
  `main()` and passed through `friendly_error()`, which matches on
  substrings of the exception's existing message to prepend a plain-
  language cause + "Next step:", then prints the original message
  underneath as `Details:`. This means the underlying modules never
  need to know about presentation — they just keep raising the same
  clear, specific messages they already do — but it also means
  `friendly_error()`'s substring matches can go stale if you reword an
  exception message without checking `friendly_error()`'s branches for
  it (see `cli.py`'s docstring on that function). Anything not matched
  falls back to a generic sentence rather than erroring.
  `except Exception` in `main()` is the last resort for truly
  unanticipated failures (a bug, a corrupt PDF) — it prints a short
  notice plus the full traceback under `Details:`, so nothing surfaces
  as a bare, unexplained crash.
- **`format_export_summary()`.** `--export`'s completion message (card/
  back counts, pixel size, output location, and a suggested next step)
  is built from the list of files `DeckExporter.export()` already
  returns — no export logic changed to support this, it's pure
  after-the-fact description.

## Claude Code Workflow

How we expect Claude Code to be used on this project:

- **Review architecture before major changes.** Re-read the "Why split
  this way" section of README.md (and this file's "Project Structure")
  before adding a new module or changing responsibilities between
  existing ones. The module boundaries exist to keep future features
  additive rather than disruptive — don't blur them for convenience.
- **Keep commits small and milestone-based.** Match the existing log
  style (`git log --oneline`): each commit should be one coherent,
  working step, not a bundle of unrelated changes.
- **Add tests for new logic.** Especially anything in `geometry.py` or
  `measure.py` — pure functions with no I/O are cheap to test
  thoroughly and expensive to get subtly wrong (see README's note about
  the per-card rounding-drift bug caught this way).
- **Update documentation when commands or workflows change.** If a CLI
  flag's behavior changes, or a new one is added, update README.md
  (conceptual/how-it-works) and this file (DEVELOPER.md) in the same
  change — not as a follow-up.
- **Preserve the vision of making DeckForge easy for non-technical
  users.** The manual-calibration-only design, the `--calibrate`
  interactive window, and the blue/red overlay convention all exist to
  make an inherently fiddly task (aligning a crop grid) forgiving and
  visual rather than requiring someone to read PDF point math. Favor
  changes that keep that experience simple and visual over ones that
  add power at the cost of clarity.

## Phase II GUI Development

Before implementing GUI changes, review the following:

- README.md
- DEVELOPER.md
- ENGINEERING_STANDARDS.md
- Everything in docs/ui/

The mockups are design specifications, not pixel-perfect implementation
requirements.

When implementation constraints require compromise, preserve the workflow,
information hierarchy, and overall user experience over exact appearance.

The purpose of the GUI is to make the engine approachable for tabletop
gamers, not to expose implementation details.

## Workflow Completion

A milestone is not complete simply because its primary functionality has been implemented.

Before considering a workflow complete, verify:

- How the user enters the workflow.
- How the user knows they are making progress.
- How the user knows they have finished.
- What the obvious next action is.
- How the next workflow step becomes available.
- How the user returns to this workflow later.

Avoid leaving users in dead-end states where the functionality is complete but the application does not clearly communicate what to do next.

## UX Validation

Implementation is not considered complete until the developer has personally exercised the workflow.

Repository analysis and unit tests cannot replace interactive evaluation.

After implementation:

- perform the workflow
- note anything surprising
- fix obvious UX issues before considering the milestone complete

## First-Time User Review

Before declaring a milestone complete, mentally walk through the workflow as a first-time user.

Assume the user has not read the documentation and does not know the internal architecture.

Review:

- terminology
- guidance text
- page numbering
- status messages
- visual hierarchy
- navigation
- completion messaging

If the implementation is technically correct but could reasonably mislead a first-time user, treat that as a UX issue rather than expected behavior.

## Design Philosophy

When improving DeckForge:

- Observe user friction first.
- Describe the problem, not the solution.
- Ask Claude Code to think like a first-time user.
- Review the proposed improvements before implementation.
- Test the workflow again.

## Maintaining This Document

Whenever new commands, workflows, or development practices are added to
DeckForge, please update DEVELOPER.md as part of the same change.
