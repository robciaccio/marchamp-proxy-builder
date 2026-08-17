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


# ----------------------------------------------------- feature 002: pack assembly (T057)


def test_the_assembly_flow_asks_for_both_paths(markup):
    """FR-005, SC-003a — neither path is configured in advance, so both must be asked for."""
    assert 'id="library-root"' in markup
    assert 'id="hero-folder"' in markup


def test_the_identified_pack_is_shown_with_its_evidence_before_confirming(markup, script):
    """FR-012. The sentence-level requirement: a user confirms against *evidence*.

    A confidence percentage alone is not something anyone can check, and the case the
    threshold structurally cannot catch is an identification that is confident and wrong
    (SC-009). This is the wording that would get edited away first.
    """
    assert 'id="pack-evidence"' in markup
    assert "Is this the right pack?" in markup
    assert 'id("pack-evidence")' in script or '$("pack-evidence")' in script


def test_a_refusal_offers_a_way_out_rather_than_a_dead_end(markup, script):
    """FR-012b — the picker exists and an unidentified folder opens it unprompted."""
    assert 'id="pack-picker"' in markup
    assert 'id="pack-candidates"' in markup
    assert "showPackPicker" in script


def test_the_decklist_is_proposed_and_not_printed_until_accepted(markup, script):
    """FR-013d — a proposal with an accept, a different pick, and a skip."""
    assert 'id="decklist-step"' in markup
    assert 'id="decklist-confirm"' in markup
    assert 'id="decklist-skip"' in markup
    assert '"select"' in script


def test_a_folder_with_no_decklist_offers_the_hall_of_heroes_and_is_not_a_failure(markup):
    """FR-013c, SC-006j — Hulk's and Phoenix's real case.

    The address is offered to the *user*; the application never fetches it, which is what
    keeps FR-002's egress allowlist at a single host.
    """
    assert 'id="decklist-missing"' in markup
    assert "Hall of Heroes" in markup
    assert "will print without one" in markup


def test_every_mutating_call_carries_if_match(script):
    """ADR 0001 at the wire — two tabs answering two questions is the lost update."""
    assert '"If-Match"' in script
    assert "assembly.run.version" in script


def test_unresolved_cards_are_named_individually_with_where_the_tool_looked(markup, script):
    """FR-026d, SC-008 — never a failed run the user has to diagnose."""
    assert 'id="gaps-list"' in markup
    assert "gap.searched" in script
    assert "Cards that could not be found" in markup


def test_substitutions_are_shown_so_a_wrong_match_is_visible(markup, script):
    """FR-024, SC-005 — everything except an exact hit in the hero folder is listed."""
    assert 'id="substitutions-list"' in markup
    assert 'provenance !== "folder_position"' in script


def test_the_pdf_is_produced_only_on_an_explicit_confirmation(markup, script):
    """FR-026a — reaching `ready` does not print by itself."""
    assert 'id="assembly-confirm"' in markup
    assert "Make the PDF" in markup
    assert 'run.state !== "ready"' in script


def test_the_assembly_client_only_uses_the_public_api(script):
    """Principle II — the wizard is a client of the HTTP API and reaches around it into
    nothing. Every path it touches is one the contract declares."""
    paths = set(re.findall(r"`(/api/assemblies[^`]*)`", script))
    for path in paths:
        assert path.startswith("/api/assemblies")
