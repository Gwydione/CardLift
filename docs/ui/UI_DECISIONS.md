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
  - Back
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

# Back Mode: the One-Page Choice

Back Mode is derived automatically from how many pages a user marks as
Back in Select Card Pages -- zero, one, or many. Automatic derivation
was preserved as far as it honestly could be: the deck's back
configuration should never require a question the page markings already
answer.

Exactly one marked Back page is the one case that genuinely can't be
derived -- it could mean a Shared Back, or a one-page deck where every
card still has its own unique reverse (Paired Back Pages). Rather than
asking every deck to choose a back mode up front, which would
reintroduce a question most decks never need, this ambiguity is
surfaced as a single inline toggle in Select Card Pages' Deck Summary,
shown only when the count is exactly one and invisible otherwise. Shared
Back is the default reading, so a deck that behaved this way before this
choice existed keeps behaving exactly the same unless the user opts in.

This is the project's answer to a more general question worth stating
explicitly: prefer a narrow, situational choice over a general settings
screen whenever the ambiguity is genuinely rare and resolvable with one
clearly-worded control.

---

# Card Inspection

Review Cards' grid thumbnails are intentionally small (150px, a lower
render scale than Calibrate) -- enough to judge inclusion (is there a
card here at all?) but not enough to judge whether a crop is actually
correct. Card Inspection closes that gap: clicking a small "look closer"
affordance on a tile opens an overlay showing that one card -- or, for a
Paired Back Pages deck, that card alongside its paired back -- at high
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

**Paired Back Pages extends this, rather than adding a second view.**
Review Cards' main grid still shows fronts only, for every Back Mode --
the grid's job is judging inclusion, not comparison, and doubling its
thumbnails would compete with that without helping it. The comparison a
Paired deck actually needs -- does this card's back really belong with
this front? -- only matters once someone is already looking closely at
one card, so it lives inside the same "look closer" overlay instead of a
new screen: opening it on a Paired deck shows that card's front and its
paired back side by side, at the same fidelity, rather than asking the
user to cross-check two separate views.

**Paired comparison needed less page context than single-card
inspection, not more.** The original page-context margin -- enough
surrounding page content, including neighboring cards and registration
marks, to judge whether a crop lines up with the physical page -- reads
well when only one card is shown. Once Paired Back Pages showed two
cards side by side, each still carrying its own full margin of context,
the surrounding detail on both sides started competing with the actual
front/back comparison rather than supporting it. The fix narrows -- it
does not remove -- the margin specifically for the paired, side-by-side
view: enough context remains to judge crop placement, but not enough to
pull neighboring cards into view. Front Only and Shared Back's
single-card inspection is unchanged.

**Discoverability is settled for the general case, and evolved through
testing for Paired Back Pages specifically.** The "look closer"
affordance is a small, always-visible (not hover-only) icon in a tile
corner, distinct from the existing include/exclude click, so the
existing toggle-inclusion interaction is completely unchanged. It's
always visible rather than hover-gated because a feature whose entire
purpose is building confidence shouldn't depend on a user incidentally
discovering it. Whether this click should stay secondary to
include/exclude, or the two should swap, was left open pending alpha
feedback; the shipped placement was confirmed as the answer.

Manual testing on Paired Back Pages decks then surfaced a second,
narrower discoverability gap: nothing distinguished a card whose "look
closer" view would show a front/back comparison from an ordinary,
single-image inspection. The first attempted fix was a clearer tooltip,
and it didn't address the actual problem -- the gap wasn't that users
misunderstood the interaction once they found it, it was that they never
suspected a richer interaction existed to look for. The fix that worked
was visual, not textual: for Paired Back Pages tiles only, the
affordance's own icon changes from the ordinary magnifying glass to two
overlapping card shapes, signaling "compare two things" before the user
ever clicks -- same corner, same always-visible convention, no new
control, and no change to Front Only/Shared Back's icon. The lesson
generalizes: a hidden capability needs a visible signal at the point of
interaction, not just clearer words once it's already been found.

---

# Open Questions

The following topics intentionally remain open until validated through
prototype testing:

- Final visual theme and typography
- Keyboard shortcut set
- Compact sidebar mode for smaller displays
- Export workspace layout
- Future support for multiple layouts and profile management

These should be resolved through iterative testing rather than
speculation.
