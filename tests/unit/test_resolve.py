"""T043, T045 — the resolution cascade, steps 1 and 3 (FR-014, FR-016, FR-020, FR-022, FR-024).

Phase 3 builds two of the six steps. Step 1 (`folder_position`) is the common case and the
only provenance that is *not* reported as a substitution. Step 3 (`reprint`) is the one that
makes a hero pack printable at all: a pack's aspect and basic cards are frequently reprints
whose scan lives in whichever pack first printed them, so without it `cap` is eight physical
cards short. Steps 2 and 4 are US3's (Phase 5); step 5 is US4's; step 6 is FR-030's.

The measured shape of `cap` against the fixture library, which is what these tests encode:

    34 records; 24 resolve by folder position and 7 by reprint — 6 into the Core Set
    (8 physical copies) and 1 backwards into Star-Lord's pack — leaving 3 for later
    steps. `Enraged` and `Expert Defense` sit under the root `Aspects/` tree with no
    usable position and need step 4's name match (Phase 5). `Followed` is unresolvable
    *against this fixture only*: it resolves by reprint into Spider-Ham's pack, whose
    folder T005 does not derive because Spider-Ham is not one of the ten acceptance
    heroes. Driven against the real library it resolves here and now.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marchamp.assembly.faces import Side, expand_pack
from marchamp.assembly.resolve import Provenance, ResolveResult, Source, resolve_pack
from marchamp.library.index import build_index
from marchamp.upstream.models import PackCard, parse_snapshot_cards
from tests.conftest import ACCEPTANCE_HEROES, SNAPSHOT_FIXTURES


def load_cards(pack_code: str) -> list[PackCard]:
    payload = json.loads((SNAPSHOT_FIXTURES / f"{pack_code}.json").read_text())
    cards, _warnings = parse_snapshot_cards(payload, pack_code)
    return cards


def printing_lookup(code: str) -> PackCard | None:
    """Find one card by code across every committed snapshot.

    Stands in for the prefix→pack map research R4 describes. What matters to the cascade is
    only that *some* other printing can be looked up by code; where it is fetched from is the
    service's problem, which is why `resolve_pack` takes this as a parameter.
    """
    for path in sorted(SNAPSHOT_FIXTURES.glob("*.json")):
        if path.stem == "packs":
            continue
        for card in load_cards(path.stem):
            if card.code == code:
                return card
    return None


@pytest.fixture(scope="module")
def cap_result(scan_library) -> ResolveResult:
    index = build_index(scan_library)
    cards = load_cards("cap")
    return resolve_pack(
        expand_pack(cards), cards, index, ACCEPTANCE_HEROES["cap"], scan_library, printing_lookup
    )


# ------------------------------------------------------------- step 1: folder_position


def test_the_identity_faces_resolve_to_their_own_suffixed_files(cap_result):
    """`03001a`/`03001b` are two distinct codes, and the library suffixes them `_1a`/`_1b`.

    Both are position 1, so the suffix is the only thing separating them. Resolving them to
    the same file would print the hero's front twice and lose the alter-ego entirely.
    """
    by_code = {r.card_code: r for r in cap_result.resolutions}
    front, back = by_code["03001a"], by_code["03001b"]
    assert front.ref.endswith("Steve Rogers_Captain America_Hero_1a.tiff")
    assert back.ref.endswith("Steve Rogers_Captain America_Alter-Ego_1b.tiff")
    assert front.provenance is Provenance.FOLDER_POSITION


def test_the_nemesis_set_resolves_from_a_subfolder(cap_result):
    """FR-015b. The nemesis cards sit in `Captain America Nemesis/`, not the hero folder.

    A lookup restricted to the named directory finds none of them, and the run would be
    five cards short with nothing in the report pointing at the reason.
    """
    by_code = {r.card_code: r for r in cap_result.resolutions}
    for code in ("03027", "03028", "03029", "03030"):
        assert code in by_code, f"nemesis card {code} did not resolve"
        assert "Nemesis/" in by_code[code].ref
        assert by_code[code].provenance is Provenance.FOLDER_POSITION


def test_a_folder_position_match_is_not_reported_as_a_substitution(cap_result):
    """FR-024, SC-005: everything *except* step 1 must be visible to the user."""
    by_code = {r.card_code: r for r in cap_result.resolutions}
    assert not by_code["03002"].substituted
    assert by_code["03016"].substituted


def test_every_resolution_carries_a_ref_relative_to_the_library(cap_result, scan_library):
    """FR-009 — no path from outside the named library root is ever retained."""
    for resolution in cap_result.resolutions:
        assert not Path(resolution.ref).is_absolute()
        assert str(scan_library) not in resolution.ref
        assert (Path(scan_library) / resolution.ref).is_file()


def test_every_resolution_carries_a_content_digest(cap_result):
    """Feeds FR-026h's reuse key: a run rebuilds when a card resolves to different bytes."""
    for resolution in cap_result.resolutions:
        assert len(resolution.content_digest) == 64
        assert resolution.source is Source.LIBRARY


