"""HTTP endpoints (contracts/openapi.yaml).

Generation is a POST'd resource with its own identity rather than a side effect of
rendering a page — Principle II's wording, and what keeps the product drivable headlessly.

Every route declares a response model. That is not decoration: FastAPI generates component
schemas from these types, and a route returning a bare dict generates none, which would
leave the contract naming types that describe nothing.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path as FilePath
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Path, Query, Response

from marchamp.api import schemas
from marchamp.assembly.service import AssemblyError, AssemblyService
from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.catalog.loader import CatalogError
from marchamp.catalog.validation import validate
from marchamp.generations.registry import GenerationRegistry
from marchamp.generations.service import Generation as GenerationState
from marchamp.generations.service import GenerationService
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import face_count
from marchamp.render import preview
from marchamp.render.images import FitMode
from marchamp.store.layout import StateLayout, UnsafeIdentifier
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
            unresolved=[schemas.UnresolvedCard(**u) for u in unresolved],
            reused=record.reused,
            pdf_id=(record.pdf or {}).get("id"),
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
        "/api/assemblies/{run_id}",
        tags=["assemblies"],
        response_model=schemas.AssemblyRun,
        responses={404: _problem("No such run.")},
    )
    def get_assembly(run_id: str):
        return _run_response(_read_run(assemblies(), run_id))

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
    )
    def decide_assembly_decklist(
        run_id: str,
        decision: schemas.DecklistDecisionRequest,
        if_match: Annotated[str, Header(alias="If-Match")],
    ):
        """FR-013d. `confirm` accepts the tool's candidate and is **not** customization.

        Were acceptance itself customization, no run would ever be standard and FR-026h's
        reuse would never fire once (FR-013e).
        """
        service = assemblies()
        _read_run(service, run_id)
        try:
            record = service.decide_decklist(
                run_id, decision.action, decision.ref, version=_if_match(if_match)
            )
        except AssemblyError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return _run_response(record)

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
