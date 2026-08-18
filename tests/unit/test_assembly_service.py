"""T049 — the run lifecycle (FR-012a, FR-026a, FR-026b, SC-009).

The three rules under test are each a specific way of being wrong, not a state diagram for
its own sake:

- **Nothing resolves before the pack is confirmed.** The case the confidence threshold
  structurally cannot catch is an identification that is confident *and* wrong, whose output
  is a deck that is entirely plausible (SC-009). Confirmation is unconditional.
- **`ready` does not print.** A ~49 s render and a ~202 MB file happen on an explicit
  confirmation and nowhere else (FR-026a).
- **Waiting is not failing.** `outcome` is null until the run is terminal, so a run awaiting
  a pack or a card is distinguishable from one that finished badly (FR-036).
"""

from __future__ import annotations

import pytest

from marchamp.assembly.service import AssemblyError, AssemblyService, FolderRefused
from marchamp.config import Settings
from marchamp.store.layout import StateLayout
from marchamp.store.runs import Outcome, RunState
from marchamp.upstream.client import MarvelCdbClient
from marchamp.upstream.snapshots import SnapshotStore
from tests.conftest import ACCEPTANCE_HEROES


@pytest.fixture
def service(tmp_path, upstream_transport) -> AssemblyService:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    layout = StateLayout(settings.state_dir)
    layout.ensure()
    client = MarvelCdbClient(settings.upstream, transport=upstream_transport)
    return AssemblyService(settings, SnapshotStore(layout, client), layout)


@pytest.fixture
def started(service, scan_library):
    return service.create(scan_library, ACCEPTANCE_HEROES["cap"])


# ---------------------------------------------------------------------- named paths


def test_a_hero_folder_outside_the_library_is_refused_specifically(service, scan_library):
    """FR-006 — the user is told which path is wrong, not handed a generic 400."""
    with pytest.raises(FolderRefused) as caught:
        service.create(scan_library, "../elsewhere")
    assert "hero_folder" in str(caught.value)


def test_a_library_root_that_does_not_exist_is_refused_specifically(service, tmp_path):
    with pytest.raises(FolderRefused) as caught:
        service.create(tmp_path / "no-such-library", "Heros/Anyone")
    assert "library_root" in str(caught.value)


def test_a_relative_library_root_is_refused(service):
    with pytest.raises(FolderRefused):
        service.create("relative/path", "Heros/Anyone")


# --------------------------------------------------------------- nothing before confirm


def test_a_new_run_identifies_and_then_waits(started):
    """FR-012a, SC-009 — identification is a proposal, never a decision."""
    assert started.state is RunState.AWAITING_PACK
    assert started.identification["pack_code"] == "cap"


def test_nothing_is_resolved_before_the_pack_is_confirmed(started):
    """The single most important assertion in this file.

    A run that resolved on identification would commit ~34 cards' worth of work — and, worse,
    a plausible deck — to a guess the user never saw.
    """
    assert started.resolutions == []
    assert started.snapshot_revision is None


def test_the_outcome_is_null_until_the_run_is_terminal(started):
    """FR-036 — waiting is not failing, and must not look like it."""
    assert started.outcome is None


def test_confirming_pins_the_snapshot_revision_and_resolves(service, started):
    """FR-044b, FR-045 — pinned here, so a later refresh cannot move composition."""
    record = service.set_pack(started.id, "confirm", version=started.version)
    assert record.snapshot_revision
    assert record.resolutions
    assert record.state in (RunState.AWAITING_CARDS, RunState.READY)


def test_a_pack_cannot_be_set_twice(service, started):
    service.set_pack(started.id, "confirm", version=started.version)
    with pytest.raises(AssemblyError) as caught:
        service.set_pack(started.id, "confirm")
    assert caught.value.status == 409


def test_a_stale_version_is_refused_rather_than_silently_applied(service, started):
    """ADR 0001's optimistic concurrency, reaching the service.

    Two browser tabs answering two different questions is the lost update the ADR's
    dissenting reviewers named.
    """
    with pytest.raises(AssemblyError) as caught:
        service.set_pack(started.id, "confirm", version=started.version + 5)
    assert caught.value.status == 409


# ------------------------------------------------------------------- selecting a pack


def test_a_user_selected_pack_is_recorded_and_is_not_customization(service, started):
    """FR-012b, FR-026i, SC-009a — correcting the tool still yields the standard PDF.

    What gets printed follows from the pack and its snapshot, so a run that selected its
    pack and then resolved everything automatically is not a *different* document.
    """
    record = service.set_pack(started.id, "select", pack_code="thor", version=started.version)
    assert record.identification["pack_code"] == "thor"
    assert record.identification["source"] == "user_selected"
    assert record.customized is False


def test_selecting_a_pack_that_does_not_exist_is_refused(service, started):
    with pytest.raises(AssemblyError) as caught:
        service.set_pack(started.id, "select", pack_code="not-a-pack", version=started.version)
    assert caught.value.status == 400


def test_the_rejected_measurement_survives_a_user_selection(service, started):
    """SC-009a — a run records that the tool and the user disagreed."""
    record = service.set_pack(started.id, "select", pack_code="thor", version=started.version)
    assert record.identification["confidence"] > 0
    assert any("chosen by the user" in line.lower() for line in record.identification["evidence"])


# ----------------------------------------------------------------- ready is not complete


