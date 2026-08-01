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

- [x] CHK001 Does the data model's Generation Record carry the fit mode that FR-022 now requires be recorded? [Conflict, Spec §FR-022 vs data-model §Generation Record]
- [x] CHK002 Are FR-0A4's numeric limits — 200 faces, 120 s, 512 MB, 80 MP — represented anywhere beyond the spec, given the plan and data model still describe them only as concepts? [Gap, Spec §FR-0A4 vs plan.md, data-model.md]
- [x] CHK003 Is FR-009d's requirement that the fit mode be identifiable *from the document itself* expressed in any design artifact, or does it exist only as prose in the spec? [Gap, Spec §FR-009d]
- [x] CHK004 Does the plan's "preview first page visible within 5 s" performance goal correspond to any success criterion in the spec, or did the plan invent a target the spec never set? [Conflict, plan.md §Technical Context vs Spec §SC-007]
- [x] CHK005 Do FR-021's six named failure conditions match the contract's `Failure.kind` enumeration exactly, with no member in one absent from the other? [Consistency, Spec §FR-021 vs contract §Failure]
- [x] CHK006 Is FR-021b's "outputs live only as long as the process" reflected in the contract's description of the generation lifecycle? [Gap, Spec §FR-021b vs contract §Generation]
- [x] CHK007 Is FR-008b's portrait requirement carried into the data model's Print Layout? [Gap, Spec §FR-008b vs data-model §Print Layout]
- [x] CHK008 Does the data model's fit-mode table state FR-009b1's blank-slot rule, or only the scaling maths? [Completeness, Spec §FR-009b1 vs data-model]
- [x] CHK009 Does the quickstart's geometry scenario assert the mode-specific tolerances FR-009 and FR-009b now define, rather than a single size? [Consistency, quickstart §V4 vs Spec §FR-009]
- [x] CHK010 Is every functional requirement traceable to a module in the plan's source layout, and does every module trace back to a requirement? [Traceability]
- [x] CHK011 Are "slot", "card size", "card box", and "printed face" used with one consistent meaning across all four artifacts? [Consistency, Terminology]
- [x] CHK012 When a requirement changes, is there a stated expectation about which artifacts must be updated with it? [Gap, Process]

## UX & Interaction Flow

- [x] CHK013 Are requirements defined for what the user sees during a generation that FR-0A4 permits to run up to 120 seconds? [Gap, Spec §FR-003, §FR-0A4]
- [x] CHK014 Does FR-003's "return to a prior step without losing selection" specify what happens once a generation is already running? [Clarity, Spec §FR-003]
- [x] CHK015 Are requirements defined for what the user sees while the catalog is being validated at startup? [Gap, Spec §FR-005c]
- [x] CHK016 Are the empty states — no catalog configured, catalog with no decks, deck with no cards — specified as presentations rather than only as error conditions? [Coverage, Spec §FR-005c3]
- [x] CHK017 Is it specified whether changing fit mode or page size invalidates an existing preview, or silently leaves a stale one on screen? [Gap, Spec §FR-016, §FR-009b]
- [x] CHK018 Is it specified how a validation report containing many errors is presented without becoming unreadable? [Clarity, Spec §FR-005d]
- [x] CHK019 Is the calibration page's discoverability specified — that a user can reach it from the flow rather than needing to know a URL? [Gap, Spec §FR-023]
- [x] CHK020 Are requirements defined for cancelling an in-flight generation? [Gap, Coverage]
- [x] CHK021 Is the download step specified — the filename, and whether the document opens or saves? [Gap, Spec §FR-008]
- [x] CHK022 Are accessibility requirements defined for any part of the wizard, or is their absence a deliberate scope decision? [Gap, Non-Functional]
- [x] CHK023 Is it specified whether the preview must be usable before all pages have rendered, or only once every page is ready? [Clarity, Spec §FR-016]

## Non-Functional Precision

