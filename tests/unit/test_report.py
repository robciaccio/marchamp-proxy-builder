"""T059, T063, T067, T069, T073 — the assembly report (US2).

US2 is not a separate feature from US1; it is the other half of it. With no deck total to
check against, **the report is the only thing that can tell a user their pack is short** —
and a pack silently missing three cards is worse than no pack at all, because the discovery
happens at the table after paying to print it.

Every section of data-model.md § Assembly Report is asserted here. The sections divide by
what they protect against:

- **Pack, Groups, Counts, Decklist, Upstream** — the run describing itself, so a stack of
  cut cards can be sorted without recognising a card on sight (FR-015e, SC-002b).
- **Substitutions, Manual choices, Omissions** — every departure from "found at its own
  position in the folder you named" is visible, so a wrong match can be rejected rather
  than printed (FR-024, FR-029, FR-030b).
- **Unused files, Uninterpretable, Conflicts, Warnings** — the library describing itself,
  so a scan sitting ignored in the folder the user pointed at is named rather than silently
  skipped (FR-031 - FR-035).
"""

from __future__ import annotations

import pytest

from marchamp.assembly.catalog import build_catalog
from marchamp.assembly.decklist import find_decklist
from marchamp.assembly.faces import Group, Side, expand_pack
from marchamp.assembly.report import AssemblyReport, build_report
from marchamp.assembly.resolve import Provenance, Resolution, Source, resolve_pack
from marchamp.library.index import build_index
from tests.conftest import ACCEPTANCE_HEROES, pack_cards, printing_lookup

CAP_FOLDER = ACCEPTANCE_HEROES["cap"]

#: A pinned stand-in for a real snapshot revision. Sixteen hex characters, matching
#: `snapshots.REVISION_LENGTH`, so nothing downstream rejects it as malformed.
REVISION = "0123456789abcdef"


@pytest.fixture(scope="module")
def cap_inputs(scan_library):
    """Everything `build_report` needs for `cap` against the derived fixture library.

    Handed over as a kwargs dict rather than a finished report so a test can vary one input
    — a user-selected pack, an extra omitted card — without repeating the twelve that stay
    the same. Module-scoped: this walks 678 files and digests ~60 images, and every test
    below reads the same immutable result.
    """
    from marchamp.assets.local_dir import LocalDirectoryStore

    cards = pack_cards("cap")
    index = build_index(scan_library)
    outcome = resolve_pack(
        expand_pack(cards), cards, index, CAP_FOLDER, scan_library, printing_lookup
    )
    decklist = find_decklist(index, CAP_FOLDER)
    built = build_catalog(
        pack_code="cap",
        pack_name="Captain America",
        cards=cards,
        resolutions=outcome.resolutions,
        snapshot_revision=REVISION,
        decklist=decklist,
    )
    return {
        "pack_code": "cap",
        "pack_name": "Captain America",
        "pack_source": "identified",
        "cards": cards,
        "resolutions": outcome.resolutions,
        "built": built,
        "decklist": decklist,
        "snapshot_revision": REVISION,
        "index": index,
        "hero_folder": CAP_FOLDER,
        "unresolved": outcome.unresolved,
        "store": LocalDirectoryStore(scan_library),
    }


@pytest.fixture(scope="module")
def cap(cap_inputs):
    return build_report(**cap_inputs)


# --------------------------------------------------------------------------- the model


#: data-model.md § Assembly Report, one key per row of its table. Asserted as a set rather
#: than field by field: a section that is dropped, renamed, or quietly never populated is
#: the failure mode this catches, and the contract test cannot see it because it compares
#: the *declared* schema against itself.
REPORT_SECTIONS = {
    "pack_code",
    "pack_name",
    "pack_source",
    "snapshot_revision",
    "snapshot_stale",
    "cards_printed",
    "cards_in_pack",
    "faces_printed",
    "page_count",
    "decklist_printed",
    "decklist_source_url",
    "resolutions",
    "omitted",
    "unused_files",
    "uninterpretable_files",
    "conflicts",
    "low_resolution",
}


def test_the_report_carries_every_section_the_data_model_names(cap):
    assert set(cap.to_json()) == REPORT_SECTIONS


def test_a_report_survives_a_round_trip_through_the_run_record(cap):
    """FR-030b — the report lives on the run, so an incomplete pack stays legible later.

    It is stored as JSON and read back on a visit a week afterwards, so anything that does
    not survive the round trip is a section the returning user does not get.
    """
    again = AssemblyReport.from_json(cap.to_json())
    assert again.to_json() == cap.to_json()


