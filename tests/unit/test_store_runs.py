"""T016 — the run record (ADR 0001, FR-026b, data-model.md § Assembly Run).

A run outlives the request that created it and the process that served it, which is the
first time this project has had state at all. Three properties carry that weight:

- it **round-trips** — a resumed run knows its library, its pack, its resolutions, and its
  report, because FR-026b promises the user can walk away and come back;
- a **stale write is rejected, not silently applied**. Two browser tabs on one run is not
  exotic, and ADR 0001's dissent asked for this specifically: without it the second tab's
  answer to card 12 overwrites the first tab's answers to cards 1 through 11, and nothing
  anywhere reports that it happened;
- a record written by a **newer** schema version is **refused**, never best-effort parsed.
  A downgrade reading a field it does not understand and dropping it is data loss that
  presents as a run mysteriously losing its uploads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marchamp.store.layout import StateLayout
from marchamp.store.runs import (
    RunNotFound,
    RunState,
    RunStore,
    StaleWrite,
    UnreadableRunRecord,
)


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(StateLayout(tmp_path / "state"))


@pytest.fixture
def run(store: RunStore):
    return store.create(library_root=Path("/Volumes/Drive/Scans"), hero_folder="Heros/Wasp")


def test_a_new_run_starts_identifying_with_no_outcome(run):
    assert run.state is RunState.IDENTIFYING
    # FR-036: a run that has not reached an outcome must be distinguishable as such, so the
    # field is null rather than a third enum value meaning "not yet".
    assert run.outcome is None
    assert run.version == 1
    assert run.id and run.created_at and run.updated_at


def test_a_run_round_trips_across_a_new_store(run, store, tmp_path):
    run.state = RunState.AWAITING_CARDS
    run.snapshot_revision = "0123456789abcdef"
    run.resolutions = [{"card_code": "13001a", "provenance": "folder_position"}]
    run.report = {"omissions": []}
    store.write(run)

    # A new store object over the same directory: the same thing a restart does.
    reopened = RunStore(StateLayout(tmp_path / "state")).read(run.id)
    assert reopened.state is RunState.AWAITING_CARDS
    assert reopened.hero_folder == "Heros/Wasp"
    assert reopened.library_root == Path("/Volumes/Drive/Scans")
    assert reopened.snapshot_revision == "0123456789abcdef"
    assert reopened.resolutions == [{"card_code": "13001a", "provenance": "folder_position"}]
    assert reopened.report == {"omissions": []}


def test_writing_bumps_the_version_and_the_timestamp(run, store):
    before = run.updated_at
    store.write(run)
    assert run.version == 2
    assert run.updated_at >= before
    assert store.read(run.id).version == 2


def test_a_stale_write_is_rejected_rather_than_applied(run, store):
    """Two readers, one writer wins, and the loser is told (ADR 0001's dissent)."""
    first = store.read(run.id)
    second = store.read(run.id)

    first.state = RunState.RESOLVING
    store.write(first)

    second.state = RunState.AWAITING_PACK
    with pytest.raises(StaleWrite) as exc:
        store.write(second)
    assert "version" in str(exc.value).lower()

    # And the winner's write survived intact rather than being half-overwritten.
    assert store.read(run.id).state is RunState.RESOLVING


def test_a_rejected_write_leaves_the_record_exactly_as_it_was(run, store):
    first = store.read(run.id)
    stale = store.read(run.id)
    store.write(first)
    on_disk = store.layout.run_record(run.id).read_bytes()

    stale.resolutions = [{"card_code": "ruined"}]
    with pytest.raises(StaleWrite):
        store.write(stale)
    assert store.layout.run_record(run.id).read_bytes() == on_disk


def test_a_record_from_a_newer_schema_version_is_refused(run, store):
    path = store.layout.run_record(run.id)
    payload = json.loads(path.read_text())
    payload["schema_version"] = "99"
    path.write_text(json.dumps(payload))

    with pytest.raises(UnreadableRunRecord) as exc:
        store.read(run.id)
    # The message has to say what to do, because the fix is "run a newer marchamp", and
    # nothing else the application can print would lead the user there.
    assert "99" in str(exc.value)


def test_a_record_from_an_older_schema_version_is_also_refused_for_now(run, store):
    """There is one schema version, so anything else is a corrupted or foreign file.

    When a second version exists this becomes a migration and this test changes with it.
    Refusing today is the fail-closed reading; guessing is not.
    """
    path = store.layout.run_record(run.id)
    payload = json.loads(path.read_text())
    payload["schema_version"] = "0"
    path.write_text(json.dumps(payload))
    with pytest.raises(UnreadableRunRecord):
        store.read(run.id)


def test_a_truncated_record_is_refused_not_half_read(run, store):
    store.layout.run_record(run.id).write_text('{"schema_version": "1", "id":')
    with pytest.raises(UnreadableRunRecord):
        store.read(run.id)


def test_reading_a_run_that_does_not_exist_says_so(store):
    with pytest.raises(RunNotFound):
        store.read("0" * 32)


def test_the_per_run_lock_excludes_a_second_holder(run, store):
    """Serialises the read-modify-write the optimistic version only *detects*.

    The version stops a stale write from being applied; the lock stops two writers from
    interleaving inside one request and both believing they read the current version.
    """
    with store.lock(run.id), pytest.raises(TimeoutError), store.lock(run.id, timeout_s=0.05):
        pass  # pragma: no cover - reaching here is the failure


def test_the_lock_is_released_even_when_the_body_raises(run, store):
    with pytest.raises(ValueError), store.lock(run.id):
        raise ValueError("something went wrong mid-run")
    with store.lock(run.id, timeout_s=0.05):
        pass  # acquired, so the first hold was released


def test_two_runs_do_not_block_each_other(store):
    a = store.create(library_root=Path("/lib"), hero_folder="Heros/Thor")
    b = store.create(library_root=Path("/lib"), hero_folder="Heros/Hulk")
    with store.lock(a.id), store.lock(b.id, timeout_s=0.05):
        pass


def test_runs_are_listed_newest_first(store):
    made = [
        store.create(library_root=Path("/lib"), hero_folder=f"Heros/{n}")
        for n in ("Thor", "Hulk", "Wasp")
    ]
    listed = store.list_runs()
    assert {r.id for r in listed} == {r.id for r in made}
    assert [r.updated_at for r in listed] == sorted((r.updated_at for r in listed), reverse=True)


def test_an_unreadable_record_does_not_break_the_run_list(store, run):
    """FR-026c lists every run. One corrupt file must not hide the other nine."""
    broken = store.create(library_root=Path("/lib"), hero_folder="Heros/Hulk")
    store.layout.run_record(broken.id).write_text("not json at all")
    listed = store.list_runs()
    assert [r.id for r in listed] == [run.id]


def test_deleting_a_run_removes_its_directory_and_its_uploads(store, run):
    upload = store.layout.upload(run.id, "c" * 64)
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"an uploaded scan")

    store.delete(run.id)
    assert not store.layout.run_dir(run.id).exists()
    with pytest.raises(RunNotFound):
        store.read(run.id)


def test_the_library_root_is_retained_and_the_hero_folder_stays_relative(run):
    """FR-009 forbids a path from *outside* the named library; the root is not outside it.

    Retaining it is required (FR-026b): a resumed run has to know which library it was
    reading, and has to be able to name it when the mount has gone.
    """
    assert run.library_root.is_absolute()
    assert not Path(run.hero_folder).is_absolute()
