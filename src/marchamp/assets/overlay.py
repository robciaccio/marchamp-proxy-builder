"""Two roots behind one adapter (FR-004, FR-007, FR-026e, research R8).

A run reads faces from the scan library the user named *and* from files they uploaded for
cards the library does not hold. Those live in unrelated places — one is a mounted Drive
folder that changes every run, the other is the run's own directory under app-owned state —
and composition must not know that either of them is a directory.

The routing rule is the ref's prefix and nothing else:

    upload:<sha256>   ->  <run_dir>/uploads/<sha256>
    anything else     ->  <library_root>/<ref>

**Two roots means two containment checks, not one check applied twice.** A library ref is
influenced by what the library holds and by what the resolver matched, so it is contained
against the folder the run named (FR-007). An upload ref names a file this application wrote
under a digest it computed, so it is validated against *that shape* — which refuses every
traversal at once rather than the ones someone remembered to think of.

The store is a value object holding two paths, deliberately. Decode and render cross a
`spawn`ed process boundary, so it is pickled; a store holding an open handle or a lock works
in every test that skips the worker pool and fails in the only place it counts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.assets.store import AssetInfo

#: The prefix that routes a ref to the run's own uploads rather than to the library.
UPLOAD_PREFIX = "upload:"

#: Lowercase hex, as `store.layout` writes it. Kept in step with `layout.SHA256_RE` by
#: agreeing on the digest's shape rather than by importing across the two packages —
#: `assets/` must not depend on `store/`, which is where the run directory comes from.
UPLOAD_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class OverlayStore:
    """Reads a run's faces from the library and from the run's uploads."""

    def __init__(self, library_root: Path, run_dir: Path) -> None:
        # Composed from the existing adapter rather than reimplementing containment: the
        # library half is exactly feature 001's behaviour, and having one traversal check in
        # the project is worth more than saving the delegation.
        self._library = LocalDirectoryStore(library_root)
        self._uploads = LocalDirectoryStore(Path(run_dir) / "uploads")

    def _route(self, ref: str) -> tuple[LocalDirectoryStore, str]:
        if not ref.startswith(UPLOAD_PREFIX):
            return self._library, ref
        digest = ref.removeprefix(UPLOAD_PREFIX)
        if not UPLOAD_DIGEST_RE.match(digest):
            raise ValueError(
                f"an upload ref must be {UPLOAD_PREFIX}<sha256 in lowercase hex>, got {ref!r}"
            )
        return self._uploads, digest

    def exists(self, ref: str) -> bool:
        try:
            store, inner = self._route(ref)
        except ValueError:
            return False
        return store.exists(inner)

    def open(self, ref: str) -> BinaryIO:
        store, inner = self._route(ref)
        return store.open(inner)

    def describe(self, ref: str) -> AssetInfo:
        store, inner = self._route(ref)
        info = store.describe(inner)
        # Report the ref the caller passed, not the routed one. A report naming a bare
        # digest where the run recorded `upload:<digest>` sends the reader looking for a
        # file that does not exist under that name.
        return AssetInfo(
            ref=ref,
            byte_size=info.byte_size,
            detected_format=info.detected_format,
            width_px=info.width_px,
            height_px=info.height_px,
        )
