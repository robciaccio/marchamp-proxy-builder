"""T032 — pack snapshots: capture, freshness, revision, refresh (FR-039, FR-044–FR-047).

The snapshot store *is* the cache. That is why no HTTP caching library is used (research
R2): a run pins a revision (FR-045), so the thing that decides when to refetch and the thing
that remembers what a run was built against have to be the same thing, and a second cache
with its own eviction policy would be free to discard what a run still depends on.

Four properties carry the requirements.

**The revision is a content hash of the reduced records, not of the response.** MarvelCDB
serves no `ETag` and `Last-Modified` moves for reasons that do not change any card. Deriving
the revision from the headers would invalidate every stored PDF on a refetch that changed
nothing — at ~202 MB and ~49 s each, that is the difference between reuse working and reuse
being theoretical (research R10, FR-026h).

**Within `max-age`, no request is issued at all.** Not a conditional one — none (FR-039,
SC-006d). Asserted here by counting requests at the transport, because a client that issues
a cheap 304 still costs the volunteer-run service a request.

**Past it, exactly one conditional request**, and a `304` keeps the revision and extends
freshness rather than rewriting anything.

**A failed refetch serves what is stored, marked stale** (FR-044a). But with nothing stored
and a failed fetch, the run is refused and the pack is named (FR-046) — guessing is the one
thing that must not happen.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from marchamp.store.layout import StateLayout
from marchamp.upstream.client import MarvelCdbClient, UpstreamUnavailable
from marchamp.upstream.snapshots import SnapshotStore, SnapshotUnavailable
from tests.conftest import SNAPSHOT_FIXTURES, UPSTREAM_LAST_MODIFIED


class FakeUpstream:
    """Counts requests, so "no request at all" is assertable rather than assumed."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None]] = []
        self.fail = False
        self.payload = json.loads((SNAPSHOT_FIXTURES / "cap.json").read_text())
        self.last_modified = UPSTREAM_LAST_MODIFIED

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            ims = request.headers.get("if-modified-since")
            self.requests.append((request.url.path, ims))
            if self.fail:
                raise httpx.ConnectError("the network is down")
            headers = {
                "cache-control": "max-age=600, public",
                "last-modified": self.last_modified,
            }
            if request.url.path == "/api/public/packs/":
                return httpx.Response(
                    200,
                    json=json.loads((SNAPSHOT_FIXTURES / "packs.json").read_text()),
                    headers=headers,
                )
            if ims == self.last_modified:
                return httpx.Response(304, headers=headers)
            return httpx.Response(200, json=self.payload, headers=headers)

        return httpx.MockTransport(handler)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        self.mono = 1000.0

    def utcnow(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.mono += seconds

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)
        self.mono += timedelta(**kwargs).total_seconds()


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def snapshots(tmp_path, upstream, clock) -> SnapshotStore:
    layout = StateLayout(tmp_path / "state")
    layout.ensure()
    client = MarvelCdbClient(
        transport=upstream.transport(),
        resolve=lambda host: ["104.21.0.1"],
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return SnapshotStore(layout=layout, client=client, utcnow=clock.utcnow)


def card_requests(upstream: FakeUpstream) -> list[tuple[str, str | None]]:
    return [r for r in upstream.requests if "cards" in r[0]]


# ------------------------------------------------------------------------- capture


def test_a_first_use_captures_the_pack(snapshots, upstream):
    snap = snapshots.get("cap")
    assert snap.pack_code == "cap"
    assert snap.cards and any(c.code == "03001a" for c in snap.cards)
    assert snap.revision and len(snap.revision) == 16
    assert snap.stale is False
    assert len(card_requests(upstream)) == 1


def test_the_captured_snapshot_is_on_disk_and_carries_no_card_text(snapshots, tmp_path):
    snapshots.get("cap")
    written = (tmp_path / "state" / "snapshots" / "cap.json").read_text()
    for banned in ("real_text", "flavor", "traits", "imagesrc", "linked_card"):
        assert banned not in written


def test_capture_aborts_and_names_the_pack_when_upstream_data_is_unusable(snapshots, upstream):
    """FR-047 — the failure surfaces here, never later at print time."""
    upstream.payload = [c for c in upstream.payload if c["type_code"] != "hero"]
    with pytest.raises(SnapshotUnavailable, match="cap"):
        snapshots.get("cap")


# ------------------------------------------------------------------------ freshness


def test_within_max_age_no_request_is_issued_at_all(snapshots, upstream):
    """FR-039, SC-006d. Not a cheap conditional request — none.

    A 304 still costs the volunteer-run service a request, so "we revalidate cheaply" is not
    what the requirement asks for.
    """
    snapshots.get("cap")
    before = len(card_requests(upstream))
    for _ in range(5):
        snapshots.get("cap")
    assert len(card_requests(upstream)) == before


def test_past_max_age_exactly_one_conditional_request_is_made(snapshots, upstream, clock):
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    snapshots.get("cap")

    conditional = [r for r in card_requests(upstream) if r[1] is not None]
    assert len(conditional) == 1
    assert conditional[0][1] == first.last_modified


def test_a_304_keeps_the_revision_and_extends_freshness(snapshots, upstream, clock):
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    revalidated = snapshots.get("cap")

    assert revalidated.revision == first.revision
    assert revalidated.stale is False
    # Freshness extended, so the next call issues nothing.
    before = len(card_requests(upstream))
    snapshots.get("cap")
    assert len(card_requests(upstream)) == before


# ------------------------------------------------------------------------- revision


def test_the_revision_is_stable_across_a_refetch_that_changed_nothing(snapshots, upstream, clock):
    """research R10 — otherwise every stored PDF is invalidated for no reason.

    `Last-Modified` moves for reasons that change no card, and there is no ETag, so a
    revision derived from the headers would be a reuse key that resets on a schedule.
    """
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    upstream.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"  # moved, contents identical
    refetched = snapshots.get("cap")

    assert refetched.last_modified != first.last_modified
    assert refetched.revision == first.revision


def test_the_revision_changes_when_a_printable_field_changes(snapshots, upstream, clock):
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    upstream.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"
    upstream.payload = [{**c, "quantity": c["quantity"] + 1} for c in upstream.payload]
    assert snapshots.get("cap").revision != first.revision


def test_the_revision_does_not_depend_on_the_order_records_arrive_in(snapshots, upstream, clock):
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    upstream.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"
    upstream.payload = list(reversed(upstream.payload))
    assert snapshots.get("cap").revision == first.revision


# --------------------------------------------------------------------------- refresh


def test_an_explicit_refresh_revalidates_even_while_fresh(snapshots, upstream):
    """FR-044b — the user asks, so freshness is not the question."""
    snapshots.get("cap")
    before = len(card_requests(upstream))
    snapshots.refresh("cap")
    assert len(card_requests(upstream)) == before + 1


def test_a_refresh_never_mutates_a_snapshot_a_run_already_pinned(snapshots, upstream, clock):
    """FR-044b, FR-045 — a run's composition cannot change under resolutions already made.

    The revision is what a run pins, and a refresh that changed something writes a *new*
    revision; the old one stays readable by the runs that pinned it.
    """
    pinned = snapshots.get("cap")
    clock.advance(seconds=601)
    upstream.last_modified = "Thu, 11 Jun 2026 09:00:00 GMT"
    upstream.payload = [{**c, "quantity": c["quantity"] + 1} for c in upstream.payload]
    refreshed = snapshots.refresh("cap")

    assert refreshed.revision != pinned.revision
    assert snapshots.read_revision("cap", pinned.revision) is not None


# ---------------------------------------------------------------------- degradation


def test_a_failed_refetch_serves_the_stored_snapshot_marked_stale(snapshots, upstream, clock):
    first = snapshots.get("cap")
    clock.advance(seconds=601)
    upstream.fail = True

    served = snapshots.get("cap")
    assert served.revision == first.revision
    # FR-044a: a run started against a stale snapshot reports it, so the flag must reach it.
    assert served.stale is True


def test_with_nothing_stored_a_failed_fetch_refuses_and_names_the_pack(snapshots, upstream):
    """FR-046 — refuse rather than guess. There is no partial pack worth printing."""
    upstream.fail = True
    with pytest.raises(SnapshotUnavailable) as exc:
        snapshots.get("cap")
    assert "cap" in str(exc.value)


def test_a_stored_snapshot_is_validated_again_when_read(snapshots, tmp_path, clock, upstream):
    """The constitution's "content validated on read" — it is a file the user can edit.

    Validating only at capture would leave every later read trusting a file nothing has
    looked at since it was written.
    """
    snapshots.get("cap")
    path = tmp_path / "state" / "snapshots" / "cap.json"
    payload = json.loads(path.read_text())
    payload["cards"] = [c for c in payload["cards"] if c["type_code"] != "hero"]
    path.write_text(json.dumps(payload))

    upstream.fail = True
    with pytest.raises(SnapshotUnavailable):
        snapshots.get("cap")


def test_a_truncated_snapshot_file_is_refused_not_half_read(snapshots, tmp_path, upstream):
    snapshots.get("cap")
    (tmp_path / "state" / "snapshots" / "cap.json").write_text('{"pack_code": "cap", "car')
    upstream.fail = True
    with pytest.raises(SnapshotUnavailable):
        snapshots.get("cap")


def test_a_snapshot_from_a_newer_schema_version_is_refused(snapshots, tmp_path, upstream):
    snapshots.get("cap")
    path = tmp_path / "state" / "snapshots" / "cap.json"
    payload = json.loads(path.read_text())
    payload["schema_version"] = "99"
    path.write_text(json.dumps(payload))
    upstream.fail = True
    with pytest.raises(SnapshotUnavailable, match="99"):
        snapshots.get("cap")


# ------------------------------------------------------------------------ pack index


def test_the_pack_index_is_cached_with_the_same_freshness_rules(snapshots, upstream, clock):
    """FR-039 applies to the index too — it is 61 rows that change a few times a year."""
    snapshots.pack_index()
    before = len([r for r in upstream.requests if "packs" in r[0]])
    snapshots.pack_index()
    assert len([r for r in upstream.requests if "packs" in r[0]]) == before

    clock.advance(seconds=601)
    snapshots.pack_index()
    assert len([r for r in upstream.requests if "packs" in r[0]]) == before + 1


def test_a_pack_code_is_checked_against_the_index_before_a_url_is_built(snapshots, upstream):
    with pytest.raises(SnapshotUnavailable):
        snapshots.get("definitely_not_a_pack")
    assert card_requests(upstream) == []


def test_the_index_is_fetched_once_for_a_run_that_captures_a_pack(snapshots, upstream):
    """SC-006d — request volume does not grow with card count."""
    snapshots.get("cap")
    assert len(upstream.requests) == 2  # the index, then the pack


def test_an_unreachable_upstream_with_no_index_stored_refuses(snapshots, upstream):
    upstream.fail = True
    with pytest.raises((SnapshotUnavailable, UpstreamUnavailable)):
        snapshots.pack_index()
