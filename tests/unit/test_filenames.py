"""T034 — parsing the library's filenames (FR-032, FR-023, research R5, R12).

Someone else organised this library and did it three different ways. Every case below was
measured against the real thing on 2026-08-16/17, and the ones that look like contrived
edge cases are the ones that actually cost a hero its cards.

The important distinction is between *no answer* and *a wrong answer*. A file with no
number is not an error: it enters the name index and is found by the card that wants it. A
file whose leading number counts physical copies is the dangerous case — read as a position,
`2_Active Altruism_Event.tif` is confidently wrong, and Phoenix and Wonder Man number their
whole hero sets that way. Which is why the copy-counting form is detected per *folder*:
one file in isolation cannot tell you which convention it is in.

And a suffix is evidence, never identity (R12). Vision's `_2a`/`_2b` are the two faces of
one code; Captain America's `_1a`/`_1b` are two distinct codes. Nothing in the filename
distinguishes them, so this module reports the suffix and refuses to interpret it — that is
the card data's job.
"""

from __future__ import annotations

import pytest

from marchamp.library.filenames import (
    Form,
    detect_copy_counting,
    normalise,
    parse_filename,
)

# --------------------------------------------------------------- the three conventions


def test_form_a_carries_a_trailing_position():
    parsed = parse_filename("Leadership_Make the Call_Event_16.tiff")
    assert parsed.form is Form.POSITION
    assert parsed.position == 16
    assert parsed.face_suffix is None


def test_form_a_with_a_face_suffix():
    parsed = parse_filename("Captain America_Captain America_Hero_1a.tiff")
    assert parsed.form is Form.POSITION
    assert parsed.position == 1
    assert parsed.face_suffix == "a"


def test_form_b_takes_the_position_and_ignores_the_set_numbering():
    """`{faction}_{Name}_{Type}_{position}_{set_position}.{set_total}`.

    The trailing `12.15` is the card's place in its set, not its place in the pack, and the
    `.15` reads as a file extension to anything naive.
    """
    parsed = parse_filename("Wasp_Pym Particles_Resource_7_12.15.tiff")
    assert parsed.form is Form.POSITION_SET
    assert parsed.position == 7


def test_form_c_reports_a_copy_number_and_never_a_position():
    """The form that produces a wrong answer rather than no answer (research R5).

    Read as a position, `2` is confidently wrong. Phoenix and Wonder Man number their whole
    hero sets this way, which is why SC-003c makes them an acceptance case.
    """
    parsed = parse_filename("2_Active Altruism_Event.tif")
    assert parsed.form is Form.COPY_NUMBER
    assert parsed.position is None
    assert parsed.copy_number == 2


def test_a_file_with_no_number_is_not_an_error():
    parsed = parse_filename("Basic_Invulnerability_Event.tiff")
    assert parsed.form is Form.NO_NUMBER
    assert parsed.position is None
    # It is name-matched only, so it must still produce name keys.
    assert parsed.name_keys


@pytest.mark.parametrize(
    "name",
    [
        "captain america decklist.tif",
        "iceman deck list.tiff",
        "psylocke decklist.jpg",
        "WASP DECKLIST.TIFF",
    ],
)
def test_a_decklist_scan_is_recognised_by_its_stem(name):
    """FR-013d. Both spellings occur, and the hero's name in it is deliberately not checked.

    `iceman deck list.tiff` sits under `Bobby Drake_Iceman`, so requiring the folder and the
    filename to agree would fail on exactly the folders the rule exists to serve.
    """
    assert parse_filename(name).form is Form.DECKLIST


def test_a_decklist_is_never_reported_as_uninterpretable():
    """FR-031, FR-032 — it matches none of the three conventions and is not a fault.

    Without this it would be listed as an uninterpretable file in the one folder where every
    file must be accounted for, on eight of the ten acceptance heroes.
    """
    parsed = parse_filename("captain america decklist.tif")
    assert parsed.form is not Form.UNPARSEABLE


@pytest.mark.parametrize("name", ["scan notes.txt.tiff", "IMG_0042.tiff", "Untitled.tiff"])
def test_something_matching_no_convention_is_reported_as_such(name):
    assert parse_filename(name).form is Form.UNPARSEABLE


# ------------------------------------------------------------ suffixes are ambiguous


def test_a_face_suffix_is_reported_and_not_interpreted():
    """research R12 — which mechanism a suffix means is decidable only from the card data.

    Vision's `_2a`/`_2b` are two faces of the single code `26002`; Captain America's
    `_1a`/`_1b` are the distinct codes `03001a`/`03001b`. A parser that decided here would
    be wrong for one of them, always.
    """
    vision = parse_filename("Vision_Intangible_Upgrade_2a.tiff")
    cap = parse_filename("Captain America_Captain America_Hero_1a.tiff")
    assert vision.face_suffix == cap.face_suffix == "a"
    assert vision.position == 2 and cap.position == 1
    for parsed in (vision, cap):
        assert not hasattr(parsed, "double_sided")
        assert not hasattr(parsed, "card_code")


def test_a_third_face_suffix_is_accepted():
    # Ant-Man's `_1c` — a second `hero` record at the same position (research R8, R12).
    assert parse_filename("Ant-Man_Ant-Man_Hero_Giant_1c.tiff").face_suffix == "c"


# ------------------------------------------------------ copy-counting, per folder


