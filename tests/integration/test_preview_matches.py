"""T051 — the preview matches the PDF, page for page and card for card (FR-017, SC-005).

The failure this guards against is specific and nasty: a preview that keeps looking right
while the printed sheet goes wrong. That happens when the preview is *drawn* from the
layout model rather than *rasterised* from the document, because then there are two
implementations of the placement rules and only one of them is the one that prints.

So the assertions here are pixel equality, not "looks about right". A progressive preview
page and the corresponding page of the finished document must be the same image.
"""

from __future__ import annotations

import io
import time

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from marchamp.api.app import create_app
from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.config import Settings
from marchamp.generations.service import GenerationService
from marchamp.render import preview
from marchamp.render.images import FitMode

PAGES = 3  # the multipage fixture is 27 faces at 9 per page
TIMEOUT_S = 30


def _await_generation(client: TestClient, generation_id: str) -> dict:
    """Poll until the run settles. Generation is asynchronous now, so tests must wait."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        state = client.get(f"/api/generations/{generation_id}").json()
        if state["status"] in ("succeeded", "failed"):
            return state
        time.sleep(0.02)
    raise AssertionError(f"generation {generation_id} did not settle within {TIMEOUT_S}s")


def _generate(client: TestClient) -> tuple[str, dict]:
    created = client.post("/api/generations", json={"deck_id": "testman-deck"})
    assert created.status_code == 202, created.text
    generation_id = created.json()["id"]
    state = _await_generation(client, generation_id)
    assert state["status"] == "succeeded", state["failures"]
    return generation_id, state


@pytest.fixture
def service(image_dir, multipage_catalog_path) -> GenerationService:
    return GenerationService(
        catalog_path=multipage_catalog_path, store=LocalDirectoryStore(image_dir)
    )


@pytest.fixture
def client(image_dir, multipage_catalog_path) -> TestClient:
    app = create_app(Settings(image_dir=image_dir, catalog_path=multipage_catalog_path))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def finished(service):
    gen = service.generate("testman-deck")
    assert gen.status == "succeeded", gen.failures
    return gen


# ------------------------------------------------------------------------- page count


def test_the_preview_has_exactly_the_pages_the_pdf_has(finished):
    assert finished.page_count == PAGES
    assert preview.page_count(finished.document) == PAGES
    assert len(PdfReader(io.BytesIO(finished.document)).pages) == PAGES


def test_every_page_is_previewable_once_the_run_succeeds(finished):
    for n in range(1, PAGES + 1):
        assert finished.preview_document(n) is not None
    assert finished.preview_document(PAGES + 1) is None
    assert finished.preview_document(0) is None


# -------------------------------------------------------- progressive vs. final bytes


def test_each_progressive_page_matches_that_page_of_the_finished_document(finished):
    """The real drift risk.

    While a generation runs, a preview is served from a single-page document composed as
    that page completes; afterwards it is served from the finished PDF. If those two ever
    disagree, the preview a user approved is not the sheet they printed.
    """
    assert len(finished.page_documents) == PAGES
    for n in range(1, PAGES + 1):
        progressive = preview.render_page(finished.page_documents[n - 1], 1)
        final = preview.render_page(finished.document, n)
        assert progressive == final, f"page {n} differs between preview and document"


def test_pages_are_distinguishable_from_one_another(finished):
    # Guards the comparison above from passing vacuously: if every page rendered to the
    # same image, page-for-page equality would prove nothing about card order or position.
    rasters = {preview.render_page(finished.document, n) for n in range(1, PAGES + 1)}
    assert len(rasters) == PAGES


def test_card_order_is_the_deck_order(finished):
    # FR-017's "card order": faces are laid out in deck order, filling each page before
    # starting the next, with a double-sided card's two faces adjacent (FR-012b).
    flattened = [card_id for page in finished.page_face_counts for card_id in page]
    assert flattened[:2] == ["testman", "testman"]
    assert len(flattened) == finished.card_count == 27
    assert [len(p) for p in finished.page_face_counts] == [9, 9, 9]


# ------------------------------------------------------------------------ over HTTP


def test_the_served_preview_is_the_downloaded_document(client):
    generation_id, state = _generate(client)
    assert state["page_count"] == PAGES

    document = client.get(f"/api/generations/{generation_id}/document")
    assert document.headers["content-type"] == "application/pdf"

    for n in range(1, PAGES + 1):
        page = client.get(f"/api/generations/{generation_id}/pages/{n}")
        assert page.status_code == 200
        assert page.headers["content-type"] == "image/png"
        assert page.content == preview.render_page(document.content, n)


def test_a_page_the_document_does_not_have_is_not_found(client):
    generation_id, _ = _generate(client)
    assert client.get(f"/api/generations/{generation_id}/pages/{PAGES + 1}").status_code == 404
    assert client.get(f"/api/generations/{generation_id}/pages/0").status_code == 422


# --------------------------------------------------------------- preview never leaks


def test_preview_width_is_bounded_and_never_reaches_the_document(client, finished):
    # FR-016d — a preview must not approach the cost of the generation it previews.
    assert preview.clamp_width(10) == preview.MIN_WIDTH_PX
    assert preview.clamp_width(10_000) == preview.MAX_WIDTH_PX

    generation_id, _ = _generate(client)

    assert client.get(f"/api/generations/{generation_id}/pages/1?width=99").status_code == 422
    assert client.get(f"/api/generations/{generation_id}/pages/1?width=99999").status_code == 422

    small = client.get(f"/api/generations/{generation_id}/pages/1?width=300").content
    large = client.get(f"/api/generations/{generation_id}/pages/1?width=1200").content
    assert len(small) < len(large)

    # Whatever width was asked for, the document is unchanged.
    served = client.get(f"/api/generations/{generation_id}/document").content
    assert served == finished.document


def test_changing_the_fit_mode_changes_the_preview(service):
    # FR-016c exists because these differ. A preview left on screen after the mode changed
    # would be describing settings the user no longer has selected.
    crop = service.generate("testman-deck", fit_mode=FitMode.CROP)
    fit = service.generate("testman-deck", fit_mode=FitMode.FIT)
    assert preview.render_page(crop.document, 1) != preview.render_page(fit.document, 1)
