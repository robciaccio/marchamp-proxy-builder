"""Catalog loading and revision (FR-005c1, FR-005c2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from marchamp.catalog.models import Catalog

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1"})


class CatalogError(Exception):
    """The catalog could not be understood at all."""


def compute_revision(payload: dict) -> str:
    """Content-derived revision (FR-005c2).

    Canonical JSON with sorted keys, so the revision depends on content and not on key
    order, whitespace, file timestamps, or where the catalog is stored.
    """
    body = {k: v for k, v in payload.items() if k != "revision"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def load_catalog(payload: dict) -> Catalog:
    version = payload.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        # Refused outright rather than parsed on a best-effort basis (FR-005c1).
        raise CatalogError(
            f"Unsupported catalog schema_version {version!r}. "
            f"This build understands: {', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))}."
        )
    try:
        return Catalog(**{**payload, "revision": compute_revision(payload)})
    except ValidationError as exc:
        raise CatalogError(f"Catalog structure is invalid: {exc.error_count()} problem(s)") from exc


def load_catalog_file(path: Path) -> Catalog:
    try:
        payload = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise CatalogError(
            f"Catalog is not valid JSON: line {exc.lineno}, column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise CatalogError(f"Catalog could not be read: {exc.strerror or exc}") from exc
    return load_catalog(payload)
