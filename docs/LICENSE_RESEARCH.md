# CardLift — Software Licensing Research

Factual investigation only, prepared in response to the licensing
finding in `docs/ALPHA_RELEASE_REVIEW.md`. This document does not
recommend a license for CardLift, does not draft a `LICENSE` file, and
does not set project policy — it reports verified facts about
CardLift's actual dependencies, with citations, so that decision can be
made deliberately by someone with the authority (and, where needed, the
legal advice) to make it.

**Method:** dependency facts were verified against what is actually
installed in this project's own `.venv` (`pip show`), not assumed from
memory or package name. License claims were then cross-checked against
each project's own official documentation. Where a primary source could
not be fetched directly (noted inline), the closest available official
source is cited instead.

**Dependencies reviewed**, as declared in `requirements.txt` /
`requirements-gui.txt` / `requirements-dev.txt` and confirmed installed:
`pymupdf==1.28.0`, `pillow==12.3.0`, `PySide6==6.11.1` (plus its own
sub-packages `PySide6_Essentials`, `PySide6_Addons`, `shiboken6`, all
under identical terms), and `pytest==9.1.1` (development-only). Also
reviewed: PyInstaller, the packaging tool named as the likely next step
in the prior release review, though it is not currently a project
dependency.

---

## 1. PyMuPDF Licensing

### What licenses are available?

PyMuPDF (and the underlying MuPDF library it wraps) is dual-licensed:
**GNU AGPLv3** (free, open-source) or a **commercial license sold
directly by Artifex Software**, the copyright holder and exclusive
commercial licensor for MuPDF. There is no third "free and closed"
option.

Confirmed two ways: Artifex's own licensing page, and the installed
package's own metadata in this project —

```
$ pip show pymupdf
License: Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License
```