# --------------------------------------------------------------------- step 3: reprint


#: Measured against the fixture library. Each `cap` card, the Core Set card it duplicates, and
#: the file the reprint step must borrow. Written out rather than derived so the test cannot
#: agree with a resolver bug by sharing its logic.
CAP_REPRINTS = {
    "03016": ("01071", "Core Set/Aspects/Leadership/Leadership_Make the Call_Event_71.tiff"),
    "03018": ("01072", "Core Set/Aspects/Leadership/Leadership_The Power of Leadership_72.tiff"),
    "03020": ("01083", "Core Set/Aspects/Basic-Grey/Grey_Mockingbird_Ally_83.tiff"),
    "03021": ("01088", "Core Set/Aspects/Basic-Grey/Grey_Energy_Resource_88.tiff"),
    "03022": ("01089", "Core Set/Aspects/Basic-Grey/Grey_Genius_Resource_89.tiff"),
    "03023": ("01090", "Core Set/Aspects/Basic-Grey/Grey_Strength_Resource_90.tiff"),
}


@pytest.mark.parametrize(("code", "expected"), sorted(CAP_REPRINTS.items()))
def test_a_reprint_borrows_the_other_printings_image(code, expected, cap_result):
    _duplicate_of, ref = expected
    by_code = {r.card_code: r for r in cap_result.resolutions}
    assert code in by_code, f"{code} did not resolve; the reprint step did not fire"
    assert by_code[code].ref == ref
    assert by_code[code].provenance is Provenance.REPRINT


def test_a_reprint_is_reported_with_where_it_came_from(cap_result):
    """FR-024, SC-005 — a borrowed image is a substitution the user can see and reject."""
    by_code = {r.card_code: r for r in cap_result.resolutions}
    note = by_code["03016"].note or ""
    assert "01071" in note or "Core Set" in note
    assert by_code["03016"].substituted


def test_the_reprint_step_follows_links_in_both_directions(scan_library):
    """FR-022. `duplicate_of_code` is one-directional in the pack response (research R4).

    Wasp's `13020` duplicates Ant-Man's `12020`, so a Core-Set-only special case would be
    wrong. This asserts the reverse link is followed too, by resolving a card whose only
    connection to its image is a `duplicated_by` entry.
    """
    index = build_index(scan_library)
    cards = load_cards("cap")
    target = next(c for c in cards if c.code == "03016")
    reversed_card = PackCard(
        code=target.code,
        pack_code=target.pack_code,
        position=target.position,
        name=target.name,
        type_code=target.type_code,
        quantity=target.quantity,
        card_set_type_name_code=target.card_set_type_name_code,
        # The forward link removed and the same relationship expressed backwards.
        duplicate_of_code=None,
        duplicated_by=["01071"],
    )
    patched = [reversed_card if c.code == "03016" else c for c in cards]
    result = resolve_pack(
        expand_pack(patched),
        patched,
        index,
        ACCEPTANCE_HEROES["cap"],
        scan_library,
        printing_lookup,
    )
    by_code = {r.card_code: r for r in result.resolutions}
    assert by_code["03016"].provenance is Provenance.REPRINT
    assert by_code["03016"].ref == CAP_REPRINTS["03016"][1]