def test_a_folder_numbering_by_copy_is_detected():
    folder = [
        "2_Active Altruism_Event.tif",
        "3_Active Altruism_Event.tif",
        "4_Active Altruism_Event.tif",
        "1_Phoenix_Hero.tif",
    ]
    assert detect_copy_counting(folder) is True


def test_a_folder_numbering_by_position_is_not_mistaken_for_one():
    folder = [
        "Captain America_Captain America_Hero_1a.tiff",
        "Captain America_Agent 13_Ally_2.tiff",
        "Leadership_Make the Call_Event_16.tiff",
        "Leadership_The Power of Leadership_Upgrade_18.tiff",
    ]
    assert detect_copy_counting(folder) is False


def test_the_signature_is_one_card_appearing_under_several_numbers():
    """Three files for one card, numbered 2, 3, 4. Positions are never like that."""
    assert detect_copy_counting(["2_Energy_Resource.tif", "3_Energy_Resource.tif"]) is True


def test_a_mixed_folder_is_treated_as_copy_counting():
    """Phoenix and Wonder Man mix: copy-numbered hero cards, unnumbered aspect cards.

    Erring toward copy-counting is the safe direction — the cost is falling back to name
    matching, and the cost of the other mistake is a card paired with the wrong file.
    """
    folder = [
        "2_Active Altruism_Event.tif",
        "3_Active Altruism_Event.tif",
        "Basic_Invulnerability_Event.tiff",
    ]
    assert detect_copy_counting(folder) is True


def test_an_empty_or_unnumbered_folder_is_not_copy_counting():
    assert detect_copy_counting([]) is False
    assert detect_copy_counting(["Basic_Invulnerability_Event.tiff"]) is False


# -------------------------------------------------------------------- normalisation


@pytest.mark.parametrize(
    "typo,canonical",
    [
        ("Stength in Numbers", "Strength in Numbers"),
        ("Steve_s Apartament", "Steve's Apartment"),
        ("Upgarde", "Upgrade"),
    ],
)
def test_the_three_observed_typos_normalise_close_to_their_canonical_names(typo, canonical):
    """Stripping punctuation alone reaches none of them: "Stength" is a dropped letter.

    That is the whole argument for an edit-distance bound rather than exact matching after
    cleanup, and these three are why the bound is 2 and not 0.
    """
    from marchamp.library.filenames import edit_distance

    assert edit_distance(normalise(typo), normalise(canonical)) <= 2


def test_normalisation_removes_what_the_library_varies_and_keeps_what_identifies():
    assert normalise("Steve's Apartment") == normalise("Steve_s  Apartment")
    assert normalise("MAKE THE CALL") == normalise("Make the Call")
    assert normalise("Ant-Man") == normalise("Ant Man")
    # And does not collapse two genuinely different cards into one key.
    assert normalise("Energy") != normalise("Enraged")


def test_a_name_key_is_produced_for_a_name_split_by_an_underscore():
    """`Steve_s Apartament` is one card name that the library wrote with an underscore.

    Indexing only underscore-separated segments would key it as "steve" and "sapartament",
    neither of which is within edit distance of the canonical name.
    """
    from marchamp.library.filenames import edit_distance

    parsed = parse_filename("Captain America_Steve_s Apartament_Support_9.tiff")
    target = normalise("Steve's Apartment")
    assert any(edit_distance(key, target) <= 2 for key in parsed.name_keys)


def test_name_keys_do_not_include_bare_numbers():
    parsed = parse_filename("Leadership_Make the Call_Event_16.tiff")
    assert "16" not in parsed.name_keys
    assert normalise("Make the Call") in parsed.name_keys


def test_the_extension_never_reaches_a_name_key():
    a = parse_filename("Leadership_The Power of Leadership_Upgrade_18.tif")
    b = parse_filename("Leadership_The Power of Leadership_Upgrade_18.tiff")
    assert a.name_keys == b.name_keys
    # FR-034: a .tif/.tiff pair is one card in two renditions, not two cards.
    assert a.position == b.position == 18


# ------------------------------------------------------------------- edit distance


def test_edit_distance_is_bounded_and_symmetric():
    from marchamp.library.filenames import edit_distance

    assert edit_distance("", "") == 0
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("abc", "abd") == 1
    assert edit_distance("abc", "acb") == 1  # one transposed pair is one slip, not two
    assert edit_distance("kitten", "sitting") == edit_distance("sitting", "kitten") == 3


def test_a_transposed_pair_stays_inside_the_bound_a_short_name_gets():
    """Phase 5 (T076). `Pheonix` is the typo the Phoenix folder actually contains.

    Scored as plain Levenshtein it is two edits from `Phoenix`, and `distance_limit` allows a
    seven-character name only one — so the hero's own identity scan fell outside the bound
    and the pack reported a gap for a card sitting in the folder the user named. The
    tightening exists because *two independent* edits on a short name can reach a different
    card; one transposed pair reaches nothing, so it is scored as the single slip it is.
    """
    from marchamp.library.filenames import matches_name

    assert matches_name("pheonix", "Phoenix")
    # And the bound is still a bound: two independent edits on a short name do not pass.
    assert not matches_name("phoemux", "Phoenix")


def test_edit_distance_gives_up_early_rather_than_computing_a_large_answer():
    """It runs against every name key in a 4,447-file index; the exact value is not needed."""
    from marchamp.library.filenames import edit_distance

    assert edit_distance("a" * 200, "b" * 200, ceiling=2) > 2
