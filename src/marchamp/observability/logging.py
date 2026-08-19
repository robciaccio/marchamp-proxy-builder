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

    `pack_source` and `resolutions` are the two places the tool could have been wrong without
    anyone noticing. A confident *wrong* identification is SC-009's failure mode and it looks
    identical in the output to a right one, so whether the pack was identified or chosen by
    the user is recorded rather than inferred. And every face carries the cascade step that
    found it: an exact positional hit inside the named folder is the only unremarkable
    provenance, and the rest are the tool having gone looking (FR-024, SC-005). A run that
    printed forty cards by name match is a run worth a second look, and only this field says
    so afterwards.
    """

    run_id: str
    pack_code: str
    snapshot_revision: str
    outcome: str
    cards_printed: int
    cards_in_pack: int
    #: `identified` or `user_selected` (FR-012b, SC-009a).
    pack_source: str = ""
    page_count: int | None = None
    reused: bool = False
    customized: bool = False
    #: One `{card_code, side, provenance, source}` per printed face. Codes and enum values
    #: only — a filename here would defeat the whole point of the record (FR-009).
    resolutions: list[dict[str, str]] = field(default_factory=list)
    omitted_card_codes: list[str] = field(default_factory=list)
    manual_card_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def provenance_counts(self) -> dict[str, int]:
        """How many faces each cascade step accounted for.

        Derived rather than stored: the counts are what a person reads, the list is what
        they audit, and storing both is how the two come to disagree.
        """
        counts: dict[str, int] = {}
        for entry in self.resolutions:
            counts[entry["provenance"]] = counts.get(entry["provenance"], 0) + 1
        return counts


def write_record(record: GenerationRecord | AssemblyRecord, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(record.as_dict(), separators=(",", ":"), sort_keys=True) + "\n")
