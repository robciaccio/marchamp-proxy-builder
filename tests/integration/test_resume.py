"""T096/T100 — a run outlives the process that started it (FR-026b, FR-026f, SC-006f).

This feature's first durable state exists for one reason: a pack is 56–60 physical cards and
the library will be short of some of them. Going to find one takes longer than a browser tab
survives, so a run that forgot its folder, its pack, and its thirty-nine other resolutions
while the user went looking for the fortieth would be a wizard nobody uses twice.

Three properties, each a different way the durability could be hollow:

- **Everything the run needs is on disk, not in the process.** The restart here is real — the
  first `TestClient` is closed and a second app is built over the same state directory — so a
  value cached in a module-level dict would fail this and only this.
- **The pinned snapshot revision survives too** (FR-045). A resumed run resolving against
  newer card data would change quantities under resolutions the user already made, which is
  worse than refusing, because nothing about it is visible.
- **A folder that has gone is reported against the run** (FR-026f). Naming the folder once is
  actionable; forty cards that "cannot be found" is the same fact rendered unusable — and a
  *finished* run must not care at all, because it holds its own PDF.
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
from marchamp.store.runs import RunState
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]
#: Thor resolves every card against the derived fixture and holds a decklist scan, so it is
#: the hero this file uses whenever a *finished* run is what is under test. `cap` cannot
#: finish here — `Followed` lives in Spider-Ham's pack, which T005 does not derive.
THOR_FOLDER = ACCEPTANCE_HEROES["thor"]

#: `cap`'s standing gap against the fixture library, present before this file deletes
#: anything (see `test_assemble_cap.py`). Named so the assertions below can subtract it
#: rather than quietly widening to "at least these".
FOLLOWED = "03032"

#: Two Captain America nemesis cards with no reprint link anywhere, so deleting their scans
#: leaves the cascade nothing to fall back to and the run reports both by name.
BARON_ZEMO = "03028"
BARON_ZEMO_SCAN = (
    f"{CAP_FOLDER}/Captain America Nemesis/Captain America Nemesis_Baron Zemo_Minion_28.tiff"
)
HYDRA_SOLDIER = "03029"
HYDRA_SOLDIER_SCAN = (
    f"{CAP_FOLDER}/Captain America Nemesis/Captain America Nemesis_Hydra Soldier_Minion_29.tiff"
)


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def app_factory(state_root, upstream_transport, monkeypatch):
    """Build the application afresh, as many times as a test needs.

    A fixture yielding a *factory* rather than a client, because the restart is the thing
    under test: a single long-lived client would exercise nothing this file claims.
    """
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)

    def build() -> TestClient:
        settings = Settings(image_dir=None, catalog_path=None, state_dir=state_root)
        return TestClient(create_app(settings))

    return build


@pytest.fixture
def writable_library(tmp_path, scan_library) -> Path:
    """A hard-linked copy, so a test can delete a scan without touching the fixture."""
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def card_bytes(width: int = LIBRARY_IMAGE_W, height: int = LIBRARY_IMAGE_H) -> bytes:
    """A generated card face as TIFF bytes. Never a real scan (FR-038a)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def start_and_confirm(client: TestClient, library: Path, folder: str = CAP_FOLDER) -> dict:
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


def unresolved_codes(run: dict) -> set[str]:
    return {u["card_code"] for u in run["unresolved"]}


# ------------------------------------------------------------------- T096, SC-006f


