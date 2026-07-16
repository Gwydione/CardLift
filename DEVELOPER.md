# CardLift Developer Handbook

This document exists so that you (or anyone else) can come back to
CardLift after weeks away and be productive again in five minutes,
without having to re-derive how the project is organized or how to run
it. If you're looking for _what CardLift is_ and _how the calibration
model works conceptually_, see [README.md](README.md) — this file is
about the mechanics of working on the code.

## Security and Network Access

The core CardLift workflow is local-first and must not require network access. Do not add telemetry, uploads, update checks, licensing calls, or other outbound communication without an explicit product decision, clear user disclosure, and documentation.

Before making a change that touches networking, file I/O, or logging, check it against [docs/PRIVACY_PROMISES.md](docs/PRIVACY_PROMISES.md)'s contributor checklist -- that document, not this section, is the canonical source for what CardLift currently promises and how to evaluate a change against it.

## First Five Minutes

The fastest path back to a working mental model after time away. Do
these in order; each one is also covered in more depth further down.

1. **Open PowerShell** in the project folder:
   ```powershell
   cd C:\Users\adodg\OneDrive\Documents\deckforge-rewrite
   ```
2. **Activate the virtual environment:**
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
   Confirm your prompt now shows a `(.venv)` prefix.
3. **Run the test suite** to confirm the project still works:
   ```powershell
   pytest
   ```
4. **Reorient yourself** on what happened last:
   ```powershell
   git status
   git log --oneline -10
   ```
5. **Skim `profiles/demo_deck.json`** and re-read README's "How the
   grid math works" if the `left`/`top`/`trim_*` fields don't
   immediately make sense — this is the part that's easiest to forget.
   `demo_deck.json` uses the legacy flat-field form; see README
   "Profiles" for the `layouts`-list form a multi-grid deck would use
   instead, and `DeckProfile.layouts` (always populated, either way) is
   what downstream code actually reads.
6. **Run a sanity-check command** against the sample deck to see
   CardLift actually do something before you start changing code:
   ```powershell
   python extract.py --profile demo_deck --preview
   ```
   Then open `preview/calibration_overlay.png` to see the current
   calibration.

At that point you're caught up — pick up wherever you left off, or see
"Typical Development Workflow" below for the normal cycle.

## Getting Started

**Open the project**

```powershell
cd C:\Users\adodg\OneDrive\Documents\deckforge-rewrite
```

There's nothing to "launch" — CardLift is a CLI tool, not a server. You
work on it in an editor and run `extract.py` from a terminal.

**Activate the virtual environment**

A venv already exists at `.venv/`. Activate it per-session:

```powershell
.venv\Scripts\Activate.ps1
```

(If you're in Git Bash instead of PowerShell: `source .venv/Scripts/activate`.)

You'll know it worked because your prompt gets a `(.venv)` prefix. Do
this every time you open a new terminal to work on CardLift — nothing
below (`pytest`, `python extract.py ...`) will find the right
dependencies without it.

**Installing dependencies**

Only needed the first time, or after `requirements.txt` /
`requirements-dev.txt` change:

```powershell
pip install -r requirements-dev.txt
```

This pulls in runtime deps (`PyMuPDF`, `Pillow`) plus `pytest` for
testing. Use `requirements.txt` alone only if you specifically want a
runtime-only install with no test tooling.

**Running the full test suite**

```powershell
pytest
```

`pyproject.toml` already points pytest at `src/` and `tests/`, so this
works from the project root with no extra flags. Run it now, before
touching anything, to confirm your environment is healthy.

**GUI (Phase II)**

A PySide6 desktop application lives in `src/deckforge_gui/`, separate
from the CLI/engine package. The Tkinter `--calibrate` window in
`src/deckforge/calibrate_ui.py` is unaffected and still the real
calibration tool.

```powershell
pip install -r requirements-gui.txt
python gui_app.py
```

`requirements-gui.txt` layers PySide6 on top of `requirements.txt`, kept
separate so CLI-only installs don't need a GUI toolkit.

Two plain-Python models back the widgets, both free of any PySide6
import so they're unit tested directly without opening a window:

- `app_state.py` — navigation/pan/guidance-collapse state
  (`tests/test_app_state.py`).
- `session.py` — the loaded PDF (`DeckSession`/`DeckLoadError`;
  `tests/test_session.py`). It reuses the engine's `PDFRenderer` (open +
  `page_count`) rather than re-implementing PDF validation — its only
  job is turning a rejected file into a friendly `DeckLoadError` at the
  GUI boundary.

**Welcome Experience milestone.** The first real workflow: launch → open
a PDF on the Deck page (drag-and-drop onto the dashed drop zone, or the
"Choose PDF" button) → CardLift reads the page count via `PDFRenderer`
→ the Deck step is marked complete and the app auto-advances to Find
Cards. `deck_workspace.py` (`DeckWorkspace`) owns the drop
zone/click-to-browse/error-display UI but never decides whether a file
is a valid PDF -- that's `DeckSession.load_pdf`'s job; `main_window.py`
wires the two together. `theme.py` centralizes the color palette (dark
navigation chrome, light PDF workspace, purple accent) so widgets don't
each hardcode hex values. Select Card Pages, Calibrate, Review Cards, and
Export are still placeholders -- this milestone only wires the Deck →
Select Card Pages step.

**Responsive Deck workspace.** `DeckWorkspace` no longer fixes the drop
zone, margins, and type scale to constant pixel sizes -- at moderate
window sizes the page looks the same as before, but on a large monitor the
drop zone, heading, and whitespace all grow instead of leaving the page
looking like a small dialog stranded in a mostly-empty workspace (see
DESIGN_PRINCIPLES.md's "The PDF is the workspace"). `_apply_responsive_metrics`
recomputes every scaled size from a single `t` (`theme.responsive_t()`,
0 at `_COMPACT_WIDTH` and below, 1 at `_SPACIOUS_WIDTH` and above) on
every `resizeEvent`/`showEvent`, so growth is continuous rather than a
hard breakpoint jump; each metric's minimum matches the old fixed value,
so nothing changes below `_COMPACT_WIDTH`. `theme.lerp()`/`clamp()`/
`responsive_t()` are generic enough that a future workspace needing the
same "scale with available width" behavior can reuse them instead of
duplicating the math.

**Select Card Pages milestone.** (Originally shipped as "Find Cards"; see
"Select Card Pages redesign" below for why it was renamed and reworked.)
The documented workflow order is Deck -> Select Card Pages -> Calibrate ->
Review Cards -> Export (docs/ui/UI_DECISIONS.md), so this step runs
_before_ any calibration profile exists. It is deliberately a coarse,
page-level scoping step, not detection or calibration: there is no
automatic card-detection algorithm anywhere in CardLift (README's MVP is
manual-calibration-only), and Calibrate's own two-corner-click flow (the
CLI's `--calibrate`, via `measure.derive_geometry()`) already owns
deriving precise card geometry later -- redoing that work here would just
be duplication.

`find_cards_state.py` is the pure-Python model (no PySide6 import, unit
tested in `tests/test_find_cards_state.py`, same pattern as
`app_state.py`/`session.py`): `FindCardsState` assigns each page at most
one `PageRole` (`FRONT` or `BACK`) -- a page's *semantics*, not a click
location or a coordinate. The state that matters is purely "what is this
whole page," so a page either has a role or it doesn't; Calibrate later
re-derives the actual card box from scratch via its own corner clicks, so
storing any location here would add nothing Calibrate can't already
produce more precisely itself.

`find_cards_workspace.py` (`FindCardsWorkspace`) renders the current page
via the engine's `PDFRenderer` at a fixed `PREVIEW_RENDER_SCALE` (no
profile/render_scale exists yet at this point in the workflow), fits it to
the canvas without upscaling, and exposes two per-page toggle buttons
("Mark as Front" / "Set as Shared Back") plus a role badge drawn on the
canvas -- there is no click-to-mark on the page image itself. `FindCardsView`
is the pure (no Qt-widget-instance dependency) fit/center transform between
the rendered image and widget pixels, recomputed on every paint -- unit
tested directly in `tests/test_find_cards_workspace.py`. Page navigation
(Previous/Next) is local to the workspace; there is no app-wide Start Over
feature yet for Select Card Pages state to participate in. Loading a (new
or replacement) PDF via `MainWindow._on_pdf_chosen` clears any previous
role assignments, since a page's role has no relationship to the same page
number in a different PDF.

