# DeckForge Developer Handbook

This document exists so that you (or anyone else) can come back to
DeckForge after weeks away and be productive again in five minutes,
without having to re-derive how the project is organized or how to run
it. If you're looking for *what DeckForge is* and *how the calibration
model works conceptually*, see [README.md](README.md) — this file is
about the mechanics of working on the code.

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

**GUI shell prototype (Phase II)**

A PySide6 desktop application-frame prototype lives in
`src/deckforge_gui/`, separate from the CLI/engine package. It does not
call the extraction engine yet — this milestone only validates the
window shell (sidebar, top bar, context toolbar, workspace, guidance
panel, status bar) and its resizing behavior. The Tkinter `--calibrate`
window in `src/deckforge/calibrate_ui.py` is unaffected and still the
real calibration tool.

```powershell
pip install -r requirements-gui.txt
python gui_app.py
```

`requirements-gui.txt` layers PySide6 on top of `requirements.txt`, kept
separate so CLI-only installs don't need a GUI toolkit. `app_state.py`
holds all navigation/state logic with no PySide6 import, so it's unit
tested directly (`tests/test_app_state.py`) without opening a window.

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
or releasing Spacebar clears *temporary* pan state only
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
`coordinate_readout_position()` (for the small "X 1234  Y 5678" readout
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
/ `MAX_DISPLAY_HEIGHT` now only seed the window's *initial* size. The
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
right after `--export` to eyeball the *entire* deck at once before
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
  *why*, not just *what* — the diff already shows what changed.
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
├── src/deckforge_gui/            # PySide6 desktop shell (Phase II prototype, no engine calls yet)
│   ├── app_state.py              # Pure navigation/state model — no PySide6 import, unit tested directly
│   ├── main_window.py            # MainWindow: assembles top bar/sidebar/toolbar/workspace/guidance/status bar
│   ├── sidebar.py                # Fixed-width workflow sidebar
│   ├── guidance_panel.py         # Collapsible right-hand guidance panel
│   ├── calibrate_toolbar.py      # Fit/Zoom/Pan toolbar shown above the Calibrate workspace
│   └── workspaces.py             # Placeholder central workspace per workflow step
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
