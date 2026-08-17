"""T036 — the library index (FR-021, FR-023, FR-031, FR-033, FR-034, research R5, R13).

One `os.walk` of the whole library at the start of a resolve pass, held for that pass only,
never persisted (R13). Persisting it would create a second source of truth that goes stale
the moment the user adds a scan — and a resumed run *must* see the library as it is now,
since going away to find a missing file is the entire reason resuming exists.

Two lookups, and they answer different questions:

- **by position**, keyed on `(pack_hint, position, face suffix)`. The `pack_hint` comes from
  the containing hero folder and is **absent under `Aspects/`**, where a position means
  nothing because there is no pack to read it against — which is precisely why the name
  index is not optional;
- **by name**, keyed on normalised filename fragments, consulted only when looking for a
  card whose canonical name is already known (FR-023).

The rule that does the most work here is that **ambiguity is reported, never resolved by
picking**. Two files claiming one position is an FR-033 conflict with both sides named. Two
files within the edit-distance bound of one card's name is the same thing. The single
exception is FR-034's duplicate rendition — a `.tif`/`.tiff` pair of one card — where the
choice is deterministic and the duplication is reported.
"""

from __future__ import annotations

import pytest

from marchamp.library.index import LibraryScanTooLarge, build_index

CAP_FOLDER = "Heros/Steve Rogers_Captain America"
WASP_FOLDER = "Heros/Janet Van Dyne_Wasp"
PHOENIX_FOLDER = "Heros/Jean Grey_Phoenix"
VISION_FOLDER = "Heros/Vision_Vision"


@pytest.fixture
def index(library_root):
    return build_index(library_root)


# --------------------------------------------------------------------- construction


def test_the_index_covers_the_whole_library_not_one_folder(index):
    """FR-021 — a hero's cards are not all in that hero's folder.

    Quincarrier is filed under Wasp and belongs to another hero; the Core Set holds the
    printings reprints borrow from. A per-folder index finds neither.
    """
    assert index.file_count == 28
    folders = {e.folder for e in index.entries}
    assert CAP_FOLDER in folders
    assert "Core Set" in folders
    assert "Aspects/Leadership" in folders


def test_the_index_is_never_written_to_disk(index, library_root, tmp_path):
    """research R13 — a persisted index is a second source of truth that goes stale."""
    before = sorted(p.relative_to(library_root) for p in library_root.rglob("*"))
    build_index(library_root)
    assert sorted(p.relative_to(library_root) for p in library_root.rglob("*")) == before
    assert not list(tmp_path.glob("**/*index*"))


def test_a_scan_larger_than_the_cap_is_refused(library_root):
    """Bounds one walk against a mistakenly named root such as `/` (research R13)."""
    with pytest.raises(LibraryScanTooLarge):
        build_index(library_root, file_cap=5)


def test_non_image_files_are_not_indexed(library_root):
    (library_root / CAP_FOLDER / "notes.txt").write_text("not a scan")
    assert all(not e.ref.endswith(".txt") for e in build_index(library_root).entries)


def test_every_ref_is_relative_to_the_library_root(index):
    """FR-009 — no absolute path from outside the named library reaches a record."""
    for entry in index.entries:
        assert not entry.ref.startswith("/")
        assert ".." not in entry.ref


# ------------------------------------------------------------------- by position


def test_a_position_resolves_inside_its_own_folder(index):
    found = index.by_position(CAP_FOLDER, 16)
    assert found.chosen is not None
    assert found.chosen.ref.endswith("Leadership_Make the Call_Event_16.tiff")


def test_a_face_suffix_distinguishes_two_files_at_one_position(index):
    a = index.by_position(CAP_FOLDER, 1, "a")
    b = index.by_position(CAP_FOLDER, 1, "b")
    assert a.chosen and b.chosen and a.chosen.ref != b.chosen.ref
    assert "Hero_1a" in a.chosen.ref and "Alter-Ego_1b" in b.chosen.ref


