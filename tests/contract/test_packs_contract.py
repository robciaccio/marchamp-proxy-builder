"""T110a — `GET` and `POST /api/packs/{pack_code}/snapshot` (FR-044, FR-044a, FR-044b).

Refresh is normally automatic and governed by the cache headers MarvelCDB sends (FR-039).
This pair exists for the case automation cannot serve: most packs are years old and their
data never changes, but a recently released one picks up corrections upstream, and a user
who *already knows* that must not have to wait out a 600-second expiry to act on it.

Two properties carry the pair, and they pull in opposite directions on purpose:

- **`POST` is the user overriding freshness**, so it issues a request even inside `max-age`.
  A refresh that respected the cache would do nothing at all, which is the one thing this
  endpoint must not do.
- **A refresh never alters an existing run** (FR-044b, FR-045). A run pins its revision when
  its pack is confirmed, and nothing reachable from here may move it — otherwise a deck's
  quantities change under resolutions the user already made, invisibly.

The second is `test_snapshots.py`'s to prove end to end (T102); what is asserted here is the
contract half — status, body, and that the endpoint does not lie about what it did.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import (
    SNAPSHOT_FIXTURES,
    UPSTREAM_LAST_MODIFIED,
    UPSTREAM_MAX_AGE,
    UnstubbedRequest,
)


class CountingUpstream:
    """The fixture transport, with a request log and a settable `Last-Modified`.

    Counting is the point: "refresh issues a conditional request even while the stored copy
    is fresh" and "a 304 keeps the revision" are both claims about traffic, and neither is
    checkable against the response body alone.
    """

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.last_modified = UPSTREAM_LAST_MODIFIED
        #: Extra cards to append to a pack's listing, keyed by pack code — how a test makes
        #: upstream genuinely change under a refresh.
        self.extra: dict[str, list[dict]] = {}

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "marvelcdb.com":
            raise UnstubbedRequest(f"outbound request to {request.url}")
        path = request.url.path
        self.paths.append(path)
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
            cards = json.loads(fixture.read_text()) + self.extra.get(pack, [])
            return httpx.Response(200, json=cards, headers=headers)

        raise UnstubbedRequest(f"unstubbed MarvelCDB path {path}")


@pytest.fixture
def upstream() -> CountingUpstream:
    return CountingUpstream()


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


def card_paths(upstream: CountingUpstream) -> list[str]:
    return [p for p in upstream.paths if p.startswith("/api/public/cards/")]


# ------------------------------------------------------------------------------ GET


def test_reading_a_pack_that_has_never_been_captured_is_404(client, upstream):
    """404 rather than a fetch. `GET` reports what is stored; `POST` is how one is made.

    A `GET` that silently captured would make the read side of this pair issue traffic the
    user did not ask for, which is the opposite of what FR-039's freshness rules are for.
    """
    response = client.get("/api/packs/cap/snapshot")
    assert response.status_code == 404, response.text
    assert card_paths(upstream) == []


def test_reading_a_stored_snapshot_reports_its_revision_and_freshness(client):
    captured = client.post("/api/packs/cap/snapshot")
    assert captured.status_code == 200, captured.text

    response = client.get("/api/packs/cap/snapshot")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pack_code"] == "cap"
    assert len(body["revision"]) == 16
    assert body["card_count"] > 0
    assert body["captured_at"] and body["fresh_until"]
    assert body["stale"] is False


def test_a_pack_code_that_is_not_a_pack_code_never_reaches_a_url(client, upstream):
    """The layout and the client both refuse it; neither depends on the other having.

    A filename and a URL are different attack surfaces, and this asserts the outcome the
    user sees rather than which of the two guards fired.
    """
    response = client.get("/api/packs/..%2F..%2Fetc/snapshot")
    assert response.status_code == 404, response.text
    assert upstream.paths == []


# ----------------------------------------------------------------------------- POST


def test_refreshing_issues_a_request_even_while_the_stored_copy_is_fresh(client, upstream):
    """FR-044b. Freshness is not the question when the user has asked."""
    client.post("/api/packs/cap/snapshot")
    before = len(card_paths(upstream))

    # Fresh by construction: `max-age` is 600 s and no time has passed.
    read = client.get("/api/packs/cap/snapshot")
    assert read.status_code == 200
    assert len(card_paths(upstream)) == before, "a read must not fetch"

    refreshed = client.post("/api/packs/cap/snapshot")
    assert refreshed.status_code == 200, refreshed.text
    assert len(card_paths(upstream)) == before + 1


def test_a_304_keeps_the_stored_records_and_the_revision(client, upstream):
    """The cheap outcome, and the one that must not throw a ~202 MB stored PDF away.

    Nothing changed upstream, so the revision every run has pinned stays exactly where it
    is — a refresh that minted a new revision from identical data would invalidate reuse
    for a pack that did not change (research R10).
    """
    first = client.post("/api/packs/cap/snapshot").json()
    second = client.post("/api/packs/cap/snapshot").json()

    assert second["revision"] == first["revision"]
    assert second["card_count"] == first["card_count"]
    assert second["captured_at"] == first["captured_at"]


def test_a_changed_listing_yields_a_new_revision(client, upstream):
    """The case the endpoint exists for: upstream corrected a recently released pack."""
    first = client.post("/api/packs/cap/snapshot").json()

    upstream.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"
    upstream.extra["cap"] = [
        {
            "code": "03099",
            "name": "A Correction Upstream",
            "position": 99,
            "quantity": 1,
            "type_code": "ally",
            "pack_code": "cap",
        }
    ]
    second = client.post("/api/packs/cap/snapshot").json()

    assert second["revision"] != first["revision"]
    assert second["card_count"] == first["card_count"] + 1


def test_refreshing_a_pack_that_does_not_exist_is_refused(client):
    """Named and refused (FR-046), not captured as an empty pack."""
    response = client.post("/api/packs/nosuchpack/snapshot")
    assert response.status_code in (404, 503), response.text
    assert "nosuchpack" in json.dumps(response.json())
