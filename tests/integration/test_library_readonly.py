"""T120 — the library is never written to (FR-001, FR-008).

The highest-consequence guarantee in the feature, because of what the library actually is: a
synced Drive folder holding the only copy of scans that took days to make. A bug that writes
into it does not produce a bad PDF and a puzzled user — it propagates to every device on the
account within seconds, and the mistake is gone before anyone knows to look for it.

Everything in a run is arranged around that. The state directory refuses to sit inside a
named library (`config.StateDirectoryInsideLibrary`), uploads are content-addressed into the
run's own directory rather than dropped beside the scan they stand in for, and the asset
adapter reads through a store that has no write path for the library root at all.

None of which is worth much as an intention, so this drives a whole run — identify, confirm,
supply a file for one card, print without another, render, then throw the run away — and
compares the library before and against after: **the same files, the same sizes, the same
mtimes**. All three, because they fail differently. A new file is a write in the obvious
sense. A changed size is a rewrite. And an unchanged size with a moved mtime is the one a
person would never spot: a file opened for append and closed, or re-saved byte-identical by
an image library that "helpfully" normalised it on the way through.

The copy here is a real one rather than the hardlinked copy the other integration tests use.
Hardlinks share inodes with the committed fixture, so a test that *failed* would corrupt the
repository it was run in — and the whole point of this file is that it is the one place a
write is plausible.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from marchamp.api.app import create_app
from marchamp.config import Settings, StateDirectoryInsideLibrary
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: The card the derived fixture cannot resolve (T005 coverage, see `test_acceptance_heroes`).
#: Used here as the natural occasion for an upload rather than as a subject in its own right.
UPLOAD_CARD = "03032"

#: Printed without, so the omission path runs too. Its scan is removed from the *copy*
#: first, because an omission answers a gap and a card that resolved has no gap to answer —
#: which is FR-030a working, not an obstacle. A nemesis minion, since FR-030a's explicit act
#: applies to every group and this is the least plausible thing to leave out by accident.
OMIT_CARD = "03028"
OMIT_CARD_SCAN = (
    f"{CAP_FOLDER}/Captain America Nemesis/Captain America Nemesis_Baron Zemo_Minion_28.tiff"
)


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def client(state_root: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=state_root)
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def library(tmp_path: Path, scan_library: Path) -> Path:
    """A genuine copy — see the module docstring on why not hardlinks.

    One scan is removed so the run has something to omit. Done here rather than inside the
    test, so that the fingerprint is taken of the library the run is actually given: a
    deletion the *test* made is not a write the application made, and folding the two
    together would either hide a real write or report a false one.
    """
    root = tmp_path / "library"
    shutil.copytree(scan_library, root)
    (root / OMIT_CARD_SCAN).unlink()
    return root


def fingerprint(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under the root, by relative path, with its size and mtime in nanoseconds.

    Nanoseconds rather than seconds: a rewrite that lands inside the same second is exactly
    the write this test would otherwise miss, and the filesystems this runs on carry the
    resolution.
    """
    out: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return out


def card_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (LIBRARY_IMAGE_W, LIBRARY_IMAGE_H), (40, 18, 60)).save(buffer, format="TIFF")
    return buffer.getvalue()


