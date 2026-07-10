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

## Where to start

New to DeckForge? Run:

```bash
python extract.py --profile your_deck --calibrate
```

Every command prints what to run next once it finishes, so following that
trail — `--calibrate` → `--preview` → `--export` → `--contact-sheet` — is
enough to go from a blank profile to an imported deck without reading the
rest of this file. Everything below is the reference for when you want
more detail on a specific step.

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
back page shares the front grid exactly. Any field left unset falls back
to the **first layout's** geometry -- for a single-layout (or legacy)
profile that's simply "the front grid"; a profile with more than one
layout that needs a distinct back geometry should set the overrides
explicitly rather than relying on the fallback.

The bundled `solo_cards.json` profile actually needs this: its back page
cards are smaller and inset within their cell, while the fronts are
edge-to-edge.

## Profiles

Every deck gets its own JSON file in `profiles/`. Required fields, common
to every profile regardless of which front-grid form it uses (below):

| Field | Meaning |
|---|---|
| `pdf_file` | Filename to look for in `sample_decks/` (or the project root) |
| `back_page` | 1-indexed page containing the card back(s) |
| `trim_left/right/top/bottom` | Inward crop, in points (see "Trim scope" below for what this governs) |
| `render_scale` | Points-to-pixels multiplier for output resolution (e.g. `4` ≈ 288 DPI) |

Optional: `back_left`, `back_top`, `back_card_width`, `back_card_height`,
`back_gap_x`, `back_gap_y` (see "Front/back grids can differ" below).

### The front grid: legacy fields or `layouts`

A profile describes its card-front grid(s) one of two ways -- pick one,
not both:

**Legacy flat fields** (what every profile used before multi-layout
support, and still the simplest choice for a single-grid deck):

| Field | Meaning |
|---|---|
| `first_front_page`, `last_front_page` | 1-indexed, contiguous page range containing card fronts |
| `rows`, `cols` | Grid size per page |
| `left`, `top` | Top-left corner of card (row 0, col 0), in points |
| `card_width`, `card_height` | Size of one card cell, in points |
| `gap_x`, `gap_y` | Space between cells, in points (0 = edge-to-edge) |

**`layouts`** -- a list of one or more grids, each tied to its own
contiguous page range, for a deck that has more than one card shape/size
(e.g. a small "boss card" layout living on different pages from the main
deck):

```json
"layouts": [
  {
    "name": "Main deck",
    "first_page": 2, "last_page": 7,
    "rows": 3, "cols": 3,
    "left": 35.75, "top": 61.25,
    "card_width": 174.58, "card_height": 239.75,
    "gap_x": 0, "gap_y": 0,
    "trim_left": 2, "trim_right": 2, "trim_top": 2, "trim_bottom": 2
  },
  {
    "name": "Boss cards",
    "first_page": 9, "last_page": 9,
    "rows": 2, "cols": 2,
    "left": 40, "top": 60,
    "card_width": 200, "card_height": 260,
    "gap_x": 5, "gap_y": 5,
    "trim_left": 2, "trim_right": 2, "trim_top": 2, "trim_bottom": 2
  }
]
```

`name` is optional and purely for readability in calibration/measure
output; layouts without one are labeled `layout 1`, `layout 2`, etc. in
profile order. Each layout carries its own `trim_left/right/top/bottom`
-- there is no shared front trim once a profile uses `layouts`.

Layouts are processed in **profile order** (the order they appear in the
JSON list, not sorted by page number), pages ascending within a layout,
and cards row-major within a page -- this determines `front_NNN.png`
numbering, which is continuous across every layout in the profile.

Front page ranges across all layouts must not overlap each other, and
`back_page` must not fall inside any layout's range. A page that belongs
to neither a layout nor `back_page` is unassigned; running a command
against it (e.g. `--overlay --page 12`) fails with a clear error instead
of guessing.

**Contiguous ranges only.** Each layout is exactly one `first_page`..
`last_page` range -- there's no separate list of individual page numbers.
A deck whose front pages for one card shape aren't contiguous (e.g. pages
2-4 and 9 use the same grid) can express that today as **two layout
entries with identical geometry**, one per contiguous range:

```json
"layouts": [
  { "name": "Main (part 1)", "first_page": 2, "last_page": 4, "...": "..." },
  { "name": "Main (part 2)", "first_page": 9, "last_page": 9, "...": "..." }
]
```

An explicit non-contiguous page list is deferred to a future phase, once
there's a real deck that needs it badly enough to justify the extra
schema/validation/GUI surface.

### Trim scope: one unavoidable distinction

