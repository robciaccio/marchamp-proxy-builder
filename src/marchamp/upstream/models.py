"""The reduced upstream record (FR-038a, FR-047, data-model.md § Pack Snapshot).

Two jobs, and they are separate on purpose.

**Reduction (FR-038a).** MarvelCDB's card record carries roughly seventy fields; eleven are
retained and the rest are dropped *here*, at ingest. That placement is the whole protection:
card text never enters the process, so it cannot reach a snapshot file, a log line, a run
record, or a committed fixture by anybody's oversight later. The nested `linked_card` is the
trap — upstream sends the linked card's entire record, rules text included, and the only
part face expansion needs is its code (research R12).

`pack.total` is dropped deliberately rather than by omission. It looks like a free
completeness cross-check and it is not: measured, it disagrees with the summed `quantity` on
two of the three packs checked, so wiring it in would fire a false alarm on most packs —
exactly what FR-018 and FR-019 forbid (research R12).

**Validation (FR-047), on capture *and* on read.** A snapshot is a JSON file on disk that
the user can edit and a partial write can truncate, so the constitution's "content validated
on read" clause applies to it directly. Every check below catches a way a snapshot can be
wrong that would otherwise surface as a bad PDF rather than as an error:

- no `type_code: hero` record — cannot satisfy FR-015a; a truncated response, not a pack;
- no `card_set_type_name_code: nemesis` record — cannot satisfy FR-015b;
- `quantity < 1` — would print zero copies of a card the pack ships;
- a field absent or of the wrong type — the resolver would then compare a string position
  against an integer one and silently match nothing.

A dangling reprint link is the single soft failure. It matters only if that card also fails
to resolve locally, and FR-025 names it then; refusing the whole pack over one bad upstream
link would make a printable pack unprintable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: data-model.md § PackCard. This tuple is the FR-038a boundary; adding to it is a spec
#: change, not a tweak (plan.md § Artifact Update Rule).
RETAINED_FIELDS = (
    "code",
    "pack_code",
    "position",
    "name",
    "type_code",
    "card_set_type_name_code",
    "quantity",
    "double_sided",
    "linked_codes",
    "duplicate_of_code",
    "duplicated_by",
)


class SnapshotInvalid(Exception):
    """Upstream data this application refuses to build a pack from.

    Raised at capture, aborting the capture and naming the pack, and again on read. Never
    downgraded to a warning: the conditions it covers all produce a wrong PDF rather than a
    visible failure.
    """


@dataclass(frozen=True)
class PackIndexEntry:
    """One row of `GET /api/public/packs/`, reduced to what identification needs."""

    code: str
    name: str


@dataclass(frozen=True)
class PackCard:
    """One card record, reduced to the fields this feature resolves against."""

    code: str
    pack_code: str
    position: int
    name: str
    type_code: str
    quantity: int
    card_set_type_name_code: str | None = None
    #: One code, two faces. Independent of `linked_codes` — R12 measured both mechanisms and
    #: an implementation reading only one prints Vision's Intangible front-only.
    double_sided: bool = False
    #: The `linked_card` chain flattened to codes. Each contributes further faces.
    linked_codes: list[str] = field(default_factory=list)
    duplicate_of_code: str | None = None
    duplicated_by: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "pack_code": self.pack_code,
            "position": self.position,
            "name": self.name,
            "type_code": self.type_code,
            "card_set_type_name_code": self.card_set_type_name_code,
            "quantity": self.quantity,
            "double_sided": self.double_sided,
            "linked_codes": list(self.linked_codes),
            "duplicate_of_code": self.duplicate_of_code,
            "duplicated_by": list(self.duplicated_by),
        }


# ------------------------------------------------------------------------- reduction


def _linked_codes(raw: dict[str, Any]) -> list[str]:
    """Flatten the `linked_card` chain to codes, discarding everything else about them.

    Bounded by a seen-set: upstream has been observed to nest a record inside its own
    linked card, and an unbounded walk there is an infinite loop at ingest.
    """
    codes: list[str] = []
    seen: set[str] = set()
    node = raw.get("linked_card")
    while isinstance(node, dict):
        code = node.get("code")
        if not isinstance(code, str) or code in seen:
            break
        seen.add(code)
        codes.append(code)
        node = node.get("linked_card")
    return codes


def _codes_from(value: Any) -> list[str]:
    """`duplicated_by` arrives as codes or as whole records depending on the endpoint."""
    out: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("code"), str):
            out.append(item["code"])
    return out


def reduce_card(raw: dict[str, Any]) -> PackCard:
    """Upstream's record to the eleven fields that are kept. Everything else is dropped."""
    if not isinstance(raw, dict):
        raise SnapshotInvalid(f"a card record must be an object, got {type(raw).__name__}")
    try:
        return PackCard(
            code=raw["code"],
            pack_code=raw["pack_code"],
            position=raw["position"],
            name=raw["name"],
            type_code=raw["type_code"],
            card_set_type_name_code=raw.get("card_set_type_name_code"),
            quantity=raw["quantity"],
            double_sided=bool(raw.get("double_sided", False)),
            # Already-reduced input (a stored snapshot, a fixture) carries `linked_codes`;
            # raw upstream carries `linked_card`. Both are read so one function serves
            # capture and read-back, which is what keeps the two from drifting.
            linked_codes=list(raw["linked_codes"])
            if isinstance(raw.get("linked_codes"), list)
            else _linked_codes(raw),
            duplicate_of_code=raw.get("duplicate_of_code"),
            duplicated_by=_codes_from(raw.get("duplicated_by")),
        )
    except KeyError as exc:
        raise SnapshotInvalid(f"card record is missing {exc.args[0]!r}") from exc


