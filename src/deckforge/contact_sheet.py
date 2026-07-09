"""
contact_sheet.py - tiles a list of same-size card images into one labeled
QA sheet.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from PIL import Image, ImageDraw


def build_contact_sheet(
    images: Sequence[Image.Image],
    labels: Optional[Sequence[str]] = None,
    columns: Optional[int] = None,
    thumb_width: int = 220,
) -> Image.Image:
    if not images:
        raise ValueError("no images to build a contact sheet from")

    w, h = images[0].size
    n = len(images)
    if columns is None:
        columns = math.ceil(math.sqrt(n))
    rows = math.ceil(n / columns)

    thumb_h = round(h * (thumb_width / w))
    label_h = 20
    pad = 8

    sheet_w = columns * (thumb_width + pad) + pad
    sheet_h = rows * (thumb_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)

    for i, img in enumerate(images):
        r, c = divmod(i, columns)
        x = pad + c * (thumb_width + pad)
        y = pad + r * (thumb_h + label_h + pad)
        thumb = img.resize((thumb_width, thumb_h))
        sheet.paste(thumb, (x, y))
        label = labels[i] if labels else str(i + 1)
        draw.text((x, y + thumb_h + 3), label, fill=(255, 255, 255))

    return sheet
