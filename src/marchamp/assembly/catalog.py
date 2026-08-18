"""Expressing a resolved pack in feature 001's structures (FR-048, FR-015d).

FR-048 requires the resolved pack to reach the PDF through 001's `Catalog` and `HeroDeck`, so
pagination, resolution enforcement, and generation are reused rather than reimplemented. This
module is the whole of that bridge, and it is deliberately the only place that knows both
vocabularies.

    PackCard             -> Card       id = the MarvelCDB code; `double_sided` from expansion
    Resolution           -> Printing   `image` / `image_back` are refs the run's Store reads
    pack + resolutions   -> HeroDeck   entries ordered (group, position, code)
    quantity             -> CardEntry.quantity, from the pack being printed (FR-016)
    snapshot_revision    -> Catalog.revision

**In memory only, and never written.** It is derived from the snapshot and the resolutions,
both of which are already durable; a third copy on disk could only ever disagree with them.

**Ordering is FR-015d's requirement, not tidiness.** 001's `paginate` chunks a flat list nine
at a time and has no notion of groups, so producing player cards, identity, nemesis, decklist
*in that order* is exactly what yields "as few pages as will hold them, with no page break
between groups" (SC-002b). What keeps the groups distinguishable for the user is the report,
not the layout (FR-015e).

**A double-sided card is one `Card` with one `Printing`, not two.** Its two resolutions
collapse into `image` and `image_back`, because 001 already prints a back immediately after
its front so the pair is cut and sleeved together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from marchamp.assembly.decklist import DecklistState
from marchamp.assembly.faces import DECKLIST_CODE, GROUP_ORDER, Group, Side, classify
from marchamp.assembly.resolve import Provenance, Resolution
from marchamp.catalog.models import Card, CardEntry, Catalog, HeroDeck, Printing
from marchamp.upstream.models import PackCard

#: The only catalog schema 001's loader accepts. Synthesised catalogs are handed to the same
#: code paths as authored ones, so they declare the same version.
CATALOG_SCHEMA_VERSION = "1"

#: The decklist card's name in the deck, and the one place it is written for a user to read.
DECKLIST_NAME = "Deck list"


@dataclass
class BuiltCatalog:
    catalog: Catalog
    deck: HeroDeck
    #: Which FR-015 group each card ended up in. The layout deliberately does not record
    #: this — no page break separates the groups — so the report reads it from here.
    group_of: dict[str, Group] = field(default_factory=dict)


def _printing_id(pack_code: str, card_code: str) -> str:
    """Stable and derived, never a counter.

    001's `Printing.id` is only ever used to point a `CardEntry` at one printing of a card.
    Deriving it means two runs of the same pack produce byte-identical structures, which is
    what FR-045's determinism is asserted on.
    """
    return f"{pack_code}:{card_code}"


def build_catalog(
    pack_code: str,
    pack_name: str,
    cards: Sequence[PackCard],
    resolutions: Sequence[Resolution],
    snapshot_revision: str,
    decklist: DecklistState | None,
) -> BuiltCatalog | None:
    """Turn a pack and its resolutions into a one-deck catalog 001 can render.

    Only cards that actually resolved reach the output. A card with no image must stop the
    run (FR-017); letting it through as a blank would print a pack that is quietly short,
    which is the failure US2 exists to prevent.

    **`None` when nothing resolved**, which is a real case and not a defensive branch: a
    library holding only the *back* of the one card it holds at all produces no printable
    entry, and 001's `HeroDeck` requires at least one. Raising here would replace a report
    naming every missing card with a validation error naming none of them — the opposite of
    FR-037 and SC-008.
    """
    by_card = _group_resolutions(resolutions)
    record_of = {c.code: c for c in cards}

    built_cards: list[Card] = []
    entries: list[CardEntry] = []
    group_of: dict[str, Group] = {}

    for card_code, sides in _ordered(by_card, record_of):
        record = _record_for(card_code, record_of)
        front = sides.get(Side.FRONT)
        if front is None:
            # A back with no front is not printable and is not silently half-printed.
            continue
        back = sides.get(Side.BACK)
        printing_id = _printing_id(pack_code, card_code)

        built_cards.append(
            Card(
                id=card_code,
                name=front.card_name or (record.name if record else card_code),
                double_sided=back is not None,
                printings=[
                    Printing(
                        id=printing_id,
                        pack=pack_code,
                        image=front.ref,
                        image_back=back.ref if back else None,
                        number=str(record.position) if record else None,
                    )
                ],
            )
        )
        entries.append(
            CardEntry(
                card_id=card_code,
                preferred_printing_id=printing_id,
                # FR-016: the pack being printed decides, never the printing that lent the
                # image. The resolution carries it so this cannot be re-derived wrongly.
                quantity=front.quantity,
            )
        )
        group_of[card_code] = classify(record) if record else Group.PLAYER

    if decklist is not None and decklist.printed and decklist.chosen_ref:
        printing_id = _printing_id(pack_code, DECKLIST_CODE)
        built_cards.append(
            Card(
                id=DECKLIST_CODE,
                name=DECKLIST_NAME,
                double_sided=False,
                printings=[Printing(id=printing_id, pack=pack_code, image=decklist.chosen_ref)],
            )
        )
        # Always one copy, and never counted among the pack's cards (FR-013b, FR-018).
        entries.append(
            CardEntry(card_id=DECKLIST_CODE, preferred_printing_id=printing_id, quantity=1)
        )
        group_of[DECKLIST_CODE] = Group.DECKLIST

    if not entries:
        return None

    deck = HeroDeck(
        id=pack_code,
        name=pack_name,
        hero_card_id=_hero_card_id(entries, group_of),
        entries=entries,
    )
    catalog = Catalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        cards=built_cards,
        decks=[deck],
        revision=snapshot_revision,
    )
    return BuiltCatalog(catalog=catalog, deck=deck, group_of=group_of)


def _group_resolutions(
    resolutions: Sequence[Resolution],
) -> dict[str, dict[Side, Resolution]]:
    """By card, then by side — skipping cards the user chose to print without (FR-030).

    An omitted resolution carries no ref, so letting one through would add a card whose
    image is the empty string: a phantom entry that counts toward `cards_printed` and fails
    at render time. FR-030b requires the opposite — the omission is named in the report and
    absent from the document.
    """
    grouped: dict[str, dict[Side, Resolution]] = {}
    for resolution in resolutions:
        if resolution.provenance is Provenance.OMITTED:
            continue
        grouped.setdefault(resolution.card_code, {})[resolution.side] = resolution
    return grouped


def _record_for(card_code: str, record_of: dict[str, PackCard]) -> PackCard | None:
    """The pack record behind a card code, following a linked code back to its record.

    An identity spans several codes and one record — `03001b` has no record of its own, only
    `03001a` does — so a direct lookup finds nothing for half the identity faces and would
    file them as ungrouped player cards.
    """
    direct = record_of.get(card_code)
    if direct is not None:
        return direct
    for record in record_of.values():
        if card_code in record.linked_codes:
            return record
    return None


def _ordered(
    by_card: dict[str, dict[Side, Resolution]], record_of: dict[str, PackCard]
) -> list[tuple[str, dict[Side, Resolution]]]:
    """FR-015d's order: group, then position, then code.

    Sorted rather than taken in resolution order so the same pack always produces the same
    document, whatever order the cascade happened to answer in (Principle V, FR-045).
    """

    def key(item: tuple[str, dict[Side, Resolution]]) -> tuple[int, int, str]:
        card_code, _sides = item
        record = _record_for(card_code, record_of)
        group = classify(record) if record else Group.PLAYER
        return (GROUP_ORDER.index(group), record.position if record else 0, card_code)

    return sorted(by_card.items(), key=key)


def _hero_card_id(entries: Sequence[CardEntry], group_of: dict[str, Group]) -> str:
    """FR-015a. 001's `HeroDeck` names the identity card explicitly.

    Falls back to the first entry only so a pack whose identity card failed to resolve still
    produces a well-formed structure — the run stops on that card anyway (FR-017), and
    raising here would replace a report naming the missing card with a validation error
    naming nothing.
    """
    for entry in entries:
        if group_of.get(entry.card_id) is Group.IDENTITY:
            return entry.card_id
    return entries[0].card_id if entries else DECKLIST_CODE
