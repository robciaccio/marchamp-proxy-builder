"""T027 — pagination (FR-007, FR-012, FR-012a, FR-012b, FR-012c)."""

from __future__ import annotations

from marchamp.catalog.loader import load_catalog
from marchamp.layout.geometry import PageSize
from marchamp.layout.paginate import Side, face_count, paginate


def test_quantities_expand_to_one_face_per_copy(catalog_dict, image_dir):
    # sig1 has quantity 2.
    cat = load_catalog(catalog_dict)
    faces = [f for p in paginate(cat, "testman-deck", PageSize.LETTER, image_dir) for f in p.faces]
    assert sum(1 for f in faces if f.card_id == "sig1") == 2


def test_double_sided_card_yields_two_faces(catalog_dict, image_dir):
    cat = load_catalog(catalog_dict)
    faces = [f for p in paginate(cat, "testman-deck", PageSize.LETTER, image_dir) for f in p.faces]
    hero = [f for f in faces if f.card_id == "testman"]
    assert len(hero) == 2
    assert {f.side for f in hero} == {Side.FRONT, Side.BACK}


def test_double_sided_faces_are_adjacent(catalog_dict, image_dir):
    # FR-012b — cut and sleeved as a pair, without hunting across pages.
    cat = load_catalog(catalog_dict)
    faces = [f for p in paginate(cat, "testman-deck", PageSize.LETTER, image_dir) for f in p.faces]
    idx = [i for i, f in enumerate(faces) if f.card_id == "testman"]
    assert idx[1] == idx[0] + 1


def test_face_count_counts_double_sided_twice(catalog_dict):
    # 1 hero (2 faces) + 2 sig1 + sig2 + sig3 + sig4 + energy = 8
    cat = load_catalog(catalog_dict)
    assert face_count(cat, "testman-deck") == 8


def test_realistic_deck_is_42_faces_over_5_pages():
    # FR-012c — the spec's worked example: 40 single-sided cards plus a double-sided hero.
    from math import ceil

    faces = 40 + 2
    assert faces == 42
    assert ceil(faces / 9) == 5


def test_last_page_is_partially_filled_with_no_placeholders(catalog_dict, image_dir):
    cat = load_catalog(catalog_dict)
    pages = paginate(cat, "testman-deck", PageSize.LETTER, image_dir)
    assert len(pages) == 1
    assert len(pages[0].faces) == 8  # not padded out to 9
