"""A folder the walk cannot read must not silently disappear (FR-021, FR-026f, Principle V).

`os.walk` ignores errors from `scandir` unless it is given an `onerror` handler. That
default is the wrong one here, and the consequence is not a crash — it is a **confident
wrong answer**:

    a hero folder that stalls is skipped, the index comes back without it, and
    identification then correctly reports that nothing in the library matches a pack.

Reported from real use on 2026-08-19 against a Google Drive library. Three heroes came back
"not found, here are some alternatives" while others assembled cleanly, on a mount that was
demonstrably stalling — the same library produced `TimeoutError: [Errno 60]` in `digest_of`
minutes earlier. Rebuilt from that folder's real filenames, Spider-Ham verifies against its
pack at **0.95**, well clear of the 0.75 floor, so the folder was never the problem.

The constitution requires a failure to name its specific cause and forbids surfacing one as
something else. "I could not read that folder" and "that folder does not look like any pack"
are different sentences with different fixes, and the second one sends the user off to
re-check filenames that were fine all along.

Deliberately *not* a partial index with a warning. A library index that is quietly missing a
folder is exactly what produces the wrong answer above, and a warning attached to a result
the user has no reason to distrust is not much better than no warning.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from marchamp.assets.store import AssetUnreadable
from marchamp.library.index import build_index
from tests.conftest import make_card_image


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Two hero folders, so a test can lose one and still have something to find."""
    root = tmp_path / "library"
    make_card_image(root / "Heros/Odinson_Thor/Thor_Mjolnir_Upgrade_9.tiff", "M", 780, 1122)
    make_card_image(root / "Heros/Odinson_Thor/Thor_Asgard_Support_7.tiff", "A", 780, 1122)
    make_card_image(
        root / "Heros/Peter Porker_Spider-Ham/Spider-Ham_Ham It Up_Event_3.tiff", "H", 780, 1122
    )
    return root


def stall(monkeypatch: pytest.MonkeyPatch, folder_name: str) -> None:
    """Make `scandir` fail for one directory, as a stalled Drive mount does."""
    original = os.scandir

    def guarded(path=".", *args, **kwargs):
        if Path(path).name == folder_name:
            # Three-arg form, because that is what sets `filename` — and a real `scandir`
            # failure always carries the path it could not read. A two-arg fake would let
            # the handler pass a test it could not pass in production.
            raise TimeoutError(60, "Operation timed out", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", guarded)


def test_a_folder_that_cannot_be_read_is_an_error_not_an_absence(library, monkeypatch):
    """The whole bug in one assertion.

    Without an `onerror` handler this returns an index that is simply missing the folder,
    and every caller downstream treats "not in the index" as "not in the library".
    """
    stall(monkeypatch, "Peter Porker_Spider-Ham")

    with pytest.raises(AssetUnreadable) as caught:
        build_index(library, file_cap=5000)

    assert "Peter Porker_Spider-Ham" in str(caught.value), str(caught.value)


def test_the_error_names_the_folder_and_not_just_the_root(library, monkeypatch):
    """Naming the root would send the user to check a mount that is plainly working —
    the other hero folders in it read fine."""
    stall(monkeypatch, "Peter Porker_Spider-Ham")

    with pytest.raises(AssetUnreadable) as caught:
        build_index(library, file_cap=5000)

    message = str(caught.value)
    assert "Spider-Ham" in message
    assert "timed out" in message.lower() or "Operation timed out" in message


def test_a_readable_library_still_indexes_normally(library):
    """The control. Without it the test above passes on a `build_index` that always raises."""
    index = build_index(library, file_cap=5000)
    folders = {e.folder for e in index.entries}
    assert "Heros/Odinson_Thor" in folders
    assert "Heros/Peter Porker_Spider-Ham" in folders


def test_a_stalled_root_is_reported_too(tmp_path, monkeypatch):
    """The same fault at the top of the walk, where there is no partial result at all."""
    root = tmp_path / "library"
    make_card_image(root / "Heros/Odinson_Thor/Thor_Asgard_Support_7.tiff", "A", 780, 1122)
    stall(monkeypatch, "library")

    with pytest.raises(AssetUnreadable):
        build_index(root, file_cap=5000)
