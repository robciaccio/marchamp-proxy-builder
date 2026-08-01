# Correctness Requirements Checklist: Hero Deck PDF Wizard

**Purpose**: Stress-test the *wording* of the print-output, content-catalog, and
failure-semantics requirements before task breakdown — unit tests for the English, not for
the code
**Created**: 2026-07-31
**Feature**: [spec.md](../spec.md)

**Depth**: Standard gate · **Timing**: Before `/speckit-tasks` · **Audience**: Spec author

> Every item asks whether a requirement is written well enough to build and verify against.
> None asks whether the software works. An unchecked item means the **spec** needs an edit.

## Requirement Completeness

- [x] CHK001 Is page size (Letter vs A4) specified as a user choice anywhere in the requirements, or only implied by "fits both"? [Gap, Spec §FR-011]
- [x] CHK002 Are requirements defined for what occupies the unused slot area in `fit` mode — white, a border, or nothing? [Gap, Spec §FR-009b]
- [x] CHK003 Is page orientation stated, or left to be inferred from the 3×3 grid? [Gap, Spec §FR-011]
- [x] CHK004 Is the form, dimension, and placement of cut guides specified, or only their intent? [Completeness, Spec §FR-013]
- [x] CHK005 Are requirements defined for where the catalog file lives and how its location is configured, as FR-019b does for the image directory? [Gap, Spec §FR-005c]
- [x] CHK006 Is the catalog's required structure — mandatory fields, format versioning — specified in the requirements, or does it exist only in the data model? [Gap, Spec §FR-005c]
- [x] CHK007 Is "content revision" defined in the requirements, given FR-022 mandates recording it? [Gap, Spec §FR-022]
- [x] CHK008 Are the card-identifier scheme's rules stated as a requirement, or only as an assumption? [Completeness, Spec §FR-005b, Assumptions]
- [x] CHK009 Is the complete set of failure kinds enumerated in the requirements, or only in the contract? [Gap, Spec §FR-021]
- [x] CHK010 Are requirements defined for how a user retries after a retryable failure, and whether the system ever retries on its own? [Gap, Spec §FR-021]
- [x] CHK011 Are requirements defined for the lifetime of a generation's outputs — whether a completed or failed generation is retained, and for how long? [Gap]
- [x] CHK012 Is a maximum deck size or card count specified, given FR-0A4 requires bounded cost? [Gap, Spec §FR-0A4]

## Requirement Clarity

- [x] CHK013 Is "target print size" unambiguous now that `fit` mode produces a face smaller than its slot? [Ambiguity, Spec §FR-009, §FR-009b]
- [x] CHK014 Is it specified whether the 300 DPI floor is evaluated against the full source image or against the portion surviving a crop? [Ambiguity, Spec §FR-010, §FR-009b]
- [x] CHK015 Are the explicit numeric limits behind "decode time, memory, and total work" stated, or left as adjectives? [Clarity, Spec §FR-0A4]
- [x] CHK016 Can "cut guides that allow accurate trimming" be objectively evaluated as written? [Measurability, Spec §FR-013]
- [x] CHK017 Is "the interface MUST state what each mode costs" specific enough to know when it has been satisfied? [Measurability, Spec §FR-009c]
- [x] CHK018 Is "actionable message" defined with enough precision to distinguish a passing message from a failing one? [Measurability, Spec §FR-019b]
- [x] CHK019 Is it clear whether "reflect newly added decks without a software release" permits requiring a restart? [Clarity, Spec §FR-004, §SC-009]
- [x] CHK020 Is "no backing card visible" in the `crop` description a requirement or an explanatory aside? [Clarity, Spec §FR-009b]

## Requirement Consistency

- [x] CHK021 Does User Story 1's acceptance scenario 2 still hold for all three fit modes, or was it written when only one size was possible? [Conflict, Spec §US1, §FR-009b]
- [x] CHK022 Do FR-009's "±0.5 mm on both axes" and FR-009b's "may be narrower or shorter" state a single testable expectation? [Conflict, Spec §FR-009, §FR-009b]
- [x] CHK023 Is the duplicate-image-mapping case consistently classified as blocking or non-blocking between the edge cases and the data model? [Inconsistency, Spec §Edge Cases]
- [x] CHK024 Do FR-010's no-upscale rule, FR-020's fail-on-too-small rule, and the "fails or warns" edge case describe the same behaviour? [Conflict, Spec §FR-010, §FR-020, §Edge Cases]
- [x] CHK025 Is error reporting consistent in granularity — FR-005d requires all catalog errors at once; do asset failures follow the same rule or stop at the first? [Consistency, Spec §FR-005d, §FR-020]
- [x] CHK026 Does the "browser cancels a slow download" edge case still describe a reachable situation under a generate-then-download model? [Consistency, Spec §Edge Cases]

