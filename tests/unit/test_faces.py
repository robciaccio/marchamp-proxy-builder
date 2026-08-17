"""T038 — cards to printable faces (FR-015, FR-015a, FR-015b, FR-015f, FR-018, research R12).

A face is the printable unit, and it is derived from the card data — never from a filename.
Two independent mechanisms produce one, and **reading only one of them is the bug FR-015f
was added to close**:

- **linked codes**: `cap` `03001a` links to `03001b`. Two codes, one physical card, two
  faces, and `double_sided` is `false` on both;
- **the `double_sided` flag**: `vision` `26002` Intangible. One code, two faces, no linked
  card at all.

An implementation reading only the linked chain prints Intangible front-only — a proxy blank
where the real card carries game text — and every other check in this feature reports the run
clean. Nothing else catches it, which is why it has a test of its own.

Ant-Man is the third shape and the reason `position` cannot be an identifier: two records at
position 1, `12001a` (linked to `12001b`) and `12001c`, giving three faces across two records
for one physical identity card.

Counting has two units and the report carries both (data-model § Face). FR-018 counts
**cards**, because that is what the pack listing counts in. The page count follows from
**faces**, which is what SC-002b asserts. Conflating them makes one of the two wrong.
"""

from __future__ import annotations

import pytest

from marchamp.assembly.faces import (
    Group,
    Side,
    card_count,
    classify,
    expand_pack,
    face_count,
    faces_for,
)
from marchamp.upstream.models import parse_snapshot_cards
from tests.conftest import snapshot_fixture


def pack(code: str):
    cards, _ = parse_snapshot_cards(snapshot_fixture(code), code)
    return cards


def card(cards, code: str):
    return next(c for c in cards if c.code == code)


# ----------------------------------------------------------- the two mechanisms


def test_linked_codes_give_two_faces():
    """`cap` `03001a` -> `03001b`. Note `double_sided` is false on both (research R8)."""
    cap = pack("cap")
    identity = card(cap, "03001a")
    assert identity.double_sided is False
    assert identity.linked_codes == ["03001b"]

    faces = faces_for(identity, cap)
    assert [(f.card_code, f.side) for f in faces] == [
        ("03001a", Side.FRONT),
        ("03001b", Side.FRONT),
    ]


def test_the_double_sided_flag_gives_two_faces_with_no_linked_card():
    """`vision` `26002` Intangible — the mechanism R8 missed and R12 found.

    Reading only the linked chain prints this front-only and reports the run clean. That is
    the exact failure FR-015f exists to close, and it is invisible to every other check.
    """
    vision = pack("vision")
    intangible = card(vision, "26002")
    assert intangible.double_sided is True
    assert intangible.linked_codes == []

    faces = faces_for(intangible, vision)
    assert [(f.card_code, f.side) for f in faces] == [
        ("26002", Side.FRONT),
        ("26002", Side.BACK),
    ]


def test_ant_mans_two_records_at_one_position_give_three_faces():
    """FR-015a — the identity card with *every* face its card data records."""
    ant = pack("ant")
    at_position_one = [c for c in ant if c.position == 1]
    assert len(at_position_one) == 2  # position is not an identifier (research R12)

    faces = [f for record in at_position_one for f in faces_for(record, ant)]
    assert [f.card_code for f in faces] == ["12001a", "12001b", "12001c"]
    assert all(f.group is Group.IDENTITY for f in faces)


def test_an_ordinary_single_faced_card_gives_one_face():
    cap = pack("cap")
    faces = faces_for(card(cap, "03002"), cap)
    assert len(faces) == 1 and faces[0].side is Side.FRONT


def test_a_linked_code_that_is_itself_double_sided_gets_a_back():
    """Not observed in any measured pack, and the model must not assume it never happens.

    The two mechanisms are independent, so the combination is expressible even though the
    twelve committed fixtures contain no instance of it. Assuming otherwise would put the
    FR-015f bug back for whichever pack first does this.
    """
    from marchamp.upstream.models import PackCard

    linked = PackCard(
        code="99002",
        pack_code="test",
        position=1,
        name="Back Face",
        type_code="upgrade",
        quantity=1,
        double_sided=True,
    )
    front = PackCard(
        code="99001",
        pack_code="test",
        position=1,
        name="Front Face",
        type_code="hero",
        quantity=1,
        linked_codes=["99002"],
    )
    faces = faces_for(front, [front, linked])
    assert [(f.card_code, f.side) for f in faces] == [
        ("99001", Side.FRONT),
        ("99002", Side.FRONT),
        ("99002", Side.BACK),
    ]


# ------------------------------------------------------------- group classification


def test_the_identity_card_is_the_hero_type():
    cap = pack("cap")
    assert classify(card(cap, "03001a")) is Group.IDENTITY


