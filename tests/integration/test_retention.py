"""T105 — deleting a run and reclaiming disk are different acts (FR-026g, FR-026g1, SC-006h).

001 measured roughly 202 MB for a single deck's PDF, and FR-026f keeps every one of them, so
this is the feature's answer to "how do I get that space back". It answers with two separate
acts, and everything here exists to hold them apart:

    DELETE /api/assemblies/{id}   throw away a deck attempt   → its uploads, and a saved PDF
    DELETE /api/pdfs/{id}         reclaim the disk            → the bytes

**These assertions are about freed bytes, not absent files**, because at 202 MB the two are
different claims and only one of them is the requirement. A standard PDF has two names — the
pack's, in `pdfs/standard/`, and a hard link inside each run that produced it — so a test
checking `runs/<id>/output.pdf` is gone would pass while the disk is exactly as full as it
was. `held_bytes` counts each inode once, which is what the operating system does.

The row an implementation gets wrong is deleting a run that built a **standard** PDF. That
file belongs to the pack (FR-026g1): fold the two acts together and discarding one run of
Captain America revokes FR-026f's guarantee for every other run of it, from a button whose
label says nothing of the kind.
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

#: Heroes that resolve every card against the derived fixture, so a run over either reaches
#: `complete` untouched by the user — which is what makes its PDF the pack's *standard* one.
THOR_FOLDER = ACCEPTANCE_HEROES["thor"]
WASP_FOLDER = ACCEPTANCE_HEROES["wsp"]


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


def held_bytes(root: Path) -> int:
    """What this tree actually costs the filesystem — each inode counted once.

    Hard links are the whole mechanism here (`pdfs.py`: "refcounting is the kernel's"), so
    summing `st_size` per *path* would count a shared PDF once per name and report a
    deletion that freed nothing as having freed 202 MB.
    """
    seen: set[tuple[int, int]] = set()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        info = path.stat()
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += info.st_size
    return total


def library_state(root: Path) -> dict[str, tuple[int, float]]:
    """Every file's size and mtime, so FR-001 can be asserted rather than assumed."""
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


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


def finish_standard(client, library: Path, folder: str) -> dict:
    """A run nobody customized: confirming the tool's own decklist candidate is not
    customization (FR-013e), so this still produces the pack's standard PDF."""
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


def finish_saved(client, library: Path, folder: str, name: str) -> dict:
    """A customized run — it skipped the decklist — so its PDF is the user's, under their
    name, and is never the pack's standard one (FR-026i)."""
    run = start(client, library, folder)
    skipped = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        json={"action": "skip"},
        headers={"If-Match": str(run["version"])},
    )
    assert skipped.status_code == 200, skipped.text
    run = skipped.json()
    assert run["state"] == "ready", run["state"]
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={"save_as": name},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    return done.json()


def stored_size(client, pdf_id: str) -> int:
    return next(p["byte_size"] for p in client.get("/api/pdfs").json()["pdfs"] if p["id"] == pdf_id)


# ------------------------------------------------------ US5 scenario 6: the standard PDF


def test_deleting_a_run_does_not_reclaim_the_packs_standard_pdf(
    client, state_root, writable_library
):
    """FR-026g1. The user must be able to predict whether discarding a run frees 202 MB.

    It never does, for a standard PDF — so what is asserted is the *number*: after the
    delete, the disk holds everything it held minus the run's own files, and the PDF's bytes
    are not among them.
    """
    first = finish_standard(client, writable_library, THOR_FOLDER)
    second = finish_standard(client, writable_library, THOR_FOLDER)
    assert second["pdf_id"] == first["pdf_id"], "both runs share the pack's standard PDF"

    pdf_bytes = stored_size(client, first["pdf_id"])
    before = held_bytes(state_root)

    deleted = client.delete(
        f"/api/assemblies/{first['id']}", headers={"If-Match": str(first["version"])}
    )
    assert deleted.status_code == 204, deleted.text
    after = held_bytes(state_root)

    assert before - after < pdf_bytes, "the PDF's bytes must still be held"
    # And the other run is untouched by it, which is the guarantee FR-026g1 protects.
    assert client.get(f"/api/assemblies/{second['id']}/document").status_code == 200
    assert stored_size(client, first["pdf_id"]) == pdf_bytes


def test_deleting_the_standard_pdf_reclaims_its_space(client, state_root, writable_library):
    """US5 scenario 6a. The bytes go back to the operating system.

    Both runs are deleted first so the stored copy holds the last name: reclamation is the
    link count reaching zero, and asserting it any other way would assert a `unlink` call
    rather than free disk.
    """
    first = finish_standard(client, writable_library, THOR_FOLDER)
    second = finish_standard(client, writable_library, THOR_FOLDER)
    pdf_bytes = stored_size(client, first["pdf_id"])

    for run in (first, second):
        assert (
            client.delete(
                f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"])}
            ).status_code
            == 204
        )

    before = held_bytes(state_root)
    assert client.delete(f"/api/pdfs/{first['pdf_id']}").status_code == 204
    after = held_bytes(state_root)

    assert before - after == pdf_bytes
    assert first["pdf_id"] not in {p["id"] for p in client.get("/api/pdfs").json()["pdfs"]}


