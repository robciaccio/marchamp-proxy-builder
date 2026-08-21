"""The two sides of an identity card must not be swapped (FR-015, SC-005).

Found on 2026-08-20 by looking at the real library rather than at the fixtures derived from
it. MarvelCDB's convention is fixed — a code ending `a` is the hero side and `b` is the alter
ego — but the scan library's `_1a`/`_1b` suffixes do not always agree:

    38 heroes   `_Hero_1a`, `_Alter-Ego_1b`      suffix agrees with the label
    10 heroes   `_Alter-Ego_1a`, `_Hero_1b`      suffix is inverted
     2 heroes   `_Hero_1A`, `_Alter-Ego_1A`      same suffix on both faces

Resolution matched on the suffix alone and ignored the `Hero` / `Alter-Ego` word sitting in
the same filename, so for those twelve the printed identity card came out with its sides
reversed — silently, since both files exist and both resolve. A hero whose alter-ego side is
printed as the hero side is unplayable.

**The label wins, and the suffix breaks ties.** The label is a statement about the card; the
suffix is a filing convention this library demonstrably applies both ways round. Where a
filename carries no label — most cards, and `Phoenix Force`, an *upgrade* with `a`/`b` faces
— nothing changes and the suffix decides as before.

Ant-Man is the case that stops the fix being "prefer the label": his identity has three faces
and **two** of them are labelled Hero, `_Hero_Tiny_1a` and `_Hero_Giant_1c`. The label narrows
to those two and the suffix then separates them, which is why the fix needs both signals
rather than a swap of which one is authoritative.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

#: Heroes whose fixture filenames carry the inversion, with the code of each face and the
#: label the file for it must carry. Written from the *card data* convention (`a` is the hero
#: side), never from what the resolver happens to do.
IDENTITY_EXPECTATIONS = {
    # Phoenix: `0_Pheonix_Hero_1B.tif` / `0_Phoenix_Alter-Ego_1A.tif` — inverted, and one of
    # the ten acceptance heroes, so this has been shipping wrong.
    "phoenix": {"34001a": "Hero", "34001b": "Alter-Ego"},
    # Ant-Man: three faces, two of them labelled Hero.
    "ant": {"12001a": "Hero", "12001b": "Alter-Ego", "12001c": "Hero"},
    # A hero whose suffixes agree with its labels, so a fix that simply swapped would fail.
    "cap": {"03001a": "Hero", "03001b": "Alter-Ego"},
    "thor": {"06001a": "Hero", "06001b": "Alter-Ego"},
}


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def resolved(client, library: Path, folder: str) -> dict[str, str]:
    """Every resolution as `card_code -> file`, after pack confirmation."""
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    return {r["card_code"]: r["file"] for r in confirmed.json()["report"]["resolutions"]}


@pytest.mark.parametrize("pack_code", sorted(IDENTITY_EXPECTATIONS))
def test_each_identity_face_gets_the_file_labelled_for_it(client, scan_library, pack_code):
    """The bug, stated as the thing a player would notice.

    Asserted on the **file**, not on the card code. Codes match whichever image was chosen,
    which is why the acceptance test for these same heroes passes today with Phoenix's sides
    reversed — it compares the set of identity codes and never which image landed on which.
    """
    files = resolved(client, scan_library, ACCEPTANCE_HEROES[pack_code])

    for code, label in IDENTITY_EXPECTATIONS[pack_code].items():
        assert code in files, f"{code} did not resolve at all"
        name = Path(files[code]).name
        assert label.lower() in name.lower(), (
            f"{pack_code} {code} should be the {label} side but resolved to {name!r}. "
            "The two faces of the identity are swapped, and the printed card is unplayable."
        )


def test_ant_mans_two_hero_faces_are_told_apart(client, scan_library):
    """Both `_Hero_Tiny_1a` and `_Hero_Giant_1c` carry the same label.

    The label alone cannot separate them, so the suffix has to. This is what stops the fix
    from being "believe the label instead of the suffix" — it has to be both.
    """
    files = resolved(client, scan_library, ACCEPTANCE_HEROES["ant"])

    assert "Tiny" in files["12001a"], files["12001a"]
    assert "Giant" in files["12001c"], files["12001c"]
    assert files["12001a"] != files["12001c"]


def test_a_non_identity_card_with_a_and_b_faces_is_untouched(client, scan_library):
    """`Phoenix Force` is an *upgrade* whose two faces are `34002a` and `34002b`.

    Its files carry no Hero/Alter-Ego label, and "a is the hero side" is a fact about
    identities that would be nonsense applied here. The suffix decides, as it always did.
    """
    files = resolved(client, scan_library, ACCEPTANCE_HEROES["phoenix"])

    assert "34002a" in files and "34002b" in files
    assert files["34002a"] != files["34002b"]
    for code in ("34002a", "34002b"):
        assert "Phoenix Force" in files[code], files[code]