def drive_a_whole_run(client: TestClient, library: Path, delete: bool = True) -> str:
    """Identify, confirm, omit, upload, render, delete. Every path that touches the library.

    `delete=False` stops before the last step, for the one test that needs to look at what
    the run wrote: discarding a customized run takes its uploads and its saved PDF with it
    (FR-026e, FR-026i), so afterwards there is nothing left to point at.
    """
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": CAP_FOLDER}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    run_id = run["id"]

    confirmed = client.post(
        f"/api/assemblies/{run_id}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    run = confirmed.json()

    omitted = client.post(
        f"/api/assemblies/{run_id}/cards/{OMIT_CARD}/omission",
        json={"acknowledged": True, "side": "front"},
        headers={"If-Match": str(run["version"])},
    )
    assert omitted.status_code == 200, omitted.text
    run = omitted.json()

    uploaded = client.post(
        f"/api/assemblies/{run_id}/cards/{UPLOAD_CARD}/image",
        files={"file": ("a rescan from my desktop.tiff", card_bytes(), "image/tiff")},
        data={"side": "front"},
        headers={"If-Match": str(run["version"])},
    )
    assert uploaded.status_code == 200, uploaded.text
    run = uploaded.json()

    if run["decklist_candidate"] is not None:
        decided = client.post(
            f"/api/assemblies/{run_id}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()

    assert run["state"] == "ready", f"{run['state']}: {run['unresolved']}"
    done = client.post(
        f"/api/assemblies/{run_id}/confirmation",
        json={"save_as": "cap, one card supplied and one left out"},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    finished = done.json()
    assert finished["state"] == "complete"
    assert client.get(f"/api/assemblies/{run_id}/document").status_code == 200

    if delete:
        deleted = client.delete(
            f"/api/assemblies/{run_id}", headers={"If-Match": str(finished["version"])}
        )
        assert deleted.status_code in (200, 204), deleted.text
    return run_id


def test_a_whole_run_leaves_every_file_in_the_library_exactly_as_it_found_it(client, library):
    """FR-001, FR-008 — the same files, the same sizes, the same mtimes.

    One assertion per failure mode rather than one comparison of the two dictionaries, so a
    failure says *which* kind of write happened. "The library changed" would send someone
    diffing 678 entries to learn what "a file was added" says in a line.
    """
    before = fingerprint(library)
    assert before, "the library fixture is empty, so this test asserts nothing"

    drive_a_whole_run(client, library)
    after = fingerprint(library)

    assert set(after) - set(before) == set(), "files were added to the library"
    assert set(before) - set(after) == set(), "files were removed from the library"
    assert {k: v[0] for k, v in after.items()} == {k: v[0] for k, v in before.items()}, (
        "a file in the library changed size"
    )
    changed = sorted(k for k in before if before[k][1] != after[k][1])
    assert changed == [], f"a file in the library was rewritten in place: {changed}"


def test_no_directory_is_created_in_the_library_either(client, library):
    """A run's own directory landing in the library would be handed to the sync client
    whether or not it ever held a file."""
    before = sorted(str(p.relative_to(library)) for p in library.rglob("*") if p.is_dir())
    drive_a_whole_run(client, library)
    after = sorted(str(p.relative_to(library)) for p in library.rglob("*") if p.is_dir())
    assert after == before


def test_the_uploaded_file_is_stored_in_the_run_not_beside_the_scan_it_replaces(
    client, library, state_root
):
    """FR-026e, research R9 — the mechanism behind the guarantee, named directly.

    Dropping the file next to the card it stands in for is the intuitive implementation and
    is the exact write FR-001 forbids. Asserting where the bytes *did* go means a change that
    reintroduced it fails with the reason rather than as a puzzling mtime.
    """
    run_id = drive_a_whole_run(client, library, delete=False)

    uploads = list((state_root / "runs" / run_id / "uploads").iterdir())
    assert len(uploads) == 1, "the supplied file is not in the run's own upload directory"
    assert not list(library.rglob("*.pdf")), "a PDF was written into the library"
    assert not list(library.rglob("run.json")), "a run record was written into the library"
    assert not list(library.rglob("*rescan*")), (
        "the uploaded file landed in the library — beside the scan it stands in for is the "
        "intuitive place to put it and the exact write FR-001 forbids"
    )


def test_a_state_directory_inside_the_library_is_refused_before_anything_is_written(
    library, monkeypatch
):
    """The structural half of FR-001, and the reason the checks above can stay simple.

    A state directory under the library would make every correct write a write into the
    user's Drive folder. It is refused when the run names its library — the first moment both
    paths are known (FR-005) — rather than being caught per write, which is what lets every
    write below it assume the two do not overlap.
    """
    monkeypatch.setenv("MARCHAMP_STATE_DIR", str(library / ".marchamp"))
    settings = Settings(image_dir=None, catalog_path=None, state_dir=library / ".marchamp")
    with pytest.raises(StateDirectoryInsideLibrary):
        settings.check_state_dir(library)
    # The symmetric mistake, which is the easier one to make: the library inside the state
    # directory. Same consequence, so the check refuses both.
    outside = Settings(image_dir=None, catalog_path=None, state_dir=library.parent)
    with pytest.raises(StateDirectoryInsideLibrary):
        outside.check_state_dir(library)
    assert not (library / ".marchamp").exists()
