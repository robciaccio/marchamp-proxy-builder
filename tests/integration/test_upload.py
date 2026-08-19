"""T083/T085/T087/T095 — the file the user supplies (FR-026e, FR-027, FR-028, FR-029).

The upload is the one place where the containment boundary this feature is otherwise built
around is deliberately opened. FR-007 governs what the tool resolves *on its own*; a file
the person running the process hands it may come from anywhere on their machine. What must
not follow from that is a path from outside the named library reaching the report, the run
record, or the log — FR-009 holds without exception, and FR-027 says so in terms.

Four properties, each guarding a different way of being wrong:

- **Validation is not skipped because a human chose the file** (FR-028). Manual choice
  bypasses discovery, never validation, and a rejected file must leave the card unresolved
  rather than resolved-to-something-unprintable.
- **A manual resolution is visibly manual** (FR-029, SC-006c). A deck assembled with human
  help is auditable as such, or the audit trail means nothing.
- **The run owns the bytes** (FR-026e, SC-006b). Not a reference to a file on disk — the
  user found that file somewhere, and it will not still be there next week.
- **Answering one gap keeps every earlier answer** (US4 scenario 8). A wizard that loses
  thirty-nine resolutions while the user goes looking for the fortieth is one they will not
  use twice.
"""

from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: Two cap cards with no reprint link anywhere, so removing their scans leaves the cascade
#: nothing to fall back to and the run reports both.
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


@pytest.fixture
def outside_file(tmp_path) -> Path:
    """A file the user picked from somewhere that is emphatically not the library.

    The directory name is the point: if any part of it reaches the report or the log,
    FR-009 has been broken and the assertions below say where.
    """
    path = tmp_path / "somewhere-private" / "Baron Zemo rescan.tiff"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(card_bytes())
    return path


def card_bytes(width: int = LIBRARY_IMAGE_W, height: int = LIBRARY_IMAGE_H) -> bytes:
    """A generated card face as TIFF bytes. Never a real scan (FR-038a)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def resolve(client, library: Path, folder: str = CAP_FOLDER) -> dict:
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


def upload(client, run: dict, card_code: str, name: str, data: bytes, side: str = "front"):
    return client.post(
        f"/api/assemblies/{run['id']}/cards/{card_code}/image",
        files={"file": (name, data, "application/octet-stream")},
        data={"side": side},
        headers={"If-Match": str(run["version"])},
    )


def answer_remaining(client, run: dict) -> dict:
    """Supply a file for every gap still open, so the run can actually print.

    The derived fixture library is short of `Followed` (03032) for `cap` — a T005 coverage
    limitation recorded in Phase 5's notes rather than a resolver shortfall — so a cap run
    over it is never complete on its own. Answering whatever is left is how a test reaches
    a printable run without asserting anything about that limitation's exact contents.
    """
    while run["unresolved"]:
        gap = run["unresolved"][0]
        response = upload(
            client,
            run,
            gap["card_code"],
            f"{gap['card_code']}.tiff",
            card_bytes(),
            side=gap["side"],
        )
        assert response.status_code == 200, response.text
        run = response.json()
    if run["decklist_candidate"] is not None:
        # An undecided deck list candidate holds the run exactly as an unresolved card does
        # (FR-013d), and cap's folder holds one. Accepting the tool's own proposal is not
        # customization (FR-013e), so this does not disturb what these tests assert.
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()
    return run


def gaps(run: dict, card_code: str) -> list[dict]:
    return [u for u in run["unresolved"] if u["card_code"] == card_code]


def resolution_for(run: dict, card_code: str) -> dict:
    (entry,) = [r for r in run["report"]["resolutions"] if r["card_code"] == card_code]
    return entry


# --------------------------------------------------------------- T083: validation (FR-028)


def test_a_file_that_is_not_an_image_is_refused_with_the_reason(client, writable_library):
    """Rejected on upload, naming why — never accepted and discovered at render time."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)

    response = upload(client, run, BARON_ZEMO, "notes.txt", b"this is not an image")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "notes.txt" in detail
    assert "image" in detail.lower()


def test_a_scan_below_the_print_resolution_floor_is_refused_with_the_reason(
    client, writable_library
):
    """FR-028 against FR-035, and the difference is deliberate.

    A *library* scan below the floor is a warning, because the user cannot re-take it and
    is entitled to decide a soft card is fine. A file they are choosing right now is
    different: they can pick another, and telling them at the point of choice is the whole
    value of validating on upload.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)

    response = upload(client, run, BARON_ZEMO, "thumbnail.tiff", card_bytes(120, 168))
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "thumbnail.tiff" in detail
    assert "300" in detail or "DPI" in detail


@pytest.mark.parametrize(
    ("name", "data"),
    [("notes.txt", b"not an image"), ("thumbnail.tiff", None)],
    ids=["undecodable", "below-the-floor"],
)
def test_a_refused_upload_leaves_the_card_unresolved(client, writable_library, name, data):
    """FR-028's second half. A rejection that half-resolved the card would be worse than
    no upload endpoint at all: the run would look answerable and print a blank."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)

    upload(client, run, BARON_ZEMO, name, data if data is not None else card_bytes(120, 168))

    again = client.get(f"/api/assemblies/{run['id']}").json()
    assert gaps(again, BARON_ZEMO)
    assert again["state"] == "awaiting_cards"