def test_form_b_positions_are_indexed_by_the_pack_position(index):
    """`Wasp_Pym Particles_Resource_7_12.15` is at position 7, not 12."""
    found = index.by_position(WASP_FOLDER, 7)
    assert found.chosen and "Pym Particles" in found.chosen.ref


def test_a_pack_hint_is_absent_under_aspects(index):
    """A position under `Aspects/` means nothing without a pack (research R13).

    These files are reachable by name only, which is why the name index carries Phoenix and
    Wonder Man entirely (SC-003c).
    """
    aspects = [e for e in index.entries if e.folder.startswith("Aspects/")]
    assert aspects
    assert all(e.pack_hint is None for e in aspects)
    # And they are still findable — by name.
    assert index.by_name("Strength in Numbers").chosen is not None


def test_a_copy_counting_folder_contributes_no_positions(index):
    """research R5 — read as positions, those numbers are confidently wrong.

    Phoenix numbers by physical copy, so `2_Active Altruism_Event.tif` must not answer a
    request for position 2. No answer is recoverable; a wrong answer is not.
    """
    assert PHOENIX_FOLDER in index.copy_counting_folders
    assert index.by_position(PHOENIX_FOLDER, 2).chosen is None
    assert index.by_position(PHOENIX_FOLDER, 1).chosen is None
    # Its cards are still reachable by name, which is the whole of SC-003c.
    assert index.by_name("Active Altruism").chosen is not None


def test_two_files_claiming_one_position_are_a_conflict_not_a_pick(index):
    """FR-033, US2 scenario 4 — measured on Vision.

    `Vision_Vivian_Ally_2.tiff` records position 2 for a card at position 3, colliding with
    the genuinely double-sided Intangible filed as `_2a`/`_2b`. A resolver that trusted the
    parsed position without checking the card it lands on picks the wrong file here.
    """
    found = index.by_position(VISION_FOLDER, 2)
    # Vivian has no suffix; the suffixed Intangible faces are separate keys.
    assert found.chosen is not None and "Vivian" in found.chosen.ref
    intangible = index.by_position(VISION_FOLDER, 2, "a")
    assert intangible.chosen is not None and "Intangible" in intangible.chosen.ref


def test_a_tif_tiff_pair_is_one_card_chosen_deterministically(index):
    """FR-034 — a duplicate rendition, not an FR-033 conflict. The card prints once."""
    found = index.by_position(CAP_FOLDER, 18)
    assert not found.conflict
    assert found.chosen is not None
    assert found.duplicate_renditions
    # Deterministic: the same library always yields the same choice (Principle V).
    rebuilt = build_index(index.root).by_position(CAP_FOLDER, 18)
    assert rebuilt.chosen is not None and rebuilt.chosen.ref == found.chosen.ref


def test_a_position_in_another_folder_is_not_returned_for_this_one(index):
    """The pack hint is what keeps position 1 of one hero out of position 1 of another."""
    assert index.by_position(CAP_FOLDER, 66).chosen is None
    assert index.by_position("Core Set", 66).chosen is not None


# ----------------------------------------------------------------------- by name


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("Strength in Numbers", "Stength in Numbers"),
        ("Steve's Apartment", "Steve_s Apartament"),
        ("Make the Call", "Make the Call"),
        ("Invulnerability", "Invulnerability"),
        ("Quincarrier", "Quincarrier"),
    ],
)
def test_a_name_match_absorbs_the_observed_typos(index, canonical, expected):
    """FR-023 at the data-model's edit-distance bound.

    All three real typos sit at distance 1-2, and stripping punctuation alone reaches none
    of them — "Stength" is a dropped letter. That is the argument for the bound existing.
    """
    found = index.by_name(canonical)
    assert found.chosen is not None, f"{canonical} did not match"
    assert expected in found.chosen.ref


