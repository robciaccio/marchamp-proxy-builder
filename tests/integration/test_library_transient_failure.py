"""A library file that cannot be read *right now* must not be a 500 (FR-021, FR-026f).

Reported from real use on 2026-08-18, against a Google Drive library:

    File "src/marchamp/assembly/resolve.py", line 499, in _resolution
        content_digest=digest_of(Path(library_root) / ref),
    File "src/marchamp/assembly/resolve.py", line 193, in digest_of
        for block in iter(lambda: handle.read(_DIGEST_BLOCK), b""):
    TimeoutError: [Errno 60] Operation timed out

**The file was there and the mount was up.** Drive had not materialised that placeholder
yet, so the read blocked and gave up. The same run succeeded minutes later — the last line
of that log is a `200`. So this is the one condition FR-021 classifies as *retryable*, and
the asset adapter has always named it: `local_dir.open` catches `OSError` and raises
`AssetUnreadable`, with the comment "locked, permissions, still syncing".

`digest_of` is the single library read that does not go through the adapter, which is
exactly why it is the one that crashed.

Three things are asserted, and the second is the one that makes this a bug rather than an
inconvenience. A 500 tells the user nothing, so they cannot know that waiting fixes it —
the constitution requires a failure to name its specific cause and forbids surfacing one as
a generic error. And the third matters because a run wrecked by a transient read would turn
a 30-second Drive stall into lost work.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]

#: One scan in the folder, chosen because it resolves by exact position and is therefore
#: reached early — the failure must not depend on which card happens to be unlucky.
STALLED_SCAN = "Odinson_Thor_Hero_1a.tiff"


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


class DriveStall:
    """One file that times out on read, like an unmaterialised Drive placeholder.

    Patches `Path.open` rather than the digest function, so the test exercises the real
    read path and would still fail if the digest were computed some other way. `armed` is
    a switch because the interesting assertion is that the run *recovers* — the same file
    reads normally once Drive catches up.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
        self.filename = filename
        self.armed = True
        self.attempts = 0
        original = pathlib.Path.open

        def guarded(inner_self, *args, **kwargs):
            if inner_self.name == self.filename and self.armed:
                self.attempts += 1
                raise TimeoutError(60, "Operation timed out")
            return original(inner_self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "open", guarded)


@pytest.fixture
def drive_stall(monkeypatch: pytest.MonkeyPatch) -> DriveStall:
    return DriveStall(monkeypatch, STALLED_SCAN)


def start(client, library: Path) -> dict:
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": THOR_FOLDER}
    )
    assert created.status_code == 202, created.text
    return created.json()


def confirm(client, run: dict):
    return client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )


def test_a_scan_that_times_out_is_not_an_internal_server_error(client, scan_library, drive_stall):
    """The reported crash. A transient read is a condition, not a bug in the server."""
    run = start(client, scan_library)
    response = confirm(client, run)

    assert drive_stall.attempts > 0, "the stall never triggered, so this asserts nothing"
    assert response.status_code != 500, response.text
    assert response.status_code == 503, response.text


def test_the_failure_names_the_file_and_says_what_to_do(client, scan_library, drive_stall):
    """The constitution's fail-closed clause: name the specific cause, never a generic error.

    Without the filename the user cannot tell a syncing library from a corrupt scan, and
    without "try again" they have no reason to believe waiting helps — which, for the case
    that actually happened, is the entire remedy.
    """
    run = start(client, scan_library)
    detail = confirm(client, run).json()["detail"]

    assert STALLED_SCAN in detail, detail
    assert "again" in detail.lower(), detail
    assert "Traceback" not in detail and "Errno" not in detail, (
        "the message is for a person, not a copy of the stack"
    )


def test_the_run_recovers_by_being_reopened_once_the_file_reads(client, scan_library, drive_stall):
    """FR-026f, FR-026b — nothing is lost. A Drive stall must not cost the user their run.

    **This is the path that was a dead end.** `set_pack` records the user's decision and
    *then* resolves, so a stall during resolution leaves a run whose pack is already set:
    posting to `/pack` again is a legitimate `409`, and reopening the run is the only way
    forward. In the reported case reopening was the request that 500ed, so both routes were
    closed and the run looked permanently broken. It was not — the log's last line is a
    `200`, once Drive caught up.

    Resolution runs before the record is written, which is what makes recovery possible at
    all; that is asserted here so a refactor moving the write earlier fails loudly rather
    than silently trading a stall for lost work.
    """
    run = start(client, scan_library)
    assert confirm(client, run).status_code == 503

    # The pack decision survived, so this route is correctly closed now.
    assert confirm(client, run).status_code == 409

    drive_stall.armed = False  # Drive catches up
    reopened = client.get(f"/api/assemblies/{run['id']}")
    assert reopened.status_code == 200, reopened.text

    resumed = reopened.json()
    assert resumed["identification"]["pack_code"] == "thor"
    assert resumed["unresolved"] == []
    assert resumed["state"] in ("ready", "awaiting_cards"), resumed["state"]


def test_a_stall_while_rendering_is_also_not_a_500(client, scan_library, monkeypatch):
    """The same fault one step later, where the file is read a second time.

    Resolution digests every scan and the renderer then decodes them, so a library that
    stalls between the two produces this instead. It is the same condition and must read
    the same way; a 500 here would be the identical defect in the identical place.
    """
    run = start(client, scan_library)
    confirmed = confirm(client, run)
    assert confirmed.status_code == 202, confirmed.text
    run = confirmed.json()

    if run["decklist_candidate"] is not None:
        run = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        ).json()

    DriveStall(monkeypatch, STALLED_SCAN)
    response = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert response.status_code != 500, response.text
    assert response.status_code == 503, response.text
    assert STALLED_SCAN in response.json()["detail"]


# ------------------------- a folder the walk cannot read, reported rather than lost


def test_a_hero_folder_that_cannot_be_read_is_not_reported_as_matching_no_pack(
    client, scan_library, monkeypatch
):
    """The reported "not found, here are some alternatives" (2026-08-19).

    `os.walk` ignored `scandir` errors, so a stalled folder was simply absent from the index
    and identification said — correctly, given what it could see — that nothing matched. The
    user is then told to check filenames that were never wrong. Rebuilt from that folder's
    real names, Spider-Ham verifies against its pack at 0.95.

    The assertion that matters is the second one: a 503 naming the folder is a different
    sentence from `unidentified`, and only one of them is true.
    """
    import os

    original = os.scandir

    def guarded(path=".", *args, **kwargs):
        if Path(path).name == "Odinson_Thor":
            raise TimeoutError(60, "Operation timed out", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", guarded)

    created = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": THOR_FOLDER},
    )

    assert created.status_code == 503, created.text
    detail = created.json()["detail"]
    assert "Odinson_Thor" in detail, detail
    assert "again" in detail.lower(), detail
