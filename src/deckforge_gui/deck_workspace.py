"""Deck workspace: the first-run drop target for a print-and-play PDF.

This widget only captures a candidate file -- by drag-and-drop or by
browsing -- and reports it up via pdf_chosen. It never decides whether a
file is a usable PDF; that's DeckSession.load_pdf's job (session.py).
MainWindow owns the session and calls show_error() back if the file was
rejected.

Responsive sizing: the drop zone, margins, and type scale all grow with
available width (see _apply_responsive_metrics), between the _COMPACT_WIDTH
and _SPACIOUS_WIDTH breakpoints, so the page reads as a real workspace on a
large monitor instead of a small fixed-size dialog stranded in empty space,
while staying unchanged at the moderate sizes it already looked right at.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    BG_WORKSPACE,
    ERROR_TEXT,
    FONT_BODY,
    FONT_BODY_SM,
    FONT_CAPTION,
    FONT_H1,
    TEXT_BODY,
    TEXT_CAPTION_MUTED,
    TEXT_HEADING,
    lerp,
    responsive_t,
)

_DEFAULT_DROP_TEXT = "Drop a PDF here"
_REPLACE_DROP_TEXT = "Drop a new PDF to replace it"
_DEFAULT_BUTTON_TEXT = "Choose PDF"
_CHANGE_BUTTON_TEXT = "Change PDF"

_DROPZONE_STYLE = f"""
QFrame#dropZone {{
    background: #f1effa;
    border: 2px dashed #c9c2e8;
    border-radius: 12px;
}}
QFrame#dropZone:hover, QFrame#dropZone[dragOver="true"] {{
    background: #e9e4fb;
    border: 2px dashed {ACCENT};
}}
"""

# Width, in workspace pixels, at/below which sizing sits at its minimum
# (unchanged from the previous fixed layout) and at/above which it sits at
# its maximum. Between the two, every metric below scales linearly with
# the workspace's actual width via responsive_t()/lerp() -- there's no
# hard breakpoint jump, so resizing the window feels continuous.
_COMPACT_WIDTH = 560
_SPACIOUS_WIDTH = 1500

# (minimum, maximum) for each metric that scales with width. Minimums match
# the previous fixed-size implementation so nothing changes at moderate
# window sizes -- only the maximums are new.
_DROPZONE_WIDTH = (480, 760)
_MARGIN = (32, 72)
_SPACING = (18, 28)
_HEADING_FONT = (FONT_H1, FONT_H1 + 10)
_SUBHEADING_FONT = (FONT_BODY, FONT_BODY + 3)
_SUBHEADING_MAX_WIDTH = (480, 640)
_DROP_TEXT_FONT = (FONT_BODY + 1, FONT_BODY + 5)
_SECONDARY_FONT = (FONT_BODY_SM, FONT_BODY_SM + 2)
_CAPTION_FONT = (FONT_CAPTION, FONT_CAPTION + 1)
_ICON_SIZE = (56, 72)
_BUTTON_FONT = (FONT_BODY_SM, FONT_BODY_SM + 2)
_REASSURANCE_MAX_WIDTH = (420, 560)


def _choose_button_style(button_font: int, padding: int) -> str:
    return f"""
QPushButton#choosePdfButton {{
    background: {ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: {padding}px {padding * 2}px;
    font-size: {button_font}px;
    font-weight: 600;
}}
QPushButton#choosePdfButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#choosePdfButton:pressed {{ background: {ACCENT_PRESSED}; }}
"""


class _DropZone(QFrame):
    """The dashed drop target. Clicking anywhere on it (except a child
    widget that handles its own click, like the button) also browses."""

    file_dropped = Signal(Path)
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setStyleSheet(_DROPZONE_STYLE)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("dragOver", False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_over(True)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        # Qt does not carry acceptance forward from dragEnterEvent: each
        # QDragMoveEvent defaults to unaccepted and must call
        # acceptProposedAction() itself, or Qt shows a "not allowed" cursor
        # and dropEvent never fires. This is general Qt drag-and-drop
        # behavior, not platform-specific.
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001 -- Qt event signature
        self._set_drag_over(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        urls = event.mimeData().urls()
        if urls:
            event.acceptProposedAction()
            self.file_dropped.emit(Path(urls[0].toLocalFile()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _set_drag_over(self, active: bool) -> None:
        self.setProperty("dragOver", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def catch_drops_from(self, child: QWidget) -> None:
        """The icon/text/button children visually cover almost the whole
        drop zone, and Qt targets drag events at the exact child widget
        under the cursor -- unlike mouse events, an ignored drag event does
        NOT bubble up to the parent. Without this, dropping anywhere but
        the frame's bare edge would silently do nothing."""
        child.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.DragEnter:
            self.dragEnterEvent(event)
            return True
        if event_type == QEvent.Type.DragMove:
            self.dragMoveEvent(event)
            return True
        if event_type == QEvent.Type.DragLeave:
            self.dragLeaveEvent(event)
            return True
        if event_type == QEvent.Type.Drop:
            self.dropEvent(event)
            return True
        return super().eventFilter(watched, event)