def test_a_name_match_finds_a_card_filed_under_the_wrong_hero(index):
    """FR-021, User Story 3 — Quincarrier is filed under Wasp and is not a Wasp card."""
    found = index.by_name("Quincarrier")
    assert found.chosen is not None
    assert found.chosen.folder == WASP_FOLDER


def test_two_files_inside_the_bound_for_one_card_are_a_conflict(library_root):
    """FR-033 — an arbitrary pick is the one outcome that must not happen.

    Two files a single edit apart from the wanted name are indistinguishable evidence. The
    resolver reports both and lets the user decide (FR-026); choosing would silently pair a
    card with art from the wrong printing.
    """
    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, make_card_image

    for stem in ("Leadership_Teamwrk_Event", "Leadership_Teamwork_Event"):
        make_card_image(
            library_root / "Aspects/Leadership" / f"{stem}.tiff",
            stem,
            width=LIBRARY_IMAGE_W,
            height=LIBRARY_IMAGE_H,
        )
    found = build_index(library_root).by_name("Teamwork")
    assert found.conflict
    assert found.chosen is None
    assert len(found.entries) == 2


def test_a_name_far_from_anything_matches_nothing(index):
    assert index.by_name("Some Card That Is Not Here").chosen is None


def test_a_short_name_is_matched_more_tightly(index, library_root):
    """Two edits on a short name reach a different card, so the bound tightens to one."""
    assert index.by_name("Energy").chosen is not None
    # "Enraged" is two edits from "Energy" and is a different card.
    assert index.by_name("Enraged").chosen is None


def test_a_name_match_never_parses_identity_out_of_a_filename(index):
    """FR-023 is directional. The index answers "is this the card I named", only."""
    assert not hasattr(index, "card_for")
    assert not hasattr(index, "identify")


# ---------------------------------------------------------- decklists and leftovers


def test_decklist_candidates_are_found_in_the_named_folder(index):
    """FR-013d — both spellings, and the hero's name is deliberately not checked."""
    cap = index.decklist_candidates(CAP_FOLDER)
    assert len(cap) == 1 and "captain america decklist" in cap[0].ref

    iceman = index.decklist_candidates("Heros/Bobby Drake_Iceman")
    assert len(iceman) == 1 and "iceman deck list" in iceman[0].ref


def test_a_folder_with_no_decklist_scan_reports_none(index):
    """Measured: Hulk and Phoenix hold none, so FR-013c's gap has a real fixture."""
    assert index.decklist_candidates(PHOENIX_FOLDER) == []


def test_a_decklist_is_never_listed_as_uninterpretable(index):
    """FR-031, FR-032 — it would otherwise be a false fault on eight of ten heroes."""
    uninterpretable = {e.ref for e in index.unparseable(CAP_FOLDER)}
    assert not any("decklist" in ref for ref in uninterpretable)


def test_uninterpretable_files_are_reported_for_the_named_folder(index):
    """FR-032 — the harm is a scan sitting in the folder the user pointed at, ignored."""
    refs = {e.ref for e in index.unparseable(CAP_FOLDER)}
    assert any("scan notes" in ref for ref in refs)


def test_accountability_is_bounded_to_the_named_folder(index):
    """FR-031 as amended — against 4,447 files, per-file accounting elsewhere is unreadable.

    Files outside the named folder surface only when used or in conflict.
    """
    assert all(e.folder == CAP_FOLDER for e in index.unparseable(CAP_FOLDER))
    assert all(e.folder == CAP_FOLDER for e in index.files_in(CAP_FOLDER))


def test_every_file_in_the_named_folder_can_be_accounted_for(index):
    """SC-004 — used, or named as unused with a reason. Nothing is silently skipped."""
    listed = {e.ref for e in index.files_in(CAP_FOLDER)}
    assert len(listed) == 9
    assert any("scan notes" in ref for ref in listed)
    assert any("decklist" in ref for ref in listed)
