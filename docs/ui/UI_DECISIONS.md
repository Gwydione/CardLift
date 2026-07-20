# CardLift UI Decisions

This document records intentional user experience decisions made during
the design of CardLift's desktop application.

Its purpose is to preserve _why_ decisions were made so future
development remains consistent.

---

# Workflow

The primary workflow is:

1.  Deck
2.  Select Card Pages
3.  Calibrate
4.  Review Cards
5.  Export

The sidebar reflects the user's workflow rather than the engine's
internal architecture.

---

# Sidebar

## Navigation

- Deck
- Select Card Pages
- Calibrate
  - Fronts
  - Shared Back
- Review Cards
- Export

Review Cards replaces "Check Cards" because it communicates confidence
rather than error checking.

Completed steps should display a subtle completion indicator.

Future steps remain visible but muted.

---

# Layout

- Fixed-width workflow sidebar.
- Large, expanding center workspace.
- Narrow, collapsible guidance panel.
- Persistent toolbar above the workspace.
- Minimal top bar.
- Status bar along the bottom.

Whenever additional window space is available, it should be given to the
PDF workspace.

---

# Top Bar

The top bar remains intentionally minimal.

It contains:

- CardLift branding
- Current version number

A future overflow/settings menu remains part of the design direction,
but the inactive placeholder control was removed in v0.1.1-alpha (no
Settings feature exists yet to attach it to).

The current PDF filename should not occupy permanent space in the top
bar.

---

# Toolbar

The toolbar should only expose controls relevant to the current
workspace.

For calibration, the initial toolbar consists of:

- Fit
- Zoom Out
- Zoom Percentage
- Zoom In
- Pan

Reference lines remain enabled by default and are not exposed as a
toolbar toggle.

---

# Guidance Panel

The guidance panel provides concise, contextual instructions.

It should:

- remain secondary to the PDF
- be collapsible
- use short, task-oriented language
- avoid technical terminology

Preferred wording:

"Show CardLift the first card."

Avoid wording that implies training or configuration complexity.

---

# Pan Mode

Pan mode must always be obvious.

Indicators include:

- highlighted Pan button
- cursor changes
- status bar message
- Escape exits persistent Pan mode
- on-canvas indicator (v0.1.1-alpha): the four indicators above all sit at
  the periphery of the window -- the toolbar above the canvas, the status
  bar at its bottom -- rather than where the user is actually looking
  right before they click or drag. An Alpha tester still found Pan mode
  unclear despite all four already being in place. A small badge drawn
  directly on the canvas (`_CalibrateCanvas._draw_pan_indicator()`),
  showing the same status-bar wording, closes that gap without adding a
  new control; it appears and disappears immediately with `pan_mode`.

---

# Language

Prefer user-oriented language.

Examples:

- Select Card Pages
- Review Cards
- Show CardLift the first card

Avoid exposing implementation concepts such as JSON, profile
normalization, crop geometry, or command-line terminology.

---

# Workflow Navigation

## Workflow Completion

Every workflow should expose one clear primary action that advances the user to the next logical step.

Users should never be left wondering:

- whether the current step is complete,
- what to do next,
- or how to reach the next stage of the workflow.

Navigation should not depend on discovering an unrelated control elsewhere in the interface.

Where appropriate:

- completed workflows should clearly communicate their scope (for example, whether an action applies to one page or all selected pages);
- the next workflow step should be explicitly presented;
- optional navigation (such as inspecting pages) should remain visually secondary to the primary workflow action.

---

# Card Inspection

Review Cards' grid thumbnails are intentionally small (150px, a lower
render scale than Calibrate) -- enough to judge inclusion (is there a
card here at all?) but not enough to judge whether a crop is actually
correct. Card Inspection closes that gap: clicking a small "look closer"
affordance on a tile opens an overlay showing that one card at high
fidelity, with a margin of surrounding page content so the crop boundary
(drawn in CardLift's own accent color) is visible in context rather than
isolated. This ports the CLI's already-proven `--preview` (macro) /
`--inspect` (micro) split into the GUI, rather than inventing a new idea.

Deliberately not a general zoom/pan viewer: Review Cards exists to build
confidence through representative sampling, not to demand exhaustive
inspection, and calibration is uniform across a page/arrangement, so
checking a card and its neighbors is representative of the whole page
rather than a partial audit. Concretely, this means:

- No interactive zoom, zoom percentage, or persistent pan mode --
  inspection shows the card at a fixed high-fidelity scale, fit to the
  available space, not a manipulable canvas.
- No thumbnail filmstrip -- Next/Previous (plus Left/Right arrow keys)
  step through cards in the grid's own reading order, so comparing a card
  against its immediate neighbor (where alignment problems actually
  cluster) costs one keypress.
- No "inspected" marking on tiles and no deck-wide "card N of M" count --
  either would read as a completion target, which contradicts sampling
  being sufficient. Position is instead conveyed only by which of
  Previous/Next is enabled and by the source page label.
- Opening/closing the inspector never rebuilds the grid, so the scroll
  position the user opened it from is exactly where they land back.
- High-fidelity renders are generated on demand, per page, only for pages
  the user actually opens -- never pre-rendered for the whole deck.

The overlay itself is a full-workspace overlay, not a modal dialog --
CardLift is "a workspace application, not a dialog application"
(DESIGN_SYSTEM.md), so it should read as the workspace focusing on one
card, not a separate application opening on top of it.

**Discoverability is a provisional decision, not a resolved one.** The
"look closer" affordance is a small, always-visible (not hover-only) icon
in a tile corner, distinct from the existing include/exclude click, so
the existing toggle-inclusion interaction is completely unchanged. It's
always visible rather than hover-gated because a feature whose entire
purpose is building confidence shouldn't depend on a user incidentally
discovering it. This is the one part of the design explicitly flagged for
alpha-testing feedback -- see "Open Questions" below.

---

# Open Questions

The following topics intentionally remain open until validated through
prototype testing:

- Final visual theme and typography
- Keyboard shortcut set
- Compact sidebar mode for smaller displays
- Export workspace layout
- Future support for multiple layouts and profile management
- Card Inspection's discoverability affordance: whether the tile's
  primary click should stay as include/exclude with inspection as a
  secondary corner affordance (current implementation), or whether the
  two should swap. Ship the current design as the default; treat alpha
  feedback on this specifically as the thing most likely to change.

These should be resolved through iterative testing rather than
speculation.
