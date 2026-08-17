"""T028 — the reduced upstream record, validated on capture and on read (FR-047, FR-038a).

Two independent requirements meet in this module.

**FR-038a: only the listed fields may be retained.** The reduction happens at ingest, not at
commit, so card text never enters the process and therefore cannot reach a fixture, a log,
or a run record by accident. The nested `linked_card` is where this is easy to get wrong —
upstream sends the linked card's entire record, rules text and all, and the only part face
expansion needs is its code.

**FR-047 and the constitution's "content validated on read": a snapshot is checked twice.**
Once when captured, and again when read back, because it is a JSON file on disk that the
user can edit and that a partial write can truncate. Validating only on capture would make
the second read trust a file nothing has looked at since.

The specific checks are not generic schema hygiene. Each catches a way a snapshot can be
wrong that would otherwise surface as a bad PDF: a pack with no `hero` record cannot satisfy
FR-015a and is a truncated response rather than a printable pack; a pack with no `nemesis`
record cannot satisfy FR-015b; `quantity < 1` would print zero copies of a card the pack
ships. A dangling reprint link is the one exception and is a **warning**, because it only
matters if that card also fails to resolve locally, and then FR-025 names it anyway.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marchamp.upstream.models import (
    PackCard,
    PackIndexEntry,
    SnapshotInvalid,
    parse_pack_index,
    parse_snapshot_cards,
    reduce_card,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "snapshots"


def fixture(pack: str) -> list[dict]:
    return json.loads((FIXTURES / f"{pack}.json").read_text())


# ------------------------------------------------------------------ reduction (FR-038a)


def test_reduction_keeps_only_the_documented_fields():
    raw = {
        "code": "03001a",
        "pack_code": "cap",
        "position": 1,
        "name": "Captain America",
        "type_code": "hero",
        "card_set_type_name_code": "hero",
        "quantity": 1,
        "double_sided": False,
        "text": "<p>Living Legend — reduce the cost...</p>",
        "real_text": "Living Legend — reduce the cost...",
        "flavor": "A man out of time.",
        "traits": "Avenger. Soldier.",
        "imagesrc": "/bundles/cards/03001a.png",
        "illustrator": "Someone",
        "linked_card": {"code": "03001b", "name": "Steve Rogers", "text": "<p>Setup...</p>"},
    }
    card = reduce_card(raw)
    assert card.code == "03001a"
    assert card.linked_codes == ["03001b"]
    for banned in ("text", "real_text", "flavor", "traits", "imagesrc", "illustrator"):
        assert banned not in vars(card)


def test_the_linked_card_is_flattened_to_a_code_and_nothing_else():
    """Upstream sends the linked card's whole record, rules text included.

    Retaining the object and reading `.code` off it later is the mistake this asserts
    against: the text would then be in memory, in the snapshot, and in the fixture.
    """
    card = reduce_card(
        {
            "code": "03001a",
            "pack_code": "cap",
            "position": 1,
            "name": "Captain America",
            "type_code": "hero",
            "quantity": 1,
            "linked_card": {
                "code": "03001b",
                "text": "<p>rules</p>",
                "linked_card": {"code": "03001c", "flavor": "more prose"},
            },
        }
    )
    assert card.linked_codes == ["03001b", "03001c"]
    assert "rules" not in json.dumps(card.to_json())
    assert "prose" not in json.dumps(card.to_json())


def test_a_linked_chain_that_loops_terminates():
    a: dict = {
        "code": "x1",
        "pack_code": "p",
        "position": 1,
        "name": "X",
        "type_code": "ally",
        "quantity": 1,
    }
    a["linked_card"] = {"code": "x2", "linked_card": a}
    assert reduce_card(a).linked_codes == ["x2", "x1"]


def test_pack_total_is_discarded():
    """research R12 — `total` disagrees with the summed quantity on two of three packs.

    Retained, it looks like a free completeness cross-check and would fire a false alarm on
    most packs, which is exactly what FR-018 and FR-019 forbid.
    """
    entries = parse_pack_index(
        [{"code": "cap", "name": "Captain America", "total": 56, "known": 34, "url": "..."}]
    )
    assert entries == [PackIndexEntry(code="cap", name="Captain America")]
    assert not hasattr(entries[0], "total")


def test_a_pack_index_entry_missing_a_field_is_refused():
    with pytest.raises(SnapshotInvalid):
        parse_pack_index([{"code": "cap"}])


# ------------------------------------------------------- validation (FR-047), on read


@pytest.mark.parametrize(
    "pack",
    [
        "cap",
        "wsp",
        "hlk",
        "thor",
        "bkw",
        "ant",
        "msm",
        "stld",
        "phoenix",
        "wonder_man",
        "core",
        "vision",
    ],
)
def test_every_committed_fixture_validates(pack):
    cards, warnings = parse_snapshot_cards(fixture(pack), pack)
    assert cards and all(isinstance(c, PackCard) for c in cards)
    assert all(isinstance(w, str) for w in warnings)


def test_a_pack_with_no_identity_card_is_refused():
    """A pack listing with no `type_code: hero` is a truncated response.

    It cannot satisfy FR-015a, and the failure it would otherwise produce is a PDF that
    quietly has no identity card in it.
    """
    cards = [c for c in fixture("cap") if c["type_code"] != "hero"]
    with pytest.raises(SnapshotInvalid, match="hero"):
        parse_snapshot_cards(cards, "cap")


def test_a_pack_with_no_nemesis_set_is_refused():
    cards = [c for c in fixture("cap") if c["card_set_type_name_code"] != "nemesis"]
    with pytest.raises(SnapshotInvalid, match="nemesis"):
        parse_snapshot_cards(cards, "cap")


def test_a_card_belonging_to_another_pack_is_refused():
    cards = fixture("cap")
    cards[3] = {**cards[3], "pack_code": "core"}
    with pytest.raises(SnapshotInvalid, match="pack_code"):
        parse_snapshot_cards(cards, "cap")


@pytest.mark.parametrize("quantity", [0, -1])
def test_a_quantity_below_one_is_refused(quantity):
    cards = fixture("cap")
    cards[3] = {**cards[3], "quantity": quantity}
    with pytest.raises(SnapshotInvalid, match="quantity"):
        parse_snapshot_cards(cards, "cap")


@pytest.mark.parametrize(
    "field,value",
    [("position", "one"), ("name", None), ("code", 3001), ("type_code", None), ("quantity", "2")],
)
def test_a_retained_field_of_the_wrong_type_is_refused(field, value):
    cards = fixture("cap")
    cards[3] = {**cards[3], field: value}
    with pytest.raises(SnapshotInvalid):
        parse_snapshot_cards(cards, "cap")


def test_a_missing_retained_field_is_refused():
    cards = fixture("cap")
    cards[3] = {k: v for k, v in cards[3].items() if k != "position"}
    with pytest.raises(SnapshotInvalid):
        parse_snapshot_cards(cards, "cap")


def test_an_empty_listing_is_refused():
    with pytest.raises(SnapshotInvalid):
        parse_snapshot_cards([], "cap")


def test_a_listing_that_is_not_a_list_is_refused():
    with pytest.raises(SnapshotInvalid):
        parse_snapshot_cards({"cards": []}, "cap")


def test_a_dangling_reprint_link_is_a_warning_not_a_refusal():
    """FR-047's one soft failure.

    It matters only if that card also fails to resolve locally, and FR-025 names it then.
    Refusing the whole pack for it would make one upstream data error unprintable.
    """
    cards = fixture("cap")
    cards[3] = {**cards[3], "duplicate_of_code": "99999"}
    parsed, warnings = parse_snapshot_cards(cards, "cap", known_pack_prefixes={"03", "01"})
    assert parsed
    assert any("99999" in w for w in warnings)


def test_a_reprint_link_into_a_known_pack_is_not_warned_about():
    """Measured, and not what one would guess: `cap`'s links point in both directions.

    Most are reprints *of* Core Set cards (prefix 01), but Falcon `03011` is `duplicated_by`
    `23014` — a pack released years later. So a rule that assumed reprints only ever point
    backwards, or only ever at the Core Set, would warn on real data every time.
    """
    cards = fixture("cap")
    prefixes = {c["code"][:2] for c in cards} | {
        target[:2]
        for c in cards
        for target in filter(None, [c["duplicate_of_code"], *c["duplicated_by"]])
    }
    assert prefixes > {"01", "03"}, "the two-directional link property this test rests on"
    _, warnings = parse_snapshot_cards(cards, "cap", known_pack_prefixes=prefixes)
    assert warnings == []


def test_validation_runs_without_a_pack_index_available():
    """The link check needs the index; the rest does not, and must not wait for it."""
    cards, warnings = parse_snapshot_cards(fixture("cap"), "cap")
    assert cards and warnings == []


# --------------------------------------------------------------------- round-tripping


def test_a_card_round_trips_through_json():
    """The snapshot is written to disk and read back, and read-back is validated again."""
    original, _ = parse_snapshot_cards(fixture("vision"), "vision")
    revived, _ = parse_snapshot_cards([c.to_json() for c in original], "vision")
    assert revived == original


def test_the_measured_face_mechanisms_survive_reduction():
    """research R12 — both mechanisms, and either alone is wrong."""
    cap, _ = parse_snapshot_cards(fixture("cap"), "cap")
    linked = next(c for c in cap if c.code == "03001a")
    assert linked.linked_codes == ["03001b"] and linked.double_sided is False

    vision, _ = parse_snapshot_cards(fixture("vision"), "vision")
    intangible = next(c for c in vision if c.code == "26002")
    assert intangible.double_sided is True and intangible.linked_codes == []

    ant, _ = parse_snapshot_cards(fixture("ant"), "ant")
    at_position_one = [c for c in ant if c.position == 1]
    # Not unique within a pack — the FR-020 join is many-to-one.
    assert len(at_position_one) == 2
