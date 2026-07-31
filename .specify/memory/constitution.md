<!--
Sync Impact Report
==================
Version change: TEMPLATE (unversioned) → 1.0.0
Rationale: Initial ratification. Version held at 1.0.0 rather than bumped to 2.0.0
despite a principle redefinition, because the prior 1.0.0 draft was never committed
(repository has zero commits) and therefore governed no work. This is a revision of
the initial ratification, not an amendment to a live document.

Modified principles:
  [PRINCIPLE_1_NAME] → I. Test-First (NON-NEGOTIABLE)
  [PRINCIPLE_2_NAME] → II. Interface-First
  [PRINCIPLE_3_NAME] → III. Content and Assets Are External Data
  [PRINCIPLE_4_NAME] → IV. Simplicity & YAGNI
  [PRINCIPLE_5_NAME] → V. Observability & Reproducibility

Added sections:
  [SECTION_2_NAME] → Asset Pipeline & Output Constraints
  [SECTION_3_NAME] → Development Workflow & Quality Gates
  (new) → Version Control & Change Flow

Removed sections: none

Companion artifacts (rules live here; formats live in files the tooling reads):
  CONTRIBUTING.md                    — commit format, branch naming, PR procedure
  .github/pull_request_template.md   — PR body scaffold carrying the merge gates
  .gitmessage                        — commit message template
  .gitignore                         — enforces the "never commit assets/output" rules

Changes from the uncommitted 1.0.0 draft:
  - Dropped the standalone "Print Fidelity" principle. Concrete print parameters are
    spec content, not governance. The verification discipline survives as a clause in
    Principle I; the numbers move to the feature spec.
  - Reversed the requirement that card metadata live in the repository. Metadata now
    MUST live in an external store so content ships without a deploy.
  - Generalized the asset adapter from storage-agnostic to storage- AND format-agnostic.
    Google Drive and TIFF are named only as the transitional beta state.
  - Reworked Principle I's deck-composition clause, which assumed in-repo deck data and
    contradicted the no-deploy content requirement. Tests now target resolution logic;
    content correctness is enforced by validation at ingest.

Deferred items:
  TODO(TECH_STACK): Language, web framework, and PDF/imaging library undecided.
    Resolve in the first /speckit-plan; amend as a MINOR bump once chosen.
  TODO(PRINT_SPEC): Carry these into the feature spec, not this document —
    card size 63.5 mm x 88.9 mm (2.5 in x 3.5 in) measured on the printed page;
    9-up (3x3) layout fitting US Letter and A4 without scaling; minimum 300 DPI at
    final print size with no upscaling; cut guides that do not intrude on card faces.
  TODO(ASSET_TARGET): Durable object-store backend and print/serving encodings are
    not yet chosen. Record in the plan that selects them.
-->

# Marchamp Proxy Builder Constitution

Marchamp Proxy Builder is a web application that assembles print-ready proxy PDFs for
Marvel Champions: The Card Game. A user selects a prebuilt hero deck, villain, modular
set, or scenario; the system gathers the corresponding card images from the external
asset store and emits print-ready PDFs that cut into a playable deck with no manual
assembly.

## Core Principles

### I. Test-First (NON-NEGOTIABLE)

Tests MUST be written before the implementation they cover, MUST be observed failing,
and MUST pass unmodified once the implementation lands. Red-Green-Refactor is enforced
in review: a pull request whose tests were authored after the code it verifies is
rejected regardless of coverage numbers.

Two consequences that are easy to skip and MUST NOT be:

- **Selection resolution is logic and MUST be tested.** The rules that turn a user's
  choice into a concrete list of card identifiers and quantities MUST have tests over
  representative fixtures. The fixtures stand in for content; they do not need to
  enumerate real decks.
- **Physically manifested output MUST be verified by automated assertion, never by
  inspection.** Page geometry, card placement, and effective resolution MUST be
  asserted against the values the active specification defines. A human looking at a
  PDF on screen is not verification, because the defect being guarded against only
  appears on paper.

This document deliberately does not state print dimensions, page sizes, or resolution
targets. Those are specification content and change per output format; the requirement
that they be asserted is what is constitutional.

### II. Interface-First

Every capability MUST be exposed through a documented, versioned HTTP API before any
UI consumes it. The web UI is a client of that API and MUST NOT reach around it into
internal modules or the data store.

- The API MUST be described by a machine-readable OpenAPI document generated from, or
  verified against, the running service — never hand-maintained in isolation.
