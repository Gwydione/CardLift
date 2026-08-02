"""Review Cards workspace: the last checkpoint before Export.

Renders every suggested card (see review_state.build_review_cards()) as a
clickable thumbnail grouped under its source PDF page, plus one Shared
Back preview shown once (it's identical for every card, not a per-card
fact -- see find_cards_state.SharedBackStatus). Clicking a thumbnail
toggles whether it's included, for the common case of a suggested grid
over-counting a partly-filled page (see review_state.py's module
docstring).

WHY THIS CALLS CardCropper DIRECTLY, NOT DeckExporter
-------------------------------------------------------
deckforge.exporter.DeckExporter is CLI-shaped: it discovers the PDF by
scanning sample_decks/ or the project root via profile.pdf_file, and every
operation writes straight to fixed preview/ or output/ folders on disk.
This workspace already has the PDF open (the same PDFRenderer instance,
whatever path the user chose) and wants in-memory PIL images to page
through live, re-cropped on every toggle -- not files rewritten per click.
deckforge.cropper.CardCropper is the lower engine layer built for exactly
this ("given a rendered page image ... produce PIL Images for each card
cell"), so this workspace calls it directly. See DEVELOPER.md's "Review
Cards milestone" section for the full reasoning.

Trim is always zero here -- see calibrate_state.py's CalibratedGeometry:
the two-corner click the user made in Calibrate already IS the exact crop
box, unlike the CLI's eyeballed-pixel-coordinates flow that trim exists to
adjust after the fact.

CARD INSPECTION (_CardInspector)
---------------------------------
Ports the CLI's --inspect idea (a closer, high-fidelity look at one card,
with a margin of surrounding page content, for when the grid's small
thumbnails aren't enough to judge a crop) into the GUI, as a workspace
overlay rather than a rendered file the user has to go find. It is
deliberately not a general-purpose zoom/pan viewer: no interactive zoom,
no persistent pan mode, no per-card "inspected" tracking or deck-wide
progress count. Review exists to build confidence through representative
sampling, not to demand exhaustive inspection -- see docs/ui/UI_DECISIONS.md's
"Card Inspection" section for the full reasoning.

Opening/closing the inspector never touches _scroll_area, so the grid's
scroll position is preserved automatically rather than needing to be
saved/restored. High-fidelity renders happen on demand, per page, cached
only for the lifetime of the current grid (_inspect_page_cache) -- never
pre-rendered for the whole deck.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRegion,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from deckforge.cropper import CardCropper
from deckforge.pdf_renderer import PDFRenderError, PDFRenderer
from deckforge.profile import GridGeometry, TrimValues

from .calibrate_state import CalibratedGeometry, CalibrateState, CalibrationTarget, paired_topology_mismatch
from .find_cards_state import BackMode, FindCardsState, SharedBackStatus
from .review_state import (
    ReviewCard,
    ReviewCardsState,
    build_review_cards,
    review_guidance_text,
    review_ready,
    review_status_text,
)
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    BG_CARD,
    BG_WORKSPACE,
    BORDER_CARD,
    FONT_BODY,
    FONT_BODY_SM,
    FONT_CAPTION,
    TEXT_BODY,
    TEXT_CAPTION_MUTED,
    TEXT_HEADING,
)

# Lower than Calibrate's CALIBRATE_RENDER_SCALE (4.0) -- these are small
# review thumbnails, not a precision click target, and this workspace may
# render many of them at once.
REVIEW_RENDER_SCALE = 1.5

_ZERO_TRIM = TrimValues(0.0, 0.0, 0.0, 0.0)

_TILE_SIZE = 150
_TILE_SPACING = 10

# Mirrors the CLI's own --inspect scale/margin (exporter.DeckExporter's
# INSPECT_SCALE_MULTIPLIER / INSPECT_MARGIN_PT) -- same product idea, kept
# as GUI-local constants rather than importing DeckExporter, which is
# CLI-shaped (see "WHY THIS CALLS CardCropper DIRECTLY" above).
INSPECT_RENDER_SCALE = REVIEW_RENDER_SCALE * 3
INSPECT_MARGIN_PT = 24.0

# Paired Backs' side-by-side inspection shows two context-margined crops at
# once, so INSPECT_MARGIN_PT's neighboring-card content (fine for one image)
# doubles up and competes with the actual front/back comparison. This floor
# keeps a sliver of page context around each crop -- enough to still judge
# placement -- even on a very tight-gap deck where the neighbor-safe margin
# would otherwise round down to nothing.
PAIRED_INSPECT_MARGIN_FLOOR_PT = 4.0

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


class _CardTile(QWidget):
    """One suggested card: its cropped thumbnail, a border/checkmark
    showing whether it's included, and a click to toggle. No caption --
    row/col is an implementation detail (DESIGN_PRINCIPLES.md), the
    per-page header above each grid section is context enough.

    A second, small "look closer" affordance (bottom-right corner, opposite
    the include/exclude badge) opens the card inspector -- always visible
    rather than hover-only, since a feature whose whole purpose is building
    confidence shouldn't depend on a user incidentally discovering it, but
    it intensifies on hover so the interactivity still reads as intentional
    (DESIGN_SYSTEM.md). It's a distinct click target so the existing
    toggle-inclusion click is completely unchanged.

    PAIRED BACKS: THE GLYPH ITSELF SIGNALS THE RICHER INTERACTION
    ------------------------------------------------------------------
    Manual testing found that a tooltip alone doesn't fix discoverability
    here -- a tooltip only pays off once someone is already hovering with
    a reason to. `is_paired` (only ever True for Paired Backs cards) swaps
    the badge's resting glyph from the plain magnifying glass to two small
    overlapping rounded "card" shapes, the same way _draw_badge() above
    already swaps between a checkmark and an X depending on inclusion --
    same badge circle, same size/position, same hover-intensify behavior,
    same click target; only the glyph drawn inside changes, so a Paired
    deck's tiles look different at rest, before any hover or click."""

    toggled = Signal(object)  # emits the ReviewCard this tile represents
    look_closer_requested = Signal(object)  # emits the ReviewCard

    _LOOK_CLOSER_RADIUS = 9
    _LOOK_CLOSER_MARGIN = 4

    def __init__(
        self, card: ReviewCard, pixmap: QPixmap, included: bool, is_paired: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.card = card
        self._included = included
        self._pixmap = pixmap
        self._hovered = False
        self._is_paired = is_paired
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        thumb_h = round(_TILE_SIZE * pixmap.height() / pixmap.width()) if pixmap.width() else _TILE_SIZE
        self.setFixedSize(_TILE_SIZE, thumb_h)
        if is_paired:
            self.setToolTip(f"PDF page {card.page_num} — compare front and paired back, or toggle include/exclude")
        else:
            self.setToolTip(f"PDF page {card.page_num} — look closer or toggle include/exclude")

    def set_included(self, included: bool) -> None:
        if included != self._included:
            self._included = included
            self.update()

    def _look_closer_rect(self, rect) -> QRect:  # noqa: ANN001 -- QRect
        r = self._LOOK_CLOSER_RADIUS
        cx = rect.right() - r - self._LOOK_CLOSER_MARGIN
        cy = rect.bottom() - r - self._LOOK_CLOSER_MARGIN
        return QRect(cx - r, cy - r, r * 2, r * 2)

    def enterEvent(self, event) -> None:  # noqa: ANN001 -- QEnterEvent
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001 -- QEvent
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._look_closer_rect(self.rect()).contains(event.position().toPoint()):
            self.look_closer_requested.emit(self.card)
        else:
            self.toggled.emit(self.card)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            rect = self.rect()
            scaled = self._pixmap.scaled(
                rect.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(0, 0, scaled)

            if not self._included:
                painter.fillRect(rect, QColor(255, 255, 255, 160))

            border_color = QColor(ACCENT) if self._included else QColor(TEXT_CAPTION_MUTED)
            pen = QPen(border_color, 2 if self._included else 1)
            if not self._included:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

            self._draw_badge(painter, rect)
            self._draw_look_closer(painter, rect)
        finally:
            painter.end()

    def _draw_badge(self, painter: QPainter, rect) -> None:  # noqa: ANN001 -- QRect
        badge_r = 9
        cx, cy = rect.right() - badge_r - 4, rect.top() + badge_r + 4
        if self._included:
            painter.setBrush(QColor(ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2)
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawLine(cx - 4, cy, cx - 1, cy + 3)
            painter.drawLine(cx - 1, cy + 3, cx + 4, cy - 3)
        else:
            painter.setBrush(QColor(BG_CARD))
            painter.setPen(QPen(QColor(TEXT_CAPTION_MUTED), 1.5))
            painter.drawEllipse(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2)
            painter.drawLine(cx - 4, cy - 4, cx + 4, cy + 4)
            painter.drawLine(cx - 4, cy + 4, cx + 4, cy - 4)

    def _draw_look_closer(self, painter: QPainter, rect) -> None:  # noqa: ANN001 -- QRect
        look_rect = self._look_closer_rect(rect)
        color = QColor(ACCENT) if self._hovered else QColor(TEXT_CAPTION_MUTED)
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.setPen(QPen(color, 1.5))
        painter.drawEllipse(look_rect)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._is_paired:
            self._draw_paired_cards_glyph(painter, look_rect, color)
        else:
            self._draw_magnifying_glass_glyph(painter, look_rect)

    @staticmethod
    def _draw_magnifying_glass_glyph(painter: QPainter, look_rect) -> None:  # noqa: ANN001 -- QRect
        """A plain magnifying-glass glyph (lens + handle) -- legible
        without a word, and avoids a new icon asset dependency. Every
        mode except Paired Backs (see _draw_paired_cards_glyph())."""
        lens_r = 3
        lens_center = QPoint(look_rect.center().x() - 1, look_rect.center().y() - 1)
        painter.drawEllipse(lens_center, lens_r, lens_r)
        painter.drawLine(
            lens_center.x() + 2, lens_center.y() + 2,
            look_rect.right() - 3, look_rect.bottom() - 3,
        )

    @staticmethod
    def _draw_paired_cards_glyph(painter: QPainter, look_rect, color: QColor) -> None:  # noqa: ANN001 -- QRect
        """Two small overlapping rounded-rect "cards" -- Paired Backs
        only (see class docstring, "PAIRED BACKS: THE GLYPH ITSELF
        SIGNALS THE RICHER INTERACTION"). Drawn back-card-first so the
        front card's fill occludes the overlap, reading as one card
        sitting slightly in front of another."""
        cx, cy = look_rect.center().x(), look_rect.center().y()
        card_w, card_h = 6, 8
        back_rect = QRect(round(cx - card_w / 2 + 2), round(cy - card_h / 2 + 2), card_w, card_h)
        front_rect = QRect(round(cx - card_w / 2 - 2), round(cy - card_h / 2 - 2), card_w, card_h)

        painter.setPen(QPen(color, 1.2))
        painter.drawRoundedRect(back_rect, 1.5, 1.5)

        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(front_rect, 1.5, 1.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)


class _CardInspector(QWidget):
    """Full-workspace overlay: one card at a closer look. Not a QDialog and
    not added to ReviewWorkspace's own layout -- it's manually sized to
    cover the whole workspace (see ReviewWorkspace.resizeEvent()) and
    raised on top, so it reads as the workspace itself focusing on one
    card rather than a separate dialog application opening
    (DESIGN_SYSTEM.md: "CardLift is... not a collection of dialogs").

    Deliberately excludes: any zoom control, pan, a thumbnail filmstrip,
    and a deck-wide "card N of M" count -- the last one specifically
    because a raw count reads as a completion target, which contradicts
    Review's own job of building confidence through sampling rather than
    demanding exhaustive inspection. Position is instead conveyed only by
    which of Previous/Next is enabled and by the source page label.

    PAIRED BACKS: A SECOND IMAGE, NOT A SECOND FEATURE
    -----------------------------------------------------
    For Paired Backs, the review question stops being "is this crop
    right" and becomes "does this front correspond to the right back" --
    a relationship the front-only grid/inspector can never show. Rather
    than build a separate pairing UI, show_card() optionally takes a
    second pixmap for the paired back, displayed side by side with the
    front (front left, back right) at comparable scale, reusing this same
    overlay, the same Next/Previous stepping, and the same on-demand
    rendering discipline. When no back pixmap is given (Front Only,
    Shared Back, or this card simply hasn't been inspected yet), the
    layout is pixel-identical to before this feature existed -- the
    second image slot stays hidden and _image_label alone fills the row."""

    closed = Signal()
    previous_requested = Signal()
    next_requested = Signal()
    toggle_included_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"_CardInspector {{ background: {BG_WORKSPACE}; }}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pixmap: Optional[QPixmap] = None
        self._back_pixmap: Optional[QPixmap] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        self._page_label = QLabel("")
        self._page_label.setStyleSheet(
            f"color: {TEXT_HEADING}; font-size: {FONT_BODY_SM}px; font-weight: 600; background: transparent;"
        )
        header.addWidget(self._page_label)
        header.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setAutoDefault(False)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        _image_style = f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 8px;"
        images_row = QHBoxLayout()
        images_row.setSpacing(14)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(_image_style)
        images_row.addWidget(self._image_label, 1)

        # Hidden unless show_card() is given a back_pixmap -- see class
        # docstring, "PAIRED BACKS: A SECOND IMAGE, NOT A SECOND FEATURE".
        self._back_image_label = QLabel()
        self._back_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._back_image_label.setStyleSheet(_image_style)
        self._back_image_label.setVisible(False)
        images_row.addWidget(self._back_image_label, 1)

        outer.addLayout(images_row, 1)

        self._crop_caption = QLabel("The area inside the outline is what CardLift will export.")
        self._crop_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._crop_caption.setWordWrap(True)
        self._crop_caption.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        outer.addWidget(self._crop_caption)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self._prev_btn = QPushButton("‹ Previous")
        self._prev_btn.setAutoDefault(False)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._prev_btn.clicked.connect(self.previous_requested.emit)
        controls.addWidget(self._prev_btn)

        self._toggle_btn = QPushButton("")
        self._toggle_btn.setAutoDefault(False)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self._toggle_btn.clicked.connect(self.toggle_included_requested.emit)
        controls.addWidget(self._toggle_btn, 1)

        self._next_btn = QPushButton("Next ›")
        self._next_btn.setAutoDefault(False)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._next_btn.clicked.connect(self.next_requested.emit)
        controls.addWidget(self._next_btn)
        outer.addLayout(controls)

    def show_card(
        self, pixmap: QPixmap, page_num: int, included: bool, has_prev: bool, has_next: bool,
        back_pixmap: Optional[QPixmap] = None, back_ok: bool = True,
    ) -> None:
        """`back_pixmap` is None for every mode except Paired Backs, which
        keeps this identical to pre-Paired-Backs behavior for Front Only/
        Shared Back. `back_ok` distinguishes an actual paired-back crop
        from an honest placeholder (no pairing found, or it couldn't be
        rendered) -- see ReviewWorkspace._render_paired_back_inspect_
        pixmap(), the only caller that ever passes back_ok=False."""
        self._pixmap = pixmap
        self._back_pixmap = back_pixmap
        self._page_label.setText(f"PDF page {page_num}")
        self._prev_btn.setEnabled(has_prev)
        self._next_btn.setEnabled(has_next)
        self._toggle_btn.setText("Exclude this card" if included else "Include this card")
        self._back_image_label.setVisible(back_pixmap is not None)
        if back_pixmap is None:
            self._crop_caption.setText("The area inside the outline is what CardLift will export.")
        elif back_ok:
            self._crop_caption.setText(
                "Front (left) and its paired back (right). The area inside each outline is what CardLift will export."
            )
        else:
            self._crop_caption.setText(
                "Front (left). No paired back could be found or rendered for this card."
            )
        self._apply_scaled_pixmap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_scaled_pixmap()

    def _apply_scaled_pixmap(self) -> None:
        self._scale_into(self._image_label, self._pixmap)
        self._scale_into(self._back_image_label, self._back_pixmap)

    @staticmethod
    def _scale_into(label: QLabel, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None:
            return
        available = label.contentsRect().size()
        if available.width() > 0 and available.height() > 0:
            scaled = pixmap.scaled(
                available, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            label.setPixmap(scaled)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.closed.emit()
        elif event.key() == Qt.Key.Key_Left:
            self.previous_requested.emit()
        elif event.key() == Qt.Key.Key_Right:
            self.next_requested.emit()
        else:
            super().keyPressEvent(event)


class ReviewWorkspace(QWidget):
    """Central Review Cards workspace."""

    continue_clicked = Signal()
    back_to_calibrate_clicked = Signal()
    state_changed = Signal()  # A card was toggled -- lets MainWindow keep
    # the status bar and guidance panel in sync, same pattern as
    # FindCardsWorkspace.state_changed.

    def __init__(
        self,
        calibrate_state: CalibrateState,
        find_cards_state: FindCardsState,
        review_state: ReviewCardsState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.calibrate_state = calibrate_state
        self.find_cards_state = find_cards_state
        self.review_state = review_state

        self._renderer: Optional[PDFRenderer] = None
        self._page_count = 0
        self._cropper = CardCropper(REVIEW_RENDER_SCALE)
        self._tiles: dict[ReviewCard, _CardTile] = {}

        # -- card inspection (see _CardInspector's docstring) ---------------
        self._inspect_cropper = CardCropper(INSPECT_RENDER_SCALE)
        self._inspect_page_cache: dict[int, Image.Image] = {}
        self._card_list: list[ReviewCard] = []
        self._grid_geometry: Optional[GridGeometry] = None
        self._inspecting_index: Optional[int] = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"ReviewWorkspace {{ background: {BG_WORKSPACE}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # -- blocked-state message (Fronts/Shared Back not ready) --------
        self._blocked_label = QLabel("")
        self._blocked_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._blocked_label.setWordWrap(True)
        self._blocked_label.setStyleSheet(
            f"font-size: {FONT_BODY}px; color: {TEXT_BODY}; background: transparent;"
        )
        self._blocked_label.setVisible(False)
        outer.addWidget(self._blocked_label, 1)

        # -- Shared Back panel (shown once, applies to every card) -------
        back_row = QHBoxLayout()
        back_row.setSpacing(10)
        self._back_thumb_label = QLabel()
        self._back_thumb_label.setFixedHeight(126)
        self._back_thumb_label.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 6px;"
        )
        self._back_thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        back_row.addWidget(self._back_thumb_label)
        self._back_caption = QLabel("")
        self._back_caption.setWordWrap(True)
        self._back_caption.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; color: {TEXT_HEADING}; background: transparent;"
        )
        back_row.addWidget(self._back_caption, 1)
        self._back_panel = QWidget()
        self._back_panel.setLayout(back_row)
        outer.addWidget(self._back_panel)

        # -- scrollable card grid, grouped per Front Page ------------------
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._content = QWidget()
        self._content.setObjectName("reviewCardsContent")
        # ID-scoped, not a bare "background: ..." declaration -- this was
        # the confirmed root cause of the Review Cards card-tile tooltip
        # rendering with a transparent (rather than opaque white) interior:
        # an unscoped setStyleSheet() here leaked straight through to any
        # QToolTip owned by a _CardTile descendant, overriding gui_app.py's
        # app-level tooltip theme. See DEVELOPER.md's tooltip-rendering note.
        self._content.setStyleSheet("#reviewCardsContent { background: transparent; }")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch(1)
        self._scroll_area.setWidget(self._content)
        outer.addWidget(self._scroll_area, 1)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        outer.addWidget(self._status_label)

        footer = QHBoxLayout()
        self._back_to_calibrate_btn = QPushButton("‹ Back to Calibrate")
        self._back_to_calibrate_btn.setAutoDefault(False)
        self._back_to_calibrate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_to_calibrate_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._back_to_calibrate_btn.clicked.connect(self.back_to_calibrate_clicked.emit)
        footer.addWidget(self._back_to_calibrate_btn)
        footer.addStretch(1)
        self._continue_btn = QPushButton("Continue to Export ›")
        self._continue_btn.setAutoDefault(False)
        self._continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self.continue_clicked.emit)
        footer.addWidget(self._continue_btn)
        outer.addLayout(footer)

        # -- card inspector overlay ------------------------------------------
        # Not added to `outer` -- manually geometry-synced to cover the whole
        # workspace (see resizeEvent()) so it reads as this workspace
        # focusing on one card, not a child widget flowing in the layout.
        self._inspector = _CardInspector(self)
        self._inspector.setVisible(False)
        self._inspector.closed.connect(self._close_inspector)
        self._inspector.previous_requested.connect(self._inspect_previous)
        self._inspector.next_requested.connect(self._inspect_next)
        self._inspector.toggle_included_requested.connect(self._inspect_toggle_included)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 -- QResizeEvent
        super().resizeEvent(event)
        if self._inspector.isVisible():
            self._inspector.setGeometry(self.rect())

    # -- PDF loading -------------------------------------------------------

    def set_pdf(self, pdf_path: Path, page_count: int) -> None:
        self._close_renderer()
        self._renderer = PDFRenderer(pdf_path)
        self._page_count = page_count
        self._inspect_page_cache = {}

    def _close_renderer(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    # -- shared-app-frame hooks ---------------------------------------------

    def on_shown(self) -> None:
        """Called by MainWindow whenever this step becomes visible.
        MainWindow has already reset any stale Calibrate target before
        calling this (see main_window.py's Review-Cards staleness check,
        the same pattern Calibrate's own on_shown() relies on), so
        calibrate_state.cards/back can be trusted as-is here."""
        self._rebuild()

    def set_pan_active(self, active: bool) -> None:
        """No-op: Review Cards has no pan mode -- it's not a Calibrate step."""

    # -- building the view ---------------------------------------------------

    def _rebuild(self) -> None:
        # Any prior inspection is for a card list this rebuild may replace
        # entirely (different geometry, different front pages) -- always
        # start from the plain grid, never resume mid-inspection.
        self._close_inspector()
        self._inspect_page_cache = {}

        cards_target = self.calibrate_state.cards
        back_target = self.calibrate_state.back
        paired_back_target = self.calibrate_state.paired_back
        shared_back_status = self.find_cards_state.shared_back_status()
        back_mode = self.find_cards_state.back_mode()
        paired_topology_ok = self._paired_topology_ok(cards_target, paired_back_target)

        ready = review_ready(
            cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok,
        )
        if not ready or self._renderer is None:
            self._show_blocked(
                cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok,
            )
            return

        geometry = cards_target.geometry
        assert geometry is not None  # guaranteed by review_ready()
        card_list = build_review_cards(
            self.find_cards_state.front_pages(), geometry, self._page_size,
        )
        self.review_state.sync(card_list)
        self._card_list = card_list

        if not card_list:
            # A degenerate suggestion (e.g. the calibrated card is larger
            # than the page) -- route through the same prominent, centered
            # message as the other blocked states rather than leaving the
            # main content area silently blank with the explanation only
            # in the status bar (see DEVELOPER.md's UX Validation note).
            self._show_blocked(
                cards_target, back_target, shared_back_status, back_mode, paired_back_target, paired_topology_ok,
            )
            return

        self._blocked_label.setVisible(False)
        self._scroll_area.setVisible(True)
        self._back_panel.setVisible(True)
        self._render_back_panel(back_target, shared_back_status, back_mode)
        self._render_grid(card_list, geometry)
        self._update_footer(cards_target, back_target, shared_back_status, back_mode, paired_back_target)

    def _page_size(self, page_num: int) -> tuple[float, float]:
        assert self._renderer is not None
        return self._renderer.page_size(page_num)

    def _paired_topology_ok(
        self, cards_target: CalibrationTarget, paired_back_target: CalibrationTarget,
    ) -> bool:
        """True unless Front and Paired Back are both calibrated and
        suggest incompatible grid topology. Vacuously True whenever either
        target isn't complete yet (that incompleteness alone already
        blocks via review_ready()) or the page sizes can't be read -- this
        is purely a refinement on top of the completeness check, not a
        substitute for it. The only place this workspace's own open
        PDFRenderer is needed for the Paired Backs gate; mirrors
        calibrate_workspace.CalibrateWorkspace._paired_topology_mismatch(),
        the analogous check gating Calibrate's own Continue button, reused
        here via the same pure calibrate_state.paired_topology_mismatch()
        rather than re-deriving the comparison."""
        if not cards_target.is_complete or not paired_back_target.is_complete:
            return True
        if self._renderer is None:
            return True
        try:
            front_size = self._renderer.page_size(cards_target.calibrated_page_num)
            back_size = self._renderer.page_size(paired_back_target.calibrated_page_num)
        except PDFRenderError:
            return True
        assert cards_target.geometry is not None and paired_back_target.geometry is not None
        mismatch = paired_topology_mismatch(cards_target.geometry, front_size, paired_back_target.geometry, back_size)
        return mismatch is None

    def _show_blocked(
        self,
        cards_target: CalibrationTarget,
        back_target: CalibrationTarget,
        shared_back_status: SharedBackStatus,
        back_mode: BackMode = BackMode.SHARED,
        paired_back_target: Optional[CalibrationTarget] = None,
        paired_topology_ok: bool = True,
    ) -> None:
        self._clear_content()
        self._tiles = {}
        self._scroll_area.setVisible(False)
        self._back_panel.setVisible(False)
        _, body = review_guidance_text(
            cards_target, back_target, shared_back_status, self.review_state,
            back_mode, paired_back_target, paired_topology_ok,
        )
        self._blocked_label.setText(body)
        self._blocked_label.setVisible(True)
        self._status_label.setText(
            review_status_text(
                cards_target, back_target, shared_back_status, self.review_state,
                back_mode, paired_back_target, paired_topology_ok,
            )
        )
        self._continue_btn.setEnabled(False)

    def _render_back_panel(
        self, back_target: CalibrationTarget, shared_back_status: SharedBackStatus, back_mode: BackMode = BackMode.SHARED,
    ) -> None:
        """The one place Review Cards explains back-related state --
        Front Only and Shared Back's branches are unchanged; Paired Backs
        gets its own honest caption rather than the panel disappearing.
        There is no single "the back" to preview here the way Shared
        Back's one thumbnail works (calibrate_state.back was never
        calibrated for this mode, and each card can have a different
        back) -- per-card pairing is instead shown in Card Inspection
        (see _render_paired_back_inspect_pixmap()), so this caption
        points there rather than claiming it doesn't exist."""
        if back_mode is BackMode.PAIRED:
            self._back_thumb_label.setVisible(False)
            self._back_caption.setText(
                "Paired Backs — click “look closer” on any card below to compare it with its paired back."
            )
            return

        if shared_back_status is SharedBackStatus.CONFIRMED_NONE:
            self._back_thumb_label.setVisible(False)
            self._back_caption.setText("This deck is Front Only.")
            return

        # ASSIGNED and calibrated -- review_ready() already guarantees this.
        self._back_thumb_label.setVisible(True)
        assert self._renderer is not None
        assert back_target.geometry is not None and back_target.calibrated_page_num is not None
        page_image = self._renderer.render_page(back_target.calibrated_page_num, REVIEW_RENDER_SCALE)
        crop = self._cropper.crop_card(page_image, back_target.geometry.to_grid_geometry(), _ZERO_TRIM, 0, 0)
        pixmap = _pil_to_pixmap(crop).scaledToHeight(126, Qt.TransformationMode.SmoothTransformation)
        self._back_thumb_label.setPixmap(pixmap)
        self._back_caption.setText(
            f"Shared Back — from page {back_target.calibrated_page_num}, applied to every card below."
        )

    def _render_grid(self, card_list: list[ReviewCard], geometry: CalibratedGeometry) -> None:
        self._clear_content()
        self._tiles = {}
        assert self._renderer is not None
        grid_geometry = geometry.to_grid_geometry()
        self._grid_geometry = grid_geometry
        is_paired = self.find_cards_state.back_mode() is BackMode.PAIRED

        pages: list[int] = []
        for card in card_list:
            if card.page_num not in pages:
                pages.append(card.page_num)

        for page_num in pages:
            page_cards = [c for c in card_list if c.page_num == page_num]
            try:
                page_image: Optional[Image.Image] = self._renderer.render_page(page_num, REVIEW_RENDER_SCALE)
            except PDFRenderError:
                page_image = None

            header = QLabel(f"PDF page {page_num} — {len(page_cards)} suggested card{'s' if len(page_cards) != 1 else ''}")
            header.setStyleSheet(
                f"color: {TEXT_HEADING}; font-size: {FONT_BODY_SM}px; font-weight: 600; background: transparent;"
            )
            self._content_layout.insertWidget(self._content_layout.count() - 1, header)

            page_grid = QGridLayout()
            page_grid.setSpacing(_TILE_SPACING)
            for card in page_cards:
                pixmap = self._crop_pixmap(page_image, grid_geometry, card)
                tile = _CardTile(card, pixmap, self.review_state.is_included(card), is_paired=is_paired)
                tile.toggled.connect(self._on_tile_toggled)
                tile.look_closer_requested.connect(self._on_look_closer_requested)
                self._tiles[card] = tile
                page_grid.addWidget(tile, card.row, card.col)
            page_section = QWidget()
            page_section.setLayout(page_grid)
            self._content_layout.insertWidget(self._content_layout.count() - 1, page_section)

    def _crop_pixmap(self, page_image: Optional[Image.Image], geometry: GridGeometry, card: ReviewCard) -> QPixmap:
        if page_image is None:
            blank = Image.new("RGB", (100, 140), (230, 230, 230))
            return _pil_to_pixmap(blank)
        crop = self._cropper.crop_card(page_image, geometry, _ZERO_TRIM, card.row, card.col)
        return _pil_to_pixmap(crop)

    def _clear_content(self) -> None:
        while self._content_layout.count() > 1:  # keep the trailing stretch
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    # -- interaction -----------------------------------------------------

    def _on_tile_toggled(self, card: ReviewCard) -> None:
        self.review_state.toggle(card)
        tile = self._tiles.get(card)
        if tile is not None:
            tile.set_included(self.review_state.is_included(card))
        cards_target = self.calibrate_state.cards
        back_target = self.calibrate_state.back
        shared_back_status = self.find_cards_state.shared_back_status()
        back_mode = self.find_cards_state.back_mode()
        self._update_footer(cards_target, back_target, shared_back_status, back_mode, self.calibrate_state.paired_back)
        self.state_changed.emit()

    def _update_footer(
        self,
        cards_target: CalibrationTarget,
        back_target: CalibrationTarget,
        shared_back_status: SharedBackStatus,
        back_mode: BackMode = BackMode.SHARED,
        paired_back_target: Optional[CalibrationTarget] = None,
    ) -> None:
        # A toggle only ever happens once _rebuild() has already confirmed
        # review_ready() -- for PAIRED that means paired_back_target is
        # complete and topology already matched, so paired_topology_ok can
        # be assumed True here rather than re-resolving page sizes on every
        # single toggle.
        self._continue_btn.setEnabled(self.review_state.included_count() > 0)
        self._status_label.setText(
            review_status_text(
                cards_target, back_target, shared_back_status, self.review_state, back_mode, paired_back_target,
            )
        )

    # -- card inspection ---------------------------------------------------

    def _on_look_closer_requested(self, card: ReviewCard) -> None:
        if card not in self._card_list:
            return
        self._open_inspector(self._card_list.index(card))

    def _open_inspector(self, index: int) -> None:
        self._inspecting_index = index
        self._refresh_inspector()
        self._inspector.setGeometry(self.rect())
        self._inspector.setVisible(True)
        self._inspector.raise_()
        self._inspector.setFocus()

    def _close_inspector(self) -> None:
        self._inspecting_index = None
        self._inspector.setVisible(False)

    def _refresh_inspector(self) -> None:
        if self._inspecting_index is None:
            return
        card = self._card_list[self._inspecting_index]
        is_paired = self.find_cards_state.back_mode() is BackMode.PAIRED
        margin_pt = INSPECT_MARGIN_PT
        paired_geometry = self.calibrate_state.paired_back.geometry if is_paired else None
        if is_paired and self._grid_geometry is not None and paired_geometry is not None:
            margin_pt = self._paired_inspect_margin_pt(
                self._grid_geometry, paired_geometry.to_grid_geometry(),
            )
        pixmap = self._render_inspect_pixmap(card, margin_pt)
        back_pixmap: Optional[QPixmap] = None
        back_ok = True
        if is_paired:
            back_pixmap, back_ok = self._render_paired_back_inspect_pixmap(card, margin_pt)
        self._inspector.show_card(
            pixmap,
            card.page_num,
            self.review_state.is_included(card),
            has_prev=self._inspecting_index > 0,
            has_next=self._inspecting_index < len(self._card_list) - 1,
            back_pixmap=back_pixmap,
            back_ok=back_ok,
        )

    def _inspect_previous(self) -> None:
        if self._inspecting_index is not None and self._inspecting_index > 0:
            self._inspecting_index -= 1
            self._refresh_inspector()

    def _inspect_next(self) -> None:
        if self._inspecting_index is not None and self._inspecting_index < len(self._card_list) - 1:
            self._inspecting_index += 1
            self._refresh_inspector()

    def _inspect_toggle_included(self) -> None:
        if self._inspecting_index is None:
            return
        card = self._card_list[self._inspecting_index]
        self._on_tile_toggled(card)  # same toggle path the grid itself uses
        self._refresh_inspector()

    def _inspect_page_image(self, page_num: int) -> Optional[Image.Image]:
        """High-fidelity page render, generated on demand and cached only
        for the current grid's lifetime (cleared in _rebuild()/set_pdf()) --
        never pre-rendered for cards the user hasn't opened."""
        if page_num not in self._inspect_page_cache:
            assert self._renderer is not None
            try:
                self._inspect_page_cache[page_num] = self._renderer.render_page(page_num, INSPECT_RENDER_SCALE)
            except PDFRenderError:
                return None
        return self._inspect_page_cache.get(page_num)

    def _render_inspect_pixmap(self, card: ReviewCard, margin_pt: float = INSPECT_MARGIN_PT) -> QPixmap:
        page_image = self._inspect_page_image(card.page_num)
        if page_image is None or self._grid_geometry is None:
            return self._blank_inspect_pixmap()
        region, card_rect = self._inspect_cropper.crop_card_with_margin(
            page_image, self._grid_geometry, _ZERO_TRIM, card.row, card.col, margin_pt,
        )
        return self._outline_crop_pixmap(region, card_rect)

    @staticmethod
    def _paired_inspect_margin_pt(front_geometry: GridGeometry, back_geometry: GridGeometry) -> float:
        """Context margin for Paired Backs' side-by-side inspection, used
        symmetrically for both the front and back crop. Derived from the
        tighter of either geometry's own gap (not a blind fixed value) so
        the margin never actually reaches into a neighboring cell,
        regardless of how tight or loose this particular deck's grid is,
        while PAIRED_INSPECT_MARGIN_FLOOR_PT keeps at least a sliver of
        context visible even on a near-zero-gap deck. Never exceeds
        INSPECT_MARGIN_PT -- this only ever shrinks the existing margin,
        never grows it."""
        tightest_gap = min(front_geometry.gap_x, front_geometry.gap_y, back_geometry.gap_x, back_geometry.gap_y)
        return max(PAIRED_INSPECT_MARGIN_FLOOR_PT, min(INSPECT_MARGIN_PT, tightest_gap / 2.0))

    def _render_paired_back_inspect_pixmap(
        self, card: ReviewCard, margin_pt: float = INSPECT_MARGIN_PT
    ) -> tuple[QPixmap, bool]:
        """(pixmap, ok) for `card`'s paired back, only meaningful while
        back_mode() is PAIRED. The back page is resolved via find_cards_
        state.paired_back_page_for() (ordered-index pairing, Phase 1) and
        cropped at the *same* (row, col) on calibrate_state.paired_back's
        own, independently-calibrated geometry -- Front and Back are only
        guaranteed to share row/column topology (validated before Review
        Cards is ever reachable), not margins, card size, or gaps, so the
        cell index is the one thing safe to reuse as-is.

        ok is False whenever no paired back could be resolved or
        rendered -- an unbalanced deck reached via a stale sidebar jump,
        or a render failure -- in which case pixmap is the same honest
        gray placeholder _render_inspect_pixmap() already falls back to,
        never a crash or a silently wrong image."""
        back_page_num = self.find_cards_state.paired_back_page_for(card.page_num)
        paired_geometry = self.calibrate_state.paired_back.geometry
        if back_page_num is None or paired_geometry is None:
            return self._blank_inspect_pixmap(), False
        back_page_image = self._inspect_page_image(back_page_num)
        if back_page_image is None:
            return self._blank_inspect_pixmap(), False
        region, card_rect = self._inspect_cropper.crop_card_with_margin(
            back_page_image, paired_geometry.to_grid_geometry(), _ZERO_TRIM, card.row, card.col, margin_pt,
        )
        return self._outline_crop_pixmap(region, card_rect), True

    @staticmethod
    def _blank_inspect_pixmap() -> QPixmap:
        blank = Image.new("RGB", (200, 280), (230, 230, 230))
        return _pil_to_pixmap(blank)

    @staticmethod
    def _outline_crop_pixmap(region: Image.Image, card_rect: tuple[int, int, int, int]) -> QPixmap:
        """Shared visual treatment for an inspected crop-with-margin
        image -- dims everything outside the crop outline (reads as
        reference, not exported output; see UI_DECISIONS.md "Card
        Inspection") and draws the crop rectangle in the accent color.
        Used for both the front card and (Paired Backs) its paired back,
        so the two read as the same kind of inspection rather than two
        different features bolted together."""
        pixmap = _pil_to_pixmap(region)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, y0, x1, y1 = card_rect

        full_rect = pixmap.rect()
        crop_rect = QRect(x0, y0, x1 - x0, y1 - y0)
        dim_region = QRegion(full_rect) - QRegion(crop_rect)
        painter.setClipRegion(dim_region)
        painter.fillRect(full_rect, QColor(255, 255, 255, 160))
        painter.setClipping(False)

        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(crop_rect)
        painter.end()
        return pixmap


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(ImageQt(image))