# ---------------------------------------------------------------------------- the pack


def test_the_pack_and_how_it_was_chosen_are_reported(cap):
    """FR-012, FR-012b, SC-009a — a user-selected pack is never reported as identified."""
    assert cap.pack_code == "cap"
    assert cap.pack_name == "Captain America"
    assert cap.pack_source == "identified"


def test_a_user_selected_pack_says_so(cap_inputs):
    report = build_report(**{**cap_inputs, "pack_source": "user_selected"})
    assert report.pack_source == "user_selected"


# -------------------------------------------------------------------------- the groups


def test_every_resolution_names_the_group_its_card_belongs_to(cap):
    """FR-015e, SC-002b — the layout deliberately does not separate the groups.

    A page routinely carries the last player cards and the first nemesis cards, so this is
    the only thing that lets the user sort the cut stack.
    """
    groups = {entry["group"] for entry in cap.resolutions}
    assert {"player", "identity", "nemesis"} <= groups
    assert all(entry["group"] in {g.value for g in Group} for entry in cap.resolutions)


def test_the_identity_card_is_distinguished_from_the_player_cards(cap):
    """FR-015a — the pack is named after this card, and it is one card among 59."""
    identity = {e["card_code"] for e in cap.resolutions if e["group"] == "identity"}
    assert identity == {"03001a", "03001b"}


def test_the_nemesis_set_is_distinguished_from_the_player_cards(cap):
    """FR-015b — kept distinct in the report, never separated on the page."""
    nemesis = {e["card_code"] for e in cap.resolutions if e["group"] == "nemesis"}
    assert {"03027", "03028", "03029", "03030"} <= nemesis


# ------------------------------------------------------------------------ the decklist


def test_an_undecided_decklist_is_not_yet_printed_and_names_where_to_get_one(cap):
    """FR-013c, SC-006j — a pack printed without one is never indistinguishable."""
    assert cap.decklist_printed is False
    assert cap.decklist_source_url
    assert "hallofheroes" in cap.decklist_source_url


# --------------------------------------------------------------------- substitutions


def test_a_borrowed_image_is_reported_with_the_card_the_file_and_the_reason(cap):
    """FR-024, SC-005 — no substitution is silent, and a wrong one can be rejected."""
    borrowed = [e for e in cap.resolutions if e["provenance"] == "reprint"]
    assert borrowed
    for entry in borrowed:
        assert entry["card_name"]
        assert entry["file"]
        assert entry["note"], f"{entry['card_code']} was borrowed and does not say why"


def test_an_exact_positional_match_is_not_reported_as_a_substitution(cap):
    """The one provenance that needs no explanation.

    If it were flagged, every run would be nothing but substitutions and SC-005's list
    would be noise the user learns to skip.
    """
    exact = [e for e in cap.resolutions if e["provenance"] == "folder_position"]
    assert exact
    assert all(entry["note"] is None for entry in exact)


# -------------------------------------------------------------------- manual choices


def test_an_uploaded_file_is_reported_by_its_own_name_and_stays_distinguishable(cap_inputs):
    """FR-027, FR-029, SC-006c — a manual choice never masquerades as an automatic one.

    The file is named as the user named it, not as a digest under the run directory: they
    chose it and must be able to recognise it a week later.
    """
    manual = Resolution(
        card_code="03031",
        card_name="Enraged",
        side=Side.FRONT,
        provenance=Provenance.MANUAL,
        source=Source.UPLOAD,
        ref="uploads/" + "f" * 64,
        content_digest="f" * 64,
        original_filename="enraged scanned again.tiff",
    )
    report = build_report(**{**cap_inputs, "resolutions": [*cap_inputs["resolutions"], manual]})
    entry = next(e for e in report.resolutions if e["card_code"] == "03031")
    assert entry["provenance"] == "manual"
    assert entry["source"] == "upload"
    assert entry["file"] == "enraged scanned again.tiff"


# ------------------------------------------------------------------------- omissions


