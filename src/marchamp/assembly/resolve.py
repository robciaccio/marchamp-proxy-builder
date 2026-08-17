"""Pairing each card with an image, and recording how it was found (FR-020 - FR-025).

The cascade is six steps, first match wins, and the step that matched *is* the provenance —
that is the whole audit record FR-024 and SC-005 are asserted against. This module builds
steps 1 and 3; steps 2 and 4 are US3's, 5 is US4's upload, and 6 is FR-030's omission.

    1  folder_position    exact (position, suffix) inside the hero folder     [here]
    2  library_position   the same, anywhere under the library root           [US3]
    3  reprint            another printing of the same card                   [here]
    4  name               the canonical name of the card being sought         [US3]
    5  manual             a file the user uploaded for this card              [US4]
    6  omitted            the user chose to print without it                  [FR-030]

**Nothing here picks between two candidates.** Ambiguity is reported and the user is asked
(FR-033); the index already draws the line between "one card in several renditions", which is
FR-034's deterministic pick, and "two cards claiming one key", which is a conflict. A resolver
that guessed would pair a card with confidently wrong art, and be silent about it.

**Copy counts never travel with a borrowed image** (FR-016). `cap` prints two Make the Call;
the Core Set printing whose scan it borrows ships three. The quantity comes from the pack
being printed, always, and a resolution carries it so nothing downstream has to re-derive it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from marchamp.assembly.faces import DECKLIST_CODE, Face, Side
from marchamp.library.index import LibraryIndex
from marchamp.upstream.models import PackCard

#: Read in blocks rather than whole: a real scan is ~2.6 MB and a pack is ~60 faces, so this
#: runs over ~150 MB of TIFF on every resolve pass.
_DIGEST_BLOCK = 1 << 20


class Provenance(StrEnum):
    DECKLIST_NAME = "decklist_name"
    FOLDER_POSITION = "folder_position"
    LIBRARY_POSITION = "library_position"
    REPRINT = "reprint"
    NAME = "name"
    MANUAL = "manual"
    OMITTED = "omitted"


class Source(StrEnum):
    LIBRARY = "library"
    UPLOAD = "upload"


#: Every provenance except step 1 is a substitution the user is shown (FR-024, SC-005). An
#: exact positional hit inside the folder they named is the case that needs no explanation;
#: everything else is the tool having gone looking, and hiding that is how a wrong match
#: becomes invisible rather than merely wrong.
_UNREMARKABLE = frozenset({Provenance.FOLDER_POSITION})


@dataclass(frozen=True)
class Resolution:
    """One card face paired with one image, and the account of how they were paired."""

    card_code: str
    card_name: str
    side: Side
    provenance: Provenance
    source: Source
    #: Relative to `library_root`, or the upload's content digest. Never an absolute path
    #: from outside the named library (FR-009, FR-027).
    ref: str
    content_digest: str
    #: Copies of this card **in the pack being printed** (FR-016), never in the printing an
    #: image was borrowed from.
    quantity: int = 1
    original_filename: str | None = None
    note: str | None = None

    @property
    def substituted(self) -> bool:
        return self.provenance not in _UNREMARKABLE

    def to_json(self) -> dict[str, Any]:
        return {
            "card_code": self.card_code,
            "card_name": self.card_name,
            "side": self.side.value,
            "provenance": self.provenance.value,
            "source": self.source.value,
            "ref": self.ref,
            "content_digest": self.content_digest,
            "quantity": self.quantity,
            "original_filename": self.original_filename,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> Resolution:
        return cls(
            card_code=payload["card_code"],
            card_name=payload["card_name"],
            side=Side(payload["side"]),
            provenance=Provenance(payload["provenance"]),
            source=Source(payload["source"]),
            ref=payload["ref"],
            content_digest=payload["content_digest"],
            quantity=payload.get("quantity", 1),
            original_filename=payload.get("original_filename"),
            note=payload.get("note"),
        )


@dataclass(frozen=True)
class UnresolvedFace:
    """A face no step could pair with an image. Named, never dropped (FR-017, FR-025)."""

    card_code: str
    card_name: str
    side: Side
    #: Where the cascade looked, in the user's terms. A gap the user cannot act on is a
    #: failure report they have to guess at (FR-037, SC-008).
    searched: tuple[str, ...] = ()
    #: Both sides of an FR-033 conflict, when that is why this did not resolve.
    conflict: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "card_code": self.card_code,
            "card_name": self.card_name,
            "side": self.side.value,
            "searched": list(self.searched),
            "conflict": list(self.conflict),
        }


@dataclass
class ResolveResult:
    resolutions: list[Resolution] = field(default_factory=list)
    unresolved: list[UnresolvedFace] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Whether every face found an image. FR-017 stops the run when this is false."""
        return not self.unresolved


