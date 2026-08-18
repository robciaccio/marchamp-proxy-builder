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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from marchamp.assembly.catalog import build_catalog
from marchamp.assembly.decklist import DecklistDecision, DecklistState, find_decklist
from marchamp.assembly.faces import expand_pack
from marchamp.assembly.report import build_report
from marchamp.assembly.resolve import Resolution, resolve_pack
from marchamp.assets.overlay import OverlayStore
from marchamp.config import Settings
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import paginate
from marchamp.library.identify import Identification, identify, rank_packs
from marchamp.library.index import build_index
from marchamp.render.document import FitMode, compose
from marchamp.store.layout import StateLayout
from marchamp.store.pdfs import PdfStore
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


def image_identity(resolutions: Sequence[Resolution]) -> str:
    """The identity of the images a run resolved — the third part of FR-026h's key.

    Content, not paths. Two runs that resolved the same bytes share a PDF even if one of
    them read them from a folder that has since been renamed (SC-006h); a run where one card
    now resolves to different bytes rebuilds (SC-006k). The card code is hashed alongside the
    digest so swapping two cards' images is a different identity, not the same multiset.
    """
    hasher = hashlib.sha256()
    for resolution in sorted(resolutions, key=lambda r: (r.card_code, r.side.value)):
        hasher.update(
            f"{resolution.card_code}:{resolution.side.value}:{resolution.content_digest}\n".encode()
        )
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

        index = build_index(root, file_cap=self.settings.limits.library_scan_files)
        result = identify(relative, index, self.snapshots.pack_index(), self._load_pack_cards)

        record.identification = result.to_json()
        record.state = RunState.AWAITING_PACK if result.confident else RunState.UNIDENTIFIED
        return self.runs.write(record)

    def _load_pack_cards(self, pack_code: str) -> list[PackCard]:
        return list(self.snapshots.get(pack_code).cards)

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
        snapshot = self.snapshots.get(pack_code)
        cards = list(snapshot.cards)

        index = build_index(record.library_root, file_cap=self.settings.limits.library_scan_files)
        outcome = resolve_pack(
            expand_pack(cards),
            cards,
            index,
            record.hero_folder,
            record.library_root,
            self._load_printing,
        )
        decklist = self._decklist_state(record, index)

        record.resolutions = [r.to_json() for r in outcome.resolutions]
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
            resolutions=outcome.resolutions,
            snapshot_revision=record.snapshot_revision or "",
            decklist=decklist,
        )
        record.report = self._report(
            record,
            cards,
            outcome.resolutions,
            decklist,
            built=built,
            index=index,
            unresolved=outcome.unresolved,
        ).to_json()
        record.report["unresolved"] = [u.to_json() for u in outcome.unresolved]
        record.decklist = decklist.to_json()

        # An undecided decklist candidate holds the run exactly as an unresolved card does
        # (FR-013d). It needs no state of its own; `skip` is the escape.
        waiting = bool(outcome.unresolved) or (
            decklist.candidate is not None and not decklist.decided
        )
        record.state = RunState.AWAITING_CARDS if waiting else RunState.READY
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
            return found.decide(previous.decision, ref=previous.chosen_ref)
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

        record.decklist = decided.to_json()
        record.report["decklist_printed"] = decided.printed
        record.report["decklist_source_url"] = (
            None if decided.printed else decided.hall_of_heroes_url
        )
        if decided.customizes_the_run:
            record.customized = True
        unresolved = record.report.get("unresolved") or []
        record.state = RunState.AWAITING_CARDS if unresolved else RunState.READY
        return self.runs.write(record)

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
        snapshot = self.snapshots.get(pack_code)
        cards = list(snapshot.cards)
        resolutions = [Resolution.from_json(r) for r in record.resolutions]
        decklist = DecklistState.from_json(record.decklist) if record.decklist else None
        identity = image_identity(resolutions)

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
            data = compose(pages, PageSize[record.page_size], FitMode(record.fit_mode), store)
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
        return self.runs.write(record)

    def document(self, run_id: str) -> bytes:
        """The finished PDF. Depends on nothing outside the run (FR-026f, SC-006h)."""
        record = self.runs.read(run_id)
        if not record.pdf:
            raise AssemblyError(
                f"run {run_id} has not produced a document; there is never partial output",
                status=409,
            )
        return (self.layout.run_dir(record.id) / "output.pdf").read_bytes()
