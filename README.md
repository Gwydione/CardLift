# DeckForge

Extract individual card images from print-and-play PDFs, laid out as a
fixed grid of cards, for import into platforms like PlayingCards.io or
Tabletop Simulator.

The MVP does **manual calibration only** — no automatic edge detection.
You tell DeckForge exactly where the grid is via a JSON profile, and it
crops accordingly. This is deliberate: PnP PDFs vary wildly in margins,
bleed, and cut-line placement, and a wrong automatic guess silently
produces bad crops. A profile you calibrated once by eye is trustworthy
and reproducible. Automatic calibration is a plausible future addition
(see "Future work" below) — the architecture is split so that a future
auto-calibrator only needs to *produce* a profile; nothing else changes.

## Requirements

- Python 3.10+ (3.12 recommended)
- Dependencies: `PyMuPDF`, `Pillow`

```bash
pip install -r requirements.txt
```

## Project structure

```
DeckForge/
├── extract.py              # CLI entry point (thin — parses args, calls src/deckforge)
├── requirements.txt
├── README.md
├── profiles/                # One JSON calibration file per deck
│   └── solo_cards.json
├── sample_decks/            # Put source PDFs here
│   └── Solo-cards-digital.pdf
├── output/                  # front_001.png ... front_NNN.png + back.png
├── preview/                 # Calibration overlay + contact sheets
└── src/deckforge/
    ├── profile.py            # DeckProfile: schema, JSON loading, validation
    ├── pdf_renderer.py        # PDFRenderer: PyMuPDF page → Pillow image (only file that imports fitz)
    ├── geometry.py            # Pure grid math: cell box → trimmed box → pixels
    ├── cropper.py             # CardCropper: renders + geometry → cropped card images
    ├── contact_sheet.py       # Tiles a list of images into a labeled QA sheet
    ├── exporter.py             # DeckExporter: orchestrates preview/export/contact-sheet
    └── cli.py                  # argparse wiring
```

### Why split this way

Each module has exactly one job, so each is independently testable and
independently replaceable:

- **pdf_renderer.py** is the only file that touches PyMuPDF. If DeckForge
  ever needs a different PDF backend, this is the only file that changes.
- **geometry.py** has zero PDF or image code — it's pure arithmetic over
  points and pixels. This is what an automatic-calibration feature would
  need to replace (feed it different numbers), without touching cropping,
  rendering, or export logic at all.
- **cropper.py** and **exporter.py** are the only files that know about
  the *shape* of a deck (rows/cols, front pages, back page). A future
  Tabletop Simulator exporter would reuse `CardCropper` output and just
  package it differently — it wouldn't need to re-derive any grid math.

## How the grid math works

All spatial values in a profile are in **PDF points** (1/72 inch) — the
same coordinate space PyMuPDF reports for a page at zoom 1.0, regardless
of `render_scale` (which is purely an output-resolution multiplier).

For a `rows` × `cols` grid, each cell's un-trimmed box is:

```
x0 = left + col * (card_width + gap_x)
y0 = top  + row * (card_height + gap_y)
x1 = x0 + card_width
y1 = y0 + card_height
```

`left`/`top` is the top-left corner of card (row 0, col 0). `gap_x`/
`gap_y` is empty space between adjacent cells (0 if cards are printed
edge-to-edge).

Then an inward trim is subtracted from each side independently:

```
x0 += trim_left
y0 += trim_top
x1 -= trim_right
y1 -= trim_bottom
```

Trim exists so you can shave off a shared border or cut-line **without**
touching `card_width`/`card_height`, which would shift every other card's
spacing at the same time.

### Front/back grids can differ

Some decks draw card backs inset in their cell (with a visible margin)
rather than edge-to-edge like the fronts. Rather than force one geometry
onto both, a profile's `back_*` fields (`back_left`, `back_top`,
`back_card_width`, `back_card_height`, `back_gap_x`, `back_gap_y`) are
optional overrides used only for `back_page`. Omit them entirely if your
back page shares the front grid exactly.

The bundled `solo_cards.json` profile actually needs this: its back page
cards are smaller and inset within their cell, while the fronts are
edge-to-edge.

## Profiles

Every deck gets its own JSON file in `profiles/`. Required fields:

| Field | Meaning |
|---|---|
| `pdf_file` | Filename to look for in `sample_decks/` (or the project root) |
| `first_front_page`, `last_front_page` | 1-indexed page range containing card fronts |
| `back_page` | 1-indexed page containing the card back(s) |
| `rows`, `cols` | Grid size per page |
| `left`, `top` | Top-left corner of card (row 0, col 0), in points |
| `card_width`, `card_height` | Size of one card cell, in points |
| `gap_x`, `gap_y` | Space between cells, in points (0 = edge-to-edge) |
| `trim_left/right/top/bottom` | Inward crop applied after grid positioning, in points |
| `render_scale` | Points-to-pixels multiplier for output resolution (e.g. `4` ≈ 288 DPI) |

Optional: `back_left`, `back_top`, `back_card_width`, `back_card_height`,
`back_gap_x`, `back_gap_y` (see above).

## Calibrating a new deck

1. Drop the PDF in `sample_decks/`, create `profiles/your_deck.json` with
   your best-guess numbers (or zeros to start).
2. Run:
   ```bash
   python extract.py --profile your_deck --preview
   ```
   This renders **only** `first_front_page`, crops its cards, and writes
   two files to `preview/`:
   - `calibration_overlay.png` — the full page with every cell drawn on
     it: **blue** = the raw cell (`left`/`top`/`card_width`/`card_height`/
     `gap`), **red** = the actual saved crop (after trim).
   - `page{N}_preview.png` — a contact sheet of just that page's cropped
     cards.
3. Open `calibration_overlay.png` and adjust the profile based on what
   you see:

   | Symptom | Fix |
   |---|---|
   | Blue grid systematically off in one direction | Adjust `left` / `top` |
   | Blue grid spacing drifts card-by-card (fine at col 0, off by col 2) | Adjust `card_width` / `card_height` |
   | Cards overlap, or grid is too tight | Increase `gap_x` / `gap_y` |
   | Red crop cuts into art on the left/right/top/bottom | Increase the matching `trim_*` |
   | Red crop includes a sliver of the neighboring card | Increase the matching `trim_*` |
   | Output looks blurry | Increase `render_scale` (e.g. `4` → `6`) |

4. Re-run `--preview` after every change until the red boxes sit exactly
   on the edges you want, with no art clipped and no neighboring card
   included.
5. If your deck's back page uses a different grid than the fronts,
   repeat steps 2–4 for the `back_*` fields, checking `output/back.png`
   after an export (there's no dedicated back-page preview command yet —
   the fastest loop is export → check `output/back.png` → adjust →
   re-export).
6. Export:
   ```bash
   python extract.py --profile your_deck --export
   ```
   This assumes every page in `[first_front_page, last_front_page]`
   shares the same front grid. If a real PDF has per-page drift (rare,
   but possible with hand-assembled PnP sheets), you'll need to spot
   check a few more pages, or split into a second profile for the
   affected range.
7. QA everything at once:
   ```bash
   python extract.py --profile your_deck --contact-sheet
   ```
   Writes `preview/contact_sheet.png` with every exported front (in
   order) plus the back, so you can scan the whole deck before importing.

## Commands

```bash
python extract.py --profile solo_cards --preview
# → preview/calibration_overlay.png, preview/page2_preview.png

python extract.py --profile solo_cards --export
# → output/front_001.png ... output/front_054.png, output/back.png

python extract.py --profile solo_cards --contact-sheet
# → preview/contact_sheet.png
```

All front cards are guaranteed to come out at identical pixel dimensions
(the crop math rounds card size once and reuses it for every cell, so
per-card rounding drift can't sneak in a 1px difference — a real bug
caught while building this).

## Included sample deck

`sample_decks/Solo-cards-digital.pdf` is a 54-card solo-RPG oracle deck:
page 1 is instructions, pages 2–7 are fronts (3×3 grid, 54 cards total),
page 8 is backs (only one unique back is needed). `profiles/solo_cards.json`
is calibrated for it and verified against the actual PDF — front cards
are edge-to-edge; back cards are inset with a visible gap, hence the
`back_*` overrides.

## Future work

Not implemented yet, but the module boundaries above were chosen to make
these additive rather than disruptive:

- Automatic grid/edge detection (would live behind `geometry.py`'s
  interface, feeding `GridGeometry` + trim values the same way a manual
  profile does)
- PlayingCards.io deck package export, Tabletop Simulator export
  (both would consume `CardCropper` output — see `exporter.py`)
- GUI (CustomTkinter), interactive calibration mode, drag-and-drop PDFs
- Multiple saved deck profiles browsed/selected from a UI
- Per-page grid overrides (for hand-assembled PnP sheets with real drift
  between pages, beyond the front/back split already supported)
