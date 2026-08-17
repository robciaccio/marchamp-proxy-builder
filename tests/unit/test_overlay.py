"""T022 — the overlay asset store (FR-004, FR-007, FR-026e, research R8).

A run's faces come from two roots that are not related to each other: the scan library the
user named, and the run's own directory holding files they uploaded for cards the library
lacks. Composition must read both without knowing either is a directory, which is what
Principle III's adapter is for and what feature 001 never actually needed.

The prefix is the whole of the routing rule. `upload:<sha256>` means the run's own uploads;
anything else is a path relative to the library root. Two roots means **two containment
checks**, not one applied twice: the library ref is user-influenced data and must not escape
the folder the run named (FR-007), while an upload ref is a digest this application wrote and
is checked against its own shape rather than against a path.

Pickling matters and is easy to miss. Decode and render run in a `ProcessPoolExecutor` with
`spawn`, so the store crosses a process boundary by value. A store holding a closure, an open
handle, or a lock works perfectly in every test that does not use the pool and fails in the
one place it counts.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from marchamp.assets.overlay import OverlayStore
from marchamp.assets.store import AssetMissing, Store

DIGEST = "a" * 64


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state" / "runs" / "9f2c40a1b7e5486dbc31a0f7d24e8b56"
    (d / "uploads").mkdir(parents=True)
    return d


@pytest.fixture
def overlay(library_root: Path, run_dir: Path) -> OverlayStore:
    return OverlayStore(library_root=library_root, run_dir=run_dir)


@pytest.fixture
def uploaded(run_dir: Path, library_root: Path) -> str:
    """A file the user supplied for a card the library does not hold."""
    source = next(library_root.rglob("*.tiff"))
    (run_dir / "uploads" / DIGEST).write_bytes(source.read_bytes())
    return f"upload:{DIGEST}"


LIBRARY_REF = "Heros/Steve Rogers_Captain America/Leadership_Make the Call_Event_16.tiff"


def test_it_is_a_store(overlay):
    assert isinstance(overlay, Store)


def test_an_ordinary_ref_resolves_inside_the_library(overlay):
    assert overlay.exists(LIBRARY_REF)
    assert overlay.describe(LIBRARY_REF).width_px > 0
    with overlay.open(LIBRARY_REF) as fh:
        assert fh.read(4)


def test_an_upload_ref_resolves_inside_the_run(overlay, uploaded):
    assert overlay.exists(uploaded)
    assert overlay.describe(uploaded).byte_size > 0


def test_the_two_roots_do_not_see_each_other(overlay, uploaded):
    # An upload digest is not a library path and must not be looked for as one.
    assert not overlay.exists(DIGEST)
    # And a library path is not an upload, even one that happens to be 64 hex characters.
    assert not overlay.exists(f"upload:{'b' * 64}")


def test_a_missing_upload_is_missing_not_searched_for_in_the_library(overlay):
    with pytest.raises(AssetMissing):
        overlay.open(f"upload:{'c' * 64}")


@pytest.mark.parametrize(
    "escape",
    [
        "../outside.tiff",
        "Heros/../../outside.tiff",
        "/etc/passwd",
        "Heros/./../../x.tiff",
    ],
)
def test_a_library_ref_cannot_escape_the_named_library(overlay, escape):
    """FR-007 — the library root is the run's containment boundary."""
    with pytest.raises(ValueError):
        overlay.open(escape)


@pytest.mark.parametrize(
    "hostile",
    [
        "upload:../../../etc/passwd",
        "upload:/etc/passwd",
        "upload:..",
        "upload:",
        "upload:not-a-digest",
        f"upload:{'A' * 64}",
    ],
)
def test_an_upload_ref_that_is_not_a_digest_is_refused(overlay, hostile):
    """Checked against its shape, not against a path.

    An upload's name is a SHA-256 this application computed and wrote. Anything else did not
    come from here, so validating the shape refuses the whole class rather than the
    traversal sequences someone thought of.
    """
    with pytest.raises(ValueError):
        overlay.open(hostile)


def test_it_never_writes(overlay, library_root, run_dir, uploaded):
    """FR-001 — the library is read-only source material, and so is a stored upload."""
    before = sorted(p.relative_to(library_root) for p in library_root.rglob("*"))
    overlay.exists(LIBRARY_REF)
    overlay.open(LIBRARY_REF).close()
    overlay.describe(uploaded)
    assert sorted(p.relative_to(library_root) for p in library_root.rglob("*")) == before


def test_it_survives_a_process_boundary(overlay, uploaded):
    """Decode and render run under `spawn`, so the store is pickled by value.

    A store holding an open handle or a lock passes every test that does not use the worker
    pool and fails in the only place that matters.
    """
    revived = pickle.loads(pickle.dumps(overlay))
    assert revived.exists(LIBRARY_REF)
    assert revived.exists(uploaded)
    assert revived.describe(uploaded).byte_size == overlay.describe(uploaded).byte_size


def test_a_finished_run_can_read_its_uploads_with_the_library_unmounted(
    run_dir, tmp_path, uploaded
):
    """SC-006h — the Drive is not always there, and a finished run must not need it."""
    gone = tmp_path / "not-mounted"
    overlay = OverlayStore(library_root=gone, run_dir=run_dir)
    assert overlay.exists(uploaded)
    assert not overlay.exists(LIBRARY_REF)


def test_format_is_detected_by_content_for_both_roots(overlay, run_dir, library_root):
    """FR-019d, and FR-028's "manual choice bypasses discovery, never validation".

    An uploaded file is the least trustworthy input this application has: it arrived over
    HTTP with a name and a declared type the user's browser chose.
    """
    source = next(library_root.rglob("*.tiff"))
    liar = run_dir / "uploads" / ("d" * 64)
    liar.write_bytes(source.read_bytes())
    assert overlay.describe(f"upload:{'d' * 64}").detected_format == "TIFF"
