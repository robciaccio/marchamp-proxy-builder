"""T092 — the folder that holds no deck list scan (FR-013c, SC-006j, research R9).

25 of 60 hero folders hold no deck list scan; Hulk's and Phoenix's are the two in the
fixture library. That is not a failure and must never become one — the rest of the pack
still prints — but a pack printed without a deck list is a pile of cards the user cannot
build the starter deck from, so the gap has to be *named* and somewhere to get one has to
be offered.

Two things are asserted here that nothing else in the suite can assert:

- **The address is offered and never fetched** (FR-013c, FR-002). Hall of Heroes is not on
  the egress allowlist and must not become the second host on it. The user downloads the
  photograph themselves and hands it back through the same upload path an unresolved card
  uses, which is why this needs no mechanism of its own (R9).
- **A Hall of Heroes photograph is very likely below the print-resolution floor** and that
  is the correct outcome rather than something to special-case into silence (R9). It is a
  *warning* on the report, exactly as a soft library scan is (FR-035) — the file the user
  went and fetched is the only one there is.
"""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

#: The two acceptance heroes whose real folders hold no deck list scan.
HULK_FOLDER = ACCEPTANCE_HEROES["hlk"]
PHOENIX_FOLDER = ACCEPTANCE_HEROES["phoenix"]
CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

HALL_OF_HEROES = "hallofheroeslcg.com"


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def client(state_root, upstream_transport, monkeypatch):
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=state_root)
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def writable_library(tmp_path, scan_library) -> Path:
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def card_bytes(width: int = LIBRARY_IMAGE_W, height: int = LIBRARY_IMAGE_H) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def resolve(client, library: Path, folder: str, pack_code: str | None = None) -> dict:
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    body = {"action": "select", "pack_code": pack_code} if pack_code else {"action": "confirm"}
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json=body,
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    return confirmed.json()


def upload_decklist(client, run: dict, name: str, data: bytes):
    return client.post(
        f"/api/assemblies/{run['id']}/decklist",
        files={"file": (name, data, "application/octet-stream")},
        headers={"If-Match": str(run["version"])},
    )


# ----------------------------------------------------- the gap, named rather than hidden


@pytest.mark.parametrize("folder", [HULK_FOLDER, PHOENIX_FOLDER], ids=["hulk", "phoenix"])
def test_a_folder_with_no_decklist_scan_names_the_gap(client, writable_library, folder):
    """FR-013c, SC-006j — never indistinguishable from a pack printed with one."""
    run = resolve(client, writable_library, folder)

    assert run["decklist_candidate"] is None
    assert run["report"]["decklist_printed"] is False
    assert HALL_OF_HEROES in run["report"]["decklist_source_url"]


@pytest.mark.parametrize("folder", [HULK_FOLDER, PHOENIX_FOLDER], ids=["hulk", "phoenix"])
def test_a_missing_decklist_never_refuses_the_run(client, writable_library, folder):
    """FR-013c — the rest of the pack still prints. The deck list is the one card in the
    pack whose absence is reported rather than fatal."""
    run = resolve(client, writable_library, folder)
    assert run["state"] in ("ready", "awaiting_cards")
    assert not [u for u in run["unresolved"] if u["card_code"] == "decklist"]


def test_the_application_never_fetches_the_hall_of_heroes_address(
    client, writable_library, no_network
):
    """FR-002, FR-013c — one host on the allowlist, and this is not it.

    Asserted against the socket rather than against a counter the code maintains:
    `no_network` fails any real connection, and the MarvelCDB client's own calls go through
    the mock transport. A run that resolved the address by fetching it would fail here
    naming the connection rather than passing quietly.
    """
    run = resolve(client, writable_library, HULK_FOLDER)
    assert HALL_OF_HEROES in run["report"]["decklist_source_url"]


# ------------------------------------------------------ the upload half of POST /decklist


def test_the_user_supplies_the_photograph_they_fetched(client, writable_library):
    """R9 — the same upload path an unresolved card uses, so this needs no new mechanism."""
    run = resolve(client, writable_library, HULK_FOLDER)

    response = upload_decklist(client, run, "hulk deck list.png", card_bytes())
    assert response.status_code == 200, response.text
    updated = response.json()

    assert updated["report"]["decklist_printed"] is True
    assert updated["report"]["decklist_source_url"] is None
    (entry,) = [r for r in updated["report"]["resolutions"] if r["group"] == "decklist"]
    assert entry["source"] == "upload"
    assert entry["file"] == "hulk deck list.png"


def test_an_uploaded_decklist_is_not_counted_among_the_packs_cards(client, writable_library):
    """FR-013b, FR-018 — it is not one of the pack's cards, however it arrived."""
    run = resolve(client, writable_library, HULK_FOLDER)
    before = run["report"]["cards_printed"]

    updated = upload_decklist(client, run, "deck list.png", card_bytes()).json()
    assert updated["report"]["cards_printed"] == before


def test_supplying_a_decklist_customizes_the_run(client, writable_library):
    """FR-026i — the folder holds no such file, so two users pointed at it would now get
    different PDFs. This is not the pack's standard PDF."""
    run = resolve(client, writable_library, HULK_FOLDER)
    updated = upload_decklist(client, run, "deck list.png", card_bytes()).json()

    refused = client.post(
        f"/api/assemblies/{updated['id']}/confirmation",
        json={},
        headers={"If-Match": str(updated["version"])},
    )
    assert refused.status_code == 400
    assert "save_as" in refused.json()["detail"]


def test_an_undecodable_decklist_upload_is_refused_with_the_reason(client, writable_library):
    """FR-028 — decode-by-content is enforced here exactly as it is for a card."""
    run = resolve(client, writable_library, HULK_FOLDER)

    response = upload_decklist(client, run, "notes.txt", b"not an image")
    assert response.status_code == 400, response.text
    assert "notes.txt" in response.json()["detail"]

    again = client.get(f"/api/assemblies/{run['id']}").json()
    assert again["report"]["decklist_printed"] is False


def test_a_soft_photograph_is_a_warning_and_not_a_refusal(client, writable_library):
    """R9, FR-035 — "will very likely fall below the print-resolution floor and trip
    FR-035's warning; that is the correct outcome and must not be special-cased into
    silence."

    This is the one place where the card path's FR-028 floor and R9 disagree, and R9 wins
    for the deck list specifically: refusing it would leave a user who did exactly what the
    tool told them to do — go to Hall of Heroes and fetch the photograph — with no way to
    print the one card that makes the pack usable. Decode is still enforced; only the
    floor's verdict is downgraded, to exactly the sentence a soft library scan gets.
    """
    run = resolve(client, writable_library, HULK_FOLDER)

    response = upload_decklist(client, run, "hall of heroes.jpg", card_bytes(600, 860))
    assert response.status_code == 200, response.text
    warned = [w for w in response.json()["report"]["low_resolution"]]
    assert any(w["file"] == "hall of heroes.jpg" for w in warned)


def test_a_folder_that_holds_a_decklist_still_decides_by_json(client, writable_library):
    """The multipart half must not displace the half US1 built (T048c).

    One path carries two shapes, and a route that dispatched on the wrong thing would take
    the JSON decision away — leaving every folder that *does* hold a scan unable to accept
    the candidate the tool proposed.
    """
    run = resolve(client, writable_library, CAP_FOLDER)
    assert run["decklist_candidate"] is not None

    response = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 200, response.text
    assert response.json()["report"]["decklist_printed"] is True
