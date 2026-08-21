"""A card's own folder beats another hero's folder (FR-014, FR-021, FR-023, SC-005).

Asked by the user on 2026-08-20, looking at a real Wolverine report:

    Battle Fury (35015) — reprint: Heros/Odinson_Thor/Aggression_Battle Fury_Upgarde_18.tiff

while `Heros/Logan_Wolverine (u)/Aggression_Battle Fury_Upgrade.tif` sat unused. Six more
cards in that one run went the same way, borrowing Thor's, Shadowcat's or the Core Set's art
for cards the user had scanned from the Wolverine pack itself.

**Why it happened.** The local file carries no number, so no positional step can find it, and
the only step that could — the name match — ran *after* the reprint step. The reprint search
looks up the duplicated card's position in whatever folder holds it and finds Thor's at
position 18. First match wins, so the local scan never got a turn.

**Why the order changed.** The reprint step exists for cards the scanner *skipped* because
they were already in the Core Set (FR-014); that is what it is good at and it keeps that job.
It was never meant to outrank a scan of the very printing being asked for. The cascade already
draws this distinction on the positional side — `folder_position` before `library_position` —
and this applies the same principle to the name path, which is the half that was missing.

Reprints still beat a name match found *elsewhere* in the library, because that is a genuine
guess about another folder's file while `duplicate_of_code` is card data. Only the hero's own
folder is promoted.

The committed fixture library cannot show this on its own: neither Captain America's nor
Thor's folder holds a local scan of any card they borrow, which is exactly why those cards are
borrowed. So this test adds the one file that makes the case real.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: `Make the Call`, which cap prints two of and the Core Set ships three. Against the fixture
#: as committed it resolves by reprint from `Core Set/`; the user's Wolverine folder is the
#: shape where that is the wrong answer.
MAKE_THE_CALL = "03016"

#: Name-only, exactly like `Aggression_Battle Fury_Upgrade.tif`. No trailing number, so no
#: positional step can reach it and the name path is its only route.
LOCAL_SCAN = "Leadership_Make the Call_Event.tif"


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def card_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (LIBRARY_IMAGE_W, LIBRARY_IMAGE_H), (90, 20, 20)).save(buffer, format="TIFF")
    return buffer.getvalue()


@pytest.fixture
def library_with_local_scan(writable_library: Path) -> Path:
    """The fixture library, plus cap's own scan of a card it currently borrows."""
    (writable_library / CAP_FOLDER / LOCAL_SCAN).write_bytes(card_bytes())
    return writable_library


def resolutions(client, library: Path) -> dict[str, dict]:
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": CAP_FOLDER}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    return {r["card_code"]: r for r in confirmed.json()["report"]["resolutions"]}


def test_the_heros_own_scan_beats_a_reprint_from_another_folder(client, library_with_local_scan):
    """The reported case. The user scanned this pack; print this pack's card."""
    entry = resolutions(client, library_with_local_scan)[MAKE_THE_CALL]

    assert entry["file"] == f"{CAP_FOLDER}/{LOCAL_SCAN}", (
        f"borrowed {entry['file']!r} while the hero's own scan sat in the folder the user named"
    )
    assert entry["provenance"] == "folder_name"


def test_the_control_without_that_scan_still_borrows(client, writable_library):
    """Unchanged behaviour when the folder genuinely lacks the card.

    Without this, the test above would pass on a build that had simply broken the reprint
    step — and FR-014 is why eight of cap's cards print at all.
    """
    entry = resolutions(client, writable_library)[MAKE_THE_CALL]

    assert entry["provenance"] == "reprint"
    assert entry["file"].startswith("Core Set/")


def test_the_substitution_is_still_reported(client, library_with_local_scan):
    """SC-005 — a name match is not an exact positional hit, whichever folder it came from.

    Promoting it above the reprint step must not promote it to unremarkable: the file was
    matched on its name, the position was never checked, and the user is entitled to know.
    """
    entry = resolutions(client, library_with_local_scan)[MAKE_THE_CALL]

    assert entry["provenance"] != "folder_position"
    assert entry["note"], "a name match with no note is a silent substitution"
    assert "name" in entry["note"].lower()


def test_a_name_match_elsewhere_still_loses_to_a_reprint(client, writable_library):
    """The half that deliberately did not change.

    `Aspects/` holds cards by name with no position, and a match there is a guess about
    another folder's file. `duplicate_of_code` is card data. Only the hero's *own* folder was
    promoted, so a card the hero folder does not hold still prefers its reprint.
    """
    entry = resolutions(client, writable_library)["03021"]  # Energy, reprinted from Core Set

    assert entry["provenance"] == "reprint"