def test_a_run_with_cards_unresolved_survives_a_restart(app_factory, writable_library):
    """SC-006f: the folder, the pack, the revision, the resolutions, and the report.

    Asserted field by field rather than by comparing the two responses wholesale. A single
    `before == after` would pass just as happily against a service that lost all of it and
    then re-derived all of it — which is a different guarantee, and not the one FR-026b
    makes, because re-deriving needs the library to still be there.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    (writable_library / HYDRA_SOLDIER_SCAN).unlink()

    with app_factory() as client:
        run = start_and_confirm(client, writable_library)
        assert run["state"] == "awaiting_cards"
        assert unresolved_codes(run) == {BARON_ZEMO, HYDRA_SOLDIER, FOLLOWED}

        supplied = client.post(
            f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/image",
            files={"file": ("zemo.tiff", card_bytes(), "application/octet-stream")},
            data={"side": "front"},
            headers={"If-Match": str(run["version"])},
        )
        assert supplied.status_code == 200, supplied.text
        before = supplied.json()

    # The process is gone. Everything below comes off the disk.
    with app_factory() as client:
        after = client.get(f"/api/assemblies/{run['id']}").json()

    assert after["library_root"] == before["library_root"]
    assert after["hero_folder"] == CAP_FOLDER
    assert after["identification"]["pack_code"] == "cap"
    assert after["identification"]["confirmed"] is True
    assert after["snapshot_revision"] == before["snapshot_revision"]
    assert after["state"] == "awaiting_cards"
    # Only the cards still outstanding are asked about; the answer already given stands.
    assert unresolved_codes(after) == {HYDRA_SOLDIER, FOLLOWED}
    assert after["report"]["cards_in_pack"] == before["report"]["cards_in_pack"]
    manual = [r for r in after["report"]["resolutions"] if r["provenance"] == "manual"]
    assert [r["card_code"] for r in manual] == [BARON_ZEMO]
    assert manual[0]["source"] == "upload"


def test_a_resumed_run_can_be_finished_from_where_it_was_left(app_factory, writable_library):
    """The point of resuming: the second card is answered against the restarted process."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    (writable_library / HYDRA_SOLDIER_SCAN).unlink()

    with app_factory() as client:
        run = start_and_confirm(client, writable_library)
        supplied = client.post(
            f"/api/assemblies/{run['id']}/cards/{BARON_ZEMO}/image",
            files={"file": ("zemo.tiff", card_bytes(), "application/octet-stream")},
            headers={"If-Match": str(run["version"])},
        )
        assert supplied.status_code == 200, supplied.text

    with app_factory() as client:
        run = client.get(f"/api/assemblies/{run['id']}").json()
        for code, name in ((HYDRA_SOLDIER, "hydra.tiff"), (FOLLOWED, "followed.tiff")):
            answered = client.post(
                f"/api/assemblies/{run['id']}/cards/{code}/image",
                files={"file": (name, card_bytes(), "application/octet-stream")},
                headers={"If-Match": str(run["version"])},
            )
            assert answered.status_code == 200, answered.text
            run = answered.json()

    assert run["unresolved"] == []
    assert run["state"] == "awaiting_cards"  # the decklist candidate is still a question


# --------------------------------------------------------- T100, FR-026f, SC-006h


