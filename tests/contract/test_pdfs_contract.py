"""T103 — deleting a run, and the stored-PDF list (FR-026f–FR-026i).

001 measured roughly 202 MB for a single deck's PDF, and retention under FR-026f is
otherwise unbounded, so "how do I get that space back" is a question this feature has to
answer. It answers it with **two separate acts**, and the separation is the requirement
rather than an implementation detail:

    DELETE /api/assemblies/{id}   throw away a deck attempt
    DELETE /api/pdfs/{id}         reclaim the disk

A standard PDF belongs to the *pack*, not to the run that happened to build it (FR-026g1).
Fold the two acts together and deleting one run of Captain America revokes FR-026f's
guarantee for every other run of Captain America — and the user cannot predict whether
discarding a run frees 202 MB or nothing, which is the worst of both.

What is asserted here is the contract: status codes, body shapes, and which resource
survives which call. `tests/integration/test_retention.py` asserts the *freed bytes*, which
is the half a status code cannot show.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

#: Two heroes that resolve every card against the derived fixture, so a run over either
#: reaches `complete` with no manual answer — the definition of a *standard* PDF.
THOR_FOLDER = ACCEPTANCE_HEROES["thor"]
WASP_FOLDER = ACCEPTANCE_HEROES["wsp"]

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]


@pytest.fixture
def client(tmp_path: Path, upstream_transport, monkeypatch):
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def writable_library(tmp_path, scan_library) -> Path:
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def start(client, library: Path, folder: str) -> dict:
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


def finish(client, library: Path, folder: str, save_as: str | None = None) -> dict:
    """Take a cleanly resolving hero to a PDF. `save_as` only when the run was customized."""
    run = start(client, library, folder)
    if run["decklist_candidate"]:
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()
    assert run["state"] == "ready", run["state"]
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={} if save_as is None else {"save_as": save_as},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    return done.json()


# ------------------------------------------------------ DELETE /api/assemblies/{id}


def test_deleting_a_run_is_204_and_the_run_is_gone(client, writable_library):
    run = start(client, writable_library, CAP_FOLDER)
    deleted = client.delete(
        f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"])}
    )
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert client.get(f"/api/assemblies/{run['id']}").status_code == 404
    assert run["id"] not in {r["id"] for r in client.get("/api/assemblies").json()["runs"]}


def test_deleting_an_unknown_run_is_404(client):
    response = client.delete("/api/assemblies/" + "0" * 32, headers={"If-Match": "1"})
    assert response.status_code == 404, response.text


def test_deleting_with_a_stale_version_is_409(client, writable_library):
    """The same precondition every other mutation carries (ADR 0001).

    Deleting is the one mutation where losing the race costs everything rather than one
    field, so it is the last place to make the check optional.
    """
    run = start(client, writable_library, CAP_FOLDER)
    response = client.delete(
        f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"] + 7)}
    )
    assert response.status_code == 409, response.text
    assert client.get(f"/api/assemblies/{run['id']}").status_code == 200


def test_deleting_a_run_leaves_the_packs_standard_pdf(client, writable_library):
    """FR-026g1 — the row an implementation gets wrong by treating a PDF as the run's.

    Two runs of the same pack share one standard PDF, so this asserts against the *second*
    run: after the first is deleted, the second must still download the same bytes. A test
    that only checked the list would pass against a service that kept a listing entry
    pointing at nothing.
    """
    first = finish(client, writable_library, THOR_FOLDER)
    second = finish(client, writable_library, THOR_FOLDER)
    assert second["reused"] is True, "the second run must have been served the stored PDF"
    assert second["pdf_id"] == first["pdf_id"]
    before = client.get(f"/api/assemblies/{second['id']}/document").content

    deleted = client.delete(
        f"/api/assemblies/{first['id']}", headers={"If-Match": str(first["version"])}
    )
    assert deleted.status_code == 204, deleted.text

    assert client.get(f"/api/assemblies/{second['id']}/document").content == before
    listed = client.get("/api/pdfs").json()
    assert first["pdf_id"] in {p["id"] for p in listed["pdfs"]}
    assert client.get(f"/api/pdfs/{first['pdf_id']}/document").status_code == 200


# --------------------------------------------------------------------- GET /api/pdfs


def test_the_stored_pdf_list_is_empty_before_anything_is_printed(client):
    assert client.get("/api/pdfs").json() == {"pdfs": [], "total_bytes": 0}


def test_the_stored_pdf_list_carries_kind_name_and_size(client, writable_library):
    """`total_bytes` is what makes FR-026g's reclamation an informed choice rather than a
    guess about which of two identical-looking rows is the 202 MB one."""
    standard = finish(client, writable_library, THOR_FOLDER)
    listed = client.get("/api/pdfs")
    assert listed.status_code == 200, listed.text
    body = listed.json()

    entry = next(p for p in body["pdfs"] if p["id"] == standard["pdf_id"])
    assert entry["kind"] == "standard"
    assert entry["pack_code"] == "thor"
    assert entry["snapshot_revision"] == standard["snapshot_revision"]
    assert entry["byte_size"] > 0
    assert entry["name"]
    assert entry["created_at"]
    assert body["total_bytes"] == sum(p["byte_size"] for p in body["pdfs"])


def test_a_saved_pdf_is_listed_separately_from_a_standard_one(client, writable_library):
    """FR-026i. A customized run's output is the user's, under the user's name."""
    standard = finish(client, writable_library, THOR_FOLDER)

    run = start(client, writable_library, WASP_FOLDER)
    skipped = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        json={"action": "skip"},
        headers={"If-Match": str(run["version"])},
    )
    assert skipped.status_code == 200, skipped.text
    run = skipped.json()
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={"save_as": "Wasp — no deck list"},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    saved = done.json()

    by_id = {p["id"]: p for p in client.get("/api/pdfs").json()["pdfs"]}
    assert by_id[standard["pdf_id"]]["kind"] == "standard"
    assert by_id[saved["pdf_id"]]["kind"] == "saved"
    assert by_id[saved["pdf_id"]]["name"] == "Wasp — no deck list"
    # A saved PDF belongs to a run, not to a pack: nothing else may be served it.
    assert by_id[saved["pdf_id"]]["pack_code"] is None