def parse_pack_index(payload: Any) -> list[PackIndexEntry]:
    """`GET /api/public/packs/`, reduced to `code` and `name` (data-model § Pack Index)."""
    if not isinstance(payload, list) or not payload:
        raise SnapshotInvalid("the pack index must be a non-empty list")
    entries: list[PackIndexEntry] = []
    for row in payload:
        if not isinstance(row, dict):
            raise SnapshotInvalid("a pack index row must be an object")
        code, name = row.get("code"), row.get("name")
        if not isinstance(code, str) or not isinstance(name, str):
            raise SnapshotInvalid(f"pack index row {row!r} needs a string code and name")
        entries.append(PackIndexEntry(code=code, name=name))
    return entries


# ------------------------------------------------------------------------ validation

_TYPES: dict[str, type | tuple[type, ...]] = {
    "code": str,
    "pack_code": str,
    "position": int,
    "name": str,
    "type_code": str,
    "quantity": int,
    "card_set_type_name_code": (str, type(None)),
    "double_sided": bool,
    "duplicate_of_code": (str, type(None)),
}


def _check_types(card: PackCard) -> None:
    for name, expected in _TYPES.items():
        value = getattr(card, name)
        # `bool` is a subclass of `int`, so an unqualified isinstance would accept
        # `position: true` — which would then compare equal to position 1.
        if expected is int and isinstance(value, bool):
            raise SnapshotInvalid(f"{card.code}: {name} must be an integer, got a boolean")
        if not isinstance(value, expected):
            raise SnapshotInvalid(
                f"{card.code}: {name} must be {expected}, got {type(value).__name__}"
            )


def parse_snapshot_cards(
    payload: Any, pack_code: str, known_pack_prefixes: set[str] | None = None
) -> tuple[list[PackCard], list[str]]:
    """Reduce and validate one pack's listing (FR-047).

    Returns the cards and any warnings. Called on capture *and* on read, because a stored
    snapshot is a file the user can edit and a partial write can truncate — validating only
    on capture would leave every later read trusting something nothing has checked.
    """
    if not isinstance(payload, list):
        raise SnapshotInvalid(f"pack {pack_code}: the card listing must be a list")
    if not payload:
        raise SnapshotInvalid(f"pack {pack_code}: the card listing is empty")

    cards = [reduce_card(raw) for raw in payload]
    for card in cards:
        _check_types(card)
        if card.pack_code != pack_code:
            raise SnapshotInvalid(
                f"{card.code}: pack_code is {card.pack_code!r} in a snapshot of "
                f"{pack_code!r} — a listing mixing packs is not a pack"
            )
        if card.quantity < 1:
            raise SnapshotInvalid(f"{card.code}: quantity must be at least 1, got {card.quantity}")

    if not any(c.type_code == "hero" for c in cards):
        raise SnapshotInvalid(
            f"pack {pack_code}: no card has type_code 'hero', so the pack has no identity "
            "card (FR-015a). This is a truncated response, not a printable pack."
        )
    if not any(c.card_set_type_name_code == "nemesis" for c in cards):
        raise SnapshotInvalid(
            f"pack {pack_code}: no card is in a nemesis set, which FR-015b requires"
        )

    return cards, _link_warnings(cards, known_pack_prefixes)


def _link_warnings(cards: list[PackCard], known_pack_prefixes: set[str] | None) -> list[str]:
    """A reprint link into a pack this application cannot fetch (FR-047, research R4).

    A warning rather than a refusal, and skipped entirely when the pack index is not
    available — the rest of validation must not wait on a second request.
    """
    if not known_pack_prefixes:
        return []
    warnings: list[str] = []
    for card in cards:
        for target in filter(None, [card.duplicate_of_code, *card.duplicated_by]):
            if target[:2] not in known_pack_prefixes:
                warnings.append(
                    f"{card.code} ({card.name}) links to {target}, which is in no pack this "
                    "application knows about. It matters only if this card also fails to "
                    "resolve locally."
                )
    return warnings
