"""T055 — the FR-026h reuse key (SC-006h, SC-006i, SC-006k).

A pack's PDF is ~202 MB and takes ~49 s to build, so serving a stored one matters. The key
has exactly three parts, and each is chosen against a specific way of being wrong:

    pack code + snapshot revision + the identity of the images this run resolved

**The revision**, so refreshing card data rebuilds rather than serving a PDF built from
superseded quantities. **The image identity**, so a second library that resolves even one
card to different bytes rebuilds (SC-006k) — a key of pack-and-revision alone would hand one
user another user's artwork. And **not the library root**, so a run whose folder was renamed
or remounted still gets its PDF when every image is byte-identical (SC-006h).

Because the third part is *content*, a run must resolve before reuse can be decided. What
reuse skips is the render, not the resolve (SC-006i) — which is the opposite of the intuitive
optimisation and the reason it is asserted here rather than assumed.

**Scope note.** These drive `image_identity` and the PDF store directly rather than through
`confirm()`. Reaching `ready` needs every card resolved, and cascade steps 2 and 4 are US3's
(Phase 5). The reuse *decision* in `service.confirm` is exercised end to end by T115 once
that lands.
"""

from __future__ import annotations

import json

import pytest

from marchamp.assembly.faces import Side, expand_pack
from marchamp.assembly.resolve import Provenance, Resolution, Source, resolve_pack
from marchamp.assembly.service import image_identity
from marchamp.library.index import build_index
from marchamp.store.layout import StateLayout
from marchamp.store.pdfs import PdfKind, PdfStore
from marchamp.upstream.models import PackCard, parse_snapshot_cards
from tests.conftest import ACCEPTANCE_HEROES, SNAPSHOT_FIXTURES

PDF_BYTES = b"%PDF-1.7\nnot a real document, but bytes are bytes\n%%EOF\n"

#: The store validates a revision as 16 hex characters, because it becomes a path segment
#: (`pdfs/standard/<pack>@<revision>@<identity>.pdf`). `compute_revision` produces exactly
#: that, so these stand in for two real ones rather than being decorative placeholders.
REVISION = "0123456789abcdef"
OTHER_REVISION = "fedcba9876543210"


def load_cards(pack_code: str) -> list[PackCard]:
    payload = json.loads((SNAPSHOT_FIXTURES / f"{pack_code}.json").read_text())
    cards, _ = parse_snapshot_cards(payload, pack_code)
    return cards


def printing_lookup(code: str) -> PackCard | None:
    for path in sorted(SNAPSHOT_FIXTURES.glob("*.json")):
        if path.stem == "packs":
            continue
        for card in load_cards(path.stem):
            if card.code == code:
                return card
    return None


@pytest.fixture
def store(tmp_path) -> PdfStore:
    layout = StateLayout(tmp_path / "state")
    layout.ensure()
    return PdfStore(layout)


@pytest.fixture(scope="module")
def cap_resolutions(scan_library):
    index = build_index(scan_library)
    cards = load_cards("cap")
    return resolve_pack(
        expand_pack(cards),
        cards,
        index,
        ACCEPTANCE_HEROES["cap"],
        scan_library,
        printing_lookup,
    ).resolutions


def _swap_one_image(resolutions, digest: str = "f" * 64):
    """The same run with exactly one card resolving to different bytes."""
    first, *rest = sorted(resolutions, key=lambda r: r.card_code)
    changed = Resolution(
        card_code=first.card_code,
        card_name=first.card_name,
        side=first.side,
        provenance=first.provenance,
        source=first.source,
        ref=first.ref,
        content_digest=digest,
        quantity=first.quantity,
    )
    return [changed, *rest]


# --------------------------------------------------------------------- image identity


def test_the_identity_is_stable_across_two_identical_resolutions(cap_resolutions):
    assert image_identity(cap_resolutions) == image_identity(list(cap_resolutions))


def test_the_identity_does_not_depend_on_the_order_cards_resolved_in(cap_resolutions):
    """The cascade answers in whatever order it happens to; the key must not follow that."""
    shuffled = list(reversed(cap_resolutions))
    assert image_identity(shuffled) == image_identity(cap_resolutions)


def test_the_identity_does_not_depend_on_the_library_root(cap_resolutions):
    """SC-006h — the folder moved, every image is the same, the PDF is still this run's.

    Refs are library-relative by construction (FR-009), so this asserts the property that
    makes that pay off: nothing absolute reaches the key.
    """
    identity = image_identity(cap_resolutions)
    assert all(not r.ref.startswith("/") for r in cap_resolutions)
    assert identity == image_identity(cap_resolutions)


