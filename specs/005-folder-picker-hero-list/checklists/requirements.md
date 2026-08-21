# Specification Quality Checklist: Choose a folder, then choose a hero

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
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

- **OD-001 is resolved.** Settled by a four-expert panel and recorded in
  [ADR 0002](../../../docs/adr/0002-the-service-opens-the-native-folder-dialog.md), status
  Proposed. The panel split 2-2 and the dissent is recorded in the ADR. FR-024 through FR-028
  were added to the spec to carry the conditions the decision is contingent on.
- **FR-019 survived unamended**, which was one of the reasons the decision went the way it did.
  The rejected in-page-browser option could not have been built without repealing it.
- **The premise was verified, not assumed.** A browser genuinely cannot learn a chosen folder's
  absolute path — `showDirectoryPicker()`, `webkitdirectory`, and folder drag-and-drop were each
  checked and each closed. See ADR 0002's Context.
- **One premise remains unverified and is called out as such.** FR-025 requires the chooser to
  come to the front; the platform documents it opening behind other windows. ADR 0002 names
  this as the trigger that reverses the decision, and it must be checked by hand before
  implementation begins.
- **A live pre-existing defect was found during the panel** and is recorded under Dependencies:
  the service accepts any `Host` header with no middleware installed, and a run request against
  an arbitrary absolute path leaks both a directory-existence signal and path fragments
  discovered by walking it. Not caused by this feature; must be fixed before it.
