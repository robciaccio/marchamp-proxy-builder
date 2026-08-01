"""Generation orchestration (FR-016a, FR-016b, FR-018, FR-018a, FR-020a, FR-020b, FR-021a,
FR-022, FR-0A4).

Split into `begin` and `run` on purpose. `begin` creates the resource and pins the catalog
revision; `run` does the work and may take up to two minutes. Keeping them apart is what
lets the HTTP layer answer the POST immediately and report advancement while the work
happens (FR-016a) — an interface that looks frozen for two minutes is indistinguishable
from one that has failed.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from marchamp.api.errors import FailureKind, GenerationFailure
from marchamp.catalog.loader import CatalogError, load_catalog_file
from marchamp.catalog.models import Catalog, HeroDeck
from marchamp.catalog.printings import ResolutionOutcome, Substitution
from marchamp.catalog.validation import validate
from marchamp.config import Limits
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import expand_faces, face_count, paginate
from marchamp.observability.logging import GenerationRecord, write_record
from marchamp.render.document import compose
from marchamp.render.images import FitMode, ImageTooSmall, ImageUnreadable, validate_source

# Validation issue kind -> the FR-021 failure condition it actually represents.
_ISSUE_TO_FAILURE = {
    "missing_image_file": FailureKind.ASSET_MISSING,
    "missing_back_image": FailureKind.ASSET_MISSING,
    "unsafe_image_path": FailureKind.CATALOG_INVALID,
}


class _LimitExceeded(Exception):
    """A FR-0A4 ceiling was reached mid-run. Unwinds out of the compose callback."""


@dataclass
class Generation:
    id: str
    deck_id: str
    page_size: PageSize
    fit_mode: FitMode
    catalog_revision: str
    status: str = "pending"
    progress: float | None = None
    pages_ready: int = 0
    page_count: int | None = None
    card_count: int | None = None
    document: bytes | None = None
    substitutions: list[Substitution] = field(default_factory=list)
    failures: list[GenerationFailure] = field(default_factory=list)
    page_face_counts: list[list[str]] = field(default_factory=list)
    duration_ms: int | None = None
    # Pages already composed, each as a standalone PDF, so a preview can be shown while the
    # rest of the deck is still rendering (FR-016b).
    page_documents: list[bytes] = field(default_factory=list, repr=False)
    # The catalog as it stood when this generation was created. Held, rather than re-read,
    # so editing the catalog mid-run cannot yield a document mixing two revisions.
    catalog: Catalog | None = field(default=None, repr=False)

    @property
    def terminal(self) -> bool:
        return self.status in ("succeeded", "failed")

    def preview_document(self, page_number: int) -> bytes | None:
        """The bytes to rasterise for a 1-based page, or None if it is not ready yet.

        Once the run has succeeded this serves slices of the finished document itself, so a
        preview and a download can never disagree about a page that exists in both.
        """
        if page_number < 1:
            return None
        if self.status == "succeeded" and self.document is not None:
            return self.document if page_number <= (self.page_count or 0) else None
        if page_number <= len(self.page_documents):
            return self.page_documents[page_number - 1]
        return None


class GenerationService:
    """Resolve -> validate -> compose. Never retries on its own (FR-021a)."""

    def __init__(self, catalog_path: Path, image_dir: Path, limits: Limits | None = None) -> None:
        self.catalog_path = Path(catalog_path)
        self.image_dir = Path(image_dir)
        self.limits = limits or Limits()

    def load(self) -> Catalog:
        return load_catalog_file(self.catalog_path)

    def decks(self) -> list[HeroDeck]:
        return list(self.load().decks)

    def _compose(self, pages, page_size, fit_mode, on_page=None) -> bytes:
        return compose(pages, page_size, fit_mode, self.image_dir, on_page=on_page)

    # ------------------------------------------------------------------ lifecycle

    def begin(
        self,
        deck_id: str,
        page_size: PageSize = PageSize.LETTER,
        fit_mode: FitMode = FitMode.CROP,
    ) -> Generation:
        """Create the resource and pin the catalog revision. Does no rendering."""
        gen = Generation(
            id=uuid.uuid4().hex,
            deck_id=deck_id,
            page_size=page_size,
            fit_mode=fit_mode,
            catalog_revision="",
            progress=0.0,
        )
        try:
            gen.catalog = self.load()
        except CatalogError as exc:
            return self._fail(
                gen, [GenerationFailure(FailureKind.CATALOG_INVALID, str(exc))], time.monotonic()
            )
        gen.catalog_revision = gen.catalog.revision
        return gen

    def generate(
        self,
        deck_id: str,
        page_size: PageSize = PageSize.LETTER,
        fit_mode: FitMode = FitMode.CROP,
    ) -> Generation:
        """Begin and run to completion. The synchronous path, for callers with no UI."""
        return self.run(self.begin(deck_id, page_size=page_size, fit_mode=fit_mode))

    def run(self, gen: Generation) -> Generation:
        """Do the work, advancing `gen` in place so a reader can watch it (FR-016a)."""
        started = time.monotonic()
        if gen.terminal or gen.catalog is None:  # begin() already settled it
            return gen
        catalog = gen.catalog
        gen.status = "running"

        report = validate(catalog, self.image_dir)
        if not report.valid:
            # Map each issue to the taxonomy FR-021 defines. A card whose every printing is
            # absent is an *asset* problem, not a malformed catalog, and the difference is
            # what the user needs to know to fix it.
            return self._fail(
                gen,
                [
                    GenerationFailure(
                        _ISSUE_TO_FAILURE.get(e.kind, FailureKind.CATALOG_INVALID),
                        e.detail,
                        e.card_id,
                        e.card_name,
                    )
                    for e in report.errors
                ],
                started,
            )

        faces, resolutions = expand_faces(catalog, gen.deck_id, self.image_dir)

        if len(faces) > self.limits.max_faces_per_generation:
            return self._fail(
                gen,
                [
                    GenerationFailure(
                        FailureKind.LIMIT_EXCEEDED,
                        f"deck expands to {len(faces)} faces, above the "
                        f"{self.limits.max_faces_per_generation}-face ceiling",
                    )
                ],
                started,
            )

        # Two units of work per face — checking its source, then drawing it — so progress
        # tracks the work actually remaining rather than jumping at phase boundaries.
        total_units = max(1, len(faces) * 2)
        done_units = 0

        # Collect every problem before giving up (FR-020a).
        failures: list[GenerationFailure] = []
        for res in resolutions:
            if res.outcome is ResolutionOutcome.UNAVAILABLE:
                failures.append(
                    GenerationFailure(
                        FailureKind.ASSET_MISSING,
                        "no printing of this card has a usable image on disk",
                        res.card.id,
                        res.card.name,
                    )
                )
            elif res.substitution is not None:
                gen.substitutions.append(res.substitution)

        slot_w, slot_h = (63.5, 88.9)
        for face in faces:
            try:
                validate_source(self.image_dir / face.image_ref, slot_w, slot_h, gen.fit_mode)
            except ImageTooSmall as exc:
                failures.append(
                    GenerationFailure(
                        FailureKind.ASSET_TOO_SMALL, str(exc), face.card_id, face.card_name
                    )
                )
            except ImageUnreadable as exc:
                failures.append(
                    GenerationFailure(
                        FailureKind.ASSET_UNREADABLE, str(exc), face.card_id, face.card_name
                    )
                )
            done_units += 1
            gen.progress = done_units / total_units

        if failures:
            return self._fail(gen, failures, started)

        pages = paginate(catalog, gen.deck_id, gen.page_size, self.image_dir)

        def on_page(index: int, page_document: bytes) -> None:
            nonlocal done_units
            gen.page_documents.append(page_document)
            gen.pages_ready = len(gen.page_documents)
            done_units += len(pages[index].faces)
            gen.progress = min(1.0, done_units / total_units)
            elapsed = time.monotonic() - started
            if elapsed > self.limits.generation_wall_clock_s:
                # FR-003b: an abandoned generation must not hold resources indefinitely.
                raise _LimitExceeded(
                    f"generation exceeded the {self.limits.generation_wall_clock_s}s ceiling "
                    f"after {elapsed:.0f}s"
                )

        try:
            gen.document = self._compose(pages, gen.page_size, gen.fit_mode, on_page)
        except _LimitExceeded as exc:
            return self._fail(
                gen, [GenerationFailure(FailureKind.LIMIT_EXCEEDED, str(exc))], started
            )

        gen.page_count = len(pages)
        gen.card_count = face_count(catalog, gen.deck_id)
        gen.page_face_counts = [[f.card_id for f in p.faces] for p in pages]
        gen.progress = 1.0
        gen.status = "succeeded"
        gen.duration_ms = int((time.monotonic() - started) * 1000)
        self._record(gen, faces)
        return gen

    def _fail(
        self, gen: Generation, failures: list[GenerationFailure], started: float
    ) -> Generation:
        gen.status = "failed"
        gen.failures = failures
        gen.document = None  # FR-020b: no partial output, ever
        gen.page_documents.clear()  # nor a partial preview of one
        gen.pages_ready = 0
        gen.duration_ms = int((time.monotonic() - started) * 1000)
        self._record(gen, [])
        return gen

    def _record(self, gen: Generation, faces) -> None:
        write_record(
            GenerationRecord(
                request_id=gen.id,
                deck_id=gen.deck_id,
                resolved_card_ids=sorted({f.card_id for f in faces}),
                catalog_revision=gen.catalog_revision,
                fit_mode=gen.fit_mode.value,
                page_size=gen.page_size.name,
                outcome=gen.status,
                page_count=gen.page_count,
                duration_ms=gen.duration_ms,
                failure_kinds=sorted({f.kind.value for f in gen.failures}),
                substitution_count=len(gen.substitutions),
            )
        )
