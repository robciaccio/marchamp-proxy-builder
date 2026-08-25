# Feature Specification: Measured Card Slot Size

**Feature Branch**: `006-measured-card-slot-size`

**Created**: 2026-08-21

**Status**: Draft

**Input**: User description: "Use the measured, native physical size of the scanned card
images as the PDF layout's card slot size, instead of the current fixed standard-poker-card
constant, backed by a statistical analysis of 111 real card scans (mean 61.31 x 87.96 mm,
CoV under 0.3%) showing the library is effectively one consistent size, smaller and a
different aspect ratio than the 63.5 x 88.9 mm standard-poker constant the layout currently
assumes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print at the library's real size (Priority: P1)

Someone printing a deck from this tool gets a PDF whose card slots match the actual physical
size of the scans in their library, rather than a generic commercial card-stock size those
scans were never measured against.

**Why this priority**: This is the entire point of the feature. Today's slot size
(63.5 × 88.9 mm, "standard poker") is proportionally wider than the real scans, so the
default `crop` fit mode trims a sliver off the top and bottom of every single card in the
library to force it into that shape — permanent, silent loss on every card ever printed.
Sizing the slot to what the scans actually measure removes that loss for the common case.

**Independent Test**: Generate a PDF for any deck and measure the printed slot with a ruler
(or assert it in a render test) — it matches the new target dimensions, and the source
image inside a `crop`-mode slot shows only the trim margin the sample's own variance
predicts, not a fixed ~2.4% sliver top and bottom.

**Acceptance Scenarios**:

1. **Given** a card image at the library's typical native scan size, **When** it is rendered
   in the default `crop` fit mode, **Then** the printed slot measures the new target size and
   the trimmed margin is within the tolerance the measured sample's own spread predicts, not
   the larger margin forced by the old 63.5 × 88.9 mm target.
2. **Given** any of the three fit modes (`crop`, `fit`, `stretch`) defined by
   `001-hero-deck-pdf-wizard`'s FR-009b, **When** a deck is rendered, **Then** each mode's
   geometry is computed against the new target size and continues to behave exactly as FR-009b
   describes, only at the new dimensions.

---

### User Story 2 - The number is evidence, not a guess (Priority: P2)

Whoever next needs to adjust the target card size — because a new scan source arrives, or a
future print run shows the number is slightly off — can see why the number is what it is and
change it in the one place FR-009a already provides, without having to re-derive the
reasoning from scratch.

**Why this priority**: Supports the first story rather than delivering independent value;
still worth its own acceptance path because a target size adopted without a documented basis
tends to drift or get second-guessed later.

**Independent Test**: Read this spec's evidence and confirm the chosen dimensions are
traceable to a measured sample (size, spread, which folders), not to an unstated assumption.

**Acceptance Scenarios**:

1. **Given** this specification, **When** someone asks why the slot is 61.3 × 88.0 mm rather
   than 63.5 × 88.9 mm, **Then** the answer is in this document: a measured sample, its size,
   and its spread — not "it looked right."

---

### User Story 3 - A cut card still fits a normal sleeve (Priority: P3)

Once a deck is printed at the new, slightly smaller size and cut out, it still fits into the
board-game sleeves people already own for this kind of card.

