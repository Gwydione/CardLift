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
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
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

from .calibrate_state import CalibratedGeometry, CalibrateState, CalibrationTarget
from .find_cards_state import FindCardsState, SharedBackStatus
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


def _to_grid_geometry(geometry: CalibratedGeometry) -> GridGeometry:
    return GridGeometry(
        left=geometry.left, top=geometry.top,
        card_width=geometry.card_width, card_height=geometry.card_height,
        gap_x=geometry.gap_x, gap_y=geometry.gap_y,
    )


class _CardTile(QWidget):
    """One suggested card: its cropped thumbnail, a border/checkmark
    showing whether it's included, and a click to toggle. No caption --
    row/col is an implementation detail (DESIGN_PRINCIPLES.md), the
    per-page header above each grid section is context enough."""

    toggled = Signal(object)  # emits the ReviewCard this tile represents

    def __init__(self, card: ReviewCard, pixmap: QPixmap, included: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card = card
        self._included = included
        self._pixmap = pixmap
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        thumb_h = round(_TILE_SIZE * pixmap.height() / pixmap.width()) if pixmap.width() else _TILE_SIZE
        self.setFixedSize(_TILE_SIZE, thumb_h)
        self.setToolTip(f"PDF page {card.page_num}")

    def set_included(self, included: bool) -> None:
        if included != self._included:
            self._included = included
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

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
        self._content.setStyleSheet("background: transparent;")
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

    # -- PDF loading -------------------------------------------------------

    def set_pdf(self, pdf_path: Path, page_count: int) -> None:
        self._close_renderer()
        self._renderer = PDFRenderer(pdf_path)
        self._page_count = page_count

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
        cards_target = self.calibrate_state.cards
        back_target = self.calibrate_state.back
        shared_back_status = self.find_cards_state.shared_back_status()

        if not review_ready(cards_target, back_target, shared_back_status) or self._renderer is None:
            self._show_blocked(cards_target, back_target, shared_back_status)
            return

        geometry = cards_target.geometry
        assert geometry is not None  # guaranteed by review_ready()
        card_list = build_review_cards(
            self.find_cards_state.front_pages(), geometry, self._page_size,
        )
        self.review_state.sync(card_list)

        if not card_list:
            # A degenerate suggestion (e.g. the calibrated card is larger
            # than the page) -- route through the same prominent, centered
            # message as the other blocked states rather than leaving the
            # main content area silently blank with the explanation only
            # in the status bar (see DEVELOPER.md's UX Validation note).
            self._show_blocked(cards_target, back_target, shared_back_status)
            return

        self._blocked_label.setVisible(False)
        self._scroll_area.setVisible(True)
        self._back_panel.setVisible(True)
        self._render_back_panel(back_target, shared_back_status)
        self._render_grid(card_list, geometry)
        self._update_footer(cards_target, back_target, shared_back_status)

    def _page_size(self, page_num: int) -> tuple[float, float]:
        assert self._renderer is not None
        return self._renderer.page_size(page_num)

    def _show_blocked(
        self, cards_target: CalibrationTarget, back_target: CalibrationTarget, shared_back_status: SharedBackStatus,
    ) -> None:
        self._clear_content()
        self._tiles = {}
        self._scroll_area.setVisible(False)
        self._back_panel.setVisible(False)
        _, body = review_guidance_text(cards_target, back_target, shared_back_status, self.review_state)
        self._blocked_label.setText(body)
        self._blocked_label.setVisible(True)
        self._status_label.setText(review_status_text(cards_target, back_target, shared_back_status, self.review_state))
        self._continue_btn.setEnabled(False)

    def _render_back_panel(self, back_target: CalibrationTarget, shared_back_status: SharedBackStatus) -> None:
        if shared_back_status is SharedBackStatus.CONFIRMED_NONE:
            self._back_thumb_label.setVisible(False)
            self._back_caption.setText("This deck has no Shared Back.")
            return

        # ASSIGNED and calibrated -- review_ready() already guarantees this.
        self._back_thumb_label.setVisible(True)
        assert self._renderer is not None
        assert back_target.geometry is not None and back_target.calibrated_page_num is not None
        page_image = self._renderer.render_page(back_target.calibrated_page_num, REVIEW_RENDER_SCALE)
        crop = self._cropper.crop_card(page_image, _to_grid_geometry(back_target.geometry), _ZERO_TRIM, 0, 0)
        pixmap = _pil_to_pixmap(crop).scaledToHeight(126, Qt.TransformationMode.SmoothTransformation)
        self._back_thumb_label.setPixmap(pixmap)
        self._back_caption.setText(
            f"Shared Back — from page {back_target.calibrated_page_num}, applied to every card below."
        )

    def _render_grid(self, card_list: list[ReviewCard], geometry: CalibratedGeometry) -> None:
        self._clear_content()
        self._tiles = {}
        assert self._renderer is not None
        grid_geometry = _to_grid_geometry(geometry)

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
                tile = _CardTile(card, pixmap, self.review_state.is_included(card))
                tile.toggled.connect(self._on_tile_toggled)
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
        self._update_footer(cards_target, back_target, shared_back_status)
        self.state_changed.emit()

    def _update_footer(
        self, cards_target: CalibrationTarget, back_target: CalibrationTarget, shared_back_status: SharedBackStatus,
    ) -> None:
        self._continue_btn.setEnabled(self.review_state.included_count() > 0)
        self._status_label.setText(
            review_status_text(cards_target, back_target, shared_back_status, self.review_state)
        )


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(ImageQt(image))
