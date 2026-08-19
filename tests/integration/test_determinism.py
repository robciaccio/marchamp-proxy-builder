"""T111 — the same library and the same snapshot produce the same bytes (FR-045, SC-007).

**Serving a stored PDF twice proves nothing.** FR-026h's reuse means the second confirmation
of a pack usually returns the file the first one wrote, and a determinism test that let that
happen would be comparing a file to itself — it would pass on a renderer that embedded the
wall clock in every page. So reuse is taken off the table here by giving each run its own
state directory: two independent installations of the application, each rendering from
scratch, each reaching for the same library and the same upstream fixture.

That is also why the assertion is *bytes* rather than page count or card list. Determinism is
what makes FR-026h's key sound in the first place: the key says "this pack, at this revision,
from these images", and reuse is only correct if that triple really does name one document.
A renderer that varied would make every stored PDF a lie about what a rebuild would give you,
and nothing downstream would notice.

Two things had to be true for this to be achievable and both are load-bearing elsewhere:
ReportLab's `invariant=1` normalises the document timestamp and object ids (`render.document`),
and `compute_revision` hashes the *reduced card records* rather than `Last-Modified`, so two
fetches of an unchanged pack agree on the revision (`upstream.snapshots`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]


def app_client(state_dir: Path) -> TestClient:
    """One installation of the application, with its own state and nothing configured."""
    return TestClient(create_app(Settings(image_dir=None, catalog_path=None, state_dir=state_dir)))


def render(client: TestClient, library: Path, folder: str = THOR_FOLDER) -> tuple[bytes, dict]:
    """Drive one run from naming a folder to holding the document."""
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
    run = confirmed.json()

    if run["decklist_candidate"] is not None:
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()

    assert run["state"] == "ready", f"run is {run['state']}, unresolved={run['unresolved']}"
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    finished = done.json()

    document = client.get(f"/api/assemblies/{finished['id']}/document")
    assert document.status_code == 200, document.text
    return document.content, finished


@pytest.fixture
def libraries(tmp_path: Path, scan_library: Path) -> tuple[Path, Path]:
    """The same library at two different paths.

    Not one path used twice: FR-026h deliberately keeps the library *root* out of the reuse
    key (SC-006h), and a determinism test that held the path fixed would not notice a
    renderer that had let an absolute path into the document. Hardlinked, so this costs
    milliseconds rather than 42 MB.
    """
    import os
    import shutil

    first = tmp_path / "library-a"
    second = tmp_path / "somewhere else" / "library-b"
    second.parent.mkdir(parents=True)
    shutil.copytree(scan_library, first, copy_function=os.link)
    shutil.copytree(scan_library, second, copy_function=os.link)
    return first, second


def test_two_independent_runs_produce_byte_identical_documents(
    tmp_path, patched_upstream, libraries
):
    """FR-045, SC-007 — with reuse structurally impossible, the bytes still match."""
    first_library, second_library = libraries

    with app_client(tmp_path / "state-a") as client:
        first_bytes, first_run = render(client, first_library)
    with app_client(tmp_path / "state-b") as client:
        second_bytes, second_run = render(client, second_library)

    assert not first_run["reused"] and not second_run["reused"], (
        "separate state directories must leave each run with an empty PDF store; a reused "
        "document would make this test compare a file with itself"
    )
    assert first_run["snapshot_revision"] == second_run["snapshot_revision"], (
        "the runs must have been built against the same card data, or byte equality would "
        "be asserting something else"
    )
    assert hashlib.sha256(first_bytes).hexdigest() == hashlib.sha256(second_bytes).hexdigest()
    assert first_bytes == second_bytes


def test_the_document_carries_no_path_from_the_machine_that_built_it(
    tmp_path, patched_upstream, libraries
):
    """The mechanism behind the equality above, asserted directly.

    Byte equality across two roots already implies it, but only as long as both roots happen
    to be the same length. Naming the property means a renderer that embedded the library
    path fails here with the reason rather than in a diff of two 40 MB blobs.
    """
    first_library, _ = libraries
    with app_client(tmp_path / "state") as client:
        document, _ = render(client, first_library)

    assert bytes(str(first_library), "utf-8") not in document
    assert bytes(str(tmp_path), "utf-8") not in document
