# Calibration Geometry Investigation

Status: **implemented.** Requested after alpha testing across multiple
real PnP PDFs found that different choices of calibration cards
systematically produce different final grids (bleed, row/column clipping,
error that grows with distance from the calibrated card). This document
traces the math end to end, explains the root cause(s), and ends with the
recommended smallest-coherent fix, which has since been implemented in
`deckforge_gui/calibrate_state.py` and `calibrate_workspace.py` (see
"Recommended smallest coherent change" below for what shipped and what's
still a follow-up).

_This document reflects the repository state at the time it was written
and is preserved for historical context; see `docs/RELEASE_READINESS.md`
for current status._

---

## 1. How row/column spacing is computed

`src/deckforge/geometry.py::cell_box()` — the *only* place a card's
position is ever computed, for calibration overlays, Review Cards
thumbnails, and the final export crop alike:

```python
x0 = left + col * (card_width + gap_x)
y0 = top  + row * (card_height + gap_y)
x1 = x0 + card_width
y1 = y0 + card_height
```

`left`/`top` place card `(row=0, col=0)`. Every other cell is `left`/`top`
plus a **constant pitch** (`card_width + gap_x`, `card_height + gap_y`)
multiplied by its row/col index. This is a direct multiplication from a
single fixed origin, computed independently per cell — not an iterative
"add the pitch repeatedly" loop. **Floating-point accumulation is not a
contributor here**: there is no repeated addition to drift, and float64
error at this scale (~1e-13 relative) is many orders of magnitude below
anything visible in a print. The "error grows with row/col" pattern you're
seeing has a different cause (below) that happens to look similar.

## 2. How calibration clicks become a complete grid

Two-corner clicks are captured in `deckforge_gui/calibrate_state.py`
(GUI) using the same math as the CLI's `--measure`
(`src/deckforge/measure.py::derive_geometry()`):

