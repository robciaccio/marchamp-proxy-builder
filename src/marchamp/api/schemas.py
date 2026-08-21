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

from datetime import datetime
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


# ------------------------------------------------------------------------- assemblies
#
# Feature 002. The contract for these lives in
# `specs/002-starter-deck-assembly/contracts/openapi.yaml`, and the same rule applies as
# above: a field with a default is absent from OpenAPI's `required` list, so the defaults
# here are that document's required sets expressed in Python.

AssemblyState = Literal[
    "identifying",
    "unidentified",
    "awaiting_pack",
    "resolving",
    "awaiting_cards",
    "ready",
    "rendering",
    "complete",
    "failed",
]

#: FR-036. Null until the run is terminal, so "still going" is distinguishable from
#: "finished badly" — which is why every field carrying this is optional.
AssemblyOutcome = Literal["clean", "warnings", "refused"]

#: FR-015's four groups. Distinct in the **report only**: FR-015d packs them into as few
#: pages as possible with no page break between them.
CardGroup = Literal["player", "identity", "nemesis", "decklist"]


class AssemblyRequest(BaseModel):
    library_root: str
    hero_folder: str
    page_size: PageSize = PageSize.LETTER
    fit_mode: FitMode = FitMode.CROP


class PackIdentification(BaseModel):
    source: Literal["identified", "user_selected"]
    evidence: list[str]
    confirmed: bool
    pack_code: str | None = None
    pack_name: str | None = None
    confidence: float | None = None


class PackCandidate(BaseModel):
    pack_code: str
    pack_name: str
    evidence: list[str]
    confidence: float | None = None


class PackCandidateList(BaseModel):
    candidates: list[PackCandidate]


class PackDecision(BaseModel):
    action: Literal["confirm", "select"]
    #: Required for `select`; must be absent for `confirm`. Enforced in the service rather
    #: than by two request models, so the refusal names the reason rather than the shape.
    pack_code: str | None = None


class DecklistDecisionRequest(BaseModel):
    action: Literal["confirm", "select", "skip"]
    #: Required for `select`: relative to `library_root`, never absolute (FR-007, FR-009).
    #: Absent rather than null when unused — `confirm` and `skip` name no file, and the
    #: service refuses a `select` that arrives without one.
    ref: str = ""


class CardOmission(BaseModel):
    """FR-030a — printing without a card requires an explicit act naming *this* card.

    `acknowledged` is `Literal[True]` rather than `bool`, so `false` and absent are both
    refused by the model. The requirement is that this "MUST NOT be reachable by dismissing
    a prompt, ignoring a warning, or staying silent", and a plain boolean with a default
    would make silence mean yes — which is the failure, spelled out.
    """

    acknowledged: Literal[True]
    #: Which face, for a double-sided card. Omitting the back of a card whose front
    #: resolved is a real case: the run prints neither, and says so.
    side: Literal["front", "back"] = "front"


class DecklistCandidate(BaseModel):
    ref: str
    #: Present when two candidates with **different stems** matched — a conflict the user
    #: resolves by picking, never by arbitrary choice (FR-033). Empty rather than null when
    #: there is no conflict: a caller reads "are there alternatives" off the length either
    #: way, and a nullable array is two absent-ish states for one meaning.
    alternatives: list[str] = Field(default_factory=list)


class UnresolvedCard(BaseModel):
    card_code: str
    card_name: str
    side: Literal["front", "back"]
    group: CardGroup
    #: Where the tool looked, in order. SC-008 requires the user to tell which card is
    #: missing and where it was sought **from the report alone**.
    searched: list[str]


class ResolutionEntry(BaseModel):
    card_code: str
    card_name: str
    side: Literal["front", "back"]
    group: CardGroup
    provenance: Literal[
        "decklist_name",
        "folder_position",
        "library_position",
        "folder_name",
        "reprint",
        "name",
        "manual",
        "omitted",
    ]
    source: Literal["library", "upload"]
    #: Relative to the library root, or an uploaded file's **own name**. Never an absolute
    #: path from outside the named folder (FR-009, FR-027).
    file: str
    note: str | None = None


