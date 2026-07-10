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
"""

from __future__ import annotations

import tkinter as tk
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

MAX_DISPLAY_WIDTH = 1300
MAX_DISPLAY_HEIGHT = 820


# -- pure helpers (no Tkinter, no I/O -- unit testable) ----------------------


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


# -- the window ---------------------------------------------------------


class CalibrationWindow(tk.Tk):
    MARKER_RADIUS = 4

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

        self.scale = display_scale(
            page_image.width, page_image.height, MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT,
        )
        display_size = (round(page_image.width * self.scale), round(page_image.height * self.scale))
        display_image = page_image.resize(display_size, Image.LANCZOS) if self.scale != 1.0 else page_image
        self.tk_image = ImageTk.PhotoImage(display_image)

        self.measurements: list[CardMeasurement] = []
        self.pending_click: Optional[tuple[float, float]] = None
        self.pending_canvas_ids: list[int] = []
        self.measurement_canvas_ids: list[int] = []
        self.suggestion_canvas_ids: list[int] = []
        self.details_expanded = False

        self.title(f"DeckForge Calibration -- {profile_name} (page {page_num})")
        self._build_widgets(display_size)
        self._set_step(
            "Step 1 of 3 -- Mark a card",
            "Click the UPPER-LEFT corner of a card. DeckForge uses this pair "
            "of clicks to work out that card's size and position.",
        )

    # -- layout -----------------------------------------------------

    def _build_widgets(self, display_size: tuple[int, int]) -> None:
        self.step_label = tk.Label(self, text="", font=("Segoe UI", 10, "bold"), fg="#2a7de1", anchor="w")
        self.step_label.pack(fill="x", padx=8, pady=(8, 0))

        self.status_label = tk.Label(self, text="", font=("Segoe UI", 11), anchor="w", wraplength=MAX_DISPLAY_WIDTH)
        self.status_label.pack(fill="x", padx=8, pady=(0, 4))

        self.canvas = tk.Canvas(self, width=display_size[0], height=display_size[1], cursor="crosshair")
        self.canvas.pack(padx=8, pady=4)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
        self.canvas.bind("<Button-1>", self._on_click)

        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=8, pady=4)

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
        self.hint_label.pack(fill="x", padx=8, pady=(0, 2))

        # Hidden until the first measurement produces something to show --
        # measurement pixels and the raw JSON patch are useful, but they're
        # implementation detail a first-time user shouldn't have to look at.
        self.details_toggle = tk.Button(
            self, text="Technical Details (Optional) ▼", command=self._toggle_details,
            relief="flat", bd=0, anchor="w", font=("Segoe UI", 9), fg="#2a7de1",
            activeforeground="#2a7de1", cursor="hand2",
        )

        self.result_text = tk.Text(self, height=11, font=("Consolas", 9), state="disabled", wrap="none")

    # -- click handling -----------------------------------------------------

    def _on_click(self, event: tk.Event) -> None:
        if len(self.measurements) >= 2:
            return  # both cards already measured; Reset to start over

        orig_x, orig_y = event.x / self.scale, event.y / self.scale

        if self.pending_click is None:
            self.pending_click = (orig_x, orig_y)
            self.pending_canvas_ids.append(self._draw_marker(event.x, event.y))
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

        self.pending_canvas_ids.append(self._draw_marker(event.x, event.y))
        self.pending_canvas_ids.append(self.canvas.create_rectangle(
            self.pending_click[0] * self.scale, self.pending_click[1] * self.scale,
            event.x, event.y, outline="red", width=2,
        ))
        second_box = PixelBox(x1, y1, x2, y2)

        if not self.measurements:
            row, col = 0, 0
        else:
            row, col = self._identify_second_card(second_box)
            if row is None:
                self._clear_pending()
                return

        self.measurements.append(CardMeasurement(row=row, col=col, box=second_box))
        # Ownership of these corner markers/rectangle passes from "pending"
        # to "measured" -- keep their canvas ids tracked so Start Over can
        # still remove them, instead of dropping the list and leaking them.
        self.measurement_canvas_ids.extend(self.pending_canvas_ids)
        self.pending_click = None
        self.pending_canvas_ids = []
        self._clear_suggestions()
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

    def _draw_marker(self, cx: float, cy: float) -> int:
        r = self.MARKER_RADIUS
        return self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="red", width=2)

    def _clear_pending(self) -> None:
        for item_id in self.pending_canvas_ids:
            self.canvas.delete(item_id)
        self.pending_canvas_ids = []
        self.pending_click = None

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
            self.details_toggle.pack(fill="x", padx=8, pady=(4, 0))
        if self.details_expanded:
            self.result_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        if len(self.measurements) == 1:
            self._show_second_card_suggestions()
        else:
            self.finish_button.configure(state="disabled")
            self.canvas.configure(cursor="arrow")
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

        any_offered = False
        right_box = predicted_neighbor_box(first.box, card_width, card_height, gap_x, gap_y, "right")
        if right_box.x2 <= self.page_image.width and right_box.y2 <= self.page_image.height:
            self._draw_suggestion(right_box)
            any_offered = True

        below_box = predicted_neighbor_box(first.box, card_width, card_height, gap_x, gap_y, "below")
        if below_box.x2 <= self.page_image.width and below_box.y2 <= self.page_image.height:
            self._draw_suggestion(below_box)
            any_offered = True

        self.finish_button.configure(state="normal")
        step_title = "Step 2 of 3 -- Improve accuracy (optional)"
        if any_offered:
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

    def _draw_suggestion(self, box: PixelBox) -> None:
        """Draws a highlighted card as an obviously clickable hotspot: a
        solid marker-style color wash over the whole card face, like a
        highlighter pen, with only a thin solid edge. A dashed outline
        reads as "trace this line"; a solid fill over the card reads as
        "this card". No text is drawn on the image -- the instruction
        lives in the status label above the canvas instead, where it's
        legible and impossible to miss."""
        x1, y1, x2, y2 = (box.x1 * self.scale, box.y1 * self.scale, box.x2 * self.scale, box.y2 * self.scale)
        self.suggestion_canvas_ids.append(
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#2a7de1", width=1,
                fill="#2a7de1", stipple="gray50",
            )
        )

    def _clear_suggestions(self) -> None:
        for item_id in self.suggestion_canvas_ids:
            self.canvas.delete(item_id)
        self.suggestion_canvas_ids = []

    def _clear_measurement_markers(self) -> None:
        for item_id in self.measurement_canvas_ids:
            self.canvas.delete(item_id)
        self.measurement_canvas_ids = []

    def _finish_without_second_card(self) -> None:
        self._clear_suggestions()
        self.finish_button.configure(state="disabled")
        self.canvas.configure(cursor="arrow")
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
            self.result_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            self.details_toggle.configure(text="Technical Details (Optional) ▲")
        else:
            self.result_text.pack_forget()
            self.details_toggle.configure(text="Technical Details (Optional) ▼")

    def _reset(self) -> None:
        self._clear_pending()
        self._clear_suggestions()
        self._clear_measurement_markers()
        self.measurements = []
        self.finish_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.canvas.configure(cursor="crosshair")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.result_text.pack_forget()
        self.details_expanded = False
        self.details_toggle.configure(text="Technical Details (Optional) ▼")
        self.details_toggle.pack_forget()
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
