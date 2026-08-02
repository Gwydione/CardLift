# CardLift Core Concepts

## Purpose

This document defines the core concepts of CardLift.

These concepts describe the user's world rather than the implementation.
The engine, GUI, and future features should all use this shared
vocabulary whenever practical.

The goal is to keep the application organized around concepts that are
meaningful to users instead of internal implementation details.

CardLift exists to understand one or more printable tabletop decks contained within a source document. Every workflow step contributes to building that understanding so the deck(s) can be accurately previewed and exported.

Core concepts should remain relatively stable over time. Features,
workflows, and implementations may evolve, but these concepts define the
language of CardLift and should change only when the understanding of
the problem domain itself changes.

---

# PDF

A PDF is the source document provided by the user.

A PDF contains one or more pages.

CardLift never modifies the original PDF.

---

# Page

A page is a single page within a PDF.

Pages may contain:

- cards
- instructions
- artwork
- cover pages
- reference material
- or any other printable content

Only pages containing cards participate in the extraction workflow.

---

# Card Page

A **Card Page** is any PDF page containing one or more printable cards.

Card Pages are identified during the **Select Card Pages** workflow.

At this stage, CardLift does **not** distinguish between front pages,
back pages, decks, or card arrangements.

The only question being answered is:

> **Does this page contain cards?**

---

# Deck

A **Deck** is a logical collection of related cards.

A Deck is the primary object users create and work with inside
CardLift.

A Deck is also the primary object CardLift seeks to understand.

A Deck owns:

- its Card Pages
- a Back Mode
- calibration
- preview
- export settings

The initial implementation supports a single Deck.

Future versions may support multiple Decks within a single PDF.

---

# Front Pages

Front Pages are the Card Pages containing the printable faces of a Deck.

A Deck may contain one or more Front Pages.

The initial implementation assumes all Front Pages within a Deck share
the same card arrangement.

Future versions may support multiple card arrangements within a single
Deck.

See Back Pages, below, for the reverse side of a Deck's cards.

---

# Back Pages

**Back Pages** are the Card Pages containing the reverse side of a
Deck's cards.

A Deck may have no Back Pages, one Back Page, or many Back Pages.

Not every Deck has Back Pages. Some cards are printed front-only.

---

# Back Mode

**Back Mode** is how a Deck's Back Pages relate to its Front Pages.

CardLift supports three Back Modes:

- **Front Only** — the Deck has no Back Pages. No back is exported.
- **Shared Back** — the Deck has exactly one Back Page. Its artwork is
  used as the reverse side for every card in the Deck.
- **Paired Back Pages** — the Deck has one Back Page for every Front
  Page. Every card has its own, unique reverse side, paired with the
  Front Page it appears on.

Back Mode is a property of the Deck, not a setting the user configures
directly. Whenever possible, CardLift derives it from how many pages
the user has marked as Back Pages: none means Front Only, one means
Shared Back, more than one means Paired Back Pages.

Exactly one Back Page is the one case count alone cannot resolve — it
could be a Shared Back, or a Deck whose Front and Back Pages both
happen to be a single page each, but where every card still has its own
unique reverse (a one-page Paired Back Pages Deck). CardLift asks the
user to choose explicitly only in this one case, rather than
introducing a general mode selector every Deck would otherwise have to
answer. See
[docs/design/MULTIPLE_BACK_MODES.md](design/MULTIPLE_BACK_MODES.md) for
the full behavior, including this ambiguity and its resolution.

Back Mode is established during **Select Card Pages** and, once set,
shapes what later workflow steps do without those steps determining or
storing it themselves:

- **Calibration** measures a representative Back Page only when the
  Deck has one (see Calibration, below).
- **Preview** shows each card's paired back alongside its front when the
  Deck's Back Mode is Paired Back Pages.
- **Export** produces one back image per card, one shared back image,
  or no back image at all, depending on Back Mode.

---

# Calibration

Calibration teaches CardLift how to interpret a Deck.

Calibration belongs to a Deck rather than to the PDF itself.

The current workflow measures:

- one representative front card
- one representative back card, if the Deck has Back Pages -- that one
  measurement applies to every Back Page, whether there is a single one
  (Shared Back) or one per Front Page (Paired Back Pages)

Future versions may calibrate multiple card arrangements as needed.

---

# Preview

Preview allows users to verify that CardLift correctly understands a
Deck before extraction.

Preview is intended to build confidence and catch mistakes before files
are generated.

---

# Export

Export generates the final extracted assets for a Deck.

The export process should faithfully represent the calibrated Deck while
preserving the original PDF.

---

# Card Arrangement

A **Card Arrangement** describes how cards are positioned on one or more
pages.

Card Arrangements are an implementation concept rather than a primary
user concept.

Whenever practical, the user interface should communicate in terms of
Decks rather than Card Arrangements.

---

# Guiding Principle

CardLift should model the user's understanding of their document rather
than exposing internal implementation details.

Users think in terms of:

- PDFs
- Pages
- Card Pages
- Decks
- Back Mode

The software may internally use card arrangements, geometry, calibration
targets, page ranges, or other implementation details, but those
concepts should remain internal whenever practical.
