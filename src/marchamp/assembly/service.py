"""The assembly run's lifecycle (FR-012a, FR-026a, FR-026h, SC-009).

    identifying ──► awaiting_pack / unidentified ──► resolving
                                                       │
                                      ┌────────────────┴────────────────┐
                                      ▼                                 ▼
                                awaiting_cards ──────────────────────► ready
                                                                        │  FR-026a
                                                                        ▼
                                                                    rendering
                                                                        │
                                                             ┌──────────┴────────┐
                                                             ▼                   ▼
                                                         complete             failed

Three rules the transitions encode, each guarding a specific way of being wrong:

**Nothing resolves before the pack is confirmed** (FR-012a, SC-009). The failure the
confidence threshold structurally cannot catch is an identification that is confident *and
wrong* — a hero folder whose filenames genuinely match another pack — and its output is a
deck that is entirely plausible. Confirmation is therefore unconditional, not a formality
skipped when confidence is high.

**`ready` is not `complete`** (FR-026a). Reaching `ready` with every card resolved does not
print. A ~49 s render and a ~202 MB file are not something to start because a state machine
happened to arrive somewhere.

**`awaiting_pack` and `awaiting_cards` are not failures** (FR-036). `outcome` stays null
until the run is terminal, so "still going" is distinguishable from "finished badly".

**Reuse skips the render, never the resolve** (SC-006i). The FR-026h key is the pack, the
snapshot revision, and the identity of the images this run actually resolved — and the third
is content, so it cannot be known before resolving. The library root is deliberately not in
the key: a run whose folder moved but whose images are byte-identical still gets its PDF
(SC-006h).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from marchamp.assembly.catalog import build_catalog
from marchamp.assembly.decklist import DecklistDecision, DecklistState, find_decklist
from marchamp.assembly.faces import DECKLIST_CODE, Side, expand_pack
from marchamp.assembly.report import (
    build_report,
    decklist_entry,
    decklist_resolution,
    low_resolution_notes,
)
from marchamp.assembly.resolve import (
    USER_SUPPLIED,
    Provenance,
    Resolution,
    manual_resolution,
    omitted_resolution,
    resolve_pack,
)
from marchamp.assets.overlay import UPLOAD_PREFIX, OverlayStore
from marchamp.assets.store import AssetUnreadable
from marchamp.config import Settings
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import paginate
from marchamp.library.identify import Identification, identify, rank_packs
from marchamp.library.index import build_index
from marchamp.observability.logging import AssemblyRecord, write_record
from marchamp.render.document import FitMode, compose
from marchamp.store.layout import StateLayout
from marchamp.store.pdfs import PdfKind, PdfStore
from marchamp.store.runs import Outcome, RunRecord, RunState, RunStore
from marchamp.upstream.models import PackCard
from marchamp.upstream.snapshots import SnapshotStore

#: Matches `snapshots.REVISION_LENGTH`, and required by `StateLayout`'s `DIGEST16_RE`:
#: the identity is a path segment in the stored-PDF name, which *is* FR-026h's reuse key.
IDENTITY_LENGTH = 16


class AssemblyError(Exception):
    """A run cannot do what was asked of it. Carries a status so routes stay thin."""

    def __init__(self, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


class FolderRefused(AssemblyError):
    """FR-006: a named path is refused *specifically*, never as a generic 400."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status=400)


def _validate_paths(library_root: Path, hero_folder: str) -> tuple[Path, str]:
    """Check both named paths and say which one is wrong (FR-006, FR-007).

    Both are named by the caller and neither is configured in advance, so this is the
    containment boundary for the whole run — and "the folder you named is not inside the
    library you named" is a sentence the user can act on, where "400 Bad Request" is not.
    """
    root = Path(library_root).expanduser()
    if not root.is_absolute():
        raise FolderRefused(f"library_root must be an absolute path, got {library_root!r}")
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FolderRefused(f"library_root {library_root!r} cannot be read: {exc}") from exc
    if not root.is_dir():
        raise FolderRefused(f"library_root {library_root!r} is not a directory")

    relative = str(hero_folder).replace("\\", "/").strip("/")
    if not relative:
        raise FolderRefused("hero_folder must name a folder inside library_root")
    if ".." in relative.split("/"):
        raise FolderRefused(f"hero_folder {hero_folder!r} escapes library_root")

    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise FolderRefused(f"hero_folder {hero_folder!r} resolves outside library_root")
    if not target.is_dir():
        raise FolderRefused(f"hero_folder {hero_folder!r} is not a directory inside library_root")
    return root, relative


