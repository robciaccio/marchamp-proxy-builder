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
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

# Matches the measured Captain America pack scans: 1446x2079 @ 600 DPI, ratio 1.4378.
SOURCE_W, SOURCE_H = 1446, 2079
SOURCE_DPI = 600


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
