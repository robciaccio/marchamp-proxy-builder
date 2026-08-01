"""Generation orchestration (FR-018, FR-018a, FR-020a, FR-020b, FR-021a, FR-022)."""

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


@dataclass
class Generation:
    id: str
    deck_id: str
    page_size: PageSize
    fit_mode: FitMode
    catalog_revision: str
    status: str = "pending"
    page_count: int | None = None
    card_count: int | None = None
    document: bytes | None = None
    substitutions: list[Substitution] = field(default_factory=list)
    failures: list[GenerationFailure] = field(default_factory=list)
    page_face_counts: list[list[str]] = field(default_factory=list)
    duration_ms: int | None = None


class GenerationService:
    """Resolve -> validate -> compose. Never retries on its own (FR-021a)."""

    def __init__(self, catalog_path: Path, image_dir: Path) -> None:
        self.catalog_path = Path(catalog_path)
        self.image_dir = Path(image_dir)

    def load(self) -> Catalog:
        return load_catalog_file(self.catalog_path)

    def decks(self) -> list[HeroDeck]:
        return list(self.load().decks)

    def _compose(self, pages, page_size, fit_mode) -> bytes:
        return compose(pages, page_size, fit_mode, self.image_dir)

    def generate(
        self,
        deck_id: str,
        page_size: PageSize = PageSize.LETTER,
        fit_mode: FitMode = FitMode.CROP,
    ) -> Generation:
        started = time.monotonic()
        gen = Generation(
            id=uuid.uuid4().hex,
            deck_id=deck_id,
            page_size=page_size,
            fit_mode=fit_mode,
            catalog_revision="",
        )

        try:
            catalog = self.load()
        except CatalogError as exc:
            return self._fail(
                gen, [GenerationFailure(FailureKind.CATALOG_INVALID, str(exc))], started
            )
        gen.catalog_revision = catalog.revision

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

        faces, resolutions = expand_faces(catalog, deck_id, self.image_dir)

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
                validate_source(self.image_dir / face.image_ref, slot_w, slot_h, fit_mode)
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

        if failures:
            return self._fail(gen, failures, started)

        pages = paginate(catalog, deck_id, page_size, self.image_dir)
        gen.document = self._compose(pages, page_size, fit_mode)
        gen.page_count = len(pages)
        gen.card_count = face_count(catalog, deck_id)
        gen.page_face_counts = [[f.card_id for f in p.faces] for p in pages]
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
