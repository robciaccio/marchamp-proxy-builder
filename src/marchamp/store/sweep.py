"""Startup orphan sweep (ADR 0001 § Consequences).

ADR 0001 chose plain files over SQLite and named the debt that choice incurs: *"there is no
transaction across a record and its blobs, so a startup sweep for orphaned uploads is
owed."* This is that sweep, and it is the whole of what is owed — nothing here is
housekeeping for its own sake.

The orphan has one cause. An upload is written to `runs/<id>/uploads/<sha256>` and the
process dies before the resolution naming it reaches `run.json`. Those bytes are then
unreachable forever: the file's only name is its content digest, and the user will re-upload
rather than reconstruct it.

**Running at startup is what makes deletion safe.** No request is in flight when the process
begins, so an upload absent from its run's record is unreferenced by definition. The same
sweep running while the service is serving would delete a file in the window between the
upload landing and the resolution being recorded — causing the exact bug it exists to clean
up after. This function must not be scheduled.

Everything here deletes the user's data, so ambiguity resolves toward leaving files alone:

- a run record this build **cannot read** is skipped entirely, uploads and all. It is very
  likely from a newer build that can still finish the run, and deleting its uploads to
  reclaim a few megabytes would destroy work that is not lost;
- a **standard PDF is never swept**, whatever the runs say. It belongs to the pack
  (FR-026g1), so it looks unreferenced from every direction except the one that matters,
  and it is ~202 MB the user waited ~49 s for;
- a **saved PDF is never swept**. It is listed and deletable in its own right (FR-026g).
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from marchamp.store.layout import StateLayout
from marchamp.store.runs import RunStore, UnreadableRunRecord

#: Debris from an interrupted `atomic_write_bytes` or `_link_into_place`. Both name their
#: temporary files this way precisely so a crash leaves something identifiable.
TEMP_SUFFIX = ".tmp"


@dataclass
class SweepReport:
    """What was reclaimed. Principle V: a deletion nobody can see is indistinguishable
    from data loss, and this one runs before anybody is watching."""

    removed: list[Path] = field(default_factory=list)
    reclaimed_bytes: int = 0
    #: Runs left untouched because this build could not read their record.
    skipped_runs: list[str] = field(default_factory=list)

    def _remove_file(self, path: Path) -> None:
        with contextlib.suppress(OSError):
            size = path.stat().st_size
            path.unlink()
            self.removed.append(path)
            self.reclaimed_bytes += size

    def _remove_tree(self, path: Path) -> None:
        for p in sorted(path.rglob("*"), reverse=True):
            if p.is_file():
                self._remove_file(p)
        with contextlib.suppress(OSError):
            shutil.rmtree(path)


def sweep_state(layout: StateLayout) -> SweepReport:
    """Reclaim what no run can reach. Call once, at startup, before serving."""
    report = SweepReport()
    if not layout.root.is_dir():
        return report

    _sweep_temp_files(layout, report)
    _sweep_runs(layout, report)
    return report


def _sweep_temp_files(layout: StateLayout, report: SweepReport) -> None:
    for path in layout.root.rglob(f"*{TEMP_SUFFIX}"):
        if path.is_file():
            report._remove_file(path)


def _sweep_runs(layout: StateLayout, report: SweepReport) -> None:
    runs_dir = layout.runs_dir()
    if not runs_dir.is_dir():
        return

    store = RunStore(layout)
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue

        record_path = run_dir / "run.json"
        if not record_path.is_file():
            # No record at all: a crash between creating the directory and writing it.
            # Distinct from an unreadable record — there is nothing here a future build
            # could make sense of either.
            report._remove_tree(run_dir)
            continue

        try:
            record = store.read(run_dir.name)
        except (UnreadableRunRecord, ValueError):
            report.skipped_runs.append(run_dir.name)
            continue

        _sweep_uploads(layout, record.id, _referenced_digests(record.resolutions), report)


def _referenced_digests(resolutions: list[dict]) -> set[str]:
    """Every upload digest the record names.

    A resolution's `ref` is `upload:<sha256>` for an uploaded file and a library-relative
    path otherwise (data-model.md § Resolution), so the prefix is the discriminator.
    """
    digests: set[str] = set()
    for resolution in resolutions:
        ref = resolution.get("ref")
        if isinstance(ref, str) and ref.startswith("upload:"):
            digests.add(ref.removeprefix("upload:"))
    return digests


def _sweep_uploads(
    layout: StateLayout, run_id: str, referenced: set[str], report: SweepReport
) -> None:
    uploads = layout.uploads_dir(run_id)
    if not uploads.is_dir():
        return
    for path in sorted(uploads.iterdir()):
        if path.is_file() and path.name not in referenced:
            report._remove_file(path)