Out of scope for this milestone, deferred to later ones: inferring
rows/cols or precise crop geometry from a page (Calibrate's job),
selecting/moving/resizing individual card rectangles (Edit Cards is a
separate, later concern), and any app-wide reset/Start Over feature.

**Select Card Pages redesign: PageRole and SharedBackStatus.** The
original Find Cards milestone stored a clicked `(x, y)` point per marked
page (`PageMarker`); once Calibrate's own click-to-measure flow existed,
it became clear the point's *location* never carried any meaning --
Calibrate always re-measures from scratch. The step was renamed Select
Card Pages and reworked to assign each page an explicit `PageRole`
(`FRONT` or `BACK`) instead, via "Mark as Front"/"Set as Shared Back"
toggle buttons rather than a click anywhere on the page. A page can hold
at most one role -- assigning Shared Back to a page overwrites whatever
role it had, and moves the Shared Back role off any other page that held
it (`FindCardsState.set_role()`), so "a page cannot be both Front and
Shared Back" is enforced by construction rather than by convention.

Because "this Deck has no Shared Back" is a valid, common answer that
must stay distinguishable from "haven't decided yet" (CORE_CONCEPTS.md),
`FindCardsState.shared_back_status()` returns a three-way
`SharedBackStatus` (`ASSIGNED` / `CONFIRMED_NONE` / `UNRESOLVED`) rather
than exposing "is some page currently assigned" as a bare boolean. An
early version of the Shared Back Calibrate step *did* collapse those into
a boolean (`has_back_page`), which meant "the user hasn't decided yet" and
"the user confirmed there's no Shared Back" were indistinguishable
downstream -- reachable in practice because `AppState.is_reached` never
regresses: once Calibrate > Shared Back has been visited once, its
sidebar entry stays enabled even after the user goes back to Select Card
Pages and un-assigns the Shared Back page, leaving it genuinely
unresolved. Calibrate would then silently display "this deck has no
Shared Back" and allow Continue, without the user ever confirming that.
The fix threads `SharedBackStatus` itself through
`calibrate_guidance_text()`/`calibrate_status_text()` and
`CalibrateWorkspace._update_continue_footer()` so all three states are
handled explicitly: `ASSIGNED` shows and calibrates that page normally;
`CONFIRMED_NONE` shows the "nothing to calibrate" state and permits
Continue; `UNRESOLVED` shows neither of those, blocks Continue, and
surfaces a "‹ Back to Select Card Pages" button
(`back_to_select_cards_clicked`) so the user has an explicit route back to
where the decision belongs, rather than Calibrate guessing on their
behalf. See `tests/test_calibrate_state.py`'s
`TestUnresolvedSharedBackReachedViaSidebar` for the regression test
covering that navigation path. The Deck Summary (in
`find_cards_workspace.py`) and the bottom status bar
(`find_cards_status_text()`) both read `shared_back_status()` and use the
same "Shared Back: not yet decided." wording for `UNRESOLVED`, rather than
two different phrasings drifting independently -- `should_prompt_shared_
back()` still separately decides *when* to reveal the inline "Confirm
there's no Shared Back" action (reaching the PDF's last page, or a
blocked Continue attempt), which is a timing question layered on top of,
not a substitute for, the underlying `SharedBackStatus` fact.

**Alpha Polish: Shared Back discoverability.** Manual alpha testing
surfaced three related friction points in this same Select Card Pages
flow, none of them a state-model problem -- `FindCardsState`/
`SharedBackStatus` already tracked everything correctly; the gap was
purely in what the workspace showed the user in the moment.

1. **"Set as Shared Back" read as disabled.** `_BACK_TOGGLE_STYLE`'s idle
   state (`find_cards_workspace.py`) used a transparent border and
   `TEXT_CAPTION_MUTED` text to stay visually lighter than "Mark as
   Front" -- but that combination is nearly identical to
   `_CONTROL_BUTTON_STYLE`'s actual `:disabled` look (same muted color, no
   border change), so the button read as inactive rather than secondary.
   The idle state now uses a real `BORDER_CARD` border and `TEXT_HEADING`
   text, keeping the *fill* difference (still unfilled vs. Front's
   filled-when-checked) as the thing that signals "lighter weight,"
   rather than muted color doing double duty as both "secondary" and
   "disabled."
2. **A blocked Continue attempt looked like nothing happened.**
   `_on_continue_clicked()` already called `state.note_continue_
   attempted()` when Shared Back was unresolved, but the only visible
   effect was revealing the Deck Summary's confirm action further down
   the workspace -- nothing changed near Continue itself.
   `find_cards_state.continue_blocked_text()` is a new, small pure
   function (same family as `find_cards_status_text()`, unit tested the
   same way) returning a message once `continue_attempted` is true and
   Shared Back is still unresolved, `None` otherwise.
   `FindCardsWorkspace._refresh()` binds it to a label right above the
   Continue button, styled with `ERROR_TEXT` (the same error-color
   convention already used in `deck_workspace.py`/`export_workspace.py`),
   so a blocked click now gets feedback at the point of the click.
3. **The inline confirm action was easy to overlook.** "Confirm there's
   no Shared Back" was plain underlined link text at `FONT_CAPTION` size
   (the smallest type on the page) despite being, whenever it's visible,
   the one thing blocking Continue. `_CONFIRM_NO_BACK_STYLE` replaces the
   link styling with a light filled "chip" (bordered, `FONT_BODY_SM`,
   always showing the hover-style fill rather than only on hover) so it
   reads as an actionable control rather than fine print, while staying
   unfilled/non-bold relative to Continue so it doesn't compete with the
   workflow's actual primary action.

All three are additive styling/messaging changes -- `FindCardsState`,
`SharedBackStatus`, and the Continue/confirm gating logic are unchanged.

**Calibrate milestone.** The first milestone where precise geometry is
established: two-corner-click measurement of one representative Fronts
page plus the single page Select Card Pages assigns as Shared Back
(see "Select Card Pages redesign" above -- Shared Back page navigation
has changed since this milestone first shipped), reusing the
CLI's calibration math (`measure.derive_geometry()`, the same
inverse-geometry solver `--calibrate`/`--measure` use) and click
semantics (corner normalization, auto-inferred neighbor cell, optional
second-card gap measurement) rather than re-deriving any of it.

