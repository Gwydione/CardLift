# Multiple Back Modes

**Status:** Draft

**Target:** v0.2.0-alpha

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

CardLift currently supports two workflows:

-   Front Only
-   Shared Back

This covers the majority of traditional print-and-play card decks.

However, some games contain cards where every card has a corresponding
reverse side.

Today these decks cannot be represented by CardLift.

------------------------------------------------------------------------

# Design Goals

## Preserve simplicity

The existing workflow should remain recognizable.

``` text
Select Card Pages
        ↓
Calibrate
        ↓
Review Cards
        ↓
Export
```

Supporting additional back modes should not require introducing
additional workflow steps unless absolutely necessary.

## Preserve CardLift's philosophy

The user should answer as few questions as possible.

Whenever CardLift can safely determine a relationship automatically, it
should.

## Preserve backward compatibility

Existing projects using:

-   Front Only
-   Shared Back

must continue to function exactly as they do today.

No migration should be required.

------------------------------------------------------------------------

# Back Modes

CardLift should support three deck types.

## Front Only

Cards contain only a front image.

No back assets are exported.

## Shared Back

All front cards share one common reverse side.

Current behavior.

No changes expected.

## Paired Back Pages

Each front page has one corresponding back page.

Each card on the front page has one corresponding card on the paired
back page.

Unlike Shared Back mode, every card may have a different reverse side.

------------------------------------------------------------------------

# Initial Assumptions

The first implementation intentionally limits scope.

Version 0.2 assumes:

-   Front and back pages contain identical grid dimensions.
-   Matching cards occupy the same row and column position.
-   Every paired page contains the same number of cards.
-   Front page N pairs with Back page N.
-   Pairing occurs automatically.
-   Users do not manually pair individual cards.

These assumptions intentionally solve a significant real-world use case
while keeping the workflow simple.

------------------------------------------------------------------------

# Export

Current Shared Back export

``` text
front001.png
front002.png
...
back.png
```

Proposed Paired Back export

``` text
001_front.png
001_back.png

002_front.png
002_back.png
```

The exported files remain platform-agnostic.

CardLift continues producing digital assets rather than
platform-specific packages.

------------------------------------------------------------------------

# Review Cards

Current behavior reviews only front cards.

The preferred long-term direction is that Review Cards represents
complete cards rather than only front images.

Whether the initial implementation shows paired fronts and backs
together remains an implementation decision.

------------------------------------------------------------------------

# Future Compatibility --- Multiple Decks

Some PDFs contain more than one logical deck or asset group.

Examples include:

-   multiple independent card decks
-   encounter and item decks
-   cards and tokens
-   decks with different back behaviors

Multiple Deck support is intentionally outside the scope of this
feature.

However, this implementation should avoid assuming that one PDF always
represents one homogeneous deck.

Conceptually:

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

Version 0.2 may expose only one deck.

Future versions may expose several independently configured decks.

This feature should preserve that architectural direction without
implementing it.

------------------------------------------------------------------------

# Explicit Non-Goals

The initial implementation will not support:

-   manual card pairing
-   arbitrary card matching
-   mirrored layouts
-   rotated layouts
-   image recognition
-   automatic artwork matching
-   print layout generation
-   printing workflows

If a deck falls outside the supported assumptions, CardLift should
clearly communicate that the layout is not currently supported.

------------------------------------------------------------------------

# Open Design Questions

The following questions remain intentionally unresolved.

-   Should paired cards be reviewed together?
-   How should unsupported layouts be detected?
-   Should exported filenames become configurable?
-   How should future multiple-back-group support relate to paired
    pages?
-   What is the cleanest internal representation of Back Mode?

These questions should be answered during implementation design.

------------------------------------------------------------------------

# Success Criteria

A user can process a deck containing paired front and back pages without
manually pairing individual cards.

The resulting workflow should feel like a natural extension of CardLift
rather than a separate feature.

------------------------------------------------------------------------

# Why This Feature Exists

CardLift's purpose is not simply to extract images from PDFs.

Its purpose is to understand cards.

Supporting Paired Back Pages is another step toward representing the
complete structure of a card rather than only its front image.

This architectural direction enables richer digital tabletop workflows
while remaining faithful to CardLift's guiding principle:

**Keep the workflow simple.**