# ------------------------------------------- DELETE and GET /api/pdfs/{pdf_id}[/document]


def test_a_stored_pdf_downloads(client, writable_library):
    run = finish(client, writable_library, THOR_FOLDER)
    response = client.get(f"/api/pdfs/{run['pdf_id']}/document")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_deleting_a_stored_pdf_is_204_and_removes_it_from_the_list(client, writable_library):
    run = finish(client, writable_library, THOR_FOLDER)
    deleted = client.delete(f"/api/pdfs/{run['pdf_id']}")
    assert deleted.status_code == 204, deleted.text

    body = client.get("/api/pdfs").json()
    assert run["pdf_id"] not in {p["id"] for p in body["pdfs"]}
    assert body["total_bytes"] == sum(p["byte_size"] for p in body["pdfs"])
    assert client.get(f"/api/pdfs/{run['pdf_id']}/document").status_code == 404


def test_the_next_assembly_rebuilds_after_the_standard_pdf_is_deleted(client, writable_library):
    """US5 scenario 6b. Deleting is reclamation, never a refusal to print again."""
    first = finish(client, writable_library, THOR_FOLDER)
    assert client.delete(f"/api/pdfs/{first['pdf_id']}").status_code == 204

    again = finish(client, writable_library, THOR_FOLDER)
    assert again["reused"] is False
    assert again["pdf_id"] == first["pdf_id"], "same key, rebuilt from the same inputs"
    assert client.get(f"/api/assemblies/{again['id']}/document").status_code == 200


@pytest.mark.parametrize(
    "pdf_id",
    [
        "0" * 16,  # well-formed saved id, nothing stored under it
        "thor@0123456789abcdef@fedcba9876543210",  # well-formed standard key, absent
        # Single path segments that reach the handler and are refused there — the
        # whitelist doing the work, rather than the routing layer. A `%2F` traversal is
        # decoded to a separator before routing, so it tests the server, not this code.
        "thor@notarevision@notanidentity",
        "NOT HEX",
    ],
)
def test_an_unknown_stored_pdf_is_404_on_both_verbs(client, pdf_id):
    """A refused identifier and an absent file are the same answer to the caller.

    Distinguishing them would tell an id-guessing caller which shapes are real, and there is
    nothing the user could do differently with the distinction.
    """
    assert client.get(f"/api/pdfs/{pdf_id}/document").status_code == 404
    assert client.delete(f"/api/pdfs/{pdf_id}").status_code == 404