`calibrate_state.py` is the pure-Python model (no PySide6 import, unit
tested in `tests/test_calibrate_state.py`): `CalibrateState` holds two
independent `CalibrationTarget`s (`cards`/`back`), each with its own
pending click, measurements, and derived `CalibratedGeometry`.
`record_click()` is a small state machine returning a `ClickOutcome`
(`PENDING_SET`/`MEASUREMENT_ADDED`/`REJECTED_DEGENERATE`/
`NEEDS_CELL_LABEL`/`COMPLETE`/`IGNORED_ALREADY_COMPLETE`) rather than
touching Qt directly, mirroring `CalibrationWindow`'s transitions exactly
but as directly-testable data. Measurements are stored in **PDF points**
(not pixels, per the project's coordinate-storage rule) -- pixel space
is reconstructed only for the moment `derive_geometry()` needs it
(`point * render_scale`, a lossless round trip, not a re-measurement).

**Shared Back is single-card only.** Fronts supports an optional second-
card measurement to derive `gap_x`/`gap_y` for a printed grid, but Shared
Back is one representative card's rectangle, not a grid -- there's no
neighboring back to space against. `CalibrationTarget.allows_second_
measurement` (`True` for `cards`, `False` for `back`) is the one switch
`record_click()` checks: when it's `False`, the target finalizes as soon
as its single card's second corner is clicked, so Shared Back never shows
neighbor suggestions or a "Finish with one card" button -- both are
already gated on `not target.is_complete`, so completing one click
earlier hides them for free rather than needing a step-specific branch in
`calibrate_workspace.py`. `calibrate_guidance_text()`/
`calibrate_status_text()`'s completion copy for Shared Back names the
representative page and states the result will be applied as the shared
back for every selected front page, mirroring how Fronts' completion
copy names its scope (see "Presenting one shared geometry" below).

Deliberately **not** reused from the CLI: the "copy suggested patch,
paste into profiles/\*.json by hand" model. That step exposes JSON/
profile-normalization concepts `docs/ui/DESIGN_PRINCIPLES.md` says the
GUI should hide, and Phase II has no profile file at all yet. Derived
geometry is instead held directly in `CalibrateState` -- a future
profile-building milestone reads from it rather than the user retyping
numbers. Relatedly, `CalibrateState` never constructs a `profile.
CardLayout` (rows/cols and page-range enumeration stay out of scope, same
as Select Card Pages) -- it only holds the `GridGeometry`-shaped subset a
future milestone would combine with rows/cols to build one.

Fronts and Shared Back have different page-navigation sources, both read
from `find_cards_state.py` rather than either rediscovering page meaning:
`CalibrateWorkspace._navigable_pages()` restricts Fronts to
`find_cards_state.front_pages()` (one shared geometry is assumed to apply
to every Front Page) and restricts Shared Back to the single page
`find_cards_state.back_page()` names, if any -- an empty list (no page to
show at all) when Shared Back is `CONFIRMED_NONE` or still `UNRESOLVED`.
Calibrate never searches the PDF for a plausible back page itself; an
earlier revision guessed the PDF's last page as a fallback when none had
been identified yet, which was removed once Select Card Pages made an
explicit assignment mandatory -- see "Select Card Pages redesign" above.
Leaving a page mid-measurement (a pending click, or one measurement not
yet finished) discards that in-progress state -- it only makes sense on
the page it was clicked on. `CalibrateState.cards_is_stale()`/
`back_is_stale()` are pull-based checks (not signals) comparing each
target's `calibrated_page_num` against Select Card Pages' current role
assignments, run by `MainWindow` whenever the user navigates into the
corresponding step, so changing a page's role resets any calibration that
depended on it without coupling the two state classes together.

`view_transform.py` is a straight port of `calibrate_ui.py`'s
`ViewTransform` (and its pure sibling functions -- `wheel_direction`,
`is_pan_gesture`, `pan_active`, `recompute_view_for_resize`) into
`deckforge_gui`, not an import: `calibrate_ui.py` imports `tkinter` at
module scope, so importing anything from it would make Tkinter a hard
dependency of the PySide6 app. It's shared GUI infrastructure rather than
Calibrate-only code, since Preview/Edit Cards will need the same
zoom/pan/fit foundation. `CalibrateWorkspace` (`calibrate_workspace.py`)
draws the page and every overlay (measured box, pending marker, neighbor
suggestions, always-on guide lines) with immediate-mode `QPainter` in one
`paintEvent`, the same pattern `find_cards_workspace.py` established,
rather than `calibrate_ui.py`'s Tkinter canvas-item approach.

The CLI's step-numbered wizard chrome ("Step 1 of 3") is intentionally
not carried over -- the guidance panel and status bar already have a
proven multi-cue pattern for "what's happening right now" (see Pan mode),
so `calibrate_guidance_text()`/`calibrate_status_text()` make that text
state-aware (pending corner / one card measured / calibrated) instead of
introducing a step counter. The underlying state machine is identical;
only the presentation differs.

**Presenting one shared geometry, not per-page calibration.** Fronts
calibration produces a single geometry from one representative Front
Page, applied to every page Select Card Pages marked Front -- but early
wording ("Calibrated.", "Page 3 (2 of 6 marked)") read as though each page
still needed its own calibration, especially with page navigation still
available afterward. `calibrate_guidance_text()`/`calibrate_status_text()`
take a `front_page_count` (threaded from `FindCardsState` through
`CalibrateWorkspace`, `GuidancePanel`, and `MainWindow._status_text()`) so
the completion message names the representative page and states that the
result applies to all selected front pages. Separately,
`CalibrateWorkspace._page_label_text()` grounds page navigation in the
original PDF's numbering ("PDF page 3 of 8") as the primary line, with the
front-page-relative position ("Front page 2 of 6") as a visually
lighter secondary line -- rather than replacing PDF page numbers with a
filtered sequence, which made pages excluded from Select Card Pages (e.g.
the shared back) feel like they'd been dropped rather than simply out of
scope for this step. Shared Back keeps just the PDF-page line, since it
navigates only its single assigned page rather than the Front Pages
subset.

**Calibration geometry robustness.** Alpha testing across real PnP PDFs
found that different choices of calibration cards produced systematically
different, sometimes-clipping grids -- root-caused in
`docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` to two additive effects, both
fixed without touching `derive_geometry()`'s math, `GridGeometry`, or the
two-click workflow:

Effect A (silent 0.0 gap fallback): `CalibratedGeometry.gap_x_derived`/
`gap_y_derived` already recorded whether an axis was actually measured
versus defaulted to edge-to-edge, but nothing read them.
`ungauged_axis_warning()` (`calibrate_state.py`) now appends a plain-
language warning to the completion banner and guidance/status text
whenever an axis was defaulted *and* it actually matters -- gated on
`suggested_grid()`'s rows/cols, so a genuine one-row, one-column, or
single-card deck (where that axis's spacing is never applied to any real
cell) never sees a spurious warning. `CalibrateWorkspace._update_continue_footer()`
and `calibrate_guidance_text()`/`calibrate_status_text()` all thread it
through, so the workspace's own prominent banner and the app-wide
guidance panel/status bar stay consistent with each other.

Effect B (adjacent-click noise amplification): a gap estimate's error is
inversely proportional to how far apart the two measured cells are, but
`predicted_neighbor_box()`'s hint previously only ever pointed at the
immediately-adjacent cell, and nothing about the workflow nudged a user
toward a wider baseline. `suggested_second_card_offset()` estimates
roughly how many cells fit across the page (reusing `_fit_count()`, the
same math `suggested_grid()` already uses) and the hint box is now drawn
that far away instead, capped at `_MAX_SUGGESTED_OFFSET` (6 cells) so a
tiny card on a large page doesn't suggest something off the default
Fit-to-Window view. `infer_second_cell()` needed no change -- it already
derived a click's real `(row, col)` from wherever the user actually
clicked, not from the hint, so it was never actually limited to adjacent
cells, only the drawn hint was.

A related, separate finding from the same alpha round: users naturally
click a card's cutting guide when one is printed, and the card's outer
printed edge when it isn't -- reasonable behavior the two-corner-click
model already tolerates *as long as the same reference point is used for
both corners of the calibrated card*, since there's no cushion (trim is
always zero in the GUI -- see "Why `review_workspace.py` calls
`CardCropper` directly" above) to absorb an inconsistency between them.
`app_state.py`'s `GUIDANCE`/`STATUS` for both Calibrate steps, and
`calibrate_state.py`'s "click the opposite corner" guidance, now name
this rule explicitly rather than leaving it for the user to infer.

Deliberately not touched: the CLI's own `--calibrate` window
(`src/deckforge/calibrate_ui.py`) has structurally the same
`predicted_neighbor_box()`/silent-fallback pattern, but it's a separate
Tkinter port (not shared code with the GUI -- see "`view_transform.py` is
a straight port" above for why), and the CLI engine is documented
elsewhere in this file as stable. Left as a follow-up rather than folded
into this pass; see `docs/RELEASE_READINESS.md`'s Open section.

**Grid-inference conflict detection (Doom Pilgrim).** A real 3×3 deck
surfaced a distinct failure mode from the one above: `infer_second_cell()`
assigning the *wrong cell* (not just a wrong gap) when a real column or
row gutter is large enough relative to card size to tip
`round(dx/card_width)`/`round(dy/card_height)` past a rounding boundary --
see `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s addendum for the full
trace. Fixed by cross-checking the click-derived offset against
`suggested_second_card_offset()`'s independent, page-bounds-based
estimate -- already computed to draw the second-card hint, now also
threaded into `CalibrateState.record_click()` as plain
`hint_col_offset`/`hint_row_offset` data (`calibrate_workspace.py`'s new
`_hint_offsets_for_conflict_check()` is the only place that reads page
size; `calibrate_state.py` stays free of any PDF/Qt import, per this
file's "WHY THIS DOESN'T MIRROR..." family of module docstrings). An axis
is only checked when the click actually differs on it, so a same-row or
same-column measurement is never flagged just because the hint's
(unrelated) value on the untouched axis differs. Agreement completes
automatically exactly as before; disagreement returns `None` from
`infer_second_cell()`, which `record_click()` already turns into
`ClickOutcome.NEEDS_CELL_LABEL` -- the pre-existing clarification prompt,
not a new dialog or workflow step. This is deliberately framed as
**conflict detection**, not a correctness guarantee: two independently-
derived estimates agreeing is good evidence, not proof, since both share
the same "gap is small" assumption that could in principle be wrong on
both sides at once.

**Cell-label prompt uses human, not internal, numbering.** Manual
validation of the conflict-detection prompt above found it asking the
user for the ambiguous card's cell as `r2c2` -- this project's internal
0-based row/col convention (also `--card`'s CLI syntax, `measure.
CARD_SPEC_RE`), never meant to be user-facing. `calibrate_state.py`'s new
`parse_human_cell_label()` accepts a plain 1-based `"row,col"` pair (e.g.
`"2,1"` for row 2, column 1) and returns the 0-based tuple `record_click()`/
`add_measurement_with_cell()` already expect -- no change to internal
storage or the click-resolution workflow, only the text at this one
boundary. `calibrate_workspace.py`'s dialog also now states the first
card's row/column (converted to 1-based for display) so the user has a
concrete anchor for what "differs from the first card" means, rather than
having to remember an unlabeled rectangle. Deliberately not touched: the
CLI's `--card`/`--measure` syntax and the separate Tkinter `calibrate_ui.py`
prompt (same rationale as the "Deliberately not touched" note above --
developer-facing, not shared code with the GUI).

**Review Cards milestone.** The last checkpoint before Export: every
suggested card is rendered as a clickable thumbnail so the user can catch
a miscount or a bad crop before anything is written to disk -- CORE_CONCEPTS.md's
definition of Preview ("build confidence and catch mistakes before files
are generated").

**Suggested grid size.** Nothing before this milestone ever determined how
many cards (rows x cols) are on a page -- Select Card Pages only assigns
page-level roles, and Calibrate deliberately defers "grid inference" (see
"Calibrate milestone" above). Review Cards needs that number to enumerate
cards at all, and README's "manual calibration only, no automatic edge
detection" philosophy rules out silently trusting a computed guess.
`calibrate_state.suggested_grid()` resolves this by computing a **starting
suggestion** -- how many `card_width x card_height` (+ `gap`) cells fit
within the calibrated Front Page's own point-dimensions
(`PDFRenderer.page_size()`, new this milestone) -- that Review Cards then
requires a human to confirm or correct before anything is exported. The
guess is never trusted unreviewed, so it doesn't reintroduce the "wrong
automatic guess silently produces bad crops" risk README warns about.

The formula (`(page_extent - origin + gap + tolerance) // (card_size + gap)`,
per axis) has a real boundary-sensitivity risk worth naming: on a deck
whose margins leave little slack past the last row/column, ordinary
calibration click imprecision (a point or two) can tip the suggestion
across an integer boundary. The two failure directions aren't symmetric --
suggesting one card too many is a one-click fix in Review Cards, while
suggesting one too few is silently missing and much easier to overlook.
`GRID_FIT_TOLERANCE_PT` (2.0pt) deliberately biases toward the cheap
failure: a page whose margin is within tolerance of fitting one more cell
still gets it suggested. `TestSuggestedGrid` in `test_calibrate_state.py`
includes a regression test against `profiles/solo_cards.json`'s real,
`--preview`-verified calibration values (against the sample deck's actual
A4 page size) precisely to keep this formula honest against a real deck,
not only synthetic numbers.

The suggestion is surfaced as a plain descriptive clause appended to
Calibrate's existing completion text ("... Looks like a 3x3 grid per
page.") -- informational only, never a question or a second confirmation
gate. `CalibrateWorkspace.grid_page_size()` is the one place that looks up
the calibrated page's dimensions, reused by the workspace's own
caption/completion-banner and by `MainWindow._status_text()`, so the
number can't drift between surfaces. Confirming or correcting the actual
count is Review Cards' job alone, not Calibrate's -- see calibrate_state.py's
`_grid_clause()` docstring.

**`review_state.py`.** Pure state module (no PySide6/PDF import, same
family as `find_cards_state.py`/`calibrate_state.py`), unit tested in
`tests/test_review_state.py`. `build_review_cards()` calls
`suggested_grid()` once per Front Page (each page can suggest a different
grid if page sizes differ) and enumerates every cell as a `ReviewCard`
(page, row, col) -- identity only, no image data. `ReviewCardsState.sync()`
reconciles that list against whatever was previously toggled: cards still
present keep their yes/no, new cards default to included, cards no longer
suggested are dropped. It's safe to call on every entry to the step
(idempotent if nothing changed), the same pull-based-refresh idiom
`cards_is_stale()`/`back_is_stale()` already use elsewhere.

This module deliberately does **not** group Select Card Pages'
`front_pages()` into contiguous runs or construct a `profile.CardLayout` --
unlike a future Export milestone (which will need one, since `CardLayout`
requires a *contiguous* page range), Review Cards only ever crops and
displays individual cells, so nothing here needs that grouping yet.

**Two additional Calibrate-staleness checks, on Review Cards' own entry.**
`MainWindow._apply_step()` already resets a stale Calibrate target when
navigating *into* Calibrate Fronts/Shared Back (`cards_is_stale()`/
`back_is_stale()`). That alone isn't sufficient for Review Cards:
`AppState.is_reached` lets the sidebar route straight to Review Cards
without passing back through Calibrate, so a target that went stale after
Review Cards was last shown (a Front Page role changed, or the Shared Back
page was reassigned to a different page) would otherwise be displayed
as-is. `_apply_step()` now runs both staleness checks whenever the target
step is `REVIEW_CARDS` too, not only the matching Calibrate step, before
`ReviewWorkspace.on_shown()` reads `calibrate_state.cards`/`back` --
`review_state.review_ready()` is the resulting gate `ReviewWorkspace` (and
its guidance/status text) branches on, covering three blocked states: Fronts
not calibrated, Shared Back still `UNRESOLVED`, and Shared Back `ASSIGNED`
but not yet calibrated (reachable via the same stale-reset path).

**Why `review_workspace.py` calls `CardCropper` directly, not
`DeckExporter`.** `deckforge.exporter.DeckExporter` is CLI-shaped: it
discovers the PDF by scanning `sample_decks/`/the project root via
`profile.pdf_file`, and every operation (`preview()`, `overlay()`,
`export()`) writes straight to fixed `preview/`/`output/` folders on disk.
The GUI already has the user's actual PDF open via its own `PDFRenderer`
(whatever path they chose, not necessarily under `sample_decks/`) and
wants in-memory `PIL.Image`s to page through live, re-cropped on every
toggle -- not files rewritten per click. `deckforge.cropper.CardCropper`
is the lower engine layer built for exactly this ("given a rendered page
image ... produce PIL Images for each card cell"), so `ReviewWorkspace`
calls it directly, matching ENGINEERING_STANDARDS.md's "the GUI should
call the engine, not duplicate it" without pulling in `DeckExporter`'s
file-orchestration layer. Trim is always `TrimValues(0, 0, 0, 0)` here --
see `calibrate_state.py`'s `CalibratedGeometry` docstring: the two-corner
click the user made in Calibrate already *is* the exact crop box, unlike
the CLI's eyeballed-pixel-coordinates flow that trim exists to nudge
afterward.

`CalibratedGeometry.to_grid_geometry()` converts to `profile.GridGeometry`,
so the shapes stay byte-identical to `profile.py`'s real dataclasses --
`review_workspace.py` and `export_state.py` both use it. An earlier version
of this note suggested Export would go further and build actual
`CardLayout`/`DeckProfile` values, reusing `DeckExporter` unchanged. That
turned out to be wrong: see "Export milestone" below for why a `CardLayout`
can't represent Review Cards' excluded cells at all, and what Export does
instead.

**Export milestone.** The final Phase II workflow step: writes the exact
set of cards Review Cards approved to PNG files in a folder the user
chooses -- PNG only, no resizing/padding/bleed/presets, no printable-PDF
formats, no contact sheet (all deferred). No profile file, JSON, or CLI
concept is ever exposed, per `docs/ui/DESIGN_PRINCIPLES.md`.

**Why `DeckProfile`/`CardLayout` are never built.** The original design
sketch (see the corrected note above) assumed Export would build a real
profile and reuse `DeckExporter.export()`. That is wrong: a `CardLayout`
always means "a complete, regular `rows x cols` grid" -- `CardCropper.
crop_all()` / `geometry.iter_grid_positions()` enumerate every cell in
range unconditionally, with no way to omit one. Review Cards, however,
lets a human exclude specific over-suggested cells from an otherwise
regular grid (e.g. a partly-filled last page). Routing that reviewed,
possibly-sparse cell list through a `CardLayout` would silently
re-include every excluded cell in the real export -- a correctness bug,
not just an inconvenience. `CardLayout`/`DeckProfile`/`DeckExporter`
remain completely untouched by this milestone; the CLI's own export
behavior is unaffected.

`deckforge/cell_export.py` is the new engine primitive instead:
`export_cells(renderer, render_scale, front_geometry, cells, output_dir,
back=None)` takes an explicit, ordered `(page_num, row, col)` sequence --
no notion of a "complete grid" at all -- and reuses `PDFRenderer`/
`CardCropper` exactly as `DeckExporter` does, just keyed by an explicit
cell list rather than `profile.layouts`. It renders each distinct page at
most once via an internal cache keyed by page number, regardless of
whether the caller's cells happen to be grouped by page (they are, by
construction -- see below -- but the function doesn't rely on that).
`front_NNN.png` numbering follows the caller's list order exactly,
1-indexed; trim is always zero (same reasoning as Review Cards' own
`_ZERO_TRIM`: Calibrate's two-corner click already *is* the exact crop
box). `back`, if given, is `(page_num, geometry)`; omitting it (the
default) writes no `back.png` -- this is how a Deck with a confirmed no
Shared Back exports, with no change to `profile.py`'s `back_page`
schema needed, since Export never constructs a profile at all.

`deckforge_gui/export_state.py` is the pure (no PySide6/PDF import)
builder: `build_export_plan()` reads `ReviewCardsState.included_cards()`
verbatim -- the exact order and exclusions Review Cards produced, with no
re-sorting or re-derivation -- converts `CalibratedGeometry` to
`profile.GridGeometry` via `to_grid_geometry()`, and bundles the Shared
Back page/geometry only when `shared_back_status()` is `ASSIGNED`.
`export_ready()` is `review_ready()` plus "at least one card included".

**Review Cards must stay authoritative, even after `AppState.is_reached`
lets the sidebar jump straight to Export.** The same mechanism that lets
the sidebar route straight to Review Cards without passing back through
Calibrate (see "Select Card Pages redesign" above) also applies to
Export once it's been reached once. `MainWindow._apply_step()`'s existing
`cards_is_stale()`/`back_is_stale()` reset check (previously run only for
`CALIBRATE_CARDS`/`CALIBRATE_BACK`/`REVIEW_CARDS`) now also runs for
`EXPORT`, catching the *structural* staleness case (the calibrated page
no longer holds the role it was calibrated for).

That alone isn't sufficient: a *content* staleness case exists too --
Calibrate redone on the *same* page (a different card size/position, so
`cards_is_stale()` sees no change since `calibrated_page_num` is
unchanged), or a new Front Page added in Select Card Pages without
touching the calibrated page -- either of which changes what
`build_review_cards()` would suggest without invalidating `cards_target.
is_complete`. `export_state.review_snapshot_is_current()` catches this:
it recomputes `build_review_cards()` from the *current* calibrated
geometry and front-page set and compares the resulting cell identities
against whatever `review_state` last synced (only possible inside Review
Cards' own `on_shown()`). `ExportWorkspace` is the only caller, since it
already owns a `PDFRenderer` for the export operation itself and needs no
new infrastructure to also use it for this check; when the snapshot is
stale, `ExportWorkspace` blocks with `stale_review_guidance_text()`/
`stale_review_status_text()` instead of running `export_cells()` against
cards the human never actually confirmed. This was verified directly (not
just by code review): a smoke run that calibrates, reviews, excludes one
card, exports (54 cards -> 53 PNGs + `back.png`, confirming the exclusion
survived), then adds an extra Front Page and jumps back to Export via the
sidebar without revisiting Review Cards, confirms `ExportWorkspace` blocks
with this exact message rather than re-exporting.

**Documented limitation: the guidance panel and status bar do not run
`review_snapshot_is_current()`.** That check needs a page-size lookup,
which needs an open `PDFRenderer`; `GuidancePanel` and `MainWindow`'s
status bar have neither, and giving them one would mean threading a
workspace reference into `GuidancePanel`, breaking its "reads only plain
state, no widget dependency" boundary for one narrow edge case.
`export_state.export_ready()` (what both of those surfaces use) therefore
does not perform this check -- only `ExportWorkspace._rebuild()` does. The
practical effect: in the specific stale-snapshot scenario described above,
the guidance panel/status bar can say "Ready to export" while the Export
workspace body (the actual gate on the action that writes files to disk)
correctly blocks and explains why. This is an accepted, deliberately
narrow gap -- the thing that actually matters (never silently exporting
an unconfirmed cell set) is guaranteed regardless -- rather than a larger
redesign (e.g. giving every step's guidance text access to a shared
renderer) to close a purely cosmetic inconsistency in one rare path. A
future polish pass could resolve it by having `MainWindow` reuse `review_
workspace.page_size` (already backed by an open renderer) for the
guidance/status-bar text too, the same way it already reaches into
`CalibrateWorkspace.grid_page_size()` for Calibrate's status line.

`export_workspace.py`'s `ExportWorkspace` owns its own `PDFRenderer` (set
via `set_pdf()`, same pattern as every other PDF-driven workspace),
renders at `export_state.EXPORT_RENDER_SCALE` (4.0, matching the CLI's
own typical profile `render_scale` -- README: "e.g. 4 ~ 288 DPI" -- since
these are the same kind of final deliverable PNG, independent of
Calibrate's precision-click scale or Review Cards' thumbnail scale). It
has four states: blocked (not ready, or a stale snapshot, both routed
through the same centered message + a "‹ Back to Review Cards" button),
ready (card/back summary, a destination-folder picker via
`QFileDialog.getExistingDirectory`, and an Export button enabled only
once a folder is chosen), in-progress (see below), and completion (see
below).

**Export in-progress feedback and a real completion state.** The first
cut of Export ran `export_cells()` synchronously on the GUI thread and
showed nothing until it returned -- fine for the sample deck, but a large
deck gives no sign anything is happening and risks the window appearing
frozen. `_ExportWorker(QThread)` in `export_workspace.py` now runs the
exact same, unmodified `export_cells()` call off the GUI thread; nothing
about the export itself (arguments, engine call, file naming) changed,
only where it runs. While it runs, the Export and Choose Folder buttons
are disabled (`self._worker is not None` doubles as a re-entrancy guard,
belt-and-suspenders alongside the disabled button, against a double
dispatch), and an indeterminate `QProgressBar` (`setRange(0, 0)`) plus an
"Exporting N cards…" label are shown -- genuinely animated, since the GUI
thread's event loop keeps running. `_close_renderer()` (called from
`set_pdf()` when a new PDF is loaded) waits on any in-flight worker
before closing the `PDFRenderer` it's reading from, so loading a
replacement PDF mid-export can't race a close against the worker thread's
PyMuPDF calls.

On success, `ExportWorkspace._export_complete` flips the ready panel into
a distinct completion state (`_apply_completion_visibility()`): the
heading becomes "Export complete.", the destination picker/Export button
and the "‹ Back to Review Cards" footer button hide (the sidebar remains
the way back to any earlier, already-reached step, same as everywhere
else in the app -- see `sidebar.py`'s `is_reached`-driven enabling), and
an Open Folder (`QDesktopServices.openUrl` on the destination) / Start
New Deck action row appears in their place. `start_new_deck_clicked`
navigates to the Deck step exactly like the sidebar's own Deck entry --
it does not duplicate any reset logic itself; `MainWindow._on_pdf_chosen`
already clears `find_cards_state`/`calibrate_state`/`review_cards_state`
whenever a (re)loaded PDF is chosen there, which is what actually starts
a new deck over.

Known, accepted gap (same category DEVELOPER.md already documents for
`review_snapshot_is_current()` above): the guidance panel and the global
status bar do not know about `_export_complete` and keep showing "Ready
to export N cards." even right after a successful export, since neither
has (or should gain, per this file's existing reasoning) a dependency on
`ExportWorkspace`'s internal widget state. The main workspace body -- the
far more prominent surface -- correctly shows "Export complete." with the
completion actions, so this is a minor, secondary-panel inconsistency
rather than something that could mislead a user about whether the export
actually finished.

**Hardened export state across navigation.** An export operation belongs
to the deck that was loaded when it began, for as long as it runs --
never to whatever deck happens to be loaded by the time its results
arrive. `ExportWorkspace._pdf_generation` is that ownership epoch: an
`int` bumped on every `set_pdf()` call, and stamped onto each
`_ExportWorker` at dispatch time. This closes three gaps the first cut of
the in-progress/completion states above didn't handle:

- `on_shown()` no longer unconditionally resets `_export_complete` to
  `False` on every entry to Export. Instead, it leaves an active
  same-generation worker's in-progress UI (`_exporting_label`,
  `_progress_bar`, disabled Export button) untouched on a revisit, rather
  than rebuilding the ready panel over it -- which would re-enable Export
  and hide the progress bar out from under a worker still writing files
  to disk.
- `_on_export_succeeded()`/`_on_export_failed()` compare
  `self.sender().pdf_generation` (the worker whose signal is being
  handled) against the current generation and no-op on a mismatch. A
  worker abandoned via `set_pdf()` before its already-queued
  `succeeded`/`failed` signal is delivered can therefore never mark a
  *different*, later deck's Export as complete, or show its file
  count/destination -- `set_pdf()` also resets `_export_complete` and a
  `_completed_plan`/`_completed_result_message` snapshot directly,
  closing the window before the stale signal even arrives.
- A completion is now restored, not just cleared: `_show_ready()`
  compares the freshly rebuilt `ExportPlan` against `_completed_plan` (an
  `ExportPlan` is a frozen dataclass, so this is a value comparison, not
  identity). If they match, the exact `_completed_result_message` shown
  when the export finished is restored verbatim, so a plain revisit (e.g.
  a trip to Review Cards and back with nothing changed) doesn't silently
  drop the "Exported N files to `<destination>`." confirmation. If they
  don't match -- a card was toggled back in Review Cards, say -- the
  completion banner clears instead of describing a plan that's no longer
  what's on screen.

`tests/test_export_workspace.py`'s `TestExportReentry` drives a real
`PDFRenderer`/`QThread`/`export_cells()` pipeline (not a synthetic slot
call) to cover all four scenarios, since the bug this closes is
specifically about *when* a queued cross-thread signal is delivered
relative to `set_pdf()`/`on_shown()` -- see
`docs/ALPHA_HARDENING_PLAN.md` §1 risks 1, 2, and 4.

**Alpha Polish: export overwrite confirmation.** `ExportWorkspace` had no
check at all for a destination folder that already contained files
`export_cells()` was about to overwrite (e.g. re-exporting into the same
folder, or picking a folder used for a previous deck) -- `Image.save()`
just clobbers a same-named file silently. `deckforge.cell_export.
output_filenames(cell_count, has_back)` is a new small function pulling
the `front_{i:03d}.png`/`back.png` naming convention out of
`export_cells()`'s write loop into one place, so it can be reused by a
caller that needs to *predict* filenames without duplicating (and
risking drift from) the format string; `export_cells()` itself now calls
it once up front rather than formatting `front_NNN.png` inline per cell.
`deckforge_gui.export_state.existing_output_files(destination, plan)`
is the pure pre-flight check built on top of it -- which of a plan's
predicted filenames already exist in a given folder -- and
`ExportWorkspace._confirm_overwrite_if_needed()` calls it right before
dispatching the export worker (not at folder-choose time, since the
plan and the folder's contents can both still change before Export is
actually clicked). A non-empty result shows a `QMessageBox` naming the
count of files that would be overwritten, with **Cancel** as both the
default button (Enter) and the escape button (Esc / closing the dialog)
-- an accidental dismissal always lands on the safe outcome, matching
`ENGINEERING_STANDARDS.md`'s "fail safely." Choosing "Overwrite"
proceeds exactly as export already did; choosing "Cancel" (or dismissing
the dialog) leaves the destination and plan untouched so the user can
just pick a different folder and try again. The filename-prediction and
existing-file-detection functions are pure and unit tested directly
(`tests/test_cell_export.py`, `tests/test_export_state.py`); the dialog
itself is not covered by an automated test, since the project has no
widget-level test infrastructure yet (see "Regression testing" in
`docs/ALPHA_HARDENING_PLAN.md` §3, not yet implemented) -- verified
manually instead.

**Safe, non-blocking shutdown during export.** Before this, `MainWindow`
had no `closeEvent` override at all -- closing the window (title-bar X,
Alt+F4, taskbar close) while `_ExportWorker` was running let Qt tear down
the widget tree, and therefore the `QThread` it owns as a child `QObject`,
while `run()` was still live on another thread: undefined behavior in Qt,
typically a hard crash. `ExportWorkspace.is_exporting()` checks the
worker's actual `isRunning()` state, not just whether `self._worker` is
still referenced, since `self._worker` stays set for one queued
event-loop turn after `run()` returns, until `_on_export_worker_finished()`
resets it.

A first version had `closeEvent()` call `wait_for_export()` -- a blocking
`.wait()` join -- and accept the close once it returned. A manual
acceptance test against a real, large export crashed anyway. Runtime
diagnostics (thread IDs, queued-signal delivery order, and polling the
real Win32 `IsHungAppWindow()` API, the same hang check Task Manager/DWM
use) showed why: an unbounded, non-pumping `.wait()` on the GUI thread
leaves the real window genuinely Windows-hung for the entire remaining
export once it runs past Windows' ~5 second hang-detection threshold --
trivially true for any real large export -- and a hung foreground window
being force-terminated by the user or the OS is indistinguishable from a
crash. None of the signal-ordering/reentrancy hypotheses reproduced under
a real `QApplication.exec()` loop; the blocking wait itself was the
defect.

The shipped design defers instead of blocking. `MainWindow.closeEvent()`
is still a no-op when nothing is exporting -- ordinary shutdown is
completely unchanged, and this also covers the automatic second close
described below, since by then the worker is already cleared. Otherwise
it shows a `QMessageBox` with **Keep CardLift Open** (default and Escape
button, same "default to the safe/reversible choice" convention as the
overwrite-confirmation dialog above) and **Finish Export, Then Close**.
The choice lives behind `MainWindow._confirm_quit_during_export()`, its
own method (same reason `_confirm_overwrite_if_needed()` above is its
own) so tests can drive the decision directly rather than simulating a
dialog click. "Keep CardLift Open" calls `event.ignore()` and does
nothing else. "Finish Export, Then Close" sets a
`MainWindow._close_after_export` flag and calls `event.ignore()` --
never a blocking join -- so the export keeps running and the GUI event
loop stays fully responsive. `ExportWorkspace.export_finished`, a signal
emitted from `_on_export_worker_finished()` only for the current (non-
stale) worker -- i.e. strictly after whichever of
`_on_export_succeeded()`/`_on_export_failed()` applies has already run --
is what `MainWindow._on_export_finished_while_closing()` waits on instead
of polling or joining anything. On success it clears the flag and
schedules `QTimer.singleShot(0, self.close)`, a fresh close on the next
event-loop turn that the ordinary "nothing exporting" branch handles with
no special-casing. On failure it just clears the flag: the window stays
open and `_on_export_failed()`'s existing message is what the user sees,
rather than the failure being concealed by quitting anyway. A repeat
close attempt while a close is already deferred is silently ignored --
no second dialog, no second pending request. No cancellation exists once
"Finish Export, Then Close" has been chosen -- confirmed as an
intentional alpha scope decision, not an oversight.

A second race turned up in review before this shipped:
`_confirm_quit_during_export()`'s `QMessageBox.exec()` runs a real nested
event loop, so the export can finish -- and `export_finished` can already
have fired, back while `_close_after_export` was still `False` -- before
the user answers the dialog. Naively arming the deferred-close flag on
that stale assumption would wait forever on a signal that already came
and went. `closeEvent()` re-checks `is_exporting()` immediately after
`_confirm_quit_during_export()` returns `True`: if the export is already
done, it closes immediately via the ordinary no-export path instead of
deferring.

This closes the crash risk for *normal in-app shutdown* only, and is
documented that narrowly: it says nothing about, and does not make export
writes atomic against, a forced process kill (Task Manager), an OS
shutdown/logoff that terminates the process outside Qt's close machinery,
or a mid-write `OSError` (unchanged, still handled by `_ExportWorker.run()`'s
existing `except (OSError, PDFRenderError)`). `tests/test_main_window.py`
drives a real `QApplication.exec()` loop with a deliberately delayed
`export_cells()` pipeline (a synthetic direct `closeEvent()` call, used by
an earlier version of this test file, cannot detect an unresponsive GUI
thread at all) and covers: no dialog when nothing is exporting; Keep
CardLift Open leaves the worker running and ignores the close; a worker
object left referenced but no longer running (the exact race
`is_exporting()` is defined against) does not trigger the confirmation; a
periodic `QTimer` keeps ticking throughout a real, multi-second delayed
export, proving the GUI thread was never blocked, and the window only
actually closes -- with the real `export_cells()` output file verified on
disk -- once that export finishes; repeated close attempts while deferred
do not stack dialogs or closes; an export that completes while the
confirmation dialog's own nested loop is still pumping events, before the
user answers it, closes immediately rather than arming a deferred close
that would never be released; a failed export leaves the window open
and clears the pending close; and `QThread.wait()` is asserted to never
be called on the worker from `closeEvent()` or the deferred path. Same
real `PDFRenderer`/`QThread`/`export_cells()` pattern `TestExportReentry`
established, no `pytest-qt` needed. See `docs/ALPHA_HARDENING_PLAN.md` §2.

## Common Commands

All commands go through `extract.py` and require `--profile <name>`
(the JSON file in `profiles/`, without `.json`). Everything below
assumes the venv is activated. Full flag reference: `python extract.py --help`.

### `--preview`

```powershell
python extract.py --profile demo_deck --preview
```

Renders `first_front_page` only, crops its cards, and writes
`preview/calibration_overlay.png` (blue = raw grid cell, red = the
actual saved crop) plus a per-page contact sheet
(`preview/page{N}_preview.png`). **Use this first, and most often** —
it's the main calibration loop: change a value in the profile JSON, run
`--preview`, look at the overlay, repeat.

### `--overlay`

```powershell
python extract.py --profile demo_deck --overlay
python extract.py --profile demo_deck --overlay --page 3
```

Same blue/red overlay as `--preview`, but for one page only, without
re-cropping everything or rebuilding a contact sheet. Use this to check
a specific page fast — most usefully the back page (`--page` with the
profile's `back_page` number), which `--preview` doesn't cover.

### `--inspect CARD_NUM`

```powershell
python extract.py --profile demo_deck --inspect 1
# → preview/inspect_card001.png
```

Exports one card at high zoom with the raw cell and trimmed crop drawn
on it, plus surrounding page context. `CARD_NUM` is 1-indexed, matching
`front_NNN.png` numbering. Use this when the full-page overlay is too
small to tell whether a trim is off by a couple of points, or to
recheck one specific card (e.g. the last on a page, in case of
cumulative drift).

### `--calibrate`

```powershell
python extract.py --profile demo_deck --calibrate
python extract.py --profile demo_deck --calibrate --page 3
```

Opens an interactive window on the rendered page: click a card's
upper-left then lower-right corner (and optionally a neighboring card,
to derive gap too), and it shows a "Copy Calibration Settings" button
plus, tucked behind an optional "Technical Details" toggle, the same
old→new patch that `--measure` prints. **This is the recommended
starting point for calibrating a brand-new deck** — no pixel-reading by
hand. It never writes to the profile itself; you paste the values in
yourself. Use it instead of `--measure` unless you're scripting or
already have pixel coordinates from another tool.

The window supports mouse-wheel zoom (anchored under the pointer), a
persistent **Pan** toggle button, Spacebar+left-drag or middle-drag pan,
"Fit to Window"/"100%" view buttons, and a **Crosshair** toggle that
draws full-canvas guide lines through the pointer — see README's "Zooming
and panning for precise clicks" and "Crosshair". These only change what's
on screen; every
click is converted from canvas (screen) pixels to rendered-image pixels
exactly once, at the point of the click, via `ViewTransform` in
`calibrate_ui.py`, so the same corner clicked at any zoom/pan/window-size
produces the same measurement. Mouse-wheel input is normalized to a
`-1`/`0`/`+1` direction (`wheel_direction()`) instead of trusting the raw
`event.delta` magnitude, since Windows and macOS report wildly different
scales for the same physical scroll — this is the one place that needs to
reason about platform differences, and it's a pure function rather than a
`sys.platform` branch. All of this — `ViewTransform`, the wheel-direction
normalization, and the pan-vs-click gesture decision
(`is_pan_gesture()`) — is plain Python with no Tkinter dependency, unit
tested in `test_calibrate_ui.py` without opening a window.

**Pan mode.** `is_pan_gesture(button, space_held, pan_mode)` is the single
decision point for whether a left press pans or clicks — it accounts for
persistent Pan mode (the button), temporary Spacebar hold, and the
always-pan middle button. `CalibrationWindow._pan_mode` is only turned off
by clicking Pan again or Escape (`pan_mode_after_escape()`); losing focus
or releasing Spacebar clears _temporary_ pan state only
(`cleared_temporary_pan_state()`), leaving a deliberately-selected Pan
mode alone. Pan mode changes only how the page is viewed, never a
calibration value — clicking Pan on/off, panning, or zooming never
touches `self.measurements`.

**Crosshair.** A discoverable calibration aid, on by default, toggled by
the **Crosshair** button next to Pan (same sunken/raised button treatment
as Pan). While enabled and the pointer is over the canvas, two reusable
canvas line items — one horizontal, one vertical, created lazily on first
`<Motion>` and moved/hidden/shown afterward rather than recreated every
event — are drawn through the pointer, spanning the full canvas. They
live entirely in canvas space (`crosshair_display_position()` returns a
canvas (x, y) or `None`) and are deliberately **not** added to
`self._overlay_ids`, so `_redraw_overlays()` never deletes them; instead
`_raise_crosshair()` runs after every image/overlay redraw to keep them
on top of newly (re)created items. `crosshair_display_position()` and
`coordinate_readout_position()` (for the small "X 1234 Y 5678" readout
next to the zoom percentage, in rendered-image pixels) both fold in
`pan_active()` — true for persistent Pan mode, a temporary Spacebar hold,
or an active pan drag — so every caller (pointer motion, leaving the
canvas, a resize, a pan-mode change) asks one function "where, if
anywhere" instead of re-deriving the visibility rule. `Start Over` and
`Escape` route the toggle's value through identity functions
(`crosshair_enabled_after_reset()`, `crosshair_enabled_after_escape()`)
purely so that invariant — neither ever touches the Crosshair preference
— has a named, unit-tested home, matching `pan_mode_after_escape()`'s
existing style. Like the rest of this section, none of it touches
`self.measurements` or any image-space calibration math.

**Responsive viewport.** The canvas is laid out with Tkinter grid
row/column weights so it expands to fill whatever space the window is
given, instead of being capped at a fixed pixel size — `MAX_DISPLAY_WIDTH`
/ `MAX_DISPLAY_HEIGHT` now only seed the window's _initial_ size. The
canvas's `<Configure>` event (fired on resize/maximize) is debounced
(`RESIZE_DEBOUNCE_MS`) and ignores degenerate sizes below
`MIN_VIEWPORT_DIM`, so a window-border drag doesn't repeatedly re-crop the
full-resolution source image, and the first render never happens against
a placeholder 1×1 canvas. `recompute_view_for_resize()` is the single pure
function deciding what happens to the view on resize: in Fit-to-Window
mode it recalculates the fit for the new canvas size
(`CalibrationWindow._fit_mode`, set by "Fit to Window" and cleared by
"100%"/manual zoom); otherwise it preserves scale and keeps the image
point at the old viewport's center under the new viewport's center
(`ViewTransform.recentered_for_resize()`) before clamping. Like the rest
of `ViewTransform`, these are unit tested without opening a window.

### `--measure`

```powershell
python extract.py --profile demo_deck --measure --card r0c0:240,420,960,1360
python extract.py --profile demo_deck --measure \
  --card r0c0:240,420,960,1360 --card r0c1:1000,420,1720,1360
```

The non-interactive sibling of `--calibrate`: give it pixel coordinates
you already read off a rendered `--preview`/`--overlay` image (e.g. in
an image viewer with a coordinate readout), and it converts them into a
suggested `left`/`top`/`card_width`/`card_height`/`gap_x`/`gap_y` patch.
Pure arithmetic — it never renders, crops, or touches the profile. Use
it when you're doing calibration headless/scripted, or already have
coordinates on hand and don't want to open the interactive window.

### `--export`

```powershell
python extract.py --profile demo_deck --export
# → output/front_001.png ... output/front_NNN.png, output/back.png
```

The real deal: exports every card front across
`[first_front_page, last_front_page]` plus the back, to `output/`. Run
this once a profile is calibrated (red boxes in the overlay sit exactly
on card edges) and you actually want the images — e.g. to import into
PlayingCards.io or Tabletop Simulator.

### `--contact-sheet`

```powershell
python extract.py --profile demo_deck --contact-sheet
# → preview/contact_sheet.png
```

Builds one tiled, labeled QA image from everything currently in
`output/` (every exported front, in order, plus the back). Use this
right after `--export` to eyeball the _entire_ deck at once before
importing it anywhere — catches things a single-card inspect would
miss, like one page's grid drifting relative to the others.

## Typical Development Workflow

1. Pull latest changes (once this repo has a remote — not yet applicable).
2. Activate the virtual environment (`.venv\Scripts\Activate.ps1`).
3. Run the test suite (`pytest`) to confirm you're starting from a clean baseline.
4. Implement the feature or fix, in small increments.
5. Run the test suite again — don't let a broken test linger while you keep coding.
6. Test manually: run the relevant `extract.py` command(s) against
   `sample_decks/CardLift_Demo_Deck.pdf` (or another real PDF) and look
   at the actual output/preview images. CardLift is an image tool —
   passing tests don't guarantee the crop looks right.
7. Commit (see "Git Workflow" below).
8. Repeat from step 4 for the next increment.

## Git Workflow

- **`git status`** — run this constantly, especially before anything
  destructive. It's the cheapest way to know what you're about to
  commit (or about to lose).
- **`git add .`** — stage everything you've changed. Fine for this
  project's size, but check `git status` output first if you've been
  experimenting with throwaway files (e.g. scratch PDFs or output
  images) you don't want committed.
- **`git commit`** — commit once a change is a coherent, working unit
  (a passing test suite, a working command). Write a message that says
  _why_, not just _what_ — the diff already shows what changed.
- **`git log --oneline`** — use this to reorient yourself at the start
  of a session, or to check whether a change you're about to make
  duplicates something already done. This project's existing log
  (`git log --oneline`) is a good model for commit message style —
  short, milestone-based, present tense.
- **Version bump.** `deckforge.__version__` (`src/deckforge/__init__.py`)
  is the single authoritative version string — the GUI's window title and
  `TopBar` label both read it directly rather than carrying their own
  copy. Bump the pre-release number (e.g. `0.1.0-alpha` → `0.1.0-alpha.2`)
  each time a build goes out for alpha testing, so a bug report can be
  tied to the exact build it came from. See `docs/ALPHA_HARDENING_PLAN.md` §5.

## Project Structure

```
CardLift/
├── extract.py              # CLI entry point — thin, delegates to src/deckforge
├── gui_app.py               # GUI entry point — thin, delegates to src/deckforge_gui (Phase II prototype)
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt     # Runtime + test dependencies (pytest)
├── requirements-gui.txt     # Runtime + PySide6, for the GUI shell prototype
├── pyproject.toml           # pytest config (test paths, src layout)
├── README.md                 # Product/conceptual docs: what CardLift is, grid math, calibration model
├── DEVELOPER.md              # This file — day-to-day mechanics of working on the repo
├── profiles/                 # One JSON calibration file per deck (e.g. demo_deck.json)
├── sample_decks/              # Source PDFs live here (e.g. CardLift_Demo_Deck.pdf)
├── output/                    # --export writes front_NNN.png / back.png here
├── preview/                    # --preview/--overlay/--inspect/--contact-sheet write here
├── src/deckforge/
│   ├── profile.py             # DeckProfile: schema, JSON loading, validation (layouts list + legacy normalization -- see README "Profiles")
│   ├── pdf_renderer.py         # PyMuPDF page → Pillow image + page_size() (only file that imports fitz)
│   ├── geometry.py             # Pure grid math: cell box → trimmed box → pixels (no I/O)
│   ├── cropper.py              # CardCropper: renders + geometry → cropped card images
│   ├── contact_sheet.py         # Tiles a list of images into a labeled QA sheet
│   ├── exporter.py              # DeckExporter: orchestrates preview/export/overlay/inspect/contact-sheet
│   ├── measure.py               # --measure: pixel coords → suggested profile patch (no rendering)
│   ├── calibrate_ui.py          # --calibrate: interactive click-to-measure window
│   ├── cell_export.py           # export_cells(): explicit ordered cell list → PNGs, no CardLayout/DeckProfile involved
│   └── cli.py                   # argparse wiring — the only file that knows about CLI flags
├── src/deckforge_gui/            # PySide6 desktop app (Phase II)
│   ├── app_state.py              # Pure navigation/state model — no PySide6 import, unit tested directly
│   ├── session.py                # Pure DeckSession/DeckLoadError model — loaded PDF, via engine's PDFRenderer
│   ├── theme.py                  # Shared color palette (dark nav chrome, light PDF workspace, purple accent)
│   ├── main_window.py            # MainWindow: assembles top bar/sidebar/toolbar/workspace/guidance/status bar
│   ├── sidebar.py                # Fixed-width workflow sidebar
│   ├── guidance_panel.py         # Collapsible right-hand guidance panel
│   ├── calibrate_toolbar.py      # Fit/Zoom/Pan toolbar shown above the Calibrate workspace
│   ├── calibrate_state.py        # Pure CalibrateState/CalibrationTarget model -- two-corner-click geometry, in PDF points
│   ├── calibrate_workspace.py    # Calibrate page (Cards/Shared Back): PDF canvas, click handling, zoom/pan, overlays
│   ├── view_transform.py         # Ported ViewTransform + pure zoom/pan/fit math (from calibrate_ui.py), shared GUI infra
│   ├── deck_workspace.py         # Deck page: drag-and-drop/click-to-browse PDF drop zone
│   ├── find_cards_state.py       # Pure FindCardsState/PageRole/SharedBackStatus model -- per-page Front/Back roles
│   ├── find_cards_workspace.py   # Select Card Pages workspace: PDF page-by-page preview + role toggle buttons
│   ├── review_state.py           # Pure ReviewCard/ReviewCardsState model -- suggested-grid cards, include/exclude toggle
│   ├── review_workspace.py       # Review Cards workspace: per-page card thumbnail grid, Shared Back preview, toggles
│   ├── export_state.py           # Pure ExportPlan/export_ready() model -- built from Review Cards' approved cells
│   ├── export_workspace.py       # Export workspace: summary, destination folder picker, Export action, result message
│   └── workspaces.py             # Central workspace per workflow step
└── tests/                        # pytest suite, mirrors the src/deckforge module split
```

The module split is deliberate and worth preserving: each file has one
job, so a future change (a new PDF backend, an auto-calibrator, a new
export target) should only ever touch one or two files. See README's
"Why split this way" for the reasoning — read it before restructuring
anything in `src/deckforge/`.

## CLI Output Conventions (`cli.py`)

`cli.py` carries two presentation conventions on top of parsing args —
both are UI-only and don't touch `exporter.py`/`geometry.py`/etc.:

- **"Next:" nudges.** Every successful command ends with a line
  suggesting the next command in the calibrate → preview → export →
  contact-sheet chain (e.g. `--preview` suggests `--export` once the
  overlay looks right). If you add a new mode flag, give it one too —
  say what a first-time user would naturally do with the output.
- **`friendly_error()`.** Every raised `ProfileError` / `PDFRenderError`
  / `ExportError` / `GeometryError` / `MeasureError` is caught in
  `main()` and passed through `friendly_error()`, which matches on
  substrings of the exception's existing message to prepend a plain-
  language cause + "Next step:", then prints the original message
  underneath as `Details:`. This means the underlying modules never
  need to know about presentation — they just keep raising the same
  clear, specific messages they already do — but it also means
  `friendly_error()`'s substring matches can go stale if you reword an
  exception message without checking `friendly_error()`'s branches for
  it (see `cli.py`'s docstring on that function). Anything not matched
  falls back to a generic sentence rather than erroring.
  `except Exception` in `main()` is the last resort for truly
  unanticipated failures (a bug, a corrupt PDF) — it prints a short
  notice plus the full traceback under `Details:`, so nothing surfaces
  as a bare, unexplained crash.
- **`format_export_summary()`.** `--export`'s completion message (card/
  back counts, pixel size, output location, and a suggested next step)
  is built from the list of files `DeckExporter.export()` already
  returns — no export logic changed to support this, it's pure
  after-the-fact description.

## Claude Code Workflow

How we expect Claude Code to be used on this project:

- **Review architecture before major changes.** Re-read the "Why split
  this way" section of README.md (and this file's "Project Structure")
  before adding a new module or changing responsibilities between
  existing ones. The module boundaries exist to keep future features
  additive rather than disruptive — don't blur them for convenience.
- **Keep commits small and milestone-based.** Match the existing log
  style (`git log --oneline`): each commit should be one coherent,
  working step, not a bundle of unrelated changes.
- **Add tests for new logic.** Especially anything in `geometry.py` or
  `measure.py` — pure functions with no I/O are cheap to test
  thoroughly and expensive to get subtly wrong (see README's note about
  the per-card rounding-drift bug caught this way).
- **Update documentation when commands or workflows change.** If a CLI
  flag's behavior changes, or a new one is added, update README.md
  (conceptual/how-it-works) and this file (DEVELOPER.md) in the same
  change — not as a follow-up.
- **Preserve the vision of making CardLift easy for non-technical
  users.** The manual-calibration-only design, the `--calibrate`
  interactive window, and the blue/red overlay convention all exist to
  make an inherently fiddly task (aligning a crop grid) forgiving and
  visual rather than requiring someone to read PDF point math. Favor
  changes that keep that experience simple and visual over ones that
  add power at the cost of clarity.

## Phase II GUI Development

Before implementing GUI changes, review the following:

1. Read CORE_CONCEPTS.md
2. Read the relevant UI documents
3. Read ENGINEERING_STANDARDS.md
4. Read DEVELOPER.md

The mockups are design specifications, not pixel-perfect implementation
requirements.

When implementation constraints require compromise, preserve the workflow,
information hierarchy, and overall user experience over exact appearance.

The purpose of the GUI is to make the engine approachable for tabletop
gamers, not to expose implementation details.

## Workflow Completion

A milestone is not complete simply because its primary functionality has been implemented.

Before considering a workflow complete, verify:

- How the user enters the workflow.
- How the user knows they are making progress.
- How the user knows they have finished.
- What the obvious next action is.
- How the next workflow step becomes available.
- How the user returns to this workflow later.

Avoid leaving users in dead-end states where the functionality is complete but the application does not clearly communicate what to do next.

## UX Validation

Implementation is not considered complete until the developer has personally exercised the workflow.

Repository analysis and unit tests cannot replace interactive evaluation.

After implementation:

- perform the workflow
- note anything surprising
- fix obvious UX issues before considering the milestone complete

## First-Time User Review

Before declaring a milestone complete, mentally walk through the workflow as a first-time user.

Assume the user has not read the documentation and does not know the internal architecture.

Review:

- terminology
- guidance text
- page numbering
- status messages
- visual hierarchy
- navigation
- completion messaging

If the implementation is technically correct but could reasonably mislead a first-time user, treat that as a UX issue rather than expected behavior.

## Design Philosophy

When improving CardLift:

- Observe user friction first.
- Describe the problem, not the solution.
- Ask Claude Code to think like a first-time user.
- Review the proposed improvements before implementation.
- Test the workflow again.

## Maintaining This Document

Whenever new commands, workflows, or development practices are added to
CardLift, please update DEVELOPER.md as part of the same change.
