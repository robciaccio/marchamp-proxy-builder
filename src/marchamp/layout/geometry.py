"""Print geometry in millimetres (FR-008a, FR-008b, FR-009, FR-009a, FR-011, FR-013).

Physical units are the source of truth. Points appear only at the single conversion
boundary below, so a rounding mistake cannot quietly change what prints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# FR-009a: the one place card size is defined. Changing it is a one-line change.
SLOT_SIZE_MM: tuple[float, float] = (63.5, 88.9)

GRID_ROWS = 3
GRID_COLS = 3

_MM_PER_INCH = 25.4
_PT_PER_INCH = 72.0


class PageSize(Enum):
    LETTER = (215.9, 279.4)
    A4 = (210.0, 297.0)


def mm_to_pt(mm: float) -> float:
    return mm / _MM_PER_INCH * _PT_PER_INCH


@dataclass(frozen=True)
class Slot:
    row: int
    col: int
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float


@dataclass(frozen=True)
class PageLayout:
    page_size: PageSize
    page_w_mm: float
    page_h_mm: float
    margin_x_mm: float
    margin_y_mm: float
    slot_size_mm: tuple[float, float]
    slots: tuple[Slot, ...]


def page_layout(page_size: PageSize) -> PageLayout:
    """A fixed 3x3 grid, centred, identical for both page sizes (FR-011)."""
    page_w, page_h = page_size.value
    slot_w, slot_h = SLOT_SIZE_MM
    grid_w = GRID_COLS * slot_w
    grid_h = GRID_ROWS * slot_h
    margin_x = (page_w - grid_w) / 2
    margin_y = (page_h - grid_h) / 2
    if margin_x < 0 or margin_y < 0:
        raise ValueError(f"grid {grid_w}x{grid_h}mm does not fit {page_size.name}")

    slots = tuple(
        Slot(
            row=r,
            col=c,
            x_mm=margin_x + c * slot_w,
            y_mm=margin_y + r * slot_h,
            w_mm=slot_w,
            h_mm=slot_h,
        )
        for r in range(GRID_ROWS)
        for c in range(GRID_COLS)
    )
    return PageLayout(page_size, page_w, page_h, margin_x, margin_y, SLOT_SIZE_MM, slots)


def cut_guides(
    layout: PageLayout, extent_mm: float = 4.0
) -> list[tuple[float, float, float, float]]:
    """Marks at every slot boundary, drawn in the margins only.

    Cards sit edge to edge, so there is no gutter to mark in — interior cut lines are
    indicated by marks that extend inward from the page margins. Nothing is ever drawn
    inside a slot, so no guide can cross a card face (FR-013).
    """
    lines: list[tuple[float, float, float, float]] = []
    slot_w, slot_h = layout.slot_size_mm

    xs = [layout.margin_x_mm + i * slot_w for i in range(GRID_COLS + 1)]
    ys = [layout.margin_y_mm + i * slot_h for i in range(GRID_ROWS + 1)]
    grid_top = layout.margin_y_mm + GRID_ROWS * slot_h
    grid_right = layout.margin_x_mm + GRID_COLS * slot_w

    for x in xs:
        lines.append((x, max(0.0, layout.margin_y_mm - extent_mm), x, layout.margin_y_mm))
        lines.append((x, grid_top, x, min(layout.page_h_mm, grid_top + extent_mm)))
    for y in ys:
        lines.append((max(0.0, layout.margin_x_mm - extent_mm), y, layout.margin_x_mm, y))
        lines.append((grid_right, y, min(layout.page_w_mm, grid_right + extent_mm), y))
    return lines
