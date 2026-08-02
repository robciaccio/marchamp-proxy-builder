"""Calibration page (FR-023, User Story 3).

Consumer printers silently apply "fit to page" scaling, producing cards a few millimetres
off — enough not to fit a sleeve, and not obvious until a whole deck has been printed. One
sheet of paper protects against wasting forty.
"""

from __future__ import annotations

import io

from reportlab.lib.colors import black
from reportlab.pdfgen import canvas

from marchamp.layout.geometry import SLOT_SIZE_MM, PageSize, mm_to_pt

RULER_MM = 100


def calibration_pdf(page_size: PageSize = PageSize.LETTER) -> bytes:
    page_w, page_h = page_size.dimensions_mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(mm_to_pt(page_w), mm_to_pt(page_h)), invariant=1)
    c.setTitle("Marchamp print calibration")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(mm_to_pt(20), mm_to_pt(page_h - 20), "Print at 100% scale — page scaling OFF")
    c.setFont("Helvetica", 9)
    c.drawString(
        mm_to_pt(20),
        mm_to_pt(page_h - 26),
        f"The ruler must measure exactly {RULER_MM} mm. The outline must match a real card.",
    )

    # Ruler with 10 mm ticks.
    base_y = page_h - 45
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    c.line(mm_to_pt(20), mm_to_pt(base_y), mm_to_pt(20 + RULER_MM), mm_to_pt(base_y))
    c.setFont("Helvetica", 6)
    for i in range(RULER_MM + 1):
        if i % 10 == 0:
            h = 4
            c.drawCentredString(mm_to_pt(20 + i), mm_to_pt(base_y - 8), str(i))
        elif i % 5 == 0:
            h = 2.5
        else:
            h = 1.2
        c.line(mm_to_pt(20 + i), mm_to_pt(base_y), mm_to_pt(20 + i), mm_to_pt(base_y + h))

    # One outline at the SLOT size — not a fit-mode face — so a real card laid over it
    # should match on all four sides whichever mode a deck is later generated with.
    slot_w, slot_h = SLOT_SIZE_MM
    ox, oy = 20.0, base_y - 20 - slot_h
    c.setLineWidth(0.4)
    c.rect(mm_to_pt(ox), mm_to_pt(oy), mm_to_pt(slot_w), mm_to_pt(slot_h), stroke=1, fill=0)
    c.setFont("Helvetica", 8)
    c.drawString(
        mm_to_pt(ox), mm_to_pt(oy - 6), f"Card outline: {slot_w} x {slot_h} mm (standard card)"
    )

    c.showPage()
    c.save()
    return buf.getvalue()
