"""Failure taxonomy (FR-019b1, FR-020, FR-021).

Errors are values here rather than exceptions-at-the-boundary, because the spec requires
them to be enumerable, classifiable as retryable or not, and reportable in batches.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    CATALOG_INVALID = "catalog_invalid"
    ASSET_MISSING = "asset_missing"
    ASSET_UNREADABLE = "asset_unreadable"
    ASSET_TOO_SMALL = "asset_too_small"
    LIMIT_EXCEEDED = "limit_exceeded"
    INTERNAL = "internal"


# FR-021: exactly one condition can clear on its own — a lock, a permission problem, or a
# cloud-sync placeholder that has not materialised yet.
_RETRYABLE = frozenset({FailureKind.ASSET_UNREADABLE})

_GENERIC_INTERNAL = "Something went wrong while generating. See the application log."


@dataclass(frozen=True)
class GenerationFailure:
    kind: FailureKind
    detail: str
    card_id: str | None = None
    card_name: str | None = None

    def __post_init__(self) -> None:
        if not self.detail:
            raise ValueError("detail is required; a failure with no explanation is not actionable")

    @property
    def retryable(self) -> bool:
        return self.kind in _RETRYABLE

    @property
    def message(self) -> str:
        """User-facing text. Names the card when there is one, never leaks internals."""
        if self.kind is FailureKind.INTERNAL:
            # Constitution's fail-closed gate: no stack traces, queries, or hostnames.
            return _GENERIC_INTERNAL
        if self.card_name:
            return f"{self.card_name}: {self.detail}"
        return self.detail

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "retryable": self.retryable,
            "detail": self.message,
            "card_id": self.card_id,
            "card_name": self.card_name,
        }
