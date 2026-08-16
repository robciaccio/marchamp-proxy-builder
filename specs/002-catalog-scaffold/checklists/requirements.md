# Specification Quality Checklist: Starter Deck Assembly from a Scan Library

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
**Last revised**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

This spec replaces an earlier draft of the same feature. The earlier one proposed generating
a catalog from filenames and having the user type in every quantity by hand, on the stated
premise that quantities were unrecoverable. That premise was wrong, and the revision follows
from disproving it rather than from a change of mind about scope.

### Evidence behind the rewrite

Every claim the spec rests on was measured against the live MarvelCDB API and the user's
library on 2026-08-16, not reasoned about:

- The trailing number in a filename is MarvelCDB's `position` — 18/18 for pack `cap`, and
  pack identification then succeeded for all eight hero folders tested.
- Deck composition is *not* derivable from pack contents: hero set + main aspect + basic
  totals 43, 43, 43, 43, 40, 43, 43, 43, 43, 43, 42, 37 across twelve packs.
- Official starter decklists exist on MarvelCDB for the five Core Set heroes only.
- Copy counts differ between printings of the same card (Energy is ×1 in `cap`, ×4 in
  `core`), which is why FR-011 exists.
- The library holds 4,447 images and every card probed exists somewhere in it.

### Deliberately left to the plan

**The pack-identification confidence threshold (FR-006).** The spec requires that weak
agreement be refused but does not say what counts as weak, because the number depends on the
matching approach chosen. If the threshold ever becomes visible to the user — a prompt, a
flag — it belongs back in the spec.

**Name-matching tolerance (FR-017).** The spec bounds *when* a name match is permitted, which
is the safety-critical part. How much misspelling to tolerate is a plan decision, and a
consequential one: the library contains "Stength in Numbers" and "Steve_s Apartament", so
exact matching is too strict, while loose matching can pair a card with the wrong file. The
plan must state the rule and test it against both.

**Whether nemesis and encounter cards get their own output (FR-010).** Stated as MAY. They
are excluded from the 40 either way, which is the part that affects correctness.

### Open risk worth naming

**SC-003 is asserted, not yet demonstrated.** Thor, Black Widow, Ant-Man, and Ms. Marvel
currently reconstruct to 37, 39, 36, and 37 with a positional resolver limited to the hero
folder. Every card responsible was located elsewhere in the library, so 40 is believed
reachable through FR-015 and FR-017 — but no resolver has yet been built that reaches it.
If planning shows one of these four cannot be resolved without guessing, the honest response
is to narrow SC-003 and report the gap, not to loosen FR-013.

No [NEEDS CLARIFICATION] markers were needed. Questions that came up during drafting were
settled against measurement, and are recorded in the spec's Clarifications section.