- [x] CHK024 Does SC-007's "95% within 30 seconds" state the deck size and machine class it is measured against? [Measurability, Spec §SC-007]
- [x] CHK025 Is the relationship between SC-007's 30-second target and FR-0A4's 120-second hard limit stated, so it is clear one is a goal and the other a cutoff? [Clarity, Spec §SC-007, §FR-0A4]
- [x] CHK026 Does FR-015's byte-identical requirement state its scope — same process, same machine, same library versions, or across all of these? [Clarity, Spec §FR-015]
- [x] CHK027 Is the pinned resampling behaviour that determinism depends on stated as a requirement, or does it exist only as a research note in the plan? [Gap, plan.md §R7 vs Spec §FR-015]
- [x] CHK028 Are the generation log's destination, format, and retention specified, given FR-022 mandates its content? [Gap, Spec §FR-022]
- [x] CHK029 Is there a requirement that logs exclude filesystem paths outside the configured directories and anything else the user would not want pasted into an issue? [Gap, Spec §FR-022]
- [x] CHK030 Is SC-006's "100% of attempts" bounded by a stated number of attempts, so the criterion can be declared met? [Measurability, Spec §SC-006]
- [x] CHK031 Is the preview raster resolution specified as a requirement, given the contract accepts a 200–2000 px width? [Gap, contract §getGenerationPage vs Spec §FR-016]
- [x] CHK032 Are the machine's assumed memory and CPU characteristics stated, given FR-0A4 sets absolute limits that only make sense against some baseline? [Assumption, Spec §FR-0A4]

## Resolution — worked 2026-07-31

All 32 items resolved. The five confirmed defects are fixed and the drift they came from is
addressed at the root.

**Drift fixed**

- **CHK001** — `fit_mode` added to the data model's Generation Record. FR-022 required it;
  I had amended FR-022 an hour earlier without propagating.
- **CHK002** — FR-0A4's numeric ceilings now appear as a Cost Limits table in the data model
  and in the plan's Technical Context, no longer only as prose in the spec.
- **CHK003** — FR-009d's "identifiable from the document itself" now lands concretely: the
  data model states it, and the contract specifies a `Content-Disposition` filename carrying
  deck, mode, and page size (new **FR-008c**).
- **CHK004** — the plan had invented a five-second preview target. Promoted to **SC-007a**
  in the spec; the plan now references the criteria rather than asserting its own.
- **CHK011** — "card box" removed; *slot* is canonical, and `card_size_mm` became
  `slot_size_mm`.

**Root cause, not just symptoms.** CHK012 produced an **Artifact Update Rule** in the plan:
a requirement change is not complete until every artifact it touches moves in the same
commit, with a table of what to check for each kind of change. Drift caused defects in two
consecutive passes, all of them mine, from edits made minutes earlier — that is a missing
rule, not carelessness. If it holds up, it belongs in the constitution's Development
Workflow section. A **Requirement-to-Module Traceability** table (CHK010) was added
alongside it.

**Interaction gaps closed** — FR-016a requires visible progress, which mattered because
FR-0A4 permits a 120-second run and nothing previously required the interface to show
anything at all; the contract gained `progress` and `pages_ready` to support it. Also:
progressive preview (FR-016b), preview invalidation on settings change (FR-016c), behaviour
during startup validation, distinguishable empty states, readable multi-error reports, and
calibration reachable from the interface (FR-003a–g).

**Non-functional claims made precise** — determinism scoped to one machine with pinned
dependency versions and explicitly *not* claimed across library versions (FR-015), with the
pinning obligation promoted from a research note to a requirement (FR-015a). SC-006 bounded
at 20 consecutive attempts including a cross-process run. SC-007 given a deck size and
machine class, and its relationship to the 120 s ceiling stated. Log destination, format,
and content restrictions specified (FR-022a–b).

**Judgment calls** — override if you disagree: explicit cancellation is *not* required
(FR-003b), since abandoning is sufficient under a 120-second ceiling; formal accessibility
conformance is *out of scope* with keyboard operability still required (FR-003g), a
deliberate scope decision for a single-user local tool rather than an omission.
