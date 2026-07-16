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
- optional Shared Back(s)
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

---

# Shared Back

A **Shared Back** is an optional Card Page whose artwork is used as the
reverse side for every card in a Deck.

Some Decks contain a Shared Back.

Some Decks do not.

Future versions may support multiple Shared Back groups.

---

# Calibration

Calibration teaches CardLift how to interpret a Deck.

Calibration belongs to a Deck rather than to the PDF itself.

The current workflow measures:

- one representative front card
- one representative shared back card (if present)

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

The software may internally use card arrangements, geometry, calibration
targets, page ranges, or other implementation details, but those
concepts should remain internal whenever practical.
