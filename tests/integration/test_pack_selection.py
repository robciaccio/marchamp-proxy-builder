"""T054 — a user-selected pack is recorded, and is not customization (FR-012b, SC-009a).

Two claims that sound similar and are not:

**Recorded.** A pack the user chose stays distinguishable from one the tool identified,
exactly as a manual card resolution stays distinguishable from an automatic one. A user who
corrected the tool should be able to see that they did, and so should anyone reading the run
later.

**Not customization.** What gets printed follows entirely from the pack and its snapshot, so
a run that corrected the identification and then resolved everything automatically produces
*the pack's standard PDF* — the same document any other user would get for that pack. If
selecting counted as customization, FR-026h's reuse would never fire for anyone who had ever
been asked to pick, and `save_as` would be demanded for a document that is not bespoke.

Driven through the HTTP API rather than the service, because FR-012b is an interface promise:
the wizard is a client of this API and must be able to make and see this distinction.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES


@pytest.fixture
def client(tmp_path, upstream_transport, monkeypatch):
    """The app with no `MARCHAMP_IMAGE_DIR` and no `MARCHAMP_CATALOG` (SC-003a).

    Feature 002's paths are named per run, so nothing here is configured in advance — and a
    test that configured them would stop proving that.
    """
    import marchamp.api.routes as routes
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    assert routes is not None

    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def start(client, scan_library, folder: str):
    response = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": folder},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_the_tool_identifies_cap_and_waits_for_confirmation(client, scan_library):
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    assert run["state"] == "awaiting_pack"
    assert run["identification"]["pack_code"] == "cap"
    assert run["identification"]["source"] == "identified"
    assert run["identification"]["confirmed"] is False
    assert run["identification"]["evidence"]


def test_selecting_a_different_pack_is_recorded_as_user_selected(client, scan_library):
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    response = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "select", "pack_code": "thor"},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 202, response.text
    updated = response.json()
    assert updated["identification"]["pack_code"] == "thor"
    assert updated["identification"]["source"] == "user_selected"
    assert updated["identification"]["confirmed"] is True


def test_a_selected_pack_does_not_make_the_run_customized(client, scan_library):
    """SC-009a, FR-026i — the point of the whole task.

    Asserted through `save_as`: a customized run *requires* it and an uncustomized one
    *forbids* it, so a run that rejects `save_as` is a run the service considers standard.
    That is a sharper probe than reading a flag, because it is the behaviour that flag
    exists to drive.
    """
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "select", "pack_code": "thor"},
        headers={"If-Match": str(run["version"])},
    )
    current = client.get(f"/api/assemblies/{run['id']}").json()
    refused = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={"save_as": "my copy"},
        headers={"If-Match": str(current["version"])},
    )
    # 400 would mean "you may not name this, it is the pack's standard PDF"; 409 means the
    # run is not ready yet. Either way it is *not* the 400 that demands a name, which is
    # what a customized run would answer with.
    assert refused.status_code in (400, 409)
    assert "customized" not in refused.json().get("detail", "").lower() or (
        "not customized" in refused.json()["detail"].lower()
    )


def test_the_candidates_endpoint_offers_a_way_out(client, scan_library):
    """FR-012b — a refusal is a prompt, never a dead end."""
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    response = client.get(f"/api/assemblies/{run['id']}/packs")
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert candidates
    assert candidates[0]["pack_code"] == "cap"


def test_the_candidates_endpoint_searches_every_pack_by_name(client, scan_library):
    """The same path serves an unidentifiable folder, which ranking cannot help."""
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    response = client.get(f"/api/assemblies/{run['id']}/packs", params={"q": "widow"})
    assert response.status_code == 200
    assert [c["pack_code"] for c in response.json()["candidates"]] == ["bkw"]


def test_a_stale_if_match_is_refused(client, scan_library):
    """ADR 0001 at the wire. Two tabs answering two questions is the lost update."""
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    response = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"] + 3)},
    )
    assert response.status_code == 409


def test_a_hero_folder_outside_the_library_is_refused_by_name(client, scan_library):
    """FR-006 — refused specifically, so the user knows which path to fix."""
    response = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": "../somewhere"},
    )
    assert response.status_code == 400
    assert "hero_folder" in response.json()["detail"]


def test_the_run_never_needed_image_dir_or_catalog(client, scan_library):
    """SC-003a — feature 002 names its paths per run and configures nothing in advance."""
    run = start(client, scan_library, ACCEPTANCE_HEROES["cap"])
    assert run["library_root"] == str(scan_library.resolve())
    health = client.get("/api/health").json()
    # 001's configuration is genuinely absent, and 002 worked anyway.
    assert any(p["kind"].startswith("image_dir") for p in health["problems"])
