"""T061 — a pack that cannot be completed stops, by name (FR-015c, FR-015f, FR-017, FR-025).

This is the failure US2 exists to prevent, and it is worse than an outright error: a pack
silently missing three cards *looks* finished. The user pays to print it, cuts it, sleeves
it, and discovers the gap at the table.

Three properties are asserted, and the third is the one an implementation drifts away from:

- **Every group is held to the same bar** (FR-015c). A missing nemesis card stops the run
  exactly as a missing player card does. With membership derivation gone, the tool has no
  basis for treating one pack card as less important than another.
- **A missing back face is a missing card** (FR-015f). `26002` Intangible is one code with
  two faces and no linked card, and it is an *upgrade* — not the identity — so an
  implementation that special-cased identity cards prints it front-only: a proxy blank where
  the real card carries game text.
- **Nothing is written.** Not a partial PDF, not a PDF missing a card. The run holds in
  `awaiting_cards` and the final confirmation is refused *naming the card*, because "409
  Conflict" is not something a user can act on (FR-037, SC-008).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES, make_card_image

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: Captain America's nemesis minion, at position 28 with no reprint link anywhere — so
#: removing its scan leaves the cascade nothing to fall back to.
BARON_ZEMO = "03028"
BARON_ZEMO_SCAN = (
    f"{CAP_FOLDER}/Captain America Nemesis/Captain America Nemesis_Baron Zemo_Minion_28.tiff"
)

VISION_FOLDER = "Heros/Vision_Vision"
#: One code, two faces, no linked card, and not the identity card (research R12).
INTANGIBLE = "26002"
INTANGIBLE_FRONT = f"{VISION_FOLDER}/Vision_Intangible_Upgrade_2a.tiff"
INTANGIBLE_BACK = f"{VISION_FOLDER}/Vision_Intangible_Upgrade_2b.tiff"

#: Small enough to build in milliseconds, large enough to clear the 300 DPI floor at final
#: size, so these files could genuinely be printed rather than only parsed.
IMAGE_W, IMAGE_H = 780, 1122


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
    """A writable copy of the derived fixture library.

    Hardlinked rather than copied: 678 files and 21 MB per test is a cost worth avoiding,
    and every test here only ever *removes* a link, which cannot touch the original. The
    session-scoped `scan_library` is deliberately read-only — FR-001's whole point is that
    this feature never writes to a scan library.
    """
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def resolve(client, library: Path, folder: str, pack_code: str | None = None) -> dict:
    """Start a run and take it through pack confirmation to a resolved report."""
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


def gap_for(run: dict, card_code: str) -> list[dict]:
    return [u for u in run["unresolved"] if u["card_code"] == card_code]


# ------------------------------------------------------------ every group, the same bar


def test_a_nemesis_card_resolves_when_its_scan_is_there(client, writable_library):
    """The control. Without it, the test below passes on a library that never worked."""
    run = resolve(client, writable_library, CAP_FOLDER)
    assert not gap_for(run, BARON_ZEMO)


def test_a_missing_nemesis_card_stops_the_run_by_name(client, writable_library):
    """FR-015c, FR-017 — the nemesis set is not a lesser part of the pack."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)

    (gap,) = gap_for(run, BARON_ZEMO)
    assert gap["card_name"] == "Baron Zemo"
    assert gap["group"] == "nemesis"
    assert run["state"] == "awaiting_cards"


def test_the_gap_says_where_the_tool_looked(client, writable_library):
    """SC-008 — a report the user cannot act on is a failure they have to diagnose."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    (gap,) = gap_for(run, BARON_ZEMO)
    assert gap["searched"]
    assert any("28" in line for line in gap["searched"])


# ------------------------------------------------------------------ a missing back face


@pytest.fixture
def vision_library(tmp_path) -> Path:
    """A library holding one genuinely double-sided player card, and nothing else.

    Purpose-built rather than derived: Vision is not one of the ten acceptance heroes, and
    what is under test needs exactly two files present or absent — everything else in the
    pack going unresolved would only make the assertion harder to read.
    """
    root = tmp_path / "vision-library"
    for rel in (INTANGIBLE_FRONT, INTANGIBLE_BACK):
        make_card_image(root / rel, Path(rel).stem, width=IMAGE_W, height=IMAGE_H)
    return root


def test_a_double_sided_player_card_resolves_both_faces(client, vision_library):
    """The control, and FR-015f's premise: both faces are found when both are there."""
    run = resolve(client, vision_library, VISION_FOLDER, pack_code="vision")
    sides = {r["side"] for r in run["report"]["resolutions"] if r["card_code"] == INTANGIBLE}
    assert sides == {"front", "back"}
    assert not gap_for(run, INTANGIBLE)


@pytest.mark.parametrize(
    ("missing", "side"),
    [(INTANGIBLE_BACK, "back"), (INTANGIBLE_FRONT, "front")],
    ids=["back-face-missing", "front-face-missing"],
)
def test_a_missing_face_stops_the_run_whichever_side_it_is(client, vision_library, missing, side):
    """FR-015f — the back is held to exactly the bar the front is held to.

    Parametrized over both sides deliberately. The two cases are the same requirement, and
    an implementation that checks only fronts passes one of them.
    """
    (vision_library / missing).unlink()
    run = resolve(client, vision_library, VISION_FOLDER, pack_code="vision")

    gaps = gap_for(run, INTANGIBLE)
    assert [g["side"] for g in gaps] == [side]
    assert gaps[0]["card_name"] == "Intangible"
    assert run["state"] == "awaiting_cards"


def test_a_card_missing_one_face_is_never_printed_with_the_other(client, vision_library):
    """The whole point of FR-015f. A proxy printed front-only is a blank card.

    Feature 001 already holds that a double-sided card missing its second face cannot be
    printed usefully; FR-048 adopts that rule rather than relaxing it.
    """
    (vision_library / INTANGIBLE_BACK).unlink()
    run = resolve(client, vision_library, VISION_FOLDER, pack_code="vision")

    confirmation = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmation.status_code == 409
    assert client.get(f"/api/assemblies/{run['id']}/document").status_code == 409


# ------------------------------------------------------------------ nothing is written


def test_an_incomplete_run_refuses_to_render_and_names_the_card(client, writable_library):
    """FR-017, FR-037, SC-006 — the refusal is actionable or it is not a refusal.

    "409 Conflict" tells the user to go and read the code. Naming Baron Zemo tells them to
    go and find one file.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)

    confirmation = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmation.status_code == 409
    detail = confirmation.json()["detail"]
    assert "Baron Zemo" in detail


def test_no_pdf_reaches_the_disk_while_a_card_is_missing(client, writable_library, state_root):
    """SC-006 — not a partial PDF, not a PDF one card short. Nothing.

    Asserted against the filesystem rather than against the response, because the failure
    being guarded is a document that exists without anyone having agreed to it.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert list(state_root.rglob("*.pdf")) == []


def test_the_run_stays_legible_as_incomplete_when_it_is_read_back(client, writable_library):
    """FR-030b — a user returning a week later must not have to rediscover the gap."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)

    again = client.get(f"/api/assemblies/{run['id']}").json()
    assert [u["card_code"] for u in again["unresolved"]] == [
        u["card_code"] for u in run["unresolved"]
    ]
    assert again["report"]["cards_printed"] < again["report"]["cards_in_pack"]
