"""Right-hand guidance panel -- contextual, short, collapsible."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_state import AppState, CALIBRATE_STEPS, WorkflowStep
from .calibrate_state import CalibrateState, calibrate_guidance_text
from .export_state import export_guidance_text
from .find_cards_state import FindCardsState
from .review_state import ReviewCardsState, review_guidance_text
from .theme import (
    ACCENT,
    BG_GUIDANCE,
    FONT_BODY_SM,
    FONT_H2,
    TEXT_NAV,
    TEXT_NAV_MUTED,
)

COLLAPSED_WIDTH = 30
EXPANDED_WIDTH = 280

# Selector-scoped, not a bare "color: ..." declaration -- see DEVELOPER.md's
# tooltip-rendering note: a bare declaration set directly on a widget leaks
# that property into the widget's own QToolTip too, not just descendants'.
# TEXT_NAV is correct for this button's own text against BG_GUIDANCE, but
# leaking it into the tooltip (rendered on a white BG_CARD background, via
# gui_app.py's _apply_tooltip_theme()) produced washed-out, low-contrast
# tooltip text -- the button's own appearance is unchanged by this fix.
_GLYPH_BUTTON_STYLE = f"QToolButton {{ color: {TEXT_NAV}; font-size: 14px; font-weight: 700; }}"


class GuidancePanel(QWidget):
    """Collapses to a thin strip with an expand button rather than disappearing."""

    collapse_toggled = Signal(bool)

    def __init__(
        self,
        state: AppState,
        calibrate_state: CalibrateState,
        find_cards_state: FindCardsState,
        review_cards_state: ReviewCardsState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.calibrate_state = calibrate_state
        self.find_cards_state = find_cards_state
        self.review_cards_state = review_cards_state
        self.setObjectName("guidancePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#guidancePanel {{ background: {BG_GUIDANCE}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("guidanceStack")
        # ID-scoped, not a bare "background: ..." declaration -- see
        # DEVELOPER.md's tooltip-rendering note: an unscoped setStyleSheet()
        # here leaked BG_GUIDANCE into the collapse/expand buttons' own
        # QToolTip, overriding gui_app.py's app-level tooltip theme.
        self._stack.setStyleSheet(f"#guidanceStack {{ background: {BG_GUIDANCE}; }}")
        outer.addWidget(self._stack)

        self._full_page = self._build_full_page()
        self._strip = self._build_strip()
        self._stack.addWidget(self._full_page)
        self._stack.addWidget(self._strip)

        self.set_collapsed(False)

    def _build_full_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(7)

        # A small accent-colored marker -- ties this label to the same purple
        # used elsewhere for "current progress" (active nav step, primary
        # actions) rather than recoloring the text itself, which at this size
        # wouldn't clear body-text contrast against BG_GUIDANCE.
        marker = QFrame()
        marker.setObjectName("guidanceMarker")
        marker.setFixedSize(7, 7)
        marker.setStyleSheet(f"#guidanceMarker {{ background: {ACCENT}; border-radius: 3px; }}")
        header_row.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("Guidance")
        title.setStyleSheet(
            f"font-size: {FONT_BODY_SM}px; font-weight: 700; letter-spacing: 1px;"
            f" color: {TEXT_NAV};"
        )
        header_row.addWidget(title)
        header_row.addStretch(1)

        collapse_btn = QToolButton()
        collapse_btn.setText("»")
        collapse_btn.setToolTip("Hide guidance panel")
        collapse_btn.setAutoRaise(True)
        collapse_btn.setStyleSheet(_GLYPH_BUTTON_STYLE)
        collapse_btn.clicked.connect(lambda: self.collapse_toggled.emit(True))
        header_row.addWidget(collapse_btn)
        layout.addLayout(header_row)

        self._headline = QLabel()
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet(
            f"font-size: {FONT_H2}px; font-weight: 700; color: {TEXT_NAV};"
        )
        layout.addWidget(self._headline)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setStyleSheet(f"font-size: {FONT_BODY_SM}px; color: {TEXT_NAV_MUTED};")
        layout.addWidget(self._body)

        layout.addStretch(1)
        return page

    def _build_strip(self) -> QWidget:
        strip = QWidget()
        layout = QVBoxLayout(strip)
        layout.setContentsMargins(4, 10, 4, 10)

        expand_btn = QToolButton()
        expand_btn.setText("«")
        expand_btn.setToolTip("Show guidance panel")
        expand_btn.setAutoRaise(True)
        expand_btn.setStyleSheet(_GLYPH_BUTTON_STYLE)
        expand_btn.clicked.connect(lambda: self.collapse_toggled.emit(False))
        layout.addWidget(expand_btn)
        layout.addStretch(1)
        return strip

    def set_collapsed(self, collapsed: bool) -> None:
        self._stack.setCurrentWidget(self._strip if collapsed else self._full_page)
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)

    def refresh(self) -> None:
        headline, body = self._guidance_text()
        self._headline.setText(headline)
        self._body.setText(body)

    def _guidance_text(self) -> tuple[str, str]:
        step = self.state.current_step
        if step in CALIBRATE_STEPS:
            return calibrate_guidance_text(
                step,
                self.calibrate_state.target_for(step),
                self.find_cards_state.front_page_count(),
                self.find_cards_state.shared_back_status(),
            )
        if step is WorkflowStep.REVIEW_CARDS:
            return review_guidance_text(
                self.calibrate_state.cards,
                self.calibrate_state.back,
                self.find_cards_state.shared_back_status(),
                self.review_cards_state,
            )
        if step is WorkflowStep.EXPORT:
            # Deliberately the simple export_ready() check (no page-size-
            # dependent stale-snapshot check) -- see export_workspace.py's
            # module docstring for why that check is workspace-only.
            return export_guidance_text(
                self.calibrate_state.cards,
                self.calibrate_state.back,
                self.find_cards_state.shared_back_status(),
                self.review_cards_state,
            )
        return self.state.guidance_text()
