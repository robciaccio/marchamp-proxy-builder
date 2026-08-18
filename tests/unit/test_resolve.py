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


def test_a_reprint_link_pointing_at_nothing_borrows_no_image(scan_library):
    """A dangling link is a gap to report, never an excuse to pick an arbitrary file.

    Phase 5 changed what happens *after* this step rather than what this step does. With
    steps 2 and 4 behind it, Make the Call falls through the dead link and is found by name
    in the Core Set's Leadership tree — which is the cascade working, not the reprint step
    inventing a file. So the assertion is on the reprint step itself: whatever provenance
    ends up on this card, it is not `reprint`, because there was no other printing to read.
    """
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
    by_code = {r.card_code: r for r in result.resolutions}
    assert by_code["03016"].provenance is not Provenance.REPRINT
    # And a card the dead link leaves with no name in the library anywhere stays a gap.
    nameless = PackCard(
        code=target.code,
        pack_code=target.pack_code,
        position=target.position,
        name="Nothing In This Library Is Called This",
        type_code=target.type_code,
        quantity=target.quantity,
        duplicate_of_code="99999",
    )
    patched = [nameless if c.code == "03016" else c for c in cards]
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


def test_the_only_card_no_step_can_reach_is_the_one_the_library_lacks(cap_result):
    """The whole cascade, and what it still cannot do.

    Phase 3 left three cards behind and this test pinned all three. Phase 5's step 4 closed
    two of them exactly as that note predicted: `Enraged` and `Expert Defense` sit under the
    root `Aspects/` tree with no position in their filenames and no reprint link, so the name
    match is the only route they have.

    `Followed` is in **no folder of the library at all** — verified against the mounted
    Drive, not just the fixture — so no cascade step can ever close it. It is the genuine
    FR-017 gap the run must stop and name, which makes it US2's acceptance case rather than
    a defect.

    Asserting the exact set means a regression that silently resolves *more* cards by some
    unintended route is as visible as one that resolves fewer.
    """
    assert {u.card_code for u in cap_result.unresolved} == {"03032"}


def test_an_unresolved_card_is_named_rather_than_dropped(cap_result):
    """FR-017 — a pack that is quietly short is the failure US2 exists to prevent."""
    for unresolved in cap_result.unresolved:
        assert unresolved.card_name
        assert unresolved.side in (Side.FRONT, Side.BACK)
        assert unresolved.searched, "a gap must say where it looked"


# =====================================================================================
# T075, T077 — steps 2 and 4 (FR-021, FR-023, FR-024, SC-005)
#
# Phase 5 adds the two steps that search *outside* the folder the user named. They are the
# reason a pack can be printed complete at all: measured against the derived fixture library,
# 24 of the ten acceptance heroes' cards live somewhere other than their own hero folder, and
# two heroes — Phoenix and Wonder Man — carry no usable positions anywhere, so the name path
# is their only route rather than a safety net.
#
# Both steps look across the whole library, and both therefore have to answer the question
# step 1 never faces: position 33 occurs in dozens of packs and the name "Hawkeye" occurs in
# four folders. What keeps them from pairing a card with confidently wrong art is that
# neither ever matches on one piece of evidence alone. Step 2 requires the position *and*
# the canonical name of the card being sought; step 4 prefers the hero folder before the rest
# of the library and, where that is still ambiguous, narrows by the face suffix and the card
# type — every one of which is something the tool already knows about the specific card it is
# looking for, which is the direction FR-023 permits.
# =====================================================================================


def resolve(pack_code: str, scan_library: Path) -> ResolveResult:
    index = build_index(scan_library)
    cards = load_cards(pack_code)
    return resolve_pack(
        expand_pack(cards),
        cards,
        index,
        ACCEPTANCE_HEROES[pack_code],
        scan_library,
        printing_lookup,
    )


@pytest.fixture(scope="module")
def bkw_result(scan_library) -> ResolveResult:
    return resolve("bkw", scan_library)


@pytest.fixture(scope="module")
def ant_result(scan_library) -> ResolveResult:
    return resolve("ant", scan_library)


@pytest.fixture(scope="module")
def phoenix_result(scan_library) -> ResolveResult:
    return resolve("phoenix", scan_library)


@pytest.fixture(scope="module")
def wonder_man_result(scan_library) -> ResolveResult:
    return resolve("wonder_man", scan_library)


# ------------------------------------------------------------ step 2: library_position


#: Measured against the fixture library, 2026-08-17. Each card, and the file the
#: whole-library positional search must reach. Every one of them sits under `Aspects/`,
#: where a position carries no pack and so cannot be found by step 1 at all — which is what
#: makes this the step the pack's aspect cards depend on.
LIBRARY_POSITION_CASES = {
    "08033": "Aspects/Basic/Basic_Espionage_Upgrade_33.tiff",
    "08032": "Aspects/Protection/Protection_Defensive Stage_Upgrade_32.tiff",
}