## Acceptance Criteria Quality

- [x] CHK027 Does SC-003 specify the sample — how many cards, from which pages — that "100% of test prints" is measured over? [Measurability, Spec §SC-003]
- [x] CHK028 Is SC-009a's "identifiable as to which mode produced it" backed by a requirement stating the mode appears on the sheet? [Traceability, Spec §SC-009a, §FR-009d]
- [x] CHK029 Are FR-009b's three modes each given a distinct, independently verifiable acceptance criterion? [Acceptance Criteria, Spec §FR-009b]
- [x] CHK030 Is the byte-identical requirement scoped precisely enough to say whether fit mode and page size are part of the identity? [Clarity, Spec §FR-015]

## Edge Case & Scenario Coverage

- [x] CHK031 Are requirements defined for source images whose aspect ratios differ *from each other*, not just from the standard card? [Gap, Coverage]
- [x] CHK032 Is the behaviour specified when a deck resolves to zero printable cards? [Gap, Coverage]
- [x] CHK033 Are requirements defined for a catalog that parses but contains no decks, so the selection list is empty? [Gap, Coverage]
- [x] CHK034 Is partial-failure behaviour stated — when most cards resolve and one does not — beyond implying the whole generation fails? [Coverage, Spec §FR-020]
- [x] CHK035 Are requirements defined for image formats other than TIFF appearing in the directory? [Gap, Coverage]

## Dependencies & Assumptions

- [x] CHK036 Is the assumption that source scans meet the resolution floor now validated against measured evidence rather than asserted? [Assumption, Spec §Assumptions]
- [x] CHK037 Is the assumption that the user authors the catalog themselves reflected in a requirement about what happens before one exists? [Assumption, Gap]
- [x] CHK038 Is the dependency on the user keeping the image directory in sync stated with defined behaviour when it is stale? [Dependency, Spec §Assumptions]

## Resolution — worked 2026-07-31

All 38 items resolved by amending the spec. The three suspected contradictions were all
real, and one additional inconsistency surfaced during the pass.

**Contradictions fixed**

- **CHK021** — User Story 1 scenario 2 predated fit modes and asserted one size for all
  three. Rewritten to distinguish the 63.5 × 88.9 mm *slot* from the printed *face*, which
  is 61.8 × 88.9 mm in `fit`.
- **CHK022** — FR-009 and FR-009b now state one testable expectation per mode, added as a
  paragraph inside FR-009b.
- **CHK024** — "fails or warns" was genuinely undecided text. Resolved to **fail**: the
  alternatives are upscaling, which FR-010 forbids, or printing a face too coarse to read.
  FR-020 and the edge case now agree.
- **CHK023** — duplicate image mapping was "reported" in the spec but a non-blocking warning
  in the data model. Settled as a **warning**.
- **CHK025** *(surfaced during the pass)* — catalog validation reported all errors at once
  but asset failures did not. New **FR-020a** makes them symmetric, which changed the
  contract: `Generation.failure` became `failures[]`.

**Gaps closed**

Page size as an explicit user choice and portrait orientation (FR-008a, FR-008b) — the
page-size decision existed only in the plan and contract. Blank unused slot area in `fit`
(FR-009b1). Per-card independent fitting (FR-009b2), because the sample scans vary from
each other, not just from the standard. Cut guide form and placement (FR-013). Catalog
location, format version, and content-derived revision (FR-005c1–c3). Opaque card
identifiers (FR-005b1). Enumerated failure conditions with exactly one retryable
(FR-021). No automatic retry (FR-021a). Output retained for the process lifetime only
(FR-021b). Concrete cost limits (FR-0A4). Error message content standard (FR-019b1).
Content-sniffed format acceptance (FR-019d). Six new edge cases, and SC-003, SC-009a,
SC-011 made measurable.

**Judgment calls made rather than escalated** — override any of these if you disagree:

| Item | Call | Reasoning |
|---|---|---|
| CHK024 | Below-resolution is a hard failure | Fail-closed; the alternatives violate FR-010 or produce unreadable cards |
| CHK014 | DPI measured over the printed region, post-crop | Discarded pixels do not contribute to what is printed |
| CHK012 | 200 card faces, 120 s, 512 MB, 80 MP per image | Far above real decks (~41 cards, ~3 MP), far below destabilising a laptop |
| CHK011 | Documents live only as long as the process | Nothing in this feature needs durable output |
| CHK002 | `fit` leaves the slot blank, no frame | A border would be a design choice nobody asked for |

Spec grew from 35 to 52 functional requirements, 12 to 14 success criteria, and 16 to 22
edge cases.
