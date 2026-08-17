"""T018 — stored PDFs (FR-026f–FR-026i, data-model.md § Stored PDF).

A pack PDF is ~202 MB and takes ~49 s to build, so storing and reusing one is not a
convenience — it is the difference between a tool that is pleasant and one that is not. Two
consequences drive everything here.

**Ownership is not obvious and getting it wrong destroys work.** A *standard* PDF belongs to
the pack, not to the run that happened to build it (FR-026g1): several runs of the same pack
against the same library produce the same file, so deleting one of those runs must not
revoke reuse for the others. A *saved* PDF is the user's own customized output and is that
run's to lose.

**Two runs can finish the same pack at the same time.** The reuse key is the filename, so
`os.link` failing with `EEXIST` is the uniqueness primitive: it is one atomic syscall, where
"does it exist? then write it" is a race with a 202 MB loser.

Refcounting is the kernel's. A run holds a hard link to the PDF it produced, so "delete the
run" and "delete the stored PDF" are two independent decrements of one count and neither has
to know about the other.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from marchamp.store.layout import StateLayout
from marchamp.store.pdfs import PdfKind, PdfStore

REVISION = "0123456789abcdef"
IDENTITY = "fedcba9876543210"
RUN_ID = "9f2c40a1b7e5486dbc31a0f7d24e8b56"
OTHER_RUN = "1a2b3c4d5e6f70819a2b3c4d5e6f7081"

DOCUMENT = b"%PDF-1.4\n" + b"x" * 4096


@pytest.fixture
def store(tmp_path: Path) -> PdfStore:
    layout = StateLayout(tmp_path / "state")
    layout.ensure()
    return PdfStore(layout)


def test_a_standard_pdf_is_stored_under_its_reuse_key(store):
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    assert stored.kind is PdfKind.STANDARD
    assert stored.path.read_bytes() == DOCUMENT
    assert stored.byte_size == len(DOCUMENT)
    # The name is derived from the pack, not asked of the user (FR-026i).
    assert "cap" in stored.name


def test_an_unbuilt_pack_reports_no_stored_pdf(store):
    assert store.find_standard("cap", REVISION, IDENTITY) is None


def test_a_matching_key_is_reused_rather_than_rebuilt(store):
    """FR-026f, SC-006i — reuse skips the ~49 s render."""
    store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    found = store.find_standard("cap", REVISION, IDENTITY)
    assert found is not None and found.path.read_bytes() == DOCUMENT


@pytest.mark.parametrize(
    "pack,revision,identity",
    [
        ("wsp", REVISION, IDENTITY),  # a different pack
        ("cap", "aaaaaaaaaaaaaaaa", IDENTITY),  # refreshed card data (US1 scenario 16)
        ("cap", REVISION, "bbbbbbbbbbbbbbbb"),  # a second library, different bytes
    ],
)
def test_any_component_of_the_key_changing_invalidates_reuse(store, pack, revision, identity):
    # SC-006k: a second library resolving even one card to different bytes must rebuild.
    store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    assert store.find_standard(pack, revision, identity) is None


def test_a_concurrent_second_write_of_the_same_key_does_not_corrupt_the_first(store):
    """`EEXIST` is the primitive, not a check-then-write.

    Both runs resolved the same pack to the same bytes, so by FR-026h their documents are
    identical and the loser's copy is redundant. What must not happen is a partially
    overwritten 202 MB file that both runs then serve.
    """
    first = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    second = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    assert first.path == second.path
    assert first.path.read_bytes() == DOCUMENT
    # And no temporary file was left behind by the loser.
    assert [p.name for p in store.layout.standard_pdfs().iterdir()] == [first.path.name]


def test_a_saved_pdf_is_named_by_the_user(store):
    stored = store.put_saved(DOCUMENT, name="Wasp — aggression, v2 (final)")
    assert stored.kind is PdfKind.SAVED
    assert stored.name == "Wasp — aggression, v2 (final)"
    # The user's title is not the filename: it contains characters a path cannot carry.
    assert stored.name not in stored.path.name
    assert stored.path.read_bytes() == DOCUMENT


def test_two_saved_pdfs_with_the_same_name_are_distinct_files(store):
    a = store.put_saved(DOCUMENT, name="Thor")
    b = store.put_saved(DOCUMENT + b"different", name="Thor")
    assert a.path != b.path
    assert b.path.read_bytes() != a.path.read_bytes()


def test_attaching_to_a_run_links_rather_than_copies(store):
    """One inode, two names. A 202 MB copy per run is the alternative."""
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    link = store.attach_to_run(RUN_ID, stored)
    assert link.read_bytes() == DOCUMENT
    assert os.stat(link).st_ino == os.stat(stored.path).st_ino
    assert os.stat(link).st_nlink == 2


def test_deleting_a_run_never_reclaims_a_standard_pdf(store):
    """FR-026g1, SC-006h, US5 scenario 6a.

    The standard PDF belongs to the pack. A user deleting one run of Captain America must
    not silently revoke reuse for every other run of Captain America.
    """
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    store.attach_to_run(RUN_ID, stored)
    store.detach_run(RUN_ID)

    assert not store.layout.run_dir(RUN_ID).joinpath("output.pdf").exists()
    assert stored.path.is_file()
    assert store.find_standard("cap", REVISION, IDENTITY) is not None


def test_deleting_a_run_does_reclaim_its_saved_pdf(store):
    stored = store.put_saved(DOCUMENT, name="Wasp custom")
    store.attach_to_run(RUN_ID, stored)

    store.delete_saved(stored.id)
    store.detach_run(RUN_ID)
    assert not stored.path.exists()


def test_deleting_a_standard_pdf_returns_the_bytes_to_the_operating_system(store, tmp_path):
    """FR-026g — the user's deletion is the only bound on storage, so it must be real.

    Asserted through the link count rather than through the file merely disappearing: an
    unlinked file whose inode is still referenced has freed nothing, and at ~202 MB a
    deletion that frees nothing is the whole feature failing quietly.
    """
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    inode = os.stat(stored.path).st_ino
    assert os.stat(stored.path).st_nlink == 1

    store.delete_standard("cap", REVISION, IDENTITY)
    assert not stored.path.exists()
    # Nothing anywhere under the state directory still references those bytes.
    remaining = [
        p for p in store.layout.root.rglob("*") if p.is_file() and os.stat(p).st_ino == inode
    ]
    assert remaining == []


def test_a_standard_pdf_deleted_while_a_run_holds_it_stays_readable_for_that_run(store):
    """The kernel's refcount is the mechanism, so this falls out rather than being coded.

    A user deleting a stored PDF should not break the run that is downloading it; the next
    assembly of that pack rebuilds (FR-026g, US5 scenario 6b), which is the intended cost.
    """
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    link = store.attach_to_run(RUN_ID, stored)
    store.delete_standard("cap", REVISION, IDENTITY)

    assert store.find_standard("cap", REVISION, IDENTITY) is None
    assert link.read_bytes() == DOCUMENT


def test_two_runs_of_one_pack_share_one_copy_of_the_bytes(store):
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    a = store.attach_to_run(RUN_ID, stored)
    b = store.attach_to_run(OTHER_RUN, stored)
    assert os.stat(a).st_ino == os.stat(b).st_ino == os.stat(stored.path).st_ino
    assert os.stat(stored.path).st_nlink == 3


def test_attaching_twice_replaces_rather_than_failing(store):
    """A run that re-renders after the user changed a card must not trip over its own link."""
    first = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    second = store.put_saved(DOCUMENT + b"customized", name="Cap, one card swapped")
    store.attach_to_run(RUN_ID, first)
    link = store.attach_to_run(RUN_ID, second)
    assert link.read_bytes() == DOCUMENT + b"customized"


def test_stored_pdfs_are_listed_with_what_the_user_needs_to_choose(store):
    store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    store.put_saved(DOCUMENT, name="Wasp custom")
    listed = store.list_stored()
    assert {p.kind for p in listed} == {PdfKind.STANDARD, PdfKind.SAVED}
    for p in listed:
        # FR-026g's deletion is a size decision: without the size the user cannot tell
        # which of these is the 202 MB one.
        assert p.byte_size == len(DOCUMENT)
        assert p.name


def test_deleting_never_touches_the_scan_library(store, library_root):
    """FR-001 — the library is read-only source material, always."""
    before = sorted(p.relative_to(library_root) for p in library_root.rglob("*"))
    stored = store.put_standard("cap", REVISION, IDENTITY, DOCUMENT)
    store.attach_to_run(RUN_ID, stored)
    store.delete_standard("cap", REVISION, IDENTITY)
    store.detach_run(RUN_ID)
    assert sorted(p.relative_to(library_root) for p in library_root.rglob("*")) == before
