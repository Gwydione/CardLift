# THIRD_PARTY_NOTICES.md

# Third-Party Software Notices

DeckForge is built on the work of several open-source software projects.
This document identifies the principal third-party software used by
DeckForge together with its purpose and license.

We believe acknowledging the software we depend on---and complying with
the licenses that make those projects possible---is an important part of
responsible open-source stewardship.

This document is intended to provide transparency and acknowledgement.
It does not replace the individual license terms that govern each
dependency.

------------------------------------------------------------------------

# Runtime Dependencies

## PyMuPDF

**Purpose**

Renders PDF pages used throughout DeckForge for page selection,
calibration, review, and export.

**Project**

https://pymupdf.readthedocs.io/

**License**

GNU Affero General Public License v3.0 (AGPL-3.0) or Commercial License.

**DeckForge's choice**

DeckForge uses PyMuPDF under its AGPL-3.0 option, which is why DeckForge
itself is distributed under the GNU AGPLv3 (see `LICENSE`). Full
research and reasoning: `docs/LICENSE_RESEARCH.md`.

------------------------------------------------------------------------

## Pillow

**Purpose**

Performs image processing during card extraction and export.

**Project**

https://python-pillow.org/

**License**

MIT-CMU License.

------------------------------------------------------------------------

## PySide6 *(GUI version only)*

**Purpose**

Provides the cross-platform desktop user interface.

**Project**

https://www.qt.io/qt-for-python

**License**

GNU Lesser General Public License v3.0 (LGPL-3.0) or Commercial License.

------------------------------------------------------------------------

# Development Dependencies

## pytest

**Purpose**

Provides the automated unit testing framework used to validate
DeckForge.

**Project**

https://pytest.org/

**License**

MIT License.

------------------------------------------------------------------------

# Why So Few Dependencies?

DeckForge intentionally keeps its dependency footprint small.

Every third-party dependency introduces long-term maintenance, security,
licensing, and compatibility considerations. New dependencies are
evaluated carefully and added only when they provide meaningful value to
the project.

Keeping the dependency footprint small helps make DeckForge easier to
understand, maintain, and trust over time.
