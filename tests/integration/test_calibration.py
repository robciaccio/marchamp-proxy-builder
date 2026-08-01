"""T058 — calibration page (FR-023, User Story 3)."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from marchamp.layout.geometry import SLOT_SIZE_MM, PageSize
from marchamp.render.calibration import RULER_MM, calibration_pdf

PT_PER_MM = 72.0 / 25.4
TOL_PT = 0.5 * PT_PER_MM


@pytest.mark.parametrize("page_size", list(PageSize))
def test_single_page_at_the_requested_size(page_size):
    reader = PdfReader(io.BytesIO(calibration_pdf(page_size)))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert float(box.width) == pytest.approx(page_size.value[0] * PT_PER_MM, abs=TOL_PT)
    assert float(box.height) == pytest.approx(page_size.value[1] * PT_PER_MM, abs=TOL_PT)


def _text() -> str:
    # Page text is compressed in the PDF stream, so it must be extracted, not grepped.
    return PdfReader(io.BytesIO(calibration_pdf())).pages[0].extract_text()


def test_outline_is_the_slot_not_a_fit_mode_face():
    # A real card laid over it must match on all four sides whichever fit mode a deck is
    # later generated with, so the outline is always 63.5 x 88.9 mm.
    assert f"{SLOT_SIZE_MM[0]} x {SLOT_SIZE_MM[1]} mm" in _text()


def test_states_the_ruler_length_so_it_can_be_measured():
    assert str(RULER_MM) in _text()


def test_tells_the_user_to_disable_scaling():
    # The whole point: consumer printers rescale silently unless told not to.
    assert "100%" in _text()


def test_calibration_is_deterministic():
    assert calibration_pdf() == calibration_pdf()
