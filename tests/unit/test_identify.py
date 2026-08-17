"""T040 — pack identification from a hero folder (FR-010, FR-011, FR-012).

Three things are under test and they fail differently, so they are tested separately:

**Ranking** picks which pack to ask MarvelCDB about. It sees folder names and the 61-entry
pack index, and nothing else — no card data, no network. Getting it wrong costs one wasted
request and a low confidence figure.

**Verification** measures how much of the folder the candidate pack actually explains. It is
the number the user is shown, and the only defence against a folder whose *name* matches a
pack it is not.

**The threshold** decides whether to propose or to ask. The case it exists for is not the
folder that matches nothing — that one is obvious — but the folder that matches something
weakly, where proposing confidently would produce a plausible and entirely wrong deck
(SC-009). Below the threshold the run must offer candidates and stay alive: FR-012b makes a
refusal a prompt, and a run that ended here would be a dead end the user cannot get out of.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marchamp.library.identify import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_MATCHED_CARDS,
    Identification,
    IdentificationSource,
    identify,
    rank_packs,
    verify,
)
from marchamp.library.index import build_index
from marchamp.upstream.models import PackCard, PackIndexEntry, parse_snapshot_cards
from tests.conftest import ACCEPTANCE_HEROES, SNAPSHOT_FIXTURES


@pytest.fixture(scope="module")
def pack_index() -> list[PackIndexEntry]:
    raw = json.loads((SNAPSHOT_FIXTURES / "packs.json").read_text())
    return [PackIndexEntry(code=e["code"], name=e["name"]) for e in raw]


def load_cards(pack_code: str) -> list[PackCard]:
    """The committed reduced listing for one pack, as the snapshot store would supply it."""
    payload = json.loads((SNAPSHOT_FIXTURES / f"{pack_code}.json").read_text())
    cards, _warnings = parse_snapshot_cards(payload, pack_code)
    return cards


# ------------------------------------------------------------------------------ ranking


@pytest.mark.parametrize(("pack_code", "folder"), sorted(ACCEPTANCE_HEROES.items()))
def test_every_acceptance_hero_ranks_its_own_pack_first(pack_code, folder, pack_index):
    """The ten folders this feature is accepted against must each rank their pack top.

    Four of them are the reason ranking is not a dictionary lookup: the library writes
    `Ms.Marvel` for the pack named "Ms. Marvel" and `Wonderman` for "Wonder Man", puts the
    hero after an alter ego in `Odinson_Thor`, and marks Phoenix's folder `(u)`.
    """
    ranked = rank_packs(folder, pack_index)
    assert ranked, f"{folder} ranked nothing at all"
    assert ranked[0].pack_code == pack_code, (
        f"{folder} ranked {ranked[0].pack_code} ({ranked[0].pack_name}) above {pack_code}"
    )


def test_ranking_reads_the_hero_not_the_alter_ego(pack_index):
    # `Odinson` is not a pack and must not drag the score toward one; `Thor` is.
    ranked = rank_packs("Heros/Odinson_Thor", pack_index)
    assert ranked[0].pack_code == "thor"


def test_ranking_ignores_a_scan_state_marker(pack_index):
    # `(u)` marks the scan, not the hero. Phoenix's folder carries it and Hulk's does not.
    assert rank_packs("Heros/Jean Grey_Phoenix (u)", pack_index)[0].pack_code == "phoenix"


def test_ranking_is_ordered_best_first(pack_index):
    ranked = rank_packs("Heros/Steve Rogers_Captain America", pack_index)
    scores = [c.score for c in ranked]
    assert scores == sorted(scores, reverse=True)


def test_ranking_offers_alternatives_not_only_a_winner(pack_index):
    """FR-012b's candidate list has to come from somewhere, including when ranking is wrong."""
    ranked = rank_packs("Heros/Some Person_Not A Hero", pack_index)
    assert len(ranked) > 1


def test_ranking_makes_no_request(pack_index, no_network):
    # Two requests identify and verify a pack (research R3); ranking is neither of them.
    rank_packs("Heros/Steve Rogers_Captain America", pack_index)


# ------------------------------------------------------------------------- verification


