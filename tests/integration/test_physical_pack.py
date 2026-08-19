"""T116 — print one pack and build the deck from paper (quickstart V12).

**The one criterion no automated test can carry.** SC-001 is five minutes of *user* time from
naming a folder to holding a printable PDF, and SC-002a ends with "a user can print that
hero, build the starter deck from the printed decklist, and play it". Neither claim is about
bytes. What this file does is the half a machine can do — drive the run against the real
library, time it, write the PDF somewhere a person can print it, and check the page count is
the fewest the card count allows — and then hand over to `physical-uat.md`, which is the
paper procedure: cut, sort from the report alone, build the deck from the printed decklist
card, play it.

Marked `physical`, so it never runs in CI. Point it at the library, and at somewhere to leave
the PDF:

```bash
MARCHAMP_REAL_LIBRARY="/Volumes/GoogleDrive/My Drive/Marvel Champions Scans" \\
MARCHAMP_UAT_OUTPUT="$HOME/Desktop/marchamp-uat" \\
    uv run pytest -m physical tests/integration/test_physical_pack.py -s
```

The measurements it records — the finished PDF's byte size and the wall clock from naming the
folder to holding it — go in `physical-uat.md` alongside the paper results. Recorded rather
than asserted: 001's SC-007 is knowingly missed at 48.9 s and 202 MB against a 30 s target,
measured and accepted because the tool is local-only, and a threshold here would either
restate that decision as a failure or be set loose enough to mean nothing. The number that
*is* a criterion is the user's five minutes, and most of that is the user.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from marchamp.layout.paginate import FACES_PER_PAGE
from tests.conftest import ACCEPTANCE_HEROES

pytestmark = pytest.mark.physical

LIBRARY_ENV = "MARCHAMP_REAL_LIBRARY"
OUTPUT_ENV = "MARCHAMP_UAT_OUTPUT"

#: Captain America, because V12 is written around it: its folder omits eight physical cards
#: that live in the Core Set, so the printed pack is also the evidence that the reprint
#: cascade produced cards a person can hold (FR-014, SC-005).
UAT_HERO = "cap"


@pytest.fixture
def real_library() -> Path:
    configured = os.environ.get(LIBRARY_ENV)
    if not configured:
        pytest.skip(f"set {LIBRARY_ENV} to the mounted scan library to run this")
    root = Path(configured).expanduser()
    if not root.is_dir():
        pytest.skip(f"{LIBRARY_ENV} is {root}, which is not a directory — is the drive mounted?")
    return root


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Where the PDF and the measurements are left.

    Defaults to the pytest temporary directory, which is fine for checking the assertions and
    useless for the paper half — a file the tester cannot find is a procedure they cannot
    carry out. The path is printed either way.
    """
    configured = os.environ.get(OUTPUT_ENV)
    out = Path(configured).expanduser() if configured else tmp_path / "uat"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def test_a_pack_prints_and_the_measurements_are_recorded(client, real_library, output_dir):
    """SC-001, SC-002a, SC-002b — the machine half of V12.

    The clock starts where the user starts: at naming a folder, not at the render call. Most
    of SC-001's five minutes is deciding, confirming, and waiting, and a timer around
    `compose` would measure the one part of it the user does not experience.
    """
    folder = ACCEPTANCE_HEROES[UAT_HERO]
    if not (real_library / folder).is_dir():
        pytest.skip(f"{folder} is not in this library")

    started = time.monotonic()

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
    run = confirmed.json()
    assert run["unresolved"] == [], (
        f"unresolved over the real library: {[u['card_code'] for u in run['unresolved']]}"
    )

    if run["decklist_candidate"] is not None:
        # FR-013d: the tool proposes, the user accepts. One click, and it catches a wrong
        # file at one page instead of forty. FR-013e: accepting is not customization.
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()

    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    finished = done.json()

    document = client.get(f"/api/assemblies/{finished['id']}/document")
    assert document.status_code == 200
    elapsed_s = time.monotonic() - started

    pdf_path = output_dir / f"{UAT_HERO}.pdf"
    pdf_path.write_bytes(document.content)

    report = finished["report"]
    measurements = {
        "hero_folder": folder,
        "pack_code": report["pack_code"],
        "snapshot_revision": finished["snapshot_revision"],
        "cards_printed": report["cards_printed"],
        "cards_in_pack": report["cards_in_pack"],
        "faces_printed": report["faces_printed"],
        "page_count": report["page_count"],
        "decklist_printed": report["decklist_printed"],
        "pdf_bytes": len(document.content),
        "pdf_megabytes": round(len(document.content) / 1_000_000, 1),
        "wall_clock_s": round(elapsed_s, 1),
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (output_dir / f"{UAT_HERO}-measurements.json").write_text(
        json.dumps(measurements, indent=2) + "\n"
    )

    print(f"\nPDF written to {pdf_path}")
    print(json.dumps(measurements, indent=2))
    print(
        "\nNow do the paper half: specs/002-starter-deck-assembly/physical-uat.md\n"
        "Copy the numbers above into its Measurements table."
    )

    # SC-002b: the fewest pages the card count allows. Asserted rather than recorded, because
    # unlike a duration it is exact — the groups pack together with no page break (FR-015d),
    # so adding the identity, the nemesis set and the decklist costs no page of its own.
    expected_pages = math.ceil(report["faces_printed"] / FACES_PER_PAGE)
    assert report["page_count"] == expected_pages, (
        f"{report['faces_printed']} faces at {FACES_PER_PAGE} per page needs "
        f"{expected_pages} pages, not {report['page_count']}. A page break between groups is "
        "the likely cause, and FR-015d forbids one"
    )

    # SC-002a: all four things, so the paper procedure has something to sort into.
    assert {r["group"] for r in report["resolutions"]} == {
        "player",
        "identity",
        "nemesis",
        "decklist",
    }
    assert report["omitted"] == []
    assert pdf_path.stat().st_size > 0
