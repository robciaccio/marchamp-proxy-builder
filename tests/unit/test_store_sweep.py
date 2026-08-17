"""T020 — the startup orphan sweep (ADR 0001 § Consequences).

ADR 0001 chose plain files knowing what it gave up, and named the debt in writing: *"there
is no transaction across a record and its blobs, so a startup sweep for orphaned uploads is
owed."* This is that sweep.

The orphan is created by a specific crash: bytes are written to `uploads/<sha256>` and the
process dies before the resolution naming them reaches `run.json`. Nothing then references
those bytes and nothing ever will, because the file's only name is its content digest and
the user will re-upload rather than guess it.

**Running at startup is what makes deleting safe.** No request is in flight when the process
begins, so an upload absent from its run's record is unreachable by definition rather than
merely not-yet-recorded. Running the same sweep while serving would delete a file between
the upload landing and the resolution being written — the sweep would cause the exact bug it
exists to clean up after.

Everything here deletes the user's data, so the bias throughout is toward leaving a file
alone when the evidence is ambiguous.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marchamp.store.layout import StateLayout
from marchamp.store.runs import RunStore
from marchamp.store.sweep import sweep_state


@pytest.fixture
def layout(tmp_path: Path) -> StateLayout:
    layout = StateLayout(tmp_path / "state")
    layout.ensure()
    return layout


@pytest.fixture
def runs(layout: StateLayout) -> RunStore:
    return RunStore(layout)


def _upload(layout: StateLayout, run_id: str, digest: str, data: bytes = b"scan") -> Path:
    p = layout.upload(run_id, digest)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def test_an_upload_no_resolution_references_is_reclaimed(layout, runs):
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Wasp")
    orphan = _upload(layout, run.id, DIGEST_A)

    report = sweep_state(layout)

    assert not orphan.exists()
    assert orphan in report.removed


def test_an_upload_a_resolution_references_is_kept(layout, runs):
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Wasp")
    kept = _upload(layout, run.id, DIGEST_A)
    run.resolutions = [{"card_code": "13001a", "source": "upload", "ref": f"upload:{DIGEST_A}"}]
    runs.write(run)

    sweep_state(layout)
    assert kept.read_bytes() == b"scan"


def test_the_sweep_distinguishes_two_uploads_in_one_run(layout, runs):
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Wasp")
    kept = _upload(layout, run.id, DIGEST_A)
    orphan = _upload(layout, run.id, DIGEST_B)
    run.resolutions = [{"card_code": "x", "source": "upload", "ref": f"upload:{DIGEST_A}"}]
    runs.write(run)

    sweep_state(layout)
    assert kept.exists()
    assert not orphan.exists()


def test_a_run_this_build_cannot_read_is_left_completely_alone(layout, runs):
    """A record from a newer schema version is not an orphan — it is the future.

    Sweeping a run whose record this build refuses to parse would delete the uploads of a
    run a newer build can still finish, which is worse than leaving bytes on disk.
    """
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Thor")
    upload = _upload(layout, run.id, DIGEST_A)
    record = layout.run_record(run.id)
    payload = json.loads(record.read_text())
    payload["schema_version"] = "99"
    record.write_text(json.dumps(payload))

    report = sweep_state(layout)
    assert upload.exists()
    assert report.skipped_runs == [run.id]


def test_a_run_directory_with_no_record_at_all_is_reclaimed(layout):
    """A crash between creating the directory and writing the record.

    Distinguishable from the case above: no record is not an unreadable record, and there
    is nothing a future build could do with an empty directory either.
    """
    run_id = StateLayout.new_run_id()
    orphan = _upload(layout, run_id, DIGEST_A)

    sweep_state(layout)
    assert not orphan.exists()
    assert not layout.run_dir(run_id).exists()


def test_temporary_files_from_an_interrupted_write_are_reclaimed(layout, runs):
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Hulk")
    debris = [
        layout.run_dir(run.id) / ".run.json.abc123.tmp",
        layout.standard_pdfs() / ".pdf.9f8e7d.tmp",
        layout.saved_pdfs() / ".pdf.112233.tmp",
    ]
    for p in debris:
        p.write_bytes(b"half a document")

    sweep_state(layout)
    for p in debris:
        assert not p.exists()


def test_a_standard_pdf_is_never_swept(layout, runs):
    """FR-026g1 — it belongs to the pack, so no run's absence orphans it.

    This is the sweep's most dangerous possible mistake: the file looks unreferenced from
    every direction except the one that matters, and it is 202 MB the user waited 49 s for.
    """
    from marchamp.store.pdfs import PdfStore

    stored = PdfStore(layout).put_standard("cap", "0" * 16, "1" * 16, b"%PDF-1.4\n")
    sweep_state(layout)
    assert stored.path.is_file()


def test_a_saved_pdf_with_no_run_is_never_swept(layout):
    """It is listed and deletable in its own right (FR-026g), not owned by a run."""
    from marchamp.store.pdfs import PdfStore

    stored = PdfStore(layout).put_saved(b"%PDF-1.4\n", name="Wasp custom")
    sweep_state(layout)
    assert stored.path.is_file()
    assert stored.path.with_suffix(".json").is_file()


def test_the_sweep_never_touches_the_scan_library(layout, library_root):
    before = sorted(p.relative_to(library_root) for p in library_root.rglob("*"))
    sweep_state(layout)
    assert sorted(p.relative_to(library_root) for p in library_root.rglob("*")) == before


def test_the_sweep_is_safe_on_a_state_directory_that_does_not_exist_yet(tmp_path):
    report = sweep_state(StateLayout(tmp_path / "never-used"))
    assert report.removed == [] and report.reclaimed_bytes == 0


def test_the_sweep_reports_what_it_reclaimed(layout, runs):
    """Principle V — a deletion the user cannot see is indistinguishable from data loss."""
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Wasp")
    _upload(layout, run.id, DIGEST_A, data=b"x" * 1024)

    report = sweep_state(layout)
    assert report.reclaimed_bytes == 1024
    assert len(report.removed) == 1


def test_sweeping_twice_finds_nothing_the_second_time(layout, runs):
    run = runs.create(library_root=Path("/lib"), hero_folder="Heros/Wasp")
    _upload(layout, run.id, DIGEST_A)
    sweep_state(layout)
    assert sweep_state(layout).removed == []