def test_confidence_is_the_share_of_interpretable_files_explained(scan_library):
    index = build_index(scan_library)
    folder = ACCEPTANCE_HEROES["cap"]
    result = verify("cap", "Captain America", load_cards("cap"), index, folder)

    assert 0.0 <= result.confidence <= 1.0
    assert result.matched_cards > 0
    assert result.interpretable_files > 0
    assert result.confidence == pytest.approx(result.matched_cards / result.interpretable_files)


def test_the_wrong_pack_scores_far_below_the_right_one(scan_library):
    """The check that ranking alone cannot make: a folder is verified against card data.

    Star-Lord's folder against the Thor pack is the shape of the failure this catches — a
    confident identification of the wrong pack yields a deck that is entirely plausible.
    """
    index = build_index(scan_library)
    folder = ACCEPTANCE_HEROES["stld"]
    right = verify("stld", "Star-Lord", load_cards("stld"), index, folder)
    wrong = verify("thor", "Thor", load_cards("thor"), index, folder)
    assert wrong.confidence < right.confidence


def test_evidence_names_what_the_figure_rests_on(scan_library):
    """FR-012: the user confirms an identification, so they are shown its basis.

    A bare percentage is not something a user can check. Naming matched cards is.
    """
    index = build_index(scan_library)
    result = verify("cap", "Captain America", load_cards("cap"), index, ACCEPTANCE_HEROES["cap"])
    assert result.evidence
    assert all(isinstance(line, str) and line for line in result.evidence)
    joined = " ".join(result.evidence).lower()
    assert "captain america" in joined


def test_the_decklist_scan_is_not_counted_against_the_pack(scan_library):
    """FR-013b: the decklist card is not one of the pack's cards, either way.

    Counted in the denominator it would depress every folder that holds one — eight of the
    ten — for having a file that can never match a pack card by construction.
    """
    index = build_index(scan_library)
    folder = ACCEPTANCE_HEROES["cap"]
    assert index.decklist_candidates(folder), "fixture regression: cap has a decklist scan"
    result = verify("cap", "Captain America", load_cards("cap"), index, folder)
    interpretable_refs = {e.ref for e in index.files_in(folder)}
    decklist_refs = {e.ref for e in index.decklist_candidates(folder)}
    assert result.interpretable_files <= len(interpretable_refs - decklist_refs)


# ----------------------------------------------------------------------------- the whole


def test_identification_below_threshold_offers_candidates_and_does_not_end_the_run(
    scan_library, pack_index
):
    """FR-011 refuses, FR-012b turns the refusal into a prompt.

    The distinction this asserts is the whole of FR-012b: `pack_code is None` means "I will
    not claim this", and a populated `candidates` list is what stops that from being a dead
    end. A refusal that also emptied the candidates would leave the user with a run they can
    neither confirm nor correct.
    """
    index = build_index(scan_library)
    result = identify(
        ACCEPTANCE_HEROES["cap"],
        index,
        pack_index,
        load_cards,
        min_confidence=1.01,  # unreachable, so refusal is forced rather than contrived
    )
    assert result.pack_code is None
    assert not result.confident
    assert result.candidates, "a refusal with no candidates is a dead end (FR-012b)"


def test_a_confident_identification_names_the_pack_and_its_evidence(scan_library, pack_index):
    index = build_index(scan_library)
    result = identify(ACCEPTANCE_HEROES["cap"], index, pack_index, load_cards)
    assert result.pack_code == "cap"
    assert result.confident
    assert result.source is IdentificationSource.IDENTIFIED
    assert result.evidence


def test_identification_asks_about_exactly_one_pack(scan_library, pack_index):
    """Research R3/R4: two requests identify and verify — the index, then one pack.

    Verifying the top three candidates would triple the request count for a figure the user
    confirms anyway, and FR-040/SC-006d hold the whole run to a request budget.
    """
    index = build_index(scan_library)
    asked: list[str] = []

    def counting_load(pack_code: str) -> list[PackCard]:
        asked.append(pack_code)
        return load_cards(pack_code)

    identify(ACCEPTANCE_HEROES["cap"], index, pack_index, counting_load)
    assert asked == ["cap"]


def test_identification_is_serialisable_onto_the_run(scan_library, pack_index):
    """The run record is JSON on disk (ADR 0001), so this has to survive a round trip."""
    index = build_index(scan_library)
    result = identify(ACCEPTANCE_HEROES["cap"], index, pack_index, load_cards)
    restored = Identification.from_json(json.loads(json.dumps(result.to_json())))
    assert restored == result


