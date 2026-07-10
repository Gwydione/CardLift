"""Shared color palette for the PySide6 shell.

Centralizes the DeckForge visual language -- dark navigation chrome, a
light PDF workspace, and a purple accent -- so individual widgets don't
each hardcode their own hex values. See docs/ui/DESIGN_PRINCIPLES.md and
docs/ui/UI_DECISIONS.md for the intent behind these choices; this module
is just the first-pass numbers.
"""

from __future__ import annotations

# Dark navigation chrome: top bar, sidebar, guidance panel.
BG_TOPBAR = "#16132a"
BG_SIDEBAR = "#1d1934"
BG_GUIDANCE = "#1d1934"
TEXT_NAV = "#e7e5f2"
# Lightened from the original #8b85a8/#6f6a8c -- those sat close to the
# 4.5:1 contrast floor against BG_SIDEBAR at sidebar text sizes, which read
# as barely legible rather than intentionally muted.
TEXT_NAV_MUTED = "#a6a0c4"
TEXT_NAV_HEADER = "#8f89ad"

# Purple accent used for the active nav item, primary buttons, and icons.
ACCENT = "#6f4fe8"
ACCENT_HOVER = "#7f61ec"
ACCENT_PRESSED = "#5d3fd1"

# Light PDF workspace -- the PDF is the workspace, so this is most of the
# window most of the time.
BG_WORKSPACE = "#f7f6fb"
BG_CARD = "#ffffff"
BORDER_CARD = "#e3e0f0"
TEXT_HEADING = "#211d33"
TEXT_BODY = "#6b6580"

ERROR_TEXT = "#b3261e"

# Type scale (px). Reused across workspaces/sidebar/guidance so the app
# reads as one hierarchy instead of each widget picking its own sizes.
FONT_H1 = 28  # workspace headline, e.g. "Turn a Print-and-Play PDF..."
FONT_H2 = 18  # guidance headline, secondary headings
FONT_BODY = 14  # standard body copy
FONT_BODY_SM = 13  # secondary copy, nav labels
FONT_CAPTION = 11  # section labels, hints

# Spacing scale (px). Used for layout margins/spacing so padding stays
# consistent instead of ad hoc per widget.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 20
SPACE_XL = 32


def clamp(value: float, low: float, high: float) -> float:
    """Restrict value to [low, high]."""
    return max(low, min(high, value))


def lerp(low: float, high: float, t: float) -> float:
    """Linear interpolation between low and high at t in [0, 1]."""
    return low + (high - low) * t


def responsive_t(width: int, compact_width: int, spacious_width: int) -> float:
    """0.0 at compact_width or narrower, 1.0 at spacious_width or wider,
    linear in between. Shared by any workspace that scales its layout
    (drop zone size, type scale, margins, ...) with available width
    instead of committing to a fixed pixel size."""
    if spacious_width <= compact_width:
        return 1.0
    return clamp((width - compact_width) / (spacious_width - compact_width), 0.0, 1.0)
