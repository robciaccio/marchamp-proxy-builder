"""T048 — the PDF carries the groups in order, packed tight (FR-015d, SC-002a, SC-002b).

FR-015d asks for two things that pull against each other: the four groups in a fixed order,
and **as few pages as the card count allows with no page break between groups**. A page
carrying the last player cards and the first nemesis cards is the intended result, not a
defect — what keeps the groups distinguishable for the user is the report (FR-015e).

001's `paginate` chunks a flat list nine at a time and has no notion of groups at all, so
this is satisfied by *ordering the list*, and these tests assert that the ordering survives
all the way into the document rather than only in `build_catalog`'s output.

**Why these render a partial pack.** Cascade steps 2 and 4 are US3's (Phase 5), so no hero
resolves completely yet. Layout is independent of completeness: the entries that resolved are
ordered and paginated exactly as a full pack's would be, and rendering them is a true test of
FR-015d. What is *not* tested here is a full pack's page count, which needs Phase 5 and is
T115's.
"""

from __future__ import annotations

import json

import pytest

from marchamp.assembly.catalog import build_catalog
from marchamp.assembly.decklist import DecklistDecision, find_decklist
from marchamp.assembly.faces import GROUP_ORDER, Group, expand_pack
from marchamp.assembly.resolve import resolve_pack
from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import paginate
from marchamp.library.index import build_index
from marchamp.render.document import FitMode, compose
from marchamp.upstream.models import PackCard, parse_snapshot_cards
from tests.conftest import ACCEPTANCE_HEROES, SNAPSHOT_FIXTURES

#: 001's grid: three by three, nine card faces to a page.
FACES_PER_PAGE = 9


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


def assemble(scan_library, pack_code: str, accept_decklist: bool = True):
    index = build_index(scan_library)
    cards = load_cards(pack_code)
    folder = ACCEPTANCE_HEROES[pack_code]
    resolved = resolve_pack(expand_pack(cards), cards, index, folder, scan_library, printing_lookup)
    decklist = find_decklist(index, folder)
    if accept_decklist and decklist.candidate is not None:
        decklist = decklist.decide(DecklistDecision.CONFIRM)
    return build_catalog(
        pack_code=pack_code,
        pack_name=pack_code,
        cards=cards,
        resolutions=resolved.resolutions,
        snapshot_revision="rev",
        decklist=decklist,
    )


def test_a_hero_with_a_decklist_scan_carries_four_groups(scan_library):
    """FR-013c's happy path — eight of the ten acceptance folders."""
    built = assemble(scan_library, "cap")
    assert set(built.group_of.values()) == set(GROUP_ORDER)


def test_a_hero_without_a_decklist_scan_carries_three(scan_library):
    """Hulk's real case. A run over Hulk reporting a decklist card would be silently wrong."""
    built = assemble(scan_library, "hlk")
    assert set(built.group_of.values()) == {Group.PLAYER, Group.IDENTITY, Group.NEMESIS}


def test_the_faces_reach_the_pdf_in_group_order(scan_library):
    """The assertion this file exists for: ordering survives pagination.

    Read off the paginated pages rather than the deck entries, because `paginate` is where
    the order could be lost and `build_catalog`'s own test cannot see that far.
    """
    built = assemble(scan_library, "cap")
    store = LocalDirectoryStore(scan_library)
    pages = paginate(built.catalog, built.deck.id, PageSize.LETTER, store)

    ranks = [
        GROUP_ORDER.index(built.group_of[placed.face.card_id])
        for page in pages
        for placed in page.placed
    ]
    assert ranks == sorted(ranks), "faces do not reach the PDF in FR-015d's group order"


def test_pages_are_packed_with_no_break_between_groups(scan_library):
    """SC-002b, and the half of FR-015d that is easy to get wrong in the other direction.

    Starting each group on a fresh page would be tidier and would waste paper, which is the
    cost this feature is minimising. Every page but the last must therefore be full.
    """
    built = assemble(scan_library, "cap")
    store = LocalDirectoryStore(scan_library)
    pages = paginate(built.catalog, built.deck.id, PageSize.LETTER, store)

    assert len(pages) > 1, "this assertion is vacuous on a single page"
    for page in pages[:-1]:
        assert len(page.placed) == FACES_PER_PAGE
    assert 0 < len(pages[-1].placed) <= FACES_PER_PAGE


def test_a_page_carrying_two_groups_is_the_intended_result(scan_library):
    """Stated positively, because it looks like a bug to anyone reading the PDF cold."""
    built = assemble(scan_library, "cap")
    store = LocalDirectoryStore(scan_library)
    pages = paginate(built.catalog, built.deck.id, PageSize.LETTER, store)
    mixed = [
        page for page in pages if len({built.group_of[p.face.card_id] for p in page.placed}) > 1
    ]
    assert mixed, "no page mixes groups, so the groups are being padded onto fresh pages"


@pytest.mark.parametrize("page_size", [PageSize.LETTER, PageSize.A4])
def test_the_document_renders(scan_library, page_size):
    """End to end into bytes, so a layout that paginates but cannot compose still fails."""
    built = assemble(scan_library, "cap")
    store = LocalDirectoryStore(scan_library)
    pages = paginate(built.catalog, built.deck.id, page_size, store)
    data = compose(pages, page_size, FitMode.CROP, store)
    assert data.startswith(b"%PDF-")
    assert len(data) > 1000
