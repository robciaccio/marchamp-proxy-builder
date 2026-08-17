"""FastAPI application (FR-0A1, FR-0A2, FR-0A3).

Local-only. Binds loopback, has no authentication because there is no remote access to
authenticate, and makes no outbound call — card images come from a local directory.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from marchamp.api.schemas import Problem
from marchamp.config import Settings, settings_from_env
from marchamp.store.layout import StateLayout
from marchamp.store.sweep import sweep_state

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

_TITLE = "Marchamp Proxy Builder — Local API"
_DESCRIPTION = (
    "Local-only service. Binds to 127.0.0.1 and is never publicly reachable. "
    "No authentication exists, because there is no remote access to authenticate. "
    "Makes no outbound network calls."
)


def _problem_response(status: int, detail: str) -> JSONResponse:
    """RFC 9457. Every error the API returns has the same shape, so a client needs one
    branch to handle failure rather than one per endpoint."""
    title = HTTPStatus(status).phrase
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content=Problem(type="about:blank", title=title, status=status, detail=detail).model_dump(),
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ADR 0001 § Consequences: plain files buy simplicity at the cost of having no
    # transaction across a run record and its uploaded blobs, and the sweep is what pays it.
    # It runs *here*, before the first request, because that is what makes deleting safe —
    # with nothing in flight, an upload its run does not reference is unreachable rather
    # than merely not-yet-recorded. Scheduling it while serving would delete a file in the
    # window between an upload landing and its resolution being written.
    settings: Settings = app.state.settings
    layout = StateLayout(settings.state_dir)
    layout.ensure()
    report = sweep_state(layout)
    if report.removed or report.skipped_runs:
        logging.getLogger("marchamp.store").info(
            "startup sweep reclaimed %d file(s), %d bytes; skipped %d unreadable run(s)",
            len(report.removed),
            report.reclaimed_bytes,
            len(report.skipped_runs),
        )
    app.state.state_layout = layout

    yield
    # An in-flight generation is bounded by FR-0A4's 120-second ceiling and holds nothing
    # worth waiting for — the document lives only in memory (FR-021b).
    workers = getattr(app.state, "generation_workers", None)
    if workers is not None:  # pragma: no cover - process teardown
        workers.shutdown(wait=False, cancel_futures=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or settings_from_env()
    app = FastAPI(
        title=_TITLE,
        version="0.1.0",
        description=_DESCRIPTION,
        servers=[{"url": f"http://127.0.0.1:{settings.port}", "description": "Loopback only"}],
        lifespan=_lifespan,
    )
    app.state.settings = settings

    @app.exception_handler(HTTPException)
    def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _problem_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Names the offending field. Constitution's fail-closed clause forbids leaking
        # internals, and a request field the caller sent is not an internal.
        where = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()
        )
        return _problem_response(422, where or "Request could not be validated")

    from marchamp.api.routes import register_routes

    register_routes(app)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=_TITLE,
                version="0.1.0",
                description=_DESCRIPTION,
                routes=app.routes,
                servers=app.servers,
                tags=[{"name": t} for t in ("catalog", "decks", "generations", "calibration")],
            )
            # Error responses reference Problem by `$ref` rather than declaring it as a
            # response model, because FastAPI would then also advertise `application/json`
            # for them. Registering the component from the model keeps it generated rather
            # than hand-written.
            schema.setdefault("components", {}).setdefault("schemas", {})["Problem"] = (
                Problem.model_json_schema()
            )
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi

    # Mounted last so it cannot shadow /api. `html=True` serves index.html at "/".
    if WEB_ROOT.is_dir():
        app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="web")

    return app


def run() -> None:  # pragma: no cover - entry point
    import uvicorn

    settings = settings_from_env()
    # Never 0.0.0.0. Settings refuses a non-loopback host, so this cannot be widened by
    # configuration alone.
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