def test_a_user_selected_pack_is_recorded_as_such(scan_library, pack_index):
    """FR-012b, SC-009a — indistinguishable from an automatic identification would hide it."""
    index = build_index(scan_library)
    result = identify(ACCEPTANCE_HEROES["cap"], index, pack_index, load_cards)
    chosen = result.select("thor", "Thor")
    assert chosen.pack_code == "thor"
    assert chosen.source is IdentificationSource.USER_SELECTED
    assert chosen.confident, "a pack the user chose needs no confidence figure to be usable"


def test_a_folder_that_is_not_a_hero_folder_refuses(scan_library, pack_index):
    """`Aspects/` holds cards from every pack and is nobody's hero folder."""
    index = build_index(scan_library)
    result = identify("Aspects/Basic", index, pack_index, load_cards)
    assert not result.confident


def test_identification_never_returns_a_path_from_outside_the_library(scan_library, pack_index):
    """FR-009 — evidence is shown to the user and written to the run's log."""
    index = build_index(scan_library)
    result = identify(ACCEPTANCE_HEROES["cap"], index, pack_index, load_cards)
    for line in result.evidence:
        assert str(Path(scan_library)) not in line


# ------------------------------------------------------------------------- T042 threshold

#: Every pack with a committed snapshot (T006). `core` is excluded from the false-positive
#: sweep below: it is not a hero pack, it is where the *other printing* of a shared card
#: lives, so a hero folder scoring against it is the reprint relationship working rather
#: than a misidentification.
CALIBRATION_PACKS = sorted(
    p.stem for p in SNAPSHOT_FIXTURES.glob("*.json") if p.stem not in {"packs", "core"}
)


@pytest.mark.parametrize(("pack_code", "folder"), sorted(ACCEPTANCE_HEROES.items()))
def test_every_acceptance_hero_clears_the_threshold(pack_code, folder, scan_library, pack_index):
    """T042 — the threshold must be one all ten clear, not one only the easy folders clear.

    Phoenix and Wonder Man are the reason this is parametrised rather than spot-checked:
    both number their files by physical copy, so they contribute no usable positions and
    must clear on name matches alone (research R5, SC-003c).
    """
    index = build_index(scan_library)
    result = identify(folder, index, pack_index, load_cards)
    assert result.pack_code == pack_code
    assert result.confident
    assert result.confidence >= DEFAULT_MIN_CONFIDENCE
    assert result.matched_cards >= DEFAULT_MIN_MATCHED_CARDS


def test_the_threshold_sits_in_the_measured_gap(scan_library, pack_index):
    """T042's calibration, asserted rather than recorded in a comment.

    The measurement that set `DEFAULT_MIN_CONFIDENCE`: score every acceptance hero's folder
    against every pack we hold a snapshot for, and require the threshold to fall strictly
    between the worst true score and the best false one. That gap is not comfortable by
    default — Ant-Man's folder scores 0.65 against the *Wasp* pack, because each of those
    two packs contains the other hero as an ally — and the originally specified 0.60 sat
    below it. If a future snapshot narrows the gap, this fails and the threshold gets
    re-derived instead of quietly admitting a wrong pack.
    """
    index = build_index(scan_library)
    true_scores: dict[str, float] = {}
    false_scores: dict[tuple[str, str], float] = {}

    for pack_code, folder in ACCEPTANCE_HEROES.items():
        for candidate in CALIBRATION_PACKS:
            cards = load_cards(candidate)
            name = next(e.name for e in pack_index if e.code == candidate)
            score = verify(candidate, name, cards, index, folder).confidence
            if candidate == pack_code:
                true_scores[pack_code] = score
            else:
                false_scores[(pack_code, candidate)] = score

    worst_true = min(true_scores.values())
    best_false = max(false_scores.values())
    assert best_false < DEFAULT_MIN_CONFIDENCE <= worst_true, (
        f"threshold {DEFAULT_MIN_CONFIDENCE} is not inside the measured gap: the weakest "
        f"true identification scores {worst_true:.2f} and the strongest false one "
        f"{best_false:.2f}"
    )
