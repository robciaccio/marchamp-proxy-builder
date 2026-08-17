"""The run record (ADR 0001, FR-026b, FR-026c, FR-026e, data-model.md § Assembly Run).

One JSON file per run, replaced atomically. What makes that safe rather than merely simple
is three rules this module enforces and nothing above it may skip:

**A stale write is rejected.** Every record carries a `version`; a write asserts the version
it read and fails if the record has moved on. ADR 0001's dissent asked for this by name.
Without it, two browser tabs on one run silently lose work: the second tab's answer to one
card overwrites the first tab's answers to eleven others, and nothing reports it.

**A record from an unrecognised schema version is refused.** Never best-effort parsed. A
downgrade that reads a newer record, drops the field it does not understand, and writes it
back is data loss that presents to the user as a run mysteriously forgetting its uploads.

**A per-run lock serialises read-modify-write.** The version *detects* a conflict; the lock
*prevents* one within a single request. Both are needed and neither substitutes for the
other.

The nested `identification`, `resolutions`, and `report` are carried as plain JSON here.
Their shapes are feature 002's assembly concern (data-model.md § Resolution, § Assembly
Report) and giving this module opinions about them would make every change to the resolution
cascade a change to the storage layer.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from marchamp.store.atomic import atomic_write_json
from marchamp.store.layout import StateLayout

#: Bumped only when a record written by this version cannot be read by the previous one.
SCHEMA_VERSION = "1"


class RunNotFound(LookupError):
    """No run with that id."""


class UnreadableRunRecord(Exception):
    """Present but not safely interpretable — wrong schema version, or not valid JSON."""


class StaleWrite(Exception):
    """The record changed since it was read. The caller's copy is out of date.

    Surfaced by the API as `409`, never resolved by retrying the write with the new version
    — that would apply the change the conflict exists to question.
    """


class RunState(StrEnum):
    """data-model.md § Assembly Run § States.

    `AWAITING_PACK` and `AWAITING_CARDS` are **not** failures (FR-036): a run waiting for
    the user is a run doing exactly what it should. `COMPLETE` and `FAILED` are terminal —
    a run is never retried in place, inherited from 001's FR-020b.
    """

    IDENTIFYING = "identifying"
    UNIDENTIFIED = "unidentified"
    AWAITING_PACK = "awaiting_pack"
    RESOLVING = "resolving"
    AWAITING_CARDS = "awaiting_cards"
    READY = "ready"
    RENDERING = "rendering"
    COMPLETE = "complete"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (RunState.COMPLETE, RunState.FAILED)


class Outcome(StrEnum):
    CLEAN = "clean"
    WARNINGS = "warnings"
    REFUSED = "refused"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunRecord:
    """One attempt to assemble one pack from one hero folder."""

    id: str
    library_root: Path
    hero_folder: str
    created_at: str
    updated_at: str
    version: int = 1
    state: RunState = RunState.IDENTIFYING
    #: Null until terminal, so FR-036 can distinguish "still going" from "finished badly".
    outcome: Outcome | None = None
    identification: dict[str, Any] | None = None
    #: Pinned when the pack is confirmed, so refreshing card data cannot change a deck's
    #: composition under resolutions already made (FR-044b, FR-045).
    snapshot_revision: str | None = None
    page_size: str = "LETTER"
    fit_mode: str = "CROP"
    resolutions: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    #: `{"kind": "standard"|"saved", "id": ...}`, or absent until the run has rendered.
    pdf: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "version": self.version,
            # Retained deliberately: FR-009 forbids paths from *outside* the named library,
            # and the root itself is not outside it. FR-026b needs it to resume.
            "library_root": str(self.library_root),
            "hero_folder": self.hero_folder,
            "state": self.state.value,
            "outcome": self.outcome.value if self.outcome else None,
            "identification": self.identification,
            "snapshot_revision": self.snapshot_revision,
            "page_size": self.page_size,
            "fit_mode": self.fit_mode,
            "resolutions": self.resolutions,
            "report": self.report,
            "pdf": self.pdf,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> RunRecord:
        try:
            return cls(
                id=payload["id"],
                library_root=Path(payload["library_root"]),
                hero_folder=payload["hero_folder"],
                created_at=payload["created_at"],
                updated_at=payload["updated_at"],
                version=payload["version"],
                state=RunState(payload["state"]),
                outcome=Outcome(payload["outcome"]) if payload.get("outcome") else None,
                identification=payload.get("identification"),
                snapshot_revision=payload.get("snapshot_revision"),
                page_size=payload.get("page_size", "LETTER"),
                fit_mode=payload.get("fit_mode", "CROP"),
                resolutions=payload.get("resolutions") or [],
                report=payload.get("report") or {},
                pdf=payload.get("pdf"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise UnreadableRunRecord(f"run record is malformed: {exc}") from exc


class RunStore:
    def __init__(self, layout: StateLayout) -> None:
        self.layout = layout

    # ------------------------------------------------------------------- lifecycle

    def create(
        self,
        library_root: Path,
        hero_folder: str,
        page_size: str = "LETTER",
        fit_mode: str = "CROP",
    ) -> RunRecord:
        now = _now()
        record = RunRecord(
            id=StateLayout.new_run_id(),
            library_root=Path(library_root),
            hero_folder=str(hero_folder),
            created_at=now,
            updated_at=now,
            page_size=page_size,
            fit_mode=fit_mode,
        )
        self.layout.uploads_dir(record.id).mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.layout.run_record(record.id), record.to_json())
        return record

    def read(self, run_id: str) -> RunRecord:
        path = self.layout.run_record(run_id)
        if not path.is_file():
            raise RunNotFound(run_id)
        return self._parse(path)

    def _parse(self, path: Path) -> RunRecord:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            raise UnreadableRunRecord(f"{path.name} is not readable JSON: {exc}") from exc

        found = payload.get("schema_version") if isinstance(payload, dict) else None
        if found != SCHEMA_VERSION:
            # Refused in both directions. There is one version today, so anything else is a
            # foreign or corrupted file rather than something to migrate; when a second
            # version exists, this is where the migration goes.
            raise UnreadableRunRecord(
                f"run record has schema_version {found!r}, and this build understands only "
                f"{SCHEMA_VERSION!r}. A record written by a newer version is refused rather "
                "than partially read, because dropping a field it does not understand would "
                "silently discard the run's work. Run a build that understands it."
            )
        return RunRecord.from_json(payload)

    def write(self, record: RunRecord) -> RunRecord:
        """Persist, asserting the version the caller read. Bumps `version` on success."""
        path = self.layout.run_record(record.id)
        if not path.is_file():
            raise RunNotFound(record.id)

        current = self._parse(path)
        if current.version != record.version:
            raise StaleWrite(
                f"run {record.id} is at version {current.version}; this write carries "
                f"version {record.version}. Re-read the run and reapply the change — "
                "retrying with the new version would apply an edit made against stale data."
            )

        record.version = current.version + 1
        record.updated_at = _now()
        atomic_write_json(path, record.to_json())
        return record

    def delete(self, run_id: str) -> None:
        """Remove the run, its record, and its uploads (FR-026g).

        Never a standard PDF: that belongs to the pack, not to the run that built it
        (FR-026g1). `pdfs.py` owns that distinction.
        """
        shutil.rmtree(self.layout.run_dir(run_id), ignore_errors=True)

    def list_runs(self) -> list[RunRecord]:
        """Every readable run, newest first (FR-026c).

        A record this build cannot read is skipped rather than raised: one corrupt file must
        not make the run list unreachable, which would hide the other nine runs the user
        came to find.
        """
        runs_dir = self.layout.runs_dir()
        if not runs_dir.is_dir():
            return []
        out: list[RunRecord] = []
        for d in sorted(runs_dir.iterdir()):
            record_path = d / "run.json"
            if not record_path.is_file():
                continue
            with contextlib.suppress(UnreadableRunRecord):
                out.append(self._parse(record_path))
        out.sort(key=lambda r: r.updated_at, reverse=True)
        return out

    # ------------------------------------------------------------------------ lock

    @contextlib.contextmanager
    def lock(self, run_id: str, timeout_s: float = 10.0) -> Iterator[None]:
        """An advisory lock on one run, held for a read-modify-write.

        A lock file beside the record rather than the record itself, so acquiring the lock
        never truncates or creates the thing being protected. `flock` is advisory and
        process-scoped, which is exactly the scope needed: one local process serving one
        user, where the race is between two concurrent requests.
        """
        lock_path = self.layout.run_dir(run_id) / "run.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = lock_path.open("a+b")
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                try:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"run {run_id} is locked by another request; waited {timeout_s}s"
                        ) from None
                    time.sleep(0.01)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()
