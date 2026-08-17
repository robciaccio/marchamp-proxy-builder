"""Where durable state lives (ADR 0001, data-model.md § Assembly Run, § Stored PDF).

One module owns every path under the state directory, because three concerns read the same
layout — the run store writes it, the PDF store links into it, and the startup sweep deletes
from it — and a sweep that disagrees with the writer about where uploads live deletes the
user's uploads.

    <state>/
      runs/<run_id>/run.json
      runs/<run_id>/uploads/<sha256>
      pdfs/standard/<pack>@<snapshot_revision>@<image_identity>.pdf
      pdfs/saved/<uuid>.pdf
      snapshots/<pack_code>.json
      snapshots/packs.json

Every identifier arriving here comes from outside the process — a run id from a URL, a pack
code from upstream, a digest from an upload — so each is validated against a whitelist
rather than sanitised. Sanitising invites the question of whether the sanitiser is complete;
a whitelist does not.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

#: A run id: what `new_run_id` produces, and nothing else.
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: The same rule the MarvelCDB client applies before a pack code reaches a URL (FR-003).
#: Stated in both places on purpose — a filename and a URL are different attack surfaces,
#: and neither should depend on the other having checked.
PACK_CODE_RE = re.compile(r"^[a-z0-9_]{1,32}$")

#: Lowercase hex only, so one set of bytes has exactly one filename.
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

#: A saved PDF's id. Never the user's title for it (FR-026i): "Wasp — aggression (final)"
#: is a perfectly good name and a bad filename.
SAVED_ID_RE = re.compile(r"^[0-9a-f]{16,32}$")

#: Truncated to 16 hex, as data-model.md § Pack Snapshot specifies for `revision`.
DIGEST16_RE = re.compile(r"^[0-9a-f]{16}$")


class UnsafeIdentifier(ValueError):
    """An identifier that must not become a path component."""


def _checked(value: str, pattern: re.Pattern[str], what: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise UnsafeIdentifier(f"{what} must match {pattern.pattern}, got {value!r}")
    return value


class StateLayout:
    """Path construction only. Touches the filesystem exactly where it says it does."""

    def __init__(self, root: Path) -> None:
        # Not resolved and not created here: this is constructed on every import path there
        # is, including `marchamp --help`, and a config object must not have side effects.
        self.root = Path(root)

    # ------------------------------------------------------------------ construction

    @staticmethod
    def new_run_id() -> str:
        """Unguessable, lowercase hex, filesystem-safe.

        Unguessable is not for secrecy — the service is loopback-only with one user — but
        because a run id names a directory the application deletes, and a predictable id
        makes an accidental collision between two runs a real event rather than a
        hypothetical one.
        """
        return secrets.token_hex(16)

    def ensure(self) -> None:
        """Create the fixed skeleton. Called on startup, and safe to repeat."""
        for d in (self.runs_dir(), self.standard_pdfs(), self.saved_pdfs(), self.snapshots_dir()):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------- runs

    def runs_dir(self) -> Path:
        return self.root / "runs"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir() / _checked(run_id, RUN_ID_RE, "run id")

    def run_record(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def uploads_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "uploads"

    def upload(self, run_id: str, content_digest: str) -> Path:
        """Uploaded bytes, stored under their own SHA-256 (research R9).

        Content-addressed so a resumed run keeps a manual resolution after the source file
        moves (FR-026e), and so the same file uploaded twice costs one copy.
        """
        return self.uploads_dir(run_id) / _checked(content_digest, SHA256_RE, "content digest")

    # ------------------------------------------------------------------------- PDFs

    def pdfs_dir(self) -> Path:
        return self.root / "pdfs"

    def standard_pdfs(self) -> Path:
        return self.pdfs_dir() / "standard"

    def saved_pdfs(self) -> Path:
        return self.pdfs_dir() / "saved"

    def standard_pdf(self, pack_code: str, snapshot_revision: str, image_identity: str) -> Path:
        """The name **is** FR-026h's reuse key.

        Encoding the key in the filename is what lets `os.link` fail with `EEXIST` and be
        the atomic uniqueness primitive (T018). A name derived from anything else would
        need a check-then-write, which is a race between two runs of the same pack.
        """
        pack = _checked(pack_code, PACK_CODE_RE, "pack code")
        revision = _checked(snapshot_revision, DIGEST16_RE, "snapshot revision")
        identity = _checked(image_identity, DIGEST16_RE, "image identity")
        return self.standard_pdfs() / f"{pack}@{revision}@{identity}.pdf"

    def saved_pdf(self, saved_id: str) -> Path:
        return self.saved_pdfs() / f"{_checked(saved_id, SAVED_ID_RE, 'saved PDF id')}.pdf"

    # -------------------------------------------------------------------- snapshots

    def snapshots_dir(self) -> Path:
        return self.root / "snapshots"

    def snapshot(self, pack_code: str) -> Path:
        return self.snapshots_dir() / f"{_checked(pack_code, PACK_CODE_RE, 'pack code')}.json"

    def pack_index(self) -> Path:
        """The reduced `GET /api/public/packs/` listing. One file, not per-pack."""
        return self.snapshots_dir() / "packs.json"
