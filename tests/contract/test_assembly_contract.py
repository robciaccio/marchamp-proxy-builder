"""T081/T088 — the two endpoints that let a user finish a pack the library cannot (US4).

`test_openapi_matches.py` verifies that the *document* the service generates agrees with
`contracts/openapi.yaml`. That is a statement about shapes and says nothing about
behaviour, so this file asserts the half a schema cannot: which status code comes back,
what the body carries, and — for the omission — *when* the endpoint refuses.

The refusal is the reason this file exists at all. FR-030a says permission to print an
incomplete pack "MUST NOT be granted in advance of the run reporting which cards are
unresolved", which is a rule about ordering rather than about payloads. A contract test
that only checked `acknowledged: true` would pass against a service that honoured a
blanket permission offered before the run had resolved anything.
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

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: Captain America's nemesis minion at position 28, with no reprint link anywhere — so
#: removing its scan leaves the cascade nothing to fall back to and the run reports it.
BARON_ZEMO = "03028"
BARON_ZEMO_SCAN = (
    f"{CAP_FOLDER}/Captain America Nemesis/Captain America Nemesis_Baron Zemo_Minion_28.tiff"
)

VISION_FOLDER = "Heros/Vision_Vision"
#: One code, two faces, no linked card (research R12) — the case `side` exists for.
INTANGIBLE = "26002"
INTANGIBLE_FRONT = f"{VISION_FOLDER}/Vision_Intangible_Upgrade_2a.tiff"
INTANGIBLE_BACK = f"{VISION_FOLDER}/Vision_Intangible_Upgrade_2b.tiff"


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def client(state_root, upstream_transport, monkeypatch):
    """The app with neither `MARCHAMP_IMAGE_DIR` nor `MARCHAMP_CATALOG` set (SC-003a)."""
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
    """A writable copy of the derived fixture library, hardlinked rather than copied.

    Every test here only ever removes a link, which cannot touch the original. The
    session-scoped `scan_library` stays read-only — FR-001's whole point is that this
    feature never writes to a scan library.
    """
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def card_bytes(width: int = LIBRARY_IMAGE_W, height: int = LIBRARY_IMAGE_H) -> bytes:
    """A generated card face as TIFF bytes. Never a real scan (FR-038a)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def start(client, library: Path, folder: str, pack_code: str | None = None) -> dict:
    """Create a run and take it through pack confirmation, so it has resolved."""
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


def unresolved(run: dict, card_code: str) -> list[dict]:
    return [u for u in run["unresolved"] if u["card_code"] == card_code]


# ------------------------------------------------- POST /cards/{card_code}/image (T081)


def test_supplying_a_file_resolves_that_card_and_returns_the_run(client, writable_library):
    """The contract's `200`: the card is resolved as a manual choice."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = start(client, writable_library, CAP_FOLDER)
    assert unresolved(run, BARON_ZEMO)

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/image",
        files={"file": ("baron zemo.tiff", card_bytes(), "image/tiff")},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == run["id"]
    assert not unresolved(updated, BARON_ZEMO)


def test_the_upload_carries_a_side_for_a_double_sided_card(client, vision_library):
    """`side` is not decoration: `26002` is one code with two faces (research R12).

    Without it the endpoint cannot say *which* face the file answers for, and a run short
    of the back would be marked complete by a file supplied for the front.
    """
    (vision_library / INTANGIBLE_BACK).unlink()
    run = start(client, vision_library, VISION_FOLDER, pack_code="vision")
    assert [u["side"] for u in unresolved(run, INTANGIBLE)] == ["back"]

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{INTANGIBLE}/image",
        files={"file": ("intangible back.tiff", card_bytes(), "image/tiff")},
        data={"side": "back"},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 200, response.text
    assert not unresolved(response.json(), INTANGIBLE)


def test_a_file_supplied_for_the_wrong_side_leaves_the_other_unresolved(client, vision_library):
    """`side` defaults to the front, and a front does not answer for a back."""
    (vision_library / INTANGIBLE_BACK).unlink()
    run = start(client, vision_library, VISION_FOLDER, pack_code="vision")

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{INTANGIBLE}/image",
        files={"file": ("wrong face.tiff", card_bytes(), "image/tiff")},
        data={"side": "front"},
        headers={"If-Match": str(run["version"])},
    )
    # The front already resolved from the library, so there is nothing to answer for.
    assert response.status_code == 409, response.text


def test_an_upload_for_an_unknown_run_is_404(client):
    response = client.post(
        f"/api/assemblies/{'0' * 32}/cards/{BARON_ZEMO}/image",
        files={"file": ("x.tiff", card_bytes(), "image/tiff")},
        headers={"If-Match": "1"},
    )
    assert response.status_code == 404


def test_an_upload_for_a_card_that_is_not_unresolved_is_409(client, writable_library):
    """FR-026's upload answers a *gap*. A card already resolved is not one."""
    run = start(client, writable_library, CAP_FOLDER)
    assert not unresolved(run, BARON_ZEMO)

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/image",
        files={"file": ("x.tiff", card_bytes(), "image/tiff")},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 409
    assert BARON_ZEMO in response.json()["detail"]


