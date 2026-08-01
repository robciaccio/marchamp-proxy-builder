"""Ordered faces to positioned slots (FR-007, FR-012, FR-012a, FR-012b, FR-012c)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from marchamp.catalog.models import Catalog
from marchamp.catalog.printings import Resolution, ResolutionOutcome, resolve_entry
from marchamp.layout.geometry import GRID_COLS, GRID_ROWS, PageSize, Slot, page_layout

FACES_PER_PAGE = GRID_ROWS * GRID_COLS


class Side(Enum):
    FRONT = "front"
    BACK = "back"


@dataclass(frozen=True)
class Face:
    card_id: str
    card_name: str
    printing_id: str
    image_ref: str
    side: Side


@dataclass(frozen=True)
class PlacedFace:
    face: Face
    slot: Slot


@dataclass(frozen=True)
class Page:
    index: int
    faces: tuple[Face, ...]
    placed: tuple[PlacedFace, ...]


def face_count(catalog: Catalog, deck_id: str) -> int:
    """Printed faces, counting a double-sided card twice (FR-012c)."""
    deck = catalog.deck(deck_id)
    if deck is None:
        raise KeyError(deck_id)
    total = 0
    for entry in deck.entries:
        card = catalog.card(entry.card_id)
        if card is None:
            raise KeyError(entry.card_id)
        total += entry.quantity * (2 if card.double_sided else 1)
    return total


def expand_faces(
    catalog: Catalog, deck_id: str, image_dir: Path
) -> tuple[list[Face], list[Resolution]]:
    """Expand a deck into an ordered face list, resolving each entry's printing."""
    deck = catalog.deck(deck_id)
    if deck is None:
        raise KeyError(deck_id)

    faces: list[Face] = []
    resolutions: list[Resolution] = []
    for entry in deck.entries:
        res = resolve_entry(catalog, entry, image_dir)
        resolutions.append(res)
        if res.outcome is ResolutionOutcome.UNAVAILABLE or res.printing is None:
            continue
        for _ in range(entry.quantity):
            # A double-sided card contributes both faces, emitted back to back so they are
            # cut and sleeved as a pair (FR-012a, FR-012b).
            faces.append(
                Face(res.card.id, res.card.name, res.printing.id, res.printing.image, Side.FRONT)
            )
            if res.card.double_sided and res.printing.image_back:
                faces.append(
                    Face(
                        res.card.id,
                        res.card.name,
                        res.printing.id,
                        res.printing.image_back,
                        Side.BACK,
                    )
                )
    return faces, resolutions


def paginate(catalog: Catalog, deck_id: str, page_size: PageSize, image_dir: Path) -> list[Page]:
    faces, _ = expand_faces(catalog, deck_id, image_dir)
    layout = page_layout(page_size)
    pages: list[Page] = []
    for i in range(0, len(faces), FACES_PER_PAGE):
        chunk = faces[i : i + FACES_PER_PAGE]
        # The last page is partially filled; no placeholder outlines are added.
        placed = tuple(PlacedFace(f, layout.slots[j]) for j, f in enumerate(chunk))
        pages.append(Page(index=i // FACES_PER_PAGE, faces=tuple(chunk), placed=placed))
    return pages
