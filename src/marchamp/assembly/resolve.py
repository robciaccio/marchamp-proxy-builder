"""Pairing each card with an image, and recording how it was found (FR-020 - FR-025).

The cascade is six steps, first match wins, and the step that matched *is* the provenance —
that is the whole audit record FR-024 and SC-005 are asserted against. This module builds
steps 1 to 4 as a search. Steps 5 and 6 are not searched for at all: they are recorded
when the user answers, and **override** the cascade on every later pass.

    1  folder_position    exact (position, suffix) inside the hero folder     [here]
    2  library_position   the same, anywhere under the library root           [here]
    3  folder_name        the card's name, inside the hero folder             [here]
    4  reprint            another printing of the same card                   [here]
    5  name               the card's name, anywhere under the library root    [here]
    6  manual             a file the user uploaded for this card              [here]
    7  omitted            the user chose to print without it                  [here]

**Step 3 outranks step 4 because the user pointed at that folder.** The reprint step exists
for cards the scanner *skipped* because they were already in another pack (FR-014); it was
never meant to outrank a scan of the very printing being asked for. A real Wolverine run
borrowed Thor's `Battle Fury`, Shadowcat's `Colossus` and the Core Set's `Energy` while the
user's own scans of all three sat unused in the folder they had named (reported 2026-08-20).
Steps 4 and 5 keep their order for the same reason in reverse: a name match *elsewhere* is a
guess about another folder's file, where `duplicate_of_code` is card data.

**Nothing here picks between two candidates.** Ambiguity is reported and the user is asked
(FR-033); the index already draws the line between "one card in several renditions", which is
FR-034's deterministic pick, and "two cards claiming one key", which is a conflict. A resolver
that guessed would pair a card with confidently wrong art, and be silent about it.

**Steps 2 and 4 search outside the folder the user named, so neither may match on one piece
of evidence alone.** Position 33 occurs in more than a dozen packs and the name `Hawkeye` in
four folders, so a whole-library step that took either on its own would pair a card with
confidently wrong art at scale. What both do instead is narrow with things already known
about the *specific card being sought* — its canonical name, the face its code asks for, its
type — which is the direction FR-023 permits. Deciding what card a filename names is the
direction it forbids, and nothing here does it.

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

from marchamp.assembly.faces import DECKLIST_CODE, Face, Group, Side
from marchamp.assets.overlay import UPLOAD_PREFIX
from marchamp.assets.store import AssetUnreadable
from marchamp.library.filenames import FaceRole
from marchamp.library.index import LibraryIndex
from marchamp.upstream.models import PackCard

#: Read in blocks rather than whole: a real scan is ~2.6 MB and a pack is ~60 faces, so this
#: runs over ~150 MB of TIFF on every resolve pass.
_DIGEST_BLOCK = 1 << 20


class Provenance(StrEnum):
    DECKLIST_NAME = "decklist_name"
    FOLDER_POSITION = "folder_position"
    LIBRARY_POSITION = "library_position"
    #: Matched by name inside the folder the user named. Distinct from `NAME`, which is the
    #: same mechanism applied to the rest of the library, for the reason `FOLDER_POSITION`
    #: is distinct from `LIBRARY_POSITION`: the folder the user pointed at is evidence, and
    #: a file found in it is a different claim from one found three folders away.
    FOLDER_NAME = "folder_name"
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
    #: Which of FR-015's groups the missing card belongs to. Carried on the gap itself
    #: because the user reads it to know what they are missing — "the nemesis set is short
    #: one minion" is actionable in a way that a bare code is not (FR-015e, SC-008).
    group: Group = Group.PLAYER
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
            "group": self.group.value,
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


def digest_of(path: Path, ref: str | None = None) -> str:
    """`sha256` of the file's bytes — the identity the FR-026h reuse key is built on.

    **Every failure here is `AssetUnreadable`, never a bare `OSError` (FR-021, FR-026f).**
    This is the one library read that does not go through the asset adapter, and it was
    therefore the one that crashed: a Google Drive library reported
    `TimeoutError: [Errno 60]` on a placeholder it had not materialised yet, and it reached
    the user as a 500 with no explanation (2026-08-18). The same run succeeded minutes
    later, which is exactly why a 500 was the wrong answer — FR-021 classifies a file that
    is locked, permission-denied, or still syncing as *the* retryable condition, and the
    adapter has always named it that way.

    Reading a whole file over a network mount is also the slowest thing this module does, so
    the failure it raises is the one most worth getting right.
    """
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(_DIGEST_BLOCK), b""):
                hasher.update(block)
    except OSError as exc:
        # `TimeoutError` and friends are all `OSError`; catching the base is deliberate,
        # because a network filesystem can fail in ways this code has not met yet.
        raise AssetUnreadable(f"{ref or path.name}: {exc.strerror or exc}") from exc
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
    #: The first FR-033 clash the cascade ran into, reported only if nothing later resolves
    #: the card. An ambiguity a subsequent step settles unambiguously is not a gap, and
    #: reporting it as one would send the user hunting for a file they already have.
    conflict: tuple[str, ...] = ()

    # ---- step 1: an exact position inside the folder the user named (FR-020)
    for suffix in face_suffixes(face):
        candidates = index.positions_under(hero_folder, card.position, suffix)
        if candidates.conflict:
            # Two different cards at one position is a failure to match, which is exactly
            # what FR-021 says to widen the search on. Ant-Man's folder holds a mis-numbered
            # `Pym Particles` at position 7 alongside `Army of Ants`, and stopping here
            # would ask the user to supply a file that is sitting in the folder they named.
            # The clash is still reported — the report derives it from the library rather
            # than from this run's failures — so nothing about it goes quiet.
            conflict = conflict or tuple(sorted(e.ref for e in candidates.entries))
            continue
        chosen = candidates.chosen
        if chosen is not None:
            return _resolution(
                face, card, chosen.ref, library_root, Provenance.FOLDER_POSITION, note=None
            )
    searched.append(f"position {card.position} in the hero folder")

    # ---- step 2: the same position, anywhere under the library root (FR-021)
    for suffix in face_suffixes(face):
        candidates = index.positions_under(None, card.position, suffix)
        narrowed = [e for e in candidates.entries if _names_agree(e, card)]
        if not narrowed:
            continue
        chosen_ref = _deterministic(narrowed)
        if chosen_ref is None:
            conflict = conflict or tuple(sorted(e.ref for e in narrowed))
            continue
        return _resolution(
            face,
            card,
            chosen_ref,
            library_root,
            Provenance.LIBRARY_POSITION,
            note=_library_position_note(chosen_ref, card, hero_folder),
        )
    searched.append(f"position {card.position} anywhere under the library root")

    # ---- step 3: the card's name, inside the folder the user named (FR-023)
    chosen_ref, clash = _named_in_folder(index, card, face, hero_folder)
    searched.append(f"the name {card.name!r} in the hero folder")
    if chosen_ref is not None:
        return _resolution(
            face,
            card,
            chosen_ref,
            library_root,
            Provenance.FOLDER_NAME,
            note=_folder_name_note(card),
        )
    conflict = conflict or clash

    # ---- step 4: another printing of the same card (FR-014, FR-022)
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

    # ---- step 5: the card's name, anywhere under the library root (FR-023)
    chosen_ref, clash = _named_anywhere(index, card, face)
    searched.append(f"the name {card.name!r} across the library")
    if chosen_ref is not None:
        return _resolution(
            face,
            card,
            chosen_ref,
            library_root,
            Provenance.NAME,
            note=_name_note(chosen_ref, card),
        )
    conflict = conflict or clash

    return UnresolvedFace(
        face.card_code,
        face.name,
        face.side,
        group=face.group,
        searched=tuple(searched),
        conflict=conflict,
    )


def _named_in_folder(
    index: LibraryIndex, card: PackCard, face: Face, hero_folder: str
) -> tuple[str | None, tuple[str, ...]]:
    """Step 3: the file whose name is this card's, **inside the folder the user named**.

    Split from the library-wide pass and promoted above the reprint step on 2026-08-20. The
    two halves used to run together, after reprints, which meant a hero's own scan lost to
    another hero's folder whenever the local file carried no readable position — the common
    case in a folder that numbers physical copies, and the reported one.

    This step carries Phoenix and Wonder Man entirely (SC-003c). Their folders number
    physical copies rather than positions, so the index records no position for a single file
    in them and every positional step finds nothing at all.
    """
    prefix = f"{hero_folder}/"
    in_folder = [
        e
        for e in index.by_name(card.name).entries
        if e.folder == hero_folder or e.folder.startswith(prefix)
    ]
    if not in_folder:
        return None, ()
    return _narrow_by_card(in_folder, card, face)


def _named_anywhere(
    index: LibraryIndex, card: PackCard, face: Face
) -> tuple[str | None, tuple[str, ...]]:
    """Step 5: the same name search, across the whole library.

    Still **after** the reprint step, and deliberately. A name match in someone else's folder
    is a guess about a file this run knows nothing else about, where `duplicate_of_code` is
    card data saying two codes are one card. Wonder Man's folder holds a `Hawkeye` and so do
    three others, which is the shape of getting this wrong.
    """
    hits = list(index.by_name(card.name).entries)
    if not hits:
        return None, ()
    return _narrow_by_card(hits, card, face)


def _narrow_by_card(
    entries: Sequence[Any], card: PackCard, face: Face
) -> tuple[str | None, tuple[str, ...]]:
    """One ref from a set of name matches, using only what is known about *this* card.

    A name identifies a *card*; what is being resolved is a *face*. So the face the code
    asks for is applied first and is a filter rather than a tie-breaker: `Vision_Intangible
    _Upgrade_2a` and `_2b` are one card's two faces under one name, and a step that took the
    name alone would answer "where is the back?" with the front — printing a blank where the
    card carries game text, and reporting the run complete. Excluding is the whole job here,
    so a face left with no candidate is a gap, never a reason to relax back to the name.

    What remains can still be several cards, because the edit-distance bound has to be loose
    enough to absorb `Battlefild Benevolence` and a bound that loose pulls `Wonder Man` into
    the candidates for `Wonder Fans`. The **card's type** settles those — a Support is not a
    Hero, and the library writes the type into the filename as its own segment.

    Anything still ambiguous is returned as an FR-033 conflict naming every side, never as an
    arbitrary pick.
    """
    entries = _same_face(entries, face, card)
    if not entries:
        return None, ()
    chosen = _deterministic(entries)
    if chosen is not None:
        return chosen, ()

    reduced = _same_type(entries, card)
    if reduced and len(reduced) < len(entries):
        entries = reduced
        chosen = _deterministic(entries)
        if chosen is not None:
            return chosen, ()
    return None, tuple(sorted(e.ref for e in entries))


def _same_face(entries: Sequence[Any], face: Face, card: PackCard) -> list[Any]:
    """Candidates that could be this face, by the filename's label first and its suffix second.

    `face_suffixes` answers this for the positional steps and its set is used here unchanged:
    an ordinary single-faced card accepts an unsuffixed file or an `a`, a code ending in a
    letter accepts only that letter, and the back of a double-sided card accepts only `b`.

    **For an identity, the label outranks the suffix**, and that ordering is the whole of the
    2026-08-20 fix. MarvelCDB's convention is fixed — a code ending `a` is the hero side — but
    the library's suffixes are not: of 50 hero folders measured, 10 write `_Alter-Ego_1a` and
    `_Hero_1b`, and 2 give both faces the same letter. Trusting the suffix printed those
    twelve identities with their sides reversed, silently, because both files exist and both
    resolve. A hero whose alter-ego side is printed as the hero side is unplayable.

    The label cannot simply replace the suffix, because Ant-Man's identity has three faces and
    **two** are labelled Hero — `_Hero_Tiny_1a` and `_Hero_Giant_1c`. The label narrows, then
    the suffix separates what is left.

    Only identities. `Phoenix Force` is an upgrade whose faces are `34002a` and `34002b`, and
    "a is the hero side" is a fact about identities that would be nonsense applied to it.
    Files carrying no label — nearly all of them — are unaffected in every case.
    """
    allowed = face_suffixes(face)
    by_suffix = [e for e in entries if e.parsed.face_suffix in allowed]

    role = expected_face_role(face, card)
    if role is None:
        return by_suffix

    by_role = [e for e in entries if e.parsed.face_role is role]
    if not by_role:
        # Nothing claims a side, so the suffix is all there is — the pre-2026-08-20 answer,
        # and the right one when the library says nothing.
        return by_suffix
    narrowed = [e for e in by_role if e.parsed.face_suffix in allowed]
    # `narrowed` empty means the label and the suffix disagree, which is the inverted case:
    # believe the label. Non-empty means they agree, or that several files share the label
    # and the suffix told them apart.
    return narrowed or by_role


def expected_face_role(face: Face, card: PackCard) -> FaceRole | None:
    """Which side of an identity this face is, or `None` when the card is not an identity.

    From the card code's trailing letter, which is MarvelCDB's own convention and does not
    vary: `01001a` is Spider-Man and `01001b` is Peter Parker. Guarded on the card being a
    hero, because a letter suffix alone means only "this code has faces" and plenty of
    ordinary cards have them.

    `c` is a further hero form — Ant-Man's Giant-Man, Phoenix's third face — so it reads as
    the hero side, and the suffix is what separates it from `a`.
    """
    if (card.type_code or "").lower() != "hero":
        return None
    tail = face.card_code[-1].lower()
    if tail == "a" or tail == "c":
        return FaceRole.HERO
    if tail == "b":
        return FaceRole.ALTER_EGO
    return None


def _same_type(entries: Sequence[Any], card: PackCard) -> list[Any]:
    """Candidates whose filename carries this card's type as one of its segments.

    Matched against whole segments rather than as a substring, so `Ally` does not match a
    card called `Allying` and `Hero` does not match `Heroic Conditioning`.
    """
    from marchamp.library.filenames import normalise

    wanted = normalise(card.type_code or "")
    if not wanted:
        return []
    return [
        e
        for e in entries
        if any(normalise(segment) == wanted for segment in e.parsed.stem.split("_"))
    ]


def _folder_name_note(card: PackCard) -> str:
    """Why this file, in the user's terms (FR-024, SC-005).

    Says plainly that the position was never checked, because that is the part worth
    doubting: the file is in the right folder and carries the right name, and neither of
    those is the exact positional hit that needs no explanation.
    """
    return (
        f"Matched by name inside the hero folder: no position could be read from this file, "
        f"so its name was matched against {card.name}. Preferred over the same card's "
        "printing in another pack, because this is a scan of the pack being printed."
    )


def _library_position_note(ref: str, card: PackCard, hero_folder: str) -> str:
    """Where this came from, in the user's terms (FR-024, US3 scenarios 1 and 2).

    `library_position` names the step; it does not tell anyone that Black Widow's
    `Espionage` came out of the shared `Aspects/Basic` tree. The two cases read differently
    and are worth saying differently: a file found elsewhere is the ordinary US3 case, while
    one found inside the hero folder got here only because the position it sits at is
    contested — which the user should know before trusting the match.
    """
    folder = str(Path(ref).parent)
    inside = folder == hero_folder or folder.startswith(f"{hero_folder}/")
    if inside:
        return (
            f"Position {card.position} in the hero folder is claimed by more than one card; "
            f"this file was chosen because its name matches {card.name}."
        )
    return (
        f"Found outside the hero folder, at position {card.position} under {folder}, "
        f"matched on the name {card.name}."
    )


def _name_note(ref: str, card: PackCard) -> str:
    """US3 scenario 3 — a name match is reported *as* a name match.

    This is the loosest thing the cascade does: it tolerates the misspellings the library
    actually contains, which means it can tolerate a genuine difference too. Saying so, and
    naming the file, is what lets a wrong match be caught by reading the report rather than
    discovered mid-game.
    """
    return (
        f"Matched by name rather than by position: this file's name is within the tolerance "
        f"for {card.name}. No position was usable, so check it is the right card."
    )


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
        content_digest=digest_of(Path(library_root) / ref, ref),
        # FR-016: from the pack being printed, never from the printing lent the image.
        quantity=card.quantity,
        note=note,
    )


#: Provenances the user produced rather than the cascade. They **override** the cascade on
#: every later pass (FR-026b, US4 scenario 8): the library is re-read each time a run
#: advances, so an answer the user already gave has to survive a resolve that would
#: otherwise report the same card missing again — forever.
USER_SUPPLIED = frozenset({Provenance.MANUAL, Provenance.OMITTED})


def manual_resolution(
    card_code: str,
    card_name: str,
    side: Side,
    content_digest: str,
    original_filename: str,
    quantity: int = 1,
) -> Resolution:
    """A face paired with a file the user handed over (FR-026e, FR-027, FR-029).

    Two things distinguish this from every resolution the cascade builds, and both are
    requirements rather than bookkeeping:

    - **The ref is content, not a path.** `upload:<sha256>` routes to the run's own uploads
      directory through `assets.OverlayStore`, which is what lets the run reprint after the
      file the user picked has been moved or deleted (FR-026e, SC-006b).
    - **Only the file's own name is retained.** The file may have come from anywhere on the
      machine (FR-027), and a path from outside the named library must not reach the report,
      the record, or the log — so FR-009 holds without an exception carved into it.
    """
    return Resolution(
        card_code=card_code,
        card_name=card_name,
        side=side,
        provenance=Provenance.MANUAL,
        source=Source.UPLOAD,
        ref=f"{UPLOAD_PREFIX}{content_digest}",
        content_digest=content_digest,
        quantity=quantity,
        original_filename=original_filename,
        note="Supplied by hand for this card; the library holds no image for it.",
    )


def omitted_resolution(card_code: str, card_name: str, side: Side) -> Resolution:
    """A face the user explicitly chose to print without (FR-030, FR-030b).

    Carries no ref and no digest, deliberately. It is not a card that resolved to something
    — it is a card that resolved to *nothing*, on purpose, and giving it a plausible-looking
    file would put a phantom entry into the document. `build_catalog` drops it and the
    report names it in `omitted` and nowhere else, so the two never disagree.
    """
    return Resolution(
        card_code=card_code,
        card_name=card_name,
        side=side,
        provenance=Provenance.OMITTED,
        source=Source.LIBRARY,
        ref="",
        content_digest="",
        quantity=0,
        note="Printed without this card, at the user's explicit request.",
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
                    group=face.group,
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
