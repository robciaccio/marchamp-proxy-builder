# Coherence Requirements Checklist: Hero Deck PDF Wizard

**Purpose**: Second-pass requirements-quality gate covering cross-artifact consistency,
interaction flow, and non-functional precision — the ground `correctness.md` did not touch
**Created**: 2026-07-31
**Feature**: [spec.md](../spec.md)

**Depth**: Standard gate · **Timing**: Before `/speckit-tasks` · **Audience**: Spec author

> IDs are scoped to this file and restart at CHK001; they do not continue from
> `correctness.md`.
>
> Cross-artifact items compare [spec.md](../spec.md) against [plan.md](../plan.md),
> [data-model.md](../data-model.md), and [contracts/openapi.yaml](../contracts/openapi.yaml).
> Two of the four defects found in pass 1 were drift of exactly this kind, which is why it
> leads here.

## Cross-Artifact Consistency

- [ ] CHK001 Does the data model's Generation Record carry the fit mode that FR-022 now requires be recorded? [Conflict, Spec §FR-022 vs data-model §Generation Record]
- [ ] CHK002 Are FR-0A4's numeric limits — 200 faces, 120 s, 512 MB, 80 MP — represented anywhere beyond the spec, given the plan and data model still describe them only as concepts? [Gap, Spec §FR-0A4 vs plan.md, data-model.md]
- [ ] CHK003 Is FR-009d's requirement that the fit mode be identifiable *from the document itself* expressed in any design artifact, or does it exist only as prose in the spec? [Gap, Spec §FR-009d]
- [ ] CHK004 Does the plan's "preview first page visible within 5 s" performance goal correspond to any success criterion in the spec, or did the plan invent a target the spec never set? [Conflict, plan.md §Technical Context vs Spec §SC-007]
- [ ] CHK005 Do FR-021's six named failure conditions match the contract's `Failure.kind` enumeration exactly, with no member in one absent from the other? [Consistency, Spec §FR-021 vs contract §Failure]
- [ ] CHK006 Is FR-021b's "outputs live only as long as the process" reflected in the contract's description of the generation lifecycle? [Gap, Spec §FR-021b vs contract §Generation]
- [ ] CHK007 Is FR-008b's portrait requirement carried into the data model's Print Layout? [Gap, Spec §FR-008b vs data-model §Print Layout]
- [ ] CHK008 Does the data model's fit-mode table state FR-009b1's blank-slot rule, or only the scaling maths? [Completeness, Spec §FR-009b1 vs data-model]
- [ ] CHK009 Does the quickstart's geometry scenario assert the mode-specific tolerances FR-009 and FR-009b now define, rather than a single size? [Consistency, quickstart §V4 vs Spec §FR-009]
- [ ] CHK010 Is every functional requirement traceable to a module in the plan's source layout, and does every module trace back to a requirement? [Traceability]
- [ ] CHK011 Are "slot", "card size", "card box", and "printed face" used with one consistent meaning across all four artifacts? [Consistency, Terminology]
- [ ] CHK012 When a requirement changes, is there a stated expectation about which artifacts must be updated with it? [Gap, Process]

## UX & Interaction Flow

- [ ] CHK013 Are requirements defined for what the user sees during a generation that FR-0A4 permits to run up to 120 seconds? [Gap, Spec §FR-003, §FR-0A4]
- [ ] CHK014 Does FR-003's "return to a prior step without losing selection" specify what happens once a generation is already running? [Clarity, Spec §FR-003]
- [ ] CHK015 Are requirements defined for what the user sees while the catalog is being validated at startup? [Gap, Spec §FR-005c]
- [ ] CHK016 Are the empty states — no catalog configured, catalog with no decks, deck with no cards — specified as presentations rather than only as error conditions? [Coverage, Spec §FR-005c3]
- [ ] CHK017 Is it specified whether changing fit mode or page size invalidates an existing preview, or silently leaves a stale one on screen? [Gap, Spec §FR-016, §FR-009b]
- [ ] CHK018 Is it specified how a validation report containing many errors is presented without becoming unreadable? [Clarity, Spec §FR-005d]
- [ ] CHK019 Is the calibration page's discoverability specified — that a user can reach it from the flow rather than needing to know a URL? [Gap, Spec §FR-023]
- [ ] CHK020 Are requirements defined for cancelling an in-flight generation? [Gap, Coverage]
- [ ] CHK021 Is the download step specified — the filename, and whether the document opens or saves? [Gap, Spec §FR-008]
- [ ] CHK022 Are accessibility requirements defined for any part of the wizard, or is their absence a deliberate scope decision? [Gap, Non-Functional]
- [ ] CHK023 Is it specified whether the preview must be usable before all pages have rendered, or only once every page is ready? [Clarity, Spec §FR-016]

## Non-Functional Precision

- [ ] CHK024 Does SC-007's "95% within 30 seconds" state the deck size and machine class it is measured against? [Measurability, Spec §SC-007]
- [ ] CHK025 Is the relationship between SC-007's 30-second target and FR-0A4's 120-second hard limit stated, so it is clear one is a goal and the other a cutoff? [Clarity, Spec §SC-007, §FR-0A4]
- [ ] CHK026 Does FR-015's byte-identical requirement state its scope — same process, same machine, same library versions, or across all of these? [Clarity, Spec §FR-015]
- [ ] CHK027 Is the pinned resampling behaviour that determinism depends on stated as a requirement, or does it exist only as a research note in the plan? [Gap, plan.md §R7 vs Spec §FR-015]
- [ ] CHK028 Are the generation log's destination, format, and retention specified, given FR-022 mandates its content? [Gap, Spec §FR-022]
- [ ] CHK029 Is there a requirement that logs exclude filesystem paths outside the configured directories and anything else the user would not want pasted into an issue? [Gap, Spec §FR-022]
- [ ] CHK030 Is SC-006's "100% of attempts" bounded by a stated number of attempts, so the criterion can be declared met? [Measurability, Spec §SC-006]
- [ ] CHK031 Is the preview raster resolution specified as a requirement, given the contract accepts a 200–2000 px width? [Gap, contract §getGenerationPage vs Spec §FR-016]
- [ ] CHK032 Are the machine's assumed memory and CPU characteristics stated, given FR-0A4 sets absolute limits that only make sense against some baseline? [Assumption, Spec §FR-0A4]

## Notes

- Check items off as `[x]` once the **spec or the drifting artifact** has been corrected.
- Verified before writing: **CHK001, CHK002, CHK003, CHK004, and CHK013 are confirmed
  defects**, not open questions. The first four are spec-to-artifact drift of the same kind
  pass 1 found; CHK013 is a genuine gap — nothing in the spec requires any feedback during a
  generation the spec itself allows to run for two minutes.
- CHK012 is deliberately a process item rather than a product one. Drift has now caused
  defects in two consecutive passes, which suggests the absence of a stated update
  expectation is itself the root cause.
