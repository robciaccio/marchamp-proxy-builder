"""HTTP endpoints (contracts/openapi.yaml).

Generation is a POST'd resource with its own identity rather than a side effect of
rendering a page — Principle II's wording, and what keeps the product drivable headlessly.

Every route declares a response model. That is not decoration: FastAPI generates component
schemas from these types, and a route returning a bare dict generates none, which would
leave the contract naming types that describe nothing.
"""

from __future__ import annotations

import hashlib
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path as FilePath
from typing import Annotated, Any, Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from marchamp.api import schemas
from marchamp.assembly.service import AssemblyError, AssemblyService, library_problem
from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.catalog.loader import CatalogError
from marchamp.catalog.validation import validate
from marchamp.config import Limits
from marchamp.generations.registry import GenerationRegistry
from marchamp.generations.service import Generation as GenerationState
from marchamp.generations.service import GenerationService
from marchamp.layout.geometry import SLOT_SIZE_MM, PageSize
from marchamp.layout.paginate import face_count
from marchamp.render import preview
from marchamp.render.images import (
    MIN_DPI,
    FitMode,
    ImageTooSmall,
    ImageUnreadable,
    validate_source,
)
from marchamp.store.layout import StateLayout, UnsafeIdentifier
from marchamp.store.pdfs import PdfStore
from marchamp.store.runs import RunNotFound, RunState
from marchamp.upstream.client import MarvelCdbClient
from marchamp.upstream.snapshots import SnapshotStore, SnapshotUnavailable

# One generation is a couple of CPU-seconds of image work; a single local user will not
# have many in flight. Bounded so an abandoned run cannot accumulate into a thread leak
# (FR-003b), and daemon threads so closing the app never hangs on one.
_MAX_CONCURRENT_GENERATIONS = 2


def _problem(description: str) -> dict[str, Any]:
    """An RFC 9457 error response, declared for OpenAPI."""
    return {
        "description": description,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
        },
    }


def _binary(media_type: str, description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {media_type: {"schema": {"type": "string", "format": "binary"}}},
    }


#: `POST /api/assemblies/{run_id}/decklist` carries two body shapes on one path, and
#: FastAPI generates a request body from a signature — which can describe one shape or the
#: other, never both. Declared here instead, matching `contracts/openapi.yaml`; the schemas
#: are inline rather than `$ref`s because a component is only generated when a route
#: signature references the model, and this route's does not.
_DECKLIST_REQUEST_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["action"],
                "properties": {
                    "action": {"type": "string", "enum": ["confirm", "select", "skip"]},
                    "ref": {"type": "string"},
                },
            }
        },
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
    },
}

#: Read in blocks so an upload is never held whole in memory. Matches the digest block size
#: `assembly.resolve` reads library scans with.
_UPLOAD_BLOCK = 1 << 20


async def _receive(upload: Any, into: FilePath, limits: Limits) -> tuple[FilePath, str]:
    """Stream an upload to a file under a byte ceiling, hashing as it goes (research R9).

    The ceiling is enforced **while writing**, not from `Content-Length`: a client controls
    that header, and trusting it would mean the bound applies to honest requests only. The
    partial file is discarded on the way out, so an over-long upload costs the ceiling in
    disk and nothing more.

    The name is taken from the upload's own filename and reduced to its last component. It
    is the only thing about where the file came from that is ever retained (FR-027), and it
    arrived from a browser, so `../../etc` is not a hypothetical.
    """
    name = FilePath(upload.filename or "upload").name or "upload"
    path = into / name
    hasher = hashlib.sha256()
    written = 0
    with path.open("wb") as handle:
        while block := await upload.read(_UPLOAD_BLOCK):
            written += len(block)
            if written > limits.upload_bytes:
                handle.close()
                path.unlink(missing_ok=True)
                raise AssemblyError(
                    f"{name!r} is larger than the {limits.upload_bytes // (1024 * 1024)} MB "
                    "an uploaded card image may be. A 600 DPI card scan is a few megabytes.",
                    status=400,
                )
            hasher.update(block)
            handle.write(block)
    return path, hasher.hexdigest()


def _require_decodable(path: FilePath, fit_mode: FitMode) -> None:
    """Refuse anything the application cannot read as an image (FR-028).

    Read through the asset adapter over the temporary directory rather than opened
    directly, so this is the same `validate_source` the library path uses and there is one
    decode rule in the project rather than two that can drift.
    """
    store = LocalDirectoryStore(path.parent)
    slot_w, slot_h = SLOT_SIZE_MM
    try:
        validate_source(store, path.name, slot_w, slot_h, fit_mode)
    except ImageUnreadable as exc:
        raise AssemblyError(
            f"{path.name!r} could not be read as an image ({exc}). Supply a file this "
            "application can decode — a TIFF, PNG, or JPEG scan of the card.",
            status=400,
        ) from exc
    except ImageTooSmall:
        # Not this function's refusal; `_require_printable` is where that decision lives.
        return


