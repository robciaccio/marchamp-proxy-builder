"""T036/T037/T038/T039/T040/T041 — US1 end to end.

Covers FR-004, FR-005g–i, FR-006, FR-008, FR-015, FR-019a, FR-020, FR-020a, FR-020b,
FR-021a, SC-003, SC-006, SC-009, SC-012.
"""

from __future__ import annotations

import copy
import json

import pytest
from pypdf import PdfReader

from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.generations.service import GenerationService
from marchamp.layout.geometry import PageSize
from marchamp.render.images import FitMode

PT_PER_MM = 72.0 / 25.4
TOL_PT = 0.5 * PT_PER_MM  # FR-009's +/-0.5 mm, expressed in points


@pytest.fixture
def service(image_dir, catalog_path) -> GenerationService:
    return GenerationService(catalog_path=catalog_path, store=LocalDirectoryStore(image_dir))


def _pdf(service, **kw):
    gen = service.generate("testman-deck", **kw)
    assert gen.status == "succeeded", gen.failures
    return gen


# ------------------------------------------------------------------ generation


def test_generates_a_pdf_for_the_whole_deck(service):
    gen = _pdf(service)
    assert gen.card_count == 8  # hero counts twice
    assert gen.page_count == 1
    assert gen.document.startswith(b"%PDF-")


def test_new_deck_becomes_selectable_without_a_rebuild(catalog_path, image_dir):
    # FR-004 / SC-009 — content ships without a release.
    data = json.loads(catalog_path.read_text())
    extra = copy.deepcopy(data["decks"][0])
    extra["id"], extra["name"] = "second-deck", "Second"
    data["decks"].append(extra)
    catalog_path.write_text(json.dumps(data))

    svc = GenerationService(catalog_path=catalog_path, store=LocalDirectoryStore(image_dir))
    assert {d.id for d in svc.decks()} == {"testman-deck", "second-deck"}


# -------------------------------------------------------------------- geometry


@pytest.mark.parametrize("page_size", list(PageSize))
@pytest.mark.parametrize("fit_mode", list(FitMode))
def test_pdf_geometry_is_correct_for_every_mode(service, page_size, fit_mode):
    gen = _pdf(service, page_size=page_size, fit_mode=fit_mode)
    reader = PdfReader(__import__("io").BytesIO(gen.document))
    box = reader.pages[0].mediabox
    w_mm, h_mm = page_size.dimensions_mm
    assert float(box.width) == pytest.approx(w_mm * PT_PER_MM, abs=TOL_PT)
    assert float(box.height) == pytest.approx(h_mm * PT_PER_MM, abs=TOL_PT)
    assert float(box.height) > float(box.width)  # portrait, FR-008b


def test_every_page_holds_at_most_nine_faces(service):
    gen = _pdf(service)
    assert all(len(p) <= 9 for p in gen.page_face_counts)


# ----------------------------------------------------------------- determinism


def test_regeneration_is_byte_identical(service):
    # FR-015 / SC-006.
    a = _pdf(service).document
    for _ in range(5):
        assert _pdf(service).document == a


def test_changing_fit_mode_changes_the_bytes(service):
    # The five inputs define the output; fit mode is one of them.
    assert (
        _pdf(service, fit_mode=FitMode.CROP).document
        != _pdf(service, fit_mode=FitMode.FIT).document
    )


def test_changing_page_size_changes_the_bytes(service):
    assert (
        _pdf(service, page_size=PageSize.LETTER).document
        != _pdf(service, page_size=PageSize.A4).document
    )


# ---------------------------------------------------------------- substitution


def test_stand_in_is_used_and_reported_before_download(service):
    # SC-012 — the fixture's 'energy' card has no pack art on disk, only Core Set art.
    gen = _pdf(service)
    assert len(gen.substitutions) == 1
    sub = gen.substitutions[0]
    assert sub.card_name == "Energy"
    assert sub.wanted_pack == "Testman Hero Pack"
    assert sub.used_pack == "Core Set"


def test_no_substitutions_when_all_pack_art_is_present(catalog_path, image_dir):
    data = json.loads(catalog_path.read_text())
    energy = next(c for c in data["cards"] if c["id"] == "energy")
    energy["printings"] = [p for p in energy["printings"] if p["id"] == "energy@core"]
    data["decks"][0]["entries"][-1]["preferred_printing_id"] = "energy@core"
    catalog_path.write_text(json.dumps(data))

    svc = GenerationService(catalog_path=catalog_path, store=LocalDirectoryStore(image_dir))
    assert svc.generate("testman-deck").substitutions == []


# --------------------------------------------------------------------- failure


def test_all_failing_cards_are_reported_together(catalog_path, image_dir):
    # FR-020a — fixing one problem per attempt is the failure mode this prevents.
    data = json.loads(catalog_path.read_text())
    for cid in ("sig1", "sig2"):
        card = next(c for c in data["cards"] if c["id"] == cid)
        card["printings"][0]["image"] = f"Heros/Test Hero_Testman/{cid}_gone.tiff"
    catalog_path.write_text(json.dumps(data))

    svc = GenerationService(catalog_path=catalog_path, store=LocalDirectoryStore(image_dir))
    gen = svc.generate("testman-deck")
    assert gen.status == "failed"
    named = {f.card_name for f in gen.failures}
    assert {"Signature 1", "Signature 2"} <= named


def test_a_failed_generation_offers_no_document(catalog_path, image_dir):
    # FR-020b — there is deliberately no partial output.
    data = json.loads(catalog_path.read_text())
    card = next(c for c in data["cards"] if c["id"] == "sig1")
    card["printings"][0]["image"] = "Heros/Test Hero_Testman/gone.tiff"
    catalog_path.write_text(json.dumps(data))

    gen = GenerationService(
        catalog_path=catalog_path, store=LocalDirectoryStore(image_dir)
    ).generate("testman-deck")
    assert gen.status == "failed"
    assert gen.document is None


def test_card_with_no_usable_printing_fails_rather_than_falling_back(catalog_path, image_dir):
    # FR-005i — fallback covers missing art, never a missing card.
    data = json.loads(catalog_path.read_text())
    energy = next(c for c in data["cards"] if c["id"] == "energy")
    for p in energy["printings"]:
        p["image"] = "Heros/Test Hero_Testman/absent.tiff"
    catalog_path.write_text(json.dumps(data))

    gen = GenerationService(
        catalog_path=catalog_path, store=LocalDirectoryStore(image_dir)
    ).generate("testman-deck")
    assert gen.status == "failed"
    assert any(f.card_name == "Energy" for f in gen.failures)


def test_nothing_retries_on_its_own(service, monkeypatch):
    # FR-021a — retrying is the user's action.
    calls = {"n": 0}
    original = service._compose

    def counting(*a, **k):
        calls["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(service, "_compose", counting)
    service.generate("testman-deck")
    assert calls["n"] == 1


# --------------------------------------------------------------------- offline


def test_generation_works_with_networking_unavailable(service, monkeypatch):
    # FR-019a / SC-001b — any socket use at all is a defect here.
    import socket

    def forbidden(*a, **k):
        raise AssertionError("generation attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert _pdf(service).document.startswith(b"%PDF-")
