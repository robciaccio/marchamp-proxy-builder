"""Preferred printing resolution and deterministic stand-ins (FR-005f–j)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from marchamp.catalog.models import Card, CardEntry, Catalog, Printing


class ResolutionOutcome(Enum):
    PREFERRED = "preferred"
    SUBSTITUTED = "substituted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Substitution:
    """One card printed with art from a pack other than its deck's own.

    The card and its rules are correct; only the artwork differs. Not a failure — but never
    silent (FR-005h).
    """

    card_id: str
    card_name: str
    wanted_printing_id: str
    wanted_pack: str | None
    used_printing_id: str
    used_pack: str | None


@dataclass(frozen=True)
class Resolution:
    card: Card
    printing: Printing | None
    outcome: ResolutionOutcome
    substitution: Substitution | None = None


def _usable(printing: Printing, card: Card, image_dir: Path) -> bool:
    if not (image_dir / printing.image).is_file():
        return False
    if card.double_sided:
        return bool(printing.image_back) and (image_dir / printing.image_back).is_file()
    return True


def resolve_entry(catalog: Catalog, entry: CardEntry, image_dir: Path) -> Resolution:
    """Prefer the deck's own pack art; fall back deterministically; never invent a card."""
    card = catalog.card(entry.card_id)
    if card is None:
        raise KeyError(entry.card_id)
    image_dir = Path(image_dir)

    preferred = card.printing(entry.preferred_printing_id)
    if preferred is not None and _usable(preferred, card, image_dir):
        return Resolution(card, preferred, ResolutionOutcome.PREFERRED)

    # Ordered by printing id, never by directory listing or hash iteration, so the same
    # catalog and the same files always choose the same stand-in (FR-005j).
    for candidate in sorted(card.printings, key=lambda p: p.id):
        if candidate.id == entry.preferred_printing_id:
            continue
        if _usable(candidate, card, image_dir):
            return Resolution(
                card,
                candidate,
                ResolutionOutcome.SUBSTITUTED,
                Substitution(
                    card_id=card.id,
                    card_name=card.name,
                    wanted_printing_id=entry.preferred_printing_id,
                    wanted_pack=preferred.pack if preferred else None,
                    used_printing_id=candidate.id,
                    used_pack=candidate.pack,
                ),
            )

    # Fallback covers missing art, never a missing card (FR-005i).
    return Resolution(card, None, ResolutionOutcome.UNAVAILABLE)
