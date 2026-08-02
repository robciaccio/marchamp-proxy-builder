# Specification Quality Checklist: Catalog Scaffolding from a Card Image Directory

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
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

All items passed on review. Two things were deliberately kept out of the spec while
drafting, and are worth recording so they are not read as omissions:

**The mechanism for "unfinished means invalid".** There is an obvious way to satisfy FR-012
using a sentinel quantity the existing validator already rejects. That is a plan decision,
not a spec one, so the spec states only the required outcome — unfinished and invalid are
the same state — and leaves the how open.

**The output's concrete shape.** The catalog format already exists in feature 001 and this
feature adds nothing to it, so the spec references it rather than restating it. The one
mention of JSON is in the motivation, describing what a user writes by hand today.

No [NEEDS CLARIFICATION] markers were needed. Three questions came up during drafting and
were settled against existing evidence rather than by asking:

1. *Whole-library or per-pack scaffolding?* Both. Cards are gathered across the whole
   directory so a card published in several packs becomes one card with several printings
   (FR-008), while deck proposals are per pack folder (Assumptions). Recorded rather than
   asked because the reference library already demonstrates both needs.
2. *What if the output already exists?* Refuse by default, merge when asked (FR-004,
   FR-022). The destructive default is the one that makes a tool unusable twice.
3. *Should quantities default to 1?* No, and this is the load-bearing decision of the whole
   feature. A default of 1 would produce a deck that is wrong and validates cleanly. FR-011
   and FR-012 exist to make that outcome unreachable.

One point deserves attention at planning time: FR-023 (preserving user edits to identifiers
across a re-run) needs a way to recognise a card whose identifier the user has changed. That
is a real design problem, not a detail, and the plan should address it explicitly.
