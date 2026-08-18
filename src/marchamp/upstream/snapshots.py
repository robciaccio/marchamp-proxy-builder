"""Pack snapshots (FR-039, FR-044–FR-047, data-model.md § Pack Snapshot, research R1, R10).

**This store is the cache**, and that is why there is no HTTP caching library (research R2).
A run pins a snapshot revision (FR-045), so the thing that decides when to refetch and the
thing that remembers what a run was built against must be the same thing. A second cache
with its own eviction policy would be free to discard what a finished run still depends on,
and reconciling the two would cost more than the thirty lines below.

Four decisions, each answering a requirement rather than a preference.

**The revision is a content hash of the reduced records.** Not of the response, and
specifically not of `Last-Modified`. MarvelCDB serves no `ETag`, and `Last-Modified` moves
for reasons that change no card — a revision derived from it would invalidate every stored
PDF on a schedule, and at ~202 MB and ~49 s apiece that is the difference between FR-026h's
reuse working and being theoretical.

**Within `max-age` (measured: 600 s) no request is issued at all** — not a cheap conditional
one, none (FR-039, SC-006d). A 304 still costs a volunteer-run service a request.

**Past it, one conditional `If-Modified-Since`.** A 304 keeps the revision and extends
freshness; nothing is rewritten.

**Degradation is asymmetric on purpose.** A failed refetch with something stored serves the
stored copy marked stale (FR-044a) — old card data prints a fine pack. A failed fetch with
nothing stored refuses and names the pack (FR-046); there is no partial pack worth printing
and guessing is the one response that must never happen.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from marchamp.store.atomic import atomic_write_json
from marchamp.store.layout import StateLayout, UnsafeIdentifier
from marchamp.upstream.client import MarvelCdbClient, UpstreamError
from marchamp.upstream.models import (
    PackCard,
    PackIndexEntry,
    SnapshotInvalid,
    parse_pack_index,
    parse_snapshot_cards,
)

SCHEMA_VERSION = "1"

#: data-model.md § Pack Snapshot: sha256 of the canonical serialisation, truncated to 16.
REVISION_LENGTH = 16


class SnapshotUnavailable(Exception):
    """No usable card data for this pack, and none can be obtained (FR-046).

    Always names the pack. "Something went wrong" leaves the user with no next step, and the
    next step here is usually "check the network" or "this pack code is wrong".
    """


@dataclass
class PackSnapshot:
    pack_code: str
    revision: str
    cards: list[PackCard]
    captured_at: str
    fresh_until: str
    last_modified: str | None = None
    #: Derived per read, never stored: it means "served after a failed refetch", which is a
    #: property of this retrieval rather than of the file (FR-044a).
    stale: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "pack_code": self.pack_code,
            "revision": self.revision,
            "cards": [c.to_json() for c in self.cards],
            "captured_at": self.captured_at,
            "fresh_until": self.fresh_until,
            "last_modified": self.last_modified,
        }


def compute_revision(cards: list[PackCard]) -> str:
    """A content hash of the reduced records, order-independent.

    Sorted before hashing so a listing that arrives in a different order — which upstream is
    under no obligation to keep stable — is recognised as the same data rather than as a
    change that invalidates every reused PDF.
    """
    canonical = json.dumps(
        sorted((c.to_json() for c in cards), key=lambda c: (c["position"], c["code"])),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:REVISION_LENGTH]


class SnapshotStore:
    def __init__(
        self,
        layout: StateLayout,
        client: MarvelCdbClient,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        self.layout = layout
        self.client = client
        self._utcnow = utcnow or (lambda: datetime.now(UTC))

    # -------------------------------------------------------------------- pack index

    def pack_index(self) -> list[PackIndexEntry]:
        """The 61-row pack list, under the same freshness rules as a snapshot (FR-039).

        It changes a few times a year and is needed before any pack code can be validated,
        so refetching it per run would be the largest single source of avoidable traffic.
        """
        path = self.layout.pack_index()
        stored = self._read_json(path)
        if stored and not self._expired(stored.get("fresh_until")):
            try:
                return parse_pack_index(stored.get("entries", []))
            except SnapshotInvalid:
                pass  # fall through and refetch; a corrupt cache is not a reason to fail

        try:
            entries = self.client.fetch_pack_index()
        except UpstreamError as exc:
            if stored:
                try:
                    return parse_pack_index(stored.get("entries", []))
                except SnapshotInvalid:
                    pass
            raise SnapshotUnavailable(f"the pack list could not be retrieved: {exc}") from exc

        atomic_write_json(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "entries": [{"code": e.code, "name": e.name} for e in entries],
                "fresh_until": self._fresh_until(self.client.settings.default_max_age_s),
            },
        )
        return entries

    # ------------------------------------------------------- finding one card by code

    def card_by_code(self, code: str) -> PackCard | None:
        """One card, wherever it lives — the lookup FR-022's reprint step needs.

        Research R4's prefix→pack map. A card code's first two digits are its pack's
        ordinal, but the reduced pack index keeps only code and name (T029), so the map
        cannot be built up front from the index alone. It is learned instead from the
        snapshots already on disk: every `cap` card's code starts `03`, so holding `cap`
        teaches `03 -> cap` for free.

        When a prefix is still unknown, one request asks which pack that single card is in
        (`fetch_card_pack_code`) and a second fetches that pack. This is the one place the
        feature spends a request it could not predict, and it stays bounded because the
        answer is then cached with the snapshot: the request count per assembled pack
        follows the number of **distinct packs referenced** — measured at two for `cap` —
        never the card count (FR-040, SC-006d).
        """
        prefix = code[:2]
        for pack_code in self._prefix_map().get(prefix, ()):
            for card in self.get(pack_code).cards:
                if card.code == code:
                    return card

        # The prefix is unknown, so ask which pack this one card is in and fetch that pack.
        # Emphatically *not* a sweep of the 61 packs looking for a matching prefix: that
        # costs 61 requests at the client's one-per-second floor, for an answer one request
        # already has.
        try:
            pack_code = self.client.fetch_card_pack_code(code)
        except UpstreamError:
            return None
        if not pack_code:
            return None
        try:
            snapshot = self.get(pack_code)
        except (SnapshotUnavailable, SnapshotInvalid):
            return None
        return next((c for c in snapshot.cards if c.code == code), None)

    def _known_pack_codes(self) -> set[str]:
        """Packs whose card listing is on disk.

        `packs.json` lives in the same directory and is the pack *index*, not a pack — a
        list of `{code, name}`, which `parse_snapshot_cards` rightly refuses. Excluding it
        by name rather than by catching the refusal keeps a genuinely corrupt snapshot loud.
        """
        index_name = self.layout.pack_index().name
        return {p.stem for p in self.layout.snapshots_dir().glob("*.json") if p.name != index_name}

    def _prefix_map(self) -> dict[str, list[str]]:
        """Two-digit code prefix to the packs on disk that use it."""
        mapping: dict[str, list[str]] = {}
        for pack_code in sorted(self._known_pack_codes()):
            try:
                snapshot = self._load(self.layout.snapshot(pack_code))
            except (UnsafeIdentifier, SnapshotInvalid):
                continue
            if snapshot and snapshot.cards:
                mapping.setdefault(snapshot.cards[0].code[:2], []).append(pack_code)
        return mapping

    # --------------------------------------------------------------------- snapshots

    def get(self, pack_code: str, force_refresh: bool = False) -> PackSnapshot:
        """The pack's card listing, fetching only when freshness says to."""
        try:
            path = self.layout.snapshot(pack_code)
        except UnsafeIdentifier as exc:
            raise SnapshotUnavailable(f"pack {pack_code!r}: {exc}") from exc

        stored = self._load(path)
        if stored and not force_refresh and not self._expired(stored.fresh_until):
            # FR-039: fresh means no request is issued at all, not a cheap conditional one.
            return stored

        try:
            index = self.pack_index()
        except SnapshotUnavailable as exc:
            # Name the pack the user asked for, not the index they never heard of. FR-046's
            # refusal is only useful if it tells them which thing could not be built.
            raise SnapshotUnavailable(
                f"pack {pack_code}: the pack list is needed before card data can be "
                f"requested, and it could not be retrieved. ({exc})"
            ) from exc
        known = {e.code for e in index}
        prefixes = {c.code[:2] for c in stored.cards} if stored else None
        try:
            response = self.client.fetch_pack_cards(
                pack_code,
                known_pack_codes=known,
                if_modified_since=stored.last_modified if stored else None,
                known_pack_prefixes=prefixes,
            )
        except UpstreamError as exc:
            if stored:
                # FR-044a: old card data still prints a good pack; say it is old.
                stored.stale = True
                return stored
            raise SnapshotUnavailable(
                f"pack {pack_code}: card data could not be retrieved and none is stored. "
                f"Refusing rather than guessing what the pack contains. ({exc})"
            ) from exc

        if response.status == 304 and stored:
            # Nothing changed: keep the revision runs have pinned, extend freshness only.
            stored.fresh_until = self._fresh_until(response.max_age_s)
            self._write(path, stored)
            return stored

        assert response.cards is not None
        return self._capture(path, pack_code, response.cards, response)

    def refresh(self, pack_code: str) -> PackSnapshot:
        """The user asked (FR-044b), so freshness is not the question.

        Never mutates a snapshot a run already pinned: changed data is written under a new
        revision and the old file for that revision stays readable, so a run in flight keeps
        the composition its resolutions were made against (FR-045).
        """
        return self.get(pack_code, force_refresh=True)

    def stored(self, pack_code: str) -> PackSnapshot | None:
        """What is on disk for this pack, or None. Never fetches.

        The read half of FR-044b's pair. Separate from `get` because `get` exists to produce
        a usable snapshot by whatever means, and reporting what is held must not be able to
        issue traffic the user did not ask for.
        """
        try:
            path = self.layout.snapshot(pack_code)
        except UnsafeIdentifier:
            return None
        return self._load(path)

    def read_revision(self, pack_code: str, revision: str) -> PackSnapshot | None:
        """The exact revision a run pinned, or None if it is no longer retained."""
        current = self._load(self.layout.snapshot(pack_code))
        if current and current.revision == revision:
            return current
        archived = self.layout.snapshots_dir() / f"{pack_code}@{revision}.json"
        return self._load(archived)

    # ---------------------------------------------------------------------- interna

    def _capture(self, path, pack_code: str, cards: list[PackCard], response) -> PackSnapshot:
        previous = self._load(path)
        snapshot = PackSnapshot(
            pack_code=pack_code,
            revision=compute_revision(cards),
            cards=cards,
            captured_at=self._utcnow().isoformat(),
            fresh_until=self._fresh_until(response.max_age_s),
            last_modified=response.last_modified,
            warnings=response.warnings,
        )
        # Archive the superseded revision before overwriting, so a run that pinned it can
        # still be resumed (FR-044b, FR-045). Skipped when nothing printable changed.
        if previous and previous.revision != snapshot.revision:
            self._write(
                self.layout.snapshots_dir() / f"{pack_code}@{previous.revision}.json", previous
            )
        self._write(path, snapshot)
        return snapshot

    def _write(self, path, snapshot: PackSnapshot) -> None:
        atomic_write_json(path, snapshot.to_json())

    def _read_json(self, path) -> dict | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _load(self, path) -> PackSnapshot | None:
        """Read and **re-validate** (FR-047, and "content validated on read").

        A snapshot is a file on disk the user can edit and a partial write can truncate.
        Anything unusable returns None so the caller refetches — but a *newer schema
        version* raises, because silently refetching over a record a newer build wrote would
        discard it.
        """
        payload = self._read_json(path)
        if payload is None:
            return None

        found = payload.get("schema_version")
        if found != SCHEMA_VERSION:
            raise SnapshotUnavailable(
                f"{path.name} has schema_version {found!r}; this build understands only "
                f"{SCHEMA_VERSION!r}. Refusing rather than overwriting it."
            )
        try:
            cards, warnings = parse_snapshot_cards(
                payload.get("cards"), payload.get("pack_code", "")
            )
        except SnapshotInvalid as exc:
            raise SnapshotUnavailable(
                f"{path.name} is stored but not usable: {exc}. It is a file on disk, so it "
                "is validated on every read, not only when captured."
            ) from exc

        return PackSnapshot(
            pack_code=payload["pack_code"],
            revision=payload.get("revision") or compute_revision(cards),
            cards=cards,
            captured_at=payload.get("captured_at", ""),
            fresh_until=payload.get("fresh_until", ""),
            last_modified=payload.get("last_modified"),
            warnings=warnings,
        )

    def _fresh_until(self, max_age_s: int | None) -> str:
        seconds = max_age_s if max_age_s is not None else self.client.settings.default_max_age_s
        return (self._utcnow() + timedelta(seconds=seconds)).isoformat()

    def _expired(self, fresh_until: str | None) -> bool:
        if not fresh_until:
            return True
        try:
            return self._utcnow() >= datetime.fromisoformat(fresh_until)
        except ValueError:
            return True
