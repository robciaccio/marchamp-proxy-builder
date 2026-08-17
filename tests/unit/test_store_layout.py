"""T014 — where durable state lives (ADR 0001, data-model.md § Assembly Run, § Stored PDF).

The layout is one module rather than paths joined at each call site because three separate
concerns read it — the run store, the PDF store, and the startup sweep — and a sweep that
disagrees with the writer about where uploads live deletes the user's uploads.

Every identifier reaching these functions comes from outside: a run id from a URL, a pack
code from upstream. So containment is asserted here rather than assumed from the callers,
per the constitution's fail-closed clause.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from marchamp.store.layout import StateLayout, UnsafeIdentifier

#: A server-assigned run id, shaped exactly as `new_run_id` produces one. Written out
#: rather than generated so the expected paths below are readable.
RUN_ID = "9f2c40a1b7e5486dbc31a0f7d24e8b56"


@pytest.fixture
def layout(tmp_path: Path) -> StateLayout:
    return StateLayout(tmp_path / "state")


def test_the_documented_layout(layout, tmp_path):
    root = tmp_path / "state"
    assert layout.run_dir(RUN_ID) == root / "runs" / RUN_ID
    assert layout.run_record(RUN_ID) == root / "runs" / RUN_ID / "run.json"
    assert layout.uploads_dir(RUN_ID) == root / "runs" / RUN_ID / "uploads"
    assert layout.upload(RUN_ID, "a" * 64) == root / "runs" / RUN_ID / "uploads" / ("a" * 64)
    assert layout.standard_pdfs() == root / "pdfs" / "standard"
    assert layout.saved_pdfs() == root / "pdfs" / "saved"
    assert layout.snapshot("cap") == root / "snapshots" / "cap.json"
    assert layout.pack_index() == root / "snapshots" / "packs.json"


def test_the_standard_pdf_name_is_the_reuse_key(layout):
    """FR-026h — pack, snapshot revision, and the identity of the images resolved.

    The name *is* the key, so two runs agreeing on all three collide on the filesystem and
    `os.link`'s EEXIST becomes the uniqueness primitive rather than a check-then-write race
    (T018). Deriving the name from anything else would quietly reintroduce that race.
    """
    p = layout.standard_pdf("cap", "0123456789abcdef", "fedcba9876543210")
    assert p.parent == layout.standard_pdfs()
    assert p.suffix == ".pdf"
    for part in ("cap", "0123456789abcdef", "fedcba9876543210"):
        assert part in p.name


def test_a_saved_pdf_is_named_by_id_not_by_the_users_title(layout):
    """FR-026i lets the user name a saved PDF, and a user's name is not a filename.

    "Wasp — aggression, v2 (final)" contains a path separator on some platforms and a
    slash on all of them. The title belongs on the run record; the file gets an id.
    """
    p = layout.saved_pdf("f3a9c1d2e5b74a68")
    assert p.parent == layout.saved_pdfs()
    assert p.name == "f3a9c1d2e5b74a68.pdf"


@pytest.mark.parametrize(
    "hostile",
    ["../escape", "..", "a/b", "/absolute", "", ".", "with space", "run\x00id", "café"],
)
def test_an_identifier_that_could_escape_is_refused(layout, hostile):
    with pytest.raises(UnsafeIdentifier):
        layout.run_dir(hostile)


@pytest.mark.parametrize("hostile", ["../../etc/passwd", "cap/../..", "", "a b"])
def test_a_pack_code_that_could_escape_is_refused(layout, hostile):
    # The pack code reaches a filename and a URL. `^[a-z0-9_]{1,32}$` is the same rule the
    # client applies before a request (FR-003), asserted here so the two cannot drift.
    with pytest.raises(UnsafeIdentifier):
        layout.snapshot(hostile)


@pytest.mark.parametrize("code", ["cap", "wonder_man", "core", "mut_gen"])
def test_real_pack_codes_are_accepted(layout, code):
    assert layout.snapshot(code).name == f"{code}.json"


def test_an_upload_digest_must_look_like_a_sha256(layout):
    with pytest.raises(UnsafeIdentifier):
        layout.upload(RUN_ID, "not-a-digest")
    with pytest.raises(UnsafeIdentifier):
        layout.upload(RUN_ID, "A" * 64)  # lowercase hex only, so one file has one name


def test_every_path_stays_inside_the_state_directory(layout, tmp_path):
    root = (tmp_path / "state").resolve()
    produced = [
        layout.run_dir(RUN_ID),
        layout.run_record(RUN_ID),
        layout.upload(RUN_ID, "b" * 64),
        layout.standard_pdf("cap", "0" * 16, "1" * 16),
        layout.saved_pdf("deadbeefdeadbeef"),
        layout.snapshot("cap"),
        layout.pack_index(),
    ]
    for p in produced:
        assert root in p.resolve().parents


def test_directories_are_created_on_demand_not_at_import(layout):
    # Constructing the layout must not touch the filesystem: `settings_from_env()` builds a
    # state directory path on every import path there is, including `--help`.
    assert not layout.root.exists()
    layout.ensure()
    for d in (
        layout.runs_dir(),
        layout.standard_pdfs(),
        layout.saved_pdfs(),
        layout.snapshots_dir(),
    ):
        assert d.is_dir()


def test_ensure_is_idempotent(layout):
    layout.ensure()
    layout.ensure()
    assert layout.runs_dir().is_dir()


def test_new_run_ids_are_unguessable_and_filesystem_safe(layout):
    ids = {StateLayout.new_run_id() for _ in range(50)}
    assert len(ids) == 50
    for run_id in ids:
        layout.run_dir(run_id)  # accepted by the same rule that rejects the hostile cases
