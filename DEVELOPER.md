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
to derive gap too), and it shows the same old→new patch that `--measure`
prints, with a "Copy patch to clipboard" button. **This is the
recommended starting point for calibrating a brand-new deck** — no
pixel-reading by hand. It never writes to the profile itself; you paste
the values in yourself. Use it instead of `--measure` unless you're
scripting or already have pixel coordinates from another tool.

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
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt     # Runtime + test dependencies (pytest)
├── pyproject.toml           # pytest config (test paths, src layout)
├── README.md                 # Product/conceptual docs: what DeckForge is, grid math, calibration model
├── DEVELOPER.md              # This file — day-to-day mechanics of working on the repo
├── profiles/                 # One JSON calibration file per deck (e.g. solo_cards.json)
├── sample_decks/              # Source PDFs live here (e.g. Solo-cards-digital.pdf)
├── output/                    # --export writes front_NNN.png / back.png here
├── preview/                    # --preview/--overlay/--inspect/--contact-sheet write here
├── src/deckforge/
│   ├── profile.py             # DeckProfile: schema, JSON loading, validation
│   ├── pdf_renderer.py         # PyMuPDF page → Pillow image (only file that imports fitz)
│   ├── geometry.py             # Pure grid math: cell box → trimmed box → pixels (no I/O)
│   ├── cropper.py              # CardCropper: renders + geometry → cropped card images
│   ├── contact_sheet.py         # Tiles a list of images into a labeled QA sheet
│   ├── exporter.py              # DeckExporter: orchestrates preview/export/overlay/inspect/contact-sheet
│   ├── measure.py               # --measure: pixel coords → suggested profile patch (no rendering)
│   ├── calibrate_ui.py          # --calibrate: interactive click-to-measure window
│   └── cli.py                   # argparse wiring — the only file that knows about CLI flags
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