class DeckWorkspace(QWidget):
    """Central Deck page: drop or browse for a PDF to start a new deck."""

    pdf_chosen = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {BG_WORKSPACE};")

        self._outer = QVBoxLayout(self)
        self._outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._heading = QLabel("Turn a Print-and-Play PDF\ninto individual cards.")
        self._heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._outer.addWidget(self._heading)

        self._subheading = QLabel(
            "DeckForge finds, crops, and prepares your cards so you can print with confidence."
        )
        self._subheading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subheading.setWordWrap(True)
        self._outer.addWidget(self._subheading)

        self._loaded_label = QLabel("")
        self._loaded_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loaded_label.setStyleSheet(f"font-weight: 600; color: {ACCENT}; background: transparent;")
        self._loaded_label.hide()
        self._outer.addWidget(self._loaded_label)

        self._dropzone = _DropZone()
        self._dropzone.file_dropped.connect(self._on_candidate_path)
        self._dropzone.clicked.connect(self._browse)
        self._outer.addWidget(self._dropzone, 0, Qt.AlignmentFlag.AlignCenter)

        self._zone_layout = QVBoxLayout(self._dropzone)
        self._zone_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel("PDF")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(
            f"background: {ACCENT}; color: white; border-radius: 12px;"
            " font-size: 12px; font-weight: 700;"
        )
        self._zone_layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignCenter)

        self._drop_text = QLabel(_DEFAULT_DROP_TEXT)
        self._drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_text.setStyleSheet(f"font-weight: 600; color: {TEXT_HEADING}; background: transparent;")
        self._zone_layout.addWidget(self._drop_text)

        self._browse_text = QLabel("or click anywhere to browse")
        self._browse_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._browse_text.setStyleSheet(f"color: {TEXT_BODY}; background: transparent;")
        self._zone_layout.addWidget(self._browse_text)

        self._or_text = QLabel("or")
        self._or_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._or_text.setStyleSheet(f"color: {TEXT_CAPTION_MUTED}; background: transparent;")
        self._zone_layout.addWidget(self._or_text)

        self._choose_btn = QPushButton(_DEFAULT_BUTTON_TEXT)
        self._choose_btn.setObjectName("choosePdfButton")
        self._choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._choose_btn.setAutoDefault(False)
        self._choose_btn.clicked.connect(self._browse)
        self._zone_layout.addWidget(self._choose_btn, 0, Qt.AlignmentFlag.AlignCenter)

        for zone_child in (self._icon, self._drop_text, self._browse_text, self._or_text, self._choose_btn):
            self._dropzone.catch_drops_from(zone_child)

        self._reassurance = QLabel("\U0001F512 Your original PDF will not be modified.")
        self._reassurance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reassurance.setStyleSheet(f"color: {TEXT_CAPTION_MUTED}; background: transparent;")
        self._outer.addWidget(self._reassurance)

        self._error_label = QLabel("")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(f"color: {ERROR_TEXT}; font-weight: 600; background: transparent;")
        self._error_label.hide()
        self._outer.addWidget(self._error_label)

        self._apply_responsive_metrics(self.width())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_metrics(event.size().width())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_responsive_metrics(self.width())

    def _apply_responsive_metrics(self, width: int) -> None:
        t = responsive_t(width, _COMPACT_WIDTH, _SPACIOUS_WIDTH)

        def scale(bounds: tuple[float, float]) -> int:
            return round(lerp(bounds[0], bounds[1], t))

        margin = scale(_MARGIN)
        self._outer.setContentsMargins(margin, margin, margin, margin)
        self._outer.setSpacing(scale(_SPACING))

        heading_font = scale(_HEADING_FONT)
        self._heading.setStyleSheet(
            f"font-size: {heading_font}px; font-weight: 700; color: {TEXT_HEADING};"
            " background: transparent;"
        )

        subheading_font = scale(_SUBHEADING_FONT)
        self._subheading.setMaximumWidth(scale(_SUBHEADING_MAX_WIDTH))
        self._subheading.setStyleSheet(
            f"font-size: {subheading_font}px; color: {TEXT_BODY}; background: transparent;"
        )

        secondary_font = scale(_SECONDARY_FONT)
        self._loaded_label.setStyleSheet(
            f"font-size: {secondary_font}px; font-weight: 600; color: {ACCENT};"
            " background: transparent;"
        )

        dropzone_width = scale(_DROPZONE_WIDTH)
        dropzone_height = round(dropzone_width * 9 / 16)
        self._dropzone.setFixedSize(dropzone_width, dropzone_height)
        zone_margin = round(lerp(24, 32, t))
        self._zone_layout.setContentsMargins(zone_margin, zone_margin, zone_margin, zone_margin)
        self._zone_layout.setSpacing(scale((8, 12)))

        icon_size = scale(_ICON_SIZE)
        self._icon.setFixedSize(icon_size, icon_size)

        drop_text_font = scale(_DROP_TEXT_FONT)
        self._drop_text.setStyleSheet(
            f"font-size: {drop_text_font}px; font-weight: 600; color: {TEXT_HEADING};"
            " background: transparent;"
        )
        self._browse_text.setStyleSheet(
            f"font-size: {secondary_font}px; color: {TEXT_BODY}; background: transparent;"
        )
        caption_font = scale(_CAPTION_FONT)
        self._or_text.setStyleSheet(
            f"font-size: {caption_font}px; color: {TEXT_CAPTION_MUTED}; background: transparent;"
        )

        button_font = scale(_BUTTON_FONT)
        button_padding = round(lerp(11, 14, t))
        self._choose_btn.setStyleSheet(_choose_button_style(button_font, button_padding))

        self._reassurance.setStyleSheet(
            f"font-size: {caption_font}px; color: {TEXT_CAPTION_MUTED}; background: transparent;"
        )

        self._error_label.setMaximumWidth(scale(_REASSURANCE_MAX_WIDTH))
        self._error_label.setStyleSheet(
            f"font-size: {secondary_font}px; color: {ERROR_TEXT}; font-weight: 600;"
            " background: transparent;"
        )

    def _browse(self) -> None:
        self._clear_error()
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Choose a PDF", str(Path.home()), "PDF Files (*.pdf)"
        )
        if path_str:
            self.pdf_chosen.emit(Path(path_str))

    def _on_candidate_path(self, path: Path) -> None:
        self._clear_error()
        self.pdf_chosen.emit(path)

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _clear_error(self) -> None:
        self._error_label.hide()

    def set_loaded(self, filename: str, page_count: int) -> None:
        """Reflect whether a PDF is already loaded -- the drop zone and its
        button double as the "Change PDF" affordance; picking another file
        replaces the current one (DeckSession.load_pdf already does this)."""
        if filename:
            self._loaded_label.setText(f"✓ Loaded: {filename}  •  {page_count} pages")
            self._loaded_label.show()
            self._drop_text.setText(_REPLACE_DROP_TEXT)
            self._choose_btn.setText(_CHANGE_BUTTON_TEXT)
        else:
            self._loaded_label.hide()
            self._drop_text.setText(_DEFAULT_DROP_TEXT)
            self._choose_btn.setText(_DEFAULT_BUTTON_TEXT)

    def set_pan_active(self, active: bool) -> None:
        """No-op: the Deck page has no page canvas to pan."""
