"""T050/T056/T057 — the wizard is served, and says what the spec requires it to say.

This is not a browser test. What it pins down is the part that can silently regress without
one: that the interface exists at `/`, that it is a client of the API and nothing more
(Principle II), and that the specific sentences the spec *requires* a user to see before
committing paper are actually present in what gets served.

FR-009c is the sharpest of these — a user must not be able to select distortion without
being told it is distortion — and it is exactly the kind of wording that gets edited away.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import WEB_ROOT, create_app
from marchamp.config import Settings


@pytest.fixture
def client(image_dir, catalog_path) -> TestClient:
    app = create_app(Settings(image_dir=image_dir, catalog_path=catalog_path))
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def script() -> str:
    return (WEB_ROOT / "app.js").read_text()


@pytest.fixture(scope="module")
def markup() -> str:
    return (WEB_ROOT / "index.html").read_text()


# ------------------------------------------------------------------------- serving


def test_the_wizard_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Marchamp Proxy Builder" in response.text


@pytest.mark.parametrize("asset", ["/app.js", "/styles.css"])
def test_the_wizard_assets_are_served(client, asset):
    assert client.get(asset).status_code == 200


def test_the_static_mount_does_not_shadow_the_api(client):
    # The UI is mounted at "/", so an ordering mistake here would take the whole API with
    # it and the failure would look like a missing endpoint rather than a routing bug.
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/decks").json()["decks"][0]["id"] == "testman-deck"


# ---------------------------------------------------------- a client, nothing more


def test_the_interface_reaches_the_service_only_through_the_public_api(script):
    # Principle II: the UI must not reach around the API. Every path it fetches is one the
    # contract describes.
    fetched = set(re.findall(r'["`](/[^"`${]*)', script))
    assert fetched, "no request paths found; the extraction below is probably wrong"
    assert all(path.startswith("/api/") for path in fetched), fetched


# ------------------------------------------------------- what the user must be told


def test_every_fit_mode_states_its_cost_at_the_point_of_choice(markup):
    # FR-009c — naming the mode is not enough; the sentence must say what it costs.
    body = markup.lower()
    assert "trims about 1.2 mm" in body, "crop must say what it discards"
    assert "61.8 mm" in body, "fit must say the printed face is smaller than a card"
    assert "distorts the art" in body, "stretch must say it distorts"


def test_stretch_cannot_be_chosen_without_being_told_it_distorts(markup):
    # FR-014 / FR-009c: the warning must sit with the control, not elsewhere on the page.
    stretch = markup[markup.index('value="STRETCH"') :]
    stretch = stretch[: stretch.index("</label>")]
    assert "distorts" in stretch.lower()


def test_the_page_and_face_counts_are_shown_before_the_download(markup, script):
    # FR-018 — counting double-sided cards as two, which is what card_count already is.
    assert "Printed faces" in markup
    assert 'id="tally-pages"' in markup and 'id="tally-faces"' in markup
    assert "generation.card_count" in script and "generation.page_count" in script


def test_substitutions_are_listed_alongside_the_preview(markup, script):
    # FR-005h / FR-018a — before paper is committed, not afterwards in a log.
    assert "Art substitutions" in markup
    assert "generation.substitutions" in script
    assert 'id="download"' in markup


def test_changing_a_setting_invalidates_the_displayed_preview(script):
    # FR-016c — a preview must never remain on screen describing settings that are no
    # longer selected.
    for control in ("page_size", "fit_mode"):
        handler = script[script.index(f'input[name="{control}"]') :][:400]
        assert "invalidatePreview()" in handler, control
