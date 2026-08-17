"""What the run tells the user about itself (FR-015e, FR-018, SC-002b, SC-006j).

FR-015d packs the four groups into as few pages as will hold them with **no page break
between them**, so a printed page routinely carries the last player cards and the first
nemesis cards. That makes the report — not the layout — the thing that tells the groups
apart, and the thing a user sorts a stack of cut cards by without recognising the cards on
sight (FR-015e, SC-002b).

It lives on the run record rather than only in the response that produced it, so an
incomplete pack is still legible as incomplete on a later visit (FR-030b).

**Phase 3 fills the parts US1 can know.** The sections US2 owns — unused and uninterpretable
files, conflicts, low-resolution warnings, omissions — are declared here with their contract
shape and left empty, because the contract test compares the whole response shape and a field
that appears later would be undeclared surface now. T059-T070 fill them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from marchamp.assembly.catalog import BuiltCatalog
from marchamp.assembly.decklist import DecklistState
from marchamp.assembly.faces import Group, card_count, face_count
from marchamp.assembly.resolve import Resolution
from marchamp.upstream.models import PackCard


@dataclass
class AssemblyReport:
    pack_code: str | None = None
    pack_name: str | None = None
    pack_source: str = "identified"
    snapshot_revision: str | None = None
    snapshot_stale: bool = False
    #: FR-018's comparison, **in cards** — a double-sided card is one card and two faces.
    #: No expected total is asserted and none is warned on: pack sizes vary, and the
    #: pre-built decks this feature was respecified around measured 40, 41, and 42.
    cards_printed: int = 0
    cards_in_pack: int = 0
    faces_printed: int = 0
    page_count: int | None = None
    #: SC-006j — a pack printed without a decklist card is never indistinguishable from one
    #: printed with it.
    decklist_printed: bool = False
    #: Where to get one when the folder held none (FR-013c). Shown, never fetched.
    decklist_source_url: str | None = None
    resolutions: list[dict[str, Any]] = field(default_factory=list)
    # ---- US2's sections (T059-T070). Declared for the contract, filled in Phase 4.
    omitted: list[dict[str, Any]] = field(default_factory=list)
    unused_files: list[dict[str, Any]] = field(default_factory=list)
    uninterpretable_files: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    low_resolution: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "pack_code": self.pack_code,
            "pack_name": self.pack_name,
            "pack_source": self.pack_source,
            "snapshot_revision": self.snapshot_revision,
            "snapshot_stale": self.snapshot_stale,
            "cards_printed": self.cards_printed,
            "cards_in_pack": self.cards_in_pack,
            "faces_printed": self.faces_printed,
            "page_count": self.page_count,
            "decklist_printed": self.decklist_printed,
            "decklist_source_url": self.decklist_source_url,
            "resolutions": self.resolutions,
            "omitted": self.omitted,
            "unused_files": self.unused_files,
            "uninterpretable_files": self.uninterpretable_files,
            "conflicts": self.conflicts,
            "low_resolution": self.low_resolution,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> AssemblyReport:
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


def build_report(
    pack_code: str | None,
    pack_name: str | None,
    pack_source: str,
    cards: Sequence[PackCard],
    resolutions: Sequence[Resolution],
    built: BuiltCatalog | None,
    decklist: DecklistState | None,
    snapshot_revision: str | None,
    snapshot_stale: bool = False,
    page_count: int | None = None,
) -> AssemblyReport:
    """Assemble the report from what the run resolved.

    `cards_printed` counts what the *entries* say, not what the pack listing says, so a run
    that omitted a card reports fewer than `cards_in_pack` rather than claiming the pack is
    complete. The decklist is excluded from both, because it is not one of the pack's cards
    (FR-013b, FR-018).
    """
    group_of = built.group_of if built else {}
    printed_cards = 0
    printed_faces = 0
    if built is not None:
        for entry in built.deck.entries:
            if group_of.get(entry.card_id) is Group.DECKLIST:
                continue
            card = built.catalog.card(entry.card_id)
            printed_cards += entry.quantity
            printed_faces += entry.quantity * (2 if card and card.double_sided else 1)

    return AssemblyReport(
        pack_code=pack_code,
        pack_name=pack_name,
        pack_source=pack_source,
        snapshot_revision=snapshot_revision,
        snapshot_stale=snapshot_stale,
        cards_printed=printed_cards,
        cards_in_pack=card_count(cards),
        faces_printed=printed_faces,
        page_count=page_count,
        decklist_printed=bool(decklist and decklist.printed),
        # Offered whenever no decklist card is being printed, which is the only time the
        # user needs somewhere to go for one (FR-013c, SC-006j).
        decklist_source_url=(
            None
            if decklist and decklist.printed
            else (decklist.hall_of_heroes_url if decklist else None)
        ),
        resolutions=[
            {
                "card_code": r.card_code,
                "card_name": r.card_name,
                "side": r.side.value,
                "group": group_of.get(r.card_code, Group.PLAYER).value,
                "provenance": r.provenance.value,
                "source": r.source.value,
                "file": r.original_filename or r.ref,
                "note": r.note,
            }
            # Sorted so the same run always renders the same report (Principle V).
            for r in sorted(resolutions, key=lambda r: (r.card_code, r.side.value))
        ],
    )


def unexpected_face_count(cards: Sequence[PackCard]) -> int:
    """The face count the pack listing implies, for Phase 4's comparison."""
    return face_count(cards)
