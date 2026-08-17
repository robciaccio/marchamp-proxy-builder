"""Parsing the scan library's filenames (FR-032, FR-033, FR-034, research R5, R12).

The library was organised by someone else and by three different conventions:

    A   {faction}_{Name}_{Type}_{position}          Leadership_Make the Call_Event_16.tiff
    B   ..._{position}_{set_position}.{set_total}   Wasp_Pym Particles_Resource_7_12.15.tiff
    C   {copy}_{Name}_{Type}                        2_Active Altruism_Event.tif

plus files with no number at all, and the decklist scan, which matches none of them.

**Form C is the one that matters.** A file with no number produces no answer, which the name
index then handles. A file whose *leading* number counts physical copies produces a *wrong*
answer: read as a position, `2_Active Altruism_Event.tif` confidently claims position 2.
Phoenix and Wonder Man number their entire hero sets that way, which is why detection is
per-folder — one filename in isolation cannot tell you which convention it is in.

**A suffix is evidence, never identity.** Vision's `_2a`/`_2b` are the two faces of the
single code `26002`; Captain America's `_1a`/`_1b` are the two distinct codes `03001a` and
`03001b` (research R12). Nothing in the filename distinguishes them, so this module reports
the suffix and refuses to interpret it — that decision belongs to the card data, and a
parser that guessed here would be wrong for one of the two cases every time.

**A name is never parsed *out* of a filename** (FR-023). What is produced is a set of
normalised keys, consulted only when looking for a card whose canonical MarvelCDB name is
already known. The direction matters: matching a known name against a filename is safe;
deciding what card a filename names is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

#: FR-013d. Both spellings occur in the real library and the hero's name in the filename is
#: deliberately not checked against the folder: `iceman deck list.tiff` sits under
#: `Bobby Drake_Iceman`, so requiring agreement would fail on the folders the rule serves.
DECKLIST_RE = re.compile(r"deck\s*list", re.IGNORECASE)

#: Form A's tail: a position, optionally with a face suffix. `_16`, `_1a`, `_1c`.
TRAILING_POSITION_RE = re.compile(r"_(\d{1,3})([a-z])?$", re.IGNORECASE)

#: Form B's tail: position, then the set numbering, whose `.15` reads as a file extension.
TRAILING_POSITION_SET_RE = re.compile(r"_(\d{1,3})_(\d{1,3})\.(\d{1,3})$")

#: Form C: the number leads. This is the structural signal; the folder check confirms it.
LEADING_COPY_RE = re.compile(r"^(\d{1,2})_")

#: Everything that is not a letter or a digit is noise the library varies: underscores
#: standing in for apostrophes, hyphens, double spaces, capitalisation.
_NOISE_RE = re.compile(r"[^0-9a-z]+")

#: Segments joined when building name keys. Three covers `Steve` + `s Apartament`, and any
#: more would start matching a faction to a type across the whole stem.
MAX_JOINED_SEGMENTS = 3

#: data-model.md § Library Index. Tightened for short names, where two edits can turn one
#: real card into another.
NAME_DISTANCE_LIMIT = 2
SHORT_NAME_LENGTH = 8
SHORT_NAME_DISTANCE_LIMIT = 1

IMAGE_SUFFIXES = frozenset({".tif", ".tiff", ".jpg", ".jpeg", ".png"})


class Form(StrEnum):
    POSITION = "position"
    POSITION_SET = "position_set"
    #: The number counts physical copies. **Never** a position.
    COPY_NUMBER = "copy_number"
    DECKLIST = "decklist"
    NO_NUMBER = "no_number"
    #: Matches none of the conventions. Reported when it sits in the folder the user named
    #: (FR-032); outside it, it surfaces only through a card that failed to resolve.
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class ParsedFilename:
    filename: str
    stem: str
    form: Form
    position: int | None = None
    face_suffix: str | None = None
    copy_number: int | None = None
    #: Which *card* this file is a scan of, as far as the filename can say. Two files share
    #: it when they are the same card: a `.tif`/`.tiff` pair (FR-034), and the three files
    #: a copy-counting folder holds for one card. It is what lets an index tell "one card,
    #: several files" apart from "two cards claiming one key", which is FR-033's whole
    #: distinction. Not an identity *claim* — it never says which MarvelCDB card this is.
    card_identity: str = ""
    #: Normalised candidate names, for the FR-023 lookup. Never an identity claim.
    name_keys: frozenset[str] = field(default_factory=frozenset)


def normalise(text: str) -> str:
    """Casefold and drop everything that is not a letter or a digit.

    Aggressive on purpose. The library varies punctuation, spacing, and capitalisation
    freely — `Steve_s Apartament` uses an underscore where the card uses an apostrophe — and
    none of that carries meaning. What survives is what identifies the card, and the
    remaining differences are genuine typos for the edit-distance bound to absorb.
    """
    return _NOISE_RE.sub("", text.casefold())


def edit_distance(a: str, b: str, ceiling: int = NAME_DISTANCE_LIMIT) -> int:
    """Levenshtein distance, abandoned once it exceeds `ceiling`.

    Called against every name key in an index built from ~4,447 files, and the exact value
    of a large distance is never wanted — only whether it is within the bound. Returns
    `ceiling + 1` to mean "further than you care about".
    """
    if a == b:
        return 0
    if abs(len(a) - len(b)) > ceiling:
        return ceiling + 1

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        if min(current) > ceiling:
            return ceiling + 1
        previous = current
    return previous[-1]


def distance_limit(canonical_normalised: str) -> int:
    """Two edits, tightened to one for short names.

    Two edits on a four-letter name reach a different card; on "Strength in Numbers" they
    barely reach the typo the library actually contains.
    """
    return (
        SHORT_NAME_DISTANCE_LIMIT
        if len(canonical_normalised) < SHORT_NAME_LENGTH
        else NAME_DISTANCE_LIMIT
    )


def matches_name(key: str, canonical: str) -> bool:
    """Whether a filename's key is the card whose canonical name this is (FR-023).

    Directional by design: the caller already knows which card it is looking for. Asking
    "what card does this filename name" is the question FR-023 forbids.
    """
    target = normalise(canonical)
    limit = distance_limit(target)
    return edit_distance(key, target, ceiling=limit) <= limit


def _stem(filename: str) -> str:
    """The filename without its image extension.

    Form B ends in `.15`, which looks exactly like an extension, so only known image
    extensions are stripped — and only one, so `scan notes.txt.tiff` keeps its `.txt`.
    """
    lowered = filename.lower()
    for suffix in IMAGE_SUFFIXES:
        if lowered.endswith(suffix):
            return filename[: -len(suffix)]
    return filename


def _name_keys(stem: str) -> frozenset[str]:
    """Candidate names: each underscore-separated segment, and short runs of adjacent ones.

    Runs are needed because the library sometimes writes one name with an underscore in it —
    `Steve_s Apartament` — so indexing segments alone would key it as "steve" and
    "sapartament", neither within edit distance of "Steve's Apartment".
    """
    segments = [s for s in stem.split("_") if s.strip()]
    keys: set[str] = set()
    for start in range(len(segments)):
        for length in range(1, MAX_JOINED_SEGMENTS + 1):
            if start + length > len(segments):
                break
            key = normalise("".join(segments[start : start + length]))
            # A bare number is not a name, and would otherwise match any short card name
            # that normalised to digits.
            if key and not key.isdigit():
                keys.add(key)
    whole = normalise(stem)
    if whole:
        keys.add(whole)
    return frozenset(keys)


def parse_filename(filename: str) -> ParsedFilename:
    """Classify one filename. Never decides what card it is."""
    stem = _stem(filename)
    keys = _name_keys(stem)

    identity = normalise(stem)

    if DECKLIST_RE.search(stem):
        # Checked first: a decklist scan matches no other convention, and without this it
        # would be reported as an uninterpretable file in the one folder where FR-031
        # demands every file be accounted for — on eight of the ten acceptance heroes.
        return ParsedFilename(filename, stem, Form.DECKLIST, card_identity=identity, name_keys=keys)

    leading = LEADING_COPY_RE.match(stem)
    if leading:
        # The leading number counts copies, so it is *not* part of the card's identity:
        # `2_`, `3_`, and `4_Active Altruism_Event` are three scans of one card, and an
        # index that read them as three different cards would report a conflict where
        # there is none.
        return ParsedFilename(
            filename,
            stem,
            Form.COPY_NUMBER,
            copy_number=int(leading.group(1)),
            card_identity=normalise(stem[leading.end() :]),
            name_keys=keys,
        )

    set_form = TRAILING_POSITION_SET_RE.search(stem)
    if set_form:
        return ParsedFilename(
            filename,
            stem,
            Form.POSITION_SET,
            position=int(set_form.group(1)),
            card_identity=identity,
            name_keys=keys,
        )

    positional = TRAILING_POSITION_RE.search(stem)
    if positional:
        return ParsedFilename(
            filename,
            stem,
            Form.POSITION,
            position=int(positional.group(1)),
            face_suffix=(positional.group(2) or "").lower() or None,
            card_identity=identity,
            name_keys=keys,
        )

    # Faction_Name_Type with no number: not an error, and name-matched only (R5). All
    # three parts are required — `IMG_0042` also has an underscore and is a camera's name
    # for a file, which FR-032 exists to report rather than to index as a card.
    segments = [s for s in stem.split("_") if s.strip()]
    if len([s for s in segments if not s.strip().isdigit()]) >= 3:
        return ParsedFilename(
            filename, stem, Form.NO_NUMBER, card_identity=identity, name_keys=keys
        )

    return ParsedFilename(filename, stem, Form.UNPARSEABLE, card_identity=identity, name_keys=keys)


def detect_copy_counting(filenames: list[str]) -> bool:
    """Whether this folder numbers by physical copy rather than by position (research R5).

    Per folder because a single filename cannot say. The signature measured in Phoenix and
    Wonder Man is one card appearing under several small leading numbers — three files for
    Active Altruism, numbered 2, 3, 4 — which positions never look like.

    Erring toward True is the safe direction. Its cost is falling back to name matching,
    which those two folders depend on anyway; the cost of the other mistake is a card paired
    with confidently wrong art.
    """
    parsed = [parse_filename(name) for name in filenames]
    leading = [p for p in parsed if p.form is Form.COPY_NUMBER]
    if not leading:
        return False

    positional = [p for p in parsed if p.form in (Form.POSITION, Form.POSITION_SET)]
    if not positional:
        # Nothing in the folder uses a trailing position, so the leading numbers are the
        # only numbering there is — and they are not positions.
        return True

    # A folder using both forms: decide on the signature rather than on the count.
    by_name: dict[str, set[int]] = {}
    for p in leading:
        rest = p.stem.split("_", 1)[1] if "_" in p.stem else p.stem
        by_name.setdefault(normalise(rest), set()).add(p.copy_number or 0)
    return any(len(numbers) > 1 for numbers in by_name.values())