def test_the_next_assembly_rebuilds_after_the_standard_pdf_is_reclaimed(client, writable_library):
    """US5 scenario 6b. Reclaiming space is never a refusal to print that pack again."""
    first = finish_standard(client, writable_library, THOR_FOLDER)
    assert client.delete(f"/api/pdfs/{first['pdf_id']}").status_code == 204

    rebuilt = finish_standard(client, writable_library, THOR_FOLDER)
    assert rebuilt["reused"] is False
    assert client.get(f"/api/assemblies/{rebuilt['id']}/document").status_code == 200


# --------------------------------------------------------- US5 scenario 5: the saved PDF


def test_deleting_a_run_reclaims_the_saved_pdf_it_named(client, state_root, writable_library):
    """The other half of FR-026g1: a saved PDF belongs to the run, so both names go.

    This is why the two acts are separable rather than simply distinct — the *same* delete
    frees 202 MB here and nothing in `test_deleting_a_run_does_not_reclaim_the_packs_...`,
    and the difference is which kind of PDF the run produced.
    """
    run = finish_saved(client, writable_library, WASP_FOLDER, "Wasp — no deck list")
    pdf_bytes = stored_size(client, run["pdf_id"])
    before = held_bytes(state_root)

    deleted = client.delete(
        f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"])}
    )
    assert deleted.status_code == 204, deleted.text

    assert before - held_bytes(state_root) >= pdf_bytes
    assert run["pdf_id"] not in {p["id"] for p in client.get("/api/pdfs").json()["pdfs"]}
    assert client.get(f"/api/pdfs/{run['pdf_id']}/document").status_code == 404


def test_deleting_a_saved_pdf_leaves_other_runs_alone(client, writable_library):
    """One user's named copy is not the other's. Deleting mine cannot cost you yours."""
    mine = finish_saved(client, writable_library, WASP_FOLDER, "Wasp — mine")
    yours = finish_saved(client, writable_library, WASP_FOLDER, "Wasp — yours")
    assert mine["pdf_id"] != yours["pdf_id"]

    assert client.delete(f"/api/pdfs/{mine['pdf_id']}").status_code == 204
    assert client.get(f"/api/assemblies/{yours['id']}/document").status_code == 200
    assert client.get(f"/api/pdfs/{yours['pdf_id']}/document").status_code == 200


# ---------------------------------------------------------------- the uploads, and FR-001


def test_deleting_a_run_reclaims_its_uploads(client, state_root, writable_library, tmp_path):
    """FR-026e's bytes are private to the run and go with it."""
    (writable_library / f"{THOR_FOLDER}/Thor Decklist.tiff").unlink()
    run = start(client, writable_library, THOR_FOLDER)

    payload = _card_bytes()
    supplied = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        files={"file": ("Thor from Hall of Heroes.tiff", payload, "application/octet-stream")},
        headers={"If-Match": str(run["version"])},
    )
    assert supplied.status_code == 200, supplied.text
    run = supplied.json()

    before = held_bytes(state_root)
    deleted = client.delete(
        f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"])}
    )
    assert deleted.status_code == 204, deleted.text
    assert before - held_bytes(state_root) >= len(payload)


def test_no_deletion_ever_touches_the_scan_library(client, writable_library):
    """FR-001, restated where it is most at risk.

    The library is a synced Drive folder, so a write here does not stay local — it
    propagates. Every act in this file is asserted against the whole tree's sizes and
    mtimes, because "we only call unlink on the state directory" is a claim about code and
    this is a claim about the user's data.
    """
    before = library_state(writable_library)

    standard = finish_standard(client, writable_library, THOR_FOLDER)
    saved = finish_saved(client, writable_library, WASP_FOLDER, "Wasp — a copy")
    for run in (standard, saved):
        assert (
            client.delete(
                f"/api/assemblies/{run['id']}", headers={"If-Match": str(run["version"])}
            ).status_code
            == 204
        )
    for stored in client.get("/api/pdfs").json()["pdfs"]:
        assert client.delete(f"/api/pdfs/{stored['id']}").status_code == 204

    assert library_state(writable_library) == before


def _card_bytes() -> bytes:
    import io

    from PIL import Image

    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

    buffer = io.BytesIO()
    Image.new("RGB", (LIBRARY_IMAGE_W, LIBRARY_IMAGE_H), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()
