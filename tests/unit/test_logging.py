"""T012 — generation records (FR-022, FR-022a, FR-022b)."""

from __future__ import annotations

import io
import json

from marchamp.observability.logging import GenerationRecord, write_record


def _record(**over) -> GenerationRecord:
    base = dict(
        request_id="r1",
        deck_id="testman-deck",
        resolved_card_ids=["testman", "sig1"],
        catalog_revision="abc123",
        fit_mode="CROP",
        page_size="LETTER",
        page_count=1,
        duration_ms=42,
        outcome="succeeded",
        failure_kinds=[],
    )
    base.update(over)
    return GenerationRecord(**base)


def test_record_carries_fit_mode_and_page_size():
    # FR-022 names both; without fit mode a record cannot be matched to a printed sheet.
    d = _record().as_dict()
    assert d["fit_mode"] == "CROP"
    assert d["page_size"] == "LETTER"


def test_record_carries_every_field_fr022_requires():
    d = _record().as_dict()
    for field in (
        "deck_id",
        "resolved_card_ids",
        "catalog_revision",
        "fit_mode",
        "page_size",
        "outcome",
    ):
        assert field in d


def test_failure_kinds_is_a_list_not_a_single_value():
    # FR-020a: all failures are reported together.
    assert _record(outcome="failed", failure_kinds=["asset_missing", "asset_too_small"]).as_dict()[
        "failure_kinds"
    ] == ["asset_missing", "asset_too_small"]


def test_record_excludes_filesystem_paths():
    # FR-022b: a record should be safe to paste into a bug report as-is.
    text = json.dumps(_record().as_dict())
    assert "/Users/" not in text
    assert "/home/" not in text


def test_written_as_one_json_line():
    buf = io.StringIO()
    write_record(_record(), stream=buf)
    line = buf.getvalue()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line)["request_id"] == "r1"
