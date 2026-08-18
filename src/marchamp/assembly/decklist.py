"""The decklist card: step 0 of the cascade (FR-013b, FR-013c, FR-013d, FR-013e).

The decklist scan is the sheet listing which cards make up the hero's starter deck. It is
**not one of the pack's cards** — it has no MarvelCDB code, no position, no quantity, and it
is never counted among them (FR-013b, FR-018). It carries the pseudo-code `decklist`.

It is nevertheless US1's and not US4's. A pack printed without it is a pile of cards the user
cannot assemble a deck from, which is the whole point of printing a pack.

**Why this is step 0 rather than a fifth thing the cascade tries.** The cascade matches on a
position or on a canonical name, and the decklist has neither, so none of steps 1-4 can
express it. What identifies it is a literal `deck\\s*list` inside the filename stem — a
substring test, deliberately not FR-023's edit-distance match, because there is no card name
to be within a distance of.

**Proposed, then accepted.** The tool never prints a decklist the user has not agreed to
(FR-013d). The match is a filename heuristic over a folder someone else organised, and the
cost of being wrong is a wasted sheet of card stock in a pack that looks complete. Accepting
the tool's own candidate is **not** customization (FR-013e): were it, no run would ever be
standard and FR-026h's reuse would never fire once.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from marchamp.library.index import LibraryIndex

#: Where a user gets a decklist when their folder holds no scan of one (SC-006j). Shown to
#: the user and never fetched: FR-002 allows exactly one outbound host and this is not it.
HALL_OF_HEROES_URL = "https://hallofheroeslcg.com/deck-lists/"


class DecklistDecision(StrEnum):
    #: Print the candidate the tool proposed. Leaves the run **uncustomized** (FR-013e).
    CONFIRM = "confirm"
    #: Print a different file the user pointed at, inside the hero folder.
    SELECT = "select"
    #: Print no decklist card. Not a failure — FR-030's shape, applied to this one card.
    SKIP = "skip"


@dataclass(frozen=True)
class DecklistCandidate:
    #: Relative to the library root, always (FR-009).
    ref: str
    filename: str

    def to_json(self) -> dict[str, Any]:
        return {"ref": self.ref, "filename": self.filename}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DecklistCandidate:
        return cls(payload["ref"], payload["filename"])


@dataclass(frozen=True)
class DecklistState:
    """What the tool found in the folder, and what the user decided about it."""

    hero_folder: str
    candidate: DecklistCandidate | None = None
    #: Every candidate found, so an FR-033 conflict can name both sides to the user.
    candidates: tuple[DecklistCandidate, ...] = ()
    conflict: bool = False
    decision: DecklistDecision | None = None
    chosen_ref: str | None = None
    #: The uploaded file's **own name**, when the user supplied one (FR-013c, FR-027). The
    #: ref is `upload:<sha256>` in that case, which is what the run reads the bytes back
    #: through and is deliberately not something a person can recognise.
    uploaded_filename: str | None = None
    hall_of_heroes_url: str = HALL_OF_HEROES_URL

    @property
    def decided(self) -> bool:
        """FR-013d. Until this is true the run waits in `awaiting_cards`.

        The decklist needs no state of its own: it is a card waiting on the user like any
        other, and `skip` is the escape.
        """
        return self.decision is not None

    @property
    def printed(self) -> bool:
        return self.chosen_ref is not None

    @property
    def uploaded(self) -> bool:
        """Whether the printed deck list came from the user rather than from the folder."""
        return self.printed and self.uploaded_filename is not None

    @property
    def customizes_the_run(self) -> bool:
        """Whether this decision makes the run non-standard (FR-013e, FR-026i).

        Confirming the tool's own candidate does not: the result follows from the pack and
        the library exactly as an untouched run would. Choosing a different file or skipping
        does, because two users pointed at the same folder would now get different PDFs.
        """
        return self.decision in (DecklistDecision.SELECT, DecklistDecision.SKIP)

    def supply(self, ref: str, filename: str) -> DecklistState:
        """The user fetched a deck list and handed it over (FR-013c, research R9).

        25 of 60 hero folders hold no deck list scan, and the tool refuses to fetch one:
        Hall of Heroes is not on FR-002's egress allowlist and must not become the second
        host on it. So the run names the gap, offers the address, and the person goes and
        gets it — which lands here.

        Recorded as a `select`, because that is exactly what it is against FR-026i: the
        folder holds no such file, so two users pointed at it would now get different PDFs
        and this run cannot be the pack's standard one. `ref` is content-addressed rather
        than a path, so the run keeps the bytes and reprints identically afterwards
        (FR-026e, FR-045).
        """
        return replace(
            self, decision=DecklistDecision.SELECT, chosen_ref=ref, uploaded_filename=filename
        )

    def carrying(self, previous: DecklistState) -> DecklistState:
        """This pass's findings, keeping the decision the user already made (FR-026b).

        The ref is copied rather than re-derived through `decide`. It was contained against
        the hero folder — or content-addressed — when the decision was taken, and
        re-validating an uploaded ref against that folder would refuse a file that is not in
        the folder by design, silently undoing an answer the user gave.
        """
        return replace(
            self,
            decision=previous.decision,
            chosen_ref=previous.chosen_ref,
            uploaded_filename=previous.uploaded_filename,
        )

    def decide(self, decision: DecklistDecision, ref: str | None = None) -> DecklistState:
        if decision is DecklistDecision.CONFIRM:
            if self.candidate is None:
                raise ValueError("there is no proposed decklist to confirm")
            chosen = self.candidate.ref
        elif decision is DecklistDecision.SELECT:
            if not ref:
                raise ValueError("`select` requires the ref of the file to print")
            chosen = _contained(ref, self.hero_folder)
        else:
            chosen = None
        # `uploaded_filename` is dropped: a decision taken here names a file in the folder
        # or none at all, so carrying an earlier upload's name would label the folder's own
        # scan with it.
        return replace(self, decision=decision, chosen_ref=chosen, uploaded_filename=None)

    def to_json(self) -> dict[str, Any]:
        return {
            "hero_folder": self.hero_folder,
            "candidate": self.candidate.to_json() if self.candidate else None,
            "candidates": [c.to_json() for c in self.candidates],
            "conflict": self.conflict,
            "decision": self.decision.value if self.decision else None,
            "chosen_ref": self.chosen_ref,
            "uploaded_filename": self.uploaded_filename,
            "hall_of_heroes_url": self.hall_of_heroes_url,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DecklistState:
        candidate = payload.get("candidate")
        return cls(
            hero_folder=payload["hero_folder"],
            candidate=DecklistCandidate.from_json(candidate) if candidate else None,
            candidates=tuple(
                DecklistCandidate.from_json(c) for c in payload.get("candidates") or ()
            ),
            conflict=payload.get("conflict", False),
            decision=DecklistDecision(payload["decision"]) if payload.get("decision") else None,
            chosen_ref=payload.get("chosen_ref"),
            uploaded_filename=payload.get("uploaded_filename"),
            hall_of_heroes_url=payload.get("hall_of_heroes_url", HALL_OF_HEROES_URL),
        )


def _contained(ref: str, hero_folder: str) -> str:
    """A ref the browser supplied, checked against the folder the user named (FR-007).

    The decision endpoint takes this straight off the wire, so `..` is not a hypothetical.
    """
    normalised = ref.replace("\\", "/").strip("/")
    if ".." in normalised.split("/"):
        raise ValueError(f"{ref!r} escapes the hero folder")
    prefix = f"{hero_folder}/"
    if not (normalised == hero_folder or normalised.startswith(prefix)):
        raise ValueError(f"{ref!r} is not inside {hero_folder!r}")
    return normalised


def find_decklist(index: LibraryIndex, hero_folder: str) -> DecklistState:
    """Propose the decklist scan in this folder, if there is exactly one card's worth.

    Three outcomes, and the difference between the last two is the whole of FR-033 vs FR-034:

    - **None** — FR-013c's gap. Hulk's and Phoenix's real case, and not a failure: the run
      prints without a decklist card and offers the Hall of Heroes address.
    - **Several renditions of one file** — a `.tif`/`.tiff` pair. One candidate, chosen by
      filename order so the same library always yields the same PDF (Principle V).
    - **Several different files** — a conflict. Both sides are reported and the user picks;
      guessing would print the wrong sheet in a pack that otherwise looks complete.
    """
    entries = index.decklist_candidates(hero_folder)
    if not entries:
        return DecklistState(hero_folder=hero_folder)

    # `card_identity` is what tells a rendition pair apart from two different sheets — the
    # same distinction the index draws for card scans, reused rather than re-derived.
    by_identity: dict[str, list] = {}
    for entry in entries:
        by_identity.setdefault(entry.parsed.card_identity, []).append(entry)

    if len(by_identity) > 1:
        candidates = tuple(
            DecklistCandidate(e.ref, e.filename) for e in sorted(entries, key=lambda e: e.filename)
        )
        return DecklistState(hero_folder=hero_folder, candidates=candidates, conflict=True)

    (only,) = by_identity.values()
    chosen = sorted(only, key=lambda e: e.filename)[0]
    candidate = DecklistCandidate(chosen.ref, chosen.filename)
    return DecklistState(hero_folder=hero_folder, candidate=candidate, candidates=(candidate,))