1. **First card** (one corner-pair click) directly sets `card_width` /
   `card_height` — literally `x2 - x1` / `y2 - y1` of that one box. This
   size is then used for **every card in the deck** (see "One shared
   layout" below).
2. **Second card (optional)** — if you click a neighbor, `infer_second_cell()`
   works out its `(row, col)` from displacement, then `derive_geometry()`
   solves for gap **only along the axis the two cards actually differ
   on**:
   ```python
   if b.col != a.col: gap_x = (bx0 - ax0) / (b.col - a.col) - card_width
   if b.row != a.row: gap_y = (by0 - ay0) / (b.row - a.row) - card_height
   ```
3. `left`/`top` are back-solved from the first card's position so that
   `cell_box(0, 0)` reproduces it exactly:
   `left = ax0 - a.col * (card_width + gap_x)`.
4. That single `(left, top, card_width, card_height, gap_x, gap_y)` tuple
   — `CalibratedGeometry` — is then extrapolated by `cell_box()` to *every*
   `(row, col)` on *every* Front Page, with no per-page or per-cell
   adjustment. `suggested_grid()` uses the same pitch to guess how many
   rows/cols fit a page (for Review Cards to confirm/trim by whole
   cards), but the crop geometry itself never changes based on that guess.

**Critical, currently-silent detail:** `derive_geometry()`'s signature is

```python
def derive_geometry(measurements, scale, fallback_gap_x: float = 0.0, fallback_gap_y: float = 0.0)
```

`calibrate_state.py::_finalize()` calls it with **no fallback override**,
so any axis that wasn't pinned by two differently-positioned cards —
which is *every* axis when you finish with one card, and *one* axis
whenever your second card shares a row or a column with the first —
is silently assumed to be **exactly 0.0 (edge-to-edge)**.

`CalibratedGeometry` does carry `gap_x_derived` / `gap_y_derived` booleans
recording whether an axis was actually measured versus defaulted — but
grepping the whole GUI layer confirms **nothing reads them**. The
information needed to warn the user already exists and is thrown away.

## 3. What the algorithm assumes

- **Perfectly rectangular, axis-aligned grid** — no rotation/skew term
  anywhere in `cell_box()`.
- **Exactly one card size for the entire deck.** `calibrate_state.py`'s
  own module docstring ("ONE SHARED LAYOUT") confirms this is
  intentional: all Front Pages share a single `CalibrationTarget`,
  calibrated from whichever one page you happened to click on. A second
  page with even slightly different margins/print drift is never
  detected or compensated.
- **Constant pitch on each axis** (`card_width+gap_x`, `card_height+gap_y`),
  derived from **at most one pair of points per axis**, then extrapolated
  arbitrarily far in both directions with no correction term.
- **An unmeasured axis's gap is exactly 0.0.** Not a neutral placeholder —
  a specific, frequently-wrong assumption (edge-to-edge), applied
  silently.
- **No accumulated floating-point stepping** — ruled out in §1; each
  cell is computed directly from the origin, not iteratively.
- **No safety margin.** The GUI calibration flow deliberately sets trim
  to zero everywhere it crops (`_ZERO_TRIM` in `cell_export.py`,
  `review_workspace.py`) — the docstring rationale is "the two-corner
  click already *is* the exact crop box." That's true for card size, but
  it also means there is **no cushion** to absorb any residual pitch
  error: any systematic bias shows up immediately as clipping or bleed,
  with nothing to soften it. The CLI's older `trim_*` fields existed
  partly to absorb exactly this kind of small discrepancy; the GUI
  workflow removed that safety valve when it made calibration "exact."
- **Review Cards cannot catch this.** It's the one designed checkpoint
  before export, but it only lets a human include/exclude whole
  suggested cells — it re-crops each thumbnail from the same `cell_box()`
  geometry, so a systematic pitch error is *visible* in the thumbnails if
  you look closely, but there is no mechanism to correct the geometry
  itself from that screen. A bad gap ships to every included card.

## 4. Why different calibration choices produce different grids

Two distinct, additive effects, both traceable to the exact math above:

**Effect A — the silent 0.0 fallback (implementation bug).** This alone
explains three of your four observed patterns:

| Calibration | Axes measured | Axes defaulted to 0 | Predicted symptom | Matches your report |
|---|---|---|---|---|
| One card | none | both `gap_x`, `gap_y` | bleed on whichever axis truly has a nonzero gap | "substantial bleed" ✅ |
| Same row | `gap_x` | `gap_y` | row 0 fine (its row-multiplier is 0, so `gap_y` never enters the math); row 1+ increasingly wrong, since `gap_y`'s error is multiplied by the row index | "first row acceptable, second row clips bottoms" ✅ |
| Same column | `gap_y` | `gap_x` | column 0 fine; farther columns increasingly wrong | "generally better, opposite column still clips" ✅ |
| Diagonal | both `gap_x`, `gap_y` | neither | should be materially better than the above three | "best overall" ✅ |

This is the single biggest lever: whichever axis you don't measure gets
assumed edge-to-edge, and because that assumed pitch is then multiplied
by the row or column index, the resulting position error is exactly zero
at the calibrated card and grows linearly with distance from it — which
is precisely "errors that accumulate across rows or columns" from your
report. It isn't float accumulation; it's a **fixed per-cell pitch error
scaled by cell index**, which looks the same to the eye.

**Effect B — adjacent-click amplification (a second, independent cause,
still present even when both axes ARE measured).** Look at the gap
formula again:

```python
gap_x = (bx0 - ax0) / (b.col - a.col) - card_width
```

The denominator is however many columns apart your two clicked cards
are. The calibration UI's own hint system (`predicted_neighbor_box()` in
`calibrate_state.py`) only ever suggests the *immediately adjacent* card
("right" or "below," one cell away), and `infer_second_cell()` rounds any
click to the nearest single-cell offset — nothing about the UI encourages
or even hints at clicking a farther-apart second card. That means the
denominator in practice is almost always **1**. Any small click-precision
error (a pixel or two at typical zoom) or any genuine tiny non-uniformity
in how the source PDF was laid out — extremely common in
hand-assembled/tool-generated PnP sheets, where card pitch is rarely
mathematically exact to the point — gets divided by 1 and then
re-multiplied by every column's index when extrapolated outward. This is
a textbook **short-baseline slope-fit problem**: fitting a line's slope
from two points that are close together massively amplifies any noise in
those two points; fitting from two points far apart is far more robust to
the same noise.

