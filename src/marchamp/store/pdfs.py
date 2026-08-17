"""Stored PDFs (FR-026f–FR-026i, data-model.md § Stored PDF).

A pack PDF is ~202 MB and ~49 s of work, so this module exists to make sure that work
happens once. Three decisions carry it.

**The reuse key is the filename** (`<pack>@<snapshot_revision>@<image_identity>.pdf`). That
is what lets `os.link` be the uniqueness primitive: linking a finished temporary file into
place either succeeds or raises `EEXIST`, atomically, in one syscall. The obvious
alternative — "does the file exist? no? write it" — is a race between two runs of the same
pack whose loser overwrites a 202 MB file another request is reading.

**Refcounting is the kernel's.** A run holds a hard link to the PDF it produced, at
`runs/<id>/output.pdf`. Deleting the run and deleting the stored PDF are then two
independent decrements of one link count, and neither has to know whether the other has
happened. Bytes are freed exactly when the last name goes, which is what FR-026g's deletion
has to mean at this size.

**Ownership differs by kind, and this is the part that is easy to get wrong.** A `standard`
PDF belongs to the *pack* (FR-026g1): deleting one run of Captain America must not revoke
reuse for every other run of Captain America, so `detach_run` only ever drops the run's own
link. A `saved` PDF is that run's customized output, and deleting it is deliberate.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from marchamp.store.atomic import atomic_write_json, durable_fsync, fsync_dir
from marchamp.store.layout import StateLayout


class PdfKind(StrEnum):
    STANDARD = "standard"
    SAVED = "saved"


@dataclass(frozen=True)
class StoredPdf:
    kind: PdfKind
    #: The standard PDF's reuse key, or the saved PDF's opaque id.
    id: str
    name: str
    path: Path
    byte_size: int


class PdfStore:
    def __init__(self, layout: StateLayout) -> None:
        self.layout = layout

    # ------------------------------------------------------------------- standard

    def find_standard(
        self, pack_code: str, snapshot_revision: str, image_identity: str
    ) -> StoredPdf | None:
        """The pack's PDF for exactly this card data and these images, or None (FR-026f).

        Every component of the key is load-bearing: the revision so a refresh invalidates
        rather than serving a PDF built from superseded card data, and the image identity so
        a second library resolving even one card to different bytes rebuilds (SC-006k).
        """
        path = self.layout.standard_pdf(pack_code, snapshot_revision, image_identity)
        if not path.is_file():
            return None
        return StoredPdf(
            kind=PdfKind.STANDARD,
            id=path.stem,
            name=self._standard_name(pack_code),
            path=path,
            byte_size=path.stat().st_size,
        )

    def put_standard(
        self, pack_code: str, snapshot_revision: str, image_identity: str, data: bytes
    ) -> StoredPdf:
        target = self.layout.standard_pdf(pack_code, snapshot_revision, image_identity)
        self._link_into_place(target, data)
        return StoredPdf(
            kind=PdfKind.STANDARD,
            id=target.stem,
            name=self._standard_name(pack_code),
            path=target,
            byte_size=target.stat().st_size,
        )

    def delete_standard(self, pack_code: str, snapshot_revision: str, image_identity: str) -> None:
        """FR-026g. The next assembly of that pack rebuilds (US5 scenario 6b)."""
        with contextlib.suppress(FileNotFoundError):
            self.layout.standard_pdf(pack_code, snapshot_revision, image_identity).unlink()

    @staticmethod
    def _standard_name(pack_code: str) -> str:
        """Derived from the pack, never asked of the user — a standard PDF is the pack's."""
        return f"{pack_code} (whole pack)"

    # ---------------------------------------------------------------------- saved

    def put_saved(self, data: bytes, name: str) -> StoredPdf:
        """A customized run's output, titled by the user (FR-026i).

        The title is metadata, not a filename. "Wasp — aggression, v2 (final)" is a good
        name and a bad path, so the file gets an id and the title goes in a sidecar.
        """
        saved_id = secrets.token_hex(8)
        target = self.layout.saved_pdf(saved_id)
        self._link_into_place(target, data)
        atomic_write_json(target.with_suffix(".json"), {"id": saved_id, "name": name})
        return StoredPdf(
            kind=PdfKind.SAVED,
            id=saved_id,
            name=name,
            path=target,
            byte_size=target.stat().st_size,
        )

    def delete_saved(self, saved_id: str) -> None:
        path = self.layout.saved_pdf(saved_id)
        for p in (path, path.with_suffix(".json")):
            with contextlib.suppress(FileNotFoundError):
                p.unlink()

    # ------------------------------------------------------------------ run links

    def attach_to_run(self, run_id: str, stored: StoredPdf) -> Path:
        """Give the run its own name for the same bytes.

        Replacing an existing link rather than failing: a run that re-renders after the user
        changed a card must not trip over the link it made last time.
        """
        link = self.layout.run_dir(run_id) / "output.pdf"
        link.parent.mkdir(parents=True, exist_ok=True)
        # Link to a temporary name, then rename over — `os.link` refuses an existing target
        # and unlinking first would leave the run with no PDF if the link then failed.
        staging = link.with_name(f".output.{secrets.token_hex(4)}.pdf")
        os.link(stored.path, staging)
        os.replace(staging, link)
        fsync_dir(link.parent)
        return link

    def detach_run(self, run_id: str) -> None:
        """Drop the run's link only.

        For a standard PDF this frees nothing, which is the point (FR-026g1, SC-006h): the
        copy in `pdfs/standard/` still holds a name, so the pack keeps its PDF. For a saved
        PDF the caller deletes the stored entry too, and the bytes go when both names do.
        """
        with contextlib.suppress(FileNotFoundError):
            (self.layout.run_dir(run_id) / "output.pdf").unlink()

    # -------------------------------------------------------------------- listing

    def list_stored(self) -> list[StoredPdf]:
        """Everything the user can delete, with the size that makes deleting a decision."""
        out: list[StoredPdf] = []
        standard_dir = self.layout.standard_pdfs()
        if standard_dir.is_dir():
            for p in sorted(standard_dir.glob("*.pdf")):
                pack = p.stem.split("@", 1)[0]
                out.append(
                    StoredPdf(
                        PdfKind.STANDARD,
                        p.stem,
                        self._standard_name(pack),
                        p,
                        p.stat().st_size,
                    )
                )
        saved_dir = self.layout.saved_pdfs()
        if saved_dir.is_dir():
            for p in sorted(saved_dir.glob("*.pdf")):
                sidecar = p.with_suffix(".json")
                name = p.stem
                if sidecar.is_file():
                    with contextlib.suppress(OSError, ValueError, KeyError):
                        name = json.loads(sidecar.read_text())["name"]
                out.append(StoredPdf(PdfKind.SAVED, p.stem, name, p, p.stat().st_size))
        return out

    # -------------------------------------------------------------------- interna

    def _link_into_place(self, target: Path, data: bytes) -> None:
        """Write to a temporary file in the same directory, then link it into place.

        `os.link` raising `FileExistsError` is not an error condition to work around — it is
        the answer. Another run finished the same pack first, and by FR-026h an identical
        key means identical bytes, so the existing file is the one to keep.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".pdf.", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                durable_fsync(handle.fileno())
            # FileExistsError is the answer, not a problem: another run finished the same
            # pack first, and an identical key means identical bytes (FR-026h).
            with contextlib.suppress(FileExistsError):
                os.link(tmp, target)
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        fsync_dir(target.parent)
