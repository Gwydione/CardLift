# DeckForge UI Design Principles

## Purpose

DeckForge exists to help tabletop gamers transform Print-and-Play PDFs
into virtual tabletop-ready card images.

The engine performs sophisticated extraction, calibration, and export
operations. The purpose of the GUI is not to expose that complexity---it
is to make it disappear.

Every design decision should reinforce clarity, confidence, and ease of
use.

------------------------------------------------------------------------

# Product Philosophy

DeckForge should feel like a polished desktop application, not a
graphical interface layered on top of a command-line tool.

Users should think about **their deck**, not about how the engine works.

The interface should guide users naturally through the workflow while
keeping advanced capabilities available without overwhelming beginners.

**Above all, DeckForge should feel user-friendly, not technical.**

Users should focus on their cards and workflow---not on the extraction
engine.

------------------------------------------------------------------------

# Core Principles

## The PDF is the workspace.

The PDF is the center of the experience.

Whenever possible, additional screen space should be given to the PDF
viewport rather than surrounding panels.

The application exists to help users work with their cards.

## Guide, don't overwhelm.

Present the user with the next meaningful action.

Avoid exposing implementation details, configuration screens, or
advanced options until they are needed.

Simple workflows should require very few decisions.

## Every interaction should build confidence.

Each completed step should leave the user more confident than before.

The interface should continually communicate what DeckForge understands
and what will happen next.

Examples include:

-   pages selected
-   layouts detected
-   page assignments
-   card counts
-   visual overlays
-   review screens
-   clear readiness indicators

Users should never wonder whether the application understood their deck
or what will happen next.

## Don't punish experienced users.

New users should receive guidance.

Experienced users should be able to move quickly.

Examples include:

-   collapsible guidance panel
-   remembered preferences
-   keyboard shortcuts
-   large PDF workspace

## The current interaction mode must always be obvious.

Users should never wonder why clicking behaves differently.

Whenever the application enters a different interaction mode, it should
communicate that through multiple cues such as:

-   highlighted controls
-   cursor changes
-   status messages

## Progressive disclosure

Advanced functionality should remain available without dominating the
interface.

The common workflow should remain simple while allowing experienced
users to accomplish more complex tasks when necessary.

## The engine does the work. The GUI tells the user's story.

The GUI should not duplicate engine logic.

Instead, it should present the engine's capabilities through an
intuitive workflow that focuses on user goals rather than implementation
details.

# Product Voice

Use language that is:

-   clear
-   friendly
-   concise
-   confident

Avoid unnecessary technical terminology.

Prefer user-oriented language such as:

-   Find Cards
-   Review Cards
-   Show DeckForge the first card

Avoid exposing concepts such as:

-   JSON
-   profile normalization
-   crop geometry
-   internal engine terminology

# Visual Philosophy

The interface should feel calm, spacious, and intentional.

Whitespace is a design tool, not empty space.

The PDF workspace should dominate the application.

Navigation and guidance should support the workflow without competing
for attention.

Users should always know:

-   where they are
-   what DeckForge understands
-   what to do next

# Decision Filter

Before adding a feature, button, dialog, or option, ask:

1.  Does this help users accomplish their goal?
2.  Would a first-time tabletop gamer immediately understand it?
3.  Can the engine handle this automatically instead?
4.  Does this simplify or complicate the workflow?
5.  If removed, would most users miss it?

If the answer to the last question is "no," the feature probably does
not belong in the primary interface.

# One Guiding Thought

> **The purpose of the GUI is not to expose the engine's
> sophistication---it is to make it disappear.**
