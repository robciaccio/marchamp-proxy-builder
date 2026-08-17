"""T048a — finding the decklist scan (FR-013c, FR-013d, FR-031, FR-032, FR-034).

The decklist card is US1's, not US4's. Without it the MVP prints a pack the user cannot build
the starter deck from, which is the reason for printing packs at all.

It is **step 0** and never enters the FR-020-FR-025 cascade: it has no pack code, no position,
and no canonical name, so there is nothing for the cascade's four steps to match on. What
identifies it is a literal `deck\\s*list` inside the filename stem, which is a substring test
rather than FR-023's edit-distance name match.

Two properties of the real library shape the rule, both measured when T005 derived the fixture:

- **The spelling and the case vary.** `Captain America Decklist.tif` and
  `0A_Wonder Man Deck List.tif` are the two forms, and the second carries a leading token, so
  the match is case-insensitive and searched *within* the stem rather than anchored to it.
- **Two of the ten hero folders hold no decklist at all.** Hulk's and Phoenix's are the real
  FR-013c case, and a run over either that reported a decklist card would be silently wrong.

The exclusion matters as much as the match: a decklist filename matches none of the library's
three conventions, so without being classified first every one of them is an FR-032
uninterpretable-file report — on eight of the ten acceptance heroes.
"""

from __future__ import annotations

import pytest

from marchamp.assembly.decklist import (
    DecklistCandidate,
    DecklistDecision,
    find_decklist,
)
from marchamp.library.filenames import Form, parse_filename
from marchamp.library.index import build_index
from tests.conftest import ACCEPTANCE_HEROES

#: Measured across the fixture library (T005). Eight folders hold one, two do not.
FOLDERS_WITH_A_DECKLIST = {
    "ant": "Ant-Man Decklist.tiff",
    "bkw": "Black Widow Decklist.tiff",
    "cap": "Captain America Decklist.tif",
    "msm": "Ms.Marvel Decklist.tif",
    "stld": "Star-Lord Decklist.tiff",
    "thor": "Thor Decklist.tiff",
    "wonder_man": "0A_Wonder Man Deck List.tif",
    "wsp": "Wasp Decklist.tif",
}
FOLDERS_WITHOUT_A_DECKLIST = ("hlk", "phoenix")


# ------------------------------------------------------------------ filename classification


@pytest.mark.parametrize(
    "filename",
    [
        "Captain America Decklist.tif",
        "captain america decklist.tif",
        "CAPTAIN AMERICA DECKLIST.TIF",
        "0A_Wonder Man Deck List.tif",
        "iceman deck list.tiff",
        "psylocke decklist.jpg",
    ],
)
def test_both_spellings_and_any_case_are_recognised(filename):
    """FR-013d. The library writes these title-cased, and one carries a leading `0A_`.

    research.md originally transcribed them lowercase, which is why the case is asserted
    explicitly rather than assumed — a rule anchored at the start of the stem, or one that
    compared case-sensitively, passes on Captain America and fails on Wonder Man.
    """
    assert parse_filename(filename).form is Form.DECKLIST


@pytest.mark.parametrize(
    "filename",
    [
        "Leadership_Make the Call_Event_16.tiff",
        "Captain America_Steve's Apartament_Support_7.tiff",
        "2_Active Altruism_Event.tif",
        "scan notes.txt.tiff",
    ],
)
def test_an_ordinary_card_scan_is_not_a_decklist(filename):
    assert parse_filename(filename).form is not Form.DECKLIST


def test_a_decklist_is_excluded_from_the_uninterpretable_report(scan_library):
    """FR-031, FR-032 — otherwise eight of the ten heroes carry a false fault.

    A decklist filename matches none of the three conventions. Reported as uninterpretable it
    would tell the user something is wrong with a file that is exactly where it should be.
    """
    index = build_index(scan_library)
    for pack_code in FOLDERS_WITH_A_DECKLIST:
        folder = ACCEPTANCE_HEROES[pack_code]
        unparseable = {e.filename for e in index.unparseable(folder)}
        assert FOLDERS_WITH_A_DECKLIST[pack_code] not in unparseable


# ------------------------------------------------------------------------------ detection


@pytest.mark.parametrize(("pack_code", "filename"), sorted(FOLDERS_WITH_A_DECKLIST.items()))
def test_each_folder_that_holds_a_decklist_proposes_exactly_one(pack_code, filename, scan_library):
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES[pack_code])
    assert found.candidate is not None
    assert found.candidate.filename == filename
    assert not found.conflict


