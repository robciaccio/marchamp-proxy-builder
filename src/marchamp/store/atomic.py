"""Crash-atomic file replacement (ADR 0001, FR-026b, FR-026f).

**LOAD-BEARING. Read ADR 0001 before changing anything here.**

ADR 0001 chose plain files over SQLite for the run store. The dissenting reviewers accepted
that on one stated condition: that this module be reviewed as the crash-atomicity mechanism
rather than as a small helper, because it is where the guarantee SQLite would have provided
now lives. Everything below is a correctness requirement; none of it is defensive habit.

A durable replacement is four steps, in this order:

1. write the new contents to a temporary file **in the target's own directory** — a rename
   is only atomic within one filesystem, and a temporary file elsewhere silently degrades
   to copy-then-delete on any machine where the two are different mounts;
2. sync that file, so its data is on the medium before anything points at it;
3. `os.replace`, which is atomic: a concurrent reader sees the old bytes or the new ones
   and never a mixture, and a crash mid-way leaves one or the other;
4. sync the **directory**, so the rename itself survives. This is the step that is almost
   always missing. Without it the data is safe and the name is not: recovery can find the
   file back under its old name with the new contents stranded in an unreferenced inode.

On Darwin, step 2 uses `F_FULLFSYNC` rather than `fsync`. `fsync` there returns once the
data has been handed to the drive, not once the drive has committed it — the drive's own
write cache is volatile, so `fsync` alone makes this module's promise false on the platform
it mostly runs on. `F_FULLFSYNC` is slower for exactly the reason it is correct.

Nothing here defends against a torn write *within* a sector or against a filesystem that
lies about `F_FULLFSYNC`; nothing portable can. What it defends against is the ordinary
case — the machine losing power or the process being killed mid-write — which is the case
that actually happens to a laptop application.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

#: Present on Darwin only. Resolved once at import so a test can substitute it and reach
#: the fallback branch on a machine that has the real thing.
try:
    import fcntl

    F_FULLFSYNC: int | None = getattr(fcntl, "F_FULLFSYNC", None)
except ImportError:  # pragma: no cover - POSIX only, and workers.py already refuses Windows
    fcntl = None  # type: ignore[assignment]
    F_FULLFSYNC = None


def durable_fsync(fd: int) -> None:
    """Flush a file descriptor as far down as the platform allows.

    Falls back to `fsync` when `F_FULLFSYNC` is unavailable *or* unsupported by the
    filesystem — some do not implement it and return `ENOTSUP` — because a weaker sync is
    better than an exception, and the caller has no better option to offer.
    """
    if F_FULLFSYNC is not None and fcntl is not None:
        try:
            fcntl.fcntl(fd, F_FULLFSYNC)
            return
        except OSError:
            pass
    os.fsync(fd)


def fsync_dir(directory: Path) -> None:
    """Sync a directory so a rename within it survives a crash.

    Opening a directory read-only and syncing it is the POSIX way to do this. It is a no-op
    on filesystems that do not need it and is not optional on the ones that do.
    """
    fd = os.open(directory, os.O_RDONLY)
    try:
        durable_fsync(fd)
    except OSError:  # pragma: no cover - some filesystems refuse to sync a directory
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace `path` with `data`, atomically and durably."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # `delete=False` because the file must outlive the handle in order to be renamed; the
    # cleanup below is what closes that off on every failure path.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            # Inside the `with`, so the buffer is flushed to the descriptor first. Syncing
            # a descriptor whose userspace buffer is still full syncs nothing useful.
            durable_fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str) -> None:
    """UTF-8, always. Card names carry em dashes and non-ASCII letters."""
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON in a canonical form.

    `sort_keys` and fixed separators are not cosmetic: the snapshot revision is a hash of
    this serialisation (research R10), so key order varying between two writes of the same
    data would produce a new revision and invalidate every reused PDF for no reason
    (FR-026h).
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    atomic_write_text(path, text + "\n")
