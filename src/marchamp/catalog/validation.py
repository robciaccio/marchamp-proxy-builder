"""Catalog validation (FR-005c, FR-005d).

Every check runs and every problem is collected. Stopping at the first error would make a
user fix one thing per run across repeated attempts, which is the failure mode FR-005d
exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from marchamp.assets.store import Store
from marchamp.catalog.models import Catalog


@dataclass(frozen=True)
class Issue:
    kind: str
    detail: str
    card_id: str | None = None
    deck_id: str | None = None
    card_name: str | None = None


@dataclass
class ValidationReport:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def _unsafe(ref: str) -> bool:
    p = Path(ref)
    return p.is_absolute() or ".." in p.parts


def validate(catalog: Catalog, store: Store) -> ValidationReport:
    # Presence is asked of the adapter, never computed from a directory and a ref (FR-004).
    # `_unsafe` stays a path check because it guards the *ref* the catalog authored, which
    # is a different question from where the adapter would put it.
    report = ValidationReport()

    seen_cards: set[str] = set()
    seen_printings: set[str] = set()
    image_owners: dict[str, list[str]] = {}
    # A card is usable if ANY printing's image is present — missing preferred art becomes a
    # stand-in at generation time, not a validation error (FR-005g).
    card_has_usable_printing: dict[str, bool] = {}

    for card in catalog.cards:
        if card.id in seen_cards:
            report.errors.append(
                Issue(
                    "duplicate_card_id",
                    f"Card id {card.id!r} used twice",
                    card.id,
                    card_name=card.name,
                )
            )
        seen_cards.add(card.id)

        usable = False
        for pr in card.printings:
            if pr.id in seen_printings:
                report.errors.append(
                    Issue(
                        "duplicate_printing_id",
                        f"Printing id {pr.id!r} used twice",
                        card.id,
                        card_name=card.name,
                    )
                )
            seen_printings.add(pr.id)

            refs = [pr.image] + ([pr.image_back] if pr.image_back else [])
            for ref in refs:
                if _unsafe(ref):
                    report.errors.append(
                        Issue(
                            "unsafe_image_path",
                            f"unsafe image path {ref!r}",
                            card.id,
                            card_name=card.name,
                        )
                    )
                    continue
                image_owners.setdefault(ref, []).append(pr.id)
                if not store.exists(ref):
                    continue

            front_ok = not _unsafe(pr.image) and store.exists(pr.image)
            back_ok = True
            if card.double_sided:
                if not pr.image_back:
                    report.errors.append(
                        Issue(
                            "missing_back_image",
                            f"is double-sided but printing {pr.id!r} has no back image",
                            card.id,
                            card_name=card.name,
                        )
                    )
                    back_ok = False
                else:
                    back_ok = not _unsafe(pr.image_back) and store.exists(pr.image_back)
            elif pr.image_back:
                report.errors.append(
                    Issue(
                        "unexpected_back_image",
                        f"is not double-sided but printing {pr.id!r} has a back image",
                        card.id,
                        card_name=card.name,
                    )
                )
            usable = usable or (front_ok and back_ok)

        card_has_usable_printing[card.id] = usable
        if not usable:
            report.errors.append(
                Issue(
                    "missing_image_file",
                    "no printing has a usable image on disk",
                    card.id,
                    card_name=card.name,
                )
            )

    for ref, owners in image_owners.items():
        if len(owners) > 1:
            # Usually a copy-paste mistake, but legitimate often enough not to block.
            report.warnings.append(
                Issue("shared_image_file", f"{len(owners)} printings share image {ref!r}")
            )

    for deck in catalog.decks:
        if catalog.card(deck.hero_card_id) is None:
            report.errors.append(
                Issue(
                    "unknown_card_reference",
                    f"Deck {deck.name!r} hero card not found",
                    deck_id=deck.id,
                )
            )
        for entry in deck.entries:
            card = catalog.card(entry.card_id)
            if card is None:
                report.errors.append(
                    Issue(
                        "unknown_card_reference",
                        f"Deck {deck.name!r} references unknown card {entry.card_id!r}",
                        entry.card_id,
                        deck.id,
                    )
                )
                continue
            if entry.quantity < 1:
                report.errors.append(
                    Issue(
                        "invalid_quantity",
                        f"quantity must be at least 1, got {entry.quantity}",
                        card.id,
                        deck.id,
                        card_name=card.name,
                    )
                )
            if card.printing(entry.preferred_printing_id) is None:
                report.errors.append(
                    Issue(
                        "printing_card_mismatch",
                        f"preferred printing {entry.preferred_printing_id!r} is not a "
                        "printing of this card",
                        card.id,
                        deck.id,
                        card_name=card.name,
                    )
                )

    return report