def test_a_resumed_run_whose_library_has_gone_reports_it_against_the_run(
    app_factory, writable_library
):
    """One sentence naming the folder — not forty cards that stopped resolving.

    The distinction is the whole requirement. Both renderings contain the same fact; only one
    of them tells the user the mount is down, and the other buries it under a wave of card
    names that will all come back the moment the drive reappears.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()

    with app_factory() as client:
        run = start_and_confirm(client, writable_library)
        assert run["state"] == "awaiting_cards"
        assert unresolved_codes(run) == {BARON_ZEMO, FOLLOWED}

    shutil.rmtree(writable_library)

    with app_factory() as client:
        resumed = client.get(f"/api/assemblies/{run['id']}")

    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["library_problem"], "the run must say its library is unreachable"
    assert str(writable_library) in body["library_problem"]
    # Not re-reported as newly missing cards: the gap the user was already working on is
    # the only one named, and it has not multiplied.
    assert unresolved_codes(body) == {BARON_ZEMO, FOLLOWED}
    assert body["state"] == "awaiting_cards"


def test_a_finished_run_downloads_its_pdf_with_the_library_gone(app_factory, writable_library):
    """FR-026f, SC-006h — a finished run depends on nothing outside itself."""
    with app_factory() as client:
        run = start_and_confirm(client, writable_library, THOR_FOLDER)
        assert run["unresolved"] == [], run["unresolved"]
        if run["state"] != "ready":
            # A decklist candidate the tool proposed still holds the run (FR-013d).
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
        assert done.json()["state"] == "complete"
        first = client.get(f"/api/assemblies/{run['id']}/document")
        assert first.status_code == 200

    shutil.rmtree(writable_library)

    with app_factory() as client:
        body = client.get(f"/api/assemblies/{run['id']}").json()
        again = client.get(f"/api/assemblies/{run['id']}/document")

    assert again.status_code == 200
    assert again.content == first.content
    assert again.headers["content-type"] == "application/pdf"
    # A finished run is not troubled by the mount at all — it never reads it again.
    assert body["library_problem"] is None


# ------------------------------------------------- T097, the crash-recovery half


@pytest.fixture
def run_store(state_root):
    """Reach into the durable record directly, to park a run where a crash would."""
    from marchamp.store.layout import StateLayout
    from marchamp.store.runs import RunStore

    return RunStore(StateLayout(state_root))


@pytest.mark.parametrize(
    ("crashed_in", "resumes_as"),
    [
        # The PDF is linked to the run only after `compose` returns, so a crashed render
        # left nothing behind. Back to `ready` — the run is not wrong, it is unfinished.
        ("rendering", "ready"),
        # Crashed before there was a pack to resume toward. FR-036 wants that stated.
        ("identifying", "failed"),
    ],
)
def test_a_run_the_process_died_inside_is_recovered(
    app_factory, writable_library, run_store, crashed_in, resumes_as
):
    """The three transient states are the ones nobody will ever move a run out of.

    `identifying`, `resolving`, and `rendering` are entered by a request and left by the
    same request. If that request dies, no later one is coming: without this, the run sits
    looking busy forever and the user's only recourse is to start again — which is the
    failure durable state exists to prevent.
    """
    with app_factory() as client:
        run = start_and_confirm(client, writable_library, THOR_FOLDER)

    record = run_store.read(run["id"])
    record.state = RunState(crashed_in)
    run_store.write(record)

    with app_factory() as client:
        resumed = client.get(f"/api/assemblies/{run['id']}").json()

    assert resumed["state"] == resumes_as


def test_a_run_that_died_resolving_resolves_again(app_factory, writable_library, run_store):
    """Safe to repeat: the cascade is a read of the library, and the user's own answers
    are laid back over it rather than recomputed."""
    with app_factory() as client:
        run = start_and_confirm(client, writable_library, THOR_FOLDER)

    record = run_store.read(run["id"])
    record.state = RunState.RESOLVING
    record.report = {}
    run_store.write(record)

    with app_factory() as client:
        resumed = client.get(f"/api/assemblies/{run['id']}").json()

    assert resumed["state"] in ("awaiting_cards", "ready")
    assert resumed["report"]["cards_in_pack"] == run["report"]["cards_in_pack"]


def test_a_run_that_died_resolving_is_not_demoted_by_an_unreachable_library(
    app_factory, writable_library, run_store
):
    """A mount being down must never cost the user the run.

    Re-resolving against a library that is not there would report every card as missing and
    overwrite a good report with that — the exact wave FR-026f exists to prevent, arriving
    by the back door.
    """
    with app_factory() as client:
        run = start_and_confirm(client, writable_library, THOR_FOLDER)

    record = run_store.read(run["id"])
    record.state = RunState.RESOLVING
    run_store.write(record)
    shutil.rmtree(writable_library)

    with app_factory() as client:
        resumed = client.get(f"/api/assemblies/{run['id']}").json()

    assert resumed["state"] == "resolving"
    assert resumed["library_problem"]
    assert resumed["report"]["cards_in_pack"] == run["report"]["cards_in_pack"]
