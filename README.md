# DeckForge

Turn a print-and-play PDF into individual card images, ready to import
into platforms like PlayingCards.io or Tabletop Simulator.

## Current Status

DeckForge is a **Windows alpha desktop application, under active
development.** The core workflow — open a PDF, calibrate its card grid,
review, and export — is complete and has been manually tested end to
end against real decks. It isn't packaged as an installer yet (run it
from source), and some hardening work (crash logging, export-reliability
edge cases, version identity) is still in progress. See
[docs/RELEASE_READINESS.md](docs/RELEASE_READINESS.md) for the current,
live list of what's shipped and what's still open.

## What DeckForge does

Print-and-play PDFs lay out a deck's card fronts — and often a shared
back — as a fixed grid on one or more pages. DeckForge lets you show it
exactly where that grid is, by clicking two corners of one card, and it
slices every card out as its own image file for a tabletop gamer to
import into a virtual tabletop.

Calibration is manual by design: PnP PDFs vary wildly in margins, bleed,
and cut-line placement, and a wrong automatic guess would silently
produce bad crops. A grid you calibrated once by eye — and can preview
before anything is written to disk — is trustworthy and reproducible.

## Screenshots

_Screenshots will be added as the alpha UI stabilizes._

## Getting started

Requirements: Python 3.10+ (3.12 recommended).

```bash
git clone <repo-url> deckforge
cd deckforge
pip install -r requirements-gui.txt
python gui_app.py
```

Drop a PDF onto the window (or use the bundled sample deck — see below)
and follow the guided steps in the sidebar. Each step tells you what to
do next and when you're ready to move on; you can always come back to an
earlier step later.

## The workflow

DeckForge walks you through six steps, in order:

1. **Deck** — open a PDF (drag-and-drop or file picker).
2. **Select Card Pages** — mark which pages contain card fronts, and
   which page, if any, is a shared back used by every card in the deck.
3. **Fronts** (Calibrate) — click a card's upper-left and lower-right
   corners to teach DeckForge the grid. Zoom, pan, and a crosshair guide
   help you land the click precisely, and a hint highlights where the
   next card is likely to be.
4. **Shared Back** (Calibrate) — the same click-to-measure step, for the
   back design, if your deck has one.
5. **Review Cards** — every card DeckForge suggests is shown as a
   thumbnail, so you can catch a miscount or a bad crop before anything
   is written to disk.
6. **Export** — writes each card front and the shared back as its own
   PNG file to a folder you choose, and warns before overwriting
   anything already there.

If a click is genuinely ambiguous — for example, a wide gap between
cards could plausibly mean two different grid sizes — DeckForge asks you
to confirm which card you meant instead of silently guessing.

## Included sample deck

`sample_decks/Solo-cards-digital.pdf` is a 54-card solo-RPG oracle deck:
page 1 is instructions, pages 2–7 are fronts (a 3×3 grid, 54 cards
total), and page 8 is the back — one shared back design for the whole
deck. It's a quick way to try the full workflow before calibrating your
own deck.

## Advanced: scripting via the CLI

The same engine that powers the GUI is also available as a command-line
tool (`extract.py`), useful for headless or scripted calibration, batch
processing, or automation. See
[docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) for the full command and
profile reference.

## Project documentation

### Product

- [docs/CORE_CONCEPTS.md](docs/CORE_CONCEPTS.md) — the vocabulary and
  concepts behind the workflow

### User Experience

- [docs/ui/DESIGN_PRINCIPLES.md](docs/ui/DESIGN_PRINCIPLES.md)
- [docs/ui/UI_DECISIONS.md](docs/ui/UI_DECISIONS.md)
- [docs/ui/DESIGN_SYSTEM.md](docs/ui/DESIGN_SYSTEM.md)

### Engineering

- [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md)
- [DEVELOPER.md](DEVELOPER.md) — project setup, architecture, and how to
  work on the code
- [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) — full CLI command and
  profile-JSON reference
- [docs/RELEASE_READINESS.md](docs/RELEASE_READINESS.md) — the live
  status board: what's shipped, what's open, before alpha ships

## Roadmap

Remaining work before DeckForge leaves alpha (see
[docs/RELEASE_READINESS.md](docs/RELEASE_READINESS.md) for the full,
prioritized, and current list):

- Export reliability hardening (background-thread race conditions, safe
  shutdown mid-export)
- Crash and error logging
- Release versioning
- A real installer/packaged build (currently run from source)

Further out, and not yet started: automatic grid/edge detection,
exporting directly to a PlayingCards.io or Tabletop Simulator package,
and support for multiple saved deck profiles browsed from within the
app.

## Contributing

See [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md) for the
project's engineering priorities and definition of done, and
[DEVELOPER.md](DEVELOPER.md) to get a development environment running.