def test_a_card_printed_without_is_named_in_the_report_and_not_counted_as_printed(cap_inputs):
    """FR-030b, SC-006e — an incomplete deck is never indistinguishable from a complete one.

    Two halves, and the second is the one that bites: naming the card while still counting
    it among those printed would leave the user reading a report that contradicts itself.
    """
    omitted = Resolution(
        card_code="03031",
        card_name="Enraged",
        side=Side.FRONT,
        provenance=Provenance.OMITTED,
        source=Source.LIBRARY,
        ref="",
        content_digest="",
    )
    resolutions = [*cap_inputs["resolutions"], omitted]
    built = build_catalog(
        pack_code="cap",
        pack_name="Captain America",
        cards=cap_inputs["cards"],
        resolutions=resolutions,
        snapshot_revision=REVISION,
        decklist=cap_inputs["decklist"],
    )
    report = build_report(**{**cap_inputs, "resolutions": resolutions, "built": built})

    assert [e["card_code"] for e in report.omitted] == ["03031"]
    assert report.omitted[0]["card_name"] == "Enraged"
    assert "03031" not in {e["card_code"] for e in report.resolutions}
    # Unchanged from the same run without the omission: a card printed without is a card
    # not printed, whatever else the report says about it.
    assert report.cards_printed == build_report(**cap_inputs).cards_printed


# -------------------------------------------------------------------------- upstream


def test_the_snapshot_the_run_resolved_against_is_reported(cap):
    """FR-044, FR-044a — which card data produced this, and whether it was stale."""
    assert cap.snapshot_revision == REVISION
    assert cap.snapshot_stale is False


def test_a_stale_snapshot_is_reported_as_stale(cap_inputs):
    report = build_report(**{**cap_inputs, "snapshot_stale": True})
    assert report.snapshot_stale is True


# ----------------------------------------------------------------------------- counts


def _resolution(code: str, name: str, side: Side, quantity: int, ref: str) -> Resolution:
    return Resolution(
        card_code=code,
        card_name=name,
        side=side,
        provenance=Provenance.FOLDER_POSITION,
        source=Source.LIBRARY,
        ref=ref,
        content_digest="0" * 64,
        quantity=quantity,
    )


@pytest.fixture(scope="module")
def double_sided_report():
    """One genuinely double-sided card, printed twice, and nothing else.

    `26002` Intangible is one code with two faces and no linked card, so two copies of it
    are **two cards and four faces** — the distinction FR-018 turns on, and the one a
    report counting faces as cards gets wrong by exactly a factor of two.
    """
    cards = [c for c in pack_cards("vision") if c.code == "26002"]
    assert cards and cards[0].double_sided, "the fixture must carry a double-sided card"
    quantity = cards[0].quantity
    resolutions = [
        _resolution("26002", "Intangible", Side.FRONT, quantity, "a.tiff"),
        _resolution("26002", "Intangible", Side.BACK, quantity, "b.tiff"),
    ]
    built = build_catalog(
        pack_code="vision",
        pack_name="Vision",
        cards=cards,
        resolutions=resolutions,
        snapshot_revision=REVISION,
        decklist=None,
    )
    report = build_report(
        pack_code="vision",
        pack_name="Vision",
        pack_source="identified",
        cards=cards,
        resolutions=resolutions,
        built=built,
        decklist=None,
        snapshot_revision=REVISION,
    )
    return report, quantity


def test_the_unit_is_cards_not_faces(double_sided_report):
    """FR-018 — the pack listing counts in cards, so the comparison must too."""
    report, quantity = double_sided_report
    assert report.cards_printed == quantity
    assert report.cards_in_pack == quantity


def test_the_face_count_is_reported_alongside_the_card_count(double_sided_report):
    """FR-018, SC-002b — the page count follows from faces, so both are stated.

    Reported *alongside*, never instead: a double-sided card is one card and two faces, and
    a report giving only one of the two numbers cannot answer both questions the user has.
    """
    report, quantity = double_sided_report
    assert report.faces_printed == quantity * 2
    assert report.faces_printed != report.cards_printed


def test_cards_printed_is_reported_against_what_the_pack_listing_records(cap):
    """SC-006a — an incomplete run is visible as a number as well as a list.

    `cap` is 34 records and 59 physical cards; the fixture library leaves three unresolved,
    so this run is genuinely short and must say so.
    """
    assert cap.cards_in_pack == 59
    assert 0 < cap.cards_printed < cap.cards_in_pack


def test_the_decklist_card_is_counted_in_neither_total(cap_inputs):
    """FR-013b, FR-018 — it is not one of the pack's cards and never inflates either count."""
    from marchamp.assembly.decklist import DecklistDecision

    decklist = cap_inputs["decklist"].decide(DecklistDecision.CONFIRM)
    printed = build_catalog(
        pack_code="cap",
        pack_name="Captain America",
        cards=cap_inputs["cards"],
        resolutions=cap_inputs["resolutions"],
        snapshot_revision=REVISION,
        decklist=decklist,
    )
    report = build_report(**{**cap_inputs, "decklist": decklist, "built": printed})

    assert report.decklist_printed is True
    assert report.cards_printed == build_report(**cap_inputs).cards_printed
    assert report.faces_printed == build_report(**cap_inputs).faces_printed