@pytest.mark.parametrize(("code", "expected"), sorted(LIBRARY_POSITION_CASES.items()))
def test_a_card_outside_the_hero_folder_is_found_by_position(code, expected, bkw_result):
    """FR-021 — the library does not reliably file a hero's cards under that hero."""
    by_code = {r.card_code: r for r in bkw_result.resolutions}
    assert code in by_code, f"{code} did not resolve; the whole-library search did not fire"
    assert by_code[code].ref == expected
    assert by_code[code].provenance is Provenance.LIBRARY_POSITION


def test_the_whole_library_search_requires_the_name_to_agree_as_well(scan_library):
    """Position alone spans the whole library, and on its own it is worthless.

    Position 33 occurs in more than a dozen packs. A step that took the position alone would
    hand Black Widow's `Espionage` whichever file happened to sort first — confidently wrong
    art, reported as found. This asserts the guard directly: with the card's name changed to
    something no file carries, the same position no longer resolves it.
    """
    index = build_index(scan_library)
    cards = load_cards("bkw")
    target = next(c for c in cards if c.code == "08033")
    renamed = PackCard(
        code=target.code,
        pack_code=target.pack_code,
        position=target.position,
        name="Nothing In This Library Is Called This",
        type_code=target.type_code,
        quantity=target.quantity,
    )
    patched = [renamed if c.code == "08033" else c for c in cards]
    result = resolve_pack(
        expand_pack(patched),
        patched,
        index,
        ACCEPTANCE_HEROES["bkw"],
        scan_library,
        printing_lookup,
    )
    assert "08033" in {u.card_code for u in result.unresolved}


def test_a_position_conflict_in_the_hero_folder_no_longer_ends_the_cascade(ant_result):
    """FR-021 read plainly: a conflict at step 1 is a *failure to match*, so the search goes on.

    Ant-Man's folder holds two different cards at position 7 — `Army of Ants` and a
    mis-numbered `Pym Particles` — so step 1 can pick neither. Stopping there would leave a
    card unresolved that the very next step identifies unambiguously by name, and the user
    would be asked to supply a file that is already sitting in the folder they named. The
    clash is still reported by the report's own pass over the index, which is derived from
    the library rather than from this run's failures.
    """
    by_code = {r.card_code: r for r in ant_result.resolutions}
    assert "12007" in by_code, "the cascade stopped at a step 1 conflict instead of continuing"
    assert by_code["12007"].ref == "Heros/Scott Lang_Ant-Man/Ant-Man_Army of Ants_Support_7.tiff"
    assert by_code["12007"].substituted, "a card recovered from a contested position is not a "
    "plain folder-position match and must not be reported as one"


# ------------------------------------------------------------------------ step 4: name


def test_the_name_path_carries_a_folder_that_numbers_copies(wonder_man_result):
    """SC-003c, FR-023 — Wonder Man's folder numbers physical copies, so it has no positions.

    `2_`, `3_` and `4_Active Altruism_Event.tif` are three scans of one card. Read as
    positions they are confidently wrong, so the index records none, and every step that
    keys on a position finds nothing. The name path is not a fallback here; it is the only
    route the card has.
    """
    by_code = {r.card_code: r for r in wonder_man_result.resolutions}
    assert by_code["58003"].provenance is Provenance.NAME
    assert by_code["58003"].ref == "Heros/Simon Williams_Wonderman/2_Active Altruism_Event.tif"


def test_the_name_path_absorbs_the_librarys_typos(wonder_man_result):
    """The library misspells names, and the edit-distance bound exists for exactly that.

    `Battlefild` is a dropped letter. Requiring an exact spelling would report a gap for a
    card whose scan is sitting in the folder.
    """
    by_code = {r.card_code: r for r in wonder_man_result.resolutions}
    assert by_code["58016"].provenance is Provenance.NAME
    assert by_code["58016"].ref.endswith("Justice_Battlefild Benevolence_Event.tif")


def test_the_hero_folder_is_searched_by_name_before_the_rest_of_the_library(wonder_man_result):
    """Four folders hold a file called `Hawkeye`, and only one of them is Wonder Man's.

    Searching the whole library in one undifferentiated pass makes this an ambiguity and
    reports a gap for a card that is right there. Preferring the folder the user named is
    the same principle that puts step 1 before step 2, applied to the name path.
    """
    by_code = {r.card_code: r for r in wonder_man_result.resolutions}
    assert by_code["58013"].ref == "Heros/Simon Williams_Wonderman/Justice_Hawkeye_Ally.tif"


