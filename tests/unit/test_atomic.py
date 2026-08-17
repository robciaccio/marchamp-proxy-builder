"""T012 — crash-atomic writes (ADR 0001, FR-026b, FR-026f).

**This file is the review surface for the mechanism ADR 0001's dissent conceded on.** The
dissenting reviewers accepted plain files instead of SQLite on one condition: that the
fsync-ordering helper be reviewed as the crash-atomicity mechanism it is rather than as
plumbing. So these tests assert the *ordering of syscalls*, which is unusual and is the
point — the failure they guard against is invisible to every behavioural test, because a
run record written without them reads back perfectly right up until the power goes out.

Three things must hold, and the third is the one everyone omits:

1. the replacement is atomic — a reader sees the old bytes or the new, never a mixture;
2. the temporary file's contents reach the disk *before* the rename, or the rename can
   publish a file whose data has not landed;
3. the *directory* is synced *after* the rename, or the rename itself can be lost and the
   file reverts to its old name on recovery.

No test here exercises real power loss; nothing portable can. They assert the calls that
make power loss survivable, which is the most a test can do and is worth considerably more
than nothing.
"""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

import pytest

from marchamp.store import atomic


@pytest.fixture
def calls(monkeypatch):
    """Record the syncing and renaming syscalls in the order they are made."""
    log: list[tuple[str, object]] = []

    real_fsync, real_replace, real_fcntl = os.fsync, os.replace, fcntl.fcntl

    def spy_fsync(fd):
        log.append(("fsync", fd))
        return real_fsync(fd)

    def spy_fcntl(fd, cmd, *args):
        if cmd == getattr(fcntl, "F_FULLFSYNC", object()):
            log.append(("fullfsync", fd))
        return real_fcntl(fd, cmd, *args)

    def spy_replace(src, dst):
        log.append(("replace", (str(src), str(dst))))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)
    monkeypatch.setattr(fcntl, "fcntl", spy_fcntl)
    return log


def _kinds(log):
    return [kind for kind, _ in log]


def test_written_bytes_are_readable(tmp_path):
    target = tmp_path / "run.json"
    atomic.atomic_write_bytes(target, b'{"state": "resolving"}')
    assert target.read_bytes() == b'{"state": "resolving"}'


def test_replacing_an_existing_file_keeps_no_intermediate_state(tmp_path):
    target = tmp_path / "run.json"
    target.write_bytes(b"old")
    atomic.atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"new"
    # The temporary file is gone, not left beside the record for the sweep to puzzle over.
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"]


def test_file_contents_are_synced_before_the_rename(tmp_path, calls):
    atomic.atomic_write_bytes(tmp_path / "run.json", b"x")
    kinds = _kinds(calls)
    assert "replace" in kinds, "the write must go through a rename, not an in-place write"
    first_sync = min(i for i, k in enumerate(kinds) if k in ("fsync", "fullfsync"))
    assert first_sync < kinds.index("replace"), (
        "the rename published a file whose bytes may not have reached the disk"
    )


def test_the_directory_is_synced_after_the_rename(tmp_path, calls):
    atomic.atomic_write_bytes(tmp_path / "run.json", b"x")
    kinds = _kinds(calls)
    after = [k for k in kinds[kinds.index("replace") + 1 :] if k in ("fsync", "fullfsync")]
    assert after, (
        "the directory was never synced after the rename, so the rename itself can be lost "
        "and the file reverts to its old name on recovery — the step everyone omits"
    )


def test_the_temporary_file_lives_in_the_target_directory(tmp_path, calls):
    """A rename is only atomic within one filesystem.

    Writing the temporary file to the system temp directory and renaming across a mount
    boundary degrades to copy-then-delete, which is exactly what this module exists to
    avoid — and it fails only on machines where those are different filesystems.
    """
    target = tmp_path / "sub" / "run.json"
    target.parent.mkdir()
    atomic.atomic_write_bytes(target, b"x")
    ((src, dst),) = [payload for kind, payload in calls if kind == "replace"]
    assert Path(src).parent == target.parent
    assert Path(dst) == target


@pytest.mark.skipif(sys.platform != "darwin", reason="F_FULLFSYNC is a Darwin facility")
def test_darwin_uses_f_fullfsync(tmp_path, calls):
    """`fsync` on Darwin does not flush the drive's own write cache; `F_FULLFSYNC` does.

    On this project's primary platform, `fsync` alone leaves the data in a volatile buffer
    the operating system has already been told about and considers done. Using it here
    would make the guarantee this module advertises false on the machine it mostly runs on.
    """
    atomic.atomic_write_bytes(tmp_path / "run.json", b"x")
    assert "fullfsync" in _kinds(calls)


def test_falls_back_to_fsync_where_f_fullfsync_is_absent(tmp_path, calls, monkeypatch):
    monkeypatch.setattr(atomic, "F_FULLFSYNC", None)
    atomic.atomic_write_bytes(tmp_path / "run.json", b"x")
    kinds = _kinds(calls)
    assert "fullfsync" not in kinds
    assert kinds.count("fsync") >= 2  # the file, then the directory


def test_a_failed_write_leaves_the_previous_contents_intact(tmp_path, monkeypatch):
    target = tmp_path / "run.json"
    target.write_bytes(b"old")

    def boom(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic.atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"old"
    # And no debris is left behind for the orphan sweep to interpret.
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"]


def test_atomic_write_text_round_trips_utf8(tmp_path):
    target = tmp_path / "run.json"
    atomic.atomic_write_text(target, '{"name": "Kamala Khan — Ms. Marvel"}')
    assert "Kamala Khan — Ms. Marvel" in target.read_text(encoding="utf-8")


def test_atomic_write_json_is_canonical_and_stable(tmp_path):
    """The snapshot revision is a hash of the serialisation (research R10).

    If key order or separators varied between writes, a refetch that changed nothing would
    produce a new revision, invalidating every reused PDF for no reason (FR-026h).
    """
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    atomic.atomic_write_json(a, {"b": 2, "a": 1})
    atomic.atomic_write_json(b, {"a": 1, "b": 2})
    assert a.read_bytes() == b.read_bytes()


def test_writes_create_the_parent_directory(tmp_path):
    target = tmp_path / "runs" / "abc123" / "run.json"
    atomic.atomic_write_bytes(target, b"x")
    assert target.is_file()
