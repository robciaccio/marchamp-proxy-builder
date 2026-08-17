"""PDF composition (FR-008, FR-013, FR-015, FR-015a).

`invariant=1` is the whole reason ReportLab was chosen: it normalises the timestamp and
document-id metadata that otherwise vary per run, which is what makes SC-006's
byte-identical requirement a test that passes or fails rather than an aspiration.
"""

from __future__ import annotations

import io
from collections.abc import Callable

from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from marchamp.assets.store import Store
from marchamp.layout.geometry import PageLayout, cut_guides, mm_to_pt, page_layout
from marchamp.layout.paginate import Page, PlacedFace
from marchamp.render.images import FitMode, fit_rect

GUIDE_COLOUR = Color(0.45, 0.45, 0.45)
GUIDE_WIDTH_PT = 0.35

# One decoded, fit-mode-cropped face and the slot it belongs in.
Prepared = tuple[Image.Image, object, PlacedFace]

#: Called with (page index, that page alone as a standalone PDF) as each page completes.
OnPage = Callable[[int, bytes], None]


def _prepare(
    store: Store, ref: str, fit: FitMode, slot_w: float, slot_h: float
) -> tuple[Image.Image, object]:
    """Decode one source image and apply the fit mode's crop.

    Reads through the adapter (FR-004). `load()` inside the handle's scope, so the decode
    finishes before the source is closed — a store's handle need not be a file, and a lazy
    Pillow image over a closed stream fails much later and somewhere else.
    """
    with store.open(ref) as handle:
        img = Image.open(handle)
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


def _new_canvas(buf: io.BytesIO, layout: PageLayout) -> canvas.Canvas:
    c = canvas.Canvas(
        buf,
        pagesize=(mm_to_pt(layout.page_w_mm), mm_to_pt(layout.page_h_mm)),
        invariant=1,  # byte-identical output; see module docstring
        pageCompression=1,
    )
    c.setTitle("Marchamp proxy sheet")
    return c


def _draw_page(c: canvas.Canvas, layout: PageLayout, prepared: list[Prepared]) -> None:
    for img, rect, placed in prepared:
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
    _draw_guides(c, layout)


def _single_page_document(layout: PageLayout, prepared: list[Prepared]) -> bytes:
    """One page as a standalone PDF, drawn by the same code as the full document.

    This is what lets a preview page appear before the rest of the deck has finished
    (FR-016b). It reuses the already-decoded images, so it costs an encode rather than a
    second decode — and, because `_draw_page` is the only placement code either path uses,
    it cannot disagree with the corresponding page of the full document.
    """
    buf = io.BytesIO()
    c = _new_canvas(buf, layout)
    _draw_page(c, layout, prepared)
    c.showPage()
    c.save()
    return buf.getvalue()


def compose(
    pages: list[Page],
    page_size,
    fit_mode: FitMode,
    store: Store,
    on_page: OnPage | None = None,
) -> bytes:
    """Compose the whole document.

    `on_page` is optional and purely additive: with it omitted, nothing extra is computed
    and the bytes are identical to a run without it, which is what keeps SC-006's
    byte-identical guarantee independent of whether anyone is watching a preview.
    """
    layout = page_layout(page_size)
    buf = io.BytesIO()
    c = _new_canvas(buf, layout)

    slot_w, slot_h = layout.slot_size_mm
    for page in pages:
        prepared: list[Prepared] = []
        for placed in page.placed:
            img, rect = _prepare(store, placed.face.image_ref, fit_mode, slot_w, slot_h)
            prepared.append((img, rect, placed))

        _draw_page(c, layout, prepared)
        c.showPage()

        if on_page is not None:
            on_page(page.index, _single_page_document(layout, prepared))
        for img, _, _ in prepared:
            img.close()

    c.save()
    return buf.getvalue()
