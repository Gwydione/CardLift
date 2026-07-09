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
    ├── measure.py              # --measure: pixel coords → suggested profile patch (no rendering, no pipeline)
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
     `gap`), **red** = the actual saved crop (after trim), each labeled by
     row/col (and card number, for a front page).
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
   included. For a single stubborn card, `--inspect` (below) gives a much
   closer look than the full-page overlay.
5. If your deck's back page uses a different grid than the fronts, run
   `--overlay --page <back_page>` to check the back grid directly (see
   "Overlay and inspect" below) instead of round-tripping through a full
   export.
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

## Measuring a new deck fast (`--measure`)

Starting a profile from `0`s and iterating blind against
`calibration_overlay.png` works, but it can take many guess-render-look
cycles to converge. `--measure` skips the guessing: give it pixel
coordinates you read directly off an already-rendered image (from
`--preview` or `--overlay`), and it converts them back into PDF points
and prints the `left`/`top`/`card_width`/`card_height`/`gap_x`/`gap_y`
values that would produce them — usually enough for the very first
`--preview` to already land close.

It does **not** render, crop, export, or touch your profile file — it's
pure arithmetic over numbers you already have, kept deliberately outside
the crop/export pipeline. It only ever prints a suggestion.

1. Render a page you don't have a profile for yet (or a rough one), e.g.
   ```bash
   python extract.py --profile your_deck --overlay
   ```
   and open `preview/calibration_overlay.png` in any image viewer that
   shows pixel coordinates on hover (e.g. GIMP, Photoshop, `ImageMagick
   display`, or your OS's default viewer if it has a coordinate readout).
2. Hover the top-left and bottom-right corners of one card's visible
   cell and note their pixel coordinates.
3. Run:
   ```bash
   python extract.py --profile your_deck --measure \
     --card r0c0:240,420,960,1360
   ```
   `r0c0` says this measurement is row 0, column 0; the four numbers are
   the cell's top-left corner `(x1,y1)` and bottom-right corner
   `(x2,y2)`, in pixels. This alone is enough to derive `left`, `top`,
   `card_width`, and `card_height` (assuming `gap_x`/`gap_y` are 0, or
   whatever the profile currently has).
4. To also derive `gap_x`/`gap_y`, measure a second card in a different
   row and/or column and pass a second `--card`:
   ```bash
   python extract.py --profile your_deck --measure \
     --card r0c0:240,420,960,1360 \
     --card r0c1:1000,420,1720,1360
   ```
   Two cards in the same row (different column) derive `gap_x`; two in
   the same column (different row) derive `gap_y`; a diagonal pair
   derives both at once.
5. `--measure` prints an old-value → new-value patch listing, e.g.:
   ```
   Suggested patch for profiles/your_deck.json:
     "left": 0.000 -> 60.000
     "top": 0.000 -> 105.000
     "card_width": 0.000 -> 180.000
     "card_height": 0.000 -> 235.000
     "gap_x": 0.000 -> 10.000
     "gap_y": 0.000  (unchanged -- not enough points to derive; add a second --card in a different row/col)
   ```
   Copy the values you want into `profiles/your_deck.json` by hand, then
   run `--preview` to check them against the real crop — `--measure`
   gets you close, but `trim_*` (shaving a border/cut-line) still needs
   the usual visual check, since it's a stylistic choice, not something
   derivable from a card's outer edges.
6. Pass `--page` to measure against the back page's grid instead (only
   meaningful if the back page uses `back_*` overrides — see "Front/back
   grids can differ" above):
   ```bash
   python extract.py --profile your_deck --measure --page 8 \
     --card r0c0:100,100,500,700
   ```
   When `--page` matches the profile's `back_page`, the suggested patch
   uses `back_left`/`back_top`/`back_card_width`/`back_card_height`/
   `back_gap_x`/`back_gap_y` instead of the front fields.

## Overlay and inspect (fine-tuning a profile)

`--preview` covers the common case (check the first front page, adjust,
repeat), but two more targeted commands help once you're down to small
adjustments or a single problem card:

- **`--overlay`** renders one page — by default `first_front_page` — with
  every crop rectangle drawn over it (same blue/red convention as
  `--preview`) and writes it to `preview/calibration_overlay.png`. Pass
  `--page` to check a different page instead, most usefully the deck's
  `back_page`:

  ```bash
  python extract.py --profile solo_cards --overlay
  python extract.py --profile solo_cards --overlay --page 8
  ```

  This is the same overlay `--preview` writes, just without also having
  to re-crop and rebuild a contact sheet — use it when you only want to
  re-check rectangle placement, especially for the back page, which
  `--preview` doesn't cover.

- **`--inspect CARD_NUM`** exports one card at high zoom, with the raw
  cell (blue) and trimmed crop (red) boundaries drawn and a margin of
  surrounding page content left visible, so you can see exactly what a
  trim value is keeping or cutting off. `CARD_NUM` is 1-indexed and
  matches the numbering `--export` uses for `front_NNN.png`:

  ```bash
  python extract.py --profile solo_cards --inspect 1
  # → preview/inspect_card001.png
  ```

  Use this when the full-page overlay is too small to tell whether a red
  box is 1-2pt off, or to check one specific card (e.g. the last one on a
  page, in case of cumulative drift) without re-rendering the whole page.

## Commands

```bash
python extract.py --profile solo_cards --preview
# → preview/calibration_overlay.png, preview/page2_preview.png

python extract.py --profile solo_cards --export
# → output/front_001.png ... output/front_054.png, output/back.png

python extract.py --profile solo_cards --contact-sheet
# → preview/contact_sheet.png

python extract.py --profile solo_cards --overlay [--page N]
# → preview/calibration_overlay.png (defaults to first_front_page)

python extract.py --profile solo_cards --inspect CARD_NUM
# → preview/inspect_card{CARD_NUM:03d}.png

python extract.py --profile solo_cards --measure --card r0c0:X1,Y1,X2,Y2 [--card rRcC:X1,Y1,X2,Y2] [--page N]
# → prints a suggested left/top/card_width/card_height/gap_x/gap_y patch; writes nothing
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
