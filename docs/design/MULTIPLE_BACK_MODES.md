# Multiple Back Modes

**Status:** Implemented (v0.2.0-alpha)

> This document describes how Multiple Back Modes works today. For the
> phase-by-phase implementation history, architecture decisions, and
> lessons learned behind it, see DEVELOPER.md's Multiple Back Modes notes.

------------------------------------------------------------------------

# Objective

Extend CardLift's card model to support additional back behaviors while
preserving the application's core philosophy:

> Transform print-and-play card PDFs into clean, organized image files
> suitable for virtual tabletops and digital play.

This feature is not intended to improve printing workflows.

It exists to support digital platforms where individual cards may have
unique reverse sides.

------------------------------------------------------------------------

# Background

CardLift previously supported two back configurations: Front Only and
Shared Back. This covered most traditional print-and-play decks, but not
games where every card has a unique reverse side -- those decks could
not be represented at all.

Paired Back Pages closes that gap.

------------------------------------------------------------------------

# Design Goals

## Preserve simplicity

The existing workflow remains recognizable:

``` text
Select Card Pages
        ↓
Calibrate
        ↓
Review Cards
        ↓
Export
```

No additional workflow steps were introduced.

## Preserve CardLift's philosophy

The user answers as few questions as possible.

Pairing between Front and Back pages happens automatically. CardLift
only asks a direct question when it genuinely cannot tell what the user
means on its own (see "The one-page case" below).

## Preserve backward compatibility

Existing Front Only and Shared Back projects continue to work exactly
as they did before.

No migration is required, and no existing deck's behavior changed as a
result of this feature.

------------------------------------------------------------------------

# Back Modes

CardLift supports three deck types.

## Front Only

Cards contain only a front image.

No back assets are exported.

## Shared Back

All front cards share one common reverse side.

CardLift's original, most common back configuration.

## Paired Back Pages

Each marked Front page has one corresponding marked Back page, and each
card on a Front page has a corresponding card on that page's paired Back
page.

Unlike Shared Back, every card can have a unique reverse side.

## The one-page case

Whether a deck uses Shared Back or Paired Back Pages is normally obvious
from how many pages are marked Back: zero means Front Only, two or more
means Paired Back Pages.

Exactly one marked Back page is genuinely ambiguous -- it could be a
Shared Back, or a one-page Paired Back deck (a full grid of unique
cards, all paired with that one Front page). When this happens, Select
Card Pages shows an explicit choice for which one it is. Shared Back is
the default, so every deck that previously had exactly one Back page
keeps behaving exactly as it always has unless the user chooses Paired.

------------------------------------------------------------------------

# Workflow

Multiple Back Modes fits into CardLift's existing four-step workflow
without adding a step.

**Select Card Pages.** Mark each page as Front or Back. CardLift
determines the deck's back mode from how many pages are marked Back,
prompting for an explicit choice only in the one ambiguous case above.
For Paired Back Pages, Continue is blocked until the Front and Back page
counts match.

**Calibrate.** Measure Front cards once, as always. For Shared Back,
measure the one shared back design. For Paired Back Pages, measure one
representative Back page the same way -- see "Calibration" below.

**Review Cards.** Confirm which suggested cards are real before
exporting -- see "Review Cards" below for how Paired Backs are shown.

**Export.** Save the confirmed cards as image files -- see "Export"
below for the resulting file set per back mode.

------------------------------------------------------------------------

# Calibration

Front cards are always calibrated the same way: a two-corner click on
one representative page, with an optional second click to measure the
gap between cards.

Paired Back Pages calibration works identically. The user calibrates one
representative Back page, not every Back page individually, and that
measurement applies to all of them -- the same way one Front measurement
already applies to every Front page.

Once both Front and Paired Back are calibrated, CardLift checks that
they describe the same grid shape: the same number of rows and columns
of cards. Margins, card size, and spacing may still differ between Front
and Back -- a back design can legitimately be printed with different
bleed or trim -- but the grid shape itself must match. If it doesn't,
CardLift asks the user to recheck their Back calibration rather than
guessing at a mismatched pairing.