def test_a_name_match_is_narrowed_by_the_face_the_card_data_asks_for(phoenix_result):
    """Two faces of one card, in a folder where the leading number is a copy count.

    `1_Phoenix Force_Upgrade_2A.tif` and `_2B.tif` are the two faces of `34002`. Their names
    are identical — the card data gives both faces the same name — so nothing about the name
    separates them, and a resolver that stopped at the name would either report a conflict
    or print one face twice. The trailing `2A`/`2B` is the only discriminator, and which one
    a face wants is read off the card code, not guessed.
    """
    by_code = {r.card_code: r for r in phoenix_result.resolutions}
    assert by_code["34002a"].ref.endswith("1_Phoenix Force_Upgrade_2A.tif")
    assert by_code["34002b"].ref.endswith("1_Phoenix Force_Upgrade_2B.tif")


def test_a_name_match_is_narrowed_by_the_cards_type_when_the_name_alone_is_ambiguous(
    wonder_man_result,
):
    """`Wonder Fans` and `Wonder Man` are one edit apart, and both are in this folder.

    The bound that absorbs `Battlefild` also pulls the hero's own identity scans into the
    candidates for `Wonder Fans`. The card type separates them exactly — a Support is not a
    Hero — and it is something the tool already knows about the card it is looking for,
    which is the direction FR-023 permits.
    """
    by_code = {r.card_code: r for r in wonder_man_result.resolutions}
    assert by_code["58007"].ref.endswith("12_Wonder Fans_Support.tif")
    assert by_code["58007"].provenance is Provenance.NAME


def test_a_name_is_only_ever_matched_against_the_card_being_sought(scan_library):
    """FR-023 — the prohibited direction is deciding what card a filename names.

    A card whose canonical name matches nothing in the library stays unresolved, however
    many files sit nearby. The library is never asked "what is this file?"; it is only ever
    asked "is this the card I already know I want?".
    """
    index = build_index(scan_library)
    cards = load_cards("wonder_man")
    target = next(c for c in cards if c.code == "58003")
    renamed = PackCard(
        code=target.code,
        pack_code=target.pack_code,
        position=target.position,
        name="Nothing In This Library Is Called This",
        type_code=target.type_code,
        quantity=target.quantity,
    )
    patched = [renamed if c.code == "58003" else c for c in cards]
    result = resolve_pack(
        expand_pack(patched),
        patched,
        index,
        ACCEPTANCE_HEROES["wonder_man"],
        scan_library,
        printing_lookup,
    )
    assert "58003" in {u.card_code for u in result.unresolved}


# --------------------------------------------------- T077: naming the origin (FR-024, SC-005)


def test_a_card_found_outside_the_hero_folder_has_its_origin_named(bkw_result):
    """US3 scenario 1 and 2, SC-005 — a substitution the user cannot see is not reported.

    The provenance says *which step* found it; the note has to say where, in the user's own
    terms, because "library_position" does not tell anyone that Black Widow's `Espionage`
    came out of the shared `Aspects/Basic` tree.
    """
    by_code = {r.card_code: r for r in bkw_result.resolutions}
    espionage = by_code["08033"]
    assert espionage.substituted
    note = espionage.note or ""
    assert "Aspects/Basic" in note
    assert "33" in note


def test_a_name_match_is_reported_as_a_name_match(wonder_man_result):
    """US3 scenario 3 — the whole point is that a wrong match is *visible*.

    A name match is the loosest thing the cascade does: it absorbs typos, which means it can
    absorb a genuine difference too. Reporting it as a name match, and naming the file, is
    what lets the user catch that by reading rather than by discovering it mid-game.
    """
    by_code = {r.card_code: r for r in wonder_man_result.resolutions}
    altruism = by_code["58003"]
    assert altruism.provenance is Provenance.NAME
    assert altruism.substituted
    note = (altruism.note or "").lower()
    assert "name" in note
    assert "active altruism" in note


def test_the_report_carries_the_step_that_found_each_card(wonder_man_result, scan_library):
    """FR-024 — the account has to survive into the thing the user actually reads."""
    from marchamp.assembly.report import build_report

    report = build_report(
        pack_code="wonder_man",
        pack_name="Wonder Man",
        pack_source="identified",
        cards=load_cards("wonder_man"),
        resolutions=wonder_man_result.resolutions,
        built=None,
        decklist=None,
        snapshot_revision=None,
        index=build_index(scan_library),
        hero_folder=ACCEPTANCE_HEROES["wonder_man"],
        unresolved=wonder_man_result.unresolved,
    )
    by_code = {e["card_code"]: e for e in report.resolutions}
    assert by_code["58003"]["provenance"] == "name"
    assert by_code["58003"]["note"]
    assert by_code["58003"]["file"].endswith("2_Active Altruism_Event.tif")
