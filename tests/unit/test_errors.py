"""T010 — failure taxonomy (FR-019b1, FR-021)."""

from __future__ import annotations

import pytest

from marchamp.api.errors import FailureKind, GenerationFailure


def test_exactly_the_six_specified_kinds_exist():
    assert {k.value for k in FailureKind} == {
        "catalog_invalid",
        "asset_missing",
        "asset_unreadable",
        "asset_too_small",
        "limit_exceeded",
        "internal",
    }


def test_only_unreadable_is_retryable():
    # FR-021: a lock, a permission problem, or a sync placeholder may clear on its own.
    # Nothing else does.
    retryable = {k for k in FailureKind if GenerationFailure(kind=k, detail="x").retryable}
    assert retryable == {FailureKind.ASSET_UNREADABLE}


def test_card_scoped_failures_carry_the_card_name():
    f = GenerationFailure(
        kind=FailureKind.ASSET_MISSING, detail="no file", card_id="c1", card_name="Quinjet"
    )
    assert "Quinjet" in f.message


def test_message_never_leaks_a_stack_trace():
    f = GenerationFailure(kind=FailureKind.INTERNAL, detail="Traceback (most recent call last):")
    assert "Traceback" not in f.message


def test_detail_is_required():
    with pytest.raises(ValueError):
        GenerationFailure(kind=FailureKind.INTERNAL, detail="")
