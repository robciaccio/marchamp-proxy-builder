"""HTTP endpoints (contracts/openapi.yaml).

Generation is a POST'd resource with its own identity rather than a side effect of
rendering a page — Principle II's wording, and what keeps the product drivable headlessly.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from marchamp.catalog.loader import CatalogError
from marchamp.catalog.validation import validate
from marchamp.generations.registry import GenerationRegistry
from marchamp.generations.service import Generation, GenerationService
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import face_count
from marchamp.render.images import FitMode


class GenerationRequest(BaseModel):
    deck_id: str = Field(min_length=1)
    page_size: PageSize = PageSize.LETTER
    fit_mode: FitMode = FitMode.CROP


def _generation_json(gen: Generation) -> dict[str, Any]:
    return {
        "id": gen.id,
        "deck_id": gen.deck_id,
        "page_size": gen.page_size.name,
        "fit_mode": gen.fit_mode.value,
        "catalog_revision": gen.catalog_revision,
        "status": gen.status,
        "page_count": gen.page_count,
        "card_count": gen.card_count,
        "substitutions": [
            {
                "card_id": s.card_id,
                "card_name": s.card_name,
                "wanted_printing_id": s.wanted_printing_id,
                "wanted_pack": s.wanted_pack,
                "used_printing_id": s.used_printing_id,
                "used_pack": s.used_pack,
            }
            for s in gen.substitutions
        ],
        "failures": [f.as_dict() for f in gen.failures],
    }


def register_routes(app: FastAPI) -> None:
    settings = app.state.settings
    registry = GenerationRegistry()
    app.state.registry = registry

    def service() -> GenerationService:
        if settings.image_dir is None or settings.catalog_path is None:
            raise HTTPException(
                status_code=503,
                detail=[p.detail for p in settings.problems()],
            )
        return GenerationService(catalog_path=settings.catalog_path, image_dir=settings.image_dir)

    @app.get("/api/health", tags=["catalog"])
    def get_health() -> dict[str, Any]:
        problems = settings.problems()
        revision, valid = None, False
        if not problems:
            try:
                cat = service().load()
                revision = cat.revision
                valid = validate(cat, settings.image_dir).valid
            except CatalogError:
                valid = False
        return {
            "status": "ok",
            "catalog_valid": valid,
            "catalog_revision": revision,
            "image_directory_configured": settings.image_dir is not None,
            "problems": [{"kind": p.kind, "detail": p.detail} for p in problems],
        }

    @app.get("/api/catalog/validation", tags=["catalog"])
    def get_catalog_validation() -> dict[str, Any]:
        # `valid: false` is a normal 200 — the request succeeded, the catalog did not.
        try:
            cat = service().load()
        except CatalogError as exc:
            return {
                "valid": False,
                "catalog_revision": None,
                "errors": [{"kind": "schema_invalid", "detail": str(exc)}],
                "warnings": [],
            }
        report = validate(cat, settings.image_dir)
        as_json = lambda i: {  # noqa: E731
            "kind": i.kind,
            "detail": (f"{i.card_name}: {i.detail}" if i.card_name else i.detail),
            "card_id": i.card_id,
            "deck_id": i.deck_id,
        }
        return {
            "valid": report.valid,
            "catalog_revision": cat.revision,
            "errors": [as_json(e) for e in report.errors],
            "warnings": [as_json(w) for w in report.warnings],
        }

    @app.get("/api/decks", tags=["decks"])
    def list_decks() -> dict[str, Any]:
        svc = service()
        try:
            cat = svc.load()
        except CatalogError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "catalog_revision": cat.revision,
            "decks": [
                {"id": d.id, "name": d.name, "card_count": face_count(cat, d.id)} for d in cat.decks
            ],
        }

    @app.get("/api/decks/{deck_id}", tags=["decks"])
    def get_deck(deck_id: str) -> dict[str, Any]:
        svc = service()
        cat = svc.load()
        deck = cat.deck(deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail=f"No deck {deck_id!r}")
        entries = []
        for e in deck.entries:
            card = cat.card(e.card_id)
            entries.append(
                {
                    "card_id": e.card_id,
                    "name": card.name if card else e.card_id,
                    "quantity": e.quantity,
                    "double_sided": bool(card and card.double_sided),
                    "preferred_printing_id": e.preferred_printing_id,
                    "preferred_printing_available": bool(
                        card
                        and (p := card.printing(e.preferred_printing_id))
                        and (settings.image_dir / p.image).is_file()
                    ),
                }
            )
        return {
            "id": deck.id,
            "name": deck.name,
            "card_count": face_count(cat, deck.id),
            "hero_card_id": deck.hero_card_id,
            "entries": entries,
        }

    @app.post("/api/generations", status_code=202, tags=["generations"])
    def create_generation(body: GenerationRequest, response: Response) -> dict[str, Any]:
        svc = service()
        try:
            cat = svc.load()
        except CatalogError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if cat.deck(body.deck_id) is None:
            raise HTTPException(status_code=404, detail=f"No deck {body.deck_id!r}")

        gen = svc.generate(body.deck_id, page_size=body.page_size, fit_mode=body.fit_mode)
        registry.put(gen)
        response.headers["Location"] = f"/api/generations/{gen.id}"
        return _generation_json(gen)

    @app.get("/api/generations/{generation_id}", tags=["generations"])
    def get_generation(generation_id: str) -> dict[str, Any]:
        gen = registry.get(generation_id)
        if gen is None:
            raise HTTPException(status_code=404, detail="No such generation")
        return _generation_json(gen)

    @app.get("/api/generations/{generation_id}/document", tags=["generations"])
    def get_generation_document(generation_id: str) -> Response:
        gen = registry.get(generation_id)
        if gen is None:
            raise HTTPException(status_code=404, detail="No such generation")
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

    @app.get("/api/calibration", tags=["calibration"])
    def get_calibration(page_size: PageSize = PageSize.LETTER) -> Response:
        from marchamp.render.calibration import calibration_pdf

        return Response(content=calibration_pdf(page_size), media_type="application/pdf")
