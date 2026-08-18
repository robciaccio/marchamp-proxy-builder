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


# ------------------------------------------ T090: printing without a card, on the record


def card_bytes() -> bytes:
    """A generated card face as TIFF bytes. Never a real scan (FR-038a)."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (IMAGE_W, IMAGE_H), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def settle(client, run: dict) -> dict:
    """Answer everything the run is still waiting on *except* what a test omitted.

    Two things stand between a cap run and `ready`, neither of them what these tests are
    about. The derived fixture library is short of `Followed` (03032) — a T005 coverage
    limitation recorded in Phase 5's notes — and cap's folder holds a deck list scan, which
    holds the run until it is accepted (FR-013d). Supplying a file for the first and
    accepting the second leaves the omission under test as the only thing missing, which is
    what makes the card counts below say something exact.
    """
    while run["unresolved"]:
        gap = run["unresolved"][0]
        response = client.post(
            f"/api/assemblies/{run['id']}/cards/{gap['card_code']}/image",
            files={"file": (f"{gap['card_code']}.tiff", card_bytes(), "image/tiff")},
            data={"side": gap["side"]},
            headers={"If-Match": str(run["version"])},
        )
        assert response.status_code == 200, response.text
        run = response.json()
    if run["decklist_candidate"] is not None:
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()
    return run


def omit(client, run: dict, card_code: str, side: str = "front"):
    """The explicit act FR-030a requires, naming *this* card."""
    return client.post(
        f"/api/assemblies/{run['id']}/cards/{card_code}/omission",
        json={"acknowledged": True, "side": side},
        headers={"If-Match": str(run["version"])},
    )


def test_an_omitted_card_is_named_in_the_report(client, writable_library):
    """FR-030b, SC-006e — an incomplete pack is legible as incomplete, not merely short.

    Named in `omitted` and **nowhere else**: a card printed without is not a card printed,
    and listing it in both sections would leave the report contradicting itself about the
    same card.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    updated = omit(client, run, BARON_ZEMO).json()

    (entry,) = updated["report"]["omitted"]
    assert entry["card_code"] == BARON_ZEMO
    assert entry["card_name"] == "Baron Zemo"
    assert entry["group"] == "nemesis"
    assert entry["provenance"] == "omitted"
    assert BARON_ZEMO not in {r["card_code"] for r in updated["report"]["resolutions"]}


def test_an_omitted_card_is_counted_against_the_pack_listings_card_count(client, writable_library):
    """FR-030b, FR-018 — the pack is short by exactly the card that was left out.

    `cards_in_pack` comes from the pack listing and does not move; `cards_printed` counts
    what the entries actually say. A report where the two agreed after an omission would be
    claiming the pack is complete.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    before = run["report"]

    after = settle(client, omit(client, run, BARON_ZEMO).json())["report"]
    assert after["cards_in_pack"] == before["cards_in_pack"]
    assert after["cards_printed"] == after["cards_in_pack"] - 1


def test_an_omitted_card_appears_in_the_runs_log_record(client, writable_library, capsys):
    """FR-030b — "the omission MUST appear in the log record for the run".

    Identified by code rather than by file, like 001's generation record: the log is meant
    to be safe to paste into a bug report without redaction, and a file path — especially
    one from outside the named library — is exactly what must not be in it (FR-009, FR-022b).
    """
    import json

    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    omitted = settle(client, omit(client, run, BARON_ZEMO).json())

    capsys.readouterr()
    confirmed = client.post(
        f"/api/assemblies/{omitted['id']}/confirmation",
        json={"save_as": "cap without Baron Zemo"},
        headers={"If-Match": str(omitted["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text

    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    records = [r for r in lines if r.get("run_id") == run["id"]]
    assert records, "the run wrote no log record"
    assert BARON_ZEMO in records[-1]["omitted_card_codes"]
    assert str(writable_library) not in json.dumps(records[-1])


def test_a_pack_with_an_omitted_card_prints(client, writable_library):
    """FR-030 — proceeding is the user's decision and the tool must not overrule it."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    omitted = settle(client, omit(client, run, BARON_ZEMO).json())
    assert omitted["state"] == "ready"

    confirmed = client.post(
        f"/api/assemblies/{omitted['id']}/confirmation",
        json={"save_as": "cap without Baron Zemo"},
        headers={"If-Match": str(omitted["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    assert confirmed.json()["state"] == "complete"
    # FR-036: an omission is something the user would want to know before paying to print.
    assert confirmed.json()["outcome"] == "warnings"
    assert client.get(f"/api/assemblies/{run['id']}/document").status_code == 200


def test_the_omission_stays_legible_a_week_later(client, writable_library):
    """FR-030b — retrievable from the run record, not only from the response that made it."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library, CAP_FOLDER)
    omit(client, run, BARON_ZEMO)

    again = client.get(f"/api/assemblies/{run['id']}").json()
    assert [o["card_code"] for o in again["report"]["omitted"]] == [BARON_ZEMO]
