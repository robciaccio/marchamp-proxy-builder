"""T065 — every file in the hero folder is accounted for (FR-031, FR-032, SC-004).

The harm this exists to prevent is narrow and real: a scan sitting in the folder the user
pointed at, skipped for a reason the tool never says. They organised that folder; a file in
it that the run silently ignored is either a card they think they are getting and are not,
or a mistake in the filename they cannot see.

**The accounting is bounded to the hero folder, and that bound is deliberate.** Read
literally against FR-021's whole-library search, FR-031 would require one hero's report to
account individually for 4,447 files that were never candidates — a report no user can read
and a criterion no test can assert. Outside the hero folder the report names only files it
actually used or that conflicted with one it used.

**The hero folder is a subtree, not a directory listing.** Captain America's nemesis set
lives in `Captain America Nemesis/` beneath it, so an accounting that stopped at the
top-level listing would silently drop five cards' worth of files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from marchamp.library.filenames import IMAGE_SUFFIXES
from tests.conftest import ACCEPTANCE_HEROES, make_card_image

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]
NEMESIS_SUBFOLDER = f"{CAP_FOLDER}/Captain America Nemesis"

#: A Core Set scan `cap` has no card for. It is under the library root, outside the hero
#: folder, and never used — so it must appear nowhere in the report at all.
UNUSED_ELSEWHERE = "Core Set/Core Set_Hawkeye_Ally_66.tiff"

IMAGE_W, IMAGE_H = 780, 1122


@pytest.fixture
def client(tmp_path, upstream_transport, monkeypatch):
    from marchamp.upstream.client import MarvelCdbClient

    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream_transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def writable_library(tmp_path, scan_library) -> Path:
    """A writable copy of the derived fixture library, hardlinked so it costs nothing."""
    root = tmp_path / "library"
    shutil.copytree(scan_library, root, copy_function=os.link)
    return root


def assemble(client, library: Path, folder: str) -> dict:
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


@pytest.fixture
def cap_run(client, writable_library) -> dict:
    return assemble(client, writable_library, CAP_FOLDER)


#: Two files the run cannot use, for two different reasons, added *after* the fixture was
#: derived so nothing in the code can have been written knowing about them. Every hero
#: folder in the real library has files like these; a report that explains neither is the
#: silent omission FR-031 forbids.
STRAY_UNINTERPRETABLE = f"{CAP_FOLDER}/notes about this pack.tiff"
#: Parses cleanly as the library's commonest convention, and names a position `cap` has no
#: card at. Nothing is wrong with the file; it simply is not one of this pack's cards.
STRAY_UNMATCHED = f"{CAP_FOLDER}/Leadership_Some Other Card_Event_240.tiff"


@pytest.fixture
def cap_run_with_strays(client, writable_library) -> dict:
    for rel in (STRAY_UNINTERPRETABLE, STRAY_UNMATCHED):
        make_card_image(writable_library / rel, "STRAY", width=IMAGE_W, height=IMAGE_H)
    return assemble(client, writable_library, CAP_FOLDER)


def images_under(root: Path, folder: str) -> set[str]:
    """Every image file beneath `folder`, as library-relative refs — read off the disk.

    Deliberately not read from the index the run built: a test that asked the code under
    test what the folder contains could not detect the code failing to look at half of it.
    """
    base = root / folder
    return {
        str(path.relative_to(root))
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }


def accounted(run: dict) -> set[str]:
    """Every hero-folder file the report claims to have looked at, used or not.

    Narrowed to the hero folder because used files are named wherever they live — most of
    `cap`'s aspect cards are borrowed out of the Core Set — and SC-004's denominator is the
    hero folder alone.
    """
    report = run["report"]
    used = {entry["file"] for entry in report["resolutions"]}
    if run.get("decklist_candidate"):
        used.add(run["decklist_candidate"]["ref"])
    named = used | {entry["file"] for entry in report["unused_files"]}
    return {ref for ref in named if ref.startswith(f"{CAP_FOLDER}/")}


# ------------------------------------------------------------------ the hero folder


def test_every_file_in_the_hero_folder_is_used_or_named_as_unused(cap_run, writable_library):
    """SC-004 — 100%, with zero silently ignored. The assertion is set equality.

    Subset in either direction would pass on a bug: missing files are the silent omission
    the requirement forbids, and extra ones are a report naming files that are not there.
    """
    on_disk = images_under(writable_library, CAP_FOLDER)
    assert on_disk, "the fixture hero folder is empty"
    assert on_disk <= accounted(cap_run)


def test_the_nemesis_subfolder_is_inside_the_hero_folder_for_this_purpose(
    cap_run, writable_library
):
    """FR-031 — a subtree, not a directory listing.

    Five of Captain America's cards live one level down. An accounting that stopped at the
    top level would leave them unexplained while still reporting 100% coverage of what it
    chose to look at.
    """
    nemesis_files = images_under(writable_library, NEMESIS_SUBFOLDER)
    assert len(nemesis_files) == 5
    assert nemesis_files <= accounted(cap_run)


def test_every_unused_file_is_accounted_for_whatever_the_reason(
    cap_run_with_strays, writable_library
):
    """SC-004 — both strays, neither usable, both named. Set equality, not a subset."""
    on_disk = images_under(writable_library, CAP_FOLDER)
    assert {STRAY_UNINTERPRETABLE, STRAY_UNMATCHED} <= on_disk
    assert on_disk == accounted(cap_run_with_strays)


def test_every_unused_file_says_why_it_was_not_used(cap_run_with_strays):
    """FR-031, FR-037 — "unused" without a reason is a fact the user cannot act on.

    The two strays are unusable for genuinely different reasons, and a report giving them
    the same sentence has told the user nothing: one is a filename to fix, the other is a
    card that belongs to a different pack.
    """
    reasons = {e["file"]: e["reason"] for e in cap_run_with_strays["report"]["unused_files"]}
    assert reasons[STRAY_UNINTERPRETABLE]
    assert reasons[STRAY_UNMATCHED]
    assert reasons[STRAY_UNINTERPRETABLE] != reasons[STRAY_UNMATCHED]


def test_a_file_nobody_can_interpret_is_named_as_such(cap_run_with_strays):
    """FR-032 — found by looking, never from a list written in advance.

    Both strays are added after the fixture was derived, so nothing in the code can have
    been written knowing about them. Only the uninterpretable one belongs in this section:
    the other parses perfectly well and simply is not one of this pack's cards.
    """
    named = {e["file"] for e in cap_run_with_strays["report"]["uninterpretable_files"]}
    assert STRAY_UNINTERPRETABLE in named
    assert STRAY_UNMATCHED not in named


def test_the_decklist_scan_is_never_reported_as_unused(cap_run):
    """It was used — as the decklist card (FR-013d).

    Without this the decklist scan in every hero folder is reported as an unexplained
    unused file, in every run, for the whole library.
    """
    candidate = cap_run["decklist_candidate"]
    assert candidate is not None
    named = {e["file"] for e in cap_run["report"]["unused_files"]}
    named |= {e["file"] for e in cap_run["report"]["uninterpretable_files"]}
    assert candidate["ref"] not in named


# --------------------------------------------------------------- beyond the hero folder


def test_nothing_outside_the_hero_folder_is_listed_as_unused(cap_run):
    """FR-031 as amended — 4,447 individually named files is not a report."""
    for entry in cap_run["report"]["unused_files"]:
        assert entry["file"].startswith(f"{CAP_FOLDER}/")


def test_a_file_used_from_outside_the_hero_folder_still_appears(cap_run):
    """Used files are named wherever they live — that is the substitution record (FR-024)."""
    used = {entry["file"] for entry in cap_run["report"]["resolutions"]}
    assert any(ref.startswith("Core Set/") for ref in used)


def test_an_unused_file_elsewhere_under_the_library_is_not_listed_at_all(cap_run):
    """FR-031 — it was never a candidate for this pack, so naming it is noise.

    Asserted against the whole serialised report rather than one section, because the
    failure being guarded is the file turning up *somewhere* in it.
    """
    import json

    assert UNUSED_ELSEWHERE not in json.dumps(cap_run["report"])