Source: [Artifex — Licensing](https://artifex.com/licensing).

### Is PyMuPDF dual licensed?

Yes, confirmed directly by both sources above.

### What are the practical differences?

| | AGPLv3 (free) | Commercial (paid, via Artifex) |
|---|---|---|
| Cost | $0 | Negotiated with Artifex |
| CardLift's own source | Must be made available under AGPL-compatible terms to anyone who receives the software (see next question) | Stays proprietary — Artifex states "No Code Disclosure Required" |
| Modifications to PyMuPDF/MuPDF itself | Must be disclosed under AGPL | No disclosure required |
| Generated PDF output | Expected to mention the open-source software / retain a producer line, per Artifex | No such expectation |
| Support | Community only | Direct vendor support; Artifex advertises "free upgrades" |

Source: [Artifex — Licensing](https://artifex.com/licensing).

### What obligations exist when distributing a desktop application using the AGPL option?

Two different AGPL clauses are relevant, and it matters which one
actually applies to CardLift's situation — a compiled Windows binary
handed to a tester, not a hosted network service:

- **AGPL §6 ("Conveying Non-Source Forms")** is the section that
  applies directly to shipping a compiled `.exe`. It requires that
  whoever conveys the covered work in object-code form — which includes
  it bundled into a frozen executable — also conveys the
  "machine-readable Corresponding Source," via one of several specified
  mechanisms (physical media, a written offer, a network server,
  peer-to-peer transmission). Verbatim, fetched directly: *"You may
  convey a covered work in object code form under the terms of sections
  4 and 5, provided that you also convey the machine-readable
  Corresponding Source under the terms of this License..."* Source:
  [GNU AGPLv3, full text, §6](https://www.gnu.org/licenses/agpl-3.0.en.html).
- **AGPL §13 ("Remote Network Interaction")** is the clause that
  actually distinguishes AGPL from ordinary GPLv3 — it closes the
  so-called "ASP loophole" by requiring source access even when
  software is never distributed at all, only run as a network service
  others interact with remotely. Verbatim: *"If you modify the Program,
  your modified version must prominently offer all users interacting
  with it remotely through a computer network... an opportunity to
  receive the Corresponding Source..."* This is the clause most
  general-audience write-ups about AGPL focus on, but it is **not**
  CardLift's actual exposure as currently scoped: CardLift is not a
  network service, so §13 adds nothing beyond what §§4–6 already
  require for a distributed binary. Source:
  [GNU AGPLv3, full text, §13](https://www.gnu.org/licenses/agpl-3.0.en.html);
  [Why the Affero GPL](https://www.gnu.org/licenses/why-affero-gpl.html).
- **Artifex's own stated position — which matters more in practice than
  a from-first-principles reading, since Artifex is the copyright
  holder who would actually enforce this** — is that using PyMuPDF
  under AGPL requires the *whole application* built with it to be
  released under AGPL-compatible terms, not just PyMuPDF's own source:
  *"you cannot deploy our open-source as part of a server-based
  application or service, without disclosing your own application's
  full source code under AGPL to any users interacting with it"*, and
  more generally, *"If your software uses PyMuPDF and you market it
  commercially, you no longer fall under the AGPL[; contact Artifex]."*
  Source: [Artifex — Licensing](https://artifex.com/licensing);
  [PyMuPDF FAQ](https://pymupdf.readthedocs.io/en/latest/faq/index.html)
  ("If you're using it as part of a commercial product's data
  pipeline... the AGPL obligations apply").

**In plain terms:** shipping a compiled CardLift `.exe` that bundles
PyMuPDF under the AGPL option means CardLift's own source would need to
be made available under AGPL-compatible terms to anyone who receives
the binary — not just PyMuPDF's source. This is Artifex's explicit,
stated reading of their own license grant, and it's the reading that
matters practically since they hold the copyright.

### Does accepting voluntary donations change those obligations?

**No.** This isn't specific to PyMuPDF — it's a foundational principle
of how the entire GPL family (which AGPL extends) works. The Free
Software Foundation's own guidance is explicit that GPL/AGPL obligations
are triggered by *distributing* (or, under AGPL, by *remote network
interaction with*) the covered work — not by whether, or how, money
changes hands:

> "You can charge nothing, a penny, a dollar, or a billion dollars...
> Free software is about freedom, and enforcing the GPL is defending
> freedom. When we defend users' freedom, we are not distracted by side
> issues such as how much of a distribution fee is charged."

Source: [GNU Project — Selling Free Software](https://www.gnu.org/philosophy/selling.en.html).

Donations don't create a new license tier, and they don't exempt a
project from AGPL's source-disclosure requirement — nor do they *add*
any obligation beyond what AGPL already requires. The operative trigger
is conveying the software (or, under §13, remote interaction with it),
full stop; whether money changes hands, and what that money is called
("donation," "sale," "gift"), is not part of that test anywhere in the
license text or the FSF's own commentary on it.

### What official documentation supports these conclusions?

- [Artifex — Licensing](https://artifex.com/licensing) — primary source; Artifex is PyMuPDF/MuPDF's copyright holder and exclusive commercial licensor
- [PyMuPDF FAQ](https://pymupdf.readthedocs.io/en/latest/faq/index.html) — official project documentation
- [GNU AGPLv3, full license text](https://www.gnu.org/licenses/agpl-3.0.en.html) — the license itself (FSF)
- [Why the Affero GPL](https://www.gnu.org/licenses/why-affero-gpl.html) — FSF's own explanation of AGPL's purpose
- [GNU Project — Selling Free Software](https://www.gnu.org/philosophy/selling.en.html) — FSF
- Installed package metadata: `pip show pymupdf` against this project's actual `.venv`

---

## 2. Third-Party Dependencies

### PyMuPDF (`pymupdf==1.28.0`)
- **License:** AGPLv3 or Artifex Commercial (dual). See §1.
- **Attribution requirements:** under the AGPL option, Artifex's page
  states CardLift should mention the open-source software and, in
  generated PDFs, retain/attribute a producer line. Source:
  [Artifex — Licensing](https://artifex.com/licensing).
- **Redistribution obligations:** yes, substantial — see §1. This is
  the dependency the prior Alpha Release Review correctly flagged as a
  release blocker.
- **NOTICE file appropriate?** Yes — regardless of which option is
  chosen, the dependency and its license should be documented somewhere
  a recipient of the binary can find it.

### Pillow (`pillow==12.3.0`)
- **License:** MIT-CMU (a permissive, OSI-approved license in the HPND
  family). Full text obtained directly from the project's own
  repository. Source:
  [Pillow LICENSE, python-pillow/Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE).
- **Attribution requirements:** yes, but lightweight. The license text
  requires "the above copyright notice appears in all copies... and
  that both that copyright notice and this permission notice appear in
  supporting documentation." In practice: preserve Pillow's
  copyright/license text somewhere in the distributed product's
  documentation.
- **Redistribution obligations:** minimal. No source-disclosure
  requirement, no copyleft — closed-source distribution is explicitly
  permitted by the license text.
- **NOTICE file appropriate?** Yes, as the simplest way to satisfy the
  notice-preservation requirement above — not separately mandated as a
  file *by that name*, only the notice content is required somewhere.

### PySide6 (`PySide6==6.11.1`, plus `PySide6_Essentials`, `PySide6_Addons`, `shiboken6` — confirmed via `pip show` to carry identical terms)
- **License:** LGPLv3 **or** GPLv2 **or** GPLv3 **or** a commercial Qt
  license — a multi-option license, not a single one. Confirmed two
  ways: installed metadata (`License: LGPL-3.0-only OR GPL-2.0-only OR
  GPL-3.0-only`) and the official PyPI project page. Source:
  [PySide6 on PyPI](https://pypi.org/project/PySide6/);
  [Qt Licensing](https://www.qt.io/licensing/).
- **Practical note:** for a proprietary desktop application that
  doesn't want to release its own source, the LGPLv3 option is the
  relevant one — the GPLv2/v3 options would require CardLift's own
  source to be GPL-licensed too, similar in spirit to PyMuPDF's AGPL
  constraint. Nothing in the current codebase indicates this choice has
  been made yet.
- **Attribution requirements (under LGPLv3):** per Qt's own official
  LGPL-obligations page, developers must provide "a copy of the LGPL
  license text to the user" and display "a prominent notice about using
  the LGPL library" — obscuring that LGPL components are in use is
  explicitly not permitted. Source:
  [Qt — Open Source LGPL Obligations](https://www.qt.io/licensing/open-source-lgpl-obligations).
- **Redistribution obligations (under LGPLv3):** real, but lighter than
  AGPL/GPL. CardLift's own source does **not** need to be disclosed,
  as long as PySide6 remains "a work that uses the library" — i.e.
  dynamically linked, which is how a normal Python `import PySide6`
  already works, not statically merged in a way that prevents
  replacement. Qt's page is explicit, though, that you must "deliver
  Complete corresponding source code of the library used with the
  application... including all modifications to the library" (PySide6/Qt's
  own source, not CardLift's), and that users must be able to "change
  and re-link the library" — Qt's page calls locking this down
  "tivoization" and prohibits it. Source:
  [Qt — Open Source LGPL Obligations](https://www.qt.io/licensing/open-source-lgpl-obligations).
- **NOTICE file appropriate?** Yes — close to a practical requirement
  given Qt's explicit "prominent notice" language, not just a courtesy.

### pytest (`pytest==9.1.1`), and its own dependencies (`colorama`, `iniconfig`, `packaging`, `pluggy`, `pygments`)
- **License:** MIT. Source:
  [pytest on PyPI](https://pypi.org/project/pytest/) ("Distributed under
  the terms of the MIT license").
- **Attribution/redistribution obligations relevant to a distributed
  binary:** none. `pytest` is declared only in `requirements-dev.txt`
  (development/test tooling), is never imported by `gui_app.py` or
  `extract.py`, and would not be bundled into a PyInstaller build of
  the application.
- **NOTICE file appropriate?** No — not part of the distributed
  product.

### PyInstaller (not currently a CardLift dependency; reviewed because it was named as the likely next packaging step)
- **License:** dual — GPLv2 for the PyInstaller project itself, with an
  explicit bootloader exception, plus a small number of files
  separately under Apache-2.0. Source:
  [PyInstaller — License](https://pyinstaller.org/en/stable/license.html).
- **Practical effect:** the bootloader exception exists specifically so
  that applications built/frozen with PyInstaller are not themselves
  subject to GPL: "You may use PyInstaller to bundle commercial
  applications out of your source code." Source:
  [PyInstaller — License](https://pyinstaller.org/en/stable/license.html).
- **Redistribution/NOTICE obligations:** none found requiring
  attribution of PyInstaller itself in the frozen application's
  distribution, per its official license page.

---

## 3. Distribution Requirements

Scenario as posed: CardLift distributes Windows binaries, with source
hosted publicly (e.g. GitHub).

### Required
(obligations that exist as-is, if the current dependency licenses are used unmodified)

- **If PyMuPDF is used under AGPL:** CardLift's own source must be
  made available under AGPL-compatible terms to anyone who receives the
  binary (§1). Publicly hosting CardLift's source on GitHub, as
  already planned, would satisfy the *availability* half of this — but
  the source would need to actually carry an AGPL-compatible license
  for the combined work, which is a decision not yet made (and
  deliberately out of scope for this document).
- **If PySide6 is used under LGPLv3:** a copy of the LGPL license text
  and a prominent notice of LGPL component usage must be provided to
  users, and PySide6 must remain dynamically linked/replaceable rather
  than statically merged in a way that prevents relinking. Source:
  [Qt — Open Source LGPL Obligations](https://www.qt.io/licensing/open-source-lgpl-obligations).
- **Pillow's copyright and permission notice** must be preserved
  somewhere in the distributed product's documentation. Source:
  [Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE).

### Recommended
(not textually mandated by any single license, but directly reduces ambiguity in meeting the requirements above)

- A single consolidated `NOTICE`/third-party-licenses file listing
  every distributed dependency, its license, and a link to its official
  license text — satisfies Pillow's and PySide6's notice requirements
  in one place instead of scattering them.
- Deciding — and documenting — whether PyMuPDF is used under AGPL or a
  purchased Artifex commercial license *before* the first binary is
  distributed, since that choice determines what else is required.

### Common practice
(widely done in comparable projects, not required by any license text reviewed here)

- An in-app "About"/"Licenses" screen or menu item listing third-party
  components — user-friendly, not required by any source reviewed.
- Shipping license files verbatim inside the installed application's
  own folder (e.g. a `licenses/` subdirectory next to the `.exe`) —
  satisfies "provide a copy of the license text" without depending on a
  GitHub link that could go stale or require network access to view
  (notably relevant given CardLift's own stated local-first,
  no-network-dependency posture in `docs/PRIVACY_PROMISES.md`).

---

## 4. Unknowns requiring legal advice

Stated plainly, not glossed over:

1. **Whether CardLift's specific packaging architecture (a Python
   interpreter plus bundled compiled extension modules, invoked via
   `import fitz`) legally constitutes a "combined work" under AGPL's
   copyleft scope, versus mere aggregation.** Artifex's own stated
   position (§1) is that it does, and as the copyright holder their
   interpretation is the one that would actually matter in a dispute —
   but the general question of what counts as "linking" for an
   interpreted language calling into a compiled extension module has
   real, unsettled edges in the wider FOSS-licensing literature,
   independent of what any one licensor prefers. This document reports
   Artifex's stated position; whether it matches a from-first-principles
   legal reading isn't something to resolve without counsel.
2. **What specific steps would make CardLift's own source AGPL-compliant**,
   if the AGPL (not commercial) path is chosen. Not addressed here, per
   the explicit instruction not to draft policy or choose a license.
3. **Whether CardLift's product itself (processing user-supplied
   Print-and-Play PDFs) raises separate IP questions unrelated to
   dependency licensing** — outside this document's scope, flagged only
   so it isn't silently assumed to be covered by the analysis above.
4. **Whether accepting AGPL for CardLift's own source is commercially
   acceptable, versus purchasing an Artifex commercial license** — a
   cost/tradeoff business decision this document doesn't evaluate.
5. **The precise scope of "distribution" for a small, private alpha
   test group.** The license texts reviewed here use "convey"/"distribute"
   without a numerical or "private group" carve-out; how narrowly or
   broadly that's interpreted in practice for a small, non-adversarial
   private alpha is a question for counsel, not this document.

Any of the above, if it turns out to matter, is worth a short
conversation with an actual IP/licensing attorney before the first
binary leaves the development machine. This document is factual
research, not a substitute for that conversation.

---

## 5. Engineering-oriented summary

For developers, not lawyers:

- **PyMuPDF is the actual blocker.** It's AGPL/commercial dual-licensed
  by Artifex. Using the free AGPL option, per Artifex's own stated
  position, means CardLift's own source needs to be made available
  under AGPL-compatible terms to anyone who gets the binary. There is
  no free option that lets CardLift stay closed-source while using
  PyMuPDF as-is.
- **Donations don't change this.** Money changing hands — or not — has
  no bearing on AGPL/GPL obligations, confirmed directly by the FSF's
  own guidance. There's no "AGPL, but exempt because it's
  donation-supported" middle ground.
- **PySide6 is the easy one, if used correctly.** Under its LGPLv3
  option, CardLift can stay closed-source as long as PySide6 stays
  dynamically linked (the normal way Python imports it anyway) and
  users get a license notice plus the ability to replace the library.
  No disclosure of CardLift's own source required.
- **Pillow is a non-issue.** Permissive license; just needs its notice
  preserved somewhere in the distribution.
- **pytest doesn't matter for distribution** — dev-only, never ships in
  the built app.
- **PyInstaller (if used) doesn't add obligations** — its GPL exception
  exists specifically so frozen apps aren't GPL-contaminated by the
  packaging tool itself.
- **The decision that actually has to be made before packaging isn't
  "how do we comply with AGPL" — it's "do we open-source CardLift
  itself (AGPL), or pay Artifex for a commercial license instead."**
  That's a business/product decision this document deliberately doesn't
  make.
- **A single third-party-notices file, decided and written before the
  first binary ships, is the practical mechanism** that satisfies
  Pillow's and PySide6's (and, if AGPL is chosen, PyMuPDF's) notice
  obligations in one place.
