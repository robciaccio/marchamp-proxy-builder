"""T121 — the ten acceptance heroes against the mounted scan library (SC-002, SC-003, SC-003c).

**This is SC-002 and SC-003's acceptance evidence.** `test_acceptance_heroes.py` runs the same
ten heroes over T005's derived fixtures and is the regression guard — it catches a resolver
change without the scans present, and it cannot discharge the criteria, because the fixtures
carry filenames over generated images and the criteria are about the real scans. SC-003b says
so explicitly and asks for both.

Marked `physical` and never run in CI, for the same reason the artwork is not in the
repository: neither the scans nor the Drive mount exist there. Point it at the library and
run it by hand:

```bash
MARCHAMP_REAL_LIBRARY="/Volumes/GoogleDrive/My Drive/Marvel Champions Scans" \\
    uv run pytest -m physical tests/integration/test_real_library.py
```

**It talks to the live MarvelCDB.** Deliberately: this is the only test that exercises the
client against the actual service rather than against a transport that agrees with it, so a
change upstream — a renamed field, a moved endpoint, a pack listing that no longer parses —
surfaces here rather than in front of a user. That makes conduct part of the test's design,
not a detail: one state directory for the whole module, so the pack index and the Core Set
are fetched once across all ten heroes rather than ten times, and the client's own one-second
floor does the rest (FR-041–FR-043).

**The assertion is stronger than the fixture run's**, and that is the entire point. Over the
fixtures, five cards across four heroes cannot resolve — a T005 coverage limit, listed there
and supplied by upload. Over the real library there is nothing to supply: every card in every
pack listing must resolve from the library alone, with no upload and no omission. A run that
needed one file would be SC-002's "no manual intervention" failing, and the fixture run cannot
see it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.assembly.decklist import HALL_OF_HEROES_URL
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

pytestmark = pytest.mark.physical

#: Where the Drive folder is mounted. Read from the environment rather than searched for:
#: the path differs per machine, and a test that went hunting the filesystem for card art is
#: a worse idea than a test that skips.
LIBRARY_ENV = "MARCHAMP_REAL_LIBRARY"

#: Measured 2026-08-17 (SC-002a). Eight of the ten folders hold a decklist scan.
HEROES_WITHOUT_A_DECKLIST_SCAN = frozenset({"hlk", "phoenix"})


@pytest.fixture(scope="module")
def real_library() -> Path:
    configured = os.environ.get(LIBRARY_ENV)
    if not configured:
        pytest.skip(f"set {LIBRARY_ENV} to the mounted scan library to run this")
    root = Path(configured).expanduser()
    if not root.is_dir():
        pytest.skip(f"{LIBRARY_ENV} is {root}, which is not a directory — is the drive mounted?")
    return root


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    """One installation for the whole module, so upstream is asked once, not ten times.

    Module-scoped for conduct rather than for speed: the pack index and the Core Set listing
    are the same for all ten heroes, and re-fetching them per test would be ten times the
    traffic for none of the information (FR-039, FR-043).
    """
    state = tmp_path_factory.mktemp("state")
    settings = Settings(image_dir=None, catalog_path=None, state_dir=state)
    assert settings.image_dir is None and settings.catalog_path is None, (
        "SC-003a: nothing about feature 001 may be configured for these paths"
    )
    with TestClient(create_app(settings)) as client:
        yield client


def hero_folder(library: Path, folder: str) -> str:
    if not (library / folder).is_dir():
        pytest.skip(f"{folder} is not in this library")
    return folder


@pytest.mark.parametrize(("pack_code", "folder"), sorted(ACCEPTANCE_HEROES.items()))
def test_each_hero_resolves_completely_from_the_real_library(
    client, real_library, pack_code, folder
):
    """SC-002, SC-003, SC-003c — every card in the pack listing, from the library alone.

    `unresolved == []` before any upload is the whole criterion. The four SC-002 heroes get
    there from their own folders plus reprint links; the four SC-003 heroes need the
    whole-library search and the name fallback; Wonder Man and Phoenix carry no usable
    positions at all and resolve almost entirely by name (FR-023). Same assertion, three
    quite different routes to it — which is why a weakened name match passes the others and
    fails these two.
    """
    created = client.post(
        "/api/assemblies",
        json={
            "library_root": str(real_library),
            "hero_folder": hero_folder(real_library, folder),
        },
    )
    assert created.status_code == 202, created.text
    run = created.json()

    assert run["identification"]["pack_code"] == pack_code, (
        f"{folder} identified as {run['identification']['pack_code']}"
    )

    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    run = confirmed.json()

    assert run["unresolved"] == [], (
        f"{pack_code} left {[u['card_code'] for u in run['unresolved']]} unresolved. Over the "
        "real library there is nothing to supply, so this is SC-002's 'no manual "
        "intervention' failing rather than a fixture-coverage gap"
    )
    report = run["report"]
    assert report["cards_printed"] == report["cards_in_pack"]

    has_scan = pack_code not in HEROES_WITHOUT_A_DECKLIST_SCAN
    assert (run["decklist_candidate"] is not None) is has_scan, (
        f"{pack_code}: decklist candidate {run['decklist_candidate']!r} contradicts what this "
        "folder was measured to hold on 2026-08-17 (SC-002a)"
    )
    if has_scan:
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()

    assert run["state"] == "ready", run["state"]
    assert run["customized"] is False, (
        "nothing was supplied or omitted, so this run must produce the pack's standard PDF"
    )

    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    finished = done.json()

    assert finished["state"] == "complete"
    assert finished["report"]["omitted"] == []
    assert finished["report"]["decklist_printed"] is has_scan
    assert finished["report"]["decklist_source_url"] == (None if has_scan else HALL_OF_HEROES_URL)

    document = client.get(f"/api/assemblies/{finished['id']}/document")
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF")


def test_the_library_is_not_written_to(client, real_library):
    """FR-001, FR-008 — asserted against the real thing, not a copy.

    `test_library_readonly.py` proves this over a copy and is the guard that runs in CI.
    This is the one that matters, because the failure it catches is irreversible: the folder
    is synced, and a write reaches every device on the account before anyone knows to look.

    Only the top level is fingerprinted rather than the whole tree. The real library is tens
    of gigabytes across thousands of files, and a `rglob` of it over a network mount would
    take longer than every other test in the suite put together — while a write the
    application made would land in a hero folder that the run above has already driven, and
    show up as a changed directory mtime here.
    """
    before = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(real_library.iterdir())
    }
    folder = hero_folder(real_library, ACCEPTANCE_HEROES["cap"])
    hero_before = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted((real_library / folder).iterdir())
    }

    created = client.post(
        "/api/assemblies", json={"library_root": str(real_library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text

    after = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(real_library.iterdir())
    }
    hero_after = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted((real_library / folder).iterdir())
    }
    assert after == before
    assert hero_after == hero_before
