"""T017/T019/T021/T023 — catalog models, loading, validation, printing resolution.

Covers FR-005a, FR-005b, FR-005b1, FR-005c, FR-005c1, FR-005c2, FR-005d, FR-005e–j.
"""

from __future__ import annotations

import copy
import json

import pytest

from marchamp.catalog.loader import CatalogError, load_catalog
from marchamp.catalog.printings import ResolutionOutcome, resolve_entry
from marchamp.catalog.validation import validate

# --------------------------------------------------------------------------- models


def test_card_is_separate_from_printing(catalog_dict):
    cat = load_catalog(catalog_dict)
    energy = cat.card("energy")
    assert len(energy.printings) == 2
    assert {p.pack for p in energy.printings} == {"Testman Hero Pack", "Core Set"}


def test_double_sided_flag_is_on_the_card(catalog_dict):
    cat = load_catalog(catalog_dict)
    assert cat.card("testman").double_sided is True
    assert cat.card("sig1").double_sided is False


def test_printing_number_is_informational_not_an_identifier(catalog_dict):
    # Make the Call is 16 in one pack and 71 in another; number never identifies a card.
    cat = load_catalog(catalog_dict)
    numbers = {p.number for p in cat.card("energy").printings}
    assert numbers == {"20", "88"}
    assert cat.card("energy").id == "energy"


# --------------------------------------------------------------------------- loading


def test_unknown_schema_version_is_refused(catalog_dict):
    bad = copy.deepcopy(catalog_dict)
    bad["schema_version"] = "99"
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_revision_is_content_derived_and_stable(catalog_dict):
    a = load_catalog(copy.deepcopy(catalog_dict)).revision
    b = load_catalog(copy.deepcopy(catalog_dict)).revision
    assert a == b and len(a) >= 16


def test_revision_changes_when_content_changes(catalog_dict):
    before = load_catalog(copy.deepcopy(catalog_dict)).revision
    changed = copy.deepcopy(catalog_dict)
    changed["decks"][0]["entries"][1]["quantity"] = 3
    assert load_catalog(changed).revision != before


def test_revision_ignores_key_order(catalog_dict):
    reordered = json.loads(json.dumps(catalog_dict, sort_keys=True))
    assert load_catalog(reordered).revision == load_catalog(copy.deepcopy(catalog_dict)).revision


# ------------------------------------------------------------------------ validation


def test_valid_catalog_passes(catalog_dict, image_dir):
    report = validate(load_catalog(catalog_dict), image_dir)
    assert report.valid, report.errors


def test_all_errors_reported_together_not_first_and_stop(catalog_dict, image_dir):
    # FR-005d — fixing one problem per run across repeated attempts is the failure mode.
    broken = copy.deepcopy(catalog_dict)
    broken["decks"][0]["entries"].append(
        {"card_id": "ghost", "preferred_printing_id": "ghost@pack", "quantity": 1}
    )
    broken["decks"][0]["entries"][1]["quantity"] = 0
    broken["cards"][1]["printings"][0]["image"] = "Heros/Test Hero_Testman/gone.tiff"

    report = validate(load_catalog(broken), image_dir)
    kinds = {e.kind for e in report.errors}
    assert {"unknown_card_reference", "invalid_quantity", "missing_image_file"} <= kinds
    assert len(report.errors) >= 3


def test_preferred_printing_must_belong_to_that_card(catalog_dict, image_dir):
    broken = copy.deepcopy(catalog_dict)
    broken["decks"][0]["entries"][1]["preferred_printing_id"] = "energy@core"
    report = validate(load_catalog(broken), image_dir)
    assert any(e.kind == "printing_card_mismatch" for e in report.errors)


def test_missing_art_is_not_an_error_when_another_printing_exists(catalog_dict, image_dir):
    # 'energy' preferred art is absent on disk by design; the Core Set printing covers it.
    report = validate(load_catalog(catalog_dict), image_dir)
    assert report.valid
    assert all(e.card_id != "energy" for e in report.errors)


def test_duplicate_image_mapping_is_a_warning_not_an_error(catalog_dict, image_dir):
    dup = copy.deepcopy(catalog_dict)
    dup["cards"][2]["printings"][0]["image"] = dup["cards"][1]["printings"][0]["image"]
    report = validate(load_catalog(dup), image_dir)
    assert report.valid
    assert any(w.kind == "shared_image_file" for w in report.warnings)


def test_unreferenced_files_are_not_a_fault(catalog_dict, image_dir):
    (image_dir / "stray.tiff").write_bytes(b"II*\x00")
    assert validate(load_catalog(catalog_dict), image_dir).valid


def test_double_sided_card_must_have_a_back(catalog_dict, image_dir):
    broken = copy.deepcopy(catalog_dict)
    del broken["cards"][0]["printings"][0]["image_back"]
    report = validate(load_catalog(broken), image_dir)
    assert any(e.kind == "missing_back_image" for e in report.errors)


def test_unsafe_image_path_is_rejected(catalog_dict, image_dir):
    broken = copy.deepcopy(catalog_dict)
    broken["cards"][1]["printings"][0]["image"] = "../../etc/passwd"
    report = validate(load_catalog(broken), image_dir)
    assert any(e.kind == "unsafe_image_path" for e in report.errors)


# ------------------------------------------------------------------ printing choice


def test_preferred_printing_wins_when_present(catalog_dict, image_dir):
    cat = load_catalog(catalog_dict)
    entry = cat.deck("testman-deck").entries[1]
    out = resolve_entry(cat, entry, image_dir)
    assert out.outcome is ResolutionOutcome.PREFERRED
    assert out.printing.id == "sig1@pack"
    assert out.substitution is None


def test_stand_in_used_and_reported_when_preferred_art_is_absent(catalog_dict, image_dir):
    cat = load_catalog(catalog_dict)
    entry = next(e for e in cat.deck("testman-deck").entries if e.card_id == "energy")
    out = resolve_entry(cat, entry, image_dir)
    assert out.outcome is ResolutionOutcome.SUBSTITUTED
    assert out.printing.id == "energy@core"
    assert out.substitution.wanted_pack == "Testman Hero Pack"
    assert out.substitution.used_pack == "Core Set"


def test_stand_in_choice_is_deterministic(catalog_dict, image_dir):
    # FR-005j — byte-identical regeneration must survive substitution.
    many = copy.deepcopy(catalog_dict)
    energy = many["cards"][5]
    energy["printings"].append(
        {
            "id": "energy@aaa",
            "pack": "Another Pack",
            "number": "5",
            "image": "Core Set/Aspects/Basic-Grey/grey_energy.tiff",
        }
    )
    cat = load_catalog(many)
    entry = next(e for e in cat.deck("testman-deck").entries if e.card_id == "energy")
    picks = {resolve_entry(cat, entry, image_dir).printing.id for _ in range(10)}
    assert picks == {"energy@aaa"}  # lowest id wins, never directory or hash order


def test_no_usable_printing_fails_rather_than_falling_back(catalog_dict, image_dir):
    # FR-005i — fallback covers missing art, never a missing card.
    broken = copy.deepcopy(catalog_dict)
    for p in broken["cards"][5]["printings"]:
        p["image"] = "Heros/Test Hero_Testman/absent.tiff"
    cat = load_catalog(broken)
    entry = next(e for e in cat.deck("testman-deck").entries if e.card_id == "energy")
    out = resolve_entry(cat, entry, image_dir)
    assert out.outcome is ResolutionOutcome.UNAVAILABLE
    assert out.printing is None