class ReportedFile(BaseModel):
    file: str
    reason: str


class AssemblyReport(BaseModel):
    pack_source: Literal["identified", "user_selected"]
    cards_printed: int
    #: FR-018's comparison, in **cards**. No total is expected and none is warned on.
    cards_in_pack: int
    faces_printed: int
    decklist_printed: bool
    resolutions: list[ResolutionEntry]
    omitted: list[ResolutionEntry]
    unused_files: list[ReportedFile]
    uninterpretable_files: list[ReportedFile]
    conflicts: list[ReportedFile]
    low_resolution: list[ReportedFile]
    pack_code: str | None = None
    pack_name: str | None = None
    snapshot_revision: str | None = None
    snapshot_stale: bool = False
    page_count: int | None = None
    decklist_source_url: str | None = None


class AssemblyRun(BaseModel):
    id: str
    version: int
    library_root: str
    hero_folder: str
    state: AssemblyState
    unresolved: list[UnresolvedCard]
    #: Declared as datetimes rather than strings so the generated document carries
    #: `format: date-time`, which is what the contract promises. The record stores ISO
    #: strings; Pydantic parses and re-serialises them to the same text.
    created_at: datetime
    updated_at: datetime
    outcome: AssemblyOutcome | None = None
    page_size: PageSize = PageSize.LETTER
    fit_mode: FitMode = FitMode.CROP
    identification: PackIdentification | None = None
    snapshot_revision: str | None = None
    snapshot_stale: bool = False
    decklist_candidate: DecklistCandidate | None = None
    #: Whether the user has changed anything about this run (FR-026i). A client needs this
    #: *before* it confirms: `save_as` is required for a customized run and refused for an
    #: uncustomized one, so without it the only way to find out which is to be told 400.
    customized: bool = False
    reused: bool | None = None
    pdf_id: str | None = None
    report: AssemblyReport | None = None
    #: Why the run cannot read its library right now, or null (FR-026f). Never persisted:
    #: an unmounted drive is a fact about this visit, not about the run.
    library_problem: str | None = None


class AssemblySummary(BaseModel):
    id: str
    version: int
    library_root: str
    hero_folder: str
    state: AssemblyState
    unresolved_count: int
    created_at: datetime
    updated_at: datetime
    pack_code: str | None = None
    pack_name: str | None = None
    outcome: AssemblyOutcome | None = None


class AssemblyList(BaseModel):
    runs: list[AssemblySummary]


class StoredPdf(BaseModel):
    id: str
    #: A `standard` PDF belongs to the **pack** and is shared by every clean run of it; a
    #: `saved` one belongs to the run that named it (FR-026g1, FR-026h, FR-026i).
    kind: Literal["standard", "saved"]
    name: str
    byte_size: int
    created_at: datetime
    pack_code: str | None = None
    snapshot_revision: str | None = None


class StoredPdfList(BaseModel):
    pdfs: list[StoredPdf]
    #: What the user is keeping, so FR-026g's reclamation is an informed choice rather than
    #: a guess about which of two identical-looking rows is the 202 MB one.
    total_bytes: int


class PackSnapshot(BaseModel):
    pack_code: str
    #: A content hash of the *reduced* records, not upstream's `Last-Modified` — so an edit
    #: to card text this feature does not retain cannot throw a 202 MB stored PDF away.
    revision: str
    card_count: int
    captured_at: datetime
    #: Within it no request is issued at all, which is what SC-006d requires literally.
    fresh_until: datetime
    stale: bool


class AssemblyConfirmation(BaseModel):
    #: Required when the run was customized, forbidden when it was not (FR-026h, FR-026i).
    save_as: str | None = None
