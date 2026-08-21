# Specification Quality Checklist: Print a hero that ships inside a box

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs)
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain — **two `TODO(clarify)` markers stand, see A**
- [X] Requirements are testable and unambiguous
- [X] Success criteria are measurable
- [X] Success criteria are technology-agnostic (no implementation details)
- [X] All acceptance scenarios are defined
- [X] Edge cases are identified
- [X] Scope is clearly bounded
- [X] Dependencies and assumptions identified

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria
- [X] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria — not assessable before
      implementation; SC-103 in particular is a regression bar that can only be measured
      against a build
- [X] No implementation details leak into specification

## Notes

### A — the two open questions are deliberate and are the point

Both are recorded as `TODO(clarify)` rather than guessed, because guessing either would put a
made-up decision into a requirement where it would later read as settled.

- **FR-107, unattributed cards.** Measured, not hypothesised: `Command Center` and `Longshot`
  in Wolverine's pack carry no card set name while every other card does. In a *hero pack*
  they are plainly the hero's. In a multi-hero box the same cards may be shared, and no
  evidence in the data says whether they print with every hero, none, or by choice. This
  changes what a document contains, so it is a scope question, not a detail.

- **FR-112, the request budget.** Card set names are only knowable from a pack's card records,
  so ranking a folder against every set in the catalogue implies holding every pack — which
  FR-040 and SC-006d forbid. There are at least three defensible routes (rank packs then sets,
  learn sets lazily from packs on disk, or fetch on demand after a pack-level match) and
  choosing between them is a design decision for `/speckit-plan`, not a requirement.

Both are answerable by `/speckit-clarify`; FR-112 may be better answered by the plan, since it
turns on cost rather than on user-visible behaviour.

### B — what this spec deliberately does not do

- It does not extend printing to **villains, scenarios or campaign encounter sets**, though the
  same `card_set_name` field would enable them and boxes are full of them. That is a larger
  product question about what the tool is for; this feature is scoped to the reported failure.
- It does not revisit **FR-018**. The investigation that produced this spec found MarvelCDB's
  physical card counts unreliable in both directions, which confirms the existing decision
  rather than reopening it. Recorded in Assumptions so the finding is not lost.