def test_the_nemesis_set_is_its_own_group():
    """FR-015b — a printed player deck with no nemesis set is not something you can play."""
    cap = pack("cap")
    nemesis = [c for c in cap if classify(c) is Group.NEMESIS]
    assert nemesis
    assert all(c.card_set_type_name_code == "nemesis" for c in nemesis)


def test_everything_else_is_a_player_card():
    cap = pack("cap")
    assert classify(card(cap, "03002")) is Group.PLAYER


def test_the_identity_classification_beats_the_card_set():
    """A hero record also carries `card_set_type_name_code: hero`, so order matters.

    Classified the other way round the identity card lands in the player deck, FR-015a's
    output is empty, and the PDF is missing the one card the whole pack is named after.
    """
    cap = pack("cap")
    identity = card(cap, "03001a")
    assert identity.card_set_type_name_code == "hero"
    assert classify(identity) is Group.IDENTITY


@pytest.mark.parametrize(
    "code", ["cap", "wsp", "hlk", "thor", "bkw", "ant", "msm", "stld", "phoenix", "wonder_man"]
)
def test_every_acceptance_hero_has_all_three_groups(code):
    """FR-015a-c — a pack missing any of them cannot be sat down and played."""
    groups = {classify(c) for c in pack(code)}
    assert {Group.IDENTITY, Group.NEMESIS, Group.PLAYER} <= groups


# ------------------------------------------------------------------------ ordering


def test_the_pack_expands_in_the_order_fr_015d_requires():
    """Player cards, identity, nemesis, then the decklist — packed with no page break.

    001's `paginate` chunks a flat face list nine at a time with no notion of groups, so
    handing it this order satisfies FR-015d and SC-002b by construction (research R8). What
    keeps the groups tellable apart is the report, not the layout (FR-015e).
    """
    faces = expand_pack(pack("cap"))
    groups = [f.group for f in faces]
    first_of = {g: groups.index(g) for g in set(groups)}
    assert first_of[Group.PLAYER] < first_of[Group.IDENTITY] < first_of[Group.NEMESIS]
    # And each group is contiguous, so the report can name a range rather than a set.
    for group in set(groups):
        indices = [i for i, g in enumerate(groups) if g is group]
        assert indices == list(range(indices[0], indices[-1] + 1))


def test_expansion_is_deterministic():
    """Principle V, research R10 — sorted on `(position, code)`, never on dict order."""
    assert [f.card_code for f in expand_pack(pack("cap"))] == [
        f.card_code for f in expand_pack(pack("cap"))
    ]


def test_both_faces_of_a_card_are_adjacent():
    """Inherited from 001's FR-012b — cut and sleeved as a pair, not hunted across pages."""
    faces = expand_pack(pack("vision"))
    codes = [f.card_code for f in faces]
    back = next(i for i, f in enumerate(faces) if f.side is Side.BACK)
    assert codes[back - 1] == codes[back]


# ------------------------------------------------------------------------ counting


def test_cards_and_faces_are_counted_in_different_units():
    """data-model § Face — the report carries both, and conflating them makes one wrong.

    FR-018 counts cards because the pack listing does. The page count follows from faces
    (SC-002b). Vision is 36 records, 59 physical cards, and more faces than either.
    """
    vision = pack("vision")
    assert len(vision) == 36
    assert card_count(vision) == 59
    assert face_count(vision) > card_count(vision)


def test_a_card_count_is_the_summed_quantity_not_the_record_count():
    """FR-016 — copies come from the pack being printed, and `quantity` is a pack count."""
    cap = pack("cap")
    assert card_count(cap) == 59
    assert len(cap) == 34


def test_a_double_sided_card_is_one_card_and_two_faces():
    vision = pack("vision")
    intangible = card(vision, "26002")
    assert card_count([intangible]) == intangible.quantity
    assert face_count([intangible]) == 2 * intangible.quantity


def test_no_expected_total_is_asserted_anywhere():
    """FR-018, FR-019 — deck sizes measured at 40, 41, and 42; no universal exists.

    `pack.total` is discarded for the same reason (research R12): it disagrees with the
    summed quantity on two of three packs, so a cross-check against it fires false alarms.
    """
    from marchamp.assembly import faces as module

    # Measured: three packs, three different totals. Any constant would be wrong for two.
    counts = {code: card_count(pack(code)) for code in ("cap", "vision", "ant")}
    assert len(set(counts.values())) > 1

    # And nothing here holds one to compare against, which is the mechanical guarantee.
    assert not hasattr(module, "EXPECTED_PACK_SIZE")
    assert not any(
        isinstance(value, int) and 30 <= value <= 70
        for name, value in vars(module).items()
        if not name.startswith("_")
    )