@pytest.mark.parametrize("pack_code", FOLDERS_WITHOUT_A_DECKLIST)
def test_a_folder_with_no_decklist_reports_the_gap(pack_code, scan_library):
    """FR-013c — Hulk's and Phoenix's real case. The gap is named, never invented."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES[pack_code])
    assert found.candidate is None
    assert not found.conflict
    assert found.hall_of_heroes_url, "the gap must offer somewhere to get one (SC-006j)"


def test_the_application_never_fetches_the_hall_of_heroes(scan_library, no_network):
    """SC-006j — the address is shown to the user; the tool does not go there.

    FR-002 allows exactly one outbound host and it is not this one, so offering the address
    and fetching it are very different things.
    """
    index = build_index(scan_library)
    find_decklist(index, ACCEPTANCE_HEROES["hlk"])


def test_a_tif_tiff_pair_of_one_stem_is_one_candidate_not_a_conflict(library_root):
    """FR-034 — duplicate renditions are resolved deterministically, never prompted.

    A user asked to choose between `x.tif` and `x.tiff` is being asked a question with no
    meaningful answer.
    """
    folder = library_root / "Heros" / "Jean Grey_Phoenix"  # holds no decklist of its own
    source = (folder / "1_Phoenix_Hero.tif").read_bytes()
    for suffix in (".tif", ".tiff"):
        (folder / f"Phoenix Decklist{suffix}").write_bytes(source)
    index = build_index(library_root)
    found = find_decklist(index, "Heros/Jean Grey_Phoenix")
    assert found.candidate is not None
    assert not found.conflict
    # Deterministic, so the same library always yields the same PDF (Principle V).
    assert find_decklist(build_index(library_root), "Heros/Jean Grey_Phoenix").candidate == (
        found.candidate
    )


def test_two_different_stems_are_a_conflict_the_user_resolves(library_root):
    """FR-033 — two genuinely different files, so the tool asks rather than picks."""
    folder = library_root / "Heros" / "Jean Grey_Phoenix"
    source = (folder / "1_Phoenix_Hero.tif").read_bytes()
    (folder / "Phoenix Decklist.tif").write_bytes(source)
    (folder / "Phoenix Deck List v2.tif").write_bytes(source)
    index = build_index(library_root)
    found = find_decklist(index, "Heros/Jean Grey_Phoenix")
    assert found.conflict
    assert found.candidate is None
    assert len(found.candidates) == 2


# ------------------------------------------------------------------------------- decisions


def test_a_candidate_is_proposed_and_not_printed_until_accepted(scan_library):
    """FR-013d — the tool proposes; the user accepts. A pick is not an acceptance."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"])
    assert found.candidate is not None
    assert not found.decided
    assert not found.printed


def test_confirming_prints_the_candidate(scan_library):
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"])
    decided = found.decide(DecklistDecision.CONFIRM)
    assert decided.decided
    assert decided.printed
    assert decided.chosen_ref == found.candidate.ref


def test_selecting_a_different_file_prints_that_one(scan_library):
    index = build_index(scan_library)
    folder = ACCEPTANCE_HEROES["cap"]
    found = find_decklist(index, folder)
    other = f"{folder}/Leadership_Quinjet_Support_19.tiff"
    decided = found.decide(DecklistDecision.SELECT, ref=other)
    assert decided.printed
    assert decided.chosen_ref == other


def test_skipping_prints_no_decklist_and_is_not_a_failure(scan_library):
    """FR-030-shaped escape: a pack without a decklist card is still a printable pack."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"])
    decided = found.decide(DecklistDecision.SKIP)
    assert decided.decided
    assert not decided.printed
    assert decided.chosen_ref is None


def test_a_selected_ref_must_be_inside_the_hero_folder(scan_library):
    """FR-007 — the decision endpoint takes a library-relative ref from the browser."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"])
    with pytest.raises(ValueError):
        found.decide(DecklistDecision.SELECT, ref="../../etc/passwd")


def test_the_decklist_state_survives_a_round_trip(scan_library):
    """It lives on the run record, which is JSON on disk (ADR 0001)."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"]).decide(DecklistDecision.CONFIRM)
    restored = type(found).from_json(found.to_json())
    assert restored == found


def test_a_candidate_carries_no_path_from_outside_the_library(scan_library):
    """FR-009 — the candidate is shown to the user and written to the run's log."""
    index = build_index(scan_library)
    found = find_decklist(index, ACCEPTANCE_HEROES["cap"])
    assert isinstance(found.candidate, DecklistCandidate)
    assert not found.candidate.ref.startswith("/")
    assert str(scan_library) not in found.candidate.ref
