"""Cards to printable faces (FR-015, FR-015a, FR-015b, FR-015f, FR-018, research R12).

A face is the printable unit and is derived from the card data, never from a filename. Two
**independent** mechanisms produce one, and reading only one of them is the defect FR-015f
was added to close:

    linked codes      cap 03001a -> 03001b     two codes, one card, two faces
                                               (`double_sided` is false on both)
    double_sided      vision 26002 Intangible  one code, two faces, no linked card

R8 recorded the first and concluded that `double_sided` was always false on identity cards.
True, and incomplete: R12 measured the second. An implementation reading only the linked
chain prints Intangible front-only — a proxy blank where the real card carries game text —
and FR-017 then reports the run clean. Nothing else in this feature catches that.

Ant-Man is the third shape and the reason `position` is never an identifier: two records at
position 1, `12001a` (linked to `12001b`) and `12001c`, three faces across two records for
one physical card.

**Counting has two units and both are reported** (data-model § Face). FR-018 counts *cards*,
because that is the unit the pack listing counts in. The page count follows from *faces*,
which is what SC-002b asserts. There is deliberately no expected total anywhere here: deck
sizes were measured at 40, 41, and 42, and `pack.total` disagrees with the summed quantity
on two of three packs, so any cross-check would fire false alarms (FR-018, FR-019, R12).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from marchamp.upstream.models import PackCard


class Side(StrEnum):
    FRONT = "front"
    BACK = "back"


class Group(StrEnum):
    PLAYER = "player"
    IDENTITY = "identity"
    NEMESIS = "nemesis"
    #: Not present in the card data at all. Found by filename (FR-013d) or uploaded
    #: (FR-013c), carries the pseudo-code `decklist`, and is never counted among the pack's
    #: cards (FR-013b, FR-018).
    DECKLIST = "decklist"


#: FR-015d's order. Player cards, identity, nemesis, decklist — packed into as few pages as
#: will hold them with *no page break between groups*, because paper is the cost being
#: minimised. 001's `paginate` chunks a flat list nine at a time with no notion of groups,
#: so handing it this order satisfies FR-015d and SC-002b by construction (research R8).
GROUP_ORDER = (Group.PLAYER, Group.IDENTITY, Group.NEMESIS, Group.DECKLIST)

#: The decklist card's stand-in code. Not a MarvelCDB code and never treated as one.
DECKLIST_CODE = "decklist"


@dataclass(frozen=True)
class Face:
    card_code: str
    side: Side
    group: Group
    #: The record this face came from. Ant-Man's identity spans two, so a face cannot be
    #: traced back by code alone.
    source_code: str = ""
    position: int = 0
    name: str = ""


def classify(card: PackCard) -> Group:
    """Which of FR-015's groups this card belongs to, from the card data alone.

    Order matters and is not arbitrary: an identity card also carries
    `card_set_type_name_code == "hero"`, so testing the card set first would file the
    identity among the player cards, leave FR-015a's output empty, and produce a PDF missing
    the one card the pack is named after.
    """
    if card.type_code == "hero":
        return Group.IDENTITY
    if card.card_set_type_name_code == "nemesis":
        return Group.NEMESIS
    return Group.PLAYER


def faces_for(card: PackCard, pack: Sequence[PackCard] = ()) -> list[Face]:
    """Expand one record into faces, applying **both** mechanisms.

        for each code C in [record.code, *record.linked_codes]:
            front(C)
            back(C)  if C is double_sided

    `pack` supplies the `double_sided` flag for a linked code when that code is also a
    record in its own right. No measured pack does that today — but the two mechanisms are
    independent, so the combination is expressible, and assuming it cannot happen would
    reintroduce the FR-015f bug for whichever pack does it first.
    """
    double_sided = {c.code: c.double_sided for c in pack}
    # The record's own flag wins over anything the pack listing says about its code, so a
    # caller passing no pack still gets correct expansion for that record.
    double_sided[card.code] = card.double_sided

    group = classify(card)
    faces: list[Face] = []
    for code in [card.code, *card.linked_codes]:
        faces.append(
            Face(
                code,
                Side.FRONT,
                group,
                source_code=card.code,
                position=card.position,
                name=card.name,
            )
        )
        if double_sided.get(code, False):
            # Emitted immediately after its front so the two are cut and sleeved as a pair,
            # inherited from 001's FR-012b.
            faces.append(
                Face(
                    code,
                    Side.BACK,
                    group,
                    source_code=card.code,
                    position=card.position,
                    name=card.name,
                )
            )
    return faces


def expand_pack(cards: Sequence[PackCard]) -> list[Face]:
    """Every face the pack prints, in FR-015d's order, one copy of each card.

    Quantity is applied later, where the resolved images are known — repeating faces here
    would mean hashing and validating the same image several times for no gain.

    Sorted on `(group, position, code)` rather than on the order records arrived in, so the
    same pack always produces the same document (Principle V, research R10).
    """
    ordered = sorted(cards, key=lambda c: (GROUP_ORDER.index(classify(c)), c.position, c.code))
    return [face for card in ordered for face in faces_for(card, cards)]


def card_count(cards: Iterable[PackCard]) -> int:
    """Physical cards, which is what FR-018 reports.

    The summed `quantity`, not the record count: `quantity` is copies **in the pack**, which
    is exactly what this feature prints (FR-016). The two differ a lot — `cap` is 34 records
    and 59 cards.
    """
    return sum(c.quantity for c in cards)


def face_count(cards: Iterable[PackCard]) -> int:
    """Printed faces, which is what the page count follows from (SC-002b).

    Reported alongside the card count rather than instead of it. A double-sided card is one
    card and two faces; Ant-Man's identity is one card and three.
    """
    cards = list(cards)
    return sum(len(faces_for(c, cards)) * c.quantity for c in cards)
