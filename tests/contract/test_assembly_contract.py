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

#: Two heroes that resolve every card against the derived fixture, so a run over either can
#: reach `complete` without a manual answer — which is what makes it a *standard* PDF.
THOR_FOLDER = ACCEPTANCE_HEROES["thor"]
WASP_FOLDER = ACCEPTANCE_HEROES["wsp"]

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


# ----------------------------------------------------- GET /api/assemblies (T098)
#
# FR-026c, SC-006g. The requirement is stated from the user's side — "without remembering
# an identifier" — so what is asserted is that a client which recorded *nothing* can still
# tell its three kinds of run apart. Every lookup below goes through the list.


def test_the_run_list_distinguishes_the_three_kinds_of_run(client, writable_library):
    """Finished, waiting on a card, and awaiting confirmation of the pack.

    Three states with three different next actions: download it, go find a scan, say yes.
    A list that collapsed any two of them into "in progress" would send the user into a run
    to find out which — which is the identifier-free browsing FR-026c exists to provide,
    given back as a chore.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    waiting = start(client, writable_library, CAP_FOLDER)
    assert waiting["state"] == "awaiting_cards"

    created = client.post(
        "/api/assemblies",
        json={"library_root": str(writable_library), "hero_folder": WASP_FOLDER},
    )
    assert created.status_code == 202, created.text
    unconfirmed = created.json()
    assert unconfirmed["state"] == "awaiting_pack"

    finished = _finish(client, writable_library, THOR_FOLDER)

    listed = client.get("/api/assemblies")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    by_id = {r["id"]: r for r in body["runs"]}
    assert set(by_id) >= {waiting["id"], unconfirmed["id"], finished["id"]}

    assert by_id[finished["id"]]["state"] == "complete"
    assert by_id[finished["id"]]["outcome"] in ("clean", "warnings")
    assert by_id[finished["id"]]["unresolved_count"] == 0

    assert by_id[waiting["id"]]["state"] == "awaiting_cards"
    assert by_id[waiting["id"]]["unresolved_count"] == len(waiting["unresolved"])
    # Still going, so no verdict yet — FR-036 keeps "waiting" distinct from "finished badly".
    assert by_id[waiting["id"]]["outcome"] is None

    assert by_id[unconfirmed["id"]]["state"] == "awaiting_pack"
    assert by_id[unconfirmed["id"]]["outcome"] is None


def test_the_run_list_carries_enough_to_choose_between_runs(client, writable_library):
    """A summary the user can act on: which hero, which pack, and how stale it is.

    Not the report, deliberately — the contract puts that on the detail resource, because
    ten packs' worth of resolutions is a list nobody loads.
    """
    run = start(client, writable_library, CAP_FOLDER)
    summary = client.get("/api/assemblies").json()["runs"][0]

    assert summary["id"] == run["id"]
    assert summary["hero_folder"] == CAP_FOLDER
    assert summary["library_root"] == str(writable_library)
    assert summary["pack_code"] == "cap"
    assert summary["pack_name"]
    assert summary["version"] == run["version"]
    assert summary["created_at"] and summary["updated_at"]
    assert "report" not in summary


def test_the_run_list_is_newest_first(client, writable_library):
    """So resuming what you were just doing is the top row, not a search."""
    first = start(client, writable_library, CAP_FOLDER)
    second = start(client, writable_library, WASP_FOLDER)

    ids = [r["id"] for r in client.get("/api/assemblies").json()["runs"]]
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_the_run_list_is_empty_before_anything_is_assembled(client):
    assert client.get("/api/assemblies").json() == {"runs": []}


def _finish(client, library: Path, folder: str) -> dict:
    """Take a cleanly resolving hero all the way to a PDF."""
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
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    return done.json()


# --------------------------------------- POST /api/assemblies/{id}/confirmation (T107)
#
# FR-026h and FR-026i are one decision seen from two sides, and `save_as` is where the
# service states which side a run fell on. Required when the run was customized, forbidden
# when it was not — and *forbidden* is the half worth having a test for, because permitting
# it silently is the shape of the bug: a user names their clean Thor run "thor v2", it goes
# to the saved list, and the pack's standard PDF is never built, so every later run of Thor
# pays the ~49 s render that FR-026h exists to avoid.


def test_a_clean_run_produces_the_packs_standard_pdf(client, writable_library):
    run = _finish(client, writable_library, THOR_FOLDER)
    assert run["pdf_id"], run
    stored = next(p for p in client.get("/api/pdfs").json()["pdfs"] if p["id"] == run["pdf_id"])
    assert stored["kind"] == "standard"


def test_save_as_is_forbidden_when_the_run_was_not_customized(client, writable_library):
    """FR-026h. Naming a clean run would quietly cost every later run of that pack the
    render the standard PDF exists to avoid."""
    run = start(client, writable_library, THOR_FOLDER)
    if run["decklist_candidate"]:
        run = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        ).json()
    assert run["state"] == "ready"

    response = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={"save_as": "thor v2"},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code == 400, response.text
    assert "save_as" in response.json()["detail"]


def test_save_as_is_required_when_the_run_was_customized(client, writable_library):
    """FR-026i. What the user changed is theirs; it is never the pack's standard PDF.

    Two users pointed at the same folder would otherwise get different documents from the
    same name — which is the property `standard` is supposed to carry.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = start(client, writable_library, CAP_FOLDER)
    for gap in run["unresolved"]:
        supplied = client.post(
            f"/api/assemblies/{run['id']}/cards/{gap['card_code']}/image",
            files={"file": ("supplied.tiff", card_bytes(), "application/octet-stream")},
            data={"side": gap["side"]},
            headers={"If-Match": str(run["version"])},
        )
        assert supplied.status_code == 200, supplied.text
        run = supplied.json()
    if run["decklist_candidate"]:
        run = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        ).json()
    assert run["state"] == "ready", run["state"]

    refused = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert refused.status_code == 400, refused.text
    assert "save_as" in refused.json()["detail"]

    named = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={"save_as": "Captain America — Zemo rescanned"},
        headers={"If-Match": str(run["version"])},
    )
    assert named.status_code == 202, named.text
    saved = named.json()
    stored = next(p for p in client.get("/api/pdfs").json()["pdfs"] if p["id"] == saved["pdf_id"])
    assert stored["kind"] == "saved"
    assert stored["name"] == "Captain America — Zemo rescanned"


def test_selecting_the_pack_is_not_customization(client, writable_library):
    """FR-012b says so in terms: what is printed follows from the pack listing, so a run
    that corrected the tool and then resolved everything automatically is still standard."""
    run = start(client, writable_library, THOR_FOLDER, pack_code="thor")
    assert run["identification"]["source"] == "user_selected"
    if run["decklist_candidate"]:
        run = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        ).json()

    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    stored = next(
        p for p in client.get("/api/pdfs").json()["pdfs"] if p["id"] == done.json()["pdf_id"]
    )
    assert stored["kind"] == "standard"
