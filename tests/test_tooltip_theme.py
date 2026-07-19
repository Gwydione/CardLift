"""Regression coverage for CardLift v0.1.1-alpha's tooltip-rendering fix.

Root cause (see docs/RELEASE_READINESS.md and DEVELOPER.md's tooltip-
rendering note): a bare, selector-less `widget.setStyleSheet("background:
...")` call leaks that property into the QToolTip of any descendant
widget -- or, it turns out, of the very widget it's set on -- silently
overriding the app-level QToolTip theme gui_app.py's
_apply_tooltip_theme() sets. Two distinct manifestations were found:

1. An ancestor's bare "background: ..." leaks into a descendant's tooltip
   background: a solid ancestor color leaks a wrong-but-opaque tooltip
   (guidance panel, before the first round of this fix); "background:
   transparent" (the Review Cards card-grid's scroll content, to let the
   workspace's own background show through) leaks a fully transparent
   tooltip interior with translucent text -- the original Alpha-reported
   defect on the Review Cards card tile.
2. A bare "color: ..." set directly ON the tooltip-owning widget itself
   leaks into that widget's OWN tooltip text color: the guidance panel's
   collapse/expand buttons use TEXT_NAV (a light lavender meant for text
   on the dark BG_GUIDANCE background) for their own on-panel glyph, and
   that same bare declaration leaked into their tooltip text once the
   background leak above was fixed -- light text on the now-correctly-
   white tooltip background read as washed out and hard to read.

Scoping each declaration to a selector (its own class name, a type
selector, or an objectName + `#id {...}` rule) stops the leak in both
directions without changing that widget's own appearance -- confirmed
empirically before either fix was written, not assumed.

The tests below are a real reproduction of the actual failure mode, not a
synthetic QPalette poke on a bare QPushButton (which is what the
regression test deleted in commit c1c4153 did, and why it didn't survive
contact with real Windows Sandbox testing -- it never rendered a tooltip
nested inside the app's real container hierarchy)."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import gui_app
from deckforge_gui.calibrate_state import CalibratedGeometry, CalibrateState
from deckforge_gui.find_cards_state import FindCardsState, PageRole
from deckforge_gui.guidance_panel import GuidancePanel
from deckforge_gui.review_state import ReviewCardsState
from deckforge_gui.review_workspace import ReviewWorkspace
from deckforge_gui.theme import BG_CARD, TEXT_NAV

SAMPLE_PDF = REPO_ROOT / "sample_decks" / "CardLift_Demo_Deck.pdf"
FRONT_GEOMETRY = CalibratedGeometry(
    left=27.0, top=139.5, card_width=180.0, card_height=252.0,
    gap_x=9.0, gap_y=9.0, gap_x_derived=False, gap_y_derived=False,
)
FRONT_PAGE = 2

_SETSTYLESHEET_CALL = re.compile(r"\.setStyleSheet\(([^)]*)\)", re.DOTALL)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    gui_app._apply_tooltip_theme(app)
    return app


def _tooltip_alpha_and_corner(app: QApplication, widget: QWidget):
    """Shows a real QToolTip for `widget` (the same internal Qt path a
    hover triggers) and returns (is_fully_opaque, corner_color_name,
    distinct_colors) -- the last so callers can assert a specific wrong
    color (e.g. a leaked TEXT_NAV) is absent, not just that *some* color
    matches the expected background."""
    QToolTip.showText(widget.mapToGlobal(QPoint(0, 0)), widget.toolTip(), widget)
    for _ in range(20):
        app.processEvents()
    tip = next((w for w in app.allWidgets() if w.objectName() == "qtooltip_label"), None)
    assert tip is not None, "no QToolTip widget was created"
    tip.resize(max(tip.width(), 1), max(tip.height(), 1))
    for _ in range(10):
        app.processEvents()
    img = tip.grab().toImage()
    fully_opaque = all(
        img.pixelColor(x, y).alpha() == 255
        for x in range(img.width())
        for y in range(img.height())
    )
    corner = img.pixelColor(2, 2)
    distinct_colors = {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())}
    QToolTip.hideText()
    for _ in range(5):
        app.processEvents()
    return fully_opaque, corner.name(), distinct_colors


class TestNoBareStyleSheetDeclarations:
    """Static guard against reintroducing the leak: any bare (selector-
    less) setStyleSheet(...) call -- one whose argument is a flat
    "property: value;" list with no selector block at all -- is the exact
    anti-pattern that caused this defect (for whichever property it sets:
    "background:" leaks into descendants' tooltips, "color:" set directly
    on a tooltip-owning widget leaks into that widget's own tooltip text),
    regardless of whether a tooltip currently sits on or underneath it.

    Two separate checks, because a call site can pass either an inline
    literal or a reference to a named module-level constant:
    - inline literals are checked against their own source text directly;
    - named constants (every one in this codebase is named `_..._STYLE`
      by convention) are checked against their actual resolved runtime
      value, not source text -- source-level checks can't reliably tell
      an escaped `{{` selector brace apart from an f-string `{COLOR}`
      interpolation without a real parser, but the *rendered* string
      unambiguously contains a literal `{` only in the scoped case (theme
      hex colors never contain braces themselves)."""

    def test_no_bare_inline_stylesheet_calls(self) -> None:
        offenders = []
        for path in sorted((REPO_ROOT / "src" / "deckforge_gui").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for match in _SETSTYLESHEET_CALL.finditer(text):
                arg = match.group(1).strip()
                # Only literal string arguments -- a bare NAME reference
                # (e.g. `_GLYPH_BUTTON_STYLE`) is checked by the runtime
                # test below instead, since its source text alone (just
                # an identifier) can't tell us anything.
                if not (arg.startswith('"') or arg.startswith("f\"") or arg.startswith("'") or arg.startswith("f'")):
                    continue
                if "{" not in arg:
                    lineno = text[: match.start()].count("\n") + 1
                    offenders.append(f"{path.name}:{lineno}: {arg[:80]}")
        assert not offenders, (
            "Found unscoped inline setStyleSheet(...) call(s) with no selector:\n"
            + "\n".join(offenders)
        )

    def test_no_bare_named_stylesheet_constants(self) -> None:
        import importlib

        offenders = []
        for path in sorted((REPO_ROOT / "src" / "deckforge_gui").glob("*.py")):
            module = importlib.import_module(f"deckforge_gui.{path.stem}")
            for name in dir(module):
                if not name.endswith("_STYLE"):
                    continue
                value = getattr(module, name)
                if isinstance(value, str) and ":" in value and ";" in value and "{" not in value:
                    offenders.append(f"{path.name}: {name} = {value[:80]!r}")
        assert not offenders, (
            "Found unscoped stylesheet constant(s) -- their rendered value has no "
            "selector at all ('{' never appears once f-string interpolations are "
            "resolved, since theme hex colors don't contain braces):\n"
            + "\n".join(offenders)
        )


class TestReviewCardTileTooltip:
    """The historically-reported location (docs/RELEASE_READINESS.md):
    the Review Cards card-tile tooltip rendered with a transparent
    background and translucent text because its ancestor chain
    (ReviewWorkspace -> _scroll_area -> _content) included a bare
    'background: transparent' declaration on _content."""

    @pytest.fixture()
    def workspace(self, qapp: QApplication) -> ReviewWorkspace:
        ws = ReviewWorkspace(CalibrateState(), FindCardsState(), ReviewCardsState())
        ws.find_cards_state.set_role(FRONT_PAGE, PageRole.FRONT)
        ws.find_cards_state.confirm_no_shared_back()
        ws.calibrate_state.cards.geometry = FRONT_GEOMETRY
        ws.calibrate_state.cards.calibrated_page_num = FRONT_PAGE
        ws.set_pdf(SAMPLE_PDF, 12)
        ws.on_shown()
        return ws

    def test_card_tile_tooltip_is_fully_opaque(self, qapp: QApplication, workspace: ReviewWorkspace) -> None:
        tile = next(iter(workspace._tiles.values()))
        assert tile.toolTip(), "fixture didn't produce a populated card tile"
        fully_opaque, corner, _colors = _tooltip_alpha_and_corner(qapp, tile)
        assert fully_opaque, "card tile tooltip has transparent/translucent pixels"
        assert corner == BG_CARD.lower()


class TestGuidancePanelTooltip:
    """The guidance panel's collapse/expand tooltips originally rendered
    with the panel's own dark navy background (BG_GUIDANCE) instead of the
    intended white tooltip card style, because their ancestor _stack had a
    bare 'background: ...' declaration. After that was fixed, the tooltip
    text itself still leaked TEXT_NAV (the buttons' own bare 'color: ...'
    declaration, correct for their on-panel glyph against BG_GUIDANCE, but
    washed-out/illegible against the now-correct white tooltip
    background) -- both are checked here."""

    @pytest.fixture()
    def panel(self, qapp: QApplication) -> GuidancePanel:
        from deckforge_gui.app_state import AppState

        return GuidancePanel(AppState(), CalibrateState(), FindCardsState(), ReviewCardsState())

    def test_collapse_button_tooltip_matches_card_theme(self, qapp: QApplication, panel: GuidancePanel) -> None:
        collapse_btn = next(w for w in panel.findChildren(QWidget) if w.toolTip() == "Hide guidance panel")
        fully_opaque, corner, colors = _tooltip_alpha_and_corner(qapp, collapse_btn)
        assert fully_opaque
        assert corner == BG_CARD.lower()
        assert TEXT_NAV.lower() not in colors, "washed-out TEXT_NAV leaked into tooltip text"

    def test_expand_button_tooltip_matches_card_theme(self, qapp: QApplication, panel: GuidancePanel) -> None:
        expand_btn = next(w for w in panel.findChildren(QWidget) if w.toolTip() == "Show guidance panel")
        fully_opaque, corner, colors = _tooltip_alpha_and_corner(qapp, expand_btn)
        assert fully_opaque
        assert corner == BG_CARD.lower()
        assert TEXT_NAV.lower() not in colors, "washed-out TEXT_NAV leaked into tooltip text"