- Endpoints MUST accept and return JSON, use stable resource identifiers for cards,
  decks, and scenarios, and treat PDF generation as an addressable resource rather
  than a side effect of a page render.
- The API MUST remain sufficient to drive the entire product without a browser, so
  that an MCP server or an autonomous agent can be layered on top without new
  application logic. Building such a layer is out of scope until asked for; keeping it
  possible is not.

Rationale: the assembly logic is the product and the browser is one consumer of it.
Binding that logic to a UI framework forecloses the agent and automation use cases this
project intends to support.

### III. Content and Assets Are External Data

The catalog is not part of the application. Cards, decks, villains, modular sets, and
scenarios are data the application reads; card images are binaries it fetches. Neither
is code, and neither MUST require a code change to grow.

- **Content ships without a deploy.** Adding or correcting a card, deck, or scenario
  MUST be possible by changing the content store alone. Any design that requires a
  release to publish new content violates this principle.
- **Content MUST be schema-validated at ingest,** and MUST NOT be trusted at
  generation time. Referential integrity — every card a deck references exists, every
  quantity is sane — MUST be checked before content becomes live, and MUST fail the
  ingest loudly rather than surfacing as a broken PDF later.
- **Content MUST be versioned and reversible.** A bad content change MUST be
  identifiable and rollable back without a code deploy, and MUST be attributable to a
  point in time so that a generated PDF can be traced to the content revision that
  produced it.
- **Storage backend and encoding format MUST be replaceable.** All asset reads go
  through a single adapter. Assembly logic MUST NOT know where a binary lives, what
  container or codec it arrived in, or which provider serves it. Changing the backend
  or the encoding MUST NOT touch assembly code.
- **Binary assets MUST NOT be committed to version control,** and MUST NOT be bundled
  into the deployed application.

Rationale: the beta reads TIFFs from Google Drive; the intended end state is a durable
object store with encodings chosen for hosting cost and print quality. That migration
is expected, so the seam it will move through is mandated up front rather than
retrofitted.

### IV. Simplicity & YAGNI

Build the smallest thing that satisfies the current specification.

- New dependencies, services, caches, queues, and abstraction layers MUST be justified
  in the pull request against a requirement that exists today. "We will need it later"
  is not a justification.
- Speculative configurability MUST be omitted. Prefer one correct default over a
  toggle.
- Duplication MUST be tolerated until the third occurrence; abstractions extracted
  from two examples are rejected by default.

The adapter seam required by Principle III is the one sanctioned exception, and its
scope is bounded: one interface, one implementation at a time. It is not license for a
plugin system.

### V. Observability & Reproducibility

- Every PDF generation request MUST emit a structured log record carrying a request
  identifier, the resolved selection, the card identifiers used, the content revision
  in effect, and the outcome.
- Failures MUST name the specific cause — which card identifier was missing, which
  asset failed to decode — and MUST NOT surface as a generic error to the user.
- Generation MUST be deterministic: the same selection against the same content
  revision and the same asset revision MUST produce a byte-identical PDF.
  Non-determinism (timestamps, nondeterministic iteration order, embedded generation
  dates) MUST be eliminated or explicitly normalized.

Rationale: determinism makes print output diffable and testable, and turns "this deck
printed wrong" into a reproducible bug rather than a report.

## Asset Pipeline & Output Constraints

**Source assets.** Card images are an external input to this system, never a part of
it. The beta reads TIFFs from a Google Drive; this is transitional and MUST NOT be
assumed anywhere outside the storage adapter. The target state is a durable object
store holding encodings selected for serving cost and print quality, plausibly
differing between the print path and any on-screen preview path.

- Missing or unreadable assets MUST fail loudly at generation time, naming the card.
  Silently substituting a placeholder or omitting a card is prohibited.
- Any derived rendition (transcode, resize, color conversion) MUST be reproducible
  from the source asset and MUST be treated as a cache, never as a source of record.
- TODO(ASSET_TARGET): the object-store backend and the chosen encodings are not yet
  decided. Record them in the plan that selects them and amend this section.

**Derived output.** Generated PDFs and any decoded or resized image cache are
disposable build products. They MUST be reproducible from source assets plus content
and MUST NOT be committed.

**Distribution scope.** The application serves proxy generation for a user's own
personal play. The project MUST NOT redistribute the card image library and MUST NOT
bundle card artwork into the deployed application or the repository. Access to source
assets is the operator's own.