def test_a_reprint_link_pointing_at_nothing_leaves_the_card_unresolved(scan_library):
    """A dangling link is a gap to report, never an excuse to pick an arbitrary file."""
    index = build_index(scan_library)
    cards = [c for c in load_cards("cap")]
    target = next(c for c in cards if c.code == "03016")
    broken = PackCard(
        code=target.code,
        pack_code=target.pack_code,
        position=target.position,
        name=target.name,
        type_code=target.type_code,
        quantity=target.quantity,
        duplicate_of_code="99999",
    )
    patched = [broken if c.code == "03016" else c for c in cards]
    result = resolve_pack(
        expand_pack(patched),
        patched,
        index,
        ACCEPTANCE_HEROES["cap"],
        scan_library,
        printing_lookup,
    )
    assert "03016" in {u.card_code for u in result.unresolved}


# ----------------------------------------------------------- T045: copy counts (FR-016)


def test_copy_counts_come_from_the_pack_being_printed(cap_result):
    """FR-016, US1 scenario 4 — the borrowed *image* never brings its quantity with it.

    `cap` prints two copies of Make the Call. The Core Set printing whose scan is borrowed
    ships three. Taking the quantity from the image's own printing would put a third copy in
    every Captain America pack, which is a wrong deck rather than a cosmetic error.
    """
    quantities = {r.card_code: r.quantity for r in cap_result.resolutions}
    assert quantities["03016"] == 2, "Make the Call must print the pack's 2, not the Core Set's 3"
    assert quantities["03018"] == 2
    assert quantities["03021"] == 1, "Energy prints 1 in cap and 4 in the Core Set"
    assert quantities["03022"] == 1
    assert quantities["03023"] == 1


def test_no_resolution_takes_its_quantity_from_the_borrowed_printing(cap_result):
    """The general form of the above, asserted across every reprint rather than by example."""
    cap_quantities = {c.code: c.quantity for c in load_cards("cap")}
    for resolution in cap_result.resolutions:
        if resolution.provenance is Provenance.REPRINT:
            assert resolution.quantity == cap_quantities[resolution.card_code]


# --------------------------------------------------------------- what Phase 3 cannot do


def test_the_reverse_link_resolves_a_card_the_forward_link_cannot(cap_result):
    """FR-022's "both directions", occurring naturally rather than by contrivance.

    `03034` Enhanced Awareness has no `duplicate_of_code` at all — only a `duplicated_by`
    entry pointing at `17031`, which is Star-Lord's printing of the same card at position 31.
    Following that backwards is the only route to its image. A resolver that read
    `duplicate_of_code` alone would leave this card unresolved and report a gap that is not
    one.
    """
    by_code = {r.card_code: r for r in cap_result.resolutions}
    assert by_code["03034"].provenance is Provenance.REPRINT
    assert by_code["03034"].ref == "Aspects/Basic/Basic_Enhanced Awareness_Upgrade_31.tiff"
    # And FR-016 still holds across the reverse link: cap ships 3, Star-Lord's printing 2.
    assert by_code["03034"].quantity == 3


def test_the_cards_left_for_later_steps_are_exactly_the_measured_three(cap_result):
    """Phase 3 has steps 1 and 3 only, and this pins what that leaves behind.

    `Enraged` and `Expert Defense` sit under the root `Aspects/` tree with no position in
    their filenames and no reprint link, so only step 4's name match reaches them (Phase 5).
    `Followed` is in **no folder of the library at all** — verified against the mounted Drive,
    not just the fixture — so no cascade step can ever close it. It is the genuine FR-017 gap
    the run must stop and name, which makes it US2's acceptance case rather than a defect.

    Asserting the exact set means a regression that silently resolves *more* cards by some
    unintended route is as visible as one that resolves fewer.
    """
    assert {u.card_code for u in cap_result.unresolved} == {"03031", "03032", "03033"}


def test_an_unresolved_card_is_named_rather_than_dropped(cap_result):
    """FR-017 — a pack that is quietly short is the failure US2 exists to prevent."""
    for unresolved in cap_result.unresolved:
        assert unresolved.card_name
        assert unresolved.side in (Side.FRONT, Side.BACK)
        assert unresolved.searched, "a gap must say where it looked"