def face_suffixes(face: Face) -> tuple[str | None, ...]:
    """Which filename suffixes could carry this face, best first.

    The library suffixes a face `_1a`, `_1b`, `_1c`, and two independent mechanisms produce
    faces (research R12), so the suffix has to be derived from whichever applies:

    - **Linked codes.** `03001a` and `03001b` are two distinct cards at one position; the
      code's own trailing letter is the suffix, and it is exact.
    - **The `double_sided` flag.** `26002` is one code with two faces and no letter to read,
      so the back is `b` by convention.
    - **Neither.** An ordinary single-faced card has no suffix at all — but a hero folder
      that suffixes everything would still write `a`, so that is tried second. Unsuffixed
      first, because it is the overwhelmingly common form and trying `a` first would let a
      genuinely suffixed file answer for a card that has no faces.
    """
    tail = face.card_code[-1]
    if tail.isalpha():
        return (tail.lower(),)
    if face.side is Side.BACK:
        return ("b",)
    return (None, "a")


def digest_of(path: Path) -> str:
    """`sha256` of the file's bytes — the identity the FR-026h reuse key is built on."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_DIGEST_BLOCK), b""):
            hasher.update(block)
    return hasher.hexdigest()


def linked_printing_codes(card: PackCard) -> list[str]:
    """Every other printing this card is linked to, in **both** directions (FR-022).

    `duplicate_of_code` is the forward link and `duplicated_by` the reverse. Measured, the
    pack response fills in only the forward one (research R4) — but Wasp's `13020` duplicates
    Ant-Man's `12020` rather than anything in the Core Set, so a resolver that special-cased
    the Core Set or followed one direction would be wrong on real data, not hypothetically.
    """
    codes: list[str] = []
    seen: set[str] = set()
    for code in [card.duplicate_of_code, *card.duplicated_by]:
        if code and code not in seen and code != card.code:
            seen.add(code)
            codes.append(code)
    return codes


def _resolve_face(
    face: Face,
    card: PackCard,
    index: LibraryIndex,
    hero_folder: str,
    library_root: Path,
    load_printing: Callable[[str], PackCard | None],
) -> Resolution | UnresolvedFace:
    searched: list[str] = []

    # ---- step 1: an exact position inside the folder the user named (FR-020)
    for suffix in face_suffixes(face):
        candidates = index.positions_under(hero_folder, card.position, suffix)
        if candidates.conflict:
            return UnresolvedFace(
                face.card_code,
                face.name,
                face.side,
                searched=(*searched, f"position {card.position} in the hero folder"),
                conflict=tuple(sorted(e.ref for e in candidates.entries)),
            )
        chosen = candidates.chosen
        if chosen is not None:
            return _resolution(
                face, card, chosen.ref, library_root, Provenance.FOLDER_POSITION, note=None
            )
    searched.append(f"position {card.position} in the hero folder")

    # ---- step 3: another printing of the same card (FR-014, FR-022)
    for other_code in linked_printing_codes(card):
        other = load_printing(other_code)
        if other is None:
            # A link into a pack this application cannot fetch. A gap to report, never a
            # reason to pick an arbitrary file (FR-047).
            searched.append(f"reprint {other_code}, whose pack could not be read")
            continue
        searched.append(f"reprint {other_code} at position {other.position}")
        borrowed = _borrowed_entry(index, other)
        if borrowed is None:
            continue
        note = (
            f"Borrowed the image from {other.name} ({other_code}), another printing of this "
            f"card, at position {other.position}."
        )
        return _resolution(face, card, borrowed, library_root, Provenance.REPRINT, note=note)

    return UnresolvedFace(face.card_code, face.name, face.side, searched=tuple(searched))


def _borrowed_entry(index: LibraryIndex, other: PackCard) -> str | None:
    """Find the other printing's scan: its position, narrowed by its name.

    Position alone is not enough and neither is name alone, which is why both are used. The
    other printing's folder cannot be named — the Core Set's aspect cards live under
    `Core Set/Aspects/<faction>/`, and this code has no way to know that from a card code —
    so the position search has to span the whole library, where position 90 occurs in many
    packs. Narrowing by the card's canonical name makes it exact.

    The reverse also bites. Searching by name alone, `Strength` at Core Set position 90 also
    matches `Stength in Numbers` in Captain America's own folder, one edit away and a
    different card entirely; the position rules it out.
    """
    for suffix in (None, "a"):
        candidates = index.positions_under(None, other.position, suffix)
        matching = [e for e in candidates.entries if _names_agree(e, other)]
        if not matching:
            continue
        chosen = _deterministic(matching)
        if chosen is not None:
            return chosen
    return None


def _names_agree(entry: Any, card: PackCard) -> bool:
    from marchamp.library.filenames import matches_name

    return any(matches_name(key, card.name) for key in entry.parsed.name_keys)


def _deterministic(entries: Sequence[Any]) -> str | None:
    """One ref, or none when two *different* cards are in play (FR-033, FR-034).

    Renditions of a single card — a `.tif`/`.tiff` pair — are one candidate resolved by
    filename order so the same library always yields the same PDF (Principle V).
    """
    identities = {e.parsed.card_identity for e in entries}
    if len(identities) != 1:
        return None
    return sorted(entries, key=lambda e: e.filename)[0].ref


def _resolution(
    face: Face,
    card: PackCard,
    ref: str,
    library_root: Path,
    provenance: Provenance,
    note: str | None,
) -> Resolution:
    return Resolution(
        card_code=face.card_code,
        card_name=face.name or card.name,
        side=face.side,
        provenance=provenance,
        source=Source.LIBRARY,
        ref=ref,
        content_digest=digest_of(Path(library_root) / ref),
        # FR-016: from the pack being printed, never from the printing lent the image.
        quantity=card.quantity,
        note=note,
    )


def resolve_pack(
    faces: Iterable[Face],
    cards: Sequence[PackCard],
    index: LibraryIndex,
    hero_folder: str,
    library_root: Path,
    load_printing: Callable[[str], PackCard | None],
) -> ResolveResult:
    """Run the cascade over every face the pack prints.

    `load_printing` is supplied by the caller rather than taken as a `SnapshotStore`
    dependency, so this module has no opinion about caching, freshness, or the network — and
    so a test can resolve a whole pack without any of them. The service wires it to research
    R4's prefix→pack map.
    """
    by_source = {c.code: c for c in cards}
    result = ResolveResult()

    for face in faces:
        if face.card_code == DECKLIST_CODE:
            # The decklist never enters the FR-020-FR-025 cascade: it has no pack code, no
            # position and no canonical name. It is step 0's, handled by the decklist module.
            continue
        card = by_source.get(face.source_code) or by_source.get(face.card_code)
        if card is None:
            result.unresolved.append(
                UnresolvedFace(
                    face.card_code,
                    face.name,
                    face.side,
                    searched=("no record for this face in the pack listing",),
                )
            )
            continue
        outcome = _resolve_face(face, card, index, hero_folder, library_root, load_printing)
        if isinstance(outcome, Resolution):
            result.resolutions.append(outcome)
        else:
            result.unresolved.append(outcome)

    return result
