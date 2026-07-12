"""Calibrate workspace: precise two-corner-click card geometry, for
either the "Fronts" or "Shared Back" workflow step.

One CalibrateWorkspace instance backs each step (see workspaces.py),
sharing the same CalibrateState -- they differ only in which
CalibrationTarget they read/write and where their page list comes from:
Fronts is restricted to the Front Pages Select Card Pages assigned
(find_cards_state), Shared Back opens directly on the single page Select
Card Pages assigned as the Shared Back -- Calibrate never searches for it.

The Shared Back step must show one of three distinct states, per
find_cards_state.SharedBackStatus, never conflating the last two:
ASSIGNED (show and calibrate that page normally), CONFIRMED_NONE (an
explicit "no Shared Back" Deck -- nothing to calibrate, treated as already
complete), or UNRESOLVED (the question hasn't been answered in Select Card
Pages yet -- Calibrate must not guess, must not offer Continue, and must
point the user back to Select Card Pages rather than silently behaving
like CONFIRMED_NONE). See _update_continue_footer().

Reuses the CLI's calibration math and click semantics (calibrate_state.py
-- record_click/normalize_box/infer_second_cell, all ported/adapted from
measure.py and calibrate_ui.py) and the ported ViewTransform for zoom/pan,
but draws overlays with Qt's immediate-mode QPainter (view_transform.py's
zoom/pan/fit math, find_cards_workspace.py's rendering pattern) rather
than reimplementing calibrate_ui.py's Tkinter canvas-item approach.

COORDINATE SPACES
-------------------
Same three-layer stack as find_cards_workspace.py: PDF points (canonical,
what CalibrateState stores) -> rendered-image pixels (CALIBRATE_RENDER_SCALE)
-> widget/canvas pixels (ViewTransform, zoomable/pannable, unlike Find
Cards' fit-only transform). A click is converted canvas -> image (via
ViewTransform) -> points (divide by render_scale) in one place,
_canvas_click_to_point(), so it can never drift between the two hops.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from deckforge.measure import CARD_SPEC_RE
from deckforge.pdf_renderer import PDFRenderError, PDFRenderer

from .app_state import AppState, WorkflowStep
from .calibrate_state import (
    CalibrateState,
    CalibrationTarget,
    ClickOutcome,
    calibrate_guidance_text,
    calibrate_status_text,
    predicted_neighbor_box,
    suggested_grid,
)
from .find_cards_state import FindCardsState, SharedBackStatus
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
from .view_transform import ViewTransform, clamp, display_scale, is_pan_gesture, pan_active, recompute_view_for_resize, wheel_direction

_MIN_ZOOM_PERCENT = 25
_MAX_ZOOM_PERCENT = 400
_ZOOM_STEP_PERCENT = 10
_WHEEL_ZOOM_STEP = 1.1

_MARKER_RADIUS = 5.0
_GUIDE_COLOR = QColor(ACCENT)
_SUGGESTION_COLOR = QColor(ACCENT)

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

# Filled/accent variant for the one forward-progressing action on the Cards
# step -- moving on to Shared Back once calibration is complete. Every other
# control here (page nav, Finish, Start Over) is secondary/outlined via
# _CONTROL_BUTTON_STYLE, matching the same primary/secondary contrast
# find_cards_workspace.py's "Continue to Calibrate" button establishes.
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

# Accent-tinted banner shown once Cards calibration completes -- makes the
# "this is done, the rest is optional inspection" state visible in the
# workspace itself rather than relying solely on the muted caption below
# the canvas (see DEVELOPER.md "Presenting one shared geometry").
_COMPLETION_BANNER_STYLE = f"""
QLabel {{
    background: #f1effa;
    border: 1px solid {ACCENT};
    border-radius: 8px;
    padding: 10px 14px;
}}
"""


class _CalibrateCanvas(QWidget):
    """The page image, click handling, and all overlay drawing. Scoped to
    this widget alone, same split find_cards_workspace.py uses, so paint/
    mouse logic never interferes with the surrounding control row."""

    clicked_point = Signal(float, float)  # canvas-space (x, y)
    view_changed = Signal()

    def __init__(self, workspace: "CalibrateWorkspace") -> None:
        super().__init__(workspace)
        self._workspace = workspace
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 8px;")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(160, 160)
        self.setMouseTracking(True)

        self._panning = False
        self._pan_last: Optional[tuple[float, float]] = None
        self._pointer_pos: Optional[tuple[float, float]] = None

    # -- painting -----------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            pixmap = self._workspace.current_pixmap()
            view = self._workspace.current_view()
            if pixmap is None or pixmap.isNull() or view is None:
                return

            dest_x, dest_y = view.image_to_canvas(0, 0)
            dest_w, dest_h = pixmap.width() * view.scale, pixmap.height() * view.scale
            painter.drawPixmap(
                QRectF(dest_x, dest_y, dest_w, dest_h), pixmap,
                QRectF(0, 0, pixmap.width(), pixmap.height()),
            )

            self._draw_measurements(painter, view)
            self._draw_pending(painter, view)
            self._draw_suggestions(painter, view)
            self._draw_guides(painter)
        finally:
            painter.end()

    def _draw_measurements(self, painter: QPainter, view: ViewTransform) -> None:
        target = self._workspace.current_target()
        if not target.measurements:
            return
        if target.calibrated_page_num is not None and target.page_num != target.calibrated_page_num:
            return  # a completed measurement only overlays the page it was taken on
        scale = self._workspace.render_scale
        pen = QPen(QColor(ACCENT), 2)
        for m in target.measurements:
            x1, y1 = view.image_to_canvas(m.x1 * scale, m.y1 * scale)
            x2, y2 = view.image_to_canvas(m.x2 * scale, m.y2 * scale)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            self._draw_marker(painter, x1, y1)
            self._draw_marker(painter, x2, y2)

    def _draw_pending(self, painter: QPainter, view: ViewTransform) -> None:
        target = self._workspace.current_target()
        if target.pending_point is None:
            return
        scale = self._workspace.render_scale
        x, y = view.image_to_canvas(target.pending_point[0] * scale, target.pending_point[1] * scale)
        self._draw_marker(painter, x, y)

    def _draw_marker(self, painter: QPainter, cx: float, cy: float) -> None:
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.setBrush(QColor(ACCENT))
        painter.drawEllipse(QPointF(cx, cy), _MARKER_RADIUS, _MARKER_RADIUS)

    def _draw_suggestions(self, painter: QPainter, view: ViewTransform) -> None:
        target = self._workspace.current_target()
        if target.is_complete or len(target.measurements) != 1:
            return
        first = target.measurements[0]
        card_width = first.x2 - first.x1
        card_height = first.y2 - first.y1
        scale = self._workspace.render_scale
        pen = QPen(_SUGGESTION_COLOR, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for direction in ("right", "below"):
            box = predicted_neighbor_box(first.as_tuple(), card_width, card_height, 0.0, 0.0, direction)
            x1, y1 = view.image_to_canvas(box[0] * scale, box[1] * scale)
            x2, y2 = view.image_to_canvas(box[2] * scale, box[3] * scale)
            painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

    def _draw_guides(self, painter: QPainter) -> None:
        app_state = self._workspace.app_state
        if pan_active(app_state.pan_mode, False, self._panning):
            return
        if self._pointer_pos is None:
            return
        x, y = self._pointer_pos
        pen = QPen(_GUIDE_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

    # -- mouse / wheel --------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        button = {
            Qt.MouseButton.LeftButton: "left",
            Qt.MouseButton.MiddleButton: "middle",
            Qt.MouseButton.RightButton: "right",
        }.get(event.button(), "other")
        pos = event.position()

        if is_pan_gesture(button, space_held=False, pan_mode=self._workspace.app_state.pan_mode):
            self._panning = True
            self._pan_last = (pos.x(), pos.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if button == "left":
            self.clicked_point.emit(pos.x(), pos.y())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._pointer_pos = (pos.x(), pos.y())
        if self._panning and self._pan_last is not None:
            last_x, last_y = self._pan_last
            self._workspace.pan_by(pos.x() - last_x, pos.y() - last_y)
            self._pan_last = (pos.x(), pos.y())
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            self._panning = False
            self._pan_last = None
            self._update_cursor()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001 -- Qt event signature
        self._pointer_pos = None
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        direction = wheel_direction(event.angleDelta().y())
        if direction == 0:
            return
        pos = event.position()
        self._workspace.zoom_by_direction(direction, pos.x(), pos.y())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._workspace.canvas_resized(event.oldSize(), event.size())
        self.update()

    def set_pan_active(self, active: bool) -> None:
        self._update_cursor(active)

    def _update_cursor(self, pan_active_hint: Optional[bool] = None) -> None:
        active = self._workspace.app_state.pan_mode if pan_active_hint is None else pan_active_hint
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif active:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)


class CalibrateWorkspace(QWidget):
    """Central Calibrate page for one step (Cards or Shared Back)."""

    calibration_changed = Signal()
    zoom_changed = Signal(int)  # percent
    continue_clicked = Signal()  # Cards only -- see _build_continue_footer
    back_to_select_cards_clicked = Signal()  # Shared Back, UNRESOLVED only

    def __init__(
        self,
        target_step: WorkflowStep,
        app_state: AppState,
        calibrate_state: CalibrateState,
        find_cards_state: FindCardsState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.target_step = target_step
        self.app_state = app_state
        self.calibrate_state = calibrate_state
        self.find_cards_state = find_cards_state
        self.render_scale = calibrate_state.render_scale

        self._renderer: Optional[PDFRenderer] = None
        self._page_count = 0
        self._pixmap: Optional[QPixmap] = None
        self._view: Optional[ViewTransform] = None
        self._fit_mode = True

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._prev_btn = QPushButton("‹ Previous page")
        self._next_btn = QPushButton("Next page ›")
        self._finish_btn = QPushButton("Finish with one card")
        self._start_over_btn = QPushButton("Start Over")
        for button in (self._prev_btn, self._next_btn, self._finish_btn, self._start_over_btn):
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
        controls.addWidget(self._finish_btn)
        controls.addWidget(self._start_over_btn)
        outer.addLayout(controls)

        # Both steps get a forward-progressing Continue action -- Fronts to
        # Shared Back, Shared Back to Review Cards -- and a completion
        # banner; they differ only in label/enable-condition, handled in
        # _update_continue_footer().
        self._is_back_step = target_step is WorkflowStep.CALIBRATE_BACK
        self._completion_banner = QLabel("")
        self._completion_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._completion_banner.setWordWrap(True)
        self._completion_banner.setStyleSheet(_COMPLETION_BANNER_STYLE)
        self._completion_banner.setVisible(False)
        outer.addWidget(self._completion_banner)

        self._canvas = _CalibrateCanvas(self)
        outer.addWidget(self._canvas, 1)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color: {TEXT_CAPTION_MUTED}; font-size: {FONT_CAPTION}px; background: transparent;"
        )
        outer.addWidget(self._status_label)

        footer = QHBoxLayout()
        # Only ever shown for the Shared Back step's UNRESOLVED state -- the
        # explicit route back to Select Card Pages so the user can resolve
        # the Deck's Shared Back decision there, rather than Calibrate
        # guessing or defaulting to "none" on their behalf.
        self._back_to_select_btn = QPushButton("‹ Back to Select Card Pages")
        self._back_to_select_btn.setAutoDefault(False)
        self._back_to_select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_to_select_btn.setStyleSheet(_CONTROL_BUTTON_STYLE)
        self._back_to_select_btn.setVisible(False)
        self._back_to_select_btn.clicked.connect(self.back_to_select_cards_clicked.emit)
        footer.addWidget(self._back_to_select_btn)
        footer.addStretch(1)
        self._continue_btn = QPushButton("")
        self._continue_btn.setAutoDefault(False)
        self._continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_btn.setStyleSheet(_PRIMARY_BUTTON_STYLE)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self.continue_clicked.emit)
        footer.addWidget(self._continue_btn)
        outer.addLayout(footer)

        self._prev_btn.clicked.connect(self._go_previous)
        self._next_btn.clicked.connect(self._go_next)
        self._finish_btn.clicked.connect(self._on_finish_one_card)
        self._start_over_btn.clicked.connect(self._on_start_over)
        self._canvas.clicked_point.connect(self._on_canvas_clicked)

        self._update_controls()

    # -- CalibrateWorkspace <-> _CalibrateCanvas -----------------------

    def current_pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def current_view(self) -> Optional[ViewTransform]:
        return self._view

    def current_target(self) -> CalibrationTarget:
        return self.calibrate_state.target_for(self.target_step)

    # -- page set/navigation --------------------------------------------

    def set_pdf(self, pdf_path: Path, page_count: int) -> None:
        self._close_renderer()
        self._renderer = PDFRenderer(pdf_path)
        self._page_count = page_count

    def on_shown(self) -> None:
        """Called by MainWindow whenever this workspace becomes visible --
        (re)validates the current page against the up-to-date navigable
        page list (Select Card Pages assignments may have changed) and
        (re)loads it."""
        target = self.current_target()
        navigable = self._navigable_pages()
        if not navigable:
            target.page_num = None
            self._pixmap = None
            self._view = None
            self._update_controls()
            self._canvas.update()
            return

        if target.page_num not in navigable:
            if target.calibrated_page_num in navigable:
                target.page_num = target.calibrated_page_num
            else:
                target.page_num = navigable[0]
        self._load_page(target.page_num)

    def _navigable_pages(self) -> list[int]:
        if self.target_step is WorkflowStep.CALIBRATE_BACK:
            back_page = self.find_cards_state.back_page()
            return [back_page] if back_page is not None else []
        return self.find_cards_state.front_pages()

    def _load_page(self, page_num: int) -> None:
        if self._renderer is None:
            return
        page_image: Image.Image = self._renderer.render_page(page_num, self.render_scale)
        self._pixmap = QPixmap.fromImage(ImageQt(page_image))
        self._fit_mode = True
        self._view = self._fitted_view()
        self._update_controls()
        self._canvas.update()
        self.zoom_changed.emit(self._zoom_percent())

    def _fitted_view(self) -> ViewTransform:
        pixmap = self._pixmap
        w, h = max(self._canvas.width(), 1), max(self._canvas.height(), 1)
        if pixmap is None:
            return ViewTransform(1.0, 0.0, 0.0)
        fit_scale = display_scale(pixmap.width(), pixmap.height(), w, h)
        return ViewTransform.fitting(fit_scale, w, h, pixmap.width(), pixmap.height())

    def _go_previous(self) -> None:
        self._step_page(-1)

    def _go_next(self) -> None:
        self._step_page(1)

    def _step_page(self, direction: int) -> None:
        navigable = self._navigable_pages()
        target = self.current_target()
        if target.page_num not in navigable:
            return
        index = navigable.index(target.page_num) + direction
        if 0 <= index < len(navigable):
            self._discard_incomplete_progress(target)
            target.page_num = navigable[index]
            self._load_page(target.page_num)
            self.calibration_changed.emit()

    def _discard_incomplete_progress(self, target: CalibrationTarget) -> None:
        """Leaving the page mid-measurement discards that in-progress
        click/measurement -- a pending corner or an unfinished single
        card only makes sense on the page it was clicked on."""
        if not target.is_complete and (target.pending_point is not None or target.measurements):
            target.reset()

    # -- clicking -----------------------------------------------------

    def _on_canvas_clicked(self, canvas_x: float, canvas_y: float) -> None:
        if self._view is None or self._pixmap is None:
            return
        img_x, img_y = self._view.canvas_to_image(canvas_x, canvas_y)
        if not (0 <= img_x <= self._pixmap.width() and 0 <= img_y <= self._pixmap.height()):
            return  # click landed outside the rendered page

        x_pt, y_pt = img_x / self.render_scale, img_y / self.render_scale
        outcome = self.calibrate_state.record_click(self.target_step, x_pt, y_pt)

        if outcome is ClickOutcome.NEEDS_CELL_LABEL:
            self._prompt_for_cell_label()
        self._after_state_change()

    def _prompt_for_cell_label(self) -> None:
        while True:
            text, ok = QInputDialog.getText(
                self, "Which card is this?",
                "Couldn't tell which grid cell that is from where you clicked.\n"
                "Row/column of this card, e.g. r0c1 (must differ from the first card's row and/or column):",
            )
            if not ok:
                self.calibrate_state.cancel_ambiguous_second_card(self.target_step)
                return
            match = CARD_SPEC_RE.match(text.strip())
            if match:
                row, col = int(match.group(1)), int(match.group(2))
                self.calibrate_state.add_measurement_with_cell(self.target_step, row, col)
                return
            # Invalid label -- loop and ask again, same as the CLI.

    def _on_finish_one_card(self) -> None:
        self.calibrate_state.finish_with_one_card(self.target_step)
        self._after_state_change()

    def _on_start_over(self) -> None:
        self.calibrate_state.start_over(self.target_step)
        self._after_state_change()

    def _after_state_change(self) -> None:
        self._update_controls()
        self._canvas.update()
        self.calibration_changed.emit()

    # -- zoom / pan / fit (driven by CalibrateToolbar) -------------------

    def fit_to_window(self) -> None:
        if self._pixmap is None:
            return
        self._fit_mode = True
        self._view = self._fitted_view()
        self._canvas.update()
        self.zoom_changed.emit(self._zoom_percent())

    def zoom_in(self) -> None:
        self._zoom_by_percent(_ZOOM_STEP_PERCENT)

    def zoom_out(self) -> None:
        self._zoom_by_percent(-_ZOOM_STEP_PERCENT)

    def _zoom_by_percent(self, delta_percent: int) -> None:
        if self._view is None:
            return
        center_x, center_y = self._canvas.width() / 2, self._canvas.height() / 2
        new_percent = clamp(self._zoom_percent() + delta_percent, _MIN_ZOOM_PERCENT, _MAX_ZOOM_PERCENT)
        self._apply_zoom(center_x, center_y, new_percent / 100)

    def zoom_by_direction(self, direction: int, pointer_x: float, pointer_y: float) -> None:
        if self._view is None:
            return
        new_scale = self._view.scale * (_WHEEL_ZOOM_STEP ** direction)
        self._apply_zoom(pointer_x, pointer_y, new_scale)

    def _apply_zoom(self, anchor_x: float, anchor_y: float, new_scale: float) -> None:
        if self._view is None or self._pixmap is None:
            return
        self._fit_mode = False
        min_scale = _MIN_ZOOM_PERCENT / 100
        max_scale = _MAX_ZOOM_PERCENT / 100
        self._view = self._view.zoomed_at(anchor_x, anchor_y, new_scale, min_scale, max_scale).clamped(
            self._canvas.width(), self._canvas.height(), self._pixmap.width(), self._pixmap.height(),
        )
        self._canvas.update()
        self.zoom_changed.emit(self._zoom_percent())

    def pan_by(self, dx: float, dy: float) -> None:
        if self._view is None or self._pixmap is None:
            return
        self._view = self._view.panned_by(dx, dy).clamped(
            self._canvas.width(), self._canvas.height(), self._pixmap.width(), self._pixmap.height(),
        )
        self._canvas.update()

    def canvas_resized(self, old_size, new_size) -> None:  # noqa: ANN001 -- QSize
        if self._view is None or self._pixmap is None:
            return
        self._view = recompute_view_for_resize(
            self._view, self._fit_mode,
            max(old_size.width(), 1), max(old_size.height(), 1),
            max(new_size.width(), 1), max(new_size.height(), 1),
            self._pixmap.width(), self._pixmap.height(),
        )
        self.zoom_changed.emit(self._zoom_percent())

    def _zoom_percent(self) -> int:
        return round(self._view.scale * 100) if self._view is not None else 100

    # -- shared-app-frame hooks ------------------------------------------

    def set_pan_active(self, active: bool) -> None:
        self._canvas.set_pan_active(active)

    def _close_renderer(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def grid_page_size(self) -> Optional[tuple[float, float]]:
        """Point-size of the calibrated Fronts page, for the completion
        text's informational grid-size guess -- None for Shared Back (no
        grid concept applies to a single card) or before a page has been
        calibrated. Used by this workspace's own caption/banner and by
        MainWindow's status-bar text, so the same lookup backs every
        surface that mentions it."""
        if self.target_step is not WorkflowStep.CALIBRATE_CARDS:
            return None
        target = self.current_target()
        if self._renderer is None or target.calibrated_page_num is None:
            return None
        try:
            return self._renderer.page_size(target.calibrated_page_num)
        except PDFRenderError:
            return None

    def _grid_note(self, target: CalibrationTarget) -> str:
        page_size = self.grid_page_size()
        if page_size is None or target.geometry is None:
            return ""
        rows, cols = suggested_grid(target.geometry, *page_size)
        if rows <= 0 or cols <= 0:
            return ""
        return f" Looks like a {rows}×{cols} grid per page."

    def _update_controls(self) -> None:
        navigable = self._navigable_pages()
        target = self.current_target()
        has_page = target.page_num is not None and target.page_num in navigable
        index = navigable.index(target.page_num) if has_page else -1

        self._prev_btn.setEnabled(has_page and index > 0)
        self._next_btn.setEnabled(has_page and 0 <= index < len(navigable) - 1)
        self._finish_btn.setVisible(not target.is_complete and len(target.measurements) == 1)
        self._start_over_btn.setEnabled(
            target.is_complete or target.pending_point is not None or bool(target.measurements)
        )
        self._update_continue_footer(target)

        front_page_count = self.find_cards_state.front_page_count()
        shared_back_status = self.find_cards_state.shared_back_status()

        if not navigable:
            if self._is_back_step and shared_back_status is SharedBackStatus.UNRESOLVED:
                self._page_label.setText("Shared Back not yet decided")
            else:
                self._page_label.setText("No pages available")
            if self._is_back_step:
                _, body = calibrate_guidance_text(self.target_step, target, front_page_count, shared_back_status)
            else:
                body = "Go back to Select Card Pages and mark at least one Front Page."
            self._status_label.setText(body)
            return

        self._page_label.setText(self._page_label_text(target, index, navigable))
        _, body = calibrate_guidance_text(
            self.target_step, target, front_page_count, shared_back_status, self.grid_page_size(),
        )
        self._status_label.setText(body)

    def _update_continue_footer(self, target: CalibrationTarget) -> None:
        front_page_count = self.find_cards_state.front_page_count()
        noun = "page" if front_page_count == 1 else "pages"

        if self._is_back_step:
            self._continue_btn.setText("Continue to Review Cards ›")
            status = self.find_cards_state.shared_back_status()
            self._back_to_select_btn.setVisible(status is SharedBackStatus.UNRESOLVED)

            if status is SharedBackStatus.UNRESOLVED:
                # Calibrate must not make or infer this decision -- no
                # Continue, no "nothing to calibrate" messaging, just a
                # clear route back to where the decision belongs.
                self._continue_btn.setEnabled(False)
                self._completion_banner.setVisible(True)
                self._completion_banner.setText(self._banner_html(
                    "Shared Back hasn't been decided",
                    "Go back to Select Card Pages to choose a Shared Back "
                    "page or confirm this deck has none.",
                    complete=False,
                ))
                return

            if status is SharedBackStatus.CONFIRMED_NONE:
                self._continue_btn.setEnabled(True)
                self._completion_banner.setVisible(True)
                self._completion_banner.setText(self._banner_html(
                    "No Shared Back needed",
                    "This deck has no Shared Back — continue whenever you're ready.",
                ))
                return

            # ASSIGNED
            complete = target.is_complete
            self._continue_btn.setEnabled(complete)
            self._completion_banner.setVisible(complete)
            if complete:
                self._completion_banner.setText(self._banner_html(
                    "Shared Back calibration complete",
                    f"Applied as the shared back for all {front_page_count} front {noun}. "
                    "Continue whenever you're ready.",
                ))
            return

        self._back_to_select_btn.setVisible(False)
        complete = target.is_complete
        self._continue_btn.setText("Continue to Shared Back ›")
        self._continue_btn.setEnabled(complete)
        self._completion_banner.setVisible(complete)
        if complete:
            self._completion_banner.setText(self._banner_html(
                "Fronts calibration complete",
                f"Applies to all {front_page_count} selected front {noun}.{self._grid_note(target)} "
                "Browsing other pages below is optional — continue to Shared Back whenever you're ready.",
            ))

    @staticmethod
    def _banner_html(title: str, body: str, *, complete: bool = True) -> str:
        prefix = "✓ " if complete else ""
        return (
            '<div style="text-align:center;">'
            f'<div style="color:{TEXT_HEADING}; font-weight:700; font-size:{FONT_BODY_SM}px;">'
            f"{prefix}{title}</div>"
            f'<div style="color:{TEXT_CAPTION_MUTED}; font-weight:400; font-size:{FONT_CAPTION}px;'
            ' margin-top:2px;">'
            f"{body}</div>"
            "</div>"
        )

    def _page_label_text(self, target: CalibrationTarget, index: int, navigable: list[int]) -> str:
        """Grounds the reader in the original PDF's page numbers first --
        the ones on their mental model of the document -- with the
        front-page-relative position as a secondary, lighter-weight line,
        rather than replacing PDF numbering with a filtered sequence (see
        DEVELOPER.md "Calibrate milestone")."""
        pdf_line = f"PDF page {target.page_num} of {self._page_count}"
        if self.target_step is not WorkflowStep.CALIBRATE_CARDS:
            return pdf_line
        front_line = f"Front page {index + 1} of {len(navigable)}"
        return (
            '<div style="text-align:center;">'
            f'<div style="color:{TEXT_HEADING}; font-weight:600; font-size:{FONT_BODY_SM}px;">{pdf_line}</div>'
            f'<div style="color:{TEXT_CAPTION_MUTED}; font-weight:400; font-size:{FONT_CAPTION}px;">{front_line}</div>'
            "</div>"
        )