**Why this priority**: Lowest priority because it is a one-time physical confirmation, not a
gate on the digital pipeline — the project already treats this class of check (see
`001-hero-deck-pdf-wizard`'s physical-marked tests) as hand-verified rather than CI-blocking.

**Independent Test**: Print one sheet at the new size, cut a card, and try it in a standard
board-game sleeve by hand.

**Acceptance Scenarios**:

1. **Given** a card printed and cut to the new 61.3 × 88.0 mm size, **When** it is inserted
   into a standard board-game sleeve sized for this game, **Then** it fits without being too
   large to insert or so loose it fails to sit flush in play.

---

### Edge Cases

- A source image whose own proportions deviate further from the new target than the sampled
  library's typical spread (e.g., a card scanned or cropped unusually) — `001`'s FR-009b2
  already fits each card on its own measurements rather than a deck-wide assumption; that
  per-card behavior is unchanged, only the target it fits against is smaller.
- A source folder scanned at a lower native resolution than the library's typical scan (this
  analysis found one, at 300/200 DPI against the library's usual 600 DPI) — FR-010's
  effective-DPI floor is evaluated exactly as before; a smaller target slot makes that floor
  easier, not harder, to clear, since less enlargement is needed to fill it.
- A PDF generated before this change, regenerated after — the two are not byte-identical,
  because the geometry itself changed between them. That is a legitimate revision boundary,
  not a violation of the determinism guarantee (`002-starter-deck-assembly`'s SC-007), which
  is scoped to the same content and asset revision, not the same code revision.
- A user who explicitly selects `fit` or `stretch` instead of the default `crop` — both are
  still defined relative to the target slot size and change only in their absolute
  dimensions, not their behavior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST lay out every card in a slot of **61.3 × 88.0 mm**, measured on
  the printed page, within ±0.5 mm on both axes — replacing the 63.5 × 88.9 mm value
  `001-hero-deck-pdf-wizard`'s FR-009 currently assigns to the same, single configurable
  value FR-009a describes. This specification does not edit FR-009's text; it supersedes the
  number by reference, since `001` is already implemented and shipped.
- **FR-002**: The target dimensions MUST be derived from empirical measurement of a
  representative sample of the card library at native scan resolution — not from a
  commercial card-stock standard — and this document MUST record the sample size and spread
  that back the chosen number.
- **FR-003**: Changing the target size MUST remain the one-place edit FR-009a requires; this
  feature MUST NOT reintroduce a second place the card size is expressed.
- **FR-004**: The system MUST continue to meet FR-010's effective-resolution floor (at least
  300 DPI at final print size, no upscaling) at the new target size, measured over the region
  actually printed exactly as FR-010 already specifies.
- **FR-005**: The three fit modes FR-009b defines (`crop`, `fit`, `stretch`) MUST continue to
  operate, unchanged in behavior and user-facing meaning, against the new target size.
- **FR-006**: Cut guides and grid placement MUST reflect the new target size, so a printed
  and cut card matches the new dimensions rather than the old ones.
- **FR-007**: Generation MUST remain deterministic under `002-starter-deck-assembly`'s SC-007
  — the new size changes what a fresh generation produces, but does not retroactively alter a
  PDF already produced and stored under the old size.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A generated PDF's printed card slot measures 61.3 × 88.0 mm, within ±0.5 mm on
  both axes, verified the same way FR-009's original slot size was verified (page geometry
  asserted against the specification, not judged by eye).
- **SC-002**: Across the sampled library, the default `crop` fit mode discards under 0.5% of
  a card's printed area to the new target, down from roughly 2.4% discarded to the old
  63.5 × 88.9 mm target.
- **SC-003**: For a card scanned at the library's typical 600 DPI, the effective print
  resolution at final size is at or near the scan's native 600 DPI, rather than the ~580 DPI
  effective resolution the old, proportionally larger target produced.
- **SC-004**: A card printed and cut to the new size fits a standard board-game sleeve for
  this game, confirmed once by hand rather than assumed.

## Assumptions

- The target dimensions — 61.3 × 88.0 mm — are the measured mean (61.31 × 87.96 mm) from a
  sample of 111 card images at native 600 DPI, spanning three hero decks (Wolverine, Captain
  America, Thor), one scenario pack (Green Goblin), and one modular set (Arcade) — covering
  heroes, allies, events, upgrades, supports, villains, minions, treacheries, and side
  schemes — rounded to 0.1 mm. The sample's coefficient of variation was under 0.3% on both
  axes, well inside the ±0.5 mm tolerance this spec retains from FR-009.
- This feature replaces the target size outright rather than adding it as a second,
  user-selectable option alongside 63.5 × 88.9 mm. The library has one real size; the layout
  should assume one target size.
- The ±0.5 mm print tolerance is unchanged from `001`'s FR-009, since the measured spread sits
  comfortably inside that existing band and there is no evidence a tighter tolerance is
  achievable in practice.
- One sampled folder (`Ronan The Accuser`) was scanned at 300/200 DPI with a different naming
  convention than the rest of the library — evidently from a different source — but its
  measured size still landed close to the same cluster. This feature treats it as an ordinary
  low-resolution source governed by existing FR-010, not as a special case to exclude or
  renormalize.
- Existing automated tests that assert 63.5 × 88.9 mm geometry, crop-margin math, or
  effective-DPI values will need their fixtures updated to the new target size; this is
  implementation follow-through, not a new requirement.
- Physical sleeve-fit confirmation (User Story 3 / SC-004) is a hand-verified check in the
  same spirit as `001`'s physical-marked tests (`pytest -m physical`) — never a CI gate,
  because it needs a printer, scissors, and a physical sleeve.