#: Anything named like a target invites a comparison FR-019 forbids. Asserted on the keys
#: rather than on prose because the report is what a consumer reads, and a field called
#: `expected_total` would be acted on whatever the docstring beside it said.
_FORBIDDEN_KEY_FRAGMENTS = ("expected", "target", "should", "shortfall")


def test_no_report_field_names_an_expected_total(cap):
    """FR-018, FR-019, SC-006a — the tool expects no total and warns on none.

    Deck sizes were measured at 40, 41, and 42, and `pack.total` disagrees with the summed
    quantity on two of three packs (research R12). Any expected total is a false alarm
    generator, and the one this feature's earlier design carried was 40.
    """
    keys = set(cap.to_json())
    for fragment in _FORBIDDEN_KEY_FRAGMENTS:
        assert not any(fragment in key for key in keys), f"{fragment!r} appears in {keys}"


def test_a_short_pack_produces_no_warning_about_being_short(cap):
    """FR-019 — the *list* of missing cards is the report, not a total-based alarm.

    `cap` prints fewer cards than its listing records against this library. Nothing in the
    warning sections may fire on that fact alone.
    """
    assert cap.cards_printed < cap.cards_in_pack
    assert cap.low_resolution == []
    assert all("total" not in entry["reason"].lower() for entry in cap.conflicts)


# ------------------------------------------- conflicts, duplicates, unreadable filenames

#: A folder built to hold each of the three things the library does wrong, and nothing else.
#: Derived fixtures cannot serve here: what is under test is the *reporting* of an awkward
#: folder, and asserting it against a folder that also holds 22 well-behaved files makes the
#: failure message a needle in a haystack.
AWKWARD_FOLDER = "Heros/Someone_Testhero"
#: Two different cards claiming one position. Never resolved by picking (FR-033).
CLASH_A = f"{AWKWARD_FOLDER}/Aggression_Card One_Event_5.tiff"
CLASH_B = f"{AWKWARD_FOLDER}/Leadership_Card Two_Event_5.tiff"
#: One card in two renditions. Resolved deterministically, and still reported (FR-034).
#: `.tif` sorts before `.tiff`, so it is the one chosen — that is the whole rule.
RENDITION_CHOSEN = f"{AWKWARD_FOLDER}/Basic_Card Three_Ally_7.tif"
RENDITION_DUPLICATE = f"{AWKWARD_FOLDER}/Basic_Card Three_Ally_7.tiff"
#: Matches none of the three conventions and is not a decklist (FR-032).
UNREADABLE_NAME = f"{AWKWARD_FOLDER}/random notes.tiff"


@pytest.fixture(scope="module")
def awkward_report(tmp_path_factory):
    """A report over a folder holding a conflict, a duplicate pair, and a junk filename."""
    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, make_card_image

    root = tmp_path_factory.mktemp("awkward-library")
    for rel in (CLASH_A, CLASH_B, RENDITION_CHOSEN, RENDITION_DUPLICATE, UNREADABLE_NAME):
        make_card_image(root / rel, "X", width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)
    index = build_index(root)

    # One card did resolve, to the chosen rendition — so "which was chosen" has an answer
    # to be right or wrong about.
    used = _resolution("90007", "Card Three", Side.FRONT, 1, RENDITION_CHOSEN)
    return build_report(
        pack_code="test",
        pack_name="Test Pack",
        pack_source="identified",
        cards=[],
        resolutions=[used],
        built=None,
        decklist=None,
        snapshot_revision=REVISION,
        index=index,
        hero_folder=AWKWARD_FOLDER,
    )


def _reasons(report, section: str) -> dict[str, str]:
    return {entry["file"]: entry["reason"] for entry in getattr(report, section)}


def test_a_position_conflict_names_both_sides(awkward_report):
    """FR-033 — both files, so the user can see which two are fighting over one number."""
    conflicts = _reasons(awkward_report, "conflicts")
    assert CLASH_A in conflicts
    assert CLASH_B in conflicts
    assert "5" in conflicts[CLASH_A]