def test_one_card_resolving_to_different_bytes_changes_the_identity(cap_resolutions):
    """SC-006k — the assertion that makes the third key component worth having."""
    assert image_identity(_swap_one_image(cap_resolutions)) != image_identity(cap_resolutions)


def test_swapping_two_cards_images_changes_the_identity(cap_resolutions):
    """Hashing the digests alone would call this the same multiset and reuse a wrong PDF."""
    ordered = sorted(cap_resolutions, key=lambda r: r.card_code)
    a, b, *rest = ordered
    swapped = [
        Resolution(
            card_code=a.card_code,
            card_name=a.card_name,
            side=a.side,
            provenance=a.provenance,
            source=a.source,
            ref=b.ref,
            content_digest=b.content_digest,
            quantity=a.quantity,
        ),
        Resolution(
            card_code=b.card_code,
            card_name=b.card_name,
            side=b.side,
            provenance=b.provenance,
            source=b.source,
            ref=a.ref,
            content_digest=a.content_digest,
            quantity=b.quantity,
        ),
        *rest,
    ]
    assert image_identity(swapped) != image_identity(ordered)


def test_a_front_and_a_back_are_not_interchangeable(scan_library):
    """One code, two faces — printing them the wrong way round is a wrong card."""
    common = {
        "card_code": "26002",
        "card_name": "Intangible",
        "provenance": Provenance.FOLDER_POSITION,
        "source": Source.LIBRARY,
        "quantity": 1,
    }
    forwards = [
        Resolution(side=Side.FRONT, ref="a.tiff", content_digest="1" * 64, **common),
        Resolution(side=Side.BACK, ref="b.tiff", content_digest="2" * 64, **common),
    ]
    backwards = [
        Resolution(side=Side.FRONT, ref="b.tiff", content_digest="2" * 64, **common),
        Resolution(side=Side.BACK, ref="a.tiff", content_digest="1" * 64, **common),
    ]
    assert image_identity(forwards) != image_identity(backwards)


# ------------------------------------------------------------------ the stored PDF key


def test_a_stored_pdf_is_served_when_all_three_components_match(store, cap_resolutions):
    identity = image_identity(cap_resolutions)
    store.put_standard("cap", REVISION, identity, PDF_BYTES)
    found = store.find_standard("cap", REVISION, identity)
    assert found is not None
    assert found.kind is PdfKind.STANDARD
    assert found.path.read_bytes() == PDF_BYTES


def test_a_refreshed_snapshot_rebuilds(store, cap_resolutions):
    """SC-006i's other half — old card data must not print under a new revision."""
    identity = image_identity(cap_resolutions)
    store.put_standard("cap", REVISION, identity, PDF_BYTES)
    assert store.find_standard("cap", OTHER_REVISION, identity) is None


def test_a_different_pack_never_shares_a_pdf(store, cap_resolutions):
    identity = image_identity(cap_resolutions)
    store.put_standard("cap", REVISION, identity, PDF_BYTES)
    assert store.find_standard("thor", REVISION, identity) is None


def test_one_changed_image_rebuilds(store, cap_resolutions):
    """SC-006k end to end against the store, not only against the hash."""
    store.put_standard("cap", REVISION, image_identity(cap_resolutions), PDF_BYTES)
    assert (
        store.find_standard("cap", REVISION, image_identity(_swap_one_image(cap_resolutions)))
        is None
    )


def test_a_moved_library_still_serves_the_same_pdf(store, cap_resolutions):
    """SC-006h. Nothing about where the files were read from is in the key.

    Modelled by keying with the identity computed from resolutions whose refs are unchanged
    — which is exactly the situation after a rename, because refs are library-relative.
    """
    identity = image_identity(cap_resolutions)
    store.put_standard("cap", REVISION, identity, PDF_BYTES)
    recomputed = image_identity(list(cap_resolutions))
    assert store.find_standard("cap", REVISION, recomputed) is not None


def test_a_saved_pdf_is_separate_from_the_packs_standard_one(store, cap_resolutions):
    """FR-026i — a customized run's document is the user's, not the pack's."""
    identity = image_identity(cap_resolutions)
    standard = store.put_standard("cap", REVISION, identity, PDF_BYTES)
    saved = store.put_saved(b"%PDF-1.7\ndifferent\n%%EOF\n", "my captain america")
    assert saved.kind is PdfKind.SAVED
    assert saved.path != standard.path
    assert store.find_standard("cap", REVISION, identity) is not None
