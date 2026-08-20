# Specification Quality Checklist: See a pack before you print it

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — **fails as worded, see A**
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain — **one `TODO(clarify)` stands, see B**
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
      implementation
- [X] No implementation details leak into specification

## Notes

### A — the spec names existing internals, deliberately

`RunState.RENDERING`, `resume()`, `compose`'s `on_page` hook, `202 Accepted`, and 001's worker
pool all appear by name. They are not proposed design; they are **evidence about the system
being changed**, and each one makes the case that a requirement is smaller than it sounds:

- User Story 2 reads like new machinery until you know the lifecycle already has a `rendering`
  state and a recovery path for a run interrupted in it.
- User Story 3 reads like a redesign of the renderer until you know `compose` already takes a
  per-page callback documented as not affecting the output bytes.
- FR-211 is only meaningful if you know the endpoint already returns `202` for work it has
  already finished.

Rewriting these into implementation-free prose would make the spec shorter and the plan
harder, so they stay and the checklist item is failed honestly rather than argued away.

### B — the one open question

**FR-213, whether page images are stored at all.** A preview can be rasterised on demand every
time, or cached. The trade is the render cost of a ~200 MB document against storage that
ADR 0001 already sweeps, and it interacts with User Story 3, where a page must be available
*before* the document exists. Answering it in the spec would be choosing an implementation;
`/speckit-plan` is where it belongs.

### C — what this deliberately excludes

- **Paper size and fit mode in the pack wizard.** A real gap, and a prerequisite for a preview
  to be worth looking at, but the API has carried both since 002 shipped and only the wizard
  omits them. Being fixed separately as a bug.
- **Making rendering faster.** 001's SC-007 and SC-007a are knowingly missed and accepted.
  This feature makes the wait visible; nothing here asserts a duration for composing.
