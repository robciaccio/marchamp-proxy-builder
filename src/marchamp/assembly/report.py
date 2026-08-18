"""What the run tells the user about itself (FR-015e, FR-018, SC-002b, SC-006j).

FR-015d packs the four groups into as few pages as will hold them with **no page break
between them**, so a printed page routinely carries the last player cards and the first
nemesis cards. That makes the report — not the layout — the thing that tells the groups
apart, and the thing a user sorts a stack of cut cards by without recognising the cards on
sight (FR-015e, SC-002b).

It lives on the run record rather than only in the response that produced it, so an
incomplete pack is still legible as incomplete on a later visit (FR-030b).

**Every section is filled from what the run already holds**, never from a second walk of
anything. The resolutions say what was found and how; the pass's `LibraryIndex` says what was
in the folder; the unresolved faces say what was not found and where the tool looked. The
report is a projection of those three, which is what makes it reproducible for the same
inputs (Principle V).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from marchamp.assembly.catalog import BuiltCatalog
from marchamp.assembly.decklist import DecklistState
from marchamp.assembly.faces import Group, card_count
from marchamp.assembly.resolve import Provenance, Resolution, UnresolvedFace
from marchamp.assets.store import Store
from marchamp.layout.geometry import SLOT_SIZE_MM
from marchamp.library.index import Candidates, LibraryIndex
from marchamp.render.images import (
    MIN_DPI,
    FitMode,
    ImageTooSmall,
    ImageUnreadable,
    validate_source,
)
from marchamp.upstream.models import PackCard


@dataclass
class AssemblyReport:
    pack_code: str | None = None
    pack_name: str | None = None
    pack_source: str = "identified"
    snapshot_revision: str | None = None
    snapshot_stale: bool = False
    #: FR-018's comparison, **in cards** — a double-sided card is one card and two faces.
    #: No expected total is asserted and none is warned on: pack sizes vary, and the
    #: pre-built decks this feature was respecified around measured 40, 41, and 42.
    cards_printed: int = 0
    cards_in_pack: int = 0
    faces_printed: int = 0
    page_count: int | None = None
    #: SC-006j — a pack printed without a decklist card is never indistinguishable from one
    #: printed with it.
    decklist_printed: bool = False
    #: Where to get one when the folder held none (FR-013c). Shown, never fetched.
    decklist_source_url: str | None = None
    resolutions: list[dict[str, Any]] = field(default_factory=list)
    #: Every card printed *without* (FR-030, FR-030b). Never also in `resolutions`: a card
    #: the user chose to print without resolved to nothing, and listing it in both would
    #: leave the report contradicting itself.
    omitted: list[dict[str, Any]] = field(default_factory=list)
    unused_files: list[dict[str, Any]] = field(default_factory=list)
    uninterpretable_files: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    low_resolution: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "pack_code": self.pack_code,
            "pack_name": self.pack_name,
            "pack_source": self.pack_source,
            "snapshot_revision": self.snapshot_revision,
            "snapshot_stale": self.snapshot_stale,
            "cards_printed": self.cards_printed,
            "cards_in_pack": self.cards_in_pack,
            "faces_printed": self.faces_printed,
            "page_count": self.page_count,
            "decklist_printed": self.decklist_printed,
            "decklist_source_url": self.decklist_source_url,
            "resolutions": self.resolutions,
            "omitted": self.omitted,
            "unused_files": self.unused_files,
            "uninterpretable_files": self.uninterpretable_files,
            "conflicts": self.conflicts,
            "low_resolution": self.low_resolution,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> AssemblyReport:
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


def _entry(resolution: Resolution, group_of: dict[str, Group]) -> dict[str, Any]:
    """One resolution as the contract's `Resolution` object.

    `file` is the uploaded file's **own name** when there is one, never the digest the run
    stores it under: the user chose that file and has to recognise it a week later (FR-027,
    FR-029, SC-006c). A card printed without has no file at all, and says so with an empty
    string rather than a plausible-looking path.
    """
    return {
        "card_code": resolution.card_code,
        "card_name": resolution.card_name,
        "side": resolution.side.value,
        "group": group_of.get(resolution.card_code, Group.PLAYER).value,
        "provenance": resolution.provenance.value,
        "source": resolution.source.value,
        "file": resolution.original_filename or resolution.ref,
        "note": resolution.note,
    }


def _sorted(resolutions: Sequence[Resolution]) -> list[Resolution]:
    """Card then side, so the same run always renders the same report (Principle V)."""
    return sorted(resolutions, key=lambda r: (r.card_code, r.side.value))


#: Why a file in the hero folder went unused. Each sentence names something the user can do
#: about it, or says plainly that there is nothing to do — "unused" on its own is a fact
#: they cannot act on (FR-031, FR-037).
UNINTERPRETABLE_REASON = (
    "its filename matches none of the three conventions this library uses, so no card "
    "could be looked up from it"
)
COPY_COUNTED_REASON = (
    "this folder numbers physical copies rather than card positions, so no position could "
    "be read from this file"
)
UNMATCHED_REASON = "no card in this pack resolved to it"


def _low_resolution(
    store: Store, resolutions: Sequence[Resolution], fit_mode: FitMode
) -> list[dict[str, Any]]:
    """Scans that cannot print at the required resolution — a warning, never a refusal.

    **The difference from feature 001 is deliberate** (FR-035 against FR-010). 001 renders a
    catalog someone authored, so an under-resolution image is a mistake to fix and refusing
    is right. This feature reads a library someone else organised and scanned once: refusing
    would make a whole pack unprintable over a single soft scan the user cannot re-take, and
    they are entitled to decide a slightly soft card is fine. So the same check runs and its
    verdict is downgraded to a sentence.

    The floor comes from `render.images` rather than being restated here. A second threshold
    would drift from the one the renderer enforces, and the report would then disagree with
    the document about the same file.

    An undecodable source lands here too. It is not low resolution and says so in its own
    words, but the contract has no other section for it and building the report must not
    raise — a corrupt scan is something to report, not something that replaces the whole
    report with a stack trace (FR-037).
    """
    slot_w, slot_h = SLOT_SIZE_MM
    warnings: list[dict[str, Any]] = []
    for resolution in _sorted(resolutions):
        try:
            validate_source(store, resolution.ref, slot_w, slot_h, fit_mode)
        except ImageTooSmall as exc:
            warnings.append(
                {
                    "file": resolution.original_filename or resolution.ref,
                    "reason": (
                        f"{resolution.card_name} ({resolution.card_code}): {exc}. It will "
                        f"print, softer than {MIN_DPI} DPI."
                    ),
                }
            )
        except ImageUnreadable as exc:
            warnings.append(
                {
                    "file": resolution.original_filename or resolution.ref,
                    "reason": (
                        f"{resolution.card_name} ({resolution.card_code}): this file "
                        f"resolved to this card but could not be read as an image ({exc})."
                    ),
                }
            )
    return warnings


def _position_groups(index: LibraryIndex, hero_folder: str) -> dict[Any, Candidates]:
    """The hero folder's files grouped exactly as a position lookup would see them.

    Keyed on `(position, face suffix)`, skipping files with no position and folders whose
    numbers count physical copies — mirroring `_by_any_position`, because a conflict this
    reports that the resolver never sees is a false alarm, and one it sees that this misses
    is a silent failure.
    """
    grouped: dict[Any, list[Any]] = {}
    for entry in index.files_under(hero_folder):
        if entry.parsed.position is None or entry.folder in index.copy_counting_folders:
            continue
        grouped.setdefault((entry.parsed.position, entry.parsed.face_suffix), []).append(entry)
    # Sorted on the suffix as text, because one position routinely carries both a suffixed
    # and an unsuffixed file — Vision's `_2` and `_2b` — and `None` will not compare with a
    # string.
    return {
        key: Candidates(tuple(entries))
        for key, entries in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))
    }


def _cards_lost_to(unresolved: Sequence[UnresolvedFace]) -> dict[str, list[str]]:
    """Which cards each conflicting file cost, keyed by file.

    "Position 5 is claimed by two different cards" is half an answer. The other half is
    which card the user is now missing because of it — without that they have to work back
    from a position number to a card themselves, which means opening the card data, which
    is the thing the report exists to save them (FR-037, SC-008).
    """
    lost: dict[str, list[str]] = {}
    for face in unresolved:
        for ref in face.conflict:
            label = f"{face.card_name} ({face.card_code})"
            if label not in lost.setdefault(ref, []):
                lost[ref].append(label)
    return lost


def _conflicts(
    index: LibraryIndex,
    hero_folder: str,
    decklist: DecklistState | None,
    unresolved: Sequence[UnresolvedFace] = (),
) -> list[dict[str, Any]]:
    """Position conflicts naming both sides, and duplicate renditions naming the pick.

    Two things that look alike and are not (FR-033 against FR-034), and collapsing them
    would either refuse every `.tif`/`.tiff` pair in the library or resolve genuine
    conflicts by guessing:

    - **Two different cards at one key** is a conflict. Nothing picks between them; the
      user is right there to be asked, and a resolver that guessed would pair a card with
      confidently wrong art and be silent about it.
    - **One card in several renditions** is a duplicate. The pick is by filename order so
      the same library always yields the same PDF, and the ones not picked are still named.

    Derived from the index rather than from the failed resolutions, so a conflict at a
    position this pack has no card for is still reported — the user's folder is wrong
    whether or not this particular run tripped over it.
    """
    out: list[dict[str, Any]] = []
    lost = _cards_lost_to(unresolved)
    for (position, suffix), candidates in _position_groups(index, hero_folder).items():
        at = f"position {position}{suffix or ''}"
        if candidates.conflict:
            for entry in sorted(candidates.entries, key=lambda e: e.ref):
                others = sorted(e.ref for e in candidates.entries if e.ref != entry.ref)
                cost = lost.get(entry.ref, [])
                out.append(
                    {
                        "file": entry.ref,
                        "reason": (
                            f"{at} is claimed by {len(candidates.entries)} different cards; "
                            f"also {', '.join(others)}. Neither was used — nothing here "
                            f"picks between two cards."
                            + (
                                f" This is why {', '.join(cost)} could not be resolved."
                                if cost
                                else ""
                            )
                        ),
                    }
                )
            continue
        chosen = candidates.chosen
        for entry in sorted(candidates.duplicate_renditions, key=lambda e: e.ref):
            out.append(
                {
                    "file": entry.ref,
                    "reason": (
                        f"a duplicate rendition of the same card at {at}; "
                        f"{chosen.ref if chosen else ''} is the one this run uses"
                    ),
                }
            )

    if decklist is not None and decklist.conflict:
        # The decklist is matched by a substring rather than by position, so it cannot come
        # out of the grouping above — but two different scans claiming to be the deck list
        # is the same FR-033 problem and is resolved the same way: by asking.
        refs = sorted(c.ref for c in decklist.candidates)
        for ref in refs:
            others = [other for other in refs if other != ref]
            out.append(
                {
                    "file": ref,
                    "reason": (
                        "more than one file in this folder looks like the deck list; "
                        f"also {', '.join(others)}. Choose which one to print."
                    ),
                }
            )
    return out


def _why_unused(
    entry: Any,
    index: LibraryIndex,
    used_by_identity: dict[str, str],
    conflicted: dict[str, str],
) -> str:
    """The reason one file was not used, most specific first.

    Order matters. A conflict, a duplicate rendition and an uninterpretable name are all
    "unused", but they ask three different things of the user — pick one, nothing, or fix a
    filename — and leading with the general case would bury all three.
    """
    from marchamp.library.filenames import Form

    if entry.ref in conflicted:
        return conflicted[entry.ref]
    chosen = used_by_identity.get(entry.parsed.card_identity)
    if chosen is not None:
        # FR-034: one card, several renditions. The pick is deterministic and the ones not
        # picked are reported rather than silently dropped.
        return f"a duplicate rendition of the same card; {chosen} was used instead"
    if entry.parsed.form is Form.UNPARSEABLE:
        return UNINTERPRETABLE_REASON
    if entry.folder in index.copy_counting_folders:
        return COPY_COUNTED_REASON
    return UNMATCHED_REASON


def _file_accounting(
    index: LibraryIndex,
    hero_folder: str,
    used_refs: set[str],
    used_by_identity: dict[str, str],
    conflicted: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every file under the hero folder, either used or named as unused with why.

    **Bounded to the hero folder on purpose** (FR-031 as amended). Read literally against
    FR-021's whole-library search this would demand naming 4,447 files that were never
    candidates for this pack — a report no user can read and a criterion no test can
    assert. The harm it exists to prevent is a scan sitting ignored in the folder the user
    pointed at, and that harm is bounded to that folder.

    An uninterpretable file appears in **both** lists, and that is not an oversight: FR-031
    requires every unused file named with a reason, and FR-032 requires uninterpretable
    names called out specifically. One of the two would otherwise have to be read as
    implying the other.
    """
    unused: list[dict[str, Any]] = []
    uninterpretable: list[dict[str, Any]] = []
    for entry in index.files_under(hero_folder):
        if entry.ref in used_refs:
            continue
        unused.append(
            {
                "file": entry.ref,
                "reason": _why_unused(entry, index, used_by_identity, conflicted),
            }
        )
    for entry in index.unparseable(hero_folder):
        if entry.ref in used_refs:
            continue
        uninterpretable.append({"file": entry.ref, "reason": UNINTERPRETABLE_REASON})
    return unused, uninterpretable


