# Specification Quality Checklist: Starter Deck Assembly from a Scan Library

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
**Last revised**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — **fails as worded**, see A
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed — User Scenarios, Requirements, Success Criteria

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — verified, zero occurrences
- [ ] Requirements are testable and unambiguous — **two are not**, see B
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [ ] All functional requirements have clear acceptance criteria — **20 scenarios for 51
      requirements**, see C
- [x] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria — not assessable before
      implementation; carry to the plan
- [ ] No implementation details leak into specification — same finding as A

## Failing items

**A. The spec names an external API.** MarvelCDB appears 22 times, four of them inside
requirements (FR-002, FR-003, FR-044, FR-046). The item as worded is not satisfied.

This is deliberate, not an oversight: *which* upstream supplies card identity and quantities
is a product decision — the feature does not exist without it — and naming it is what makes
FR-002 (metadata only, no art) and FR-046 (refuse rather than guess when unreachable)
enforceable. Endpoint paths, response schemas, and the HTTP client stay out and belong in the
plan. Recorded as failing rather than quietly reinterpreted, so a reviewer can disagree.

**B. Two requirements are not unambiguous.**

- **FR-011** requires refusing a pack identification when agreement is "too weak to be
  confident" without saying what weak means.
- **FR-023** bounds *when* a name match is permitted but not how much misspelling to tolerate.

Both are consequential — FR-023 in particular, since too strict a rule leaves Thor's
`Invulnerability` unresolvable and too loose a rule pairs a card with the wrong file. Both are
deferred to the plan below, and that deferral is what makes these boxes fail. If either
becomes user-visible, it belongs back in the spec.

**C. Acceptance coverage is partial.** 20 acceptance scenarios against 51 functional
requirements. Covered: deck composition, quantities, borrowing, folder selection, manual
resolution, and the failure paths — the correctness-critical parts. Uncovered:

- the reporting block, FR-031 to FR-037
- the MarvelCDB conduct block, FR-038 to FR-043 — only FR-040 has a proxy, in SC-006d
- the upstream-data block, FR-044 to FR-047

Those need scenarios before planning closes, or they will be implemented against prose alone.
The conduct block is the one where that matters most: a requirement to honour cache headers
with nothing asserting it is a requirement that quietly does not hold.

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
  `core`), which is why FR-016 exists.
- The library holds 4,447 images and every card probed exists somewhere in it.

### Corrected after review

**Deck size was overstated.** An earlier revision of this spec asserted that a Marvel
Champions deck is exactly 40 cards and built the feature's correctness check on it. The
deckbuilding rules permit 40 to 50. The evidence for 40 is real but partial — five official
starter decklists and eight reconstructed hero folders, thirteen observations against roughly
sixty released packs — and none of it establishes a universal.

The verification mechanism moved accordingly: from "does the deck total 40" to "did every card
resolve to an image" (FR-017), with the total reported and a deviation from 40 raised as a
warning (FR-018). This is the stronger check regardless, since it is what actually
distinguishes a correct deck from a quietly short one.

**Hall of Heroes was investigated as a source of official pre-built contents and rejected.**
It publishes each pack's starter deck as a photograph of the decklist card, so it would need
the same optical recognition the library's own scanned decklist photos would.

### Deliberately left to the plan

**The pack-identification confidence threshold (FR-011).** The spec requires that weak
agreement be refused but does not say what counts as weak, because the number depends on the
matching approach chosen. If the threshold ever becomes visible to the user — a prompt, a
flag — it belongs back in the spec.

**Name-matching tolerance (FR-023).** The spec bounds *when* a name match is permitted, which
is the safety-critical part. How much misspelling to tolerate is a plan decision, and a
consequential one: the library contains "Stength in Numbers" and "Steve_s Apartament", so
exact matching is too strict, while loose matching can pair a card with the wrong file. The
plan must state the rule and test it against both.

**Whether nemesis and encounter cards get their own output (FR-015).** Stated as MAY. They
are excluded from the 40 either way, which is the part that affects correctness.

### Open risk worth naming

**SC-003 is asserted, not yet demonstrated.** Thor, Black Widow, Ant-Man, and Ms. Marvel
currently reconstruct to 37, 39, 36, and 37 with a positional resolver limited to the hero
folder. Every card responsible was located elsewhere in the library, so 40 is believed
reachable through FR-021 and FR-023 — but no resolver has yet been built that reaches it.
If planning shows one of these four cannot be resolved without guessing, the honest response
is to narrow SC-003 and report the gap, not to loosen FR-019.

No [NEEDS CLARIFICATION] markers were needed. Questions that came up during drafting were
settled against measurement, and are recorded in the spec's Clarifications section.
