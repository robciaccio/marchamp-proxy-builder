"""T058 — assembling `cap` end to end over the fixture library (US1, SC-003a).

The MVP's acceptance case: point the tool at `Heros/Steve Rogers_Captain America/` with no
catalog present and nothing configured, and have it identify the pack, gather the cards, and
recover the eight physical cards whose scans live in the Core Set.

**What this asserts, and what it deliberately does not.**

`cap` cannot be assembled *completely* against this library, and that is a fact about the
fixture rather than a shortfall in the cascade. `Followed` (03032) resolves by reprint into
Spider-Ham's pack, and T005 derives only the ten acceptance heroes plus the Core Set and
`Aspects/`, so Spider-Ham's folder is not here. Driven against the mounted library this card
resolves as it stands.

Phase 5 closed the other two. `Enraged` (03031) and `Expert Defense` (03033) sit under the
root `Aspects/` tree with no position in their filenames and no reprint link, and cascade
step 4's name match is the only route they have.

So the run reaches `awaiting_cards` with exactly one named gap against the fixture — none
against the real library — and this file asserts that precisely. A test claiming "every card
resolved" here would either be wrong or would have to weaken FR-017.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: The six `cap` cards whose image is borrowed from the Core Set, and the copies each
#: prints. 2+2+1+1+1+1 = the eight physical cards US1's independent test names.
CORE_SET_REPRINTS = {
    "03016": 2,  # Make the Call — the Core Set ships three; cap prints two (FR-016)
    "03018": 2,  # The Power of Leadership
    "03020": 1,  # Mockingbird
    "03021": 1,  # Energy
    "03022": 1,  # Genius
    "03023": 1,  # Strength
}

#: What the whole cascade leaves unresolved **against the derived fixture**. `03032` is a
#: fixture-coverage artefact and resolves against the real library today. See the module
#: docstring.
EXPECTED_GAPS = {"03032"}


@pytest.fixture
def client(tmp_path, upstream_transport, monkeypatch):
    """The app with **neither** `MARCHAMP_IMAGE_DIR` nor `MARCHAMP_CATALOG` set (SC-003a).

    This is the point of the fixture, not incidental setup: feature 002 names its paths per
    run, and a test that configured 001's would stop proving that.
    """
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    assert settings.image_dir is None and settings.catalog_path is None
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def resolved_run(client, scan_library):
    """A `cap` run taken as far as Phase 3 can take it: identified, confirmed, resolved."""
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": CAP_FOLDER},
    )
    assert created.status_code == 202, created.text
    run = created.json()

    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    return confirmed.json()


def test_the_pack_is_identified_from_the_folder_alone(client, scan_library):
    """FR-010 — no catalog, no configuration, just a folder the user named."""
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": CAP_FOLDER},
    )
    run = created.json()
    assert run["identification"]["pack_code"] == "cap"
    assert run["identification"]["confidence"] >= 0.75
    assert run["state"] == "awaiting_pack"


def test_confirming_pins_a_snapshot_revision(resolved_run):
    """FR-044b, FR-045 — what the run resolved against cannot move under it later."""
    assert resolved_run["snapshot_revision"]
    assert len(resolved_run["snapshot_revision"]) == 16


@pytest.mark.parametrize(("code", "quantity"), sorted(CORE_SET_REPRINTS.items()))
def test_each_core_set_reprint_is_recovered(code, quantity, resolved_run):
    """US1's independent test: the eight physical cards sourced from the Core Set.

    Both halves matter. The image comes from the Core Set's printing (FR-014, FR-022), and
    the *quantity* comes from `cap` (FR-016) — Make the Call prints twice here and ships
    three times in the Core Set, so a run taking the quantity along with the image would put
    a third copy in every Captain America pack.
    """
    resolutions = {r["card_code"]: r for r in resolved_run["report"]["resolutions"]}
    assert code in resolutions, f"{code} did not resolve"
    assert resolutions[code]["provenance"] == "reprint"
    assert resolutions[code]["file"].startswith("Core Set/")


def test_the_reprints_account_for_eight_physical_cards(resolved_run):
    assert sum(CORE_SET_REPRINTS.values()) == 8


def test_a_borrowed_image_is_reported_as_a_substitution(resolved_run):
    """FR-024, SC-005 — a borrowed image is visible, so a wrong one can be rejected."""
    resolutions = {r["card_code"]: r for r in resolved_run["report"]["resolutions"]}
    assert resolutions["03016"]["note"]
    assert "01071" in resolutions["03016"]["note"]


def test_the_identity_and_the_nemesis_set_are_present(resolved_run):
    """FR-015a, FR-015b — the pack is named after the identity, and the nemesis is a subfolder."""
    by_group: dict[str, set[str]] = {}
    for entry in resolved_run["report"]["resolutions"]:
        by_group.setdefault(entry["group"], set()).add(entry["card_code"])
    assert by_group["identity"] == {"03001a", "03001b"}
    assert {"03027", "03028", "03029", "03030"} <= by_group["nemesis"]


def test_the_decklist_scan_is_proposed_and_not_yet_printed(resolved_run):
    """FR-013d — the tool proposes; the user accepts."""
    candidate = resolved_run["decklist_candidate"]
    assert candidate is not None
    assert candidate["ref"].endswith("Captain America Decklist.tif")
    assert resolved_run["report"]["decklist_printed"] is False


def test_confirming_the_decklist_prints_it_without_customizing_the_run(client, resolved_run):
    """FR-013e — otherwise no run is ever standard and reuse never fires."""
    response = client.post(
        f"/api/assemblies/{resolved_run['id']}/decklist",
        json={"action": "confirm"},
        headers={"If-Match": str(resolved_run["version"])},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["report"]["decklist_printed"] is True
    assert updated["decklist_candidate"] is None


def test_the_run_stops_and_names_exactly_the_cards_it_cannot_find(resolved_run):
    """FR-017 — a pack that is quietly short is the failure US2 exists to prevent.

    The exact set is asserted, so a regression that resolves *more* by some unintended route
    is as visible as one that resolves fewer. See the module docstring for why these three.
    """
    gaps = {u["card_code"] for u in resolved_run["unresolved"]}
    assert gaps == EXPECTED_GAPS
    assert resolved_run["state"] == "awaiting_cards"


def test_every_gap_says_where_the_tool_looked(resolved_run):
    """SC-008 — the user must be able to act on the report alone."""
    for gap in resolved_run["unresolved"]:
        assert gap["card_name"]
        assert gap["group"]
        assert gap["searched"], f"{gap['card_code']} names no search"


def test_the_run_is_not_yet_an_outcome(resolved_run):
    """FR-036 — waiting on a card is not failing, and must not be reported as failure."""
    assert resolved_run["outcome"] is None


def test_no_pdf_is_produced_before_confirmation(client, resolved_run):
    """FR-026a — and there is never partial output."""
    assert resolved_run["pdf_id"] is None
    response = client.get(f"/api/assemblies/{resolved_run['id']}/document")
    assert response.status_code == 409


def test_the_report_counts_cards_not_faces(resolved_run):
    """FR-018 — the unit is cards, and no expected total is asserted or warned on."""
    report = resolved_run["report"]
    assert report["cards_in_pack"] == 59, "cap is 34 records and 59 physical cards"
    assert 0 < report["cards_printed"] <= report["cards_in_pack"]
    assert report["faces_printed"] >= report["cards_printed"]


def test_the_run_survives_being_read_back(client, resolved_run):
    """FR-026b, ADR 0001 — the record on disk is the run."""
    again = client.get(f"/api/assemblies/{resolved_run['id']}")
    assert again.status_code == 200
    assert again.json()["report"]["resolutions"] == resolved_run["report"]["resolutions"]


def test_nothing_outside_the_library_reaches_the_report(resolved_run, scan_library):
    """FR-009 — refs are library-relative and no absolute path is retained."""
    for entry in resolved_run["report"]["resolutions"]:
        assert not entry["file"].startswith("/")
        assert str(scan_library) not in entry["file"]
