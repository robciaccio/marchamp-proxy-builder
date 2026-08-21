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


def test_each_unresolved_card_carries_its_own_way_out(script):
    """FR-026d — "each unresolved card individually", which is a rule about controls.

    The failure being guarded is a single "upload the missing cards" control, or one "print
    anyway" button covering the list. Both would satisfy a reading of the requirement and
    neither lets the user answer *this* card, which is the whole of FR-030a's explicit act.
    So the per-card picker and the per-card omit button are built inside the loop over
    `run.unresolved`, and this test says so.
    """
    gaps = script.split("function renderGaps(")[1].split("\nfunction ")[0]
    assert "for (const gap of gaps)" in gaps
    assert 'picker.type = "file"' in gaps
    assert "supplyCardImage(gap, file)" in gaps
    assert "omitCard(gap)" in gaps


def test_a_supplied_file_is_uploaded_rather_than_named_by_path(markup, script):
    """FR-026e — the user must not have to type a filesystem path for a card."""
    assert "new FormData()" in script
    assert 'body.append("file", file)' in script
    assert "/image" in script
    # No text input anywhere asks for a per-card path.
    assert 'type="file"' in markup


def test_printing_without_a_card_is_an_explicit_act(script):
    """FR-030a — not the default, not inferred from silence, and never blanket."""
    assert "acknowledged: true" in script
    assert "/omission" in script
    assert "side: gap.side" in script


def test_a_folder_with_no_decklist_can_be_answered_with_a_file(markup, script):
    """FR-013c — the address is offered, the user fetches it, and it comes back here."""
    assert 'id="decklist-file"' in markup
    assert "supplyDecklist(file)" in script
    assert "hallofheroes" in markup.lower() or "Hall of Heroes" in markup


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


# ------------------------------------------------------- T074: the report, US2's half


def test_the_cut_cards_can_be_sorted_by_group_without_recognising_them(markup, script):
    """FR-015e, SC-002b — the layout deliberately does not separate the groups.

    A printed page routinely carries the last player cards and the first nemesis cards, so
    a user who does not know Marvel Champions by sight has only this list to sort by. If it
    is not grouped, the pack is a shuffled stack of 59 cards and a card name they cannot
    place.
    """
    assert 'id="groups"' in markup
    assert "Sorting the cut cards" in markup
    assert 'id="groups-list"' in markup
    for group in ("player", "identity", "nemesis", "decklist"):
        assert f'"{group}"' in script


def test_cards_printed_without_are_named_where_the_user_will_see_them(markup, script):
    """FR-030b, SC-006e — an incomplete deck is never indistinguishable from a complete one."""
    assert 'id="omitted-list"' in markup
    assert "report.omitted" in script


def test_the_library_problems_the_user_can_fix_are_shown(markup, script):
    """FR-031 - FR-035 — a scan sitting ignored in the folder they pointed at is named."""
    for element in ("unused-list", "conflicts-list", "warnings-list"):
        assert f'id="{element}"' in markup
    assert "report.unused_files" in script
    assert "report.conflicts" in script
    assert "report.low_resolution" in script


def test_a_low_resolution_scan_is_shown_as_a_warning_and_not_as_a_refusal(markup):
    """FR-035 — the user decides whether a soft card is acceptable, not the tool."""
    assert "will still print" in markup


def test_the_outcome_is_shown_once_the_run_is_finished(markup, script):
    """FR-036 — and only then: waiting on a card is not an outcome (and not a failure)."""
    assert 'id="assembly-outcome"' in markup
    assert "run.outcome" in script


# ------------------------------------------------------------------ US5 (T109)
#
# FR-026c is worded from the user's side — "without remembering an identifier" — so the
# wizard has to *show* the runs rather than accept one. And FR-026g's deletion is only a
# real choice if the list says what each row costs, which is why `total_bytes` reaches the
# markup rather than staying a field on the response.


def test_unfinished_runs_can_be_found_and_resumed_without_an_identifier(markup, script):
    """FR-026c, SC-006g. The list is the entry point, not a box to paste a run id into."""
    assert 'id="runs-list"' in markup
    assert '"/api/assemblies"' in script
    assert "resumeRun(" in script
    # No control anywhere asks the user for a run id.
    assert "run id" not in markup.lower()


def test_the_run_list_says_which_runs_are_waiting_and_which_are_printable(markup, script):
    """The three states have three different next actions, so the list distinguishes them.

    Asserted against the label map rather than against prose in the render function: the
    failure being guarded is two states collapsing into one word, and a map is where that
    would happen.
    """
    labels = script.split("const RUN_STATES = {")[1].split("};")[0]
    for state in ("complete", "awaiting_cards", "awaiting_pack"):
        assert f"{state}:" in labels, state
    described = {line.split('"')[1] for line in labels.splitlines() if '"' in line}
    assert len(described) == len([ln for ln in labels.splitlines() if '"' in ln]), (
        "two run states share a label, so the list cannot tell them apart"
    )

    runs = script.split("function renderRuns(")[1].split("\nfunction ")[0]
    assert "RUN_STATES[run.state]" in runs
    assert "unresolved_count" in runs


