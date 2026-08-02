"""Preview rasterisation (FR-016d, FR-017, SC-005).

The preview is rasterised **from the generated PDF**, never re-drawn from the layout model.
Re-drawing would produce a second implementation of the placement rules, and the two would
drift — silently, and in exactly the direction that makes a preview worthless: it would keep
showing the right thing while the printed sheet went wrong.

Nothing here can affect the document. It takes PDF bytes and returns PNG bytes.
"""

from __future__ import annotations

import io

import pypdfium2

# FR-016d: enough to read a card name off the preview, capped so that asking for a preview
# cannot approach the cost of the generation it is previewing.
MIN_WIDTH_PX = 200
MAX_WIDTH_PX = 2000
DEFAULT_WIDTH_PX = 800


class PageOutOfRange(LookupError):
    """Asked for a page the document does not have."""


def clamp_width(width_px: int) -> int:
    return max(MIN_WIDTH_PX, min(MAX_WIDTH_PX, width_px))


def page_count(pdf: bytes) -> int:
    doc = pypdfium2.PdfDocument(io.BytesIO(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def render_page(pdf: bytes, page_number: int, width_px: int = DEFAULT_WIDTH_PX) -> bytes:
    """Rasterise one 1-based page to PNG at approximately `width_px` pixels wide."""
    width_px = clamp_width(width_px)
    doc = pypdfium2.PdfDocument(io.BytesIO(pdf))
    try:
        if not 1 <= page_number <= len(doc):
            raise PageOutOfRange(f"page {page_number} of {len(doc)}")
        page = doc[page_number - 1]
        # pypdfium2 scales relative to the PDF's own 72-dpi user space, so the requested
        # pixel width is expressed as a scale factor over the page's point width.
        image = page.render(scale=width_px / page.get_width()).to_pil()
        out = io.BytesIO()
        # optimize=False keeps the encode cheap; a preview is discarded after it is looked at.
        image.save(out, format="PNG", optimize=False)
        return out.getvalue()
    finally:
        doc.close()
