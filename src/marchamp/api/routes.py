"""HTTP endpoints (contracts/openapi.yaml).

Generation is a POST'd resource with its own identity rather than a side effect of
rendering a page — Principle II's wording, and what keeps the product drivable headlessly.

Every route declares a response model. That is not decoration: FastAPI generates component
schemas from these types, and a route returning a bare dict generates none, which would
leave the contract naming types that describe nothing.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Query, Response

from marchamp.api import schemas
from marchamp.catalog.loader import CatalogError
from marchamp.catalog.validation import validate
from marchamp.generations.registry import GenerationRegistry
from marchamp.generations.service import Generation as GenerationState
from marchamp.generations.service import GenerationService
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import face_count
from marchamp.render import preview

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

    def service() -> GenerationService:
        if settings.image_dir is None or settings.catalog_path is None:
            raise HTTPException(
                status_code=503,
                detail="; ".join(p.detail for p in settings.problems()),
            )
        return GenerationService(
            catalog_path=settings.catalog_path,
            image_dir=settings.image_dir,
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
                valid = validate(cat, settings.image_dir).valid
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
        report = validate(cat, settings.image_dir)

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
                        and (settings.image_dir / p.image).is_file()
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
