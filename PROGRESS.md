# Phase 3 progress — 002 US1, print a hero's whole pack

Branch `002-starter-deck-assembly-3`, cut from `origin/main` at 6ae071e (Phases 1-2 merged
as PR #22). Delete this file before opening the PR.

## Done

- **T005** — library fixture derived from the mounted Drive (commit d60829e). Required
  fixing T004's hero matching, a `.gitignore` hole, and the placeholder generator's colour
  count. 678 files.
- **T009** — contract test merges both feature OpenAPI documents (commit 15dab22). Added
  `_PENDING_OPERATIONS` so the test is green at the end of each phase rather than red until
  Phase 7. Corrected 002's `Problem` schema, which had drifted from 001's.

## Remaining, in order

- [ ] T040-T042 pack identification + threshold calibration
- [ ] T043-T045 resolve cascade steps 1 and 3, copy counts from the printed pack
- [ ] T046-T047 bridge to 001's Catalog/HeroDeck
- [ ] T048 PDF group ordering integration test
- [ ] T048a-T048b decklist detection
- [ ] T049-T050 run lifecycle service
- [ ] T051-T053 contract tests, schemas, routes
- [ ] T048c-T048d decklist decision route
- [ ] T054 pack selection is not customization
- [ ] T055-T056 reuse key
- [ ] T057 web UI
- [ ] T058 end-to-end `cap`

## Open decisions

- T042's threshold is provisional at ≥ 0.60 with ≥ 5 matched cards. Must be measured against
  all ten acceptance heroes and written back into data-model.md § Pack Identification.
