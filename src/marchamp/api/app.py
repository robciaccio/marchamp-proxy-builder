"""FastAPI application (FR-0A1, FR-0A2, FR-0A3).

Local-only. Binds loopback, has no authentication because there is no remote access to
authenticate, and makes no outbound call — card images come from a local directory.
"""

from __future__ import annotations

from fastapi import FastAPI

from marchamp.config import Settings, settings_from_env


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or settings_from_env()
    app = FastAPI(
        title="Marchamp Proxy Builder — Local API",
        version="0.1.0",
        description=(
            "Local-only service. Binds to 127.0.0.1 and is never publicly reachable. "
            "No authentication exists, because there is no remote access to authenticate. "
            "Makes no outbound network calls."
        ),
        servers=[{"url": f"http://127.0.0.1:{settings.port}", "description": "Loopback only"}],
    )
    app.state.settings = settings

    from marchamp.api.routes import register_routes

    register_routes(app)
    return app


def run() -> None:  # pragma: no cover - entry point
    import uvicorn

    settings = settings_from_env()
    # Never 0.0.0.0. Settings refuses a non-loopback host, so this cannot be widened by
    # configuration alone.
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
