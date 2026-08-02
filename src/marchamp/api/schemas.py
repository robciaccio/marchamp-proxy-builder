"""Request and response models (contracts/openapi.yaml).

Constitution Principle II requires the OpenAPI document be generated from or verified
against the running service. Routes that return `dict[str, Any]` generate no component
schemas at all, so the contract's named types — `Generation`, `DeckDetail`, `Substitution`
— existed only in the YAML file and described nothing. These models are what make the
generated document real; `tests/contract/test_openapi_matches.py` is what keeps them true.

Optionality is deliberate throughout: a field with a default is absent from OpenAPI's
`required` list, so the defaults here are the contract's required sets expressed in Python.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from marchamp.layout.geometry import PageSize
from marchamp.render.images import FitMode

# ------------------------------------------------------------------------------ errors


class Problem(BaseModel):
    """RFC 9457 problem detail. Served as `application/problem+json`."""

    type: str
    title: str
    status: int
    detail: str | None = None


# ------------------------------------------------------------------------------ health


class ConfigProblem(BaseModel):
    kind: Literal["image_dir_unset", "image_dir_missing", "catalog_unset", "catalog_missing"]
    detail: str


class Health(BaseModel):
    status: Literal["ok"]
    catalog_valid: bool
    image_directory_configured: bool
    problems: list[ConfigProblem]
    catalog_revision: str | None = None


# -------------------------------------------------------------------------- validation


class ValidationIssue(BaseModel):
    kind: Literal[
        "schema_invalid",
        "duplicate_card_id",
        "duplicate_printing_id",
        "unknown_card_reference",
        "printing_card_mismatch",
        "missing_image_file",
        "missing_back_image",
        "unexpected_back_image",
        "invalid_quantity",
        "shared_image_file",
        "unsafe_image_path",
    ]
    detail: str
    card_id: str | None = None
    deck_id: str | None = None


class ValidationReport(BaseModel):
    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    catalog_revision: str | None = None


# ------------------------------------------------------------------------------- decks


class DeckSummary(BaseModel):
    id: str
    name: str
    card_count: int = Field(
        description="Total faces printed, counting quantities and a double-sided card as two."
    )


class DeckEntry(BaseModel):
    card_id: str
    name: str
    quantity: int = Field(ge=1)
    double_sided: bool
    preferred_printing_id: str
    preferred_printing_available: bool


class DeckDetail(DeckSummary):
    hero_card_id: str
    entries: list[DeckEntry]


class DeckList(BaseModel):
    catalog_revision: str
    decks: list[DeckSummary]


# ------------------------------------------------------------------------- generations


class GenerationRequest(BaseModel):
    deck_id: str = Field(min_length=1)
    page_size: PageSize = PageSize.LETTER
    fit_mode: FitMode = FitMode.CROP


class Substitution(BaseModel):
    card_id: str
    card_name: str
    wanted_printing_id: str
    used_printing_id: str
    wanted_pack: str | None = None
    used_pack: str | None = None


class Failure(BaseModel):
    kind: Literal[
        "catalog_invalid",
        "asset_missing",
        "asset_unreadable",
        "asset_too_small",
        "limit_exceeded",
        "internal",
    ]
    retryable: bool
    detail: str
    card_id: str | None = None
    card_name: str | None = None


class Generation(BaseModel):
    id: str
    deck_id: str
    page_size: PageSize
    fit_mode: FitMode
    catalog_revision: str
    status: Literal["pending", "running", "succeeded", "failed"]
    progress: float | None = Field(default=None, ge=0, le=1)
    pages_ready: int | None = None
    page_count: int | None = None
    card_count: int | None = None
    substitutions: list[Substitution] = Field(default_factory=list)
    failures: list[Failure] = Field(default_factory=list)
