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

- [ ] CHK001 Is page size (Letter vs A4) specified as a user choice anywhere in the requirements, or only implied by "fits both"? [Gap, Spec §FR-011]
- [ ] CHK002 Are requirements defined for what occupies the unused slot area in `fit` mode — white, a border, or nothing? [Gap, Spec §FR-009b]
- [ ] CHK003 Is page orientation stated, or left to be inferred from the 3×3 grid? [Gap, Spec §FR-011]
- [ ] CHK004 Is the form, dimension, and placement of cut guides specified, or only their intent? [Completeness, Spec §FR-013]
- [ ] CHK005 Are requirements defined for where the catalog file lives and how its location is configured, as FR-019b does for the image directory? [Gap, Spec §FR-005c]
- [ ] CHK006 Is the catalog's required structure — mandatory fields, format versioning — specified in the requirements, or does it exist only in the data model? [Gap, Spec §FR-005c]
- [ ] CHK007 Is "content revision" defined in the requirements, given FR-022 mandates recording it? [Gap, Spec §FR-022]
- [ ] CHK008 Are the card-identifier scheme's rules stated as a requirement, or only as an assumption? [Completeness, Spec §FR-005b, Assumptions]
- [ ] CHK009 Is the complete set of failure kinds enumerated in the requirements, or only in the contract? [Gap, Spec §FR-021]
- [ ] CHK010 Are requirements defined for how a user retries after a retryable failure, and whether the system ever retries on its own? [Gap, Spec §FR-021]
- [ ] CHK011 Are requirements defined for the lifetime of a generation's outputs — whether a completed or failed generation is retained, and for how long? [Gap]
- [ ] CHK012 Is a maximum deck size or card count specified, given FR-0A4 requires bounded cost? [Gap, Spec §FR-0A4]

## Requirement Clarity

- [ ] CHK013 Is "target print size" unambiguous now that `fit` mode produces a face smaller than its slot? [Ambiguity, Spec §FR-009, §FR-009b]
- [ ] CHK014 Is it specified whether the 300 DPI floor is evaluated against the full source image or against the portion surviving a crop? [Ambiguity, Spec §FR-010, §FR-009b]
- [ ] CHK015 Are the explicit numeric limits behind "decode time, memory, and total work" stated, or left as adjectives? [Clarity, Spec §FR-0A4]
- [ ] CHK016 Can "cut guides that allow accurate trimming" be objectively evaluated as written? [Measurability, Spec §FR-013]
- [ ] CHK017 Is "the interface MUST state what each mode costs" specific enough to know when it has been satisfied? [Measurability, Spec §FR-009c]
- [ ] CHK018 Is "actionable message" defined with enough precision to distinguish a passing message from a failing one? [Measurability, Spec §FR-019b]
- [ ] CHK019 Is it clear whether "reflect newly added decks without a software release" permits requiring a restart? [Clarity, Spec §FR-004, §SC-009]
- [ ] CHK020 Is "no backing card visible" in the `crop` description a requirement or an explanatory aside? [Clarity, Spec §FR-009b]

## Requirement Consistency

- [ ] CHK021 Does User Story 1's acceptance scenario 2 still hold for all three fit modes, or was it written when only one size was possible? [Conflict, Spec §US1, §FR-009b]
- [ ] CHK022 Do FR-009's "±0.5 mm on both axes" and FR-009b's "may be narrower or shorter" state a single testable expectation? [Conflict, Spec §FR-009, §FR-009b]
- [ ] CHK023 Is the duplicate-image-mapping case consistently classified as blocking or non-blocking between the edge cases and the data model? [Inconsistency, Spec §Edge Cases]
- [ ] CHK024 Do FR-010's no-upscale rule, FR-020's fail-on-too-small rule, and the "fails or warns" edge case describe the same behaviour? [Conflict, Spec §FR-010, §FR-020, §Edge Cases]
- [ ] CHK025 Is error reporting consistent in granularity — FR-005d requires all catalog errors at once; do asset failures follow the same rule or stop at the first? [Consistency, Spec §FR-005d, §FR-020]
- [ ] CHK026 Does the "browser cancels a slow download" edge case still describe a reachable situation under a generate-then-download model? [Consistency, Spec §Edge Cases]

## Acceptance Criteria Quality

- [ ] CHK027 Does SC-003 specify the sample — how many cards, from which pages — that "100% of test prints" is measured over? [Measurability, Spec §SC-003]
- [ ] CHK028 Is SC-009a's "identifiable as to which mode produced it" backed by a requirement stating the mode appears on the sheet? [Traceability, Spec §SC-009a, §FR-009d]
- [ ] CHK029 Are FR-009b's three modes each given a distinct, independently verifiable acceptance criterion? [Acceptance Criteria, Spec §FR-009b]
- [ ] CHK030 Is the byte-identical requirement scoped precisely enough to say whether fit mode and page size are part of the identity? [Clarity, Spec §FR-015]

## Edge Case & Scenario Coverage

- [ ] CHK031 Are requirements defined for source images whose aspect ratios differ *from each other*, not just from the standard card? [Gap, Coverage]
- [ ] CHK032 Is the behaviour specified when a deck resolves to zero printable cards? [Gap, Coverage]
- [ ] CHK033 Are requirements defined for a catalog that parses but contains no decks, so the selection list is empty? [Gap, Coverage]
- [ ] CHK034 Is partial-failure behaviour stated — when most cards resolve and one does not — beyond implying the whole generation fails? [Coverage, Spec §FR-020]
- [ ] CHK035 Are requirements defined for image formats other than TIFF appearing in the directory? [Gap, Coverage]

## Dependencies & Assumptions

- [ ] CHK036 Is the assumption that source scans meet the resolution floor now validated against measured evidence rather than asserted? [Assumption, Spec §Assumptions]
- [ ] CHK037 Is the assumption that the user authors the catalog themselves reflected in a requirement about what happens before one exists? [Assumption, Gap]
- [ ] CHK038 Is the dependency on the user keeping the image directory in sync stated with defined behaviour when it is stale? [Dependency, Spec §Assumptions]

## Notes

- Check items off as `[x]` once the **spec** has been corrected, not once the code exists.
- Unchecked items are spec edits to make before `/speckit-tasks`, so ambiguity does not
  harden into a task list and then into code.
- Highest-priority suspicions going in: **CHK021**, **CHK022**, and **CHK024** look like
  genuine contradictions rather than omissions, and CHK001 looks like a decision that was
  made in the plan but never written back into the requirements.
