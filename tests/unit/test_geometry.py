"""T025 — print geometry (FR-008a, FR-008b, FR-009, FR-009a, FR-011, FR-013).

The constitution requires these values be asserted, not inspected. Geometry is pure, so it
is asserted here in millimetres; the generated PDF is asserted separately in integration.
"""

from __future__ import annotations

import pytest

from marchamp.layout.geometry import (
    GRID_COLS,
    GRID_ROWS,
    SLOT_SIZE_MM,
    PageSize,
    cut_guides,
    mm_to_pt,
    page_layout,
)

TOL = 0.5  # FR-009 tolerance, in mm


def test_slot_is_standard_card_size():
    assert pytest.approx((63.5, 88.9)) == SLOT_SIZE_MM


def test_grid_is_three_by_three():
    assert (GRID_ROWS, GRID_COLS) == (3, 3)


def test_mm_to_pt_boundary_is_exact():
    assert mm_to_pt(25.4) == pytest.approx(72.0)


@pytest.mark.parametrize(
    ("page", "w_mm", "h_mm"),
    [(PageSize.LETTER, 215.9, 279.4), (PageSize.A4, 210.0, 297.0)],
)
def test_page_dimensions_are_portrait(page, w_mm, h_mm):
    lay = page_layout(page)
    assert lay.page_w_mm == pytest.approx(w_mm)
    assert lay.page_h_mm == pytest.approx(h_mm)
    assert lay.page_h_mm > lay.page_w_mm  # FR-008b


@pytest.mark.parametrize(
    ("page", "mx", "my"),
    [(PageSize.LETTER, 12.70, 6.35), (PageSize.A4, 9.75, 15.15)],
)
def test_margins_are_centred_and_positive(page, mx, my):
    lay = page_layout(page)
    assert lay.margin_x_mm == pytest.approx(mx, abs=0.01)
    assert lay.margin_y_mm == pytest.approx(my, abs=0.01)
    assert lay.margin_x_mm > 0 and lay.margin_y_mm > 0


@pytest.mark.parametrize("page", list(PageSize))
def test_nine_slots_fit_within_the_page(page):
    lay = page_layout(page)
    assert len(lay.slots) == 9
    for s in lay.slots:
        assert s.w_mm == pytest.approx(63.5, abs=TOL)
        assert s.h_mm == pytest.approx(88.9, abs=TOL)
        assert s.x_mm >= -1e-9
        assert s.y_mm >= -1e-9
        assert s.x_mm + s.w_mm <= lay.page_w_mm + 1e-9
        assert s.y_mm + s.h_mm <= lay.page_h_mm + 1e-9


@pytest.mark.parametrize("page", list(PageSize))
def test_slots_do_not_overlap(page):
    slots = page_layout(page).slots
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            separated = (
                a.x_mm + a.w_mm <= b.x_mm + 1e-9
                or b.x_mm + b.w_mm <= a.x_mm + 1e-9
                or a.y_mm + a.h_mm <= b.y_mm + 1e-9
                or b.y_mm + b.h_mm <= a.y_mm + 1e-9
            )
            assert separated


@pytest.mark.parametrize("page", list(PageSize))
def test_no_cut_guide_enters_a_slot(page):
    # FR-013 — a guide inside a slot would print across a card face.
    lay = page_layout(page)
    for gx1, gy1, gx2, gy2 in cut_guides(lay):
        for s in lay.slots:
            inside_x = s.x_mm < gx1 < s.x_mm + s.w_mm and s.x_mm < gx2 < s.x_mm + s.w_mm
            inside_y = s.y_mm < gy1 < s.y_mm + s.h_mm and s.y_mm < gy2 < s.y_mm + s.h_mm
            assert not (inside_x and inside_y)


def test_slot_size_is_a_single_configurable_value():
    # FR-009a — changing the card size must be a one-place change.
    from marchamp.layout import geometry

    assert geometry.SLOT_SIZE_MM is geometry.page_layout(PageSize.LETTER).slot_size_mm
