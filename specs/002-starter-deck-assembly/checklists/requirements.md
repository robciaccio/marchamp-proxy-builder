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

- [ ] All functional requirements have clear acceptance criteria — **37 scenarios for 69
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

**C. Acceptance coverage is partial.** 37 acceptance scenarios against 69 functional
requirements, after two clarification sessions on 2026-08-16 added to both. Covered: deck
composition, quantities, borrowing, folder selection, manual resolution, run durability, PDF
retention and reuse, pack confirmation, the identity and nemesis outputs, and the failure
paths — the correctness-critical parts. Uncovered:

- the reporting block, FR-031 to FR-037
- the MarvelCDB conduct block, FR-038 to FR-043 — only FR-040 has a proxy, in SC-006d
- the upstream-data block, partly closed: FR-044a and FR-044b now have scenarios (US1 12–13)
  and SC-006d covers request volume, but FR-046 and FR-047 remain unasserted

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

### Resolved by clarification, 2026-08-16

**Whether nemesis and encounter cards get their own output (FR-015).** No longer deferred and
no longer a MAY. Assembling a hero now produces the player deck, the identity card, and the
nemesis set as three distinct outputs (FR-015a to FR-015c), because a printed player deck on
its own is not something anyone can sit down and play. They stay out of the deck total.
Distinctness is a matter of the report, not the page — see the second session's note on
FR-015d below.

**How the user resolves a card the tool could not find, and what happens if they stop
halfway.** Assembly is a durable run the wizard walks the user through card by card, resumable
on a later visit, listed as finished or still waiting (FR-026a to FR-026d). This retires
feature 001's premise that generations need not outlive the process.

**Whether this feature ships a CLI.** It does not. FR-036's outcome signal is a field on the
run rather than a process exit status.

**How the eight named heroes are verified.** Against the real library on the user's machine
for SC-002 and SC-003, and against fixtures derived from that library's filenames for
automated runs. Because this repository is public, FR-038a now forbids committing card art or
MarvelCDB card text as fixture data.

### Resolved by a second clarification session, 2026-08-16

**Output packaging (FR-015d, FR-015e).** One PDF, not three files, and packed into as few pages
as the cards allow — the player deck, identity card, and nemesis set run together with no page
break between them, so a single page may carry cards from two of the three. Paper is the cost
being minimised. "Distinct outputs" elsewhere in the spec means distinct in the report and in
the deck total, never distinct files or pages, and FR-015e makes the report responsible for
telling the three apart since the layout no longer does.

**How a replacement card reaches the tool (FR-026e).** By browser upload, with the run keeping
the bytes. This closed a real contradiction: FR-027 required recording a manual choice made
from outside the run's folder while FR-009 forbade logging any path from outside it. Nothing
outside the boundary is recorded now — only the uploaded file's own name.

**Upstream scope and refresh (FR-040, FR-044a, FR-044b).** Snapshots are per pack, captured on
first use of that pack and reused after. FR-040 previously permitted fetching the full card
list; it no longer does. Refresh is cache-header driven with an explicit manual refresh, and a
refresh never mutates an existing run.

**PDF retention and reuse (FR-026f to FR-026i).** Finished PDFs are stored, not rebuilt. A run
needing no user input produces the pack's *standard* PDF, reused by later requests for that
pack against the same snapshot; a customized run's PDF is named by the user and kept in a
separate saved list. Reuse is keyed on snapshot revision so refreshed data invalidates it.
Storage is unbounded by design, so FR-026g adds user deletion as the bound — at roughly 202 MB
per deck this is load-bearing, not housekeeping.

**Pack confirmation (FR-012a).** The user now confirms the identified pack before any card is
resolved. FR-011 refuses a weak match; FR-012a covers the confident-but-wrong case, which
FR-011 structurally cannot.

### Open risk worth naming

**SC-003 is asserted, not yet demonstrated.** Thor, Black Widow, Ant-Man, and Ms. Marvel
currently reconstruct to 37, 39, 36, and 37 with a positional resolver limited to the hero
folder. Every card responsible was located elsewhere in the library, so 40 is believed
reachable through FR-021 and FR-023 — but no resolver has yet been built that reaches it.
If planning shows one of these four cannot be resolved without guessing, the honest response
is to narrow SC-003 and report the gap, not to loosen FR-019.

No [NEEDS CLARIFICATION] markers were needed. Questions that came up during drafting were
settled against measurement, and are recorded in the spec's Clarifications section.