**Technology.** TODO(TECH_STACK): Language, web framework, and PDF/imaging library are
not yet chosen. The choice MUST be recorded in the first implementation plan and this
section amended accordingly. Until then, no code may assume a stack that has not been
written down here.

## Development Workflow & Quality Gates

- Work follows the Spec Kit flow: `/speckit-specify` → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement`. Implementation MUST NOT begin before a plan
  exists.
- Every pull request MUST state which principles it engages and how it satisfies them.
  Complexity added under Principle IV MUST carry its justification in the PR
  description, not only in commit messages.
- The following gates MUST pass before merge:
  1. Full test suite green, including the output-geometry assertions required by
     Principle I.
  2. Content schema and referential-integrity validation green.
  3. API contract check green — the OpenAPI document matches the running service.
  4. No card images or generated PDFs added to version control.
  5. No storage backend, provider SDK, or image-format assumption outside the asset
     adapter.
- A change that cannot satisfy a gate MUST either be reduced in scope or accompanied by
  a constitution amendment. Gates MUST NOT be waived per-pull-request.

## Version Control & Change Flow

`main` is the trunk and MUST always be in a releasable state. This section states the
rules; their concrete formats live in `CONTRIBUTING.md` and the templates it references,
which are the authoritative source for exact syntax.

**Branching.**

- All work happens on a branch. Direct commits to `main` are prohibited, with a single
  exception: the repository bootstrap commit, which has no base to branch from and no
  remote to open a pull request against.
- Feature branches MUST be named for the Spec Kit feature they implement, matching the
  generated `specs/<feature>/` directory exactly (`NNN-short-name`). The tooling
  computes this name; it MUST NOT be improvised.
- Non-feature work MUST use a `type/short-name` branch, where `type` is drawn from the
  same vocabulary as commit types.
- Branches are short-lived. A branch that cannot merge within a few days SHOULD be
  split, not carried.

**Commits.**

- Commit messages MUST follow Conventional Commits. The type vocabulary and full format
  are defined in `CONTRIBUTING.md`.
- Subject lines MUST be imperative mood and MUST NOT exceed 72 characters.
- The body MUST explain *why* the change was made when the reason is not obvious from
  the diff. Restating the diff in prose is not a body.
- A commit MUST represent one logical change. Mixed-purpose commits MUST be split.
- Commits MUST NOT introduce secrets, credentials, card images, or generated output.
  `.gitignore` is a safety net, not the control.

**Pull requests.**

- Every change reaches `main` through a pull request. Self-merge is permitted for a
  solo maintainer, but the PR MUST still exist and its gates MUST still be checked —
  the record is the point.
- PR bodies MUST follow `.github/pull_request_template.md`, which carries the merge
  gates from *Development Workflow & Quality Gates* as an explicit checklist.
- A PR MUST be small enough to review in one sitting. Size is a review concern in its
  own right, and "it is all related" is not a defense.
- A PR that amends this constitution MUST change nothing else.

**History.**

- `main` history MUST be linear. Merge via squash or rebase; merge commits MUST NOT
  land on `main`.
- Force-pushing `main` is prohibited. Force-pushing your own unmerged branch is
  permitted and MUST use `--force-with-lease`.

## Governance

This constitution supersedes conflicting practices, conventions, and prior guidance.
Where a tool default, template, or habit conflicts with a principle here, the principle
wins.

**Scope.** This document governs how the project is built, not what any feature does.
Concrete parameters — dimensions, formats, page sizes, endpoint shapes, schemas —
belong in specifications. If a rule proposed for this document would change when a
feature changes, it belongs in a spec instead.

**Amendments.** Any change to this document MUST be proposed as a pull request that
states the rationale, the version bump and its justification, and the migration path
for any work already in flight. Amendments take effect on merge.

**Versioning.** This document is versioned semantically:

- **MAJOR** — a principle is removed or redefined in a way that invalidates existing
  compliant work.
- **MINOR** — a principle or section is added, or existing guidance is materially
  expanded.
- **PATCH** — clarification, wording, or typo fixes that do not change what is
  required.

**Compliance.** Reviewers MUST verify compliance as part of every code review; an
approval asserts that the gates above were checked. Principles marked NON-NEGOTIABLE
MUST NOT be suspended for expedience — the correct response to a blocking
NON-NEGOTIABLE principle is to amend this constitution deliberately, or to change the
work.

**Version**: 1.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-07-31
