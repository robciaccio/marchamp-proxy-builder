"""T115 — all ten acceptance heroes over the derived fixture library (SC-002, SC-003, SC-003c).

SC-003b splits the acceptance evidence in two on purpose. The real library is the thing the
criteria are *about*, and it is on the user's machine — `test_real_library.py` drives it and
never runs in CI. This file is the regression guard: the same ten heroes over T005's derived
fixtures, which carry the real library's filenames and folder layout over generated images.
It catches a resolver regression without the scans present, and it is not a substitute for
the other one.

**The one thing this file must not do is agree with a bug.** A run over Hulk that reported a
decklist card would be silently wrong — Hulk's folder holds no decklist scan, so a report
claiming one means the tool found something that is not a deck list and printed it as one.
So the decklist expectation is stated per hero, from what the folders were measured to hold
(SC-002a), rather than derived from what the run happens to say.

Likewise the identification: every hero is checked against a hand-written pack code, so a
resolver that identified `wsp` as `cap` and then resolved 60 cap cards cleanly would fail
here rather than pass with a full report.

**What the fixture cannot cover, named rather than hidden.** Five cards across four heroes
resolve only through a `duplicated_by` link into a pack T005 does not derive, and their scans
live in no folder it carries. They are listed in `FIXTURE_GAPS` and supplied by upload so the
run can reach a PDF; the list is exact, so a *sixth* gap — a real regression — fails. Against
the mounted library these five resolve on their own, which is what T121 exists to show.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from marchamp.api.app import create_app
from marchamp.assembly.decklist import HALL_OF_HEROES_URL
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES, LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, pack_cards

#: Measured 2026-08-16 and restated in SC-002a: 25 of 60 hero folders hold no decklist scan,
#: and two of the ten acceptance heroes are among them. Hand-written, because deriving it
#: from the run is how a test comes to agree with the bug it should catch.
HEROES_WITHOUT_A_DECKLIST_SCAN = frozenset({"hlk", "phoenix"})

#: Cards the derived fixture cannot resolve, per hero. Every one is the same shape: the
#: card's own folder holds no scan of it, and its only reprint route is a `duplicated_by`
#: link into a pack T005 does not carry. A T005 coverage limit, not a resolver shortfall.
FIXTURE_GAPS: dict[str, frozenset[str]] = {
    "cap": frozenset({"03032"}),  # Followed -> 30018, Spider-Ham's pack
    "msm": frozenset({"05032"}),  # Morale Boost -> 29019
    "stld": frozenset({"17020", "17022"}),  # Cosmo, Knowhere -> 22020, 22021
    "wonder_man": frozenset({"58034"}),  # Avengers Compound -> 59032
}

#: The four things SC-002a names. Used here as a *set* — the ordering is `expand_pack`'s and
#: is asserted in `tests/unit/test_faces.py`, while the report is sorted by card code so that
#: the same run always renders the same report (Principle V).
SC_002A_GROUPS = frozenset({"player", "identity", "nemesis", "decklist"})


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    """Neither `MARCHAMP_IMAGE_DIR` nor `MARCHAMP_CATALOG` set (SC-003a)."""
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    assert settings.image_dir is None and settings.catalog_path is None
    with TestClient(create_app(settings)) as client:
        yield client


def card_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (LIBRARY_IMAGE_W, LIBRARY_IMAGE_H), (18, 32, 84)).save(buffer, format="TIFF")
    return buffer.getvalue()


def start(client, library: Path, folder: str) -> dict:
    created = client.post(
        "/api/assemblies", json={"library_root": str(library), "hero_folder": folder}
    )
    assert created.status_code == 202, created.text
    return created.json()


def confirm_pack(client, run: dict) -> dict:
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    return confirmed.json()


def fill(client, run: dict, expected_gaps: frozenset[str]) -> dict:
    """Supply a file for each known fixture gap, and refuse to paper over any other.

    The assertion is the point. Uploading whatever is left would turn a resolver regression
    into a passing test with one more upload in it.
    """
    assert {u["card_code"] for u in run["unresolved"]} == set(expected_gaps), (
        f"unexpected gaps: {sorted({u['card_code'] for u in run['unresolved']})} against "
        f"the {sorted(expected_gaps)} this fixture is known not to carry"
    )
    while run["unresolved"]:
        gap = run["unresolved"][0]
        response = client.post(
            f"/api/assemblies/{run['id']}/cards/{gap['card_code']}/image",
            files={"file": (f"{gap['card_code']}.tiff", card_bytes(), "image/tiff")},
            data={"side": gap["side"]},
            headers={"If-Match": str(run["version"])},
        )
        assert response.status_code == 200, response.text
        run = response.json()
    return run


def render(client, run: dict) -> dict:
    """Confirm and print.

    A run that needed an upload is customized (FR-026i), so its PDF is not the pack's
    standard one and has to be named. Reading that off the run rather than off the hero is
    deliberate: it keeps this helper honest if a hero's fixture gap ever closes.
    """
    body = {"save_as": f"{run['hero_folder']} (fixture uploads)"} if run["customized"] else {}
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json=body,
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    return done.json()


@pytest.mark.parametrize(("pack_code", "folder"), sorted(ACCEPTANCE_HEROES.items()))
def test_each_acceptance_hero_identifies_and_prints(client, scan_library, pack_code, folder):
    """SC-002, SC-003, SC-003c, SC-002a, SC-006j — one run per hero, end to end.

    Written as one test per hero rather than one loop, so a failure names the hero. The four
    SC-002 heroes resolve from their own folders and reprint links, the four SC-003 heroes
    need whole-library search and name fallback, and the two SC-003c heroes carry no usable
    positions at all — three different code paths behind one identical assertion.

    Every claim about a hero is made against **one** run of it. Splitting the decklist
    assertions into their own parametrized tests read more tidily and rendered each of the
    ten heroes twice, which is a minute of CI to learn nothing the first render had not
    already shown.
    """
    run = confirm_pack(client, start(client, scan_library, folder))

    identification = run["identification"]
    assert identification["pack_code"] == pack_code, (
        f"{folder} identified as {identification['pack_code']}; a confident wrong "
        "identification prints a complete-looking pack of the wrong hero (SC-009)"
    )

    # SC-002a, measured 2026-08-17: eight of the ten folders hold a decklist scan, Hulk's
    # and Phoenix's do not. Stated per hero rather than read off the run — a run over Hulk
    # that reported a decklist card would be the tool having found something that is not a
    # deck list and printed it as one, and a test that believed the run would agree with it.
    has_scan = pack_code not in HEROES_WITHOUT_A_DECKLIST_SCAN
    assert (run["decklist_candidate"] is not None) is has_scan, (
        f"{pack_code}: decklist candidate {run['decklist_candidate']!r} contradicts what "
        "this folder was measured to hold (SC-002a)"
    )
    if has_scan:
        # FR-013d: the tool proposes and the user accepts. FR-013e: accepting the tool's own
        # candidate is not customization, so this run still produces the pack's standard PDF.
        decided = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        )
        assert decided.status_code == 200, decided.text
        run = decided.json()

    run = fill(client, run, FIXTURE_GAPS.get(pack_code, frozenset()))
    assert run["state"] == "ready", run["state"]
    finished = render(client, run)

    assert finished["state"] == "complete"
    document = client.get(f"/api/assemblies/{finished['id']}/document")
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF"), "the run reported complete with no document"

    report = finished["report"]
    assert report["cards_printed"] == report["cards_in_pack"], (
        "every card in the pack listing must be accounted for; omissions are a separate act"
    )
    assert report["omitted"] == []
    assert report["page_count"] >= 1

    # FR-013c, SC-006j — the absence is named, addressed, and not fatal. Three claims, and
    # the third is easy to get wrong in either direction: a run that refused would make 25 of
    # 60 heroes unprintable, and a run that said nothing would leave the user believing they
    # had a complete pack. The address is offered *only* when it is needed — telling someone
    # to go and fetch a thing they are holding is how people learn to stop reading reports.
    assert report["decklist_printed"] is has_scan
    assert report["decklist_source_url"] == (None if has_scan else HALL_OF_HEROES_URL)
    printed_decklists = [r for r in report["resolutions"] if r["group"] == "decklist"]
    assert len(printed_decklists) == (1 if has_scan else 0)


def test_the_printed_pack_carries_all_four_of_the_things_sc_002a_names(client, scan_library):
    """SC-002a — player cards, a complete identity, the nemesis set, and the decklist card.

    Composition, not order. The *order* is a property of `expand_pack`, which sorts on
    `(group, position, code)` and is asserted directly in `tests/unit/test_faces.py`; the
    report is deliberately sorted by card code instead, so that the same run always renders
    the same report (Principle V). Asserting order here would be asserting it of the wrong
    artefact.

    The identity is the part worth checking end to end. It is one physical card with as many
    faces as its card data records — two for Thor, three for Ant-Man — and those faces are
    separate codes in a `linked_codes` chain rather than sides of one record. So a resolver
    that stopped at the hero side would print a hero with no alter-ego, and the report would
    still say one identity card. The expected codes are read off the pack listing rather than
    off the run, so the assertion cannot agree with the bug.
    """
    run = confirm_pack(client, start(client, scan_library, ACCEPTANCE_HEROES["thor"]))
    decided = client.post(
        f"/api/assemblies/{run['id']}/decklist",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert decided.status_code == 200, decided.text
    report = render(client, decided.json())["report"]

    assert {r["group"] for r in report["resolutions"]} == SC_002A_GROUPS, (
        f"a group is missing entirely: {sorted({r['group'] for r in report['resolutions']})}"
    )
    hero = next(c for c in pack_cards("thor") if c.type_code == "hero")
    expected_identity = {hero.code, *hero.linked_codes}
    identity = {
        r["card_code"]: r["file"] for r in report["resolutions"] if r["group"] == "identity"
    }
    assert set(identity) == expected_identity, (
        f"the identity printed {sorted(identity)} against the {sorted(expected_identity)} "
        "its card data records. A hero side with no alter-ego side is unplayable, and the "
        "report would still say one identity card"
    )
    # Which image landed on which side, not only that both codes resolved. Comparing codes
    # alone is what let Phoenix ship with its two faces swapped: both files exist, both
    # resolve, and the set of codes is identical either way (2026-08-20). The sides are
    # asserted for every acceptance hero in `test_identity_faces.py`; this line exists so
    # that the test which *claims* to check the identity cannot pass on a swap.
    assert "hero" in identity[hero.code].lower(), identity[hero.code]
    for code in hero.linked_codes:
        assert "alter-ego" in identity[code].lower(), identity[code]
    assert report["faces_printed"] >= report["cards_printed"], (
        "a double-sided card is one card and two faces (SC-006a)"
    )
