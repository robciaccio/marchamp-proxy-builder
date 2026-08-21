"""Paper size and fit mode reach the document (FR-009c, FR-014).

The pack path shipped with these fields on the API and no way to set them from the wizard,
so every pack anyone printed was Letter and Crop — cropped about 1.2 mm top and bottom
without being asked, with A4 unreachable. Noticed in real use, 2026-08-20.

The wizard half is asserted in `test_web_ui.py`. This is the other half: that the values a
client sends are actually carried through to a different document, so wiring the controls up
is worth doing. A run records both when it is created and nothing changes them afterwards,
which is why they are read back off the run rather than off anything transient.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def build(client, library: Path, **options) -> tuple[dict, bytes]:
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(library), "hero_folder": THOR_FOLDER, **options},
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
    finished = done.json()
    document = client.get(f"/api/assemblies/{finished['id']}/document")
    assert document.status_code == 200
    return finished, document.content


def test_the_defaults_are_still_letter_and_crop(client, scan_library):
    """Unchanged for a client that sends neither — the wizard is what changed, not the API."""
    run, _ = build(client, scan_library)
    assert run["page_size"] == "LETTER"
    assert run["fit_mode"] == "CROP"


def test_a4_is_reachable_and_produces_a_different_document(client, scan_library):
    """The gap that had no workaround: nothing in the interface could ask for A4."""
    letter, letter_pdf = build(client, scan_library)
    a4, a4_pdf = build(client, scan_library, page_size="A4")

    assert a4["page_size"] == "A4"
    assert a4["report"]["page_count"] == letter["report"]["page_count"], (
        "both sheets carry nine cards, so the page count should not move — if it does, the "
        "geometry changed rather than the paper"
    )
    assert a4_pdf != letter_pdf


@pytest.mark.parametrize("mode", ["FIT", "STRETCH"])
def test_each_fit_mode_produces_its_own_document(client, scan_library, mode):
    """FR-014 — the three modes are three different compromises, not a label.

    A user told that Stretch "distorts the art" and Crop "trims 1.2 mm" is entitled to have
    the choice mean something; asserting the bytes differ is the cheapest way to know it
    reached the renderer rather than being recorded and ignored.
    """
    crop, crop_pdf = build(client, scan_library)
    chosen, chosen_pdf = build(client, scan_library, fit_mode=mode)

    assert chosen["fit_mode"] == mode
    assert chosen_pdf != crop_pdf


def test_the_choice_survives_being_read_back(client, scan_library):
    """FR-026b — a run reopened later reports what it was built with.

    The report is the only thing that can tell a cropped sheet from a fitted one after the
    fact, and a run that forgot would leave the user unable to reproduce their own print.
    """
    run, _ = build(client, scan_library, page_size="A4", fit_mode="STRETCH")

    reopened = client.get(f"/api/assemblies/{run['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["page_size"] == "A4"
    assert reopened.json()["fit_mode"] == "STRETCH"