def test_a_run_whose_library_has_gone_says_so_rather_than_listing_missing_cards(script):
    """FR-026f. One sentence naming the folder is actionable; forty card names are not."""
    assert "library_problem" in script


def test_the_stored_pdfs_are_listed_with_what_they_cost(markup, script):
    """FR-026g. 001 measured ~202 MB for one deck, so reclaiming must be an informed act."""
    assert 'id="pdfs-list"' in markup
    assert 'id="pdfs-total"' in markup
    assert '"/api/pdfs"' in script
    assert "total_bytes" in script
    assert "byte_size" in script


def test_deleting_a_run_and_reclaiming_disk_are_offered_as_different_acts(markup, script):
    """FR-026g1 — the separation is the requirement, so it has to survive into the UI.

    A single "delete" control on a run row that also removed the pack's standard PDF would
    read identically to the user and would revoke FR-026f for every other run of that pack.
    The two live in two lists with two different verbs, and the run list says so in words.
    """
    assert "deleteRun(" in script
    assert "deleteStoredPdf(" in script
    assert "/api/pdfs/" in script
    # The run list states what discarding a run does *not* do.
    assert "standard" in markup.lower()


def test_the_assembly_client_still_only_uses_the_public_api(script):
    """Principle II, re-asserted over the routes US5 adds."""
    for path in re.findall(r'"(/api/[^"]*)"', script):
        assert path.startswith("/api/"), path


def test_a_customized_run_is_asked_to_name_its_pdf_before_it_can_be_built(markup, script):
    """FR-026i — and the reason the run response carries `customized` at all.

    `save_as` is required for a customized run and refused for an uncustomized one, so a
    client that cannot tell them apart cannot get either right. This one posted `{}`
    unconditionally, which meant a user who supplied a file for one missing card — US4's
    whole path — reached the Build button and got a 400 with no way forward.

    Asserted at both ends: the field exists in the markup, and the script decides on
    `run.customized` rather than on anything it inferred for itself.
    """
    assert 'id="assembly-save-as-field"' in markup
    assert 'id="assembly-save-as"' in markup
    assert "run.customized" in script
    assert "save_as" in script


def test_an_uncustomized_run_is_not_offered_a_name(markup, script):
    """The other half, and not symmetry for its own sake.

    An untouched run produces the pack's *standard* PDF, which belongs to the pack rather
    than to this attempt — every other run of that pack is served the same file (FR-026h).
    Offering a name for it would invite the user to believe they owned a copy they do not.
    """
    assert "hidden" in markup.split('id="assembly-save-as-field"')[1].split(">")[0]
    assert "customized ? { save_as:" in script


def test_the_pack_path_offers_paper_and_fitting(markup, script):
    """FR-009c, FR-014 — every mode's cost stated where it is chosen, on *both* paths.

    The pack path shipped without these controls and silently used the API's defaults, so
    every pack printed was cropped ~1.2 mm top and bottom without being asked and A4 could
    not be reached from the interface at all. The API has carried both fields since 002
    shipped; only the wizard omitted them.
    """
    assert 'name="assembly_page_size"' in markup
    assert 'name="assembly_fit_mode"' in markup
    for value in ("LETTER", "A4", "CROP", "FIT", "STRETCH"):
        assert f'value="{value}"' in markup
    assert "page_size: checkedValue" in script
    assert "fit_mode: checkedValue" in script


def test_the_pack_paths_stretch_option_says_it_distorts(markup):
    """FR-014, the same bar 001 is held to by `test_stretch_cannot_be_chosen_without_...`.

    Asserted against the fitting fieldset that belongs to the pack form, so a build that
    dropped the pack controls could not pass on 001's copy sitting elsewhere in the page.
    """
    fieldset = markup.split('name="assembly_fit_mode"')[-1]
    assert "distorts" in fieldset.lower()
    assert "1.2 mm" in markup and "61.8 mm" in markup


def test_the_pack_controls_do_not_collide_with_the_deck_controls(markup, script):
    """`app.js` reads 001's radios with a document-wide `querySelectorAll` on the bare
    names, so an unprefixed second set would be read as 001's and the two forms would
    silently fight over one value."""
    assert markup.count('name="page_size"') == 2  # 001's Letter and A4, and no more
    assert markup.count('name="fit_mode"') == 3  # 001's three modes, and no more
    assert "querySelectorAll('input[name=\"page_size\"]')" in script


def test_the_report_says_which_paper_and_fitting_produced_it(markup, script):
    """A run reopened days later must report what it was built with (FR-026b), which is why
    this reads the run rather than the form."""
    assert 'id="report-paper"' in markup
    assert 'id="report-fit"' in markup
    assert "run.page_size" in script and "run.fit_mode" in script