def _require_printable(path: FilePath, fit_mode: FitMode) -> None:
    """FR-028 in full: decodable **and** printable at the required resolution.

    A library scan below the floor is a warning rather than a refusal (FR-035), because the
    user cannot re-take it and is entitled to decide a soft card is fine. A file they are
    choosing right this moment is a different situation: they can pick another one, and
    saying so at the point of choice is the whole value of validating on upload.
    """
    _require_decodable(path, fit_mode)
    store = LocalDirectoryStore(path.parent)
    slot_w, slot_h = SLOT_SIZE_MM
    try:
        validate_source(store, path.name, slot_w, slot_h, fit_mode)
    except ImageTooSmall as exc:
        raise AssemblyError(
            f"{path.name!r} cannot print at {MIN_DPI} DPI at card size: {exc}. The card is "
            "left unresolved; supply a higher-resolution scan.",
            status=400,
        ) from exc


def _parse_json_body(body: bytes, model: type[BaseModel]) -> Any:
    """Validate a hand-read JSON body, naming the field at fault.

    Only needed because the deck list route reads its own body to serve two media types on
    one path; every other route lets FastAPI do this.
    """
    try:
        return model.model_validate_json(body or b"{}")
    except ValidationError as exc:
        where = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise AssemblyError(where or "the request body could not be validated", status=422) from exc


def _as_schema(gen: GenerationState) -> schemas.Generation:
    # Lists are copied because the worker thread may still be appending to them.
    return schemas.Generation(
        id=gen.id,
        deck_id=gen.deck_id,
        page_size=gen.page_size,
        fit_mode=gen.fit_mode,
        catalog_revision=gen.catalog_revision,
        status=gen.status,
        progress=gen.progress,
        pages_ready=gen.pages_ready,
        page_count=gen.page_count,
        card_count=gen.card_count,
        substitutions=[schemas.Substitution(**vars(s)) for s in list(gen.substitutions)],
        failures=[schemas.Failure(**f.as_dict()) for f in list(gen.failures)],
    )


