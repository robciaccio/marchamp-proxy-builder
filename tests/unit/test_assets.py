"""T014 — asset store adapter (FR-019, FR-019c, FR-019d)."""

from __future__ import annotations

import pytest

from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.assets.store import AssetUnreadable, Store


def test_local_dir_satisfies_the_store_protocol(image_dir):
    assert isinstance(LocalDirectoryStore(image_dir), Store)


def test_reads_a_present_file(image_dir):
    store = LocalDirectoryStore(image_dir)
    ref = "Heros/Test Hero_Testman/hero_front.tiff"
    assert store.exists(ref)
    assert store.describe(ref).byte_size > 0


def test_absent_file_reports_absent_rather_than_raising(image_dir):
    assert not LocalDirectoryStore(image_dir).exists("Heros/nope.tiff")


@pytest.mark.parametrize(
    "escape",
    ["../outside.tiff", "Heros/../../outside.tiff", "/etc/passwd", "Heros/./../../x.tiff"],
)
def test_paths_cannot_escape_the_configured_directory(image_dir, escape):
    # The catalog is authored data, but it is data, and it is validated like data.
    with pytest.raises(ValueError):
        LocalDirectoryStore(image_dir).open(escape)


def test_store_never_writes(image_dir):
    # FR-019c: the image directory is read-only source material.
    store = LocalDirectoryStore(image_dir)
    before = sorted(p.name for p in image_dir.rglob("*"))
    store.exists("Heros/Test Hero_Testman/hero_front.tiff")
    store.open("Heros/Test Hero_Testman/hero_front.tiff").close()
    assert sorted(p.name for p in image_dir.rglob("*")) == before


def test_format_detected_by_content_not_extension(image_dir, tmp_path):
    # FR-019d: a TIFF named .png is still a TIFF.
    src = image_dir / "Heros" / "Test Hero_Testman" / "hero_front.tiff"
    liar = image_dir / "Heros" / "Test Hero_Testman" / "actually_tiff.png"
    liar.write_bytes(src.read_bytes())
    assert (
        LocalDirectoryStore(image_dir)
        .describe("Heros/Test Hero_Testman/actually_tiff.png")
        .detected_format
        == "TIFF"
    )


def test_unreadable_file_raises_asset_unreadable(image_dir):
    bad = image_dir / "Heros" / "Test Hero_Testman" / "truncated.tiff"
    bad.write_bytes(b"II*\x00garbage")
    with pytest.raises(AssetUnreadable):
        LocalDirectoryStore(image_dir).describe("Heros/Test Hero_Testman/truncated.tiff")
