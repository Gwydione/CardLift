# CardLift — Alpha Release Review

Read-only release-engineering assessment. Written 2026-07-15, against
commit `53cc28d` ("Link Privacy Promises into project documentation").
This document reports findings and proposed dispositions only — nothing
in this review was implemented, and no other files were changed to
produce it.

_This document reflects the repository state at the time it was written
(including test counts and other point-in-time figures) and is preserved
for historical context; see `docs/RELEASE_READINESS.md` for current
status._

Central question this review answers:

> Can we responsibly ask another human to spend their time and trust
> testing this application?

---

## 1. Executive assessment

**The application itself is trustworthy enough to test.** The three
highest-severity classes of risk a release engineer should worry about —
data-corrupting calibration math, thread-safety/crash risk during the
app's core file-writing action, and silent failure with no diagnostic
trail — have each been individually investigated, fixed, and covered by
targeted regression tests, with the reasoning preserved in
`docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` and
`docs/ALPHA_HARDENING_PLAN.md`. The full test suite passes (508/508,
verified by direct run — see §4). Privacy posture is unusually strong
for an alpha: no networking dependency exists at all, diagnostic logging
is local-only and was itself just hardened against a real path-leak
regression, and `docs/PRIVACY_PROMISES.md` is genuinely tester-ready
prose today.

**What is not ready is almost entirely outside the code.** No packaging
work has been started (confirmed: no `.spec` file, no installer script,
no packaging tool installed in the venv) — consistent with the pause
this review was requested during. More materially: there is no LICENSE
file for CardLift itself, no third-party attribution notices despite a
core dependency (PyMuPDF) carrying an AGPL/commercial dual license, no
verified redistribution rights for the 16 MB sample PDF committed to the
repo, no tester-facing quick-start or known-limitations note (only
detailed internal engineering logs), and no bug-report channel or in-app
pointer to one. None of this requires further feature engineering — it
requires a short, concrete, mostly-non-code checklist (§11).

