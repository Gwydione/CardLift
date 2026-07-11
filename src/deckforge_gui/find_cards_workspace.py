"""Select Card Pages workspace: page-by-page semantic classification.

The user pages through the loaded PDF and, for each page, says what it is:
a Front Page, the Shared Back, or neither (the default -- most pages, e.g.
instructions or reference material, need no marking at all). See
find_cards_state.py for why this is a page-level role rather than a
clicked point: the state that matters is "what is this whole page," and a
stored coordinate previously implied a click's location mattered when it
never did.

COORDINATE SPACES
------------------
Two coordinate spaces are in play (one fewer than before -- there is no
longer a click to convert):

1. Rendered-image pixels -- the page rasterized at the fixed
   PREVIEW_RENDER_SCALE via the engine's PDFRenderer. Independent of any
   profile (none exists yet at this point in the workflow).
2. Widget pixels -- the rendered image fit (never upscaled) and centered
   inside whatever size the canvas widget currently is.

FindCardsView.image_rect() still does this fit/center transform, recomputed
on every paint, since the canvas still needs to know where to draw the page
image and its role badge. Business logic (role assignment, the Shared Back
decision) lives entirely in FindCardsState; this module only turns button
clicks into calls against it and renders the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from deckforge.pdf_renderer import PDFRenderer

from .find_cards_state import FindCardsState, PageRole, SharedBackStatus
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

# Fixed points-to-pixels scale for rasterizing pages in Select Card Pages.
# There is no calibration profile yet at this point in the workflow
# (Calibrate comes after -- see docs/ui/UI_DECISIONS.md "Workflow"), so
# this is just a resolution high enough to look sharp once fit to a large
# window.
PREVIEW_RENDER_SCALE = 2.0

_BADGE_MARGIN = 10.0
_BADGE_PAD_X = 10.0
_BADGE_PAD_Y = 5.0

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
# to Calibrate once at least one page is marked as a Front Page. Every other
# control here (page nav) is secondary/outlined via _CONTROL_BUTTON_STYLE
# above; this is the only forward-progressing action, so it reads as the
# obvious next step rather than blending in with paging controls.
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

# "Mark as Front" -- the primary per-page control, used on every front page
# (many times a session), so it gets the same filled-accent-when-active
# weight as a primary action.
_FRONT_TOGGLE_STYLE = f"""
QPushButton {{
    padding: 10px 20px;
    border: 1px solid {BORDER_CARD};
    border-radius: 6px;
    background: {BG_CARD};
    color: {TEXT_HEADING};
    font-size: {FONT_BODY_SM}px;
    font-weight: 600;
}}
QPushButton:hover {{ background: #f1effa; border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
"""

# "Set as Shared Back" -- a secondary control, used at most once a session,
# so it stays visually lighter even when active (outline, not a fill) --
# it should never compete with the Front toggle for attention.
_BACK_TOGGLE_STYLE = f"""
QPushButton {{
    padding: 8px 16px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
    color: {TEXT_CAPTION_MUTED};
    font-size: {FONT_BODY_SM}px;
}}
QPushButton:hover {{ color: {TEXT_HEADING}; background: #f1effa; }}
QPushButton:checked {{ border-color: {ACCENT}; color: {ACCENT}; font-weight: 600; background: #f1effa; }}
"""

# The inline "Confirm there's no Shared Back" action -- appears only inside
# the Deck Summary's Shared Back line, only once should_prompt_shared_back()
# is true. Link-styled rather than a boxed button so it reads as part of
# the summary sentence, not a new competing control.
_LINK_BUTTON_STYLE = f"""
QPushButton {{
    border: none;
    background: transparent;
    color: {ACCENT};
    font-size: {FONT_CAPTION}px;
    font-weight: 600;
    text-decoration: underline;
    padding: 0px;
}}
QPushButton:hover {{ color: {ACCENT_HOVER}; }}
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
    """Maps PDF-page pixels to widget pixels, for the current page's
    rendered image displayed in the canvas. `render_scale` is the fixed
    points-to-pixels scale the page was rasterized at; `display_scale`
    additionally fits that rendered image into the widget without
    upscaling; `offset_x`/`offset_y` center the (possibly letterboxed)
    image within the widget."""

    render_scale: float
    display_scale: float
    offset_x: float
    offset_y: float

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
    """Just the page image and its role badge. No click handling -- a
    page's role is set via the toggle buttons below the canvas, never by
    where on the page the user clicks."""

    def __init__(self, workspace: "FindCardsWorkspace") -> None:
        super().__init__(workspace)
        self._workspace = workspace
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 8px;")
        self.setMinimumSize(160, 160)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            pixmap = self._workspace.current_pixmap()
            if pixmap is None or pixmap.isNull():
                return

            view = FindCardsView.fitting(
                pixmap.width(), pixmap.height(), self.width(), self.height(), PREVIEW_RENDER_SCALE,
            )
            x, y, w, h = view.image_rect(pixmap.width(), pixmap.height())
            painter.drawPixmap(QRectF(x, y, w, h), pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))

            role = self._workspace.current_role()
            if role is not None:
                self._draw_role_badge(painter, x, y, role)
        finally:
            painter.end()

    def _draw_role_badge(self, painter: QPainter, image_x: float, image_y: float, role: PageRole) -> None:
        text = "FRONT" if role is PageRole.FRONT else "SHARED BACK"
        filled = role is PageRole.FRONT

        font = QFont(painter.font())
        font.setPixelSize(FONT_CAPTION)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_w, text_h = metrics.horizontalAdvance(text), metrics.height()

        badge = QRectF(
            image_x + _BADGE_MARGIN, image_y + _BADGE_MARGIN,
            text_w + _BADGE_PAD_X * 2, text_h + _BADGE_PAD_Y * 2,
        )
        painter.setPen(QPen(QColor(ACCENT), 1.5))
        painter.setBrush(QColor(ACCENT) if filled else QColor(BG_CARD))
        painter.drawRoundedRect(badge, 5, 5)
        painter.setPen(QColor("white") if filled else QColor(ACCENT))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update()


class FindCardsWorkspace(QWidget):
    """Central Select Card Pages workspace: navigate the loaded PDF page by
    page and, for each page, mark it as a Front Page, the Shared Back, or
    leave it unmarked.

    Owns a PDFRenderer for the currently loaded PDF (opened once in
    set_pdf(), not reopened per page turn) and reuses it purely for
    rendering -- no detection or geometry logic lives here or in the
    engine; that's Calibrate's job in a later step, consuming the roles
    assigned here rather than rediscovering pages.
    """

    continue_clicked = Signal()
    state_changed = Signal()  # Any role/Shared-Back-decision change -- lets
    # MainWindow keep the status bar and guidance panel in sync without
    # them re-deriving FindCardsState changes themselves. Mirrors
    # CalibrateWorkspace.calibration_changed.

    def __init__(self, state: FindCardsState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._renderer: Optional[PDFRenderer] = None
        self._page_count = 0
        self._pixmap: Optional[QPixmap] = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # -- page navigation --------------------------------------------
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self._prev_btn = QPushButton("‹ Previous page")
        self._next_btn = QPushButton("Next page ›")
        for button in (self._prev_btn, self._next_btn):
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(_CONTROL_BUTTON_STYLE)

        self._page_label = QLabel("")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setStyleSheet(
            f"color: {TEXT_HEADING}; font-size: {FONT_BODY_SM}px; font-weight: 600; background: transparent;"
        )

        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label, 1)
        nav.addWidget(self._next_btn)
        outer.addLayout(nav)

        # -- per-page role controls ---------------------------------------
        roles = QHBoxLayout()
        roles.setSpacing(10)
        roles.addStretch(1)

        self._front_btn = QPushButton("Mark as Front")
        self._front_btn.setCheckable(True)
        self._front_btn.setAutoDefault(False)
        self._front_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._front_btn.setStyleSheet(_FRONT_TOGGLE_STYLE)

        self._back_btn = QPushButton("Set as Shared Back")
        self._back_btn.setCheckable(True)
        self._back_btn.setAutoDefault(False)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(_BACK_TOGGLE_STYLE)

        roles.addWidget(self._front_btn)
        roles.addWidget(self._back_btn)
        roles.addStretch(1)
        outer.addLayout(roles)

        self._canvas = _PageCanvas(self)
        outer.addWidget(self._canvas, 1)

        # -- Deck Summary: passive, except the Shared Back line's inline
        # confirm action, shown only once should_prompt_shared_back() is
        # true. ----------------------------------------------------------
        summary = QVBoxLayout()
        summary.setSpacing(2)

        self._front_summary_label = QLabel("")
        self._front_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._front_summary_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        summary.addWidget(self._front_summary_label)

        back_row = QHBoxLayout()
        back_row.setSpacing(6)
        back_row.addStretch(1)

        self._back_summary_label = QLabel("")
        self._back_summary_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        back_row.addWidget(self._back_summary_label)

        self._confirm_no_back_btn = QPushButton("Confirm there's no Shared Back")
        self._confirm_no_back_btn.setAutoDefault(False)
        self._confirm_no_back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_no_back_btn.setStyleSheet(_LINK_BUTTON_STYLE)
        self._confirm_no_back_btn.setVisible(False)
        back_row.addWidget(self._confirm_no_back_btn)
        back_row.addStretch(1)
        summary.addLayout(back_row)
        outer.addLayout(summary)

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
        self._front_btn.clicked.connect(self._on_front_toggled)
        self._back_btn.clicked.connect(self._on_back_toggled)
        self._confirm_no_back_btn.clicked.connect(self._on_confirm_no_back)
        self._continue_btn.clicked.connect(self._on_continue_clicked)

        self._refresh()

    # -- FindCardsWorkspace <-> _PageCanvas -----------------------------

    def current_pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def current_role(self) -> Optional[PageRole]:
        if not self._page_count:
            return None
        return self.state.role_for_page(self.state.current_page)

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
            self.state.note_page_viewed(self.state.current_page)
        self._canvas.update()
        self._refresh()

    # -- navigation --------------------------------------------------------

    def _go_previous(self) -> None:
        if self.state.current_page > 1:
            self.state.current_page -= 1
            self._load_current_page()

    def _go_next(self) -> None:
        if self.state.current_page < self._page_count:
            self.state.current_page += 1
            self._load_current_page()

    # -- role controls -------------------------------------------------------

    def _on_front_toggled(self) -> None:
        self.state.toggle_front(self.state.current_page)
        self._canvas.update()
        self._refresh()
        self.state_changed.emit()

    def _on_back_toggled(self) -> None:
        self.state.toggle_back(self.state.current_page)
        self._canvas.update()
        self._refresh()
        self.state_changed.emit()

    def _on_confirm_no_back(self) -> None:
        self.state.confirm_no_shared_back()
        self._refresh()
        self.state_changed.emit()

    def _on_continue_clicked(self) -> None:
        if self.state.front_page_count() == 0:
            return
        if self.state.shared_back_resolved():
            self.continue_clicked.emit()
            return
        # Shared Back is still unresolved -- this is the fallback trigger
        # for should_prompt_shared_back(): reveal the same Deck Summary
        # nudge reaching the last page would have shown, rather than
        # leaving. The user clicks Continue again once resolved.
        self.state.note_continue_attempted()
        self._refresh()

    # -- rendering -----------------------------------------------------------

    def _refresh(self) -> None:
        if self._page_count:
            self._page_label.setText(f"Page {self.state.current_page} of {self._page_count}")
        else:
            self._page_label.setText("No PDF loaded")

        self._prev_btn.setEnabled(self._page_count > 0 and self.state.current_page > 1)
        self._next_btn.setEnabled(self.state.current_page < self._page_count)

        role = self.current_role()
        self._front_btn.setChecked(role is PageRole.FRONT)
        self._back_btn.setChecked(role is PageRole.BACK)
        self._front_btn.setEnabled(self._page_count > 0)
        self._back_btn.setEnabled(self._page_count > 0)

        front_count = self.state.front_page_count()
        self._continue_btn.setEnabled(front_count > 0)

        self._refresh_deck_summary(front_count)

    def _refresh_deck_summary(self, front_count: int) -> None:
        if not self._page_count:
            self._front_summary_label.setText("Open a PDF on the Deck page to begin.")
            self._back_summary_label.setText("")
            self._confirm_no_back_btn.setVisible(False)
            return

        if front_count == 0:
            self._front_summary_label.setText("No Front Pages selected yet — mark at least one to continue.")
        else:
            noun = "page" if front_count == 1 else "pages"
            self._front_summary_label.setText(f"{front_count} Front {noun} selected.")

        status = self.state.shared_back_status()
        if status is SharedBackStatus.ASSIGNED:
            self._back_summary_label.setText(f"Shared Back: page {self.state.back_page()}.")
            self._confirm_no_back_btn.setVisible(False)
        elif status is SharedBackStatus.CONFIRMED_NONE:
            self._back_summary_label.setText("Shared Back: none.")
            self._confirm_no_back_btn.setVisible(False)
        else:
            # UNRESOLVED -- same wording as find_cards_status_text()'s
            # status-bar line regardless of whether the inline confirm
            # action below happens to be showing yet; that visibility is a
            # separate timing concern (should_prompt_shared_back()), not a
            # different fact about the Deck.
            self._back_summary_label.setText("Shared Back: not yet decided.")
            self._confirm_no_back_btn.setVisible(self.state.should_prompt_shared_back(self._page_count))

    def set_pan_active(self, active: bool) -> None:
        """No-op: Select Card Pages has no pan mode -- it's not a
        Calibrate step."""