def test_reaching_ready_does_not_produce_a_pdf(service, started):
    """FR-026a. `cap` holds in `awaiting_cards` on this library, which is the same point:

    no state the run reaches on its own produces a document.
    """
    record = service.set_pack(started.id, "confirm", version=started.version)
    assert record.pdf is None
    assert record.state is not RunState.COMPLETE


def test_a_run_that_is_not_ready_cannot_be_confirmed(service, started):
    record = service.set_pack(started.id, "confirm", version=started.version)
    assert record.state is RunState.AWAITING_CARDS
    with pytest.raises(AssemblyError) as caught:
        service.confirm(record.id, version=record.version)
    assert caught.value.status == 409


def test_a_run_with_no_document_refuses_to_serve_one(service, started):
    """No partial output, ever — inherited from 001's FR-020b."""
    with pytest.raises(AssemblyError) as caught:
        service.document(started.id)
    assert caught.value.status == 409


# --------------------------------------------------------------------------- durability


def test_a_run_survives_being_re_read(service, started):
    """ADR 0001 — the record on disk is the run, not an in-memory object."""
    again = service.get(started.id)
    assert again.id == started.id
    assert again.hero_folder == started.hero_folder
    assert again.identification == started.identification


def test_the_library_root_is_retained_so_a_resumed_run_can_name_it(started, scan_library):
    """FR-026b. Retained deliberately: FR-009 forbids paths from *outside* the named
    library, and the root itself is not outside it."""
    assert started.library_root == scan_library.resolve()


# ------------------------------------------------------------------------- the outcome

#: A pack whose every card is generated at its own position, so the run reaches `complete`
#: without any of Phase 5's or Phase 6's machinery. `vision` rather than an acceptance hero
#: because it is not in the derived fixture library and so cannot be confused with it.
FULL_PACK = "vision"
FULL_FOLDER = "Heros/Vision_Vision"


@pytest.fixture
def complete_library(tmp_path):
    """A folder holding exactly one scan for every face `vision` prints.

    Generated from the pack listing rather than hand-written: what is being tested is the
    outcome of a run that wants for nothing, and a folder assembled by hand would sooner or
    later be missing a card and turn this into a test of something else.
    """
    from marchamp.assembly.faces import faces_for
    from marchamp.assembly.resolve import face_suffixes
    from tests.conftest import LIBRARY_IMAGE_H, LIBRARY_IMAGE_W, make_card_image, pack_cards

    root = tmp_path / "complete-library"
    cards = pack_cards(FULL_PACK)
    for card in cards:
        for face in faces_for(card, cards):
            suffix = face_suffixes(face)[0] or ""
            name = card.name.replace("/", "-")
            rel = f"{FULL_FOLDER}/Test_{name}_Card_{card.position}{suffix}.tiff"
            make_card_image(root / rel, name, width=LIBRARY_IMAGE_W, height=LIBRARY_IMAGE_H)
    return root


@pytest.fixture
def ready_run(service, complete_library):
    started = service.create(complete_library, FULL_FOLDER)
    return service.set_pack(started.id, "select", pack_code=FULL_PACK, version=started.version)


def test_a_run_waiting_on_a_card_has_no_outcome(service, started):
    """FR-036 — `awaiting_cards` is the tool doing its job, not the tool failing.

    A consumer that read a missing outcome as a failure would tell the user their pack was
    refused when it is waiting for them.
    """
    record = service.set_pack(started.id, "confirm", version=started.version)
    assert record.state is RunState.AWAITING_CARDS
    assert record.outcome is None


def test_a_ready_run_has_no_outcome_either(ready_run):
    """`ready` is not `complete` (FR-026a), so it is not an outcome."""
    assert ready_run.state is RunState.READY
    assert ready_run.outcome is None


def test_a_run_that_resolved_everything_completes_cleanly(service, ready_run):
    """FR-036 — `clean` means exactly that: nothing the user needs to know about."""
    record = service.confirm(ready_run.id, version=ready_run.version)
    assert record.state is RunState.COMPLETE
    assert record.outcome is Outcome.CLEAN


def test_the_outcome_survives_being_read_back(service, ready_run):
    """FR-026b — it is on the record, not only in the response that produced it."""
    service.confirm(ready_run.id, version=ready_run.version)
    assert service.get(ready_run.id).outcome is Outcome.CLEAN


def test_a_completed_run_with_something_to_report_says_warnings(service, ready_run):
    """FR-036 — "assembled with warnings" is a third answer, not a shade of `clean`.

    Driven by putting a genuinely under-resolution scan in the folder, because the
    distinction has to be visible to a consumer that never reads the prose.
    """
    from tests.conftest import make_card_image

    scan = next(p for p in (ready_run.library_root / FULL_FOLDER).iterdir() if p.suffix == ".tiff")
    make_card_image(scan, "SMALL", width=240, height=336)

    reresolved = service._resolve(service.get(ready_run.id))
    record = service.confirm(reresolved.id, version=reresolved.version)
    assert record.state is RunState.COMPLETE
    assert record.report["low_resolution"]
    assert record.outcome is Outcome.WARNINGS


def test_the_three_outcomes_are_the_only_ones(service, ready_run):
    """FR-036 — a machine-readable outcome a consumer can exhaust.

    Asserted against the enum rather than against a run, so adding a fourth value forces
    someone to come back to this file and to the contract that declares it.
    """
    assert {o.value for o in Outcome} == {"clean", "warnings", "refused"}