def test_a_position_conflict_names_the_other_side_in_each_entry(awkward_report):
    """Naming both sides means each entry points at its opposite.

    A list of two files with no statement of what they collide with reads as two unrelated
    problems, and the user has to work out that they are one.
    """
    conflicts = _reasons(awkward_report, "conflicts")
    assert "Card Two" in conflicts[CLASH_A] or CLASH_B in conflicts[CLASH_A]
    assert "Card One" in conflicts[CLASH_B] or CLASH_A in conflicts[CLASH_B]


def test_a_position_conflict_is_resolved_by_neither_file(awkward_report):
    """FR-033 — a resolver that guessed would pair a card with confidently wrong art.

    The user is right there to be asked, which is why neither side is used.
    """
    used = {entry["file"] for entry in awkward_report.resolutions}
    assert CLASH_A not in used
    assert CLASH_B not in used


def test_a_duplicate_rendition_names_which_one_was_chosen(awkward_report):
    """FR-034 — reported, and the pick is deterministic rather than arbitrary.

    `.tif` before `.tiff` by filename order, so the same library always yields the same PDF
    (Principle V, FR-005j). A duplicate is not a failure; being silent about it is.
    """
    conflicts = _reasons(awkward_report, "conflicts")
    assert RENDITION_DUPLICATE in conflicts
    assert RENDITION_CHOSEN in conflicts[RENDITION_DUPLICATE]
    assert RENDITION_CHOSEN not in conflicts


def test_a_duplicate_rendition_is_not_reported_as_a_position_conflict(awkward_report):
    """The distinction FR-033 and FR-034 turn on: one card twice, not two cards once.

    Collapsing them would either refuse every `.tif`/`.tiff` pair in the library or resolve
    genuine conflicts by picking, and both are wrong.
    """
    reason = _reasons(awkward_report, "conflicts")[RENDITION_DUPLICATE]
    assert "duplicate" in reason.lower()
    assert "claimed by" not in reason.lower()


def test_an_uninterpretable_filename_in_the_hero_folder_is_named(awkward_report):
    """FR-032 — the harm is a scan sitting in the folder the user pointed at, ignored."""
    assert UNREADABLE_NAME in _reasons(awkward_report, "uninterpretable_files")


def test_every_awkward_file_is_still_accounted_for_as_unused(awkward_report):
    """FR-031 — a conflict is a reason a file went unused, not an excuse to skip it."""
    unused = _reasons(awkward_report, "unused_files")
    assert {CLASH_A, CLASH_B, RENDITION_DUPLICATE, UNREADABLE_NAME} <= set(unused)
    assert RENDITION_CHOSEN not in unused


# ------------------------------------------------------- resolution, warned not refused

#: Far below the 300 DPI the application requires at 63.5x88.9 mm, which needs ~750x1050.
TOO_SMALL_W, TOO_SMALL_H = 240, 336


def _report_over(root, ref: str, **overrides):
    """A one-card report over a purpose-built library, for the warning sections."""
    from marchamp.assets.local_dir import LocalDirectoryStore

    used = _resolution("90001", "Small Card", Side.FRONT, 1, ref)
    kwargs = {
        "pack_code": "test",
        "pack_name": "Test Pack",
        "pack_source": "identified",
        "cards": [],
        "resolutions": [used],
        "built": None,
        "decklist": None,
        "snapshot_revision": REVISION,
        "index": build_index(root),
        "hero_folder": AWKWARD_FOLDER,
        "store": LocalDirectoryStore(root),
    }
    return build_report(**{**kwargs, **overrides})


@pytest.fixture
def small_scan(tmp_path):
    """A folder whose one scan cannot print at 300 DPI."""
    from tests.conftest import make_card_image

    ref = f"{AWKWARD_FOLDER}/Basic_Small Card_Ally_5.tiff"
    make_card_image(tmp_path / ref, "SMALL", width=TOO_SMALL_W, height=TOO_SMALL_H)
    return tmp_path, ref


def test_a_scan_below_the_print_resolution_floor_is_warned_about(small_scan):
    """FR-035 — reported, so the user can go and rescan it if they care."""
    root, ref = small_scan
    report = _report_over(root, ref)
    warned = {entry["file"]: entry["reason"] for entry in report.low_resolution}
    assert ref in warned
    assert "dpi" in warned[ref].lower()