**Answer to the central question: yes, conditionally.** It would be
responsible to hand this to a trusted human tester once the sample-deck
licensing and PyMuPDF licensing questions are answered (so a tester
isn't being handed an unresolved legal exposure) and a short tester-facing
"what to expect / how to report problems" note exists. Neither is a code
change. Handing it over *today*, with no such note and two open legal
questions, would not meet the standard this review was asked to apply.

---

## 2. Current release-surface inventory

Verified directly (`git status`, `git log`, `find`, `pip show`):

| Surface | State |
|---|---|
| Git repo | Single branch (`master`), clean working tree, **no tags**, 39 commits from `6373182` (scaffold) to `53cc28d` (this session's docs-link commit) |
| Entry points | `gui_app.py` (GUI, thin `sys.path` shim), `extract.py` (CLI, same pattern) |
| Version identity | `deckforge.__version__ = "0.1.0-alpha"` (`src/deckforge/__init__.py`) — single source of truth, read by window title, `TopBar` label, and crash-log session header |
| Dependencies | `PyMuPDF>=1.24`, `Pillow>=10.0` (runtime); `+PySide6>=6.6` (GUI); `+pytest>=8.0` (dev). No lock file — all ranges unpinned |
| Packaging config | **None** — no `.spec`, `setup.py`, `setup.cfg`, installer script, or `[project]` table in `pyproject.toml` (which contains only pytest config); no packaging tool (`pyinstaller`/`cx_freeze`/`nuitka`/`briefcase`) installed in `.venv` |
| Icon/branding assets | **None** — `docs/BRANDING.md` documents a concept but explicitly states it "requires a simplified production pass" before use; no `.ico`/`.icns`/asset files exist anywhere in the repo |
| License | **No LICENSE file for CardLift.** No NOTICE/third-party-attribution file |
| CI | No `.github/` directory — no workflows, no issue templates |
| Test suite | 21 test files, 508 tests, run directly (see §4) |
| Tracked repo payload | 36 MB total tracked content; `sample_decks/Solo-cards-digital.pdf` (16 MB) + `preview/` (6.8 MB) + `output/` (10.8 MB, 54 generated PNGs) + `docs/ui/UI_REFERENCE_LAYOUT.png` (1.7 MB) account for nearly all of it |
| `.gitignore` | Four lines: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.venv/` — does **not** exclude `output/`, `preview/`, or a stray tracked file (`claude engineering prompt.txt`, repo root) |
| Diagnostic logging | Local-only rotating file, `%LOCALAPPDATA%\CardLift\logs\cardlift.log`, 1 MB × 3 backups (`deckforge_gui/logging_setup.py`) — confirmed no networking dependency exists anywhere in the dependency tree |

---

## 3. Verified strengths

Stated plainly, since a release review that only lists problems is
misleading:

- **The three real crash/correctness risks that would make external
  testing irresponsible have already been found, fixed, and tested.**
  Export thread synchronization (cross-thread `PyMuPDF` document access,
  stale in-progress UI, a destination-message race, stale cross-deck
  completion) and safe shutdown during export (a `QThread`
  destroyed-while-running crash class, discovered and diagnosed via a
  real `IsHungAppWindow()` check, not guesswork) are both fixed with
  dedicated regression tests (`tests/test_export_workspace.py`,
  `tests/test_main_window.py`) that drive a **real** `QThread`/event
  loop rather than synthetic slot calls — verified by reading both test
  files directly.
- **The core "click two corners, get a grid" risk was investigated with
  real rigor**, not patched reactively.
  `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` traces two distinct,
  additive error sources to their exact formulas, distinguishes an
  implementation bug (silent 0.0-gap fallback — now surfaced as an
  explicit warning) from a genuine mathematical property of a two-point
  linear fit (adjacent-click amplification — now mitigated by hinting a
  farther second card), and is explicit about what the fix does and does
  not guarantee. This is a materially higher bar than most alpha
  software clears.
- **Privacy posture is unusually strong for this stage.** Verified via
  `pip show`/dependency inspection: the dependency tree contains no
  networking library at all (`PyMuPDF`, `Pillow`, `PySide6`, `pytest`
  only) — the app is structurally incapable of a network call without a
  code change, not merely configured not to make one. A real leak
  (full local paths reaching the diagnostic log via wrapped exception
  messages) was found and fixed this session, with regression tests
  proven to fail against the prior code before the fix (verified by
  reverting the source change and re-running the new tests). No
  telemetry, no update checker, no account/license system anywhere in
  the codebase.
- **Version identity has no drift risk.** One constant
  (`deckforge.__version__`), read directly by every surface that
  displays it (window title, `TopBar`, crash-log header) — verified by
  `grep`, not inferred.
- **Writable-path discipline is already correct.** The app writes
  exactly two kinds of files: exports to the user-chosen destination
  folder, and its own local log under `%LOCALAPPDATA%`. Nothing writes
  to the install directory. This derisks a common PyInstaller
  distribution trap (apps that assume a writable install location) well
  before packaging has even started.
- **`docs/PRIVACY_PROMISES.md` is genuinely tester-ready today**, written
  in plain language, linked from `README.md`, and — per this session's
  own credibility review — checked sentence-by-sentence against what the
  code can actually prove. Reusable as-is in tester-facing material.
- **Overwrite protection is correctly cautious.** `_confirm_overwrite_if_needed()`
  (`export_workspace.py:584`) defaults to Cancel on both Enter and
  Escape, and only proceeds on an explicit destructive-styled click —
  verified by reading the implementation, not just the docstring.

---

## 4. Test suite — exact result

```
$ python -m pytest -q
508 passed in 31.31s
```

Run twice (once mid-investigation, once for this report) with identical
results. No code was changed to make this pass. Test distribution by
file (`grep -c "def test_"`), most-to-least:

`test_calibrate_state.py` 108, `test_calibrate_ui.py` 83 (CLI/Tkinter),
`test_view_transform.py` 36, `test_find_cards_state.py` 35,
`test_profile.py` 34, `test_review_state.py` 26, `test_measure.py` 22,
`test_export_state.py` 21, `test_review_workspace.py` 16,
`test_exporter.py` 15, `test_geometry.py`/`test_cli.py`/`test_cell_export.py`
13 each, `test_app_state.py` 11, `test_export_workspace.py` 10,
`test_main_window.py` 8, `test_find_cards_workspace.py` 7,
`test_session.py` 6, `test_pdf_renderer.py` 5, `test_cropper.py` 4.

Only **three** test files instantiate a real `QApplication`/widget
(`test_export_workspace.py`, `test_main_window.py`,
`test_review_workspace.py`) — see Finding B1/B2 below for what that
means for coverage.

---

## 5. Findings

Each finding: evidence, disposition, confidence.

### A. Product and scope clarity

**A1 — The single-shared-layout assumption is documented for
developers but never surfaced to a tester in the moment it would
matter.**
Evidence: `calibrate_state.py`'s module docstring ("ONE SHARED LAYOUT")
and `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` §3 both confirm all
Front Pages share one calibrated geometry with no per-page drift
detection; `docs/CORE_CONCEPTS.md` documents "single Deck"/"single card
arrangement" as the *initial* scope with "Future versions may support
multiple card arrangements..." framing. This is honest scope-setting —
but it lives only in developer-facing docs. A tester who loads a PDF
with genuinely mixed card sizes gets no warning; the only signal is
whatever visibly-wrong crop appears in Review Cards' thumbnails, which
they have no way to attribute to "unsupported deck structure" versus
"CardLift bug."
**Disposition:** Accept and disclose for Alpha 1 — cheap to fix via a
tester-facing sentence, not a code change.
**Confidence:** High (directly verified in code + investigation doc).

**A2 — Card Inspection's provisional status needs to be stated to
testers, not just recorded internally.**
Evidence: `docs/RELEASE_READINESS.md` already states, in its own words,
that Card Inspection is "implemented, not yet decided... awaiting your
own use and alpha-tester feedback before being considered part of the
product." That's the right internal framing, but nothing tester-facing
currently exists to tell a tester their feedback on this specific
feature is particularly wanted, or that it might change/disappear.
**Disposition:** Accept and disclose (communication task, not a defect).
**Confidence:** High.

### B. Engineering readiness

**B1 — No regression test exists for the Deck page's drag-and-drop
handling — the exact area a real bug was manually found and fixed in,
and the first interaction every tester will have.**
Evidence: `docs/ALPHA_HARDENING_PLAN.md`'s addendum documents a real,
manually-found-and-fixed Qt event-handling bug in `deck_workspace.py`'s
`_DropZone` (`dragMoveEvent` not re-accepting, child widgets swallowing
drag events). No `tests/test_deck_workspace.py` exists at all — confirmed
by directory listing. Only three test files in the whole suite drive a
real widget (§4); this isn't one of them.
**Disposition:** Accept and disclose for Alpha 1 — the fix itself is
manually verified and its mechanism is well understood and documented;
a regression test is valuable but a first alpha does not need to wait
for it.
**Confidence:** High (verified file absence + documented fix).

**B2 — `calibrate_workspace.py`, the actual interactive click-to-calibrate
canvas — the single highest-risk, highest-complexity interactive surface
in the app per its own investigation doc — has no widget-level test
file.**
Evidence: no `tests/test_calibrate_workspace.py` exists. All calibration
correctness assurance comes from `calibrate_state.py`'s 108 pure-function
tests (which do cover the underlying math extensively, including the
exact real-world regression case documented in
`docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`'s addendum) plus documented
manual verification sessions against real PDFs.
**Disposition:** Defer beyond Alpha 1 — pure-function coverage plus
repeated, documented manual verification against real decks is a
reasonable substitute for a first alpha; building a click-driven-canvas
test harness is real, separate work not needed to answer this review's
central question.
**Confidence:** High.

**B3 — The worker-thread failure path has no automated test exercising
a real raised exception through a real `QThread`.**
Evidence: `docs/RELEASE_READINESS.md` itself already states "worker-failure
test still not started" — confirmed still accurate by reading
`tests/test_export_workspace.py` directly: `TestExportFailureLogging`
exercises `_on_export_failed()` with a synthetic string, not a real
exception raised inside `_ExportWorker.run()`.
**Disposition:** Accept and disclose — already tracked accurately in
existing docs, not a surprise finding, and the surrounding crash-logging
safety net (§ Privacy strengths above) is itself tested and verified.
**Confidence:** High.

**B4 — `gui_app.py`'s own module docstring is materially stale.**
Evidence: it describes the app as "Phase II prototype... application
frame only... does not call the PDF/calibration engine yet" — true many
milestones ago, false today (the app has the complete six-step workflow,
crash logging, and Card Inspection). This is the entry point file
itself — the first thing anyone reading the source to understand "what
does running this do" would open.
**Disposition:** Accept and disclose if source is ever shared with
testers (§E); otherwise low-urgency doc cleanup outside this review's
scope to fix.
**Confidence:** High (direct read).

**B5 — `DEVELOPER.md`'s "Getting Started" section contradicts
`README.md`'s now GUI-first framing.**
Evidence: `DEVELOPER.md` still opens with "There's nothing to
'launch' — CardLift is a CLI tool, not a server," walking through CLI
setup first and GUI setup second under "GUI (Phase II)" — while
`README.md` was deliberately rewritten (per `RELEASE_READINESS.md`'s own
accomplished-item log) to lead with the GUI workflow. Both documents are
live and disagree about which surface is primary.
**Disposition:** Defer — contributor-facing, not tester-facing; real but
low-urgency doc inconsistency, named per this review's explicit
instruction to call out contradictions.
**Confidence:** High.

**B6 — Path-resolution assumptions that work from source may not
survive PyInstaller bundling unchanged.**
Evidence: both entry points do
`sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))`
rather than relying on an installed package. This is correct for a dev
checkout; PyInstaller (especially one-file mode, which extracts to a
temp directory at runtime) changes `__file__`/`sys.path` semantics in
ways that have broken exactly this pattern in other projects.
**Disposition:** Must resolve as part of packaging — not a current
defect, a real unknown a packaging spike must specifically test, not
assume away.
**Confidence:** Medium (a known general PyInstaller failure class; not
yet tested against this specific codebase).

**B7 — A dead UI affordance: the TopBar's "⋮" button implies
interactivity it doesn't have.**
Evidence: `main_window.py`'s `TopBar` gives the button a tooltip
("Settings") and hover styling but no `.clicked.connect(...)` exists
anywhere — confirmed by grep. Clicking it does nothing. This directly
contradicts the app's own stated principle
(`docs/ui/DESIGN_SYSTEM.md`: "Interactive elements should communicate
interactivity before users click them... users should never wonder why
the interface behaves differently"). It's also the only unlabeled icon
in the top bar — a first-time tester is likely to click it out of
curiosity.
**Disposition:** Accept and disclose for Alpha 1 — low severity (no
data/workflow risk), but worth naming since it's a concrete instance of
the app's own design standard not being met, and a one-line note (or
disabling the button) is a trivial fix if you'd rather not carry it
into testing.
**Confidence:** High (verified absence of any signal connection).

### C. Packaging readiness

No packaging work exists to critique — by design, per this review's
premise. What follows are decisions/unknowns a packaging spike would
need to resolve, not defects:

- **Entry point** is clean and thin (`gui_app.py`) — good starting shape
  for a PyInstaller target, but see B6.
- **Icon/Windows metadata**: no asset exists yet; `BRANDING.md` is
  explicit that its concept art isn't production-ready. **Must resolve
  as part of packaging.**
- **Version consistency**: already solved (§3) — no packaging work
  needed here.
- **Writable vs. read-only paths**: already verified correct (§3).
- **Dependency packaging implications**: `PyMuPDF` and `PySide6` are
  large, binary-heavy dependencies with known PyInstaller hook
  complexity (Qt plugins/platform DLLs especially); neither has been
  test-bundled. **Explicit unknown requiring a packaging spike**, not
  assumed to "just work."
- **One-file vs. one-folder, portable vs. installer**: no evidence
  either way exists anywhere in the repo. **Undecided — must resolve.**
- **Clean uninstall**: trivially clean *today* (no installer, no
  registry footprint, only `%LOCALAPPDATA%\CardLift\logs` persists) —
  worth stating as a baseline to preserve, and worth a one-line tester
  note now even before any installer exists.
- **SmartScreen/unsigned binary**: no code-signing evidence anywhere.
  An unsigned PyInstaller EXE will reliably trigger a Windows
  "Unknown Publisher" SmartScreen warning. **Must resolve** — at
  minimum via advance tester communication ("expect this, click Run
  Anyway"), not necessarily a paid certificate for a small private
  alpha.
- **Reproducibility**: `requirements*.txt` use unpinned `>=` ranges, no
  lock file. A build made today and one made next month could pull
  different `PyMuPDF`/`PySide6` versions. **Must resolve before a
  repeatable build procedure can be claimed.**
- **PyMuPDF's license** (see E below) is as much a packaging-readiness
  blocker as a legal one — it determines what *can* legitimately be
  bundled and distributed at all.

### D. First-run and complete user journey

Walked end-to-end against verified code, not assumption:

- **Obtaining/launching**: `git clone` → `pip install -r
  requirements-gui.txt` → `python gui_app.py` — verified accurate
  against `gui_app.py`'s actual behavior. This presumes the tester
  already has Python, pip, and git set up, which is a real, nontrivial
  assumption for a non-developer tester. Not a defect — but an
  assumption "obvious only to the developers" that should be made
  explicit (§F: who exactly is Alpha 1's tester group?).
- **Understanding what it does**: `README.md`'s framing is clear and
  accurate against the implemented workflow — verified by full read.
- **Selecting a PDF**: drag-and-drop and file-picker both implemented
  and hardened against a real, documented Qt event-forwarding quirk.
- **Card pages / shared back**: the three-way `SharedBackStatus`
  (`ASSIGNED`/`CONFIRMED_NONE`/`UNRESOLVED`) deliberately avoids
  collapsing "not decided yet" into "none" — a real, previously-found
  bug class, now closed by construction.
- **Calibrating**: the single riskiest step. Effect A (silent 0.0-gap)
  now warns explicitly; Effect B (adjacent-click amplification) is
  mitigated, not eliminated —
  `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md` is explicit that
  agreement between the click and the hint is "sufficient confidence to
  proceed automatically... not proof of correctness." This residual
  risk is real, disclosed in internal docs, and should be the single
  most prominent item in tester-facing "what to expect" material:
  measure a second card far from the first, and check Review Cards'
  thumbnails carefully before exporting.
- **Review/inspect**: solid, tested; see A2 on communicating its
  provisional status.
- **Export destination/success/failure**: overwrite-protected,
  clearly messaged, "Open Folder" uses Qt's cross-platform
  `QDesktopServices.openUrl` (verified) rather than a Windows-only
  shell call.
- **Starting another deck**: wired and functional (verified signal
  chain).
- **Finding help**: **no in-app help, feedback, or bug-report affordance
  exists anywhere** — verified by reading `TopBar`/`Sidebar`/status-bar
  code. A tester has no way, from inside the app, to learn how to report
  a problem or where `cardlift.log` lives.
- **Removing the application**: today, "uninstall" = delete the folder;
  `%LOCALAPPDATA%\CardLift\logs` persists afterward. Not documented
  anywhere yet, trivial to write down.

### E. Release artifacts and legal/attribution readiness

| Artifact | State | Actual need for this alpha |
|---|---|---|
| Tester quick-start | README exists but is developer-voiced (git/pip/run-from-source) | Needed only if non-developer testers are in scope — otherwise README is close to sufficient as-is |
| Release notes | None (internal docs only, wrong voice for a tester) | **Needed** — cheap to produce by condensing `RELEASE_READINESS.md`, not new investigation |
| Known-issues/scope statement | Exists internally (`RELEASE_READINESS.md`, `CALIBRATION_GEOMETRY_INVESTIGATION.md`), not tester-facing | **Needed**, same reason |
| Privacy Promises | **Exists, tester-ready** (`docs/PRIVACY_PROMISES.md`) | Done |
| CardLift's own license | **Missing entirely** — no LICENSE file | **Needed** — even "private alpha, all rights reserved" is a decision that should be explicit, not silent |
| Third-party attribution/notices | **Missing entirely** | **Needed, with real urgency** — see below |
| Bug-report instructions | None, no in-app pointer | **Needed** |
| Version/build identity | Solid (§3) | Done |
| Checksums | N/A — no build artifact exists yet | Not needed until packaging exists |
| Screenshots | README explicitly placeholders this ("will be added as the alpha UI stabilizes") — honest, not stale | Nice-to-have, not needed to test responsibly |
| Sample/test material redistribution rights | **Unverified** — see below | **Needed** |
| Uninstall instructions | None written | Cheap, needed |
| Source-code availability policy | Undecided | Needed, tied to the license question |

**Two items above warrant elevated attention, not boilerplate:**

1. **PyMuPDF's license is AGPL-3.0 or a paid Artifex commercial
   license** — verified directly via package metadata
   (`pip show pymupdf` → `License: Dual Licensed - GNU AFFERO GPL 3.0 or
   Artifex Commercial License`). This is not "mature commercial software
   boilerplate" — it is a real constraint on what can be distributed and
   under what terms, and nothing in the repository currently addresses
   it. `PySide6` (LGPL/GPL, verified via metadata) carries lighter but
   still real attribution obligations. **Disposition: Must resolve as
   part of release preparation** — needs an explicit decision
   (AGPL-compatible source availability, or a commercial license),
   not a "we'll figure it out later." Confidence: high on the license
   fact itself; the compliance conclusion depends on decisions not yet
   made, so that part is an explicit unknown, not a verified violation.
2. **`sample_decks/Solo-cards-digital.pdf` (16 MB) is committed to the
   repo with no accompanying license, attribution, or permission
   statement found anywhere.** If this repository (or an archive of it)
   is what testers receive, its redistribution rights are unverified. I
   cannot determine from the repository alone whether this file is
   safe to redistribute. **Disposition: explicit unknown requiring a
   definitive answer before external distribution** — if the answer is
   anything other than "cleared for redistribution," this becomes a
   Must-fix (replace with an originally-authored or clearly-licensed
   test fixture) before any external tester receives it.

**Repo-hygiene note, related but distinct**: `output/` (54 generated
PNGs, 10.8 MB) and `preview/` (6.8 MB) are tracked in git despite being
regeneratable CLI output — not excluded by `.gitignore`. A stray file,
`claude engineering prompt.txt`, is also tracked at the repo root.
Neither is a defect, but both inflate whatever gets handed to a tester
(a `git clone` today pulls 36 MB, most of it either regeneratable output
or the same-licensing-question sample PDF twice over — once as source,
54 more times as its own exported card images).
**Disposition:** Must resolve as part of release/packaging prep (trivial
`.gitignore` fix + `git rm --cached`, not attempted here per this
review's read-only scope). **Confidence:** High.

### F. Alpha tester experience and supportability

- **No bug-report channel exists anywhere** — not in-app, not in any
  doc. **Explicit unknown requiring a decision** (§10).
- **Diagnostic info is genuinely good** (version-stamped, session
  headers, real exception content per `docs/PRIVACY_PROMISES.md`'s own
  description) but **discoverability is entirely external** — no
  in-app "Open log folder," which `docs/ALPHA_HARDENING_PLAN.md` §6
  already explicitly deferred on purpose. A non-technical tester would
  not find `%LOCALAPPDATA%\CardLift\logs` without being told.
- **Log-sharing safety is already well-communicated** in
  `docs/PRIVACY_PROMISES.md` and reusable verbatim in tester
  instructions.
- **Build-version identification is solid** and reusable as-is ("tell
  us the version shown in the title bar").
- **Known-limitations communication exists only internally** (§E) —
  needs distillation, not new content.
- **Distinguishing a CardLift defect from an unsupported PDF structure
  has no in-app answer today** (§A1) — the single most likely source of
  tester confusion, and currently unaddressed by anything the tester
  would actually see.

### G. Distribution and trust

Given the implied scale (a small, trusted, private alpha — "another
human," not a public release):

**Recommended: a private GitHub repository with a GitHub Release
(pre-release/draft) per build**, if the project is or can be hosted on
GitHub — I found no direct evidence in the local repository of where (or
whether) it's currently hosted, so this is conditional. This is the
smallest channel that gives, for free: versioned/named artifacts,
built-in release-notes surface, access control via collaborators,
artifact replacement with history, and a tester audience likely to
already trust and know how to use GitHub.

**Considered and not recommended as primary:**
- A direct cloud-drive link (notably, this project's own working
  directory is already inside OneDrive) — lower setup cost, but no
  version history, no access revocation granularity, and reads less
  credible to a tester than a tagged release.
- itch.io or a similar public storefront — appropriate *later*, once a
  packaged installer and public identity (icon, branding) exist; adds
  discovery/marketing overhead this stage doesn't need and isn't asking
  for.

**Given no code signing exists**, SmartScreen warnings should be
pre-communicated regardless of channel — this is a tester-communication
task, not a channel-selection one.

**Today, with no packaged artifact at all, "distribution" is really
"how do I hand you a git checkout."** Nothing more elaborate than the
above is warranted until packaging exists.

### H. Release process and clean-machine validation

- **No git tags exist** — nothing to build "the vX.Y.Z release" from in
  a reproducible, addressable way, even though `DEVELOPER.md` already
  documents a version-bump convention. **Must resolve** — cheap
  (`git tag` at build time), not yet exercised even once (the version
  string has never actually been bumped past `0.1.0-alpha`).
- **No deterministic artifact-naming convention** — not applicable
  until packaging exists.
- **No repeatable build procedure** — by definition, given no packaging
  config exists at all.
- **No release-execution checklist exists** — `RELEASE_READINESS.md` is
  a *readiness board* (what's done vs. open), a different document from
  a *release checklist* (steps to actually cut a build). Both are
  useful; only the first exists.
- **No evidence of validation on a machine/account without the
  development environment.** Every fix in this review's evidence trail
  (thread-safety, shutdown, drag-and-drop, crash logging) was manually
  verified by the developer in their own dev environment. Whether
  README's own from-source instructions (`pip install -r
  requirements-gui.txt` && `python gui_app.py`) succeed on a genuinely
  clean Windows machine — different Python version, no pre-existing
  `.venv`, no prior pip cache — has apparently never been tested. This
  is squarely relevant to "respecting the tester's time": if the very
  first thing a tester does fails for environmental reasons nobody
  anticipated, that is the most expensive possible way to discover a
  gap. **Disposition: Must fix before Alpha 1** — not a code change, a
  validation task: run the documented instructions on a machine that
  isn't the development machine, once, before asking anyone else to.
  **Confidence:** High that this hasn't been done (no evidence anywhere
  of a second machine/environment being involved in any fix's
  verification); the *outcome* of doing so is unknown.

---

## 6. Packaging-readiness assessment (summary)

Not started, appropriately so per this review's premise. Genuinely
solved already: version consistency, writable-path discipline, a thin
entry point. Genuinely open, requiring real decisions before a spike can
even be scoped: icon/metadata, one-file vs. one-folder, installer vs.
portable, code-signing posture, dependency-bundling risk for
PyMuPDF/PySide6, build reproducibility (unpinned dependencies), and —
overshadowing all of the above — whether PyMuPDF's license permits the
distribution model being considered at all. See §5C and §10.

---

## 7. First-run and tester-experience assessment (summary)

The guided in-app workflow itself is well-designed and, where tested,
correctly implemented — three-way state modeling avoiding ambiguous
"undecided" states, explicit warnings for known calibration risk,
overwrite protection, clear success/failure messaging. What's missing
sits entirely at the edges of that workflow: no in-app help/feedback
path, no in-app acknowledgment of the single-layout scope limit, and one
dead UI affordance. See §5D and §5F.

---

## 8. Required release artifacts (summary)

Present and reusable as-is: version identity, Privacy Promises. Missing
and needed regardless of scale: CardLift's own license, third-party
attribution (elevated urgency — AGPL), tester-facing release notes and
known-issues note, bug-report instructions, uninstall note, and a
definitive answer on the sample deck's redistribution rights. Not
needed yet: checksums, screenshots (already honestly placeholdered).
See §5E.

---

## 9. Distribution recommendation (summary)

Smallest credible channel for the implied private/small tester group: a
private GitHub repo + GitHub Releases (pre-release), conditional on
confirming the project is (or can be) hosted there. Direct cloud-drive
link is an acceptable fallback, not a recommended primary. Public
storefronts (itch.io etc.) are premature. See §5G.

---

## 10. Explicit unknowns requiring decisions or experiments

1. **Are `sample_decks/Solo-cards-digital.pdf`'s redistribution rights
   clear?** Unverifiable from the repository alone — needs a definitive
   answer before any external distribution.
2. **What is CardLift's licensing/distribution posture given
   PyMuPDF's AGPL/commercial dual license?** Needs an explicit decision,
   not silence.
3. **Who is the actual Alpha 1 tester group** — developer-literate
   (comfortable with `git clone`/`pip install`) or not? This determines
   whether source-run distribution is viable for this round at all, or
   whether packaging is a hard prerequisite rather than a later
   convenience.
4. **Is this repository currently hosted anywhere (e.g., GitHub), and
   is it private?** No direct evidence either way was found locally.
5. **One-file vs. one-folder; portable zip vs. installer?** No evidence
   either way exists yet.
6. **Code-signing posture** — accept SmartScreen warnings for this
   alpha, or invest in a certificate? No evidence of a decision either
   way.
7. **Has the current from-source tester path ever been run on a
   non-development machine?** Evidence suggests no.
8. **What feedback/bug-report channel fits this specific tester
   group?** Not chosen anywhere in the docs — appropriate to keep
   lightweight (a personal contact, a shared doc, or a private GitHub
   Issues tracker), not over-engineered, given the stated small-private-alpha
   scale.

---

## 11. Proposed Alpha 1 exit criteria

1. Full test suite passes (508/508) — **already true today.**
2. Sample-deck licensing question (§10.1) answered, compatible with the
   chosen distribution method.
3. PyMuPDF licensing posture (§10.2) decided and, if it implies any
   obligation (source availability, attribution), satisfied.
4. A short, tester-voiced quick-start + known-limitations note exists —
   condensed from existing internal docs, not new investigation. Must
   include, at minimum: the single-card-arrangement scope limit (§A1),
   Card Inspection's provisional status (§A2), and the calibration
   guidance already written in `docs/CALIBRATION_GEOMETRY_INVESTIGATION.md`
   ("measure a second card far from the first").
5. A LICENSE decision for CardLift itself is made and stated, even if
   informal for a private alpha.
6. A feedback/bug-report channel is chosen and communicated, including
   where to find and how to safely share `cardlift.log`.
7. At least one clean-machine (non-development-environment) run-through
   of the actual tester-facing instructions succeeds.
8. `docs/RELEASE_READINESS.md` is brought current with this session's
   two most recent commits, so its own "single place to check 'are we
   ready yet'" claim stays true.

None of the above require further application feature work.

---

## 12. Final recommendation

**Ready after specified pre-packaging work.**

Not "not ready to prepare a release candidate" — that would understate
how solid the engineering investigation and hardening work already is;
the application would not embarrass anyone who tested it today from a
correctness or crash-safety standpoint. Not "ready for a controlled
packaging spike" — a packaging spike cannot resolve the sample-deck and
PyMuPDF licensing questions, which are prerequisites independent of any
packaging tooling decision, and proceeding to a spike without them risks
building distribution machinery around an artifact that can't yet be
legitimately distributed. Not "ready to prepare the first release
candidate" — real, currently-missing artifacts (license, attribution
notices, a tester-facing note, a feedback channel) stand between here
and that.

The gap between where CardLift is and a responsible first alpha is
short, concrete, and almost entirely non-code — §11's eight items. Close
those, and the answer to this review's central question becomes an
unconditional yes.