def output_identity(
    resolutions: Sequence[Resolution], page_size: str = "LETTER", fit_mode: str = "CROP"
) -> str:
    """The identity of the document a run would produce — the third part of FR-026h's key.

    Content, not paths. Two runs that resolved the same bytes share a PDF even if one of
    them read them from a folder that has since been renamed (SC-006h); a run where one card
    now resolves to different bytes rebuilds (SC-006k). The card code is hashed alongside the
    digest so swapping two cards' images is a different identity, not the same multiset.

    **Paper size and fit mode are part of it, and their absence was a bug** (found
    2026-08-20). This was `image_identity` and hashed the images alone, so a Letter/Crop
    document and an A4/Stretch document of the same pack shared one key: printing a pack
    twice with different settings silently served the first document back. The images are
    the same in both, which is exactly why hashing only the images could not tell them
    apart — and why nothing caught it until the wizard could ask for a second setting.

    The default arguments keep the pre-existing key stable for the overwhelmingly common
    Letter/Crop case, so already-stored documents are not orphaned by this change.
    """
    hasher = hashlib.sha256()
    for resolution in sorted(resolutions, key=lambda r: (r.card_code, r.side.value)):
        hasher.update(
            f"{resolution.card_code}:{resolution.side.value}:{resolution.content_digest}\n".encode()
        )
    if (page_size, fit_mode) != ("LETTER", "CROP"):
        # Appended only when it is not the default, so every document stored before this
        # change keeps the key it already has on disk.
        hasher.update(f"page_size={page_size}\nfit_mode={fit_mode}\n".encode())
    # Truncated to 16 hex, matching `compute_revision`. This value becomes a path segment in
    # `pdfs/standard/<pack>@<revision>@<identity>.pdf`, and `StateLayout` validates it as
    # exactly 16 hex characters — a full digest is refused there, so every standard PDF
    # would fail to store.
    return hasher.hexdigest()[:IDENTITY_LENGTH]


#: Report sections whose presence makes a completed run "assembled with warnings" rather
#: than "assembled cleanly" (FR-036). Each is something the user would want to know before
#: paying to print, and each is a thing they can act on.
#:
#: **Substitutions are deliberately not here.** Borrowing an image from another printing of
#: the same card is the *normal* path — `cap` sources eight physical cards from the Core Set
#: — so counting them would mark every real run as warned and leave the field meaning
#: nothing. Nor are unused files: every hero folder has some, and the report names them.
WARNING_SECTIONS = ("omitted", "low_resolution", "conflicts")


def outcome_for(state: RunState, report: dict[str, Any]) -> Outcome | None:
    """FR-036's machine-readable verdict, so a consumer need not parse prose.

    **Null until terminal**, which is the half that is easy to get wrong: a run awaiting
    confirmation of its pack or waiting on a card has not reached an outcome, and a consumer
    that read a missing one as a failure would tell the user their pack was refused when it
    is waiting for them.
    """
    if not state.terminal:
        return None
    if state is RunState.FAILED:
        return Outcome.REFUSED
    flagged = any(report.get(section) for section in WARNING_SECTIONS)
    return Outcome.WARNINGS if flagged else Outcome.CLEAN


def _apply_user_answers(record: RunRecord, outcome) -> tuple[list[Resolution], list]:
    """This pass's cascade, with the answers the user already gave laid over it (FR-026a).

    The library is re-read on every pass (FR-026b), so the cascade is run again each time a
    run advances — and it will report the same card missing again, because supplying a file
    for it did not put anything in the library. US4 scenario 8 is exactly that case: a run
    reporting two gaps, one of them answered, must ask only about the second and must keep
    every earlier resolution. That is what this does, and it is the reason a manual choice
    is stored on the run rather than folded into the resolutions and forgotten.

    An override wins for its `(card, side)` alone. Answering one face of a double-sided card
    leaves the other on whatever the cascade found, which is what makes `side` meaningful on
    the upload rather than decorative.
    """
    overrides = {
        (r["card_code"], r["side"]): Resolution.from_json(r)
        for r in record.resolutions
        if Provenance(r["provenance"]) in USER_SUPPLIED
    }
    if not overrides:
        return list(outcome.resolutions), list(outcome.unresolved)

    resolutions = [r for r in outcome.resolutions if (r.card_code, r.side.value) not in overrides]
    unresolved = [u for u in outcome.unresolved if (u.card_code, u.side.value) not in overrides]
    return [*resolutions, *overrides.values()], unresolved