This is the most likely explanation for **why even your best case (diagonal)
still clips the second column** — if that diagonal pair was two adjacent
cells (e.g. `r0c0` and `r1c1`, which is what the UI naturally nudges you
toward), the derived `gap_x`/`gap_y` still carry whatever small
measurement/print noise existed in those two specific points, just
undiluted by any averaging across the rest of the grid, and that error
still scales with distance from the calibrated pair — worst at the far
corner, which is exactly "second column" on the kind of narrow grids
you're testing.

## 5. Is this expected from the current algorithm?

**Yes — deterministically, not randomly.** Given the exact two cells you
click, the resulting geometry (and its error at every other cell) is
fully determined by the formulas above. That determinism is *why* the
pattern reads as systematic rather than noisy: the same calibration
strategy on the same PDF will reproduce the same clipping every time, and
different strategies produce different, individually-predictable error
shapes — which is exactly what your testing found.

## 6. Bug, mathematical limitation, or implementation mistake?

**Both, cleanly separable, and neither requires abandoning the model:**

- **Effect A (silent 0.0 gap fallback) is a straightforward implementation
  mistake**, not a limitation of the underlying math. The code already
  computes whether each axis was actually measured
  (`gap_x_derived`/`gap_y_derived`) and already has a `fallback_gap_x`/
  `fallback_gap_y` parameter built for exactly this — it's just never
  wired to anything other than its silent 0.0 default. This fully
  explains one-card, same-row, and same-column calibration's specific
  symptoms.
- **Effect B (adjacent-click amplification) is a real mathematical
  property of a two-point linear fit**, not a coding bug — but it's
  fully addressable *within the current architecture* by changing which
  second card the workflow encourages/accepts, not by changing the
  underlying grid model.

