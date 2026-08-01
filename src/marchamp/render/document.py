"""PDF composition (FR-008, FR-013, FR-015, FR-015a).

`invariant=1` is the whole reason ReportLab was chosen: it normalises the timestamp and
document-id metadata that otherwise vary per run, which is what makes SC-006's
byte-identical requirement a test that passes or fails rather than an aspiration.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from marchamp.layout.geometry import PageLayout, cut_guides, mm_to_pt, page_layout
from marchamp.layout.paginate import Page
from marchamp.render.images import FitMode, fit_rect

GUIDE_COLOUR = Color(0.45, 0.45, 0.45)
GUIDE_WIDTH_PT = 0.35


def _prepare(path: Path, fit: FitMode, slot_w: float, slot_h: float) -> tuple[Image.Image, object]:
    """Decode one source image and apply the fit mode's crop."""
    img = Image.open(path)
    img.load()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    rect = fit_rect(img.width, img.height, slot_w, slot_h, fit)
    if any(
        (
            rect.src_crop_top_px,
            rect.src_crop_bottom_px,
            rect.src_crop_left_px,
            rect.src_crop_right_px,
        )
    ):
        img = img.crop(
            (
                round(rect.src_crop_left_px),
                round(rect.src_crop_top_px),
                img.width - round(rect.src_crop_right_px),
                img.height - round(rect.src_crop_bottom_px),
            )
        )
    return img, rect


def _draw_guides(c: canvas.Canvas, layout: PageLayout) -> None:
    c.setStrokeColor(GUIDE_COLOUR)
    c.setLineWidth(GUIDE_WIDTH_PT)
    for x1, y1, x2, y2 in cut_guides(layout):
        c.line(mm_to_pt(x1), mm_to_pt(y1), mm_to_pt(x2), mm_to_pt(y2))


def compose(
    pages: list[Page],
    page_size,
    fit_mode: FitMode,
    image_dir: Path,
) -> bytes:
    layout = page_layout(page_size)
    buf = io.BytesIO()
    c = canvas.Canvas(
        buf,
        pagesize=(mm_to_pt(layout.page_w_mm), mm_to_pt(layout.page_h_mm)),
        invariant=1,  # byte-identical output; see module docstring
        pageCompression=1,
    )
    c.setTitle("Marchamp proxy sheet")

    slot_w, slot_h = layout.slot_size_mm
    for page in pages:
        for placed in page.placed:
            img, rect = _prepare(image_dir / placed.face.image_ref, fit_mode, slot_w, slot_h)
            # PDF origin is bottom-left; slots are indexed from the top.
            x_mm = placed.slot.x_mm + rect.offset_x_mm
            y_from_top = placed.slot.y_mm + rect.offset_y_mm
            y_mm = layout.page_h_mm - y_from_top - rect.draw_h_mm
            c.drawImage(
                ImageReader(img),
                mm_to_pt(x_mm),
                mm_to_pt(y_mm),
                width=mm_to_pt(rect.draw_w_mm),
                height=mm_to_pt(rect.draw_h_mm),
            )
            img.close()
        _draw_guides(c, layout)
        c.showPage()

    c.save()
    return buf.getvalue()
