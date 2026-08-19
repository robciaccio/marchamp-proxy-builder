"""T012, T114 — the two log records (FR-022, FR-022a, FR-022b, FR-009, FR-030b).

Both are meant to be safe to paste into a bug report without redaction, which is a
property of the *fields they have* rather than of the values a particular run produced. The
assembly record carries the harder version of the rule: a run may hold a file the user
supplied from anywhere on their machine, and FR-009 forbids a path from outside the named
library reaching the log any more than the report.
"""

from __future__ import annotations

import io
import json

from marchamp.observability.logging import AssemblyRecord, GenerationRecord, write_record


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


# ------------------------------- T114: the assembly run record (FR-009, FR-030b, Principle V)


def _assembly(**over) -> AssemblyRecord:
    base = dict(
        run_id="01J8ZK",
        pack_code="cap",
        pack_source="identified",
        snapshot_revision="0123456789abcdef",
        outcome="succeeded",
        cards_printed=34,
        cards_in_pack=34,
        page_count=6,
        resolutions=[
            {
                "card_code": "03001a",
                "side": "front",
                "provenance": "folder_position",
                "source": "library",
            },
            {"card_code": "03016", "side": "front", "provenance": "reprint", "source": "library"},
            {"card_code": "03031", "side": "front", "provenance": "name", "source": "library"},
            {"card_code": "03032", "side": "front", "provenance": "manual", "source": "upload"},
        ],
        manual_card_codes=["03032"],
    )
    base.update(over)
    return AssemblyRecord(**base)


def test_the_record_says_whether_the_pack_was_identified_or_chosen():
    """SC-009a, FR-012b — a confident wrong identification looks exactly like a right one.

    The output cannot distinguish them and neither can the user at print time. This field is
    the only place the difference survives, which is why it is recorded rather than inferred
    from whether a `select` call happened to be made.
    """
    assert _assembly().as_dict()["pack_source"] == "identified"
    assert _assembly(pack_source="user_selected").as_dict()["pack_source"] == "user_selected"


def test_every_printed_face_carries_the_cascade_step_that_found_it():
    """FR-024, SC-005 — provenance is the audit trail for a substitution.

    An exact positional hit inside the named folder needs no explanation; everything else is
    the tool having gone looking, and a run that printed most of a pack by name match is one
    a person would want to check.
    """
    record = _assembly()
    for entry in record.as_dict()["resolutions"]:
        assert set(entry) == {"card_code", "side", "provenance", "source"}
    assert record.provenance_counts == {
        "folder_position": 1,
        "reprint": 1,
        "name": 1,
        "manual": 1,
    }


def test_an_omission_is_recorded_separately_from_a_resolution():
    """FR-030b — a card printed without is not a card printed.

    Listing it in both places would leave the record contradicting itself about the same
    card, which is precisely the confusion the field exists to prevent.
    """
    record = _assembly(omitted_card_codes=["03028"])
    assert "03028" not in {r["card_code"] for r in record.resolutions}
    assert record.as_dict()["omitted_card_codes"] == ["03028"]


def test_the_assembly_record_carries_no_filesystem_path():
    """FR-009, FR-022b, Principle V — the record must be safe to paste unredacted.

    Two different leaks are possible and both are checked. A resolution's `ref` is a path
    *inside* the named library, which names the user's folder layout; an upload's
    `original_filename` came from wherever on their machine they picked the file, which is
    the one FR-009 names explicitly. Neither has a field to live in, and this asserts that
    rather than trusting it.
    """
    text = json.dumps(
        _assembly(
            resolutions=[
                {
                    "card_code": "03016",
                    "side": "front",
                    "provenance": "reprint",
                    "source": "library",
                }
            ]
        ).as_dict()
    )
    for marker in ("/Users/", "/home/", "C:\\", ".tiff", ".tif", "library_root", "ref"):
        assert marker not in text, f"the assembly record leaked {marker!r}"


def test_the_assembly_record_is_written_as_one_json_line():
    buf = io.StringIO()
    write_record(_assembly(), stream=buf)
    line = buf.getvalue()
    assert line.count("\n") == 1
    assert json.loads(line)["run_id"] == "01J8ZK"