def register_routes(app: FastAPI) -> None:
    settings = app.state.settings
    registry = GenerationRegistry()
    app.state.registry = registry
    workers = ThreadPoolExecutor(
        max_workers=_MAX_CONCURRENT_GENERATIONS, thread_name_prefix="marchamp-gen"
    )
    app.state.generation_workers = workers

    def image_store() -> LocalDirectoryStore:
        """Feature 001's configured directory, behind the adapter (FR-004, research R8).

        Feature 002's runs use `assets.OverlayStore` instead, built per run over the library
        root that run named plus its own upload directory — which is why nothing here can be
        a module-level singleton.
        """
        return LocalDirectoryStore(settings.image_dir)

    def service() -> GenerationService:
        if settings.image_dir is None or settings.catalog_path is None:
            raise HTTPException(
                status_code=503,
                detail="; ".join(p.detail for p in settings.problems()),
            )
        return GenerationService(
            catalog_path=settings.catalog_path,
            # Feature 001's decks come from one configured directory, so its store is the
            # plain one. Feature 002's runs overlay a per-run upload directory on top of a
            # per-run library root, which is `assets.OverlayStore` and is built per run.
            store=image_store(),
            limits=settings.limits,
        )

    def load_catalog():
        try:
            return service().load()
        except CatalogError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # ------------------------------------------------------------------- catalog

    @app.get("/api/health", tags=["catalog"], response_model=schemas.Health)
    def get_health() -> schemas.Health:
        problems = settings.problems()
        revision, valid = None, False
        if not problems:
            try:
                cat = service().load()
                revision = cat.revision
                valid = validate(cat, image_store()).valid
            except CatalogError:
                valid = False
        return schemas.Health(
            status="ok",
            catalog_valid=valid,
            catalog_revision=revision,
            image_directory_configured=settings.image_dir is not None,
            problems=[schemas.ConfigProblem(kind=p.kind, detail=p.detail) for p in problems],
        )

    @app.get(
        "/api/catalog/validation",
        tags=["catalog"],
        response_model=schemas.ValidationReport,
        responses={503: _problem("Not configured yet.")},
    )
    def get_catalog_validation() -> schemas.ValidationReport:
        # `valid: false` is a normal 200 — the request succeeded, the catalog did not.
        try:
            cat = service().load()
        except CatalogError as exc:
            return schemas.ValidationReport(
                valid=False,
                errors=[schemas.ValidationIssue(kind="schema_invalid", detail=str(exc))],
                warnings=[],
            )
        report = validate(cat, image_store())

        def as_issue(i) -> schemas.ValidationIssue:
            return schemas.ValidationIssue(
                kind=i.kind,
                detail=(f"{i.card_name}: {i.detail}" if i.card_name else i.detail),
                card_id=i.card_id,
                deck_id=i.deck_id,
            )

        return schemas.ValidationReport(
            valid=report.valid,
            catalog_revision=cat.revision,
            errors=[as_issue(e) for e in report.errors],
            warnings=[as_issue(w) for w in report.warnings],
        )

    # --------------------------------------------------------------------- decks

    @app.get(
        "/api/decks",
        tags=["decks"],
        response_model=schemas.DeckList,
        responses={503: _problem("Catalog is invalid; nothing can be listed.")},
    )
    def list_decks() -> schemas.DeckList:
        cat = load_catalog()
        return schemas.DeckList(
            catalog_revision=cat.revision,
            decks=[
                schemas.DeckSummary(id=d.id, name=d.name, card_count=face_count(cat, d.id))
                for d in cat.decks
            ],
        )

    @app.get(
        "/api/decks/{deck_id}",
        tags=["decks"],
        response_model=schemas.DeckDetail,
        responses={404: _problem("No such deck."), 503: _problem("Catalog is invalid.")},
    )
    def get_deck(deck_id: str) -> schemas.DeckDetail:
        cat = load_catalog()
        deck = cat.deck(deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail=f"No deck {deck_id!r}")

        entries = []
        for e in deck.entries:
            card = cat.card(e.card_id)
            entries.append(
                schemas.DeckEntry(
                    card_id=e.card_id,
                    name=card.name if card else e.card_id,
                    quantity=e.quantity,
                    double_sided=bool(card and card.double_sided),
                    preferred_printing_id=e.preferred_printing_id,
                    preferred_printing_available=bool(
                        card
                        and (p := card.printing(e.preferred_printing_id))
                        and image_store().exists(p.image)
                    ),
                )
            )
        return schemas.DeckDetail(
            id=deck.id,
            name=deck.name,
            card_count=face_count(cat, deck.id),
            hero_card_id=deck.hero_card_id,
            entries=entries,
        )

    # --------------------------------------------------------------- generations

    @app.post(
        "/api/generations",
        status_code=202,
        tags=["generations"],
        response_model=schemas.Generation,
        responses={
            202: {
                "description": "Accepted. Poll the resource for status.",
                "headers": {
                    "Location": {
                        "schema": {"type": "string"},
                        "description": "URL of the created generation.",
                    }
                },
            },
            404: _problem("No such deck."),
            503: _problem("Catalog is invalid."),
        },
    )
    def create_generation(
        body: schemas.GenerationRequest, response: Response
    ) -> schemas.Generation:
        svc = service()
        cat = load_catalog()
        if cat.deck(body.deck_id) is None:
            raise HTTPException(status_code=404, detail=f"No deck {body.deck_id!r}")

        gen = svc.begin(body.deck_id, page_size=body.page_size, fit_mode=body.fit_mode)
        registry.put(gen)
        # Returns before the work is done, so the interface can show advancement rather
        # than blocking for up to two minutes (FR-016a).
        if not gen.terminal:
            workers.submit(svc.run, gen)
        response.headers["Location"] = f"/api/generations/{gen.id}"
        return _as_schema(gen)

    def _require(generation_id: str) -> GenerationState:
        gen = registry.get(generation_id)
        if gen is None:
            raise HTTPException(status_code=404, detail="No such generation")
        return gen

    @app.get(
        "/api/generations/{generation_id}",
        tags=["generations"],
        response_model=schemas.Generation,
        responses={404: _problem("No such generation.")},
    )
    def get_generation(generation_id: str) -> schemas.Generation:
        return _as_schema(_require(generation_id))

    @app.get(
        "/api/generations/{generation_id}/document",
        tags=["generations"],
        response_class=Response,
        responses={
            200: _binary("application/pdf", "The PDF."),
            404: _problem("No such generation."),
            409: _problem("Generation has not succeeded; no document exists."),
        },
    )
    def get_generation_document(generation_id: str) -> Response:
        gen = _require(generation_id)
        if gen.status != "succeeded" or gen.document is None:
            # No partial output, ever (FR-020b).
            raise HTTPException(status_code=409, detail=f"Generation is {gen.status}")
        # Filename carries deck, mode, and page size so a printed sheet stays identifiable
        # after the application closes (FR-008c, FR-009d).
        name = f"{gen.deck_id}-{gen.fit_mode.value}-{gen.page_size.name}.pdf"
        return Response(
            content=gen.document,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get(
        "/api/generations/{generation_id}/pages/{page_number}",
        tags=["generations"],
        response_class=Response,
        responses={
            200: _binary("image/png", "Page raster."),
            404: _problem("No such generation or page."),
            409: _problem("Generation has not succeeded; nothing to preview."),
        },
    )
    def get_generation_page(
        generation_id: str,
        page_number: Annotated[int, Path(ge=1)],
        width: Annotated[
            int,
            Query(
                ge=preview.MIN_WIDTH_PX,
                le=preview.MAX_WIDTH_PX,
                description="Target raster width in pixels. Preview only; never affects the PDF.",
            ),
        ] = preview.DEFAULT_WIDTH_PX,
    ) -> Response:
        gen = _require(generation_id)
        if gen.status == "failed":
            raise HTTPException(status_code=409, detail="Generation failed; nothing to preview")

        document = gen.preview_document(page_number)
        if document is None:
            # A page that is merely not composed yet is genuinely not there yet; the client
            # polls the generation to learn how many pages are ready (FR-016b).
            raise HTTPException(status_code=404, detail=f"Page {page_number} is not available")

        # While running, each page is its own single-page document; once succeeded, it is a
        # slice of the finished PDF. Either way the raster comes from PDF bytes (FR-017).
        index = page_number if gen.status == "succeeded" else 1
        return Response(content=preview.render_page(document, index, width), media_type="image/png")

    # --------------------------------------------------------------- calibration

    @app.get(
        "/api/calibration",
        tags=["calibration"],
        response_class=Response,
        responses={200: _binary("application/pdf", "Calibration PDF.")},
    )
    def get_calibration(page_size: PageSize = PageSize.LETTER) -> Response:
        from marchamp.render.calibration import calibration_pdf

        return Response(content=calibration_pdf(page_size), media_type="application/pdf")

    # --------------------------------------------------------------- assemblies (002)
    #
    # Feature 002's routes. They share the app with 001's but almost nothing else: a run
    # names its own library root and hero folder, so none of `MARCHAMP_IMAGE_DIR`,
    # `MARCHAMP_CATALOG`, or the module-level generation service is involved (FR-005,
    # SC-003a). `serve` starts with both unset and these endpoints work.

    def assemblies() -> AssemblyService:
        """One service per request, because a run's asset store is built per run.

        The snapshot store and the client are cheap to construct and hold no connection
        pool worth reusing across a local single-user session.
        """
        layout = StateLayout(settings.state_dir)
        client = MarvelCdbClient(settings.upstream)
        return AssemblyService(settings, SnapshotStore(layout, client), layout)

    def _if_match(if_match: str | None) -> int | None:
        """The run version the caller read, off the `If-Match` header.

        A header rather than a body field so JSON and multipart requests carry it the same
        way. A malformed value is refused rather than treated as "no precondition": silently
        dropping a precondition is how a lost update happens (ADR 0001).
        """
        if if_match is None:
            return None
        try:
            return int(if_match.strip().strip('"'))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"If-Match must be a run version, got {if_match!r}"
            ) from None

    def _run_response(record) -> schemas.AssemblyRun:
        identification = record.identification or {}
        report = dict(record.report or {})
        unresolved = report.pop("unresolved", [])
        decklist = record.decklist or {}

        candidate = None
        # Shown only while it is still a question. Once decided it is history, and the
        # report carries whether a decklist was printed (FR-013d, SC-006j).
        if decklist.get("candidate") and not decklist.get("decision"):
            candidate = schemas.DecklistCandidate(ref=decklist["candidate"]["ref"])
        elif decklist.get("conflict") and not decklist.get("decision"):
            alternatives = [c["ref"] for c in decklist.get("candidates", [])]
            candidate = schemas.DecklistCandidate(
                ref=alternatives[0] if alternatives else "", alternatives=alternatives
            )

        return schemas.AssemblyRun(
            id=record.id,
            version=record.version,
            library_root=str(record.library_root),
            hero_folder=record.hero_folder,
            state=record.state.value,
            outcome=record.outcome.value if record.outcome else None,
            page_size=record.page_size,
            fit_mode=record.fit_mode,
            identification=(
                schemas.PackIdentification(
                    source=identification.get("source", "identified"),
                    evidence=identification.get("evidence", []),
                    # A pack is confirmed once the run has moved past choosing one.
                    confirmed=record.state
                    not in (RunState.IDENTIFYING, RunState.AWAITING_PACK, RunState.UNIDENTIFIED),
                    pack_code=identification.get("pack_code"),
                    pack_name=identification.get("pack_name"),
                    confidence=identification.get("confidence"),
                )
                if identification
                else None
            ),
            snapshot_revision=record.snapshot_revision,
            snapshot_stale=bool(report.get("snapshot_stale", False)),
            decklist_candidate=candidate,
            # Projected onto the contract's fields rather than splatted: the stored gap also
            # carries both sides of an FR-033 conflict, which belongs in the report's
            # `conflicts` section (Phase 4) and not on the card.
            unresolved=[
                schemas.UnresolvedCard(
                    card_code=u["card_code"],
                    card_name=u["card_name"],
                    side=u["side"],
                    group=u.get("group", "player"),
                    searched=u.get("searched", []),
                )
                for u in unresolved
            ],
            customized=bool(record.customized),
            reused=record.reused,
            pdf_id=(record.pdf or {}).get("id"),
            library_problem=library_problem(record),
            report=schemas.AssemblyReport(**report) if report else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @app.post(
        "/api/assemblies",
        tags=["assemblies"],
        status_code=202,
        response_model=schemas.AssemblyRun,
        responses={
            400: _problem("A named path was refused, and the reason names which one."),
            503: _problem("Card data could not be retrieved and none is stored."),
        },
    )
    def create_assembly(request: schemas.AssemblyRequest, response: Response):
        """Start a run. Identifies the pack and stops — nothing resolves yet (FR-012a)."""
        service = assemblies()
        try:
            record = service.create(
                FilePath(request.library_root),
                request.hero_folder,
                page_size=(request.page_size or PageSize.LETTER).value
                if hasattr(request.page_size or PageSize.LETTER, "value")
                else str(request.page_size or "LETTER"),
                fit_mode=str(
                    getattr(request.fit_mode, "value", request.fit_mode) or FitMode.CROP.value
                ),
            )
        except SnapshotUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        response.headers["Location"] = f"/api/assemblies/{record.id}"
        return _run_response(record)

    @app.get(
        "/api/assemblies",
        tags=["assemblies"],
        response_model=schemas.AssemblyList,
    )
    def list_assemblies() -> schemas.AssemblyList:
        """FR-026c, SC-006g — the runs, without the user having recorded an identifier.

        Summaries only. The report lives on the detail resource because ten packs' worth of
        resolutions is a list nobody loads, and the three facts that decide what the user
        does next — is it finished, is it waiting on a card, is it waiting for me to confirm
        the pack — are all here.

        No `library_problem` on a summary, deliberately. Answering it means a `stat` per run
        against a mount that may be down, which is exactly the request that hangs; the run's
        own resource says so when the user opens it.
        """
        return schemas.AssemblyList(
            runs=[_summary_response(r) for r in assemblies().runs.list_runs()]
        )

    def _summary_response(record) -> schemas.AssemblySummary:
        identification = record.identification or {}
        return schemas.AssemblySummary(
            id=record.id,
            version=record.version,
            library_root=str(record.library_root),
            hero_folder=record.hero_folder,
            state=record.state.value,
            outcome=record.outcome.value if record.outcome else None,
            pack_code=identification.get("pack_code"),
            pack_name=identification.get("pack_name"),
            unresolved_count=len((record.report or {}).get("unresolved") or []),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @app.get(
        "/api/assemblies/{run_id}",
        tags=["assemblies"],
        response_model=schemas.AssemblyRun,
        responses={404: _problem("No such run.")},
    )
    def get_assembly(run_id: str):
        """Read a run, and reopen it if this is a later visit (FR-026b, SC-006f).

        `resume` rather than `get`: the folder, the pack, the pinned revision, and every
        resolution come straight off disk, but a run the process died inside — mid-render,
        mid-resolve — would otherwise sit in that state forever, because the only request
        that could have moved it on is the one that died.
        """
        service = assemblies()
        _read_run(service, run_id)
        try:
            return _run_response(service.resume(run_id))
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc

    def _read_run(service: AssemblyService, run_id: str):
        try:
            return service.get(run_id)
        except (RunNotFound, UnsafeIdentifier) as exc:
            raise HTTPException(status_code=404, detail=f"No run {run_id!r}") from exc

    @app.get(
        "/api/assemblies/{run_id}/packs",
        tags=["packs"],
        response_model=schemas.PackCandidateList,
        responses={404: _problem("No such run.")},
    )
    def list_assembly_pack_candidates(run_id: str, q: str | None = Query(default=None)):
        """FR-012b. The ranked candidates, or a name search across every pack.

        The same path serves an FR-011 refusal and an unidentifiable folder, so neither
        leaves the user holding a good folder and no way to print it.
        """
        service = assemblies()
        _read_run(service, run_id)
        return schemas.PackCandidateList(
            candidates=[schemas.PackCandidate(**c) for c in service.candidates(run_id, q)]
        )

    @app.post(
        "/api/assemblies/{run_id}/pack",
        tags=["packs"],
        status_code=202,
        response_model=schemas.AssemblyRun,
        responses={
            404: _problem("No such run."),
            409: _problem("The run is not awaiting a pack, or the version is stale."),
        },
    )
    def set_assembly_pack(
        run_id: str,
        decision: schemas.PackDecision,
        if_match: Annotated[str, Header(alias="If-Match")],
    ):
        service = assemblies()
        _read_run(service, run_id)
        try:
            record = service.set_pack(
                run_id, decision.action, decision.pack_code, version=_if_match(if_match)
            )
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(record)

    @app.post(
        "/api/assemblies/{run_id}/cards/{card_code}/image",
        tags=["assemblies"],
        status_code=200,
        response_model=schemas.AssemblyRun,
        responses={
            400: _problem("The file is not a decodable image, or is below print resolution."),
            404: _problem("No such run."),
            409: _problem("That card is not unresolved, or the version is stale."),
        },
    )
    async def upload_assembly_card_image(
        run_id: str,
        card_code: str,
        file: Annotated[UploadFile, File()],
        if_match: Annotated[str, Header(alias="If-Match")],
        side: Annotated[Literal["front", "back"], Form()] = "front",
    ):
        """FR-026e. An upload, not a path — and validated before it is kept (FR-028).

        The order here is the whole of the endpoint's safety, and each step exists because
        the next one is dangerous without it:

        1. **Refuse before reading.** A request naming a card the run did not report as
           unresolved is turned away before 64 MB of it has been streamed anywhere.
        2. **Stream to a temporary file under a byte ceiling, before decode.** The bytes are
           untrusted and Pillow is a decoder; bounding the input is what keeps a hostile
           file from being a memory problem rather than a rejected one (research R9).
        3. **Validate from the temporary directory.** A file that fails is never written
           into the run at all, so a rejection cannot leave the run one record away from
           resolving a card to an image this service has just said it will not print.
        """
        service = assemblies()
        record = _read_run(service, run_id)
        try:
            service.unresolved_face(run_id, card_code, side)
            with tempfile.TemporaryDirectory() as scratch:
                path, digest = await _receive(file, FilePath(scratch), settings.limits)
                _require_printable(path, FitMode(record.fit_mode))
                updated = service.supply_card_image(
                    run_id,
                    card_code,
                    side,
                    source=path,
                    content_digest=digest,
                    original_filename=path.name,
                    version=_if_match(if_match),
                )
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(updated)

    @app.post(
        "/api/assemblies/{run_id}/cards/{card_code}/omission",
        tags=["assemblies"],
        status_code=200,
        response_model=schemas.AssemblyRun,
        responses={
            404: _problem("No such run."),
            409: _problem("The run has not yet reported which cards are unresolved."),
        },
    )
    def omit_assembly_card(
        run_id: str,
        card_code: str,
        omission: schemas.CardOmission,
        if_match: Annotated[str, Header(alias="If-Match")],
    ):
        """FR-030, FR-030a. Printing without a card is the user's call, once informed.

        `acknowledged` is typed as `Literal[True]`, so `false` and absent are both refused
        by the request model rather than by a branch someone could relax. FR-030a's other
        half — that the permission cannot be granted before the run has reported a gap — is
        the service's `unresolved_face`, because it is a fact about the run rather than
        about the payload.
        """
        service = assemblies()
        _read_run(service, run_id)
        try:
            record = service.omit_card(
                run_id, card_code, omission.side, version=_if_match(if_match)
            )
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(record)

    @app.post(
        "/api/assemblies/{run_id}/decklist",
        tags=["assemblies"],
        # 200, not 202: a decision is applied synchronously, and the contract says so.
        status_code=200,
        response_model=schemas.AssemblyRun,
        responses={
            400: _problem("The decision, or the file it named, was refused."),
            404: _problem("No such run."),
            409: _problem("The run has not resolved yet, or the version is stale."),
        },
        # Two body shapes on one path, which a FastAPI signature cannot express: declaring
        # a `File` parameter turns *every* field into a form field, taking the JSON decision
        # away. The body is therefore parsed by hand below and described here, so the
        # contract test still compares a real request body rather than an absent one.
        openapi_extra={"requestBody": _DECKLIST_REQUEST_BODY},
    )
    async def decide_assembly_decklist(
        request: Request,
        run_id: str,
        if_match: Annotated[str, Header(alias="If-Match")],
    ):
        """FR-013d and FR-013c — two ways to answer the same question about one card.

        A JSON `DecklistDecision` answers the candidate the tool found in the folder;
        `confirm` accepts it and is **not** customization, because were acceptance itself
        customization no run would ever be standard and FR-026h's reuse would never fire
        once (FR-013e).

        A multipart upload is the other case: 25 of 60 hero folders hold no deck list scan
        at all, so there is nothing to confirm. The run names that gap and offers the Hall
        of Heroes address — and never fetches it, which is what keeps FR-002's allowlist at
        one host — and the file the user downloaded arrives here (research R9).
        """
        service = assemblies()
        _read_run(service, run_id)
        version = _if_match(if_match)
        media_type = (request.headers.get("content-type") or "").split(";")[0].strip()

        try:
            if media_type == "multipart/form-data":
                form = await request.form()
                upload = form.get("file")
                if not isinstance(upload, StarletteUploadFile):
                    raise AssemblyError("`file` is required for a deck list upload", status=400)
                record = _read_run(service, run_id)
                with tempfile.TemporaryDirectory() as scratch:
                    path, digest = await _receive(upload, FilePath(scratch), settings.limits)
                    # Decode is enforced; the print-resolution floor deliberately is not.
                    # R9: a Hall of Heroes photograph "will very likely fall below the
                    # print-resolution floor and trip FR-035's warning; that is the correct
                    # outcome". Refusing here would leave a user who did exactly what the
                    # tool told them to do unable to print the card, so the softness is
                    # reported on the report instead of refused at the door.
                    _require_decodable(path, FitMode(record.fit_mode))
                    updated = service.supply_decklist(
                        run_id,
                        source=path,
                        content_digest=digest,
                        original_filename=path.name,
                        version=version,
                    )
            else:
                decision = _parse_json_body(await request.body(), schemas.DecklistDecisionRequest)
                updated = service.decide_decklist(
                    run_id, decision.action, decision.ref, version=version
                )
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(updated)

    @app.post(
        "/api/assemblies/{run_id}/confirmation",
        tags=["assemblies"],
        status_code=202,
        response_model=schemas.AssemblyRun,
        responses={
            404: _problem("No such run."),
            409: _problem("The run is not ready, or the version is stale."),
        },
    )
    def confirm_assembly(
        run_id: str,
        confirmation: schemas.AssemblyConfirmation,
        if_match: Annotated[str, Header(alias="If-Match")],
    ):
        """The only place a PDF is produced (FR-026a)."""
        service = assemblies()
        _read_run(service, run_id)
        try:
            record = service.confirm(run_id, confirmation.save_as, version=_if_match(if_match))
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(record)

    @app.delete(
        "/api/assemblies/{run_id}",
        tags=["assemblies"],
        status_code=204,
        response_class=Response,
        responses={
            204: {"description": "Deleted."},
            404: _problem("No such run."),
            409: _problem("The `If-Match` version is stale."),
        },
    )
    def delete_assembly(
        run_id: str, if_match: Annotated[str, Header(alias="If-Match")]
    ) -> Response:
        """Discard a deck attempt. **Not** the act that reclaims disk (FR-026g1).

        Its uploads go, and a *saved* PDF it named goes with it. The pack's **standard** PDF
        does not: every other run of that pack was served the same file, and revoking
        FR-026f for all of them from a button labelled "delete this run" is not something
        the user could have predicted. `DELETE /api/pdfs/{id}` is the act that says what it
        does, and the two stay separate on purpose.
        """
        service = assemblies()
        _read_run(service, run_id)
        try:
            service.delete(run_id, version=_if_match(if_match))
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return Response(status_code=204)

    # -------------------------------------------------------------- stored PDFs (002)

    def _pdfs() -> PdfStore:
        return PdfStore(StateLayout(settings.state_dir))

    def _stored_pdf(stored) -> schemas.StoredPdf:
        return schemas.StoredPdf(
            id=stored.id,
            kind=stored.kind.value,
            name=stored.name,
            byte_size=stored.byte_size,
            created_at=stored.created_at,
            pack_code=stored.pack_code,
            snapshot_revision=stored.snapshot_revision,
        )

    @app.get("/api/pdfs", tags=["pdfs"], response_model=schemas.StoredPdfList)
    def list_stored_pdfs() -> schemas.StoredPdfList:
        """FR-026i's browsable list, and the only place a standard PDF can be deleted from.

        `total_bytes` is not decoration. Retention under FR-026f is unbounded and 001
        measured roughly 202 MB for one deck, so this figure is how the user sees what they
        are keeping before deciding what to give back.
        """
        stored = _pdfs().list_stored()
        return schemas.StoredPdfList(
            pdfs=[_stored_pdf(p) for p in stored],
            total_bytes=sum(p.byte_size for p in stored),
        )

    @app.delete(
        "/api/pdfs/{pdf_id}",
        tags=["pdfs"],
        status_code=204,
        response_class=Response,
        responses={
            204: {"description": "Deleted; the space is reclaimed."},
            404: _problem("No such stored PDF."),
        },
    )
    def delete_stored_pdf(pdf_id: str) -> Response:
        """FR-026g. The next assembly of that pack rebuilds; the scan library is untouched."""
        if not _pdfs().delete(pdf_id):
            raise HTTPException(status_code=404, detail=f"no stored PDF {pdf_id!r}")
        return Response(status_code=204)

    @app.get(
        "/api/pdfs/{pdf_id}/document",
        tags=["pdfs"],
        response_class=Response,
        responses={
            200: _binary("application/pdf", "The PDF."),
            404: _problem("No such stored PDF."),
        },
    )
    def get_stored_pdf_document(pdf_id: str) -> Response:
        stored = _pdfs().find(pdf_id)
        if stored is None:
            raise HTTPException(status_code=404, detail=f"no stored PDF {pdf_id!r}")
        return Response(content=stored.path.read_bytes(), media_type="application/pdf")

    # ------------------------------------------------------------------- packs (002)

    def _snapshots() -> SnapshotStore:
        layout = StateLayout(settings.state_dir)
        return SnapshotStore(layout, MarvelCdbClient(settings.upstream))

    def _snapshot_response(snapshot) -> schemas.PackSnapshot:
        return schemas.PackSnapshot(
            pack_code=snapshot.pack_code,
            revision=snapshot.revision,
            card_count=len(snapshot.cards),
            captured_at=snapshot.captured_at,
            fresh_until=snapshot.fresh_until,
            stale=snapshot.stale,
        )

    @app.get(
        "/api/packs/{pack_code}/snapshot",
        tags=["packs"],
        response_model=schemas.PackSnapshot,
        responses={404: _problem("No snapshot is stored for that pack.")},
    )
    def get_pack_snapshot(pack_code: str) -> schemas.PackSnapshot:
        """What is stored for this pack, and how fresh it is.

        Reports; never captures. A `GET` that fetched when nothing was stored would make the
        read side of this pair issue traffic the user did not ask for, which is what FR-039's
        freshness rules exist to avoid. `POST` is how a snapshot comes into being.
        """
        try:
            stored = _snapshots().stored(pack_code)
        except SnapshotUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail=f"no snapshot is stored for pack {pack_code!r}; assemble a deck from "
                "it, or refresh it, to capture one",
            )
        return _snapshot_response(stored)

    @app.post(
        "/api/packs/{pack_code}/snapshot",
        tags=["packs"],
        response_model=schemas.PackSnapshot,
        responses={
            404: _problem("No such pack."),
            503: _problem("Card data could not be retrieved and none is stored."),
        },
    )
    def refresh_pack_snapshot(pack_code: str) -> schemas.PackSnapshot:
        """FR-044b — the user overriding freshness, because they know something we do not.

        Most packs are years old and never change, so refresh is automatic and governed by
        the cache headers MarvelCDB sends. A recently released pack can pick up corrections
        upstream, and a user who already knows that must not wait out a 600-second expiry.

        **This never alters a run.** A run pins its revision when its pack is confirmed
        (FR-045), and a changed listing is written under a *new* revision rather than over
        the old one — so a deck in flight keeps the composition its resolutions were made
        against. A `304` keeps the stored records and the revision untouched, which is what
        stops a refresh of unchanged data from invalidating a ~202 MB stored PDF.
        """
        store = _snapshots()
        try:
            return _snapshot_response(store.refresh(pack_code))
        except SnapshotUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get(
        "/api/assemblies/{run_id}/document",
        tags=["assemblies"],
        response_class=Response,
        responses={
            200: _binary("application/pdf", "The PDF."),
            404: _problem("No such run."),
            409: _problem("The run has not produced a document. No partial output, ever."),
        },
    )
    def get_assembly_document(run_id: str) -> Response:
        """A finished run depends on nothing outside itself (FR-026f, SC-006h)."""
        service = assemblies()
        _read_run(service, run_id)
        try:
            data = service.document(run_id)
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return Response(content=data, media_type="application/pdf")
