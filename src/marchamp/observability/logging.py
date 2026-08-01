"""Structured generation records (FR-022, FR-022a, FR-022b)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import TextIO


@dataclass(frozen=True)
class GenerationRecord:
    """One line per generation.

    Deliberately carries no filesystem paths: FR-022b expects a record to be safe to paste
    into a bug report without redaction. Cards are named by identifier, not by file.
    """

    request_id: str
    deck_id: str
    resolved_card_ids: list[str]
    catalog_revision: str
    fit_mode: str
    page_size: str
    outcome: str
    page_count: int | None = None
    duration_ms: int | None = None
    failure_kinds: list[str] = field(default_factory=list)
    substitution_count: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def write_record(record: GenerationRecord, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(record.as_dict(), separators=(",", ":"), sort_keys=True) + "\n")