`back_page` is deliberately **not** a layout -- DeckForge has exactly one
shared back, and folding it into `layouts` would blur what a `CardLayout`
means (a grid of card fronts). Since the back isn't a layout, its trim
still needs to come from somewhere:

- **Legacy profiles** (no `layouts`): the top-level `trim_left/right/top/
  bottom` fields govern **both** the (single, normalized) front layout
  and the back page, exactly as before multi-layout support existed.
- **`layouts` profiles**: each layout owns its own front trim, so the
  top-level `trim_left/right/top/bottom` fields apply to the **back page
  only**.

This is the one place a legacy profile and a `layouts` profile behave
differently. Phase I deliberately does not introduce a separate
`back_trim_*` schema or otherwise redesign back-page trimming -- the
existing top-level trim fields are reused, just with their scope
narrowed to "back only" once a profile opts into `layouts`.

## Calibrating a new deck

New to DeckForge? Start with `--calibrate` (below) instead — it walks you
through the same measurements interactively, one click at a time, with no
pixel-reading by hand. The steps below are the fully manual fallback (also
useful once you understand the fields and just want to nudge a value).

1. Drop the PDF in `sample_decks/`, create `profiles/your_deck.json` with
   your best-guess numbers (or zeros to start).
2. Run:
   ```bash
   python extract.py --profile your_deck --preview
   ```
   This renders **only** the first page of the first layout (for a legacy
   profile, that's just `first_front_page`), crops its cards, and writes
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
   This assumes every page within a layout's `[first_page, last_page]`
   range shares that layout's grid. If a real PDF has per-page drift
   (rare, but possible with hand-assembled PnP sheets), you'll need to
   spot check a few more pages, or split the affected range into its own
   layout (or profile).
7. QA everything at once:
   ```bash
   python extract.py --profile your_deck --contact-sheet
   ```
   Writes `preview/contact_sheet.png` with every exported front (in
   order) plus the back, so you can scan the whole deck before importing.

   **Known limitation:** the contact sheet resizes every thumbnail to the
   same box, sized from the first image's aspect ratio. For a
   single-layout deck (or several layouts sharing one card aspect ratio)
   this is invisible. A profile whose layouts use genuinely different
   card aspect ratios (e.g. square "boss cards" mixed with standard
   portrait cards) will see those thumbnails visibly stretched or
   squashed in the contact sheet, even though the actual exported PNGs in
   `output/` are correct and unaffected -- only the QA sheet's rendering
   is off. Fixing this (e.g. per-image aspect-preserving thumbnails) is
   deferred; `contact_sheet.py` is unchanged in this milestone.

## Interactive calibration (`--calibrate`)

The fastest way to calibrate a new deck: click on the rendered page instead
of reading pixel coordinates off an image viewer. Run:

```bash
python extract.py --profile your_deck --calibrate
```

This opens a window showing the deck's first front page (pass `--page N`
for a different page, e.g. to calibrate the back grid) and walks you
through three steps:

1. **Mark a card.** Click a card's upper-left corner, then its
   lower-right corner. DeckForge assumes this first card is `r0c0` (the
   grid's top-left card).
2. **Add spacing (optional).** Once one card is measured, DeckForge
   highlights where a neighboring card is likely to be — click it to also
   work out the gap between cards, or click **Finish** to skip straight to
   step 3 with card size only.
3. **Finish up.** The window confirms calibration is complete and gives
   you a **Copy Calibration Settings** button. Paste the values into
   `profiles/your_deck.json` by hand, then run `--preview` to check them
   against the real crop — just like the manual workflow above,
   `--calibrate` never writes to the profile file itself. The same
   old-value → new-value patch `--measure` prints (see below) is there
   too, tucked behind a **Technical Details (Optional)** toggle for
   anyone who wants to see the raw numbers.

Use **Start Over** at any point to clear both measured corners and start
over on the same page. The status line above the image always says what
to click next and why; the window is done once it says "Step 3 of 3."

The calibration window is resizable, and the image view expands to fill it:
maximizing the window (or dragging it larger) gives you a bigger view of the
page, not more blank space around a fixed-size image. Shrinking the window
shrinks the view the same way. The image is never stretched — its aspect
ratio is always preserved, with any leftover space on one axis left empty
around it.

### Zooming and panning for precise clicks

High-resolution PDF pages get shrunk a lot to fit on screen, which can make
it hard to land a click exactly on a corner. The calibration window can be
zoomed and panned to get a closer look — this only changes what you see, it
never changes the calibration values a click produces:

- **Scroll** over the area you want to inspect to zoom in or out. Zoom
  stays centered on wherever your mouse is, so scrolling in on a corner
  brings that corner closer instead of the view jumping around.
- **Pan.** Click the **Pan** button, then left-drag to move around the
  page — the most discoverable way to move around, and the recommended
  one if you're not used to the shortcuts below. Left-clicking while Pan
  is off makes a calibration mark as usual; Pan never does. Click **Pan**
  again, or press **Escape**, to go back to normal clicking.
- **Hold Spacebar and drag** with the left mouse button to move around the
  page without leaving Pan mode on — handy for a quick nudge mid-click.
  Middle-mouse-button drag also works, if your mouse has one.
- **Fit to Window** returns to the full-page view, recalculated for
  however large the window currently is; **100%** shows the page at its
  original rendered resolution (useful for checking fine detail). The
  current zoom level is shown next to these buttons.
- **Start Over** clears your measurements but keeps your current
  zoom/pan view and Pan selection, so you can retry a mis-click without
  losing your place.

Panning and Pan mode only change what you're looking at — they never
affect a calibration value. Clicking the same two corners produces the
same calibration values no matter how zoomed in, panned, or resized the
window is when you click them.

### Crosshair

The **Crosshair** button (next to Pan) draws a thin horizontal and
vertical guide line through the mouse pointer, spanning the full canvas.
It's on by default and helps line up a corner precisely — especially
useful when a PDF's printed cut marks don't extend all the way across
the card, so you only have a short mark to align against instead of a
full edge. A small coordinate readout next to the zoom percentage shows
the pointer's position in the same rendered-image pixels the crop math
uses.

Click **Crosshair** to turn it off if you find it distracting. It's
purely a visual aid — like zoom and pan, it never changes a calibration
value, and it automatically gets out of the way while panning (Pan mode,
Spacebar-drag, or mid-drag) so it doesn't clutter the view while you're
moving the page.

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

- **`--overlay`** renders one page — by default the first page of the
  first layout — with every crop rectangle drawn over it (same blue/red
  convention as `--preview`) and writes it to
  `preview/calibration_overlay.png`. Pass `--page` to check a different
  page instead, most usefully the deck's `back_page`, or any other
  layout's pages in a multi-layout profile:

  ```bash
  python extract.py --profile solo_cards --overlay
  python extract.py --profile solo_cards --overlay --page 8
  ```

  This is the same overlay `--preview` writes, just without also having
  to re-crop and rebuild a contact sheet — use it when you only want to
  re-check rectangle placement, especially for the back page, which
  `--preview` doesn't cover. `--page` with a page that belongs to neither
  a layout nor `back_page` fails with a clear "not assigned" error rather
  than guessing which grid to use.

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
# → preview/calibration_overlay.png (defaults to the first layout's first page)

python extract.py --profile solo_cards --inspect CARD_NUM
# → preview/inspect_card{CARD_NUM:03d}.png

python extract.py --profile solo_cards --measure --card r0c0:X1,Y1,X2,Y2 [--card rRcC:X1,Y1,X2,Y2] [--page N]
# → prints a suggested left/top/card_width/card_height/gap_x/gap_y patch; writes nothing
```

All front cards **within one layout** are guaranteed to come out at
identical pixel dimensions (the crop math rounds card size once and
reuses it for every cell, so per-card rounding drift can't sneak in a 1px
difference — a real bug caught while building this). Different layouts
in the same profile may use different card sizes.

`--export` finishes with a plain-language summary — how many card fronts
and backs were produced, their pixel size, where the files landed, and
that they're ready to import into platforms like PlayingCards.io or
Tabletop Simulator — followed by a suggestion to run `--contact-sheet` as
a final visual check.

## If something goes wrong

Every error DeckForge can anticipate (a missing profile, invalid JSON, a
PDF that isn't where the profile says, trim values that collapse a card
to nothing, a malformed `--card` spec, …) prints a one- or two-line
plain-language explanation of the likely cause and what to try next,
followed by `Details:` with the underlying technical message — keep
reading past the first lines if you need the exact value or field name.
Anything DeckForge doesn't have a specific explanation for (a bug, or an
unusual PDF) still exits cleanly with a short notice and the full
technical detail, instead of a raw crash.

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
- Explicit non-contiguous page lists per layout (today's workaround: two
  layout entries with identical geometry — see "The front grid" above)
- Aspect-ratio-aware contact sheet thumbnails, for profiles whose
  layouts mix card aspect ratios (see "Known limitation" under
  "Calibrating a new deck")
- Multiple backs, group-aware output filenames, and mixed card sizes
  within a single page remain out of scope, independent of `layouts`