def build_report(
    pack_code: str | None,
    pack_name: str | None,
    pack_source: str,
    cards: Sequence[PackCard],
    resolutions: Sequence[Resolution],
    built: BuiltCatalog | None,
    decklist: DecklistState | None,
    snapshot_revision: str | None,
    snapshot_stale: bool = False,
    page_count: int | None = None,
    *,
    index: LibraryIndex | None = None,
    hero_folder: str = "",
    unresolved: Sequence[UnresolvedFace] = (),
    store: Store | None = None,
    fit_mode: FitMode = FitMode.CROP,
) -> AssemblyReport:
    """Assemble the report from what the run resolved.

    `cards_printed` counts what the *entries* say, not what the pack listing says, so a run
    that omitted a card reports fewer than `cards_in_pack` rather than claiming the pack is
    complete. The decklist is excluded from both, because it is not one of the pack's cards
    (FR-013b, FR-018).

    The keyword-only arguments are what the library sections need and nothing else does.
    They are optional so a caller that only wants the counts — a test, or a run that has not
    resolved yet — is not forced to build an index it has no use for; when they are absent
    the sections they feed are empty rather than wrong.
    """
    # Counted off what was actually built rather than off the pack listing, so a run short
    # of three cards reports being short of three cards. Both units are reported and
    # neither substitutes for the other: `faces.card_count` is what the pack listing counts
    # in and what FR-018 compares against, while faces are what the page count follows from
    # (SC-002b). Ant-Man is the case that keeps them honest — one physical card, two
    # records, three faces.
    group_of = built.group_of if built else {}
    printed_cards = 0
    printed_faces = 0
    if built is not None:
        for entry in built.deck.entries:
            # Never one of the pack's cards, so it inflates neither count (FR-013b, FR-018).
            if group_of.get(entry.card_id) is Group.DECKLIST:
                continue
            card = built.catalog.card(entry.card_id)
            printed_cards += entry.quantity
            printed_faces += entry.quantity * (2 if card and card.double_sided else 1)

    # A card printed without is not a card printed. It appears in `omitted` and nowhere
    # else, so the two lists never disagree about the same card (FR-030b, SC-006e).
    printed = [r for r in resolutions if r.provenance is not Provenance.OMITTED]
    omitted = [r for r in resolutions if r.provenance is Provenance.OMITTED]

    unused_files: list[dict[str, Any]] = []
    uninterpretable_files: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    low_resolution = _low_resolution(store, printed, fit_mode) if store is not None else []
    if index is not None and hero_folder:
        used_refs = {r.ref for r in printed}
        # A file matched as the decklist was *used*, whether or not the user has decided
        # about it yet. Without this, every hero folder's decklist scan is reported as an
        # unexplained unused file in every run, for the whole library.
        if decklist is not None:
            used_refs |= {c.ref for c in decklist.candidates}
            if decklist.chosen_ref:
                used_refs.add(decklist.chosen_ref)
        used_by_identity = {
            e.parsed.card_identity: e.ref
            for e in index.files_under(hero_folder)
            if e.ref in used_refs
        }
        conflicts = _conflicts(index, hero_folder, decklist, unresolved)
        # One reason per file, first wins: a file on both sides of a position clash is
        # named as such rather than as "no card resolved to it", which is true but useless.
        conflicted = {}
        for entry in conflicts:
            conflicted.setdefault(entry["file"], entry["reason"])
        unused_files, uninterpretable_files = _file_accounting(
            index, hero_folder, used_refs, used_by_identity, conflicted
        )

    return AssemblyReport(
        pack_code=pack_code,
        pack_name=pack_name,
        pack_source=pack_source,
        snapshot_revision=snapshot_revision,
        snapshot_stale=snapshot_stale,
        cards_printed=printed_cards,
        cards_in_pack=card_count(cards),
        faces_printed=printed_faces,
        page_count=page_count,
        decklist_printed=bool(decklist and decklist.printed),
        # Offered whenever no decklist card is being printed, which is the only time the
        # user needs somewhere to go for one (FR-013c, SC-006j).
        decklist_source_url=(
            None
            if decklist and decklist.printed
            else (decklist.hall_of_heroes_url if decklist else None)
        ),
        resolutions=[_entry(r, group_of) for r in _sorted(printed)],
        omitted=[_entry(r, group_of) for r in _sorted(omitted)],
        unused_files=unused_files,
        uninterpretable_files=uninterpretable_files,
        conflicts=conflicts,
        low_resolution=low_resolution,
    )