**Is the uniform-pitch lattice model itself mathematically incapable of
producing consistent results for common printable PDFs?** No — not based
on the evidence gathered here. CardLift's stated scope
(`README.md`: "fixed grid of cards") is decks that *are* laid out as a
true uniform grid by design; a rigid lattice is the right model for that
input class, and the CLI side of this codebase (hand-typed profiles) has
apparently worked fine for a while on the same model. Everything observed
in this alpha round is fully explained by Effect A and Effect B, both of
which are properties of *how the two calibration points are chosen and
used*, not evidence that a uniform grid can't be fit accurately from good
points. If, after fixing both effects, a diagonal calibration using two
*widely separated* cards still shows systematic clipping on a given PDF,
that would be real evidence of genuine per-card non-uniformity in that
specific print source — a different, harder problem (would need
per-cell/auto-detection, which the README explicitly and deliberately
excludes from this product's MVP scope) — but nothing gathered so far
requires reaching for that conclusion yet.

---

## Recommended smallest coherent change (implemented)

Both parts preserve the existing one-or-two-click workflow, the
`GridGeometry`/`cell_box()` architecture, and the "manual calibration
only" product principle. Neither adds a new step or a new UI screen.

**1. Stop silently defaulting an unmeasured axis's gap to 0.0. — Shipped.**
`gap_x_derived`/`gap_y_derived` already existed and were already computed
— they were just discarded. `ungauged_axis_warning()`
(`calibrate_state.py`) now surfaces them: when calibration finishes with
an axis still defaulted (one-card finish, or a same-row/same-column
second click), the completion banner and guidance/status text say so
explicitly ("Spacing between columns and rows wasn't measured, so
CardLift assumed cards sit edge-to-edge. If cards look clipped in Review
Cards, click Start Over and measure a second card farther away instead of
finishing with one."), pointing at the already-existing Start Over
control. The warning only fires when the axis actually has more than one
cell (per `suggested_grid()`), so a genuine one-row, one-column, or
single-card deck — where that axis's spacing is never used — never sees
a spurious warning. Covered by `TestUngaugedAxisWarning` in
`tests/test_calibrate_state.py`.

**2. Make the suggested second card farther from the first, not
adjacent. — Shipped.** `predicted_neighbor_box()` previously only ever
hinted at the immediately-adjacent cell. Since Effect B shows the gap
estimate's error is inversely proportional to how far apart the two
measured cells are, `suggested_second_card_offset()` now estimates how
many cells roughly fit across the page (reusing the existing
`_fit_count()` grid-size math) and the hint is drawn that far away
instead — e.g. near the opposite edge of the visible grid, not the next
cell over — capped at `_MAX_SUGGESTED_OFFSET` (6 cells) so a tiny card on
a huge page doesn't suggest something off-screen. `infer_second_cell()`
needed no change: it already derived a click's real `(row, col)` from
wherever the user actually clicked, not from the hint, so it was never
actually limited to adjacent cells — only the drawn hint was. Covered by
`TestSuggestedSecondCardOffset` and the new `cells_away` cases in
`TestPredictedNeighborBox`.

**3. Guide users toward a consistent crop-boundary reference point. —
Shipped**, addressing a related finding from alpha testing (clicking a
cutting guide when present vs. the card's printed edge when absent):
Calibrate's first-corner and opposite-corner guidance text
(`app_state.py`'s `GUIDANCE`/`STATUS`, and `calibrate_state.py`'s
"opposite corner" copy) now explicitly names the cutting-guide-if-present,
otherwise-outer-edge rule, and tells the user to use the *same* reference
point for both corners of the card they calibrate on.

**Not implemented (deliberately out of scope for this pass):** the CLI's
own `--calibrate` window (`src/deckforge/calibrate_ui.py`) has a
structurally identical `predicted_neighbor_box()`/silent-fallback issue —
it's a separate Tkinter port, not shared code with the GUI. DEVELOPER.md
already documents the CLI engine as stable, and the GUI is the surface
`RELEASE_READINESS.md` #1 was raised against, so the CLI fix is left as a
follow-up rather than folded into this pass.

**Immediate, zero-code mitigation for continued alpha testing (now
superseded by (2) above, kept for historical context):** until either fix
shipped, calibrating with two cards that are **far apart**
(e.g. opposite corners of the visible grid) rather than adjacent
neighbors measurably reduced the residual error, since nothing in
`derive_geometry()` actually requires the two
measured cells to be neighbors — that's purely a UI hinting convention,
not a math constraint.

---

## Addendum: grid-inference conflict detection (Doom Pilgrim, implemented)

A distinct, later finding — **not** a variant of Effects A or B above.
Effects A and B are *continuous magnitude* errors: the inferred `(row,
col)` was always correct, and only the derived `gap_x`/`gap_y` value was
off by some amount that grew with distance. This finding is a *discrete*
error: `infer_second_cell()` assigns the **wrong cell** before any gap
math even runs, because `round(dx / card_width)` and `round(dy /
card_height)` implicitly assume the real gap is small relative to the
card. On a real reproduction PDF ("DP Pocket 20 pages for centered
bothsided print.pdf") with a 3×3 grid and a genuine two-column click —
upper-left card at internal `(0,0)`, lower-right at intended `(2,2)` —
the deck's real `gap_x` (~40.6pt) is ~27% of `card_width` (149.5pt),
just over the `1/(2·2) = 25%` threshold at which `round(dx/card_width)`
tips from 2 to 3. The result: the second card was silently labeled
`(2,3)` instead of `(2,2)`, and Review Cards suggested 12 cells in a
3×4 layout instead of 9 in the correct 3×3.

**Why this can't be fixed by a smarter rounding rule.** For *any*
candidate integer offset `n`, `derive_geometry()`'s
`gap = (bx0-ax0)/n - card_width` reproduces the two clicked points
**exactly**, by construction — there is no formula that recovers a
unique `(interval count, gap)` pair from two boxes alone; page bounds
narrow the plausible range but do not resolve it in general (both `n=2`
and `n=3` are independently page-bounds-plausible for this exact deck).
This is a genuine information shortfall, not a tuning problem — the only
way to close it is to ask.

**The fix: cross-check the click against the independent hint, not a
tuned ratio threshold.** `CalibrateWorkspace` already computes
`suggested_second_card_offset()` — a page-bounds estimate, derived from
card size and page dimensions alone, entirely independent of where the
second click lands — to draw the farther-card hint from fix (2) above.
`infer_second_cell()` (`calibrate_state.py`) now accepts that same value
as an optional `hint_col_offset`/`hint_row_offset`, passed through
`CalibrateState.record_click()` as plain data (page bounds live behind
`PDFRenderer`, which `calibrate_state.py` deliberately never imports —
see this module's docstring). For each axis the second card actually
differs on, if the click-derived offset and the hint-derived offset
**agree**, the click is used exactly as before, automatically — this is
still the overwhelming common case, since guidance already nudges users
toward the hinted card. If they **disagree**, `infer_second_cell()`
returns `None`, which `record_click()` already turns into
`ClickOutcome.NEEDS_CELL_LABEL` — the same clarification prompt that has
always handled an ambiguous (near-identical) click. No new dialog, no new
workflow step, no tunable "how close to a rounding boundary" margin: the
check is an equality comparison between two independently-derived
integers.

An axis whose click-derived offset is `0` (a same-row or same-column
measurement) is never checked against the hint, even if the hint's value
for that axis is nonzero — the hint is drawn for a *general* two-axis
suggestion, and a same-row/-column click never touched that axis at all.

**What this guarantees, and what it doesn't.** Agreement between the two
estimates is treated as sufficient confidence to proceed automatically —
it is **not** proof the resulting label is correct. Both estimates share
the same "gap is small enough not to matter" assumption, and it is
possible (if unlikely) for both to be wrong in the same way at once, in
which case this change provides no protection. What it does guarantee is
narrower and concrete: it detects and escalates the specific class of
conflict this investigation found — a click-derived offset that
disagrees with an independently-computed, already-displayed estimate —
rather than silently trusting whichever one the rounding happened to
produce. It is conflict detection and human clarification, not a claim
of universal correctness for every theoretically ambiguous grid.

**Verified against the real PDF**, not just synthetic numbers: an
end-to-end smoke test drives the actual `CalibrateWorkspace` (real
`PDFRenderer`, real `ViewTransform`, real click handling) against "DP
Pocket 20 pages for centered bothsided print.pdf", confirms the
cell-label prompt fires for the conflicting click, and confirms that
resolving it with `r2c2` produces a correct 3×3 suggested grid (9 cells)
in Review Cards. See `tests/test_calibrate_state.py`'s
`TestDoomPilgrimGridInferenceConflict` for the state-layer regression
coverage of the same scenario.

**Follow-up: the clarification prompt itself was confusing.** Manual
validation of the above surfaced a separate issue with the prompt this
conflict routes to -- it asked the user to type the internal 0-based
`r2c2` form shown throughout this document, developer/CLI syntax never
meant to reach the GUI. `calibrate_state.py`'s new
`parse_human_cell_label()` now accepts a plain 1-based `"row,col"` pair
(e.g. `"3,3"` for the same lower-right card described above) instead;
internal storage is unaffected. Re-verified end-to-end against this same
PDF and click coordinates with the new prompt: the dialog states the
first card's 1-based row/column, rejects both free-text garbage and the
old `r2c2` form (retries as before), accepts `"3,3"`, and still produces
the correct 3×3 / 9-card grid. See DEVELOPER.md's "Cell-label prompt uses
human, not internal, numbering."
