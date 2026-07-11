"""Zoom/pan/fit coordinate transform, shared by any workspace with a
zoomable PDF canvas (Calibrate today; Preview/Edit Cards later).

Ported from src/deckforge/calibrate_ui.py's ViewTransform (the CLI's
--calibrate window), which is pure Python with no Tkinter dependency in
the class itself -- but that module imports tkinter at the top level, so
importing ViewTransform from it directly would make Tkinter a hard import
for this PySide6 app. This module is a straight port of that same design,
not a reimplementation: same fields, same method behavior, same tests
(see tests/test_view_transform.py, adapted from tests/test_calibrate_ui.py).

COORDINATE SPACES
-------------------
"image space" -- pixels of the full-resolution rendered PDF page.
"canvas space" -- pixels of the widget's own viewport (there is no
separate letterboxing step the way FindCardsView needs one: `clamped()`
already centers content smaller than the viewport, so the widget's own
pixel space doubles as "canvas space" directly).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def display_scale(image_width: int, image_height: int, max_width: int, max_height: int) -> float:
    """Scale factor to fit an image within (max_width, max_height) without
    upscaling. 1.0 if the image already fits."""
    if image_width <= 0 or image_height <= 0 or max_width <= 0 or max_height <= 0:
        return 1.0
    return min(1.0, max_width / image_width, max_height / image_height)


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
    """Normalizes a wheel event's delta into -1 (zoom out), 0 (no-op), or
    +1 (zoom in). Using only the sign -- never the magnitude -- keeps an
    unusually large delta from producing a bigger zoom jump than a single
    notch of a mechanical wheel, and is portable across platforms that
    report wildly different delta scales for the same physical scroll."""
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def is_pan_gesture(button: str, space_held: bool, pan_mode: bool) -> bool:
    """Decides whether a mouse-button press should start a pan instead of
    registering a calibration click. Middle-button always pans. Left-
    button pans if EITHER persistent Pan mode is on OR Spacebar is held;
    otherwise it's an ordinary click. Any other button never pans."""
    if button == "middle":
        return True
    if button == "left":
        return pan_mode or space_held
    return False


def pan_active(pan_mode: bool, space_held: bool, panning: bool) -> bool:
    """True while the user is doing anything pan-related -- persistent Pan
    mode, a temporary Spacebar hold, or an active pan drag. Calibration
    aids like guide lines get out of the way for all three, since the
    user is moving the page, not aligning a corner."""
    return pan_mode or space_held or panning


@dataclass(frozen=True)
class ViewTransform:
    """Maps rendered-image pixel coordinates to canvas (widget) pixel
    coordinates and back. `scale` is canvas-pixels-per-image-pixel;
    `offset_x`/`offset_y` is where image point (0, 0) lands on the canvas.

    Every click is converted through `canvas_to_image` exactly once, on
    the way in -- everything downstream stays in image space (and, one
    further division by render_scale, PDF-point space) and never touches
    scale/offset again. All mutating-looking methods return a new
    ViewTransform rather than modifying in place.
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
        new viewport's center. Used when the widget is resized while the
        user is manually zoomed (not Fit) -- growing or shrinking the
        window should feel like the viewport changing size around a fixed
        point in the image, not a jump back to the image's origin."""
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
        visible in the viewport, clipped to the image's own bounds."""
        x1, y1 = self.canvas_to_image(0, 0)
        x2, y2 = self.canvas_to_image(canvas_w, canvas_h)
        return (
            clamp(x1, 0, image_w), clamp(y1, 0, image_h),
            clamp(x2, 0, image_w), clamp(y2, 0, image_h),
        )

    @classmethod
    def fitting(cls, scale: float, canvas_w: float, canvas_h: float, image_w: float, image_h: float) -> "ViewTransform":
        """A view at `scale`, centered in the viewport. Used for both
        "Fit" and "100%" -- they differ only in which scale is passed in."""
        return cls(scale, 0.0, 0.0).clamped(canvas_w, canvas_h, image_w, image_h)


def recompute_view_for_resize(
    view: ViewTransform,
    is_fit: bool,
    old_canvas_w: float, old_canvas_h: float,
    new_canvas_w: float, new_canvas_h: float,
    image_w: float, image_h: float,
) -> ViewTransform:
    """The one place that decides what the view should become when the
    canvas viewport changes size (widget resize).

    In Fit mode the view is simply recalculated at the new fit scale,
    same as clicking "Fit" again. Otherwise (manual zoom) the scale is
    preserved and the image point that was at the old viewport's center
    is kept at the new viewport's center, so a resize doesn't throw away
    the user's place. Either way the result is clamped to the new
    viewport, exactly like every other view change.
    """
    if is_fit:
        fit_scale = display_scale(int(image_w), int(image_h), int(new_canvas_w), int(new_canvas_h))
        new_view = ViewTransform(fit_scale, 0.0, 0.0)
    else:
        new_view = view.recentered_for_resize(old_canvas_w, old_canvas_h, new_canvas_w, new_canvas_h)
    return new_view.clamped(new_canvas_w, new_canvas_h, image_w, image_h)
