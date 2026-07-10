"""Find Cards state -- coarse, page-level card-grid markers.

Deliberately free of any PySide6 import, same rationale as app_state.py and
session.py: this is the controller/session layer the GUI reads from, kept
separate from widget code and unit tested without opening a window.

Find Cards is a coarse scoping step, not calibration: the user pages through
the PDF and marks, per page, roughly where a card grid begins -- one point
per page, nothing more. It deliberately does not derive rows/cols/card size
or any precise crop geometry; that is Calibrate's job (see calibrate_ui.py's
two-corner-click flow, reused via measure.derive_geometry()), which comes
after Find Cards in the documented workflow order (see
docs/ui/UI_DECISIONS.md "Workflow").

COORDINATE SPACE
-----------------
Each marker is stored as (page_num, x, y) in PDF points -- the same
canonical page coordinate space profile.py/geometry.py already use
everywhere (1/72", at zoom 1.0, independent of render_scale; see README
"How the grid math works"). Storing in points rather than rendered-image or
canvas pixels means a marker stays correct no matter how the workspace is
resized, fit, or (later) zoomed/panned -- only the widget that draws it
needs to know the current display transform.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageMarker:
    """One coarse "this page has a card grid" point on a page, in PDF
    points.

    The marker is presence-based: only whether a page has one matters to
    the current workflow (see marked_page_count()/marked_pages()). The
    (x, y) location is stored and preserved, but deliberately carries no
    semantic meaning yet -- Calibrate re-derives precise geometry on its
    own via its own two-corner-click flow, independent of this marker.
    Keeping the coordinate around is a placeholder for a possible future
    UX enhancement (e.g. centering the Calibrate view on it, or seeding
    Calibrate's first click), not a workflow dependency."""
    page_num: int
    x: float
    y: float


@dataclass
class FindCardsState:
    current_page: int = 1
    _markers: dict[int, PageMarker] = field(default_factory=dict)

    def set_marker(self, page_num: int, x: float, y: float) -> None:
        """Places or replaces the marker for `page_num`. A page holds at
        most one marker -- placing a new one always replaces the last."""
        self._markers[page_num] = PageMarker(page_num=page_num, x=x, y=y)

    def marker_for_page(self, page_num: int) -> PageMarker | None:
        return self._markers.get(page_num)

    def clear_page(self, page_num: int) -> None:
        self._markers.pop(page_num, None)

    def clear_all(self) -> None:
        self._markers.clear()

    def marked_page_count(self) -> int:
        return len(self._markers)

    def marked_pages(self) -> list[int]:
        return sorted(self._markers)
