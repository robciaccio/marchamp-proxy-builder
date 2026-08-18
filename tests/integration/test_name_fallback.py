"""T080 — the two heroes for whom the name match is the *only* route (US3, SC-003c).

Phoenix and Wonder Man are filed under the third convention: `{copy}_{Name}_{Type}`, where
the leading number counts physical copies rather than card positions. `2_`, `3_` and
`4_Active Altruism_Event.tif` are three scans of one card, not three cards. Read as a
position that number is *confidently wrong*, which is worse than no answer at all, so the
index records no position for a single file in either folder — and every positional step in
the cascade therefore finds nothing whatsoever.

That makes these two the acceptance case rather than an edge case. Everywhere else the name
match is a safety net under three positional steps; here it is load-bearing on its own, and
a regression in it that the other eight heroes would absorb takes these two to nothing. The
measured numbers are the point: under positional matching alone Phoenix resolves 4 of 37
faces and Wonder Man 1 of 35.

Two things the name path has to do that a simple normalise-and-compare cannot, both drawn
from these folders rather than invented:

- **absorb the library's typos.** `Pheonix`, `Battlefild`, `Unifield`, `Upgarde`, `Boms
  Away` are all real. Requiring an exact spelling reports a gap for a card that is sitting
  in the folder the user named.
- **not be fooled by them.** A bound loose enough for `Battlefild` also puts `Wonder Man`
  within reach of `Wonder Fans`, and the two faces of one card carry the *same* name in the
  card data. Neither is settled by looking harder at the filename; both are settled by the
  face and the type the card data already states.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

PHOENIX_FOLDER = ACCEPTANCE_HEROES["phoenix"]
WONDER_MAN_FOLDER = ACCEPTANCE_HEROES["wonder_man"]

#: Wonder Man's only unresolvable card, and why. `Avengers Compound` has no scan in his
#: folder and its one other printing is `59032`, in a pack T005 does not derive — the same
#: shape as `cap`'s `Followed`. A gap in the fixture's coverage, not in the cascade.
WONDER_MAN_FIXTURE_GAP = {"58034"}


@pytest.fixture
def client(tmp_path, upstream_transport, monkeypatch):
    """The app with neither `MARCHAMP_IMAGE_DIR` nor `MARCHAMP_CATALOG` set (SC-003a)."""
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def assemble(client, library, folder: str, pack_code: str) -> dict:
    """Start a run, pick the pack, and answer the decklist question if there is one.

    The pack is **selected** rather than confirmed. Identification reads the folder name,
    and these two folders are `Jean Grey_Phoenix (u)` and `Simon Williams_Wonderman` — a
    parenthesised marker and a missing space — so what is under test here is the resolver,
    not FR-010's confidence in a folder name.
    """
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    selected = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "select", "pack_code": pack_code},
        headers={"If-Match": str(run["version"])},
    )
    assert selected.status_code == 202, selected.text
    run = selected.json()

    if run["decklist_candidate"] is not None:
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()
    return run


@pytest.fixture
def phoenix(client, scan_library) -> dict:
    return assemble(client, scan_library, PHOENIX_FOLDER, "phoenix")


@pytest.fixture
def wonder_man(client, scan_library) -> dict:
    return assemble(client, scan_library, WONDER_MAN_FOLDER, "wonder_man")


def resolutions(run: dict) -> dict[str, dict]:
    return {r["card_code"]: r for r in run["report"]["resolutions"]}


# ------------------------------------------------------------------------------- Phoenix


def test_phoenix_resolves_completely(phoenix):
    """SC-003c — every card, with no positional evidence available anywhere.

    Phoenix holds no decklist scan either, so this run reaches `ready` with the pack alone,
    which is the case SC-002a distinguishes from the eight heroes whose folders hold one.
    """
    assert phoenix["unresolved"] == []
    assert phoenix["state"] == "ready"


def test_the_name_path_is_phoenixs_primary_route_not_a_safety_net(phoenix):
    """SC-003c — the distinguishing property of this folder, asserted as a proportion.

    Most of this pack has no other route at all. Asserting a majority rather than a count
    keeps the test honest if the fixture gains a card, while still failing loudly if the
    name path quietly stops being what carries this hero.
    """
    provenances = [r["provenance"] for r in phoenix["report"]["resolutions"]]
    assert provenances.count("name") > len(provenances) / 2
    assert "folder_position" not in provenances, (
        "a copy-counting folder must contribute no positions at all; one appearing here "
        "means a copy number was read as a position, which is a wrong answer rather than none"
    )


def test_the_identity_faces_are_told_apart_despite_the_typo_and_the_shared_name(phoenix):
    """Both faces carry the name `Phoenix`, and one of the two files misspells it.

    `0_Pheonix_Hero_1B.tif` and `0_Phoenix_Alter-Ego_1A.tif` are one card's two faces. The
    name cannot separate them — the card data gives both the same one — and on the file that
    could carry the distinction the name is misspelled by a transposed pair. Resolving both
    faces to the one correctly-spelled file would print the alter-ego twice and lose the
    hero, while reporting the run complete.

    Note that this folder labels the hero `1B` and the alter-ego `1A`, the reverse of every
    other folder in the library. The resolver follows the suffix the card codes ask for
    rather than the word in the filename, so the pairing here is the library's, not a guess
    — and it is reported as a name match, which is what puts it in front of the user.
    """
    found = resolutions(phoenix)
    assert found["34001a"]["file"] != found["34001b"]["file"]
    assert {found["34001a"]["file"], found["34001b"]["file"]} == {
        f"{PHOENIX_FOLDER}/0_Phoenix_Alter-Ego_1A.tif",
        f"{PHOENIX_FOLDER}/0_Pheonix_Hero_1B.tif",
    }


def test_the_two_faces_of_one_upgrade_are_told_apart_by_suffix_alone(phoenix):
    """`1_Phoenix Force_Upgrade_2A.tif` and `_2B.tif`: same name, same type, same folder.

    Nothing but the trailing suffix distinguishes these, and which one a face wants is read
    off the card code rather than guessed. This is the case that makes the face narrowing a
    filter rather than a tie-breaker — a step that fell back to the name when the suffix
    excluded everything would answer "where is the back?" with the front.
    """
    found = resolutions(phoenix)
    assert found["34002a"]["file"] == f"{PHOENIX_FOLDER}/1_Phoenix Force_Upgrade_2A.tif"
    assert found["34002b"]["file"] == f"{PHOENIX_FOLDER}/1_Phoenix Force_Upgrade_2B.tif"


def test_the_three_scans_of_one_card_are_one_card(phoenix):
    """FR-034 — a copy-counting folder holds several files per card, and prints one.

    `Telekinetic Attack` has two scans in this folder because the pack ships two copies. The
    quantity comes from the pack listing (FR-016), never from counting files, so this must
    resolve to a single ref and print whatever the pack says.
    """
    found = resolutions(phoenix)
    telekinetic = [r for code, r in found.items() if r["card_name"] == "Telekinetic Attack"]
    assert len(telekinetic) == 1
    assert telekinetic[0]["file"].endswith("_Telekinetic Attack_Event.tif")


# ---------------------------------------------------------------------------- Wonder Man


def test_wonder_man_resolves_everything_the_fixture_holds(wonder_man):
    """SC-003c, against the coverage the derived fixture actually has.

    The one gap is `Avengers Compound`, which has no scan in the folder and whose only other
    printing is in a pack T005 does not derive. Asserting the exact set rather than a count
    means a regression that loses a *different* card is not absorbed by the same number.
    """
    assert {u["card_code"] for u in wonder_man["unresolved"]} == WONDER_MAN_FIXTURE_GAP
    assert wonder_man["state"] == "awaiting_cards"


def test_the_name_path_absorbs_the_typos_this_folder_actually_contains(wonder_man):
    """Four real misspellings, each a different shape of mistake.

    Written out as data rather than asserted in prose: each of these was measured in the
    library, and a bound that stopped absorbing any one of them would report a gap for a
    card whose scan is right there.
    """
    misspelled = {
        "58016": "Justice_Battlefild Benevolence_Event.tif",  # dropped letter
        "58020": "Leadership_Unifield Strike_Event.tif",  # transposed pair
        "58030": "Aggression_Caught in the Crossfire_Upgarde.tif",  # in the type, not the name
        "58017": "Aggression_Bombs Away_Event.tif",  # correct here; `Boms Away` is under Aspects/
    }
    found = resolutions(wonder_man)
    for code, filename in misspelled.items():
        assert found[code]["file"] == f"{WONDER_MAN_FOLDER}/{filename}", code


def test_a_name_one_edit_from_another_card_is_settled_by_the_card_type(wonder_man):
    """`Wonder Fans` and `Wonder Man` are within the bound of each other, in one folder.

    The bound cannot be tightened to separate them without dropping `Battlefild`, so the
    separation comes from somewhere else entirely: the card data says one is a Support and
    the other a Hero, and the library writes the type into the filename. Picking either at
    random would pair a card with confidently wrong art and say nothing about it.
    """
    found = resolutions(wonder_man)
    assert found["58007"]["file"] == f"{WONDER_MAN_FOLDER}/12_Wonder Fans_Support.tif"
    assert found["58001a"]["file"] == f"{WONDER_MAN_FOLDER}/0_Wonderman_Hero_1A.tif"
    assert found["58001b"]["file"] == f"{WONDER_MAN_FOLDER}/0_Wonderman_Alter-Ego_1B.tif"


def test_the_hero_folder_is_preferred_over_the_rest_of_the_library(wonder_man):
    """Four folders hold a file called `Hawkeye`, and `Sentry` is in two.

    Searching the whole library in one undifferentiated pass makes both of these ambiguous
    and reports a gap for cards that are in the folder the user named. Preferring that
    folder is the same principle that puts the folder search before the library search,
    applied to the name path.
    """
    found = resolutions(wonder_man)
    assert found["58013"]["file"] == f"{WONDER_MAN_FOLDER}/Justice_Hawkeye_Ally.tif"
    assert found["58015"]["file"] == f"{WONDER_MAN_FOLDER}/Justice_Sentry_Ally.tif"


def test_every_name_match_is_reported_as_one(phoenix, wonder_man):
    """SC-005, US3 scenario 3 — across two whole packs, not by example.

    These two heroes resolve almost entirely by the loosest step the cascade has. If a name
    match ever went unreported, this is where it would matter most and where a spot check
    would be least likely to catch it.
    """
    for run in (phoenix, wonder_man):
        matched = [r for r in run["report"]["resolutions"] if r["provenance"] == "name"]
        assert matched
        for entry in matched:
            assert entry["note"], entry["card_code"]
            assert "name" in entry["note"].lower(), entry["card_code"]
