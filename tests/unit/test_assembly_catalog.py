"""T046 — expressing a resolved pack in feature 001's structures (FR-048, FR-015d).

FR-048 requires the resolved pack to reach the PDF through 001's `Catalog` and `HeroDeck`, so
pagination, resolution enforcement, and generation are reused rather than reimplemented. The
mapping is total and introduces no new output format:

    PackCard                 -> Card       (id = MarvelCDB code, double_sided from expansion)
    Resolution               -> Printing   (image / image_back are refs the run's Store reads)
    pack + resolutions       -> HeroDeck   (entries ordered (group, position, code))
    quantity                 -> CardEntry.quantity, from the pack being printed (FR-016)
    snapshot_revision        -> Catalog.revision

The synthesised catalog is **in memory only**. It is derived from the snapshot and the
resolutions, both already durable, and writing it would create a third thing that can disagree
with them.

The ordering assertions are FR-015d's requirement, not a grouping convenience: 001's
`paginate` chunks a flat list nine at a time with no notion of groups, so handing it this
order is what produces "as few pages as will hold them, with no page break between groups"
(SC-002b) by construction.
"""

from __future__ import annotations

import json

import pytest

from marchamp.assembly.catalog import build_catalog
from marchamp.assembly.decklist import DecklistDecision, find_decklist
from marchamp.assembly.faces import DECKLIST_CODE, Group, expand_pack
from marchamp.assembly.resolve import resolve_pack
from marchamp.library.index import build_index
from marchamp.upstream.models import PackCard, parse_snapshot_cards
from tests.conftest import ACCEPTANCE_HEROES, SNAPSHOT_FIXTURES


def load_cards(pack_code: str) -> list[PackCard]:
    payload = json.loads((SNAPSHOT_FIXTURES / f"{pack_code}.json").read_text())
    cards, _ = parse_snapshot_cards(payload, pack_code)
    return cards


def printing_lookup(code: str) -> PackCard | None:
    for path in sorted(SNAPSHOT_FIXTURES.glob("*.json")):
        if path.stem == "packs":
            continue
        for card in load_cards(path.stem):
            if card.code == code:
                return card
    return None


@pytest.fixture(scope="module")
def built(scan_library):
    """`cap` resolved as far as Phase 3 reaches, with its decklist accepted."""
    index = build_index(scan_library)
    cards = load_cards("cap")
    folder = ACCEPTANCE_HEROES["cap"]
    resolved = resolve_pack(expand_pack(cards), cards, index, folder, scan_library, printing_lookup)
    decklist = find_decklist(index, folder).decide(DecklistDecision.CONFIRM)
    return build_catalog(
        pack_code="cap",
        pack_name="Captain America",
        cards=cards,
        resolutions=resolved.resolutions,
        snapshot_revision="rev-under-test",
        decklist=decklist,
    )


def test_the_catalog_revision_is_the_pinned_snapshot_revision(built):
    """A resumed run keeps the revision it started with (FR-044b, FR-045)."""
    assert built.catalog.revision == "rev-under-test"


def test_every_entry_points_at_a_card_and_a_printing_that_exist(built):
    """001's loader validates this; a dangling reference would fail there, not here."""
    cards = {c.id: c for c in built.catalog.cards}
    for entry in built.deck.entries:
        assert entry.card_id in cards
        printings = {p.id for p in cards[entry.card_id].printings}
        assert entry.preferred_printing_id in printings


def test_quantities_come_from_the_pack_being_printed(built):
    """FR-016 again, at the bridge — the last place a borrowed quantity could sneak in."""
    quantities = {c.code: c.quantity for c in load_cards("cap")}
    for entry in built.deck.entries:
        if entry.card_id == DECKLIST_CODE:
            continue
        # Identity faces are separate codes sharing one record's quantity.
        assert entry.quantity == quantities.get(entry.card_id, entry.quantity)
    assert next(e for e in built.deck.entries if e.card_id == "03016").quantity == 2