def test_a_stale_version_is_refused(client, writable_library):
    """ADR 0001's optimistic concurrency, on the endpoint two tabs race on."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = start(client, writable_library, CAP_FOLDER)

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/image",
        files={"file": ("x.tiff", card_bytes(), "image/tiff")},
        headers={"If-Match": str(run["version"] - 1)},
    )
    assert response.status_code == 409


# ---------------------------------------------- POST /cards/{card_code}/omission (T088)


def test_an_acknowledged_omission_is_recorded(client, writable_library):
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = start(client, writable_library, CAP_FOLDER)

    response = client.post(
        f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/omission",
        json={"acknowledged": True},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert not unresolved(updated, BARON_ZEMO)
    assert [o["card_code"] for o in updated["report"]["omitted"]] == [BARON_ZEMO]


def test_an_unacknowledged_omission_is_refused(client, writable_library):
    """FR-030a — not reachable by dismissing a prompt, and not inferred from silence."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = start(client, writable_library, CAP_FOLDER)

    for body in ({"acknowledged": False}, {}):
        response = client.post(
            f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/omission",
            json=body,
            headers={"If-Match": str(run["version"])},
        )
        assert response.status_code == 422, response.text
        assert unresolved(client.get(f"/api/assemblies/{run['id']}").json(), BARON_ZEMO), (
            "a refused omission must leave the card unresolved"
        )


def test_a_blanket_permission_offered_before_the_gap_is_known_is_refused(client, writable_library):
    """FR-030a, US4 scenario 9 — the whole point of the endpoint's `409`.

    The run has been created but not resolved, so it has reported no gap. A decision taken
    now is not an informed one, and the run must still stop on the first card it cannot
    resolve rather than carrying a permission granted in advance.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(writable_library), "hero_folder": CAP_FOLDER},
    )
    run = created.json()

    premature = client.post(
        f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/omission",
        json={"acknowledged": True},
        headers={"If-Match": str(run["version"])},
    )
    assert premature.status_code == 409, premature.text

    resolved = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    ).json()
    assert unresolved(resolved, BARON_ZEMO)
    assert resolved["state"] == "awaiting_cards"


def test_an_omission_for_an_unknown_run_is_404(client):
    response = client.post(
        f"/api/assemblies/{'0' * 32}/cards/{BARON_ZEMO}/omission",
        json={"acknowledged": True},
        headers={"If-Match": "1"},
    )
    assert response.status_code == 404


@pytest.fixture
def vision_library(tmp_path) -> Path:
    """A library holding one genuinely double-sided player card, and nothing else.

    Purpose-built rather than derived: what is under test needs exactly two files present
    or absent, and everything else in the pack going unresolved would only make the
    assertions harder to read.
    """
    from tests.conftest import make_card_image

    root = tmp_path / "vision-library"
    for rel in (INTANGIBLE_FRONT, INTANGIBLE_BACK):
        make_card_image(root / rel, Path(rel).stem, width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)
    return root
