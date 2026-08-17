# Specification Quality Checklist: Editing a Deck Before Printing

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — **fails as worded**, see A
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed — User Scenarios, Requirements, Success Criteria

## Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain — **two remain by instruction**, see B
- [ ] Requirements are testable and unambiguous — **two are not**, see C
- [x] Success criteria are measurable
- [ ] Success criteria are technology-agnostic (no implementation details) — same finding as A
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [ ] All functional requirements have clear acceptance criteria — **43 scenarios for 59
      requirements**, see D
- [x] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria — not assessable before
      implementation; carry to the plan
- [ ] No implementation details leak into specification — same finding as A

## Failing items

**A. The spec names an external service and an interface style.** MarvelCDB appears
throughout, including inside requirements (FR-001, FR-002, FR-041, FR-048, FR-055), and
FR-056 names the HTTP API. SC-013 names the decklist endpoint.

This is the same deliberate exception feature 002 recorded, for the same reason: *which*
upstream supplies card identity is a product decision — the feature does not exist without it
— and naming it is what makes FR-001 (metadata only, never art) enforceable. The HTTP API is
named because constitution principle II requires it before any UI, so it is governance, not a
technology choice this spec is making. Endpoint paths, response schemas, storage format for
saved decks, and the HTTP client stay out and belong in the plan. Recorded as failing rather
than quietly reinterpreted, so a reviewer can disagree.

**B. Two [NEEDS CLARIFICATION] markers remain, deliberately.** Both are in the
deck-building-advisories block, and both were left for `/speckit-clarify` at the requester's
explicit instruction rather than resolved during drafting.

- **FR-050** — which rules are checked: deck size range and per-card copy limits only, or also
  aspect legality, or also hero-specific eligibility. This is a scope question, not a detail:
  each step widens the upstream data required and the implementation substantially, and the
  last of them is a genuine rules engine.
- **FR-051** — the posture when printing a rule-breaking deck. The spec is written as
  advisory (warn, print anyway), which is the requester's stated preference and is consistent
  with the feature's framing. The open part is whether printing a rule-breaking deck should
  require an explicit acknowledgement, matching feature 002's FR-030a pattern for printing an
  *incomplete* deck. That precedent exists in this project and cuts both ways: 002 used it for
  a deck that is silently wrong, whereas a rule-breaking deck is one the user chose knowingly.

Everything downstream of these two is written to hold under any of the candidate answers, so
the spec is coherent as it stands. Only FR-050, FR-051, and SC-011 change.

**C. Two requirements are not unambiguous, and are deferred to the plan.**

- **FR-024** requires search results to be "bounded so that a broad query stays usable"
  without stating the bound. The number depends on how results are presented and is not
  meaningful to fix before that is designed. What the spec does fix is the part that matters
  for correctness: the bound must be visible, never a silent truncation.
- **FR-020** requires filtering by traits without stating the matching semantics — whether a
  trait query matches exactly, by prefix, or by substring. Consequential enough to state in
  the plan and test, not consequential enough to gate the spec.

If either becomes visible to the user as a setting or a prompt, it belongs back in the spec.

**D. Acceptance coverage is partial.** 43 acceptance scenarios against 59 functional
requirements. Covered: every editing operation, pool search, image availability, persistence
and reopening, import and its failure paths, and the advisory behaviour — the
correctness-critical parts. Uncovered:

- the conduct block, FR-048 and FR-049. Only FR-048's request-volume clause has a proxy, in
  SC-009. This inherits feature 002's identical gap, which that spec also recorded as
  uncovered, so the two should be closed together rather than separately.
- FR-056 and FR-057 — API-first and reuse of feature 001's PDF path. Both are architectural
  constraints better asserted by a contract test and an architecture test than by a user
  scenario, but they currently have neither written down.

Those need assertions before planning closes, or they will be implemented against prose
alone. The conduct block is where that matters most: a requirement to honour cache headers
with nothing asserting it is a requirement that quietly does not hold.

## Notes

### Relationship to feature 002

This feature is named in 002's own Assumptions section as out of scope for it and belonging in
its own feature, together with the three things it would need — a mutable deck outliving one
run, a browsable card pool, and rules for deck contents. Those three are User Story 2, User
Story 3, and User Story 7 here. The spec was written to that boundary deliberately: 002
answers what a pack contained and where its images are, 003 answers what the user wants on the
page.

Nothing in this spec relaxes a 002 or 001 requirement. Three are restated rather than assumed
because this feature creates the first situation where they could plausibly be broken:

- **FR-001** (never download art) — restated because this feature lets a user reference a card
  they have never scanned, which is precisely when downloading art becomes tempting.
- **FR-029** (an incomplete deck stops, and prints only on an explicit act) — restated because
  a user-edited deck reaches unresolved cards through a much wider set of inputs than 002 did.
- **FR-004 / FR-038** (the library stays read-only) — restated because this is the first
  feature in the project that writes anything at all during normal operation.

### Deliberately not asked as clarifications

Three questions came up during drafting and were settled with a default recorded in
Assumptions rather than spending a marker on them. Any of them is fair game for
`/speckit-clarify` to revisit:

- **Where saved decks live.** Defaulted to an application-managed local store, outside the
  scan library and outside the repository. The read-only guarantee about the library is what
  actually matters and is stated as FR-038.
- **What happens when a saved deck meets a newer snapshot.** Defaulted to reporting every
  changed or missing card by name and never silently re-resolving a code (FR-037), because the
  alternative is a deck that quietly becomes a different deck.
- **Whether the pool is the whole snapshot or only packs the library holds.** Settled as the
  whole snapshot, because the requester stated it directly and because restricting it would
  defeat the feature's purpose. The cost — that a user can add a card that cannot print — is
  handled by FR-026 through FR-029 rather than by narrowing the pool.

### Open risk worth naming

**The decklist endpoint is undocumented.** User Story 6 rests on a MarvelCDB endpoint that
works today but carries no stability promise. FR-047 confines the cost of its disappearance to
import alone, and SC-013 asserts that confinement — but the risk is real and is the reason
import is ranked P3 rather than higher. If planning finds that isolation cannot be achieved
cheaply, dropping User Story 6 costs this feature nothing else.
