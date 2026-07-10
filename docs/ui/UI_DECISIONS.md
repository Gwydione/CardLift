# DeckForge UI Decisions

This document records intentional user experience decisions made during
the design of DeckForge's desktop application.

Its purpose is to preserve *why* decisions were made so future
development remains consistent.

------------------------------------------------------------------------

# Workflow

The primary workflow is:

1.  Deck
2.  Find Cards
3.  Calibrate
4.  Review Cards
5.  Export

The sidebar reflects the user's workflow rather than the engine's
internal architecture.

------------------------------------------------------------------------

# Sidebar

## Navigation

-   Deck
-   Find Cards
-   Calibrate
    -   Cards
    -   Shared Back
-   Review Cards
-   Export

Review Cards replaces "Check Cards" because it communicates confidence
rather than error checking.

Completed steps should display a subtle completion indicator.

Future steps remain visible but muted.

------------------------------------------------------------------------

# Layout

-   Fixed-width workflow sidebar.
-   Large, expanding center workspace.
-   Narrow, collapsible guidance panel.
-   Persistent toolbar above the workspace.
-   Minimal top bar.
-   Status bar along the bottom.

Whenever additional window space is available, it should be given to the
PDF workspace.

------------------------------------------------------------------------

# Top Bar

The top bar remains intentionally minimal.

It contains:

-   DeckForge branding
-   Overflow/settings menu

The current PDF filename should not occupy permanent space in the top
bar.

------------------------------------------------------------------------

# Toolbar

The toolbar should only expose controls relevant to the current
workspace.

For calibration, the initial toolbar consists of:

-   Fit
-   Zoom Out
-   Zoom Percentage
-   Zoom In
-   Pan

Reference lines remain enabled by default and are not exposed as a
toolbar toggle.

------------------------------------------------------------------------

# Guidance Panel

The guidance panel provides concise, contextual instructions.

It should:

-   remain secondary to the PDF
-   be collapsible
-   use short, task-oriented language
-   avoid technical terminology

Preferred wording:

"Show DeckForge the first card."

Avoid wording that implies training or configuration complexity.

------------------------------------------------------------------------

# Pan Mode

Pan mode must always be obvious.

Indicators include:

-   highlighted Pan button
-   cursor changes
-   status bar message
-   Escape exits persistent Pan mode

------------------------------------------------------------------------

# Language

Prefer user-oriented language.

Examples:

-   Find Cards
-   Review Cards
-   Show DeckForge the first card

Avoid exposing implementation concepts such as JSON, profile
normalization, crop geometry, or command-line terminology.

------------------------------------------------------------------------

# Open Questions

The following topics intentionally remain open until validated through
prototype testing:

-   Final visual theme and typography
-   Keyboard shortcut set
-   Compact sidebar mode for smaller displays
-   Review Cards layout
-   Export workspace layout
-   Future support for multiple layouts and profile management

These should be resolved through iterative testing rather than
speculation.