def test_a_low_resolution_scan_is_not_a_refusal(small_scan):
    """FR-035, and the whole distinction it draws.

    Feature 001 refuses one (FR-010) because it renders a catalog someone authored and can
    fix. This feature reads a library someone else organised: refusing would make a whole
    pack unprintable over one scan the user cannot re-take, and they are entitled to decide
    that a slightly soft card is fine.
    """
    root, ref = small_scan
    report = _report_over(root, ref)
    # Still used, still reported as a resolution, and named nowhere that means "rejected".
    assert ref in {entry["file"] for entry in report.resolutions}
    assert ref not in {entry["file"] for entry in report.unused_files}
    assert report.low_resolution, "a warning is the whole of what FR-035 asks for"


def test_a_scan_that_clears_the_floor_is_not_warned_about(tmp_path):
    """The control. Without it the warning could fire on everything and still pass."""
    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, make_card_image

    ref = f"{AWKWARD_FOLDER}/Basic_Big Card_Ally_5.tiff"
    make_card_image(tmp_path / ref, "BIG", width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)
    assert _report_over(tmp_path, ref).low_resolution == []


def test_the_warning_reads_the_floor_from_the_render_module(small_scan):
    """One definition of "too small", shared with 001's `validate_source` (FR-010).

    A second threshold written here would drift from the one the renderer enforces, and the
    report would then disagree with the document about the same file.
    """
    from marchamp.render.images import MIN_DPI

    root, ref = small_scan
    (entry,) = _report_over(root, ref).low_resolution
    assert str(MIN_DPI) in entry["reason"]


def test_a_source_that_cannot_be_read_at_all_is_named_rather_than_swallowed(tmp_path):
    """FR-037 — a file the run resolved to and then could not decode is not silence.

    There is no separate section for it in the contract, so it is warned about here with a
    sentence of its own. Building the report must not raise: a corrupt scan is something to
    report, not something that replaces the whole report with a stack trace.
    """
    ref = f"{AWKWARD_FOLDER}/Basic_Broken Card_Ally_6.tiff"
    path = tmp_path / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a TIFF")

    (entry,) = _report_over(tmp_path, ref).low_resolution
    assert entry["file"] == ref
    assert "read" in entry["reason"].lower()


# ----------------------------------------------------- nothing generic, ever (FR-037)

#: Words that stand in for an explanation. A report saying any of these on its own sends the
#: user to read source code, which is precisely what SC-008 requires them not to have to do.
GENERIC = ("error", "failed", "invalid", "unknown", "something went wrong", "n/a")

REPORTED_FILE_SECTIONS = ("unused_files", "uninterpretable_files", "conflicts", "low_resolution")


def test_every_reported_file_names_the_file_and_says_something_specific(awkward_report):
    """FR-037 — the file at fault, by name, with a sentence about it."""
    for section in REPORTED_FILE_SECTIONS:
        for entry in getattr(awkward_report, section):
            assert entry["file"], f"{section} carries an entry with no file"
            assert len(entry["reason"]) > 20, f"{section}: {entry['reason']!r} explains nothing"
            assert entry["reason"].strip().lower() not in GENERIC


def test_every_resolution_names_the_card_and_the_file_it_came_from(cap):
    """FR-024, SC-005 — a substitution the user cannot trace is one they cannot reject."""
    for entry in cap.resolutions:
        assert entry["card_code"] and entry["card_name"]
        assert entry["file"]


def test_a_conflict_names_the_card_it_cost(tmp_path):
    """SC-008 — "position 5 is ambiguous" is half an answer.

    The other half is which card the user is now missing because of it. Without that they
    have to work back from a position number to a card themselves, which means opening the
    card data — the thing the report exists to save them.
    """
    from marchamp.assembly.resolve import UnresolvedFace
    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, make_card_image

    for rel in (CLASH_A, CLASH_B):
        make_card_image(tmp_path / rel, "X", width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)

    lost = UnresolvedFace(
        card_code="90005",
        card_name="Card One",
        side=Side.FRONT,
        group=Group.PLAYER,
        searched=("position 5 in the hero folder",),
        conflict=(CLASH_A, CLASH_B),
    )
    report = build_report(
        pack_code="test",
        pack_name="Test Pack",
        pack_source="identified",
        cards=[],
        resolutions=[],
        built=None,
        decklist=None,
        snapshot_revision=REVISION,
        index=build_index(tmp_path),
        hero_folder=AWKWARD_FOLDER,
        unresolved=[lost],
    )
    reasons = " ".join(entry["reason"] for entry in report.conflicts)
    assert "Card One" in reasons
    assert "90005" in reasons
