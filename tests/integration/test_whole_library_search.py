"""T079 — a pack card that is not in the hero's folder is found anyway (US3, SC-003).

The library was organised by someone else, and it does not reliably file a hero's cards
under that hero. Printing the *whole pack* rather than a derived starter deck makes that
more load-bearing than it looks: a pack's aspect cards live under the shared `Aspects/`
tree by design, not by accident, and its basic cards are frequently a reprint whose only
scan sits in whichever pack printed the card first.

Two heroes, two different routes out of the hero folder, both asserted end to end through
the API rather than against the resolver:

- **Black Widow's `Quincarrier`** is filed under Wasp. Not as a copy — the file *is* Wasp's
  printing of the card, at Wasp's position — so the step that reaches it is the reprint
  link, and the origin it names is the other printing.
- **Thor's `Teamwork`** is filed under `Aspects/Leadership/`, where a position means nothing
  because there is no pack to read it against. Its filename carries no position at all, so
  the name match is the only route it has.

What makes them one test file rather than two is the property they share and that SC-003
turns on: the card is found, and the report says where it came from. A tool that found the
file and said nothing would be the more dangerous of the two failures, because the user has
no way to notice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

BKW_FOLDER = ACCEPTANCE_HEROES["bkw"]
THOR_FOLDER = ACCEPTANCE_HEROES["thor"]

#: Black Widow's, filed under Wasp — measured 2026-08-17 against the derived fixture.
QUINCARRIER = "08023"
QUINCARRIER_SCAN = "Heros/Nadia Van Dyne_Wasp/Basic_Quincarrier_Support_25.tiff"

#: Thor's, filed under the shared aspect tree with no position in its name.
TEAMWORK = "06032"
TEAMWORK_SCAN = "Aspects/Leadership/Leadership_Teamwork_Event_Thor.tiff"


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


def assemble(client, library, folder: str) -> dict:
    """Start a run and take it all the way to `ready`.

    The decklist decision is taken as part of getting there, because an undecided candidate
    holds the run in `awaiting_cards` exactly as an unresolved card does (FR-013d). Skipping
    it would leave every assertion below unable to tell "this pack has a gap" apart from
    "nobody has answered the decklist question yet", which is the one distinction these
    tests exist to make.
    """
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    run = confirmed.json()

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
def black_widow(client, scan_library) -> dict:
    return assemble(client, scan_library, BKW_FOLDER)


@pytest.fixture
def thor(client, scan_library) -> dict:
    return assemble(client, scan_library, THOR_FOLDER)


# ------------------------------------------------ US3 scenario 1: another hero's folder


def test_black_widow_resolves_completely(black_widow):
    """SC-003 — the harder acceptance set, and the whole point of US3.

    Black Widow needs every step the cascade has. Under folder matching alone she is short
    twelve cards; the exact-zero assertion is what stops a regression in any one of them
    from hiding behind the others.
    """
    assert black_widow["unresolved"] == []
    assert black_widow["state"] == "ready"


def test_a_card_filed_under_another_hero_is_found(black_widow):
    """US3 scenario 1 — `Quincarrier` is a Black Widow card sitting in Wasp's folder."""
    resolutions = {r["card_code"]: r for r in black_widow["report"]["resolutions"]}
    assert QUINCARRIER in resolutions, "Quincarrier did not resolve"
    assert resolutions[QUINCARRIER]["file"] == QUINCARRIER_SCAN


def test_that_cards_origin_is_named_in_the_report(black_widow):
    """FR-024, SC-005 — found silently is the failure mode that costs the user a print run.

    The file is Wasp's printing rather than a stray copy of Black Widow's, so what the
    report has to say is *which other printing* lent the image. The user can then decide
    whether an identical card from a different pack is acceptable to them, which is a
    decision they cannot make if they are never told.
    """
    resolutions = {r["card_code"]: r for r in black_widow["report"]["resolutions"]}
    entry = resolutions[QUINCARRIER]
    assert entry["provenance"] != "folder_position"
    assert entry["note"], "a substitution with no note is a silent substitution"
    assert "13025" in entry["note"] or "25" in entry["note"]


# ---------------------------------------------------------- US3 scenario 2: `Aspects/`


def test_thor_resolves_completely(thor):
    """SC-003 — Thor's pack reaches outside his folder for five of its cards."""
    assert thor["unresolved"] == []
    assert thor["state"] == "ready"


def test_a_card_filed_under_aspects_is_found(thor):
    """US3 scenario 2. `Aspects/` is where a position stops meaning anything.

    The index records no pack hint for anything under that tree, because a position there
    has no pack to be read against — so `Teamwork` cannot be found by the positional steps
    at all, however far they widen. The name match is not a safety net for this card; it is
    the only route it has.
    """
    resolutions = {r["card_code"]: r for r in thor["report"]["resolutions"]}
    assert TEAMWORK in resolutions, "Teamwork did not resolve"
    assert resolutions[TEAMWORK]["file"] == TEAMWORK_SCAN
    assert resolutions[TEAMWORK]["provenance"] == "name"


def test_a_name_match_says_so_in_the_report(thor):
    """US3 scenario 3 — the loosest step in the cascade is the one that must be loudest.

    A name match tolerates the misspellings the library actually contains, which means it
    can tolerate a genuine difference too. Reporting it as a name match is what lets a wrong
    match be caught by reading rather than discovered at the table.
    """
    resolutions = {r["card_code"]: r for r in thor["report"]["resolutions"]}
    entry = resolutions[TEAMWORK]
    assert entry["provenance"] == "name"
    assert "name" in (entry["note"] or "").lower()


# --------------------------------------------------------- what searching wide must not cost


def test_searching_the_whole_library_does_not_pull_in_another_packs_cards(thor):
    """FR-021 widens where images are looked for, never what is printed.

    The distinction the hero folder draws is between *where images are found* and *what the
    pack contains*, and the second comes from the pack listing alone. A search that widened
    both would quietly print Star-Lord's Leadership cards into Thor's pack, because they are
    equally reachable under `Aspects/Leadership/`.
    """
    printed = {r["card_code"] for r in thor["report"]["resolutions"]}
    assert all(code.startswith("06") for code in printed), sorted(
        code for code in printed if not code.startswith("06")
    )


def test_the_report_still_accounts_only_for_the_hero_folder(thor):
    """FR-031 as amended, SC-004 — the whole library is searched; the report is not a listing.

    Read literally against FR-021 the file-by-file accounting would name all 678 fixture
    files — 4,447 in the real library — for one hero, which no user can read and no test can
    assert. The two halves are asserted together because either alone is satisfiable by
    doing nothing: files from outside the folder *do* reach the report, through the
    resolutions that used them, and they reach it *only* that way.
    """
    used_outside = [
        r["file"] for r in thor["report"]["resolutions"] if not r["file"].startswith(THOR_FOLDER)
    ]
    assert used_outside, "no card was resolved from outside the hero folder at all"

    listed = [
        entry["file"]
        for section in ("unused_files", "uninterpretable_files", "conflicts")
        for entry in thor["report"][section]
    ]
    assert all(ref.startswith(THOR_FOLDER) for ref in listed), listed
