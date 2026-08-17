"""Shared fixtures.

Every image here is GENERATED, never copied from the real card library. The constitution
prohibits card artwork entering this repository absolutely, and the obvious shortcut —
dropping a few real TIFFs into tests/ — would violate that permanently and irreversibly.

Synthetic images deliberately mimic the real scans' awkward property: they are ~2.7% taller
in proportion than a standard card, so the fit-mode logic is exercised by fixtures rather
than only by hand.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

# Matches the measured Captain America pack scans: 1446x2079 @ 600 DPI, ratio 1.4378.
SOURCE_W, SOURCE_H = 1446, 2079
SOURCE_DPI = 600

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT_FIXTURES = FIXTURES / "snapshots"


def make_card_image(path: Path, label: str, width: int = SOURCE_W, height: int = SOURCE_H) -> Path:
    """Write a synthetic full-bleed card face.

    Full-bleed on purpose: art runs to all four edges, like the real scans, so `crop` mode
    has something to lose and tests can detect it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), (18, 32, 84))
    d = ImageDraw.Draw(img)
    # Edge bands let a test detect how much `crop` trimmed off top and bottom.
    band = max(1, height // 40)
    d.rectangle([0, 0, width, band], fill=(220, 40, 40))
    d.rectangle([0, height - band, width, height], fill=(220, 40, 40))
    d.rectangle(
        [band * 2, band * 2, width - band * 2, height - band * 2], outline=(255, 255, 255), width=6
    )
    d.text((width // 8, height // 2), label, fill=(255, 255, 255))
    img.save(path, format="TIFF", dpi=(SOURCE_DPI, SOURCE_DPI))
    return path


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """A card image directory laid out like the real Drive mirror."""
    root = tmp_path / "images"
    pack = root / "Heros" / "Test Hero_Testman"
    core = root / "Core Set" / "Aspects" / "Basic-Grey"

    make_card_image(pack / "hero_front.tiff", "HERO")
    make_card_image(pack / "hero_back.tiff", "ALTER-EGO")
    for i in range(1, 5):
        make_card_image(pack / f"sig_{i}.tiff", f"SIG{i}")
    # Stand-in art living in its own pack folder — never copied into the deck folder.
    make_card_image(core / "grey_energy.tiff", "ENERGY")
    return root


def _catalog_dict() -> dict:
    """Deck of 8 faces: hero (double-sided, 2 faces) + 4 sig (6 copies total)."""
    return {
        "schema_version": "1",
        "cards": [
            {
                "id": "testman",
                "name": "Testman",
                "double_sided": True,
                "printings": [
                    {
                        "id": "testman@pack",
                        "pack": "Testman Hero Pack",
                        "number": "1a",
                        "image": "Heros/Test Hero_Testman/hero_front.tiff",
                        "image_back": "Heros/Test Hero_Testman/hero_back.tiff",
                    }
                ],
            },
            *[
                {
                    "id": f"sig{i}",
                    "name": f"Signature {i}",
                    "double_sided": False,
                    "printings": [
                        {
                            "id": f"sig{i}@pack",
                            "pack": "Testman Hero Pack",
                            "number": str(i + 1),
                            "image": f"Heros/Test Hero_Testman/sig_{i}.tiff",
                        }
                    ],
                }
                for i in range(1, 5)
            ],
            {
                # Preferred pack art is absent from disk; the Core Set printing stands in.
                "id": "energy",
                "name": "Energy",
                "double_sided": False,
                "printings": [
                    {
                        "id": "energy@pack",
                        "pack": "Testman Hero Pack",
                        "number": "20",
                        "image": "Heros/Test Hero_Testman/energy_missing.tiff",
                    },
                    {
                        "id": "energy@core",
                        "pack": "Core Set",
                        "number": "88",
                        "image": "Core Set/Aspects/Basic-Grey/grey_energy.tiff",
                    },
                ],
            },
        ],
        "decks": [
            {
                "id": "testman-deck",
                "name": "Testman",
                "hero_card_id": "testman",
                "entries": [
                    {"card_id": "testman", "preferred_printing_id": "testman@pack", "quantity": 1},
                    {"card_id": "sig1", "preferred_printing_id": "sig1@pack", "quantity": 2},
                    {"card_id": "sig2", "preferred_printing_id": "sig2@pack", "quantity": 1},
                    {"card_id": "sig3", "preferred_printing_id": "sig3@pack", "quantity": 1},
                    {"card_id": "sig4", "preferred_printing_id": "sig4@pack", "quantity": 1},
                    {"card_id": "energy", "preferred_printing_id": "energy@pack", "quantity": 1},
                ],
            }
        ],
    }


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(_catalog_dict(), indent=2))
    return p


@pytest.fixture
def catalog_dict() -> dict:
    return _catalog_dict()


# --------------------------------------------------------------- feature 002 fixtures


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An app-owned state directory, isolated per test (ADR 0001).

    Exported as `MARCHAMP_STATE_DIR` as well as returned, because the refusal-to-start and
    default-resolution paths read the environment rather than taking an argument, and a test
    that forgot to isolate it would write run records into the developer's real
    `~/Library/Application Support/marchamp`.
    """
    d = tmp_path / "state"
    monkeypatch.setenv("MARCHAMP_STATE_DIR", str(d))
    return d


#: The scan library's real awkwardness, reproduced verbatim as filenames (research R5, R11).
#: Every entry here was measured on 2026-08-16/17 and each one exists to defeat a plausible
#: shortcut, so changing one to something tidier deletes a test without failing it:
#:
#: - three filename conventions, one of which numbers physical copies rather than positions;
#: - the three observed typos, at Levenshtein distance 1-2 from the canonical name;
#: - a `.tif`/`.tiff` pair of one card (FR-034 duplicate rendition, not FR-033 conflict);
#: - Vision's `Vivian` recorded at position 2 when the card is at 3, colliding with the
#:   genuinely double-sided Intangible filed as `_2a`/`_2b`;
#: - Quincarrier filed under Wasp though it belongs to another hero;
#: - both spellings of the decklist scan, and one hero folder holding none;
#: - `Aspects/`, where a position means nothing because there is no pack to read it against.
LIBRARY_TREE: tuple[str, ...] = (
    # Form A: {faction}_{Name}_{Type}_{position}, with a/b suffixes for the two codes of one
    # physical card.
    "Heros/Steve Rogers_Captain America/Captain America_Captain America_Hero_1a.tiff",
    "Heros/Steve Rogers_Captain America/Captain America_Steve Rogers_Alter-Ego_1b.tiff",
    "Heros/Steve Rogers_Captain America/Captain America_Agent 13_Ally_2.tiff",
    "Heros/Steve Rogers_Captain America/Leadership_Make the Call_Event_16.tiff",
    # A .tif/.tiff pair of one card: one rendition is chosen, the duplication is reported.
    "Heros/Steve Rogers_Captain America/Leadership_The Power of Leadership_Upgrade_18.tif",
    "Heros/Steve Rogers_Captain America/Leadership_The Power of Leadership_Upgrade_18.tiff",
    # Typo: canonical name is "Steve's Apartment".
    "Heros/Steve Rogers_Captain America/Captain America_Steve_s Apartament_Support_9.tiff",
    "Heros/Steve Rogers_Captain America/captain america decklist.tif",
    # Form B: {faction}_{Name}_{Type}_{position}_{set_position}.{set_total}
    "Heros/Janet Van Dyne_Wasp/Wasp_Wasp_Hero_1a.tiff",
    "Heros/Janet Van Dyne_Wasp/Wasp_Janet Van Dyne_Alter-Ego_1b.tiff",
    "Heros/Janet Van Dyne_Wasp/Wasp_Pym Particles_Resource_7_12.15.tiff",
    # Filed under Wasp, but it is not a Wasp card. The whole-library search is what finds it.
    "Heros/Janet Van Dyne_Wasp/Aggression_Quincarrier_Support_21.tiff",
    "Heros/Janet Van Dyne_Wasp/wasp decklist.tiff",
    # Form C: the leading number counts physical copies. Read as a position it is
    # confidently wrong, which is worse than no answer. Phoenix holds no decklist scan.
    "Heros/Jean Grey_Phoenix/2_Active Altruism_Event.tif",
    "Heros/Jean Grey_Phoenix/3_Active Altruism_Event.tif",
    "Heros/Jean Grey_Phoenix/4_Active Altruism_Event.tif",
    "Heros/Jean Grey_Phoenix/1_Phoenix_Hero.tif",
    # The other decklist spelling. Both must survive, or the pattern is only half tested.
    "Heros/Bobby Drake_Iceman/iceman deck list.tiff",
    "Heros/Bobby Drake_Iceman/Iceman_Iceman_Hero_1a.tiff",
    # A position recorded wrong, colliding with a genuinely double-sided card at that number.
    "Heros/Vision_Vision/Vision_Vivian_Ally_2.tiff",
    "Heros/Vision_Vision/Vision_Intangible_Upgrade_2a.tiff",
    "Heros/Vision_Vision/Vision_Intangible_Upgrade_2b.tiff",
    # No position at all: name-matched only. Two of the three observed typos live here.
    "Aspects/Leadership/Leadership_Stength in Numbers_Event.tiff",
    "Aspects/Leadership/Leadership_Upgarde_Upgrade.tiff",
    "Aspects/Basic/Basic_Invulnerability_Event.tiff",
    "Core Set/Aspects/Basic-Grey/Basic_Energy_Resource_88.tiff",
    "Core Set/Core Set_Hawkeye_Ally_66.tiff",
    # Matches none of the three conventions and is not a decklist: reported as
    # uninterpretable when it sits in the folder the user named (FR-032).
    "Heros/Steve Rogers_Captain America/scan notes.txt.tiff",
)

#: Small enough that building the tree costs milliseconds per test, large enough to clear
#: the 300 DPI floor at 63.5x88.9 mm (312 DPI on both axes) so these files can actually be
#: printed by an integration test rather than only parsed.
LIBRARY_IMAGE_W, LIBRARY_IMAGE_H = 780, 1122


@pytest.fixture
def library_root(tmp_path: Path) -> Path:
    """A scan library reproducing the real one's filename awkwardness (FR-007, FR-021).

    Generated, like every other image here. What is under test is the filenames and the
    folder layout, never the pixels — the resolver matches on positions and names.
    """
    root = tmp_path / "library"
    for rel in LIBRARY_TREE:
        make_card_image(root / rel, Path(rel).stem, width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)
    return root


def snapshot_fixture(pack_code: str) -> list[dict]:
    """The committed reduced listing for one pack (T006)."""
    return json.loads((SNAPSHOT_FIXTURES / f"{pack_code}.json").read_text())


#: Measured on `cards/cap.json`, 2026-08-17. There is no ETag; `Last-Modified` is the only
#: validator MarvelCDB serves, and `max-age` is 600 s (research R1, R12).
UPSTREAM_MAX_AGE = 600
UPSTREAM_LAST_MODIFIED = "Wed, 10 Jun 2026 14:21:35 GMT"


class UnstubbedRequest(AssertionError):
    """A test reached for the network. Nothing in this suite may."""


@pytest.fixture
def upstream_transport() -> httpx.MockTransport:
    """Serves the T006 fixtures and fails loudly on anything else.

    Failing rather than returning 404 is the point: a client bug that widens the allowlist,
    or a test that quietly starts depending on the live API, both show up here as an error
    naming the URL instead of as a slow test that passes when the network happens to be up.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "marvelcdb.com":
            raise UnstubbedRequest(f"outbound request to {request.url}")

        headers = {
            "cache-control": f"max-age={UPSTREAM_MAX_AGE}, public",
            "last-modified": UPSTREAM_LAST_MODIFIED,
            "content-type": "application/json",
        }
        path = request.url.path

        if path == "/api/public/packs/":
            return httpx.Response(
                200,
                json=json.loads((SNAPSHOT_FIXTURES / "packs.json").read_text()),
                headers=headers,
            )

        if path.startswith("/api/public/cards/") and path.endswith(".json"):
            pack = path.removeprefix("/api/public/cards/").removesuffix(".json")
            fixture = SNAPSHOT_FIXTURES / f"{pack}.json"
            if not fixture.is_file():
                return httpx.Response(404, json={"error": "no such pack"}, headers=headers)
            if request.headers.get("if-modified-since") == UPSTREAM_LAST_MODIFIED:
                # Measured: a 304 carries zero bytes, which is what makes revalidation
                # cheaper than refetching and is asserted in the freshness tests.
                return httpx.Response(304, headers=headers)
            return httpx.Response(200, json=json.loads(fixture.read_text()), headers=headers)

        raise UnstubbedRequest(f"unstubbed MarvelCDB path {path}")

    return httpx.MockTransport(handler)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any real socket connection, for tests asserting that none is made.

    `upstream_transport` covers the client's own calls; this covers everything else, so
    "within max-age no request is issued at all" (FR-039) is asserted against the socket
    rather than against a counter the code under test maintains.
    """
    import socket

    def refuse(*args: object, **kwargs: object):
        raise UnstubbedRequest("a test opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    yield


def http_date(ts) -> str:
    """RFC 7231 date, as `Last-Modified` and `If-Modified-Since` carry it."""
    return format_datetime(ts, usegmt=True)


@pytest.fixture
def multipage_catalog_path(tmp_path: Path) -> Path:
    """The same deck at 27 faces, so it paginates to three pages.

    Preview and progress are only meaningful across more than one page: a single-page deck
    cannot show a page arriving before the run has finished, which is the whole of FR-016b.
    """
    data = _catalog_dict()
    for entry in data["decks"][0]["entries"]:
        if entry["card_id"].startswith("sig"):
            entry["quantity"] = 6
    p = tmp_path / "multipage-catalog.json"
    p.write_text(json.dumps(data, indent=2))
    return p