This check compares the pages the user actually calibrated, not every
individual page in the deck. If a PDF mixes page sizes in a way that
changes the suggested grid on some pages but not others, the results are
still worth double-checking in Review Cards.

------------------------------------------------------------------------

# How Pairing Works

Front and Back pages are paired by position, not by page number: the
first marked Front page pairs with the first marked Back page, the
second with the second, and so on, in the order they appear in the PDF
-- not by matching literal page numbers.

Pairing happens automatically. There is no manual step for matching
individual cards or pages.

Every marked Front page must have a corresponding marked Back page. If
the counts don't match, CardLift says so and blocks Continue or Export
until they do -- it never guesses which pages should pair.

------------------------------------------------------------------------

# Review Cards

Review Cards shows the suggested front-card grid for every back mode,
unchanged from Front Only and Shared Back -- this is where the user
confirms which suggested cards are real and excludes any that aren't
(for example, blank space on a partly-filled page).

For Paired Back Pages, opening a card for a closer look also shows its
paired back side by side, so the user can confirm the pairing and crop
placement together, without a second full grid competing for space with
the front-card review. The two sides are resolved by the pairing rule
above and cropped using each side's own calibration.

If a deck's Front and Back page counts are unbalanced, or a paired back
can't be resolved for a specific card, CardLift shows this plainly
rather than silently leaving it out.

------------------------------------------------------------------------

# Export

Export writes the confirmed cards from Review Cards to individual PNG
files in a folder the user chooses. The filenames depend on the deck's
back mode.

Front Only:

``` text
front_001.png
front_002.png
...
```

Shared Back:

``` text
front_001.png
front_002.png
...
back.png
```

Paired Back Pages:

``` text
001_front.png
001_back.png
002_front.png
002_back.png
...
```

Paired Back Pages uses a different naming convention on purpose: pairing
each front and back by a shared number prefix means the two files for
one card sort next to each other in a file browser, rather than every
front followed by a single trailing `back.png`.

CardLift only exports a Paired Back deck once every included card has a
resolved paired back -- an unresolved or unbalanced pairing blocks
Export rather than producing an incomplete set of files.

Exported files remain plain PNGs, platform-agnostic, with no
printable-PDF or platform-specific packaging -- consistent with every
other CardLift export.

------------------------------------------------------------------------

# Non-Goals

Multiple Back Modes does not support:

-   manual card pairing
-   arbitrary card matching
-   mirrored or rotated layouts
-   image recognition or automatic artwork matching
-   print layout generation or printing workflows
-   configurable export filenames

If a deck falls outside what CardLift can pair automatically, CardLift
says so rather than guessing.

------------------------------------------------------------------------

# Future Compatibility --- Multiple Decks

Some PDFs contain more than one logical deck or asset group -- multiple
independent card decks, encounter and item decks, cards and tokens, or
decks with different back behaviors. Multiple Deck support is
intentionally outside the scope of this feature.

Multiple Back Modes does not assume a PDF always represents one
homogeneous deck:

``` text
PDF
    ↓
Deck
    ├── Selected Pages
    ├── Back Mode
    ├── Calibration
    ├── Review State
    └── Export
```

CardLift currently exposes only one deck per PDF. This structure is
preserved so that a future version could expose several independently
configured decks without requiring changes to how any single deck's
back mode works.

------------------------------------------------------------------------

# Success Criteria

A user can process a deck containing paired front and back pages without
manually pairing individual cards -- confirmed.

The resulting workflow feels like a natural extension of CardLift's
existing four steps, rather than a separate feature.

------------------------------------------------------------------------

# Why This Feature Exists

CardLift's purpose is not simply to extract images from PDFs.

Its purpose is to understand cards.

Supporting Paired Back Pages is another step toward representing the
complete structure of a card rather than only its front image.

This architectural direction enables richer digital tabletop workflows
while remaining faithful to CardLift's guiding principle:

**Keep the workflow simple.**