def test_a_refused_upload_leaves_nothing_behind_in_the_run(client, writable_library, state_root):
    """A file that was rejected must not be sitting in the run's uploads directory.

    Stored bytes are what a resolution refers to. Keeping a rejected file would leave the
    run one record away from resolving a card to an image the service has already said it
    will not print.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    upload(client, run, BARON_ZEMO, "notes.txt", b"not an image")

    uploads = state_root / "runs" / run["id"] / "uploads"
    assert list(uploads.iterdir()) == []


# ------------------------------------------- T085: manual, and named by its own name only


def test_a_manual_resolution_is_distinguishable_from_every_automatic_one(
    client, writable_library, outside_file
):
    """FR-029, SC-006c — a deck assembled with human help is auditable as such."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)

    answered = upload(client, run, BARON_ZEMO, outside_file.name, outside_file.read_bytes()).json()

    entry = resolution_for(answered, BARON_ZEMO)
    assert entry["provenance"] == "manual"
    assert entry["source"] == "upload"

    automatic = [r for r in answered["report"]["resolutions"] if r["card_code"] != BARON_ZEMO]
    assert automatic, "the control: the rest of the pack resolved on its own"
    assert all(r["provenance"] != "manual" for r in automatic)
    assert all(r["source"] == "library" for r in automatic)


def test_only_the_uploaded_files_own_name_is_recorded(
    client, writable_library, outside_file, state_root
):
    """FR-027, FR-009 — no path from outside the named library root, anywhere.

    Asserted against the run record on disk as well as against the response, because the
    record is what a later visit reads and what a bug report would carry.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    answered = upload(client, run, BARON_ZEMO, outside_file.name, outside_file.read_bytes()).json()

    assert resolution_for(answered, BARON_ZEMO)["file"] == outside_file.name

    record = (state_root / "runs" / run["id"] / "run.json").read_text()
    assert str(outside_file) not in record
    assert str(outside_file.parent) not in record
    assert "somewhere-private" not in record
    # The name itself is retained — it is what the user recognises a week later.
    stored = json.loads(record)
    assert any(r.get("original_filename") == outside_file.name for r in stored["resolutions"])


def test_the_stored_upload_is_named_by_its_content(client, writable_library, state_root):
    """Research R9 — content-addressed, so the same file twice costs one copy and a
    resumed run can still find it (FR-026e)."""
    import hashlib

    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    data = card_bytes()
    upload(client, run, BARON_ZEMO, "zemo.tiff", data)

    uploads = state_root / "runs" / run["id"] / "uploads"
    assert [p.name for p in uploads.iterdir()] == [hashlib.sha256(data).hexdigest()]


def test_supplying_a_file_makes_the_run_customized(client, writable_library):
    """FR-026i — two users pointed at the same folder would now get different PDFs, so
    this run cannot be stored as the pack's standard PDF."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    answered = answer_remaining(
        client, upload(client, run, BARON_ZEMO, "zemo.tiff", card_bytes()).json()
    )
    assert answered["state"] == "ready"

    without_a_name = client.post(
        f"/api/assemblies/{answered['id']}/confirmation",
        json={},
        headers={"If-Match": str(answered["version"])},
    )
    assert without_a_name.status_code == 400
    assert "save_as" in without_a_name.json()["detail"]


# ------------------------------------------ T087: the run holds the bytes (US4 scenario 4)


