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


@dataclass(frozen=True)
class AssemblyRecord:
    """One line per assembly run that produced a PDF (FR-030b, FR-022b).

    The same rule as `GenerationRecord`, and it bites harder here: **no filesystem paths**.
    A run may hold a file the user supplied from anywhere on their machine (FR-027), and
    FR-009 forbids a path from outside the named library reaching the log any more than the
    report. Cards are identified by MarvelCDB code, which is stable, meaningless outside the
    game, and safe to paste into a bug report — the *names* live in the report, where the
    person reading them is the person who owns the library.

    `omitted_card_codes` is what FR-030b requires of this record specifically: printing a
    pack with a card left out must be legible as such afterwards, and the report alone is
    not enough because a report can be regenerated while a log line is what happened.
    """

    run_id: str
    pack_code: str
    snapshot_revision: str
    outcome: str
    cards_printed: int
    cards_in_pack: int
    page_count: int | None = None
    reused: bool = False
    customized: bool = False
    omitted_card_codes: list[str] = field(default_factory=list)
    manual_card_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def write_record(record: GenerationRecord | AssemblyRecord, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(record.as_dict(), separators=(",", ":"), sort_keys=True) + "\n")