class LibraryStalled(AssemblyError):
    """A library file could not be read *right now* (FR-021, FR-026f).

    `library_problem` is FR-026f's answer for a library that is wholly unavailable — moved,
    unmounted, unreadable. It checks the *root*, which is the right check for the case it
    describes and no help at all for the one that actually happened: a mount that is up,
    holding a file the sync client has not materialised, which times out on read and reads
    fine a minute later.

    `503` rather than `409` or `500`. Not a server fault — nothing here is broken — and not
    a conflict with the run's state, which is unchanged and still perfectly good. It is
    "temporarily unable, try again", which is both true and the whole remedy.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status=503)


def stalled_library(exc: AssetUnreadable) -> LibraryStalled:
    """Turn an unreadable asset into a sentence a person can act on.

    Names the file, because "something could not be read" leaves the user unable to tell a
    syncing library from a corrupt scan. Says to try again, because for the reported case
    waiting *is* the fix and nothing else in the message implies that.
    """
    return LibraryStalled(
        f"{exc} — the library could not be read just now. This usually means a synced "
        "folder has not finished downloading that file. Nothing is lost: wait a moment and "
        "open this run again."
    )


def library_problem(record: RunRecord) -> str | None:
    """Why this run cannot read its library right now, or `None` (FR-026f).

    **Derived per read, never stored.** A Drive mount that is down at nine is up at ten, and
    a run carrying a persisted "your folder is missing" would go on saying so after the
    folder came back — a fact about one visit written down as though it were a fact about
    the run.

    **Terminal runs are exempt, and that is the requirement rather than an optimisation.** A
    finished run holds its own PDF and depends on nothing outside itself (FR-026f, SC-006h);
    checking a mount it will never read again could only produce a warning about nothing.

    **One sentence naming the folder, not a wave of missing cards.** Both renderings carry
    the same fact. Only this one tells the user the mount is down; the other buries it under
    forty card names that will all come back when the drive reappears, which is why the spec
    requires the report to hang off the run.
    """
    if record.state.terminal:
        return None

    root = record.library_root
    if not root.exists():
        return (
            f"the library folder {root} is not there. It has been moved, renamed, or "
            "unmounted since this run started. Nothing is lost — restore it and reopen "
            "this run."
        )
    if not root.is_dir():
        return f"the library folder {root} is no longer a directory."
    if not os.access(root, os.R_OK | os.X_OK):
        return f"the library folder {root} can no longer be read."

    hero = root / record.hero_folder
    if not hero.is_dir():
        return (
            f"the hero folder {record.hero_folder} is no longer inside {root}. The library "
            "is readable, so it has been renamed or moved rather than unmounted."
        )
    return None


def _waiting_state(unresolved: Sequence[Any], decklist: DecklistState) -> RunState:
    """Whether the run is still waiting on the user.

    An undecided decklist candidate holds the run exactly as an unresolved card does
    (FR-013d). It needs no state of its own; `skip` is the escape.
    """
    waiting = bool(unresolved) or (decklist.candidate is not None and not decklist.decided)
    return RunState.AWAITING_CARDS if waiting else RunState.READY


class AssemblyService:
    def __init__(
        self,
        settings: Settings,
        snapshots: SnapshotStore,
        layout: StateLayout | None = None,
    ) -> None:
        self.settings = settings
        self.snapshots = snapshots
        self.layout = layout or StateLayout(settings.state_dir)
        self.layout.ensure()
        self.runs = RunStore(self.layout)
        self.pdfs = PdfStore(self.layout)

    # ------------------------------------------------------------------ lookups

    def get(self, run_id: str) -> RunRecord:
        return self.runs.read(run_id)

    def resume(self, run_id: str) -> RunRecord:
        """Reopen a run on a later visit (FR-026b, SC-006f).

        For the case the user actually meets — a run parked in `awaiting_pack` or
        `awaiting_cards` — this is a read, and that is the point: the folder, the pack, the
        pinned revision, the resolutions, and the report are all on disk, so there is nothing
        to reconstruct and nothing that needs the library to still be mounted.

        What it does do is recover a run the *process* left mid-step. ADR 0001 chose plain
        files knowing a crash can land between a state change and the work it announced, and
        `identifying`, `resolving`, and `rendering` are the three states nobody will ever
        move a run out of, because the only thing that could was the request that died:

        - **`rendering`** goes back to `ready`. The PDF is linked to the run only after
          `compose` returns, so a crashed render left nothing; the user confirms again. Not
          `failed`, because nothing about the run is wrong.
        - **`resolving`** re-resolves, which is safe to repeat — the cascade is a pure read
          of the library and the user's own answers are laid back over it. Skipped when the
          library is unreachable, so a run is never demoted for a mount being down.
        - **`identifying`** is `failed`. It crashed before there was a pack, and there is
          nothing to resume toward; FR-036 requires that to be a stated outcome rather than
          a run that sits forever looking busy.

        Left strictly alone otherwise. A resumed run is never silently advanced past a
        question the user has not answered.
        """
        record = self.runs.read(run_id)
        if record.state is RunState.RENDERING:
            record.state = RunState.READY
            return self.runs.write(record)
        if record.state is RunState.IDENTIFYING:
            record.state = RunState.FAILED
            record.outcome = Outcome.REFUSED
            return self.runs.write(record)
        if record.state is RunState.RESOLVING and library_problem(record) is None:
            return self._resolve(record)
        return record

    def _check_version(self, record: RunRecord, expected: int | None) -> None:
        """Optimistic concurrency (ADR 0001). A stale value is 409, never a silent write.

        Two browser tabs answering two different unresolved cards is the lost update the
        ADR's dissenting reviewers named, and this is the mechanism they named for it.
        """
        if expected is not None and expected != record.version:
            raise AssemblyError(
                f"run {record.id} is at version {record.version}, not {expected}. "
                "Re-read the run and retry.",
                status=409,
            )

    # ------------------------------------------------------------------ creation

    def create(
        self,
        library_root: Path,
        hero_folder: str,
        page_size: str = "LETTER",
        fit_mode: str = "CROP",
    ) -> RunRecord:
        """Start a run: validate the paths, identify the pack, and stop (FR-012a).

        Deliberately does not resolve. The run settles in `awaiting_pack` or `unidentified`
        and waits for a human, because SC-009's failure is a confident wrong identification
        and no amount of confidence substitutes for being asked.

        Both enum names are upper-cased on the way in. They are stored as strings and read
        back as `PageSize[...]` and `FitMode(...)`, both of which are case-sensitive, so a
        caller that said `"crop"` would produce a run that resolves and then fails to render
        — a long way from the mistake.
        """
        root, relative = _validate_paths(library_root, hero_folder)
        record = self.runs.create(
            root, relative, page_size=str(page_size).upper(), fit_mode=str(fit_mode).upper()
        )

        try:
            index = build_index(root, file_cap=self.settings.limits.library_scan_files)
        except AssetUnreadable as exc:
            # A folder the walk could not read used to vanish from the index, so the run
            # reached `unidentified` and told the user their folder matched no pack — a
            # confident wrong answer to a question about a mount, not about filenames.
            raise stalled_library(exc) from exc
        result = identify(relative, index, self.snapshots.pack_index(), self._load_pack_cards)

        record.identification = result.to_json()
        record.state = RunState.AWAITING_PACK if result.confident else RunState.UNIDENTIFIED
        return self.runs.write(record)

    def _load_pack_cards(self, pack_code: str) -> list[PackCard]:
        return list(self.snapshots.get(pack_code).cards)

    def _pinned_snapshot(self, record: RunRecord, pack_code: str):
        """The listing this run was resolved against, not the current one (FR-044b, FR-045).

        A run pins its revision when its pack is confirmed, and every later pass — a
        re-resolve after an upload, the render itself — has to read *that* listing. Reading
        the current one instead is the failure with no symptom: an explicit refresh brings
        down a corrected pack, and the run the user comes back to prints a different deck
        with all forty of their resolutions still sitting there looking answered.

        Falls back to the current snapshot when the pinned revision is no longer retained.
        The alternative is refusing to finish a run whose archived file has gone, which
        costs the user their work to protect them from a listing that has usually not
        changed — and when it has, the report still names the revision that was used.
        """
        pinned = record.snapshot_revision
        if pinned:
            snapshot = self.snapshots.read_revision(pack_code, pinned)
            if snapshot is not None:
                return snapshot
        return self.snapshots.get(pack_code)

    # ------------------------------------------------------------------ the pack

    def candidates(self, run_id: str, query: str | None = None) -> list[dict[str, Any]]:
        """FR-012b. The ranked candidates, or a name search across every pack.

        The same path serves an FR-011 refusal and an unidentifiable folder, so neither
        leaves the user holding a good folder and no way to print it.
        """
        record = self.runs.read(run_id)
        if query:
            needle = query.casefold()
            return [
                {"pack_code": e.code, "pack_name": e.name, "confidence": None, "evidence": []}
                for e in self.snapshots.pack_index()
                if needle in e.name.casefold()
            ]
        identification = Identification.from_json(record.identification or {})
        return [
            {
                "pack_code": c.pack_code,
                "pack_name": c.pack_name,
                "confidence": c.score,
                "evidence": list(identification.evidence)
                if c is identification.candidates[0]
                else [],
            }
            for c in identification.candidates
        ] or [
            {
                "pack_code": c.pack_code,
                "pack_name": c.pack_name,
                "confidence": c.score,
                "evidence": [],
            }
            for c in rank_packs(record.hero_folder, self.snapshots.pack_index())
        ]

    def set_pack(
        self, run_id: str, action: str, pack_code: str | None = None, version: int | None = None
    ) -> RunRecord:
        """Confirm the identification or select a different pack, then resolve.

        Selecting is **not** customization (FR-026i, SC-009a): what gets printed follows from
        the pack and its snapshot, so a run that corrected the tool and then resolved
        everything automatically still produces that pack's standard PDF.
        """
        record = self.runs.read(run_id)
        self._check_version(record, version)
        if record.state not in (RunState.AWAITING_PACK, RunState.UNIDENTIFIED):
            raise AssemblyError(
                f"run {run_id} is {record.state.value}; a pack can only be set while it is "
                "awaiting_pack or unidentified"
            )

        identification = Identification.from_json(record.identification or {})
        if action == "select":
            if not pack_code:
                raise AssemblyError("`select` requires a pack_code", status=400)
            names = {e.code: e.name for e in self.snapshots.pack_index()}
            if pack_code not in names:
                raise AssemblyError(f"no pack with code {pack_code!r}", status=400)
            identification = identification.select(pack_code, names[pack_code])
        elif action == "confirm":
            if not identification.confident:
                raise AssemblyError(
                    "nothing was identified for this run; select a pack instead", status=409
                )
        else:
            raise AssemblyError(f"unknown action {action!r}", status=400)

        record.identification = identification.to_json()
        # Pinned here, so refreshing card data later cannot change composition or quantities
        # under resolutions already made (FR-044b, FR-045).
        snapshot = self.snapshots.get(identification.pack_code or "")
        record.snapshot_revision = snapshot.revision
        record.state = RunState.RESOLVING
        record = self.runs.write(record)
        return self._resolve(record)

    # ------------------------------------------------------------------ resolving

    def _resolve(self, record: RunRecord) -> RunRecord:
        identification = Identification.from_json(record.identification or {})
        pack_code = identification.pack_code or ""
        # The revision this run pinned, never the current one (FR-045). Re-resolving after
        # an upload must not quietly pick up a listing refreshed in the meantime.
        snapshot = self._pinned_snapshot(record, pack_code)
        cards = list(snapshot.cards)

        try:
            index = build_index(
                record.library_root, file_cap=self.settings.limits.library_scan_files
            )
        except AssetUnreadable as exc:
            raise stalled_library(exc) from exc
        try:
            outcome = resolve_pack(
                expand_pack(cards),
                cards,
                index,
                record.hero_folder,
                record.library_root,
                self._load_printing,
            )
        except AssetUnreadable as exc:
            # Raised before the record is touched, so the run is exactly as it was and a
            # later pass re-resolves from scratch. The test asserts that, because a refactor
            # moving the write earlier would trade a transient stall for lost work.
            raise stalled_library(exc) from exc
        resolutions, unresolved = _apply_user_answers(record, outcome)
        decklist = self._decklist_state(record, index)

        record.resolutions = [r.to_json() for r in resolutions]
        # The catalog is built here as well as at render time, and not only to save work
        # later: it is what knows each card's FR-015 group and what the entries actually
        # print. Without it a run waiting on a card reports every resolution as a player
        # card and zero cards printed — and FR-030b requires an incomplete pack to stay
        # legible as incomplete, which a report claiming nothing was found is not. In
        # memory only, as always.
        built = build_catalog(
            pack_code=pack_code,
            pack_name=identification.pack_name or pack_code,
            cards=cards,
            resolutions=resolutions,
            snapshot_revision=record.snapshot_revision or "",
            decklist=decklist,
        )
        record.report = self._report(
            record,
            cards,
            resolutions,
            decklist,
            built=built,
            index=index,
            unresolved=unresolved,
        ).to_json()
        record.report["unresolved"] = [u.to_json() for u in unresolved]
        record.decklist = decklist.to_json()
        record.state = _waiting_state(unresolved, decklist)
        return self.runs.write(record)

    def _decklist_state(self, record: RunRecord, index) -> DecklistState:
        stored = record.decklist
        found = find_decklist(index, record.hero_folder)
        if not stored:
            return found
        previous = DecklistState.from_json(stored)
        if previous.decided:
            # A decision already made survives re-resolution; the library is re-read on every
            # pass (FR-026b) and re-asking would undo an answer the user already gave.
            return found.carrying(previous)
        return found

    def _load_printing(self, code: str) -> PackCard | None:
        """Research R4's prefix→pack map, learned from snapshots already held.

        A card code's first two digits are its pack's ordinal, but the reduced pack index
        keeps only code and name, so the map cannot be built up front. It is learned from
        every snapshot on disk and extended by one fetch when a prefix is still unknown —
        which bounds the request count by the number of *distinct packs referenced*, not by
        the card count (FR-040, SC-006d).
        """
        return self.snapshots.card_by_code(code)

    def _report(
        self,
        record,
        cards,
        resolutions,
        decklist,
        built=None,
        page_count=None,
        index=None,
        unresolved=(),
    ):
        """The report for this run, from what this pass already holds.

        `index` and the run's own store are passed through rather than rebuilt: the library
        sections describe the pass that produced the resolutions, and re-walking the library
        here could describe a different one (FR-026b re-reads it on every pass).
        """
        identification = Identification.from_json(record.identification or {})
        return build_report(
            pack_code=identification.pack_code,
            pack_name=identification.pack_name,
            pack_source=identification.source.value,
            cards=cards,
            resolutions=resolutions,
            built=built,
            decklist=decklist,
            snapshot_revision=record.snapshot_revision,
            page_count=page_count,
            index=index,
            hero_folder=record.hero_folder,
            unresolved=unresolved,
            store=OverlayStore(record.library_root, self.layout.run_dir(record.id)),
            # The run's own fit mode: `crop` trims the overflowing edges, so the DPI a scan
            # actually prints at depends on it, and warning against the wrong one would
            # report a file the document is perfectly happy with (FR-035).
            fit_mode=FitMode(record.fit_mode),
        )

    # ------------------------------------------------- answering a card by hand (US4)

    def unresolved_face(self, run_id: str, card_code: str, side: str) -> dict[str, Any]:
        """The gap this card and side names, or the reason there is nothing to answer.

        Called before an upload is read off the wire, so a request that cannot be honoured
        is refused before 64 MB of it has been streamed to disk.

        **The refusal for a run that has not resolved yet is FR-030a's**, and it is a rule
        about ordering rather than about payloads: permission to print an incomplete pack
        cannot be granted before the run has reported which cards are unresolved, because a
        decision taken then is not an informed one. A blanket permission offered up front is
        refused rather than remembered, and the run still stops on the first card it cannot
        resolve (US4 scenario 9).
        """
        record = self.runs.read(run_id)
        if record.state is not RunState.AWAITING_CARDS:
            raise AssemblyError(
                f"run {run_id} is {record.state.value} and has not reported which cards it "
                "could not resolve. A decision about a card the run has not asked about yet "
                "is not an informed one, so it is refused rather than remembered (FR-030a).",
                status=409,
            )
        for gap in record.report.get("unresolved") or []:
            if gap["card_code"] == card_code and gap.get("side", "front") == side:
                return gap
        waiting_on = ", ".join(
            sorted(
                f"{g['card_code']} ({g.get('side', 'front')})" for g in record.report["unresolved"]
            )
        )
        raise AssemblyError(
            f"{card_code} ({side}) is not one of the cards run {run_id} could not resolve, "
            f"so there is nothing to answer for it. This run is waiting on: {waiting_on}.",
            status=409,
        )

    def supply_card_image(
        self,
        run_id: str,
        card_code: str,
        side: str,
        source: Path,
        content_digest: str,
        original_filename: str,
        version: int | None = None,
    ) -> RunRecord:
        """Record a file the user chose for one card (FR-026, FR-026e, FR-027, FR-029).

        The bytes are taken into the run, not referenced where they sit. The user went and
        found that file somewhere and has no reason to keep it there, so a run that pointed
        at it would stop printing the day they tidied up (SC-006b, US4 scenario 4).

        Validation has already happened by the time this is called — a rejected file must
        never reach the run's uploads directory, or the run would be one record away from
        resolving a card to an image the service has said it will not print (FR-028).
        """
        record = self.runs.read(run_id)
        self._check_version(record, version)
        gap = self.unresolved_face(run_id, card_code, side)

        self._store_upload(record, source, content_digest)
        record.resolutions.append(
            manual_resolution(
                card_code=card_code,
                card_name=gap.get("card_name") or card_code,
                side=Side(side),
                content_digest=content_digest,
                original_filename=original_filename,
                quantity=self._quantity_for(record, card_code),
            ).to_json()
        )
        # FR-026i: two users pointed at the same folder would now get different PDFs, so
        # this is not the pack's standard one.
        record.customized = True
        return self._resolve(record)

    def omit_card(
        self, run_id: str, card_code: str, side: str, version: int | None = None
    ) -> RunRecord:
        """Print without this card, at the user's explicit request (FR-030, FR-030b).

        The default when a card cannot be resolved is to stop; proceeding anyway is the
        user's decision and the tool must not overrule it. What it must do is make the
        result legible as incomplete afterwards, which is the report's job and not this
        method's — here the card simply stops being a gap and starts being an omission.
        """
        record = self.runs.read(run_id)
        self._check_version(record, version)
        gap = self.unresolved_face(run_id, card_code, side)

        record.resolutions.append(
            omitted_resolution(
                card_code=card_code,
                card_name=gap.get("card_name") or card_code,
                side=Side(side),
            ).to_json()
        )
        record.customized = True
        return self._resolve(record)

    def _store_upload(self, record: RunRecord, source: Path, content_digest: str) -> Path:
        """Take the bytes into the run, named by their own SHA-256 (research R9).

        Content-addressed for two reasons that both matter: the same file supplied twice
        costs one copy, and the ref a resolution carries then says nothing about where the
        file came from — which is what lets FR-027 and FR-009 both hold without an exception.
        """
        destination = self.layout.upload(record.id, content_digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        return destination

    def _quantity_for(self, record: RunRecord, card_code: str) -> int:
        """Copies of this card **in the pack being printed** (FR-016).

        Read from the pinned snapshot rather than assumed to be one: `cap` prints three
        Honorary Avenger, and a manually supplied file for it must print three times like
        every other resolution of that card.
        """
        identification = Identification.from_json(record.identification or {})
        for card in self._pinned_snapshot(record, identification.pack_code or "").cards:
            if card.code == card_code or card_code in card.linked_codes:
                return card.quantity
        return 1

    # ------------------------------------------------------------------ decklist

    def decide_decklist(
        self,
        run_id: str,
        action: str,
        ref: str | None = None,
        version: int | None = None,
    ) -> RunRecord:
        record = self.runs.read(run_id)
        self._check_version(record, version)
        if not record.decklist:
            raise AssemblyError(f"run {run_id} has not resolved yet", status=409)
        state = DecklistState.from_json(record.decklist)
        try:
            decided = state.decide(DecklistDecision(action), ref=ref)
        except ValueError as exc:
            raise AssemblyError(str(exc), status=400) from exc

        self._apply_decklist(record, decided)
        return self.runs.write(record)

    def supply_decklist(
        self,
        run_id: str,
        source: Path,
        content_digest: str,
        original_filename: str,
        version: int | None = None,
    ) -> RunRecord:
        """The deck list photograph the user fetched themselves (FR-013c, research R9).

        25 of 60 hero folders hold no deck list scan. The run names that gap and offers the
        address at which Hall of Heroes publishes one; the application never fetches it,
        which is what keeps FR-002's egress allowlist at a single host. This is where the
        file the user downloaded comes back — through the same upload mechanism an
        unresolved card uses, because the deck list card has no MarvelCDB code and so needs
        a path of its own but no machinery of its own.
        """
        record = self.runs.read(run_id)
        self._check_version(record, version)
        if not record.decklist:
            raise AssemblyError(f"run {run_id} has not resolved yet", status=409)

        self._store_upload(record, source, content_digest)
        state = DecklistState.from_json(record.decklist)
        self._apply_decklist(
            record, state.supply(f"{UPLOAD_PREFIX}{content_digest}", original_filename)
        )
        return self.runs.write(record)

    def _apply_decklist(self, record: RunRecord, decided: DecklistState) -> None:
        """Fold a deck list decision into the run and its report.

        Patched onto the stored report rather than rebuilt through `_resolve`, because a
        deck list decision changes exactly one card and a full pass re-hashes ~40 scans of
        ~3 MB to learn nothing. The three fields and the one entry written here are exactly
        what `build_report` would produce for the same state, which is why both call the
        same helpers — two spellings of one projection is how a report starts disagreeing
        with itself depending on which endpoint last touched it.
        """
        record.decklist = decided.to_json()
        report = record.report
        report["decklist_printed"] = decided.printed
        report["decklist_source_url"] = None if decided.printed else decided.hall_of_heroes_url

        entries = [e for e in report.get("resolutions") or [] if e["card_code"] != DECKLIST_CODE]
        notes = [
            note
            for note in report.get("low_resolution") or []
            if note["file"] not in {decided.chosen_ref, decided.uploaded_filename}
        ]
        if (entry := decklist_entry(decided)) is not None:
            entries.append(entry)
            # FR-035, research R9: a Hall of Heroes photograph will very likely fall below
            # the print-resolution floor, and that is the correct outcome rather than
            # something to special-case into silence. It prints, and it is reported soft.
            notes.extend(
                low_resolution_notes(
                    OverlayStore(record.library_root, self.layout.run_dir(record.id)),
                    [card for card in [decklist_resolution(decided)] if card],
                    FitMode(record.fit_mode),
                )
            )
        report["resolutions"] = entries
        report["low_resolution"] = notes

        if decided.customizes_the_run:
            record.customized = True
        record.state = _waiting_state(report.get("unresolved") or [], decided)

    # ------------------------------------------------------------------ rendering

    def _require_complete(self, record: RunRecord) -> None:
        """FR-017, FR-025, FR-037 — every card resolves, or the run says which did not.

        Deliberately not the same check as `state is READY`, and deliberately first. The
        state says *that* the run is not printable; this says *which cards*, which is the
        only form of the refusal a user can act on. A message reading "409 Conflict" or
        "run is awaiting_cards" sends them to read source code (SC-008).

        Held against the record rather than against a fresh resolve, so it cannot disagree
        with the report the user is looking at.
        """
        unresolved = record.report.get("unresolved") or []
        if not unresolved:
            return
        named = ", ".join(
            f"{u.get('card_name') or u['card_code']} ({u['card_code']}, {u.get('side', 'front')})"
            for u in sorted(unresolved, key=lambda u: (u["card_code"], u.get("side", "")))
        )
        raise AssemblyError(
            f"run {record.id} cannot print: {len(unresolved)} face(s) resolved to no image "
            f"— {named}. Supply a file for each, or choose to print without it.",
            status=409,
        )

    def confirm(
        self, run_id: str, save_as: str | None = None, version: int | None = None
    ) -> RunRecord:
        """Produce the PDF. The only place one is produced (FR-026a)."""
        record = self.runs.read(run_id)
        self._check_version(record, version)
        self._require_complete(record)
        if record.state is not RunState.READY:
            raise AssemblyError(
                f"run {run_id} is {record.state.value}; only a ready run can be confirmed"
            )

        customized = bool(record.customized)
        if customized and not save_as:
            raise AssemblyError(
                "this run was customized, so its PDF is not the pack's standard one and "
                "must be named with `save_as` (FR-026i)",
                status=400,
            )
        if not customized and save_as:
            raise AssemblyError(
                "this run was not customized, so it produces the pack's standard PDF and "
                "`save_as` must be absent (FR-026h)",
                status=400,
            )

        identification = Identification.from_json(record.identification or {})
        pack_code = identification.pack_code or ""
        snapshot = self._pinned_snapshot(record, pack_code)
        cards = list(snapshot.cards)
        resolutions = [Resolution.from_json(r) for r in record.resolutions]
        decklist = DecklistState.from_json(record.decklist) if record.decklist else None
        identity = output_identity(resolutions, record.page_size, record.fit_mode)

        record.state = RunState.RENDERING
        record = self.runs.write(record)

        built = build_catalog(
            pack_code=pack_code,
            pack_name=identification.pack_name or pack_code,
            cards=cards,
            resolutions=resolutions,
            snapshot_revision=record.snapshot_revision or "",
            decklist=decklist,
        )
        if built is None:
            # Unreachable through the wizard — `_require_complete` above has already
            # stopped a run with any unresolved face. Named rather than left to an
            # `AttributeError`, because the one way to arrive here is a pack listing that
            # holds no cards at all, and "no cards" is a sentence (FR-037).
            raise AssemblyError(
                f"run {record.id} resolved no printable card, so there is nothing to render"
            )

        reused = False
        stored = None
        if not customized:
            stored = self.pdfs.find_standard(pack_code, record.snapshot_revision or "", identity)
            reused = stored is not None

        store = OverlayStore(record.library_root, self.layout.run_dir(record.id))
        pages = paginate(built.catalog, built.deck.id, PageSize[record.page_size], store)

        if stored is None:
            try:
                data = compose(pages, PageSize[record.page_size], FitMode(record.fit_mode), store)
            except AssetUnreadable as exc:
                # Resolution digested every scan and the renderer decodes them again, so a
                # library that stalls between the two lands here instead. Same condition,
                # same answer — no partial PDF is written either way (FR-020a).
                raise stalled_library(exc) from exc
            stored = (
                self.pdfs.put_saved(data, save_as)
                if customized
                else self.pdfs.put_standard(
                    pack_code, record.snapshot_revision or "", identity, data
                )
            )

        self.pdfs.attach_to_run(record.id, stored)
        record.pdf = {"kind": stored.kind.value, "id": stored.id}
        record.reused = reused
        record.report = self._report(
            record, cards, resolutions, decklist, built=built, page_count=len(pages)
        ).to_json()
        record.report["unresolved"] = []
        record.state = RunState.COMPLETE
        record.outcome = outcome_for(record.state, record.report)
        record = self.runs.write(record)
        self._log(record, resolutions)
        return record

    def _log(self, record: RunRecord, resolutions: Sequence[Resolution]) -> None:
        """One line for the finished run (FR-030b, FR-022b).

        Written after the record, not before: a log line claiming a run completed when the
        write that made it complete failed is worse than no line at all.
        """
        write_record(
            AssemblyRecord(
                run_id=record.id,
                pack_code=(record.report or {}).get("pack_code") or "",
                pack_source=(record.report or {}).get("pack_source") or "",
                snapshot_revision=record.snapshot_revision or "",
                outcome=record.outcome.value if record.outcome else "",
                cards_printed=(record.report or {}).get("cards_printed", 0),
                cards_in_pack=(record.report or {}).get("cards_in_pack", 0),
                page_count=(record.report or {}).get("page_count"),
                reused=bool(record.reused),
                customized=bool(record.customized),
                # Codes, sides and enum values. Not `ref`, which is a path inside the
                # library, and not `original_filename`, which is a name from wherever the
                # user picked the file — the two fields FR-009 is about.
                resolutions=[
                    {
                        "card_code": r.card_code,
                        "side": r.side.value,
                        "provenance": r.provenance.value,
                        "source": r.source.value,
                    }
                    for r in resolutions
                    if r.provenance is not Provenance.OMITTED
                ],
                omitted_card_codes=sorted(
                    {r.card_code for r in resolutions if r.provenance is Provenance.OMITTED}
                ),
                manual_card_codes=sorted(
                    {r.card_code for r in resolutions if r.provenance is Provenance.MANUAL}
                ),
            )
        )

    def delete(self, run_id: str, version: int | None = None) -> None:
        """Throw away a deck attempt (FR-026g1). **Not** the same act as reclaiming disk.

        What goes is what is private to this run: its record, the files uploaded to it
        (FR-026e), and — if it produced one — the *saved* PDF it named (FR-026i).

        What stays is the pack's **standard** PDF. It belongs to the pack, not to the run
        that happened to build it, and every other run of that pack was served the same
        file; deleting it here would revoke FR-026f's guarantee for all of them, from a
        button whose label says nothing about that. It is removed from the stored-PDF list
        instead, which is the act that says what it does.

        The consequence the user actually feels is predictability: discarding a run frees a
        few uploaded scans, never 202 MB, unless the run's PDF was theirs alone.
        """
        record = self.runs.read(run_id)
        self._check_version(record, version)

        stored = record.pdf or {}
        if stored.get("kind") == PdfKind.SAVED.value and stored.get("id"):
            self.pdfs.delete_saved(stored["id"])
        # `runs.delete` removes the whole run directory, and the run's hard link to a
        # standard PDF goes with it — which frees nothing, because `pdfs/standard/` still
        # holds a name for the same inode. That is the refcount doing the work rather than
        # a rule someone has to remember here.
        self.runs.delete(run_id)

    def document(self, run_id: str) -> bytes:
        """The finished PDF. Depends on nothing outside the run (FR-026f, SC-006h)."""
        record = self.runs.read(run_id)
        if not record.pdf:
            raise AssemblyError(
                f"run {run_id} has not produced a document; there is never partial output",
                status=409,
            )
        return (self.layout.run_dir(record.id) / "output.pdf").read_bytes()
