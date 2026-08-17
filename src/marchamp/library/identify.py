"""Identifying which pack a hero folder holds (FR-010, FR-011, FR-012, research R3, R4).

The user names a folder. Nothing in the folder says which MarvelCDB pack it is — there is no
manifest, no pack code, and the filenames carry card names at best. So identification is a
guess that gets checked, in two steps and two requests:

1. **Rank** the 61 pack names against the folder's name. Cheap, offline, and usually right,
   because the library is organised `<alter ego>_<hero>` and packs are named after heroes.
2. **Verify** the top candidate by fetching that one pack's cards and measuring how much of
   the folder they explain. This is the step that catches a folder whose *name* matches a
   pack it is not.

**Only the top candidate is verified.** Checking the top three would triple the request count
for a figure the user confirms by hand anyway, and FR-040/SC-006d hold a whole run to a
request budget measured in single digits (research R4).

**The threshold is not the safety mechanism; confirmation is.** FR-011's floor catches the
folder that matches almost nothing. It structurally cannot catch an identification that is
confident and wrong — a hero folder holding a *different* hero's scans ranks and verifies
perfectly well against the wrong pack if the filenames say so. That case is why FR-012a makes
confirmation unconditional and why nothing resolves before it (SC-009). Below the floor the
run is refused *and offered candidates*: a refusal is a prompt, never a dead end (FR-012b).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from marchamp.library.filenames import Form, edit_distance, normalise
from marchamp.library.index import LibraryIndex
from marchamp.upstream.models import PackCard, PackIndexEntry

#: FR-011's floor, **measured in T042** across the ten acceptance heroes against every pack
#: with a committed snapshot. The full matrix is in data-model.md § Pack Identification.
#:
#:     lowest score for a folder's own pack   0.87  (Wasp, 20 of 23 files)
#:     highest score for a wrong pack         0.65  (Ant-Man's folder against the Wasp pack)
#:
#: 0.75 sits in that gap with margin on both sides. The provisional 0.60 this replaces was
#: *below* the measured false-positive ceiling and would have admitted that Ant-Man/Wasp
#: pair — the two packs each contain the other hero as an ally, so they genuinely share
#: names. A threshold only the easy folders clear is worse than none.
DEFAULT_MIN_CONFIDENCE = 0.75

#: A share alone passes a folder holding two files that both happen to match. The count is
#: the guard against small folders, not against wrong ones — every true pack matched at
#: least 17 cards, so this floor never binds in a real case.
DEFAULT_MIN_MATCHED_CARDS = 5

#: How many alternatives FR-012b offers when identification is refused or declined. Enough
#: to contain the right answer when ranking is merely off, short enough to read.
DEFAULT_CANDIDATE_LIMIT = 8

#: A trailing `(u)`, `(ns)` and friends mark the *scan* — unofficial art, no scan yet — not
#: the hero. Phoenix's folder is `Jean Grey_Phoenix (u)` and the pack is plain "Phoenix".
_TRAILING_MARKER_RE = re.compile(r"\s*\([^)]*\)\s*$")

#: Ranking is a name comparison, so it uses the same bound as FR-023's name matching rather
#: than inventing a second one. Beyond this a candidate is not a spelling variant.
_RANK_DISTANCE_CEILING = 6


class IdentificationSource(StrEnum):
    IDENTIFIED = "identified"
    #: FR-012b. Reported and distinguishable, exactly as a manual card resolution is
    #: (SC-009a) — a user who corrected the tool should be able to see that they did.
    USER_SELECTED = "user_selected"


@dataclass(frozen=True)
class PackCandidate:
    pack_code: str
    pack_name: str
    #: Name similarity only, 0..1. Ranking evidence, never the confidence figure — that one
    #: rests on card data and is a different measurement entirely.
    score: float

    def to_json(self) -> dict[str, Any]:
        return {"pack_code": self.pack_code, "pack_name": self.pack_name, "score": self.score}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> PackCandidate:
        return cls(payload["pack_code"], payload["pack_name"], payload["score"])


@dataclass(frozen=True)
class Verification:
    """How much of the folder one candidate pack explains."""

    pack_code: str
    pack_name: str
    matched_cards: int
    interpretable_files: int
    evidence: tuple[str, ...] = ()

    @property
    def confidence(self) -> float:
        if not self.interpretable_files:
            return 0.0
        return self.matched_cards / self.interpretable_files


@dataclass(frozen=True)
class Identification:
    """What the tool believes about this folder, and what it is resting that on."""

    pack_code: str | None
    pack_name: str | None
    source: IdentificationSource = IdentificationSource.IDENTIFIED
    confidence: float = 0.0
    matched_cards: int = 0
    interpretable_files: int = 0
    evidence: tuple[str, ...] = ()
    candidates: tuple[PackCandidate, ...] = field(default_factory=tuple)

    @property
    def confident(self) -> bool:
        """Whether there is a pack to propose.

        A user-selected pack is confident by definition: the measurement exists to decide
        whether to *ask*, and the user has already answered.
        """
        return self.pack_code is not None

    def select(self, pack_code: str, pack_name: str) -> Identification:
        """Record the user's own choice (FR-012b), keeping what was measured about the folder.

        The rejected measurement is deliberately retained. A run whose report says "matched
        62% against `cap`, user selected `thor`" is the record SC-009a asks for; overwriting
        it would erase the fact that the tool and the user disagreed.
        """
        return Identification(
            pack_code=pack_code,
            pack_name=pack_name,
            source=IdentificationSource.USER_SELECTED,
            confidence=self.confidence,
            matched_cards=self.matched_cards,
            interpretable_files=self.interpretable_files,
            evidence=(*self.evidence, f"Pack chosen by the user: {pack_name} ({pack_code})."),
            candidates=self.candidates,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "pack_code": self.pack_code,
            "pack_name": self.pack_name,
            "source": self.source.value,
            "confidence": self.confidence,
            "matched_cards": self.matched_cards,
            "interpretable_files": self.interpretable_files,
            "evidence": list(self.evidence),
            "candidates": [c.to_json() for c in self.candidates],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> Identification:
        return cls(
            pack_code=payload.get("pack_code"),
            pack_name=payload.get("pack_name"),
            source=IdentificationSource(payload.get("source", "identified")),
            confidence=payload.get("confidence", 0.0),
            matched_cards=payload.get("matched_cards", 0),
            interpretable_files=payload.get("interpretable_files", 0),
            evidence=tuple(payload.get("evidence") or ()),
            candidates=tuple(PackCandidate.from_json(c) for c in payload.get("candidates") or ()),
        )


def folder_hero_key(hero_folder: str) -> str:
    """The normalised hero name a folder announces.

    `Heros/Kamala Khan_Ms.Marvel` → `msmarvel`. Three transformations, each earning its keep
    against the real library: take the segment after the last `_` because the library writes
    `<alter ego>_<hero>` and the alter ego is not a pack; drop a trailing `(u)`/`(ns)` because
    it marks the scan rather than the hero; and strip non-alphanumerics because the library
    writes `Ms.Marvel` for "Ms. Marvel" and `Wonderman` for "Wonder Man".
    """
    name = Path(hero_folder).name
    name = name.rsplit("_", 1)[-1]
    name = _TRAILING_MARKER_RE.sub("", name)
    return normalise(name)


def rank_packs(
    hero_folder: str,
    pack_index: Sequence[PackIndexEntry],
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[PackCandidate]:
    """Rank the pack index against the folder's name. Offline, and makes no request.

    An exact normalised match scores 1.0 and is the common case — all ten acceptance heroes
    reach their pack this way. Everything else degrades by edit distance, which is what keeps
    a misspelled or abbreviated folder from ranking nothing at all.
    """
    key = folder_hero_key(hero_folder)
    if not key:
        return []

    scored: list[PackCandidate] = []
    for entry in pack_index:
        target = normalise(entry.name)
        if not target:
            continue
        if key == target:
            score = 1.0
        else:
            distance = edit_distance(key, target, ceiling=_RANK_DISTANCE_CEILING)
            if distance > _RANK_DISTANCE_CEILING:
                continue
            # Normalised by the longer name so a two-edit difference counts for more on a
            # short pack name than on a long one.
            score = max(0.0, 1.0 - distance / max(len(key), len(target)))
        scored.append(PackCandidate(entry.code, entry.name, score))

    # Sorted by code as well as score so equal scores rank deterministically (Principle V).
    scored.sort(key=lambda c: (-c.score, c.pack_code))
    return scored[:limit]


#: Forms that could in principle name a pack card. `UNPARSEABLE` cannot — it is FR-032's
#: report, not a card — and `DECKLIST` must not: the decklist is not one of the pack's cards
#: (FR-013b), so counting it would penalise the eight acceptance heroes whose folder holds
#: one for possessing a file that can never match by construction.
_INTERPRETABLE_FORMS = frozenset(
    {Form.POSITION, Form.POSITION_SET, Form.COPY_NUMBER, Form.NO_NUMBER}
)


def verify(
    pack_code: str,
    pack_name: str,
    cards: Sequence[PackCard],
    index: LibraryIndex,
    hero_folder: str,
) -> Verification:
    """Measure how much of the hero folder this pack's cards explain.

    The figure is the share of *interpretable* files in the folder whose filename matches the
    canonical name of some card in the pack. Files matching none of the library's conventions
    are excluded rather than counted as failures: they are FR-032's report and say nothing
    about whether the pack is right.

    **Name agreement only, deliberately.** data-model.md originally specified "by position or
    name"; measuring it in T042 showed position agreement carries no signal at all here.
    Every hero pack numbers its cards from 1, so every hero folder's positions match every
    hero pack's positions — Star-Lord's folder verifies 100% against Thor on positions alone,
    which is precisely the confident-and-wrong identification FR-011 exists to prevent. Names
    separate the same case completely: 0.87-1.00 for the right pack, 0.00-0.65 for a wrong
    one. Position agreement is still *reported*, because it is meaningful corroboration for a
    human reading the evidence; it just does not move the number.

    Matching here is deliberately looser than FR-020's resolution cascade. This answers "is
    this the right pack", where a file matching *any* card is evidence; the cascade answers
    "which file is this specific card", where it must be exactly one.
    """
    entries = [e for e in index.files_in(hero_folder) if e.parsed.form in _INTERPRETABLE_FORMS]
    if not entries:
        return Verification(pack_code, pack_name, 0, 0, ())

    positions = {c.position for c in cards}
    positional = hero_folder not in index.copy_counting_folders
    names = [(c, normalise(c.name)) for c in cards]

    matched_refs: set[str] = set()
    matched_names: list[str] = []
    corroborating_positions = 0

    for entry in entries:
        hit = _first_name_hit(entry.parsed.name_keys, names)
        if hit is None:
            continue
        matched_refs.add(entry.ref)
        matched_names.append(hit.name)
        if positional and entry.parsed.position is not None and entry.parsed.position in positions:
            corroborating_positions += 1

    evidence = _evidence(
        pack_name, len(matched_refs), len(entries), corroborating_positions, matched_names
    )
    return Verification(pack_code, pack_name, len(matched_refs), len(entries), evidence)


def _first_name_hit(
    name_keys: frozenset[str], names: Sequence[tuple[PackCard, str]]
) -> PackCard | None:
    """The first pack card whose canonical name one of this file's keys matches.

    Directional, like `filenames.matches_name`: the pack supplies the names and the filename
    is tested against them. Asking what card a filename names is what FR-023 forbids.
    """
    from marchamp.library.filenames import distance_limit

    for card, target in names:
        if not target:
            continue
        limit = distance_limit(target)
        for key in name_keys:
            if edit_distance(key, target, ceiling=limit) <= limit:
                return card
    return None


def _evidence(
    pack_name: str,
    matched: int,
    total: int,
    corroborating_positions: int,
    matched_names: Sequence[str],
) -> tuple[str, ...]:
    """What the figure rests on, in the user's terms (FR-012).

    A bare percentage is not something a user can check; a named card is. Nothing here
    carries a path — evidence reaches both the wizard and the run's log, and FR-009 forbids
    retaining any path from outside the named library root.
    """
    share = (matched / total * 100) if total else 0.0
    lines = [
        f"{matched} of {total} interpretable files in this folder are named after a card in "
        f"{pack_name} ({share:.0f}%).",
    ]
    if corroborating_positions:
        lines.append(
            f"{corroborating_positions} of those also sit at the position that card holds "
            "in the pack."
        )
    if matched_names:
        # A handful, sorted, so the same folder always shows the same evidence.
        sample = sorted(dict.fromkeys(matched_names))[:5]
        lines.append("Cards found include: " + ", ".join(sample) + ".")
    return tuple(lines)


def identify(
    hero_folder: str,
    index: LibraryIndex,
    pack_index: Sequence[PackIndexEntry],
    load_cards: Callable[[str], Sequence[PackCard]],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_matched_cards: int = DEFAULT_MIN_MATCHED_CARDS,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> Identification:
    """Rank, verify the top candidate, and decide whether to propose it.

    `load_cards` is passed in rather than a `SnapshotStore` taken as a dependency, so this
    module stays a reader of the library with no opinion about caching, freshness, or the
    network — and so a test can count exactly how many packs were asked about.
    """
    candidates = tuple(rank_packs(hero_folder, pack_index, limit=candidate_limit))
    if not candidates:
        return Identification(None, None, candidates=())

    top = candidates[0]
    result = verify(top.pack_code, top.pack_name, load_cards(top.pack_code), index, hero_folder)

    if result.confidence < min_confidence or result.matched_cards < min_matched_cards:
        # Refused, but not ended. FR-012b: the candidate list is what makes this a prompt.
        return Identification(
            pack_code=None,
            pack_name=None,
            confidence=result.confidence,
            matched_cards=result.matched_cards,
            interpretable_files=result.interpretable_files,
            evidence=(
                *result.evidence,
                f"Not confident enough to propose {top.pack_name} "
                f"({result.confidence:.0%} against a {min_confidence:.0%} threshold, "
                f"{result.matched_cards} cards matched against {min_matched_cards} required). "
                "Choose the pack below.",
            ),
            candidates=candidates,
        )

    return Identification(
        pack_code=top.pack_code,
        pack_name=top.pack_name,
        source=IdentificationSource.IDENTIFIED,
        confidence=result.confidence,
        matched_cards=result.matched_cards,
        interpretable_files=result.interpretable_files,
        evidence=result.evidence,
        candidates=candidates,
    )
