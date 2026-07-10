"""
calibrate_ui.py - lightweight interactive calibration window (--calibrate).

Replaces the "generate overlay -> open it in another app -> read pixel
coordinates -> type them into --measure" loop with a small Tkinter window:
click a card's upper-left corner, click its lower-right corner, read the
suggested profile values off the screen.

This module owns NO measurement math. It only turns mouse clicks into the
same PixelBox/CardMeasurement inputs --measure already accepts, and hands
them straight to measure.derive_geometry() / measure.format_suggested_patch()
-- the exact inverse-geometry code --measure uses. That keeps the
pixel<->point arithmetic in one place (unit tested in test_measure.py) and
means this window can never drift from CLI behavior.

Tkinter is part of the Python standard library, so this adds no new
dependency. It is imported lazily by cli.py so headless environments
(CI, etc.) never pay for it unless --calibrate is actually used.

Like --measure, this NEVER writes to the profile JSON. It only displays a
suggested patch (and optionally copies it to the clipboard) for the user
to paste in by hand.

ZOOM/PAN AND COORDINATE SPACES
-------------------------------
Two coordinate spaces are in play: "image space" (pixels of the full-
resolution rendered page, `page_image`) and "canvas space" (pixels on
screen, inside the viewport -- the canvas widget, which resizes with the
window). Every calibration measurement is stored in image space and never
changes when the view is zoomed, panned, or the viewport is resized
-- `ViewTransform` is the only thing that knows how to convert between the
two, and every mouse event is converted through it exactly once, on the way
in. This is what keeps clicking the same two corners at any zoom level
producing the same suggested profile values.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, simpledialog
from typing import Optional, Sequence

from PIL import Image, ImageTk

from .measure import (
    BACK_FIELDS,
    CARD_SPEC_RE,
    FRONT_FIELDS,
    CardMeasurement,
    MeasureError,
    PixelBox,
    derive_geometry,
    format_suggested_patch,
)
from .profile import DeckProfile

# Used only as initial-window-size guidance (see CalibrationWindow.__init__)
# -- the live viewport is whatever size the canvas widget actually is, and
# grows/shrinks as the window is resized or maximized.
MAX_DISPLAY_WIDTH = 1300
MAX_DISPLAY_HEIGHT = 820

# Canvas <Configure> events fire with degenerate (e.g. 1x1) sizes while
# Tkinter is still laying out the window; ignore anything smaller than this
# rather than computing a view against a meaningless viewport.
MIN_VIEWPORT_DIM = 10

# How long to wait after the last <Configure> event before recomputing the
# view and re-rendering, so dragging a window border doesn't re-crop/resize
# the source image on every intermediate pixel.
RESIZE_DEBOUNCE_MS = 80

# Zoom is expressed as canvas-pixels-per-image-pixel. 100% = the rendered
# page's native resolution (1 image pixel = 1 canvas pixel). MIN_ZOOM_FLOOR
# is a lower bound on top of which "Fit to Window" is still always
# reachable (see CalibrationWindow.min_zoom); MAX_ZOOM is fixed at 800% of
# native resolution, plenty for pixel-precise corner placement.
MIN_ZOOM_FLOOR = 0.1
MAX_ZOOM = 8.0
ZOOM_STEP = 1.1


# -- pure helpers (no Tkinter, no I/O -- unit testable) ----------------------


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def display_scale(image_width: int, image_height: int, max_width: int, max_height: int) -> float:
    """Scale factor to fit an image within (max_width, max_height) without
    upscaling. 1.0 if the image already fits."""
    return min(1.0, max_width / image_width, max_height / image_height)


def normalize_box(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
    """Orders two arbitrary corner points into (x1,y1,x2,y2) with x2>x1,
    y2>y1, so a click sequence that isn't perfectly upper-left-then-lower-
    right still produces a valid PixelBox."""
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def parse_cell_label(label: str) -> tuple[int, int]:
    """Parses a 'rNcN' cell label (same syntax as --card's cell part)."""
    match = CARD_SPEC_RE.match(label.strip())
    if not match:
        raise MeasureError(f"'{label}' is not in 'rNcN' form, e.g. 'r0c1'")
    return int(match.group(1)), int(match.group(2))


def predicted_neighbor_box(
    first_box: PixelBox, card_width: float, card_height: float,
    gap_x: float, gap_y: float, direction: str,
) -> PixelBox:
    """Guesses where a horizontally- or vertically-adjacent card would be,
    in the same pixel space as `first_box`, using the just-measured card
    size and the profile's current (possibly-default) gap. This is only
    ever used to draw a "click here" hint -- if the guess is wrong the
    user simply won't click there, and can measure any other card
    instead."""
    if direction == "right":
        x1 = first_box.x2 + gap_x
        return PixelBox(x1, first_box.y1, x1 + card_width, first_box.y2)
    if direction == "below":
        y1 = first_box.y2 + gap_y
        return PixelBox(first_box.x1, y1, first_box.x2, y1 + card_height)
    raise ValueError(f"direction must be 'right' or 'below', got {direction!r}")


def infer_second_cell(
    first_row: int, first_col: int, first_box: PixelBox, second_box: PixelBox,
    cell_width: float, cell_height: float,
) -> Optional[tuple[int, int]]:
    """Figures out a second measured card's (row, col) from where it sits
    relative to the first card, so the user never has to type a cell
    label for the common case of clicking a visibly-adjacent card.

    Compares how far the second card's center has moved from the first
    card's center, in units of one grid cell, along whichever axis moved
    more. Returns None if that movement doesn't round to a clean,
    nonzero cell offset (e.g. the two boxes overlap, or the click wasn't
    aligned with either axis) -- callers should fall back to asking.
    """
    if cell_width <= 0 or cell_height <= 0:
        return None
    dx = (second_box.x1 + second_box.x2) / 2 - (first_box.x1 + first_box.x2) / 2
    dy = (second_box.y1 + second_box.y2) / 2 - (first_box.y1 + first_box.y2) / 2
    if abs(dx) >= abs(dy):
        col_offset = round(dx / cell_width)
        if col_offset == 0:
            return None
        return (first_row, first_col + col_offset)
    row_offset = round(dy / cell_height)
    if row_offset == 0:
        return None
    return (first_row + row_offset, first_col)


def build_result_text(
    profile_name: str,
    page_num: int,
    is_back: bool,
    measurements: Sequence[CardMeasurement],
    current: dict,
    field_names: Sequence[str],
    scale: float,
    fallback_gap_x: float,
    fallback_gap_y: float,
) -> str:
    """Runs derive_geometry() and formats the same report --measure prints
    to the console, for display in the window (and stdout)."""
    result = derive_geometry(
        measurements, scale=scale,
        fallback_gap_x=fallback_gap_x, fallback_gap_y=fallback_gap_y,
    )
    grid_label = f"back grid, page {page_num}" if is_back else f"front grid, page {page_num}"
    lines = [f"Measured {len(measurements)} card(s) on the {grid_label} at render_scale={scale}:"]
    for m in measurements:
        lines.append(
            f"  r{m.row}c{m.col}: px({m.box.x1:g},{m.box.y1:g})-({m.box.x2:g},{m.box.y2:g})"
        )
    for w in result.warnings:
        lines.append(f"  WARNING: {w}")
    lines.append(f"\nSuggested patch for profiles/{profile_name}.json:")
    lines.append(format_suggested_patch(result, current, field_names))
    lines.append(
        f"\nThis is a suggestion only -- profiles/{profile_name}.json was NOT "
        f"modified. Copy the values you want into the JSON by hand, then "
        f"re-run --preview or --overlay to check them."
    )
    return "\n".join(lines)


# -- view transform (pure, no Tkinter -- unit testable) ----------------------


def _clamp_offset_axis(offset: float, scale: float, canvas_dim: float, image_dim: float) -> float:
    """Keeps one axis of the image reachable inside the viewport: centers
    it when the scaled image is smaller than the canvas on this axis,
    otherwise clamps the offset so the image can't be dragged fully out of
    view (its near edge can't cross the canvas's far edge)."""
    content = image_dim * scale
    if content <= canvas_dim:
        return (canvas_dim - content) / 2
    return clamp(offset, canvas_dim - content, 0.0)


def wheel_direction(delta: int) -> int:
    """Normalizes a Tkinter <MouseWheel> event's `delta` into -1 (zoom
    out), 0 (no-op), or +1 (zoom in).

    Windows reports `delta` in multiples of 120; macOS reports small
    integers (often 1-3, sometimes fractional-feeling from trackpad
    momentum). Using only the sign -- never the magnitude -- is what makes
    one code path correct on both without a single `sys.platform` check,
    and keeps an unusually large delta from producing a bigger zoom jump
    than a single notch of a mechanical wheel."""
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def is_pan_gesture(button: str, space_held: bool, pan_mode: bool) -> bool:
    """Decides whether a mouse-button press should start a pan instead of
    registering a calibration click. This is the one place that decision
    is made -- callers never need their own mode checks.

    Middle-button always pans. Left-button pans if EITHER persistent Pan
    mode is on (the discoverable "Pan" toggle) OR Spacebar is held (the
    original power-user shortcut); otherwise it's an ordinary calibration
    click. Any other button never pans.
    """
    if button == "middle":
        return True
    if button == "left":
        return pan_mode or space_held
    return False


def pan_mode_after_escape(pan_mode: bool) -> bool:
    """Escape always exits persistent Pan mode outright, regardless of its
    prior state -- an unconditional exit is easier to reason about (and to
    explain to a non-technical user) than a toggle."""
    return False


def cleared_temporary_pan_state(pan_mode: bool) -> tuple[bool, bool]:
    """Returns the (space_held, pan_mode) state after an event that clears
    *temporary* pan state -- Spacebar release or focus loss. Spacebar hold
    always clears; a deliberately-selected persistent Pan mode is passed
    through unchanged, since only clicking Pan again or pressing Escape
    should turn it off."""
    return (False, pan_mode)


def pan_active(pan_mode: bool, space_held: bool, panning: bool) -> bool:
    """True while the user is doing anything pan-related -- persistent Pan
    mode, a temporary Spacebar hold, or an active pan drag. Calibration
    aids like the crosshair and coordinate readout get out of the way for
    all three, since the user is moving the page, not aligning a corner."""
    return pan_mode or space_held or panning


def crosshair_display_position(
    enabled: bool,
    pan_mode: bool,
    space_held: bool,
    panning: bool,
    pointer: Optional[tuple[float, float]],
) -> Optional[tuple[float, float]]:
    """The canvas (x, y) position the crosshair guide lines should be drawn
    at, or None if they should be hidden. Combines the user's Crosshair
    toggle, every form of pan state, and the last known pointer position
    (None once the pointer has left the canvas) into one display decision,
    so every caller -- pointer motion, leaving the canvas, a resize, a pan
    mode change -- just asks "where, if anywhere" instead of re-deriving
    the visibility rule."""
    if pointer is None or not enabled or pan_active(pan_mode, space_held, panning):
        return None
    return pointer


def coordinate_readout_position(
    pan_mode: bool,
    space_held: bool,
    panning: bool,
    pointer: Optional[tuple[float, float]],
) -> Optional[tuple[float, float]]:
    """Same idea as crosshair_display_position for the small coordinate
    readout, but independent of the Crosshair toggle -- the readout is a
    separate aid that's always available in normal calibration mode."""
    if pointer is None or pan_active(pan_mode, space_held, panning):
        return None
    return pointer


def crosshair_enabled_after_reset(enabled: bool) -> bool:
    """Start Over clears all measurement state but must never touch the
    user's Crosshair toggle -- an explicit identity function (like
    pan_mode_after_escape) gives that invariant a named, testable home
    instead of leaving it as an implicit omission inside _reset()."""
    return enabled


def crosshair_enabled_after_escape(enabled: bool) -> bool:
    """Escape exits persistent Pan mode only (see pan_mode_after_escape);
    it must never disable the Crosshair toggle."""
    return enabled


def format_pointer_readout(img_x: float, img_y: float) -> str:
    """Formats original rendered-image pixel coordinates for the small
    readout shown near the zoom percentage, e.g. 'X 1432  Y 2876'."""
    return f"X {round(img_x)}  Y {round(img_y)}"


@dataclass(frozen=True)
class ViewTransform:
    """Maps rendered-image pixel coordinates to canvas (screen) pixel
    coordinates and back. `scale` is canvas-pixels-per-image-pixel;
    `offset_x`/`offset_y` is where image point (0, 0) lands on the canvas.

    Every calibration click is converted through `canvas_to_image` exactly
    once, on the way in -- everything downstream (measurements, suggested
    profile values) stays in image space and never touches scale/offset
    again. All mutating-looking methods return a new ViewTransform rather
    than modifying in place, so a CalibrationWindow just reassigns
    `self.view = self.view.zoomed_at(...)` etc.
    """

    scale: float
    offset_x: float
    offset_y: float

    def image_to_canvas(self, img_x: float, img_y: float) -> tuple[float, float]:
        return (img_x * self.scale + self.offset_x, img_y * self.scale + self.offset_y)

    def canvas_to_image(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        return ((canvas_x - self.offset_x) / self.scale, (canvas_y - self.offset_y) / self.scale)

    def zoomed_at(
        self, pointer_x: float, pointer_y: float, new_scale: float,
        min_scale: float, max_scale: float,
    ) -> "ViewTransform":
        """A new ViewTransform at `new_scale` (clamped to [min_scale,
        max_scale]) with offsets adjusted so the image point currently
        under (pointer_x, pointer_y) stays under it -- pointer-anchored
        zoom, so the view never jumps."""
        new_scale = clamp(new_scale, min_scale, max_scale)
        img_x, img_y = self.canvas_to_image(pointer_x, pointer_y)
        return ViewTransform(
            new_scale,
            pointer_x - img_x * new_scale,
            pointer_y - img_y * new_scale,
        )

    def panned_by(self, dx: float, dy: float) -> "ViewTransform":
        return ViewTransform(self.scale, self.offset_x + dx, self.offset_y + dy)

    def recentered_for_resize(
        self, old_canvas_w: float, old_canvas_h: float, new_canvas_w: float, new_canvas_h: float,
    ) -> "ViewTransform":
        """A new ViewTransform at the same `scale`, with offsets adjusted
        so the image point that was at the old viewport's center is at the
        new viewport's center. Used when the canvas is resized while the
        user is manually zoomed (not Fit-to-Window) -- growing or
        shrinking the window should feel like the viewport changing size
        around a fixed point in the image, not a jump back to the image's
        origin or a re-fit."""
        old_center_x, old_center_y = old_canvas_w / 2, old_canvas_h / 2
        img_x, img_y = self.canvas_to_image(old_center_x, old_center_y)
        new_center_x, new_center_y = new_canvas_w / 2, new_canvas_h / 2
        return ViewTransform(
            self.scale,
            new_center_x - img_x * self.scale,
            new_center_y - img_y * self.scale,
        )

    def clamped(self, canvas_w: float, canvas_h: float, image_w: float, image_h: float) -> "ViewTransform":
        """Keeps the image reachable within the viewport on both axes (see
        `_clamp_offset_axis`)."""
        return ViewTransform(
            self.scale,
            _clamp_offset_axis(self.offset_x, self.scale, canvas_w, image_w),
            _clamp_offset_axis(self.offset_y, self.scale, canvas_h, image_h),
        )

    def visible_source_rect(
        self, canvas_w: float, canvas_h: float, image_w: float, image_h: float,
    ) -> tuple[float, float, float, float]:
        """The (x1, y1, x2, y2) region of the source image currently
        visible in the viewport, clipped to the image's own bounds. This
        is the only region that ever needs to be cropped out of the
        full-resolution source and resized for display -- the rest of the
        viewport (if the image is smaller than the canvas) stays blank."""
        x1, y1 = self.canvas_to_image(0, 0)
        x2, y2 = self.canvas_to_image(canvas_w, canvas_h)
        return (
            clamp(x1, 0, image_w), clamp(y1, 0, image_h),
            clamp(x2, 0, image_w), clamp(y2, 0, image_h),
        )

    @classmethod
    def fitting(cls, scale: float, canvas_w: float, canvas_h: float, image_w: float, image_h: float) -> "ViewTransform":
        """A view at `scale`, centered in the viewport. Used for both "Fit
        to Window" and "100%" -- they differ only in which scale is
        passed in."""
        return cls(scale, 0.0, 0.0).clamped(canvas_w, canvas_h, image_w, image_h)


def recompute_view_for_resize(
    view: ViewTransform,
    is_fit: bool,
    old_canvas_w: float, old_canvas_h: float,
    new_canvas_w: float, new_canvas_h: float,
    image_w: float, image_h: float,
) -> ViewTransform:
    """The one place that decides what the view should become when the
    canvas viewport changes size (window resize/maximize).

    In Fit-to-Window mode the view is simply recalculated at the new fit
    scale, same as clicking "Fit to Window" again. Otherwise (manual zoom,
    including "100%") the scale is preserved and the image point that was
    at the old viewport's center is kept at the new viewport's center, so
    a resize doesn't throw away the user's place. Either way the result is
    clamped to the new viewport, exactly like every other view change.
    """
    if is_fit:
        fit_scale = display_scale(int(image_w), int(image_h), int(new_canvas_w), int(new_canvas_h))
        new_view = ViewTransform(fit_scale, 0.0, 0.0)
    else:
        new_view = view.recentered_for_resize(old_canvas_w, old_canvas_h, new_canvas_w, new_canvas_h)
    return new_view.clamped(new_canvas_w, new_canvas_h, image_w, image_h)


# -- the window ---------------------------------------------------------


class CalibrationWindow(tk.Tk):
    MARKER_RADIUS = 4
    # "hand2" (not "fleur") because it renders correctly on both Windows
    # and macOS Tk without any platform branching; "fleur" is unreliable
    # on Mac Tk.
    PAN_CURSOR = "hand2"
    # A saturated magenta reads as high-contrast against both light and
    # dark card art without needing a two-tone/dashed trick.
    CROSSHAIR_COLOR = "#ff33cc"

    def __init__(
        self,
        profile: DeckProfile,
        profile_name: str,
        page_image: Image.Image,
        page_num: int,
        is_back: bool,
    ):
        super().__init__()
        self.profile = profile
        self.profile_name = profile_name
        self.page_image = page_image
        self.page_num = page_num
        self.is_back = is_back

        resolved = profile.back_geometry() if is_back else profile.front_geometry()
        self.field_names = BACK_FIELDS if is_back else FRONT_FIELDS
        self.current_values = dict(zip(self.field_names, (
            resolved.left, resolved.top,
            resolved.card_width, resolved.card_height,
            resolved.gap_x, resolved.gap_y,
        )))
        self.fallback_gap_x = resolved.gap_x
        self.fallback_gap_y = resolved.gap_y

        # The canvas is a *responsive* viewport onto page_image -- its real
        # size is whatever Tkinter actually allocates it (see
        # _on_canvas_configure), which grows and shrinks as the window is
        # resized or maximized. self.canvas_width/height start out as
        # placeholders (MAX_DISPLAY_WIDTH/HEIGHT, used only for initial
        # window sizing) and are replaced by the canvas's real dimensions
        # the first time Tkinter reports a nontrivial size.
        self.canvas_width = MAX_DISPLAY_WIDTH
        self.canvas_height = MAX_DISPLAY_HEIGHT
        self.fit_scale = display_scale(
            page_image.width, page_image.height, self.canvas_width, self.canvas_height,
        )
        # Zooming out past the fit scale isn't useful, but this keeps
        # "Fit to Window" reachable even in the (unlikely) case fit_scale
        # itself is below the usual floor.
        self.min_zoom = min(MIN_ZOOM_FLOOR, self.fit_scale)
        self.view = ViewTransform.fitting(
            self.fit_scale, self.canvas_width, self.canvas_height,
            page_image.width, page_image.height,
        )
        # Whether self.view should track "Fit to Window" across a resize
        # (True) or hold its current scale, re-anchored at the viewport
        # center (False, set by manual zoom / 100% / scroll-wheel).
        self._fit_mode = True
        # True once the canvas has reported a real (non-degenerate) size
        # and the image has been rendered at least once.
        self._initialized = False
        self._resize_job: Optional[str] = None
        self._pending_canvas_size: Optional[tuple[int, int]] = None

        self.measurements: list[CardMeasurement] = []
        self.pending_click: Optional[tuple[float, float]] = None
        self.suggestion_boxes: list[PixelBox] = []
        self.details_expanded = False
        self._done = False

        self.image_canvas_id: Optional[int] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self._overlay_ids: list[int] = []

        self._space_held = False
        self._panning = False
        self._pan_last: Optional[tuple[float, float]] = None
        # Persistent Pan mode, toggled on/off by the "Pan" button (or
        # cleared by Escape) -- distinct from the temporary Spacebar hold.
        self._pan_mode = False

        # Crosshair calibration aid -- canvas-space only (see module
        # docstring's coordinate-space note); defaults on. The two line
        # items are created lazily on first pointer motion and reused
        # (moved/hidden/shown) rather than recreated every event.
        self._crosshair_enabled = True
        self._crosshair_h_id: Optional[int] = None
        self._crosshair_v_id: Optional[int] = None
        self._pointer_xy: Optional[tuple[float, float]] = None

        self.title(f"DeckForge Calibration -- {profile_name} (page {page_num})")
        # Initial window size only; the canvas expands to fill whatever
        # space the user resizes/maximizes the window to.
        self.geometry(f"{MAX_DISPLAY_WIDTH}x{MAX_DISPLAY_HEIGHT + 200}")
        self.minsize(480, 360)
        self._build_widgets()
        self._set_step(
            "Step 1 of 3 -- Mark a card",
            "Click the UPPER-LEFT corner of a card. DeckForge uses this pair "
            "of clicks to work out that card's size and position.",
        )

    # -- layout -----------------------------------------------------

    def _build_widgets(self) -> None:
        # Row 4 (the canvas) is the only row that grows -- instruction
        # text, view controls, and the workflow buttons/text beneath the
        # canvas keep their natural height, so maximizing/resizing the
        # window grows the calibration viewport, not blank space.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.step_label = tk.Label(self, text="", font=("Segoe UI", 10, "bold"), fg="#2a7de1", anchor="w")
        self.step_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        self.status_label = tk.Label(self, text="", font=("Segoe UI", 11), anchor="w", justify="left")
        self.status_label.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        view_frame = tk.Frame(self)
        view_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 2))
        tk.Button(view_frame, text="Fit to Window", command=self._fit_to_window).pack(side="left")
        tk.Button(view_frame, text="100%", command=self._zoom_to_100).pack(side="left", padx=4)
        self.pan_button = tk.Button(
            view_frame, text="Pan", command=self._toggle_pan_mode, relief="raised", width=5,
        )
        self.pan_button.pack(side="left", padx=4)
        self.crosshair_button = tk.Button(
            view_frame, text="Crosshair", command=self._toggle_crosshair, relief="sunken",
        )
        self.crosshair_button.pack(side="left", padx=4)
        self.zoom_label = tk.Label(view_frame, text="", font=("Segoe UI", 9), fg="#555555", anchor="e")
        self.zoom_label.pack(side="right")
        self.coord_label = tk.Label(
            view_frame, text="", font=("Segoe UI", 9), fg="#555555", anchor="e", width=16,
        )
        self.coord_label.pack(side="right", padx=(0, 8))

        self.pan_hint_label = tk.Label(
            self, anchor="w", font=("Segoe UI", 9), fg="#555555",
            text="Move page: Select Pan, or hold Spacebar and drag.",
        )
        self.pan_hint_label.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 2))

        self.canvas = tk.Canvas(self, cursor=self._current_base_cursor(), background="#dddddd")
        self.canvas.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<B1-Motion>", self._on_left_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<ButtonPress-2>", self._on_middle_press)
        self.canvas.bind("<B2-Motion>", self._on_middle_motion)
        self.canvas.bind("<ButtonRelease-2>", self._on_middle_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)  # Windows + macOS
        self.canvas.bind("<Button-4>", self._on_wheel_button4)  # Linux (X11) scroll up
        self.canvas.bind("<Button-5>", self._on_wheel_button5)  # Linux (X11) scroll down
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)

        self.bind("<KeyPress-space>", self._on_space_press)
        self.bind("<KeyRelease-space>", self._on_space_release)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Configure>", self._on_root_configure)
        self.focus_set()

        self._update_zoom_label()

        button_frame = tk.Frame(self)
        button_frame.grid(row=5, column=0, sticky="ew", padx=8, pady=4)

        self.finish_button = tk.Button(
            button_frame, text="Finish with one card",
            command=self._finish_without_second_card, state="disabled",
        )
        self.finish_button.pack(side="left")

        self.copy_button = tk.Button(
            button_frame, text="Copy Calibration Settings",
            command=self._copy_result, state="disabled",
        )
        self.copy_button.pack(side="left", padx=4)

        tk.Button(button_frame, text="Start Over", command=self._reset).pack(side="left", padx=4)

        self.hint_label = tk.Label(
            self, anchor="w", font=("Segoe UI", 9), fg="#555555",
            text=(
                f"Nothing here is saved automatically -- profiles/{self.profile_name}.json "
                f"only changes once you copy your calibration settings into it by hand."
            ),
        )
        self.hint_label.grid(row=6, column=0, sticky="ew", padx=8, pady=(0, 2))

        # Hidden until the first measurement produces something to show --
        # measurement pixels and the raw JSON patch are useful, but they're
        # implementation detail a first-time user shouldn't have to look at.
        self.details_toggle = tk.Button(
            self, text="Technical Details (Optional) ▼", command=self._toggle_details,
            relief="flat", bd=0, anchor="w", font=("Segoe UI", 9), fg="#2a7de1",
            activeforeground="#2a7de1", cursor="hand2",
        )

        self.result_text = tk.Text(self, height=11, font=("Consolas", 9), state="disabled", wrap="none")

    # -- rendering (image + overlays, driven entirely by self.view + model) --

    def _redraw_image(self) -> None:
        x1, y1, x2, y2 = self.view.visible_source_rect(
            self.canvas_width, self.canvas_height, self.page_image.width, self.page_image.height,
        )
        ix1, iy1, ix2, iy2 = round(x1), round(y1), round(x2), round(y2)
        if ix2 <= ix1 or iy2 <= iy1:
            if self.image_canvas_id is not None:
                self.canvas.delete(self.image_canvas_id)
                self.image_canvas_id = None
            return

        crop = self.page_image.crop((ix1, iy1, ix2, iy2))
        dest_w = max(1, round((ix2 - ix1) * self.view.scale))
        dest_h = max(1, round((iy2 - iy1) * self.view.scale))
        if crop.size != (dest_w, dest_h):
            crop = crop.resize((dest_w, dest_h), Image.BILINEAR)

        self.tk_image = ImageTk.PhotoImage(crop)
        dest_x, dest_y = self.view.image_to_canvas(ix1, iy1)
        if self.image_canvas_id is None:
            self.image_canvas_id = self.canvas.create_image(dest_x, dest_y, anchor="nw", image=self.tk_image)
        else:
            self.canvas.coords(self.image_canvas_id, dest_x, dest_y)
            self.canvas.itemconfig(self.image_canvas_id, image=self.tk_image)
        self.canvas.tag_lower(self.image_canvas_id)
        self._raise_crosshair()

    def _redraw_overlays(self) -> None:
        """Clears every overlay canvas item and redraws it from the model
        (measurements, pending click, suggestion boxes) using the current
        view -- the single place overlay screen positions are computed, so
        they can never drift out of sync with a zoom/pan change."""
        for item_id in self._overlay_ids:
            self.canvas.delete(item_id)
        self._overlay_ids = []

        for m in self.measurements:
            self._overlay_ids.extend(self._draw_measured_box(m.box))
        if self.pending_click is not None:
            cx, cy = self.view.image_to_canvas(*self.pending_click)
            self._overlay_ids.append(self._draw_marker(cx, cy))
        for box in self.suggestion_boxes:
            self._overlay_ids.append(self._draw_suggestion(box))
        self._raise_crosshair()

    def _draw_measured_box(self, box: PixelBox) -> list[int]:
        x1, y1 = self.view.image_to_canvas(box.x1, box.y1)
        x2, y2 = self.view.image_to_canvas(box.x2, box.y2)
        return [
            self._draw_marker(x1, y1),
            self._draw_marker(x2, y2),
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=2),
        ]

    def _draw_marker(self, cx: float, cy: float) -> int:
        # Constant screen-pixel radius regardless of zoom, so markers stay
        # visible/clickable-looking at any scale.
        r = self.MARKER_RADIUS
        return self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="red", width=2)

    def _draw_suggestion(self, box: PixelBox) -> int:
        """Draws a highlighted card as an obviously clickable hotspot: a
        solid marker-style color wash over the whole card face, like a
        highlighter pen, with only a thin solid edge. A dashed outline
        reads as "trace this line"; a solid fill over the card reads as
        "this card". No text is drawn on the image -- the instruction
        lives in the status label above the canvas instead, where it's
        legible and impossible to miss."""
        x1, y1 = self.view.image_to_canvas(box.x1, box.y1)
        x2, y2 = self.view.image_to_canvas(box.x2, box.y2)
        return self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="#2a7de1", width=1,
            fill="#2a7de1", stipple="gray50",
        )

    def _update_zoom_label(self) -> None:
        self.zoom_label.configure(text=f"{round(self.view.scale * 100)}%")

    # -- resize (canvas viewport size, and window width for wrapping) -------

    def _on_canvas_configure(self, event: tk.Event) -> None:
        # Debounced: a window-border drag fires many of these in quick
        # succession, and each one would otherwise re-crop/resize the
        # full-resolution source image.
        self._pending_canvas_size = (event.width, event.height)
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._apply_pending_canvas_resize)

    def _apply_pending_canvas_resize(self) -> None:
        self._resize_job = None
        if self._pending_canvas_size is None:
            return
        new_w, new_h = self._pending_canvas_size
        self._pending_canvas_size = None

        # Ignore degenerate/transient sizes reported while Tkinter is still
        # laying out the window -- wait for a real, usable viewport before
        # computing (and rendering) anything against it.
        if new_w < MIN_VIEWPORT_DIM or new_h < MIN_VIEWPORT_DIM:
            return
        if self._initialized and (new_w, new_h) == (self.canvas_width, self.canvas_height):
            return

        old_w, old_h = self.canvas_width, self.canvas_height
        self.view = recompute_view_for_resize(
            self.view, self._fit_mode, old_w, old_h, new_w, new_h,
            self.page_image.width, self.page_image.height,
        )
        self.canvas_width, self.canvas_height = new_w, new_h
        self.fit_scale = display_scale(self.page_image.width, self.page_image.height, new_w, new_h)
        self.min_zoom = min(MIN_ZOOM_FLOOR, self.fit_scale)
        self._initialized = True

        self._redraw_image()
        self._redraw_overlays()
        self._update_zoom_label()
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _on_root_configure(self, event: tk.Event) -> None:
        # Keep the instruction text wrapping to the window's current
        # width instead of a value hard-coded to the old fixed canvas
        # size, which would look wrong once the window is resized.
        if event.widget is self:
            self.status_label.configure(wraplength=max(200, self.winfo_width() - 16))

    # -- click handling -----------------------------------------------------

    def _on_left_press(self, event: tk.Event) -> None:
        if is_pan_gesture("left", self._space_held, self._pan_mode):
            self._start_pan(event.x, event.y)
            return
        img_x, img_y = self.view.canvas_to_image(event.x, event.y)
        self._on_click_at(img_x, img_y)

    def _on_left_motion(self, event: tk.Event) -> None:
        if self._panning:
            self._continue_pan(event.x, event.y)

    def _on_left_release(self, event: tk.Event) -> None:
        if self._panning:
            self._end_pan()

    def _on_middle_press(self, event: tk.Event) -> None:
        self._start_pan(event.x, event.y)

    def _on_middle_motion(self, event: tk.Event) -> None:
        if self._panning:
            self._continue_pan(event.x, event.y)

    def _on_middle_release(self, event: tk.Event) -> None:
        if self._panning:
            self._end_pan()

    def _on_click_at(self, orig_x: float, orig_y: float) -> None:
        if len(self.measurements) >= 2:
            return  # both cards already measured; Reset to start over

        if self.pending_click is None:
            self.pending_click = (orig_x, orig_y)
            self._redraw_overlays()
            step_title = (
                "Step 1 of 3 -- Mark a card" if not self.measurements
                else "Step 2 of 3 -- Improve accuracy (optional)"
            )
            self._set_step(
                step_title,
                "Now click the LOWER-RIGHT corner of that same card.",
            )
            return

        x1, y1, x2, y2 = normalize_box(
            self.pending_click[0], self.pending_click[1], orig_x, orig_y,
        )
        if x2 - x1 < 1 or y2 - y1 < 1:
            messagebox.showwarning(
                "Same point", "Those two clicks are on top of each other -- "
                "click two distinct corners of the card.",
            )
            self._clear_pending()
            return

        second_box = PixelBox(x1, y1, x2, y2)

        if not self.measurements:
            row, col = 0, 0
        else:
            row, col = self._identify_second_card(second_box)
            if row is None:
                self._clear_pending()
                return

        self.measurements.append(CardMeasurement(row=row, col=col, box=second_box))
        self.pending_click = None
        self._clear_suggestions()
        self._redraw_overlays()
        self._show_result()

    def _identify_second_card(self, box: PixelBox) -> tuple[Optional[int], Optional[int]]:
        """Figures out the clicked card's (row, col) automatically when
        it's a recognizable horizontal/vertical neighbor of the first
        card; falls back to asking only when the click doesn't line up
        with either axis (e.g. a diagonal or far-away card)."""
        first = self.measurements[0]
        cell_width = (first.box.x2 - first.box.x1) + self.fallback_gap_x * self.profile.render_scale
        cell_height = (first.box.y2 - first.box.y1) + self.fallback_gap_y * self.profile.render_scale
        inferred = infer_second_cell(first.row, first.col, first.box, box, cell_width, cell_height)
        if inferred is not None:
            return inferred
        return self._prompt_cell_label()

    def _clear_pending(self) -> None:
        self.pending_click = None
        self._redraw_overlays()

    def _prompt_cell_label(self) -> tuple[Optional[int], Optional[int]]:
        guess = "r0c1" if self.measurements[0].col == 0 else "r1c0"
        while True:
            label = simpledialog.askstring(
                "Which card is this?",
                "Couldn't tell which grid cell that is from where you "
                "clicked. Row/column of this card, e.g. r0c1 (must differ "
                "from the first card's row and/or column):",
                initialvalue=guess, parent=self,
            )
            if label is None:
                return None, None
            try:
                return parse_cell_label(label)
            except MeasureError as e:
                messagebox.showerror("Invalid cell", str(e))

    # -- pan -----------------------------------------------------

    def _start_pan(self, x: float, y: float) -> None:
        self._panning = True
        self._pan_last = (x, y)
        self.canvas.configure(cursor=self.PAN_CURSOR)
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _continue_pan(self, x: float, y: float) -> None:
        last_x, last_y = self._pan_last
        self.view = self.view.panned_by(x - last_x, y - last_y).clamped(
            self.canvas_width, self.canvas_height, self.page_image.width, self.page_image.height,
        )
        self._pan_last = (x, y)
        self._redraw_image()
        self._redraw_overlays()

    def _end_pan(self) -> None:
        self._panning = False
        self._pan_last = None
        self.canvas.configure(cursor=self.PAN_CURSOR if self._space_held else self._current_base_cursor())
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _on_space_press(self, event: tk.Event) -> None:
        if self._space_held:
            return
        self._space_held = True
        if not self._panning:
            self.canvas.configure(cursor=self.PAN_CURSOR)
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _on_space_release(self, event: tk.Event) -> None:
        self._space_held, self._pan_mode = cleared_temporary_pan_state(self._pan_mode)
        if not self._panning:
            self.canvas.configure(cursor=self._current_base_cursor())
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _on_focus_out(self, event: tk.Event) -> None:
        # Alt-tabbing (or any other focus loss) mid-drag or mid-Spacebar-
        # hold must not leave pan/space state stuck with no way to clear
        # it -- but it also must not disable a deliberately selected
        # persistent Pan mode, which cleared_temporary_pan_state()
        # preserves.
        if self._panning:
            self._end_pan()
        self._space_held, self._pan_mode = cleared_temporary_pan_state(self._pan_mode)
        self.canvas.configure(cursor=self._current_base_cursor())
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _current_base_cursor(self) -> str:
        if self._pan_mode:
            return self.PAN_CURSOR
        return "arrow" if self._done else "crosshair"

    # -- Pan mode -----------------------------------------------------

    def _toggle_pan_mode(self) -> None:
        self._set_pan_mode(not self._pan_mode)

    def _on_escape(self, event: tk.Event) -> None:
        # Escape exits Pan mode only -- crosshair_enabled_after_escape() is
        # an identity function, but assigning through it (rather than just
        # not touching self._crosshair_enabled) keeps this invariant
        # explicit and unit tested, matching pan_mode_after_escape().
        self._crosshair_enabled = crosshair_enabled_after_escape(self._crosshair_enabled)
        self._set_pan_mode(pan_mode_after_escape(self._pan_mode))

    def _set_pan_mode(self, enabled: bool) -> None:
        self._pan_mode = enabled
        self.pan_button.configure(relief="sunken" if enabled else "raised")
        if not self._panning:
            self.canvas.configure(cursor=self._current_base_cursor())
        self._refresh_crosshair()
        self._refresh_coord_label()

    # -- crosshair (calibration aid; canvas-space only -- see module
    # docstring's coordinate-space note. Never touches self.measurements
    # or any image-space math.) -----------------------------------------

    def _toggle_crosshair(self) -> None:
        self._crosshair_enabled = not self._crosshair_enabled
        self.crosshair_button.configure(relief="sunken" if self._crosshair_enabled else "raised")
        self._refresh_crosshair()

    def _on_canvas_motion(self, event: tk.Event) -> None:
        self._pointer_xy = (event.x, event.y)
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _on_canvas_leave(self, event: tk.Event) -> None:
        self._pointer_xy = None
        self._refresh_crosshair()
        self._refresh_coord_label()

    def _refresh_crosshair(self) -> None:
        position = crosshair_display_position(
            self._crosshair_enabled, self._pan_mode, self._space_held, self._panning, self._pointer_xy,
        )
        if position is None:
            self._hide_crosshair()
        else:
            self._show_crosshair_at(*position)

    def _show_crosshair_at(self, x: float, y: float) -> None:
        if self._crosshair_h_id is None:
            self._crosshair_h_id = self.canvas.create_line(
                0, y, self.canvas_width, y, fill=self.CROSSHAIR_COLOR, width=1,
            )
            self._crosshair_v_id = self.canvas.create_line(
                x, 0, x, self.canvas_height, fill=self.CROSSHAIR_COLOR, width=1,
            )
        else:
            self.canvas.coords(self._crosshair_h_id, 0, y, self.canvas_width, y)
            self.canvas.coords(self._crosshair_v_id, x, 0, x, self.canvas_height)
            self.canvas.itemconfigure(self._crosshair_h_id, state="normal")
            self.canvas.itemconfigure(self._crosshair_v_id, state="normal")
        self._raise_crosshair()

    def _hide_crosshair(self) -> None:
        if self._crosshair_h_id is not None:
            self.canvas.itemconfigure(self._crosshair_h_id, state="hidden")
            self.canvas.itemconfigure(self._crosshair_v_id, state="hidden")

    def _raise_crosshair(self) -> None:
        # Called after every image/overlay redraw so newly (re)created
        # items -- which Tkinter stacks on top by default -- never end up
        # covering the crosshair. Not added to self._overlay_ids, so
        # _redraw_overlays() never deletes it.
        if self._crosshair_h_id is not None:
            self.canvas.tag_raise(self._crosshair_h_id)
            self.canvas.tag_raise(self._crosshair_v_id)

    def _refresh_coord_label(self) -> None:
        position = coordinate_readout_position(self._pan_mode, self._space_held, self._panning, self._pointer_xy)
        if position is None:
            self.coord_label.configure(text="")
            return
        img_x, img_y = self.view.canvas_to_image(*position)
        img_x = clamp(img_x, 0, self.page_image.width)
        img_y = clamp(img_y, 0, self.page_image.height)
        self.coord_label.configure(text=format_pointer_readout(img_x, img_y))

    # -- zoom -----------------------------------------------------

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._zoom_by_direction(wheel_direction(event.delta), event.x, event.y)

    def _on_wheel_button4(self, event: tk.Event) -> None:
        self._zoom_by_direction(1, event.x, event.y)

    def _on_wheel_button5(self, event: tk.Event) -> None:
        self._zoom_by_direction(-1, event.x, event.y)

    def _zoom_by_direction(self, direction: int, pointer_x: float, pointer_y: float) -> None:
        if direction == 0:
            return
        self._fit_mode = False
        new_scale = self.view.scale * (ZOOM_STEP ** direction)
        self.view = self.view.zoomed_at(
            pointer_x, pointer_y, new_scale, self.min_zoom, MAX_ZOOM,
        ).clamped(self.canvas_width, self.canvas_height, self.page_image.width, self.page_image.height)
        self._redraw_image()
        self._redraw_overlays()
        self._update_zoom_label()
        self._refresh_coord_label()

    def _fit_to_window(self) -> None:
        self._fit_mode = True
        self.view = ViewTransform.fitting(
            self.fit_scale, self.canvas_width, self.canvas_height,
            self.page_image.width, self.page_image.height,
        )
        self._redraw_image()
        self._redraw_overlays()
        self._update_zoom_label()
        self._refresh_coord_label()

    def _zoom_to_100(self) -> None:
        self._fit_mode = False
        scale = clamp(1.0, self.min_zoom, MAX_ZOOM)
        self.view = ViewTransform.fitting(
            scale, self.canvas_width, self.canvas_height,
            self.page_image.width, self.page_image.height,
        )
        self._redraw_image()
        self._redraw_overlays()
        self._update_zoom_label()
        self._refresh_coord_label()

    # -- results -----------------------------------------------------

    def _show_result(self) -> None:
        try:
            text = build_result_text(
                profile_name=self.profile_name, page_num=self.page_num, is_back=self.is_back,
                measurements=self.measurements, current=self.current_values,
                field_names=self.field_names, scale=self.profile.render_scale,
                fallback_gap_x=self.fallback_gap_x, fallback_gap_y=self.fallback_gap_y,
            )
        except MeasureError as e:
            messagebox.showerror("Measurement error", str(e))
            return

        print(text)
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")
        self.copy_button.configure(state="normal")
        if not self.details_toggle.winfo_ismapped():
            self.details_toggle.grid(row=7, column=0, sticky="ew", padx=8, pady=(4, 0))
        if self.details_expanded:
            self.result_text.grid(row=8, column=0, sticky="nsew", padx=8, pady=(0, 8))

        if len(self.measurements) == 1:
            self._show_second_card_suggestions()
        else:
            self.finish_button.configure(state="disabled")
            self._done = True
            self.canvas.configure(cursor=self._current_base_cursor())
            self._set_step(
                "Step 3 of 3 -- Finish up",
                "Calibration complete.\n"
                "Copy your calibration settings, then run --preview to check them.",
            )

    def _show_second_card_suggestions(self) -> None:
        """Highlights likely-adjacent cards as obviously clickable hotspots
        so the user can optionally measure a second card for a more
        accurate calibration -- entirely in terms of "click this card for
        better accuracy", never rows, columns, or gap spacing."""
        first = self.measurements[0]
        card_width = first.box.x2 - first.box.x1
        card_height = first.box.y2 - first.box.y1
        gap_x = self.fallback_gap_x * self.profile.render_scale
        gap_y = self.fallback_gap_y * self.profile.render_scale

        self.suggestion_boxes = []
        right_box = predicted_neighbor_box(first.box, card_width, card_height, gap_x, gap_y, "right")
        if right_box.x2 <= self.page_image.width and right_box.y2 <= self.page_image.height:
            self.suggestion_boxes.append(right_box)

        below_box = predicted_neighbor_box(first.box, card_width, card_height, gap_x, gap_y, "below")
        if below_box.x2 <= self.page_image.width and below_box.y2 <= self.page_image.height:
            self.suggestion_boxes.append(below_box)

        self._redraw_overlays()

        self.finish_button.configure(state="normal")
        step_title = "Step 2 of 3 -- Improve accuracy (optional)"
        if self.suggestion_boxes:
            self._set_step(
                step_title,
                "For a more accurate calibration, measure a highlighted card "
                "too: click its UPPER-LEFT corner, then its LOWER-RIGHT "
                "corner -- or Finish with one card if this is enough.",
            )
        else:
            self._set_step(
                step_title,
                "For a more accurate calibration, measure another visible "
                "card the same way: click its UPPER-LEFT corner, then its "
                "LOWER-RIGHT corner -- or Finish with one card if this is "
                "enough.",
            )

    def _clear_suggestions(self) -> None:
        self.suggestion_boxes = []

    def _finish_without_second_card(self) -> None:
        self._clear_suggestions()
        self._redraw_overlays()
        self.finish_button.configure(state="disabled")
        self._done = True
        self.canvas.configure(cursor=self._current_base_cursor())
        self._set_step(
            "Step 3 of 3 -- Finish up",
            "Calibration complete using one card.\n"
            "Copy your calibration settings, then run --preview to check them.",
        )

    def _copy_result(self) -> None:
        text = self.result_text.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        original_text = self.copy_button.cget("text")
        self.copy_button.configure(text="Copied!")
        self.after(1200, lambda: self.copy_button.configure(text=original_text))

    def _toggle_details(self) -> None:
        self.details_expanded = not self.details_expanded
        if self.details_expanded:
            self.result_text.grid(row=8, column=0, sticky="nsew", padx=8, pady=(0, 8))
            self.details_toggle.configure(text="Technical Details (Optional) ▲")
        else:
            self.result_text.grid_remove()
            self.details_toggle.configure(text="Technical Details (Optional) ▼")

    def _reset(self) -> None:
        # Clears all calibration state and drawings, but deliberately
        # leaves self.view (zoom/pan) and the Crosshair toggle untouched --
        # a user retrying a mis-click almost certainly wants to keep
        # looking at the same spot, with the same aids on or off.
        self._crosshair_enabled = crosshair_enabled_after_reset(self._crosshair_enabled)
        self.pending_click = None
        self.suggestion_boxes = []
        self.measurements = []
        self._done = False
        self._redraw_overlays()

        self.finish_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.canvas.configure(cursor=self._current_base_cursor())
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.result_text.grid_remove()
        self.details_expanded = False
        self.details_toggle.configure(text="Technical Details (Optional) ▼")
        self.details_toggle.grid_remove()
        self._set_step(
            "Step 1 of 3 -- Mark a card",
            "Click the UPPER-LEFT corner of a card. DeckForge uses this pair "
            "of clicks to work out that card's size and position.",
        )

    def _set_step(self, step: str, instruction: str) -> None:
        self.step_label.configure(text=step)
        self.status_label.configure(text=instruction)


def run_calibration(
    profile: DeckProfile,
    profile_name: str,
    page_image: Image.Image,
    page_num: int,
    is_back: bool,
) -> None:
    """Opens the interactive calibration window and blocks until closed."""
    window = CalibrationWindow(profile, profile_name, page_image, page_num, is_back)
    window.mainloop()
