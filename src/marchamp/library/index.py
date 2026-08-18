"""The library index (FR-013d, FR-020, FR-021, FR-031, research R5, R13).

One `os.walk` of the whole library at the start of a resolve pass, held for that pass only,
**never persisted**. Persisting it would create a second source of truth that goes stale the
moment the user adds a scan, and a resumed run must see the library as it is *now* — going
away to find a missing file is the entire reason resuming exists (FR-026b). One pass over
~4,447 `os.scandir` entries costs tens of milliseconds against a ~49 s render, so there is
nothing to buy.

Two lookups answering two different questions:

**By position**, keyed on `(pack_hint, position, face suffix)`. The hint is the containing
hero folder and is **absent under `Aspects/`**, where a position means nothing because there
is no pack to read it against — which is exactly why the name index is not optional.

**By name**, keyed on normalised filename fragments and consulted only when the caller
already knows the canonical name it wants (FR-023). It carries Phoenix and Wonder Man
entirely, because those folders number by physical copy and contribute no positions at all.

The rule doing the most work is that **ambiguity is reported, never resolved by picking.**
Two files claiming one position is an FR-033 conflict naming both sides; two files inside
the edit-distance bound of one card is the same thing. Choosing between them would pair a
card with confidently wrong art, and the user is right there to be asked (FR-026). The one
exception is FR-034's duplicate rendition — a `.tif`/`.tiff` pair of a single card — where
the choice is deterministic and the duplication is still reported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from marchamp.library.filenames import (
    IMAGE_SUFFIXES,
    Form,
    ParsedFilename,
    detect_copy_counting,
    matches_name,
    parse_filename,
)

#: Positions there mean nothing without a pack, so no hint is recorded (research R13).
ASPECTS_DIRNAME = "Aspects"

#: Matches `config.Limits.library_scan_files`. Passed in rather than imported so this module
#: stays a pure reader with no opinion about configuration.
DEFAULT_FILE_CAP = 50_000


class LibraryScanTooLarge(Exception):
    """The walk hit its ceiling.

    Almost always a mistyped library root — `/` or a home directory — and stopping is much
    kinder than indexing a filesystem and then failing to find any cards in it.
    """


@dataclass(frozen=True)
class LibraryEntry:
    #: Relative to the library root, always. FR-009 forbids retaining anything else.
    ref: str
    filename: str
    folder: str
    #: The containing hero folder, or None under `Aspects/`.
    pack_hint: str | None
    parsed: ParsedFilename


@dataclass(frozen=True)
class Candidates:
    """What the index found. Deliberately not "the answer"."""

    entries: tuple[LibraryEntry, ...] = ()

    @property
    def _by_card(self) -> dict[str, list[LibraryEntry]]:
        """Grouped by which card each file is a scan of, not by filename.

        This is what separates FR-034 from FR-033. Three files for one card in a
        copy-counting folder, and a `.tif`/`.tiff` pair, are one card in several renditions;
        two files a single edit apart from one name are two cards claiming one key.
        """
        grouped: dict[str, list[LibraryEntry]] = {}
        for entry in self.entries:
            grouped.setdefault(entry.parsed.card_identity, []).append(entry)
        return grouped

    @property
    def conflict(self) -> bool:
        """Two *different* cards claiming one key (FR-033). Never resolved here."""
        return len(self._by_card) > 1

    @property
    def chosen(self) -> LibraryEntry | None:
        """The one file to use, or None when there is nothing or too much.

        `None` on a conflict is the point: the caller reports both sides and asks. Among
        renditions of a single card the pick is deterministic — sorted by filename, so the
        same library always yields the same PDF (Principle V, FR-005j).
        """
        grouped = self._by_card
        if len(grouped) != 1:
            return None
        (only,) = grouped.values()
        return sorted(only, key=lambda e: e.filename)[0]

    @property
    def duplicate_renditions(self) -> tuple[LibraryEntry, ...]:
        """The `.tif`/`.tiff` siblings not chosen (FR-034). Reported, never a failure."""
        chosen = self.chosen
        if chosen is None:
            return ()
        return tuple(
            e
            for e in self.entries
            if e is not chosen and e.parsed.card_identity == chosen.parsed.card_identity
        )


@dataclass
class LibraryIndex:
    root: Path
    entries: list[LibraryEntry] = field(default_factory=list)
    #: Folders whose numbers count physical copies, so they contribute no positions.
    copy_counting_folders: set[str] = field(default_factory=set)
    _by_position: dict[tuple[str | None, int, str | None], list[LibraryEntry]] = field(
        default_factory=dict
    )
    #: The same positions, keyed *without* a pack hint. `_by_position` answers "position 16 in
    #: this pack's folder"; this answers "position 16 anywhere", which the caller then narrows
    #: by folder or by the name of the specific card it is looking for. Two lookups need it
    #: and neither can use `_by_position`: FR-021's whole-library search has no hint to give,
    #: and FR-022's reprint knows a position in a *different* pack whose folder it cannot name.
    _by_any_position: dict[tuple[int, str | None], list[LibraryEntry]] = field(default_factory=dict)
    _by_name: dict[str, list[LibraryEntry]] = field(default_factory=dict)
    _by_folder: dict[str, list[LibraryEntry]] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.entries)

    # ------------------------------------------------------------------- lookups

    def by_position(
        self, pack_hint: str | None, position: int, face_suffix: str | None = None
    ) -> Candidates:
        return Candidates(tuple(self._by_position.get((pack_hint, position, face_suffix), ())))

    def positions_under(
        self, folder: str | None, position: int, face_suffix: str | None = None
    ) -> Candidates:
        """Files at `position` inside `folder` **and its subfolders**, or anywhere if None.

        Subfolders are not a convenience. The nemesis set lives in one — `Steve Rogers_Captain
        America/Captain America Nemesis/` — so a lookup restricted to the named folder itself
        finds no nemesis card at all, and FR-015b requires every one of them. `by_position`
        keys on the *containing* folder and therefore cannot answer this; it stays as it is
        because FR-020's "inside `hero_folder`" is a subtree, not a directory listing.
        """
        found = self._by_any_position.get((position, face_suffix), ())
        if folder is None:
            return Candidates(tuple(found))
        prefix = f"{folder}/"
        return Candidates(
            tuple(e for e in found if e.folder == folder or e.folder.startswith(prefix))
        )

    def by_name(self, canonical_name: str) -> Candidates:
        """Every file whose normalised key is within the bound of this card's name (FR-023).

        Scanned rather than looked up, because the match is fuzzy: a dictionary hit would
        find only the exact spelling and the three typos this exists for are all misspelled.
        The keys number a few per file, so one pass over them is cheap against a render.
        """
        seen: dict[str, LibraryEntry] = {}
        for key, entries in self._by_name.items():
            if matches_name(key, canonical_name):
                for entry in entries:
                    seen.setdefault(entry.ref, entry)
        return Candidates(tuple(sorted(seen.values(), key=lambda e: e.ref)))

    # ---------------------------------------------------- reporting on one folder

    def files_in(self, folder: str) -> list[LibraryEntry]:
        """Every indexed file in the named folder.

        Bounded to that folder on purpose (FR-031 as amended). Read literally against
        FR-021's whole-library search, per-file accounting would demand naming 4,447 files
        in one hero's report — unreadable for the user and untestable as SC-004. The harm it
        exists to prevent is a scan sitting in the folder the user pointed at, ignored.
        """
        return list(self._by_folder.get(folder, ()))

    def files_under(self, folder: str) -> list[LibraryEntry]:
        """Every indexed file in the named folder **and its subfolders**.

        The unit FR-031's accounting is done in, and deliberately not `files_in`. The hero
        folder is a subtree: Captain America's nemesis set lives in `Captain America
        Nemesis/` beneath it, so an accounting that stopped at the top-level listing would
        leave five cards' worth of files unexplained while still reporting full coverage of
        what it chose to look at.

        Ordered by ref so the report reads the same way twice (Principle V).
        """
        prefix = f"{folder}/"
        return sorted(
            (e for e in self.entries if e.folder == folder or e.folder.startswith(prefix)),
            key=lambda e: e.ref,
        )

    def decklist_candidates(self, folder: str) -> list[LibraryEntry]:
        """Files in the named folder whose stem contains `deck\\s*list` (FR-013d)."""
        return [e for e in self.files_in(folder) if e.parsed.form is Form.DECKLIST]

    def unparseable(self, folder: str) -> list[LibraryEntry]:
        """Files under the named folder matching none of the three conventions (FR-032).

        The subtree, for the same reason `files_under` is: a junk filename sitting in the
        nemesis subfolder is inside the folder the user pointed at, and FR-032 is about
        exactly that.

        A decklist scan matches none of them either and is excluded by `parse_filename`
        classifying it first — without that it would be a false fault on eight of the ten
        acceptance heroes.
        """
        return [e for e in self.files_under(folder) if e.parsed.form is Form.UNPARSEABLE]


def _pack_hint(folder: str) -> str | None:
    """The containing hero folder, or None under `Aspects/` (research R13)."""
    parts = Path(folder).parts
    return None if ASPECTS_DIRNAME in parts else folder


def build_index(root: Path, file_cap: int = DEFAULT_FILE_CAP) -> LibraryIndex:
    """Walk the library once and build the pass's index.

    `os.walk` rather than `find`: BSD `find` does not traverse the Drive mount this library
    lives on, measured 2026-08-17 (research R13).
    """
    root = Path(root)
    index = LibraryIndex(root=root)

    per_folder: dict[str, list[str]] = {}
    seen = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        folder = str(Path(dirpath).relative_to(root))
        folder = "" if folder == "." else folder
        images = sorted(f for f in filenames if Path(f).suffix.lower() in IMAGE_SUFFIXES)
        if not images:
            continue
        seen += len(images)
        if seen > file_cap:
            raise LibraryScanTooLarge(
                f"more than {file_cap} images under {root}. This is almost always a "
                "mistyped library root; indexing a whole filesystem and then finding no "
                "cards in it is a worse outcome than stopping here."
            )
        per_folder[folder] = images

    for folder, filenames in per_folder.items():
        # Per folder, because one filename cannot say which convention it is in (R5).
        copy_counting = detect_copy_counting(filenames)
        if copy_counting:
            index.copy_counting_folders.add(folder)
        hint = _pack_hint(folder)

        for filename in filenames:
            parsed = parse_filename(filename)
            entry = LibraryEntry(
                ref=f"{folder}/{filename}" if folder else filename,
                filename=filename,
                folder=folder,
                pack_hint=hint,
                parsed=parsed,
            )
            index.entries.append(entry)
            index._by_folder.setdefault(folder, []).append(entry)

            # A position is recorded only when it is one. In a copy-counting folder the
            # number is a copy index, and a wrong answer is worse than none (R5).
            if parsed.position is not None and not copy_counting:
                index._by_any_position.setdefault((parsed.position, parsed.face_suffix), []).append(
                    entry
                )
                if hint is not None:
                    key = (hint, parsed.position, parsed.face_suffix)
                    index._by_position.setdefault(key, []).append(entry)

            for name_key in parsed.name_keys:
                index._by_name.setdefault(name_key, []).append(entry)

    return index