def test_a_run_still_prints_after_the_uploaded_file_is_deleted(
    client, writable_library, outside_file
):
    """FR-026e, SC-006b, US4 scenario 4 — the run retains the bytes, not a reference.

    The user went and found this file somewhere. Depending on it still being there is
    depending on something the application does not control and the user has no reason to
    preserve.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    answered = answer_remaining(
        client,
        upload(client, run, BARON_ZEMO, outside_file.name, outside_file.read_bytes()).json(),
    )

    outside_file.unlink()

    confirmed = client.post(
        f"/api/assemblies/{answered['id']}/confirmation",
        json={"save_as": "cap with a rescanned Zemo"},
        headers={"If-Match": str(answered["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    assert confirmed.json()["state"] == "complete"

    document = client.get(f"/api/assemblies/{run['id']}/document")
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF")


def test_the_manual_resolution_survives_being_read_back(client, writable_library):
    """FR-026b — the run record carries it, not the response that produced it."""
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    upload(client, run, BARON_ZEMO, "zemo.tiff", card_bytes())

    again = client.get(f"/api/assemblies/{run['id']}").json()
    assert not gaps(again, BARON_ZEMO)
    assert resolution_for(again, BARON_ZEMO)["provenance"] == "manual"


# ----------------------------------------- T095: answering one gap keeps the other answers


def test_answering_the_first_of_two_gaps_asks_only_about_the_second(client, writable_library):
    """US4 scenario 8 — the folder, the pack, and every earlier choice are kept.

    This is the requirement that decides how manual resolution is implemented rather than
    merely whether it exists. Re-running the cascade from scratch on every answer is
    correct — the library is re-read on every pass (FR-026b) — but only if the answers
    already given override it. An implementation that rebuilds the resolutions and forgets
    the uploads asks about the first card again, forever.
    """
    for scan in (BARON_ZEMO_SCAN, HYDRA_SOLDIER_SCAN):
        (writable_library / scan).unlink()
    run = resolve(client, writable_library)

    missing = {u["card_code"] for u in run["unresolved"]}
    assert {BARON_ZEMO, HYDRA_SOLDIER} <= missing

    before = {(r["card_code"], r["side"]): r["file"] for r in run["report"]["resolutions"]}
    answered = upload(client, run, BARON_ZEMO, "zemo.tiff", card_bytes()).json()

    # Only the second is still asked about.
    assert not gaps(answered, BARON_ZEMO)
    assert gaps(answered, HYDRA_SOLDIER)
    assert answered["state"] == "awaiting_cards"

    # The folder, the pack, and every earlier resolution are untouched.
    assert answered["hero_folder"] == run["hero_folder"]
    assert answered["library_root"] == run["library_root"]
    assert answered["identification"]["pack_code"] == run["identification"]["pack_code"]
    assert answered["snapshot_revision"] == run["snapshot_revision"]
    after = {(r["card_code"], r["side"]): r["file"] for r in answered["report"]["resolutions"]}
    assert before.items() <= after.items()


def test_answering_both_gaps_completes_the_run(client, writable_library):
    """The other half of scenario 8: the user is asked once per card and then done."""
    for scan in (BARON_ZEMO_SCAN, HYDRA_SOLDIER_SCAN):
        (writable_library / scan).unlink()
    run = resolve(client, writable_library)

    run = upload(client, run, BARON_ZEMO, "zemo.tiff", card_bytes()).json()
    run = upload(client, run, HYDRA_SOLDIER, "hydra.tiff", card_bytes()).json()
    assert not gaps(run, BARON_ZEMO) and not gaps(run, HYDRA_SOLDIER)

    run = answer_remaining(client, run)
    assert run["unresolved"] == []
    assert run["state"] == "ready"
    manual = {r["card_code"] for r in run["report"]["resolutions"] if r["provenance"] == "manual"}
    assert {BARON_ZEMO, HYDRA_SOLDIER} <= manual


# ------------------------------------------- T114: the same rule, applied to the log record


def test_the_runs_log_record_carries_no_path_from_outside_the_library(
    client, writable_library, outside_file, capsys
):
    """FR-009, FR-030b, Principle V — the log line, not just the run record.

    `test_only_the_uploaded_files_own_name_is_recorded` covers what is written to
    `run.json`, which stays on the user's own machine. This covers the line written to
    stdout, which is the one that gets pasted into a bug report — a different destination
    with a stricter rule, because there even the filename the user recognises has no
    business appearing next to a directory they did not choose to share.

    The provenance the same line carries is asserted alongside. A record that dropped the
    paths by dropping the resolutions would pass the first half and be useless.
    """
    (writable_library / BARON_ZEMO_SCAN).unlink()
    run = resolve(client, writable_library)
    answered = answer_remaining(
        client,
        upload(client, run, BARON_ZEMO, outside_file.name, outside_file.read_bytes()).json(),
    )

    capsys.readouterr()
    confirmed = client.post(
        f"/api/assemblies/{answered['id']}/confirmation",
        json={"save_as": "cap with a rescanned Zemo"},
        headers={"If-Match": str(answered["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text

    line = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and '"run_id"' in line
    )
    for leak in (str(outside_file), str(outside_file.parent), "somewhere-private"):
        assert leak not in line, f"the log record leaked {leak!r}"
    assert str(writable_library) not in line
    assert outside_file.name not in line, (
        "a filename from outside the library is exactly what FR-009 keeps out of the log; "
        "the run record keeps it, the log line must not"
    )

    record = json.loads(line)
    assert record["pack_code"] == "cap"
    assert record["pack_source"] == "identified"
    assert BARON_ZEMO in record["manual_card_codes"]
    assert {
        "card_code": BARON_ZEMO,
        "side": "front",
        "provenance": "manual",
        "source": "upload",
    } in record["resolutions"]
