"""T052 — pages become viewable progressively and progress advances (FR-016a, FR-016b).

FR-0A4 lets a generation run for up to 120 seconds. An interface that looks frozen for two
minutes is indistinguishable from one that has failed, so "it finishes eventually" is not
the property under test — *observable advancement while it is still running* is.

The tests below step a real generation one page at a time through a semaphore pair rather
than sleeping and hoping, so they assert the intermediate states directly instead of racing
for them.
"""

from __future__ import annotations

import threading
import time

import pytest

from marchamp.assets.local_dir import LocalDirectoryStore
from marchamp.generations import service as service_module
from marchamp.generations.service import GenerationService
from marchamp.render import document as document_module

PAGES = 3  # the multipage fixture is 27 faces at 9 per page
TIMEOUT_S = 30


@pytest.fixture
def service(image_dir, multipage_catalog_path) -> GenerationService:
    return GenerationService(
        catalog_path=multipage_catalog_path, store=LocalDirectoryStore(image_dir)
    )


@pytest.fixture
def stepper(monkeypatch):
    """Pause a generation after each composed page until the test lets it continue."""
    real_compose = document_module.compose
    composed = threading.Semaphore(0)  # released once per finished page
    resume = threading.Semaphore(0)  # the test releases to allow the next page

    def gated(pages, page_size, fit_mode, image_dir, on_page=None):
        def hook(index: int, page_document: bytes) -> None:
            if on_page is not None:
                on_page(index, page_document)
            composed.release()
            assert resume.acquire(timeout=TIMEOUT_S), "generation was never resumed"

        return real_compose(pages, page_size, fit_mode, image_dir, on_page=hook)

    monkeypatch.setattr(service_module, "compose", gated)
    return composed, resume


def _run_in_background(service: GenerationService, gen) -> threading.Thread:
    thread = threading.Thread(target=service.run, args=(gen,), daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------- advancement


def test_progress_advances_page_by_page_while_the_generation_runs(service, stepper):
    composed, resume = stepper
    gen = service.begin("testman-deck")
    assert gen.status == "pending"
    thread = _run_in_background(service, gen)

    observed: list[float] = []
    for page in range(1, PAGES + 1):
        assert composed.acquire(timeout=TIMEOUT_S), f"page {page} never completed"
        assert gen.status == "running", "status must report the work in flight"
        observed.append(gen.progress)
        resume.release()

    thread.join(timeout=TIMEOUT_S)
    assert not thread.is_alive()
    assert gen.status == "succeeded", gen.failures

    assert observed == sorted(observed), f"progress went backwards: {observed}"
    assert len(set(observed)) == PAGES, f"progress did not move between pages: {observed}"
    assert 0.0 < observed[0] < 1.0, "an in-flight generation must not report 0 or 1"
    assert gen.progress == 1.0


def test_progress_also_advances_before_composition_begins(service, monkeypatch):
    """Checking every card's source file is real work and can take a while on a cold disk.

    If progress only moved once drawing started, the interface would sit at zero through
    the entire preflight — exactly the frozen-looking window FR-016a forbids.
    """
    gen = service.begin("testman-deck")
    real_validate = service_module.validate_source
    seen: list[float] = []

    def recording(*args, **kwargs):
        seen.append(gen.progress)
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(service_module, "validate_source", recording)
    service.run(gen)

    assert gen.status == "succeeded", gen.failures
    assert len(seen) == 27
    assert seen == sorted(seen)
    assert seen[0] < seen[-1], "preflight did not advance progress"


# ------------------------------------------------------------ progressive viewability


def test_a_page_is_viewable_before_the_rest_of_the_deck_is_rendered(service, stepper):
    # FR-016b — the point of the whole thing. Waiting for page three to see page one is
    # the behaviour this replaces.
    composed, resume = stepper
    gen = service.begin("testman-deck")
    thread = _run_in_background(service, gen)

    assert composed.acquire(timeout=TIMEOUT_S)
    assert gen.status == "running"
    assert gen.pages_ready == 1
    # Known before the run ends, so an interface can say how many pages are still coming
    # rather than counting up from nothing.
    assert gen.page_count == PAGES
    assert gen.card_count == 27
    assert gen.preview_document(1) is not None, "page 1 must be viewable already"
    assert gen.preview_document(2) is None, "page 2 has not been composed yet"
    assert gen.document is None, "no document exists until the run succeeds (FR-020b)"

    for page in range(2, PAGES + 1):
        resume.release()
        assert composed.acquire(timeout=TIMEOUT_S)
        assert gen.pages_ready == page
        assert gen.preview_document(page) is not None
    resume.release()

    thread.join(timeout=TIMEOUT_S)
    assert gen.pages_ready == PAGES
    assert gen.status == "succeeded"


def test_a_failed_generation_leaves_no_partial_preview(image_dir, multipage_catalog_path):
    # FR-020b covers the document; a half-rendered preview would be the same broken promise
    # wearing a different hat.
    import json

    data = json.loads(multipage_catalog_path.read_text())
    card = next(c for c in data["cards"] if c["id"] == "sig1")
    card["printings"][0]["image"] = "Heros/Test Hero_Testman/gone.tiff"
    multipage_catalog_path.write_text(json.dumps(data))

    gen = GenerationService(
        catalog_path=multipage_catalog_path, store=LocalDirectoryStore(image_dir)
    ).generate("testman-deck")

    assert gen.status == "failed"
    assert gen.document is None
    assert gen.page_documents == []
    assert gen.pages_ready == 0
    assert gen.preview_document(1) is None


# -------------------------------------------------------------------- over the API


def test_the_post_returns_before_the_work_is_done(image_dir, multipage_catalog_path, stepper):
    """FR-016a, at the seam that matters: the HTTP layer must not block for the run.

    The generation is held at its first page while the test asks the API about it, so a
    POST that only answered once rendering finished would deadlock here rather than
    quietly taking two minutes.
    """
    from fastapi.testclient import TestClient

    from marchamp.api.app import create_app
    from marchamp.config import Settings

    composed, resume = stepper
    app = create_app(Settings(image_dir=image_dir, catalog_path=multipage_catalog_path))

    with TestClient(app) as client:
        created = client.post("/api/generations", json={"deck_id": "testman-deck"})
        assert created.status_code == 202, created.text
        body = created.json()
        assert body["status"] in ("pending", "running")
        assert created.headers["Location"] == f"/api/generations/{body['id']}"

        assert composed.acquire(timeout=TIMEOUT_S), "generation never started"
        in_flight = client.get(f"/api/generations/{body['id']}").json()
        assert in_flight["status"] == "running"
        assert in_flight["pages_ready"] == 1
        assert 0.0 < in_flight["progress"] < 1.0

        # A page that is ready is served; the document is not, because it does not exist.
        assert client.get(f"/api/generations/{body['id']}/pages/1").status_code == 200
        assert client.get(f"/api/generations/{body['id']}/document").status_code == 409

        for _ in range(PAGES):
            resume.release()

        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            final = client.get(f"/api/generations/{body['id']}").json()
            if final["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.02)
        assert final["status"] == "succeeded", final["failures"]
        assert final["progress"] == 1.0
        assert final["pages_ready"] == PAGES