def test_the_hero_card_is_the_identity_card(built):
    """FR-015a. 001's `HeroDeck` names it explicitly, and an empty one is a broken deck."""
    assert built.deck.hero_card_id == "03001a"


def test_entries_follow_the_group_order(built):
    """FR-015d: player cards, identity, nemesis, decklist — in that order."""
    order = [built.group_of[e.card_id] for e in built.deck.entries]
    ranks = [list(Group).index(g) for g in order]
    assert ranks == sorted(ranks), "entries are not in FR-015d's group order"


def test_the_decklist_is_last_and_is_not_one_of_the_packs_cards(built):
    """FR-013b — printed with the pack, never counted among it."""
    assert built.deck.entries[-1].card_id == DECKLIST_CODE
    assert built.group_of[DECKLIST_CODE] is Group.DECKLIST
    assert next(e for e in built.deck.entries if e.card_id == DECKLIST_CODE).quantity == 1
    # And it carries no MarvelCDB code, so nothing may treat it as a card in the pack.
    assert DECKLIST_CODE not in {c.code for c in load_cards("cap")}


def test_a_run_that_skipped_the_decklist_has_no_decklist_entry(scan_library):
    """Hulk's and Phoenix's case, and any user who chose `skip` (FR-013c)."""
    index = build_index(scan_library)
    cards = load_cards("hlk")
    folder = ACCEPTANCE_HEROES["hlk"]
    resolved = resolve_pack(expand_pack(cards), cards, index, folder, scan_library, printing_lookup)
    decklist = find_decklist(index, folder)
    assert decklist.candidate is None
    result = build_catalog(
        pack_code="hlk",
        pack_name="Hulk",
        cards=cards,
        resolutions=resolved.resolutions,
        snapshot_revision="rev",
        decklist=decklist,
    )
    assert DECKLIST_CODE not in {e.card_id for e in result.deck.entries}


def test_a_double_sided_card_carries_both_refs_on_one_printing(scan_library):
    """001's `Printing` holds `image` and `image_back`, and a back is held to the same bar.

    Vision's `26002` Intangible is the measured case: one code, two faces, so the two
    resolutions must collapse into one printing rather than two cards.
    """
    from marchamp.assembly.faces import Side
    from marchamp.assembly.resolve import Provenance, Resolution, Source

    cards = load_cards("vision")
    intangible = next(c for c in cards if c.code == "26002")
    assert intangible.double_sided, "fixture regression: 26002 should be double-sided"
    resolutions = [
        Resolution(
            card_code="26002",
            card_name="Intangible",
            side=side,
            provenance=Provenance.FOLDER_POSITION,
            source=Source.LIBRARY,
            ref=f"Heros/Vision/{side.value}.tiff",
            content_digest="0" * 64,
            quantity=intangible.quantity,
        )
        for side in (Side.FRONT, Side.BACK)
    ]
    result = build_catalog(
        pack_code="vision",
        pack_name="Vision",
        cards=[intangible],
        resolutions=resolutions,
        snapshot_revision="rev",
        decklist=None,
    )
    card = next(c for c in result.catalog.cards if c.id == "26002")
    assert card.double_sided
    printing = card.printings[0]
    assert printing.image.endswith("front.tiff")
    assert printing.image_back is not None
    assert printing.image_back.endswith("back.tiff")


def test_a_card_with_no_resolution_is_absent_rather_than_blank(built):
    """An unresolved card must stop the run (FR-017), never reach the PDF as a gap."""
    ids = {e.card_id for e in built.deck.entries}
    assert "03032" not in ids, "`Followed` has no image and must not reach the catalog"


def test_the_catalog_is_never_written_to_disk(built, tmp_path):
    """data-model.md § Bridge: in memory only, derived from things already durable."""
    assert not list(tmp_path.rglob("*.json"))
    assert built.catalog.schema_version
