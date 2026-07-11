"""Find Cards workspace: page-by-page coarse card-grid scoping.

The user pages through the loaded PDF and, for each page that has a card
grid on it, clicks roughly where that grid begins -- one point marker per
page (see find_cards_state.py for why a point, not a rectangle: Calibrate's
own two-corner-click flow re-derives the precise card box later, so a
coarse region here would add nothing Calibrate can't already do more
precisely itself).

COORDINATE SPACES
------------------
Three coordinate spaces are in play, same layering calibrate_ui.py uses for
the CLI's --calibrate window:

1. PDF points (1/72", zoom 1.0) -- what FindCardsState stores. Stable
   forever, regardless of window size or render scale.
2. Rendered-image pixels -- the page rasterized at the fixed
   PREVIEW_RENDER_SCALE via the engine's PDFRenderer. Independent of any
   profile (none exists yet at this point in the workflow).
3. Widget pixels -- the rendered image fit (never upscaled) and centered
   inside whatever size the canvas widget currently is.

FindCardsView.point_to_widget()/widget_to_point() convert directly between
(1) and (3) in one step (folding the render scale and the fit/center
transform together), recomputed on every paint so a marker placed at any
window size, then viewed after a resize, is still exactly where it was
clicked. Business logic (state transitions) lives entirely in
FindCardsState; this module only turns paint/mouse events into calls
against it and a FindCardsView, per ENGINEERING_STANDARDS's "avoid business
logic in Qt widgets."
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from deckforge.pdf_renderer import PDFRenderer

from .find_cards_state import FindCardsState, PageMarker
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    BG_CARD,
    BG_WORKSPACE,
    BORDER_CARD,
    FONT_BODY_SM,
    FONT_CAPTION,
    TEXT_CAPTION_MUTED,
    TEXT_HEADING,
)

# Fixed points-to-pixels scale for rasterizing pages in Find Cards. There is
# no calibration profile yet at this point in the workflow (Calibrate comes
# after Find Cards -- see docs/ui/UI_DECISIONS.md "Workflow"), so this is
# just a resolution high enough to look sharp once fit to a large window.
PREVIEW_RENDER_SCALE = 2.0

MARKER_RADIUS = 7.0

_CONTROL_BUTTON_STYLE = f"""
QPushButton {{
    padding: 6px 14px;
    border: 1px solid {BORDER_CARD};
    border-radius: 6px;
    background: {BG_CARD};
    color: {TEXT_HEADING};
    font-size: {FONT_BODY_SM}px;
}}
QPushButton:hover {{ background: #f1effa; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #e9e4fb; }}
QPushButton:disabled {{ color: {TEXT_CAPTION_MUTED}; background: {BG_WORKSPACE}; }}
"""

# Filled/accent variant for the one primary action on this page -- moving on
# to Calibrate once at least one page is marked. Every other control here
# (page nav, clear) is secondary/outlined via _CONTROL_BUTTON_STYLE above;
# this is the only forward-progressing action, so it reads as the obvious
# next step rather than blending in with paging controls.
_PRIMARY_BUTTON_STYLE = f"""
QPushButton {{
    padding: 8px 18px;
    border: none;
    border-radius: 6px;
    background: {ACCENT};
    color: white;
    font-size: {FONT_BODY_SM}px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton:disabled {{ background: #cfc9e8; color: #f4f2fb; }}
"""


def fit_scale(image_w: float, image_h: float, max_w: float, max_h: float) -> float:
    """Scale factor to fit an image within (max_w, max_h) without
    upscaling past its native resolution. 1.0 if it already fits, or if
    any dimension is non-positive (nothing sensible to fit yet)."""
    if image_w <= 0 or image_h <= 0 or max_w <= 0 or max_h <= 0:
        return 1.0
    return min(1.0, max_w / image_w, max_h / image_h)


@dataclass(frozen=True)
class FindCardsView:
    """Maps PDF points directly to widget pixels and back, for the current
    page's rendered image displayed in the canvas. `render_scale` is the
    fixed points-to-pixels scale the page was rasterized at;
    `display_scale` additionally fits that rendered image into the widget
    without upscaling; `offset_x`/`offset_y` center the (possibly
    letterboxed) image within the widget."""

    render_scale: float
    display_scale: float
    offset_x: float
    offset_y: float

    def point_to_widget(self, x_pt: float, y_pt: float) -> tuple[float, float]:
        scale = self.render_scale * self.display_scale
        return (x_pt * scale + self.offset_x, y_pt * scale + self.offset_y)

    def widget_to_point(self, wx: float, wy: float) -> tuple[float, float]:
        scale = self.render_scale * self.display_scale
        return ((wx - self.offset_x) / scale, (wy - self.offset_y) / scale)

    def image_rect(self, image_w: float, image_h: float) -> tuple[float, float, float, float]:
        """The (x, y, width, height) the rendered image occupies inside
        the widget, in widget pixels."""
        return (self.offset_x, self.offset_y, image_w * self.display_scale, image_h * self.display_scale)

    @classmethod
    def fitting(
        cls, image_w: float, image_h: float, widget_w: float, widget_h: float, render_scale: float,
    ) -> "FindCardsView":
        scale = fit_scale(image_w, image_h, widget_w, widget_h)
        offset_x = (widget_w - image_w * scale) / 2
        offset_y = (widget_h - image_h * scale) / 2
        return cls(render_scale=render_scale, display_scale=scale, offset_x=offset_x, offset_y=offset_y)


class _PageCanvas(QWidget):
    """Just the page image and its marker. Painting and click handling are
    scoped to this widget alone so they never interfere with the
    surrounding page-navigation controls."""

    def __init__(self, workspace: "FindCardsWorkspace") -> None:
        super().__init__(workspace)
        self._workspace = workspace
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 8px;")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(160, 160)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            pixmap = self._workspace.current_pixmap()
            if pixmap is None or pixmap.isNull():
                self._workspace.set_view(None)
                return

            view = FindCardsView.fitting(
                pixmap.width(), pixmap.height(), self.width(), self.height(), PREVIEW_RENDER_SCALE,
            )
            self._workspace.set_view(view)

            x, y, w, h = view.image_rect(pixmap.width(), pixmap.height())
            painter.drawPixmap(QRectF(x, y, w, h), pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))

            marker = self._workspace.current_marker()
            if marker is not None:
                wx, wy = view.point_to_widget(marker.x, marker.y)
                painter.setPen(QPen(QColor(ACCENT), 2))
                painter.setBrush(QColor(ACCENT))
                painter.drawEllipse(QPointF(wx, wy), MARKER_RADIUS, MARKER_RADIUS)
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        view = self._workspace.current_view()
        pixmap = self._workspace.current_pixmap()
        if view is None or pixmap is None:
            return

        wx, wy = event.position().x(), event.position().y()
        x, y, w, h = view.image_rect(pixmap.width(), pixmap.height())
        if not (x <= wx <= x + w and y <= wy <= y + h):
            return  # click landed in the letterboxed margin, not the page

        x_pt, y_pt = view.widget_to_point(wx, wy)
        self._workspace.place_marker(x_pt, y_pt)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update()


class FindCardsWorkspace(QWidget):
    """Central Find Cards page: navigate the loaded PDF page by page and
    mark, per page, roughly where a card grid begins.

    Owns a PDFRenderer for the currently loaded PDF (opened once in
    set_pdf(), not reopened per page turn) and reuses it purely for
    rendering -- no detection or geometry logic lives here or in the
    engine; that's Calibrate's job in a later milestone.
    """

    continue_clicked = Signal()

    def __init__(self, state: FindCardsState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._renderer: Optional[PDFRenderer] = None
        self._page_count = 0
        self._pixmap: Optional[QPixmap] = None
        self._view: Optional[FindCardsView] = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._prev_btn = QPushButton("‹ Previous page")
        self._next_btn = QPushButton("Next page ›")
        self._clear_btn = QPushButton("Clear this page")
        for button in (self._prev_btn, self._next_btn, self._clear_btn):
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(_CONTROL_BUTTON_STYLE)

        self._page_label = QLabel("")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setStyleSheet(
            f"color: {TEXT_HEADING}; font-size: {FONT_BODY_SM}px; font-weight: 600; background: transparent;"
        )

        controls.addWidget(self._prev_btn)
        controls.addWidget(self._page_label, 1)
        controls.addWidget(self._next_btn)
        controls.addSpacing(16)
        controls.addWidget(self._clear_btn)
        outer.addLayout(controls)

        self._canvas = _PageCanvas(self)
        outer.addWidget(self._canvas, 1)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        outer.addWidget(self._status_label)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._continue_btn = QPushButton("Continue to Calibrate ›")
        self._continue_btn.setAutoDefault(False)
        self._continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        footer.addWidget(self._continue_btn)
        outer.addLayout(footer)

        self._prev_btn.clicked.connect(self._go_previous)
        self._next_btn.clicked.connect(self._go_next)
        self._clear_btn.clicked.connect(self._clear_current_page)
        self._continue_btn.clicked.connect(self.continue_clicked.emit)

        self._update_labels()

    # -- FindCardsWorkspace <-> _PageCanvas -----------------------------

    def current_pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def current_marker(self) -> Optional[PageMarker]:
        if not self._page_count:
            return None
        return self.state.marker_for_page(self.state.current_page)

    def current_view(self) -> Optional[FindCardsView]:
        return self._view

    def set_view(self, view: Optional[FindCardsView]) -> None:
        self._view = view

    def place_marker(self, x_pt: float, y_pt: float) -> None:
        self.state.set_marker(self.state.current_page, x_pt, y_pt)
        self._canvas.update()
        self._update_labels()

    # -- PDF loading -----------------------------------------------------

    def set_pdf(self, pdf_path: Path, page_count: int) -> None:
        """Opens `pdf_path` for rendering and starts back on page 1.
        Replaces (closes) any previously open PDF."""
        self._close_renderer()
        self._renderer = PDFRenderer(pdf_path)
        self._page_count = page_count
        self.state.current_page = 1
        self._load_current_page()

    def _close_renderer(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def _load_current_page(self) -> None:
        self._pixmap = None
        if self._renderer is not None and self._page_count:
            page_image: Image.Image = self._renderer.render_page(self.state.current_page, PREVIEW_RENDER_SCALE)
            self._pixmap = QPixmap.fromImage(ImageQt(page_image))
        self._canvas.update()
        self._update_labels()

    # -- navigation / clearing -------------------------------------------

    def _go_previous(self) -> None:
        if self.state.current_page > 1:
            self.state.current_page -= 1
            self._load_current_page()

    def _go_next(self) -> None:
        if self.state.current_page < self._page_count:
            self.state.current_page += 1
            self._load_current_page()

    def _clear_current_page(self) -> None:
        self.state.clear_page(self.state.current_page)
        self._canvas.update()
        self._update_labels()

    def _update_labels(self) -> None:
        if self._page_count:
            self._page_label.setText(f"Page {self.state.current_page} of {self._page_count}")
        else:
            self._page_label.setText("No PDF loaded")

        self._prev_btn.setEnabled(self._page_count > 0 and self.state.current_page > 1)
        self._next_btn.setEnabled(self.state.current_page < self._page_count)
        self._clear_btn.setEnabled(self.current_marker() is not None)

        count = self.state.marked_page_count()
        self._continue_btn.setEnabled(count > 0)

        if self._page_count:
            noun = "page" if count == 1 else "pages"
            marked_text = f"{count} of {self._page_count} {noun} marked with a card grid"
            if count == 0:
                marked_text += " — mark at least one page to continue"
            self._status_label.setText(marked_text)
        else:
            self._status_label.setText("Open a PDF on the Deck page to begin.")

    def set_pan_active(self, active: bool) -> None:
        """No-op: Find Cards has no pan mode -- it's not a Calibrate step."""
