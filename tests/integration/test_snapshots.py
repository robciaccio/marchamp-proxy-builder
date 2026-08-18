"""T102 — a run keeps the card data it started with (FR-044b, FR-045, US5).

The failure this guards against has no symptom. A user resolves forty cards against one
pack listing, an explicit refresh brings down a corrected listing, and the run they come
back to prints a *different deck* — one more card, or two copies where there was one —
with every resolution they made still sitting there looking answered. Nothing is reported,
because from the inside nothing went wrong.

So the pinning has to be real rather than incidental: the revision is recorded when the pack
is confirmed, and every later pass of that run reads the listing **at that revision**, not
the current one. `SnapshotStore.read_revision` exists for this and the superseded file is
archived rather than overwritten, which is what makes it possible at all.

The mirror property matters just as much and is asserted alongside: a *new* run started
after the refresh gets the new data. A pin that leaked into the store would freeze the
application at whatever it first fetched.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import (
    ACCEPTANCE_HEROES,
    SNAPSHOT_FIXTURES,
    UPSTREAM_LAST_MODIFIED,
    UPSTREAM_MAX_AGE,
    UnstubbedRequest,
)

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]

#: The correction upstream publishes half way through the run. A player card, so it lands in
#: the pack's card count and in what would be printed — a change nobody could miss if it
#: happened, and nobody would notice if it happened silently.
CORRECTION = {
    "code": "40099",
    "name": "A Correction Upstream",
    "position": 99,
    "quantity": 1,
    "type_code": "ally",
    "pack_code": "thor",
}


class MutableUpstream:
    """MarvelCDB, with a listing a test can change between requests."""

    def __init__(self) -> None:
        self.last_modified = UPSTREAM_LAST_MODIFIED
        self.extra: dict[str, list[dict]] = {}

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def publish(self, pack_code: str, card: dict) -> None:
        """Upstream corrects a pack. A new `Last-Modified`, or the conditional request
        would be answered `304` and nothing would change — which is the other half of the
        contract and is asserted in `test_packs_contract.py`."""
        self.extra.setdefault(pack_code, []).append(card)
        self.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "marvelcdb.com":
            raise UnstubbedRequest(f"outbound request to {request.url}")
        path = request.url.path
        headers = {
            "cache-control": f"max-age={UPSTREAM_MAX_AGE}, public",
            "last-modified": self.last_modified,
            "content-type": "application/json",
        }
        if path == "/api/public/packs/":
            return httpx.Response(
                200,
                json=json.loads((SNAPSHOT_FIXTURES / "packs.json").read_text()),
                headers=headers,
            )
        if path.startswith("/api/public/cards/") and path.endswith(".json"):
            pack = path.removeprefix("/api/public/cards/").removesuffix(".json")
            fixture = SNAPSHOT_FIXTURES / f"{pack}.json"
            if not fixture.is_file():
                return httpx.Response(404, json={"error": "no such pack"}, headers=headers)
            if request.headers.get("if-modified-since") == self.last_modified:
                return httpx.Response(304, headers=headers)
            return httpx.Response(
                200,
                json=json.loads(fixture.read_text()) + self.extra.get(pack, []),
                headers=headers,
            )
        if path.startswith("/api/public/card/") and path.endswith(".json"):
            code = path.removeprefix("/api/public/card/").removesuffix(".json")
            for fixture in sorted(SNAPSHOT_FIXTURES.glob("*.json")):
                if fixture.stem == "packs":
                    continue
                for raw in json.loads(fixture.read_text()):
                    if raw.get("code") == code:
                        return httpx.Response(
                            200, json={"code": code, "pack_code": fixture.stem}, headers=headers
                        )
            return httpx.Response(404, json={"error": "no such card"}, headers=headers)
        raise UnstubbedRequest(f"unstubbed MarvelCDB path {path}")


@pytest.fixture
def upstream() -> MutableUpstream:
    return MutableUpstream()


@pytest.fixture
def client(tmp_path: Path, upstream, monkeypatch):
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream.transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def writable_library(tmp_path, scan_library) -> Path:
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def start_and_confirm(client, library: Path, folder: str = THOR_FOLDER) -> dict:
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
    return confirmed.json()


def decide_decklist(client, run: dict) -> dict:
    if not run["decklist_candidate"]:
        return run
    decided = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert decided.status_code == 200, decided.text
    return decided.json()


# --------------------------------------------------------------- T102, FR-044b, FR-045


def test_a_run_keeps_its_revision_when_the_snapshot_is_refreshed(
    client, writable_library, upstream
):
    """The revision the run pinned, and the composition that goes with it.

    Both are asserted, because only the second one is the requirement. A run that reported
    the old revision while printing the new listing would satisfy a test checking the field
    alone and would be the exact silent substitution FR-045 exists to prevent.
    """
    run = start_and_confirm(client, writable_library)
    pinned = run["snapshot_revision"]
    cards_in_pack = run["report"]["cards_in_pack"]

    upstream.publish("thor", CORRECTION)
    refreshed = client.post("/api/packs/thor/snapshot")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["revision"] != pinned, "the refresh must actually have changed it"

    resumed = client.get(f"/api/assemblies/{run['id']}").json()
    assert resumed["snapshot_revision"] == pinned
    assert resumed["report"]["cards_in_pack"] == cards_in_pack


def test_a_pinned_run_prints_the_pack_it_was_resolved_against(client, writable_library, upstream):
    """Through to the PDF. Every later pass of the run reads the listing at its revision."""
    run = start_and_confirm(client, writable_library)
    pinned = run["snapshot_revision"]
    cards_in_pack = run["report"]["cards_in_pack"]

    upstream.publish("thor", CORRECTION)
    assert client.post("/api/packs/thor/snapshot").status_code == 200

    run = decide_decklist(client, client.get(f"/api/assemblies/{run['id']}").json())
    assert run["state"] == "ready", run["state"]
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    finished = done.json()

    assert finished["state"] == "complete"
    assert finished["snapshot_revision"] == pinned
    assert finished["report"]["snapshot_revision"] == pinned
    assert finished["report"]["cards_in_pack"] == cards_in_pack
    assert CORRECTION["code"] not in {r["card_code"] for r in finished["report"]["resolutions"]}


def test_a_run_started_after_the_refresh_gets_the_new_data(client, writable_library, upstream):
    """The mirror property. A pin that leaked into the store would freeze the application
    at whatever listing it first fetched, which is a worse bug than the one being fixed."""
    first = start_and_confirm(client, writable_library)

    upstream.publish("thor", CORRECTION)
    assert client.post("/api/packs/thor/snapshot").status_code == 200

    second = start_and_confirm(client, writable_library)
    assert second["snapshot_revision"] != first["snapshot_revision"]
    assert second["report"]["cards_in_pack"] == first["report"]["cards_in_pack"] + 1
