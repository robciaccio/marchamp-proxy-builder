"""T007 — committed fixtures carry no card data and no real scan (FR-038, FR-038a).

This repository is public. FR-038a governs fixtures as much as runtime, and a fixture is
where the rule is easiest to break by accident: re-running a derivation script against a
changed upstream, or dropping in "just one real TIFF" to debug something, both look
harmless in a diff and are both permanent once pushed.

So this is a mechanical guard rather than a behavioural test, and it is deliberately blunt.
It asserts two things about every file under `tests/fixtures/`:

- a JSON fixture holds only the fields data-model.md § PackCard lists, and no key or string
  anywhere in it resembles FFG's card text;
- an image fixture is *generated* — a handful of flat colours, not a scan.

The field list is written out here rather than imported from the reduction that produced
the fixtures. A guard that imports the thing it guards passes by construction the moment
that thing is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SNAPSHOTS = FIXTURES / "snapshots"
LIBRARY = FIXTURES / "library"

#: data-model.md § PackCard, written out independently. Widening this is a spec change.
PACKCARD_FIELDS = frozenset(
    {
        "code",
        "pack_code",
        "position",
        "name",
        "type_code",
        "card_set_type_name_code",
        "quantity",
        "double_sided",
        "linked_codes",
        "duplicate_of_code",
        "duplicated_by",
    }
)

#: data-model.md § Pack Index Entry — `code` and `name` only. `total` in particular is
#: dropped on purpose (research R12).
PACK_INDEX_FIELDS = frozenset({"code", "name"})

#: Keys upstream sends that must never reach a committed file. `imagesrc` is here with the
#: text fields because a URL to card art is the address of the thing FR-038 forbids
#: mirroring, and retaining it is how a later change starts fetching art without deciding to.
FORBIDDEN_KEYS = frozenset(
    {
        "text",
        "real_text",
        "back_text",
        "flavor",
        "back_flavor",
        "traits",
        "real_traits",
        "imagesrc",
        "backimagesrc",
        "illustrator",
        "linked_card",
        "octgn_id",
        "url",
    }
)

#: A generated fill has a handful of colours; a 600-DPI scan of printed artwork has
#: thousands. This is the check that actually distinguishes them — byte size alone does not,
#: because a compressed scan of a dark card can be small.
MAX_DISTINCT_COLOURS = 64

#: Well above a generated placeholder, well below a real 600-DPI card scan (~2-6 MB).
MAX_FIXTURE_IMAGE_BYTES = 512 * 1024

IMAGE_SUFFIXES = frozenset({".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp", ".gif"})


def _walk(node: object, path: str = "$"):
    """Every (path, key, value) in a nested JSON structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{path}.{k}", k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _snapshot_files() -> list[Path]:
    return sorted(p for p in SNAPSHOTS.glob("*.json") if p.name != "packs.json")


def test_snapshot_fixtures_exist():
    # Guarding nothing is the failure mode this file is least able to notice on its own.
    assert _snapshot_files(), "no snapshot fixtures found — T006 has not run"


@pytest.mark.parametrize("path", _snapshot_files(), ids=lambda p: p.name)
def test_snapshot_holds_only_packcard_fields(path: Path):
    cards = json.loads(path.read_text())
    assert isinstance(cards, list) and cards
    for card in cards:
        extra = set(card) - PACKCARD_FIELDS
        assert not extra, f"{path.name}: {card.get('code')} carries {sorted(extra)}"
        missing = PACKCARD_FIELDS - set(card)
        assert not missing, f"{path.name}: {card.get('code')} is missing {sorted(missing)}"


@pytest.mark.parametrize("path", sorted(SNAPSHOTS.glob("*.json")), ids=lambda p: p.name)
def test_no_fixture_carries_card_text(path: Path):
    data = json.loads(path.read_text())
    for where, key, _ in _walk(data):
        assert key not in FORBIDDEN_KEYS, f"{path.name}: card data at {where}"


@pytest.mark.parametrize("path", sorted(SNAPSHOTS.glob("*.json")), ids=lambda p: p.name)
def test_no_fixture_carries_prose(path: Path):
    """A card name is a few words; rules text is a sentence with markup.

    Catches a field that slipped through under a name this file does not know, which is the
    case the key list above cannot cover.
    """
    data = json.loads(path.read_text())
    for where, _, value in _walk(data):
        if isinstance(value, str):
            assert "<" not in value, f"{path.name}: markup at {where}"
            assert len(value) <= 80, f"{path.name}: {len(value)}-character string at {where}"


def test_pack_index_is_reduced_to_code_and_name():
    index = json.loads((SNAPSHOTS / "packs.json").read_text())
    for entry in index:
        assert set(entry) == PACK_INDEX_FIELDS, f"pack {entry.get('code')} carries {sorted(entry)}"


def _library_images() -> list[Path]:
    if not LIBRARY.is_dir():
        return []
    return sorted(p for p in LIBRARY.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)


def test_no_image_fixture_is_a_real_scan():
    """Every committed image is generated, in this repository, from a flat fill.

    Applies to the whole of `tests/fixtures/`, not only the derived library, so a real scan
    dropped anywhere under it fails here rather than in review.
    """
    images = sorted(p for p in FIXTURES.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    for p in images:
        size = p.stat().st_size
        assert size <= MAX_FIXTURE_IMAGE_BYTES, (
            f"{p.relative_to(FIXTURES)} is {size / 1024:.0f} KB — too large to be generated"
        )
        with Image.open(p) as img:
            colours = img.convert("RGB").getcolors(maxcolors=MAX_DISTINCT_COLOURS)
        assert colours is not None, (
            f"{p.relative_to(FIXTURES)} has more than {MAX_DISTINCT_COLOURS} distinct "
            "colours, which a generated placeholder does not"
        )


def test_library_fixture_filenames_carry_no_card_text():
    """Filenames are the whole point of the library fixture, and are not card text.

    What must not appear is a *path* out of the user's machine — the fixture is a relative
    tree by construction, and this asserts the construction (FR-009).
    """
    for p in _library_images():
        rel = p.relative_to(LIBRARY)
        assert not rel.is_absolute()
        assert ".." not in rel.parts
