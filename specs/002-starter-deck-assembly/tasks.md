---

description: "Task list for Hero Pack Printing from a Scan Library"
---

# Tasks: Hero Pack Printing from a Scan Library

**Input**: Design documents from `/specs/002-starter-deck-assembly/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/openapi.yaml](./contracts/openapi.yaml),
[ADR 0001](../../docs/adr/0001-durable-run-state-on-the-filesystem.md)

**Tests**: **MANDATORY, not optional.** The template treats tests as opt-in; the project
constitution's Principle I (Test-First, NON-NEGOTIABLE) overrides that. Every test task below
MUST be written, run, and **observed failing** before the implementation task it covers, and MUST
pass unmodified afterwards. A pull request whose tests were authored after the code is rejected
in review regardless of coverage.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5, matching spec.md user stories
- Exact file paths are given in every task

## Path Conventions

Single Python project per plan.md: `src/marchamp/` and `tests/` at repository root. Four new
packages — `upstream/`, `library/`, `assembly/`, `store/` — plus changes to `assets/`, `catalog/`,
`render/`, `api/`, `config.py`, and `web/`.

## Two things to know before starting

- **`card_directory/` is gitignored and no card art or MarvelCDB card text may ever be
  committed** (FR-038a). Every fixture image is *generated*; every fixture snapshot is *reduced*.
  T007 is the mechanical guard, and it is not optional.
- **`store/atomic.py` (T013) is load-bearing code, not plumbing.** ADR 0001's dissenting
  reviewers accepted plain files only on the condition that the fsync-ordering helper be reviewed
  as the crash-atomicity mechanism it is — no test exercises power loss, and the directory
  `fsync` is the line everyone omits.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, source tree, and the fixture library every later phase asserts against

- [ ] T001 Promote `httpx` from `[dependency-groups] dev` to `[project] dependencies` and add `python-multipart` in `pyproject.toml` (research R2, R9)
- [ ] T002 Regenerate `uv.lock` and confirm `uv sync --locked` fails if the lockfile would change
- [ ] T003 Create source tree `src/marchamp/{upstream,library,assembly,store}/` with `__init__.py` in each
- [ ] T004 Write `scripts/derive_library_fixture.py` — reads the real library with `Path.rglob` (BSD `find` does not traverse the Drive mount, research R13) and writes filenames and folder layout over **generated** placeholder images, covering the ten hero folders, the Core Set folder, and the `Aspects/` subtree
- [ ] T005 Run T004 and commit `tests/fixtures/library/` for the ten acceptance heroes **plus the Core Set folder and the `Aspects/` subtree** — without the first the reprint path has no image to borrow (T043, T058), and without the second the whole-library search has nothing to find (T079). Preserve the real awkwardness verbatim: the three filename conventions, the typos, missing positions, `.tif`/`.tiff` pairs, Ant-Man's duplicate position, Quincarrier filed under Wasp, and the decklist scans **under their real filenames** (`captain america decklist.tif`, `iceman deck list.tiff` — both spellings must survive derivation) with Hulk's and Phoenix's folders left without one
- [ ] T006 [P] Commit reduced upstream fixtures in `tests/fixtures/snapshots/` for the ten packs plus `core`, carrying only the fields in data-model.md § PackCard (FR-038a)
- [ ] T007 [P] Write `tests/unit/test_fixtures_carry_no_card_data.py` asserting no fixture holds card text, flavour, traits, `imagesrc`, or a real image — this repository is public and FR-038a governs fixtures as much as runtime
- [ ] T008 [P] Extend `tests/conftest.py` with a temporary state directory, a fixture `library_root`, and an offline `httpx` transport that serves the T006 fixtures and fails on any unstubbed host

**Checkpoint**: `uv run pytest` green, and T007 proves the fixtures are clean.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Durable state, the outbound client, and the library reader — shared by every story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### The contract test must merge two documents first

- [ ] T009 Change `tests/contract/test_openapi_matches.py` to load **both** `specs/001-*/contracts/openapi.yaml` and `specs/002-*/contracts/openapi.yaml`, union their `paths` and `components`, and compare that union against the live document. Today it compares 001's file alone with `set(live["paths"]) == set(contract["paths"])`, so the first 002 route breaks CI. Observe it fail (002's paths are absent from the live app) — that failure is the red state every route task below turns green.

### Configuration

- [ ] T010 Write failing tests for `MARCHAMP_STATE_DIR` resolution, the platform default, and refusal when it resolves inside a named library root, in `tests/unit/test_config.py` (data-model.md § Configuration)
- [ ] T011 Extend `src/marchamp/config.py` with the state directory, the upstream host, the upload byte ceiling, the library scan file-count cap, and backoff settings — and confirm `serve` still starts with `MARCHAMP_IMAGE_DIR` and `MARCHAMP_CATALOG` unset (FR-005, SC-003a)

### Durable state (ADR 0001)

- [ ] T012 Write failing tests for atomic replace, file `fsync` before rename, directory `fsync` after it, and `F_FULLFSYNC` on Darwin, in `tests/unit/test_atomic.py`
- [ ] T013 Implement `src/marchamp/store/atomic.py`. **Flag this for review as load-bearing**, per ADR 0001's dissent
- [ ] T014 [P] Write failing tests for state-directory path construction in `tests/unit/test_store_layout.py`
- [ ] T015 Implement `src/marchamp/store/layout.py` — `runs/<id>/run.json`, `runs/<id>/uploads/<sha256>`, `pdfs/standard/`, `pdfs/saved/`, `snapshots/<pack>.json`
- [ ] T016 Write failing tests for run-record round-trip, the optimistic `version` (stale write rejected, not silently applied), a per-run lock, and **refusal** of a record written by a newer `schema_version`, in `tests/unit/test_store_runs.py` (FR-026b)
- [ ] T017 Implement `src/marchamp/store/runs.py`
- [ ] T018 Write failing tests for standard vs saved PDFs, `os.link` refcounting, `EEXIST` as the atomic uniqueness primitive for the FR-026h key, and that deletion returns bytes **to the operating system**, in `tests/unit/test_store_pdfs.py` (FR-026g, FR-026g1)
- [ ] T019 Implement `src/marchamp/store/pdfs.py`
- [ ] T020 [P] Write failing test for the startup orphan sweep in `tests/unit/test_store_sweep.py` (ADR 0001 § Consequences)
- [ ] T021 Implement `src/marchamp/store/sweep.py` and call it from `src/marchamp/api/app.py` at startup

### Asset adapter: two roots, and 001 moved behind the seam

- [ ] T022 Write failing tests for `OverlayStore` — `upload:`-prefixed refs resolve inside the run directory, everything else inside the library root, each with its own containment check, and the store pickles across a process boundary — in `tests/unit/test_overlay.py` (FR-004, FR-007, FR-026e)
- [ ] T023 Implement `src/marchamp/assets/overlay.py`
- [ ] T024 Change `compose()` in `src/marchamp/render/document.py` to take an `assets.Store` instead of `image_dir: Path`; 001's tests MUST pass unmodified (research R8)
- [ ] T025 Change `validate_source()` in `src/marchamp/render/images.py` to take a `Store` and a ref
- [ ] T026 [P] Change `src/marchamp/catalog/printings.py` and `src/marchamp/catalog/validation.py` to reach files through the `Store` rather than joining `image_dir / ref`
- [ ] T027 Update the call sites in `src/marchamp/generations/service.py` and `src/marchamp/api/routes.py` to construct a `LocalDirectoryStore` — feature 001's behaviour is unchanged, and its suite is the proof

### Upstream: MarvelCDB

- [ ] T028 Write failing tests for snapshot validation on capture **and on read** — every retained field present and typed, `pack_code` consistent, at least one `type_code: hero`, at least one `card_set_type_name_code: nemesis`, `quantity` ≥ 1, dangling reprint link a warning — in `tests/unit/test_upstream_models.py` (FR-047)
- [ ] T029 Implement `src/marchamp/upstream/models.py` — `PackIndexEntry` (`code`, `name` only) and `PackCard`, discarding card text, flavour, traits, `imagesrc`, and `pack.total` (research R12)
- [ ] T030 Write failing tests for the client — one allowlisted host, redirects **not** followed, loopback/link-local/private ranges refused after resolution, `pack_code` validated against `^[a-z0-9_]{1,32}$` and against the pack index before reaching a URL, descriptive `User-Agent`, explicit timeouts, `Retry-After`-aware backoff with at most two retries, never more than one request in flight and never two requests inside 1 s — in `tests/unit/test_upstream_client.py` (FR-003, FR-041, FR-042, FR-043)
- [ ] T031 Implement `src/marchamp/upstream/client.py`
- [ ] T032 Write failing tests for the snapshot store — revision is a content hash of the reduced records and is stable across a refetch that changed nothing; within `max-age` **no request is issued at all**; past it one conditional `If-Modified-Since`; a `304` keeps the revision and extends freshness; a failed refetch serves the stored snapshot marked stale; no snapshot and a failed fetch refuses naming the pack — in `tests/unit/test_snapshots.py` (FR-039, FR-044, FR-044a, FR-046, research R1, R10)
- [ ] T033 Implement `src/marchamp/upstream/snapshots.py`

### Reading the library

- [ ] T034 Write failing tests for the three filename conventions, per-folder detection of the copy-counting form, the `a`/`b` suffix being ambiguous between the two face mechanisms, and unparseable names, in `tests/unit/test_filenames.py` (FR-032, research R5, R12)
- [ ] T035 Implement `src/marchamp/library/filenames.py`
- [ ] T036 Write failing tests for index construction — `(pack_hint, position, suffix)` and normalised-name maps, `pack_hint` absent under `Aspects/`, and normalisation matching each of the three observed typos ("Stength in Numbers", "Steve_s Apartament", "Upgarde") at the data-model's edit-distance bound, plus a case where two files fall inside the bound for one card and the result is a **conflict** rather than a pick — in `tests/unit/test_library_index.py` (FR-021, FR-023, FR-033, research R5, R13)
- [ ] T037 Implement `src/marchamp/library/index.py` with one `os.walk` per resolve pass, bounded by the T011 file-count cap, never persisted

### Faces and groups

- [ ] T038 Write failing tests for face expansion under **both** mechanisms — linked codes (`cap` `03001a`→`03001b`), the `double_sided` flag (`vision` `26002` Intangible), and Ant-Man's two records at position 1 giving three faces — plus group classification and the cards-vs-faces counts, in `tests/unit/test_faces.py` (FR-015, FR-015a, FR-015b, FR-015f, FR-018)
- [ ] T039 Implement `src/marchamp/assembly/faces.py`

**Checkpoint**: state survives a restart, the client is provably contained, and the library and
the snapshot can each be read on their own. User story work can begin.

---

## Phase 3: User Story 1 — Print a hero's whole pack (Priority: P1) 🎯 MVP

**Goal**: Point the tool at a hero folder and receive the entire pack print-ready — every card in
the pack's quantities, the identity card with every face, the nemesis set, and the decklist card —
as one PDF, with no catalog authored by hand.

**Independent test**: Point the tool at `Heros/Steve Rogers_Captain America/` in the fixture
library with no catalog present. It succeeds when every card the `cap` pack contains is printed in
the pack's quantities — including the eight physical cards sourced from the Core Set — together
with the identity card, the nemesis set, and the decklist card.

### Identifying the pack

- [ ] T040 [US1] Write failing tests for pack ranking against the pack index, the confidence figure, the evidence list, and refusal below threshold routing to selection rather than ending the run, in `tests/unit/test_identify.py` (FR-010, FR-011, FR-012)
- [ ] T041 [US1] Implement `src/marchamp/library/identify.py` — rank the 61 pack names from the index, then verify against that one pack's cards (two requests to identify and verify; the packs a reprint points at are fetched later, research R3, R4)
- [ ] T042 [US1] Calibrate the FR-011 threshold against all ten acceptance heroes and **record the chosen number in data-model.md § Pack Identification**. Phoenix and Wonder Man carry no usable positions and must clear it on name matches alone; a threshold only the easy folders clear is worse than none

### Resolving and composing

- [ ] T043 [US1] Write failing tests for cascade step 1 (`folder_position`) and step 3 (`reprint`), following `duplicate_of_code` and `duplicated_by` in both directions and wherever they point — not only to the Core Set — in `tests/unit/test_resolve.py` (FR-014, FR-020, FR-022, FR-024)
- [ ] T044 [US1] Implement cascade steps 1 and 3 in `src/marchamp/assembly/resolve.py`, recording provenance and a content digest per resolution
- [ ] T045 [US1] Write failing test that copy counts come from the pack being printed and never from the printing an image was borrowed from — `cap` `03016` Make the Call prints twice whatever the Core Set ships — in `tests/unit/test_resolve.py` (FR-016, US1 scenario 4)
- [ ] T046 [US1] Write failing test for the bridge to feature 001's structures: pack plus resolutions to an in-memory `Catalog` and one `HeroDeck`, entries ordered `(group, position, code)`, in `tests/unit/test_assembly_catalog.py` (FR-048)
- [ ] T047 [US1] Implement `src/marchamp/assembly/catalog.py`. The synthesised catalog is in memory only and is never written to disk
- [ ] T048 [US1] Write failing test that the PDF carries the groups in order, packed into the fewest pages the card count allows, with **no page break between groups**, in `tests/integration/test_pack_pdf.py`. Four groups for a hero whose folder holds a decklist scan and three for Hulk or Phoenix, which hold none (FR-013c, FR-015d, SC-002a, SC-002b)

### The decklist card

The decklist is US1's, not US4's: without it the MVP prints a pack the user cannot build the
starter deck from, which is the whole point of printing packs. US4 keeps only the
download-from-Hall-of-Heroes upload for folders that hold no scan.

- [ ] T048a [US1] Write failing tests for decklist detection in `tests/unit/test_decklist.py` — **both** observed spellings (`captain america decklist.tif`, `iceman deck list.tiff`) and all three extensions; the hero name in the filename **not** required to match the folder's; one candidate proposed and **not** printed until accepted; a `.tif`/`.tiff` pair of one stem treated as a single candidate resolved deterministically (FR-034) rather than prompting; two candidates with **different** stems reported as a conflict the user resolves (FR-033); zero candidates reported as FR-013c's gap, which is Hulk's and Phoenix's real case; and a matched candidate excluded from **both** the unused-file and uninterpretable lists — no decklist filename matches any of the three conventions, so without the exclusion every one of them is an FR-032 report (FR-013d, FR-031, FR-032)
- [ ] T048b [US1] Implement decklist detection — the `decklist_candidates` entry in `src/marchamp/library/index.py` and the `decklist_name` cascade step in `src/marchamp/assembly/resolve.py`, carrying the pseudo-code `decklist`. It never enters the FR-020–FR-025 cascade proper
- [ ] T048c [US1] Write failing contract test for the `DecklistDecision` half of `POST /api/assemblies/{run_id}/decklist` — `confirm`, `select` with a library-relative `ref`, and `skip` — and a test that `confirm` leaves the run **uncustomized** so it still produces the pack's standard PDF while `select` and `skip` do not, in `tests/contract/test_assembly_contract.py`. Were acceptance itself customization, no run would ever be standard and reuse would never fire (FR-013d, FR-013e, FR-026h, FR-026i)
- [ ] T048d [US1] Implement the decision route in `src/marchamp/api/routes.py`, the `decklist_candidate` field on the run, the hold in `awaiting_cards` while it is undecided, and the `decklist_printed` / `decklist_source_url` fields in `src/marchamp/assembly/report.py` (FR-013b, FR-013d, FR-013e, SC-006j)

### The run as a resource

- [ ] T049 [US1] Write failing tests for the run lifecycle — `identifying` → `awaiting_pack` / `unidentified` → `resolving` → `awaiting_cards` / `ready` → `rendering` → `complete` / `failed`, that **nothing resolves before the pack is confirmed**, and that `ready` does not print by itself — in `tests/unit/test_assembly_service.py` (FR-012a, FR-026a, SC-009)
- [ ] T050 [US1] Implement `src/marchamp/assembly/service.py`
- [ ] T051 [US1] Write failing contract tests for `POST /api/assemblies`, `GET /api/assemblies/{run_id}`, `GET /api/assemblies/{run_id}/packs`, `POST /api/assemblies/{run_id}/pack`, `POST /api/assemblies/{run_id}/confirmation`, and `GET /api/assemblies/{run_id}/document` in `tests/contract/test_assembly_contract.py`, including `If-Match` and the `409` on a stale version
- [ ] T052 [US1] Add the request and response models from contracts/openapi.yaml to `src/marchamp/api/schemas.py`
- [ ] T053 [US1] Implement those routes in `src/marchamp/api/routes.py`, with both named paths validated when named and refused specifically (FR-006), and T009 now green for them
- [ ] T054 [US1] Write failing test that a user-selected pack is recorded as such and is **not** customization under FR-026i, in `tests/integration/test_pack_selection.py` (FR-012b, SC-009a)

### Reuse

- [ ] T055 [US1] Write failing tests for the FR-026h key — served when pack, snapshot revision, and resolved image identity all match; **rebuilt** when the snapshot is refreshed; **rebuilt** when one card resolves to different bytes; **still served** when the library folder has moved and every image resolves identically — in `tests/integration/test_reuse.py` (SC-006i, SC-006k, SC-006h)
- [ ] T056 [US1] Implement `image_identity` in `src/marchamp/assembly/resolve.py` and the reuse decision in `src/marchamp/assembly/service.py` against `src/marchamp/store/pdfs.py`. A run resolves before it can decide: reuse skips the render, not the resolve

### Interface

- [ ] T057 [US1] Extend `src/marchamp/web/index.html`, `app.js`, and `styles.css` — name the library root and hero folder, show the identified pack with its evidence and wait for confirmation, show the proposed decklist card and wait for acceptance or a different pick (FR-013d), show progress, offer the download
- [ ] T058 [US1] Write the end-to-end integration test for `cap` over the fixture library in `tests/integration/test_assemble_cap.py` — every card resolved, the eight Core Set reprints recovered, one PDF, `MARCHAMP_IMAGE_DIR` and `MARCHAMP_CATALOG` unset throughout (SC-003a)

**Checkpoint**: a user can print one hero's whole pack from a folder they name, with nothing
configured. This is the MVP.

---

## Phase 4: User Story 2 — Be told exactly what could not be resolved (Priority: P1)

**Goal**: A run that cannot resolve every card says which are missing and where it looked, rather
than producing a pack that is quietly short.

**Independent test**: Print a hero whose folder omits a pack card that exists in no other
printing. It succeeds when the run stops, names that card, and prints nothing.

**Note**: shares P1 with US1 because it is the other half of the same feature — with no deck total
to check against, the report is the *only* thing that can tell the user a pack is short.

- [ ] T059 [US2] Write failing tests for the report model and every section in data-model.md § Assembly Report, in `tests/unit/test_report.py`
- [ ] T060 [US2] Implement `src/marchamp/assembly/report.py`
- [ ] T061 [US2] Write failing tests that a card resolving to no image stops the run by name — including a **nemesis** card and a **missing back face**, held to exactly the same bar as a missing front — and that no PDF is written, in `tests/integration/test_incomplete.py` (FR-015c, FR-015f, FR-017, FR-025, SC-006)
- [ ] T062 [US2] Implement the completeness check in `src/marchamp/assembly/service.py`
- [ ] T063 [US2] Write failing test that cards printed are reported against the number the pack listing records, **in cards**, with the face count alongside, and that no run reports an expected total or warns on one, in `tests/unit/test_report.py` (FR-018, FR-019, SC-006a)
- [ ] T064 [US2] Implement the counts in `src/marchamp/assembly/report.py`, taking the face count from `src/marchamp/assembly/faces.py`
- [ ] T065 [US2] Write failing test that 100% of files in the **hero folder** are either used or named as unused with a reason, and that files elsewhere under the library root appear only when used or in conflict, in `tests/integration/test_file_accounting.py` (FR-031, SC-004)
- [ ] T066 [US2] Implement file accounting in `src/marchamp/assembly/report.py`, using the hero-folder entries from `src/marchamp/library/index.py`
- [ ] T067 [US2] [P] Write failing tests for position conflicts naming both sides and resolved by neither, duplicate `.tif`/`.tiff` renditions naming which was chosen deterministically, and uninterpretable filenames within the hero folder, in `tests/unit/test_report.py` (FR-032, FR-033, FR-034)
- [ ] T068 [US2] Implement conflict and duplicate reporting in `src/marchamp/assembly/report.py` and the deterministic rendition choice in `src/marchamp/library/index.py`
- [ ] T069 [US2] [P] Write failing test that a scan below the print-resolution floor is a **warning, not a refusal**, in `tests/unit/test_report.py` (FR-035)
- [ ] T070 [US2] Implement the low-resolution warning in `src/marchamp/assembly/report.py`, reading the floor from `src/marchamp/render/images.py`
- [ ] T071 [US2] Write failing test that `outcome` is `clean`, `warnings`, or `refused` and is **null until terminal**, so awaiting confirmation or waiting on a card is distinguishable from a failure, in `tests/unit/test_assembly_service.py` (FR-036)
- [ ] T072 [US2] Implement the outcome field in `src/marchamp/assembly/service.py` and expose it in `src/marchamp/api/schemas.py`
- [ ] T073 [US2] Write failing test that every failure names the specific card or file at fault and never a generic error, in `tests/unit/test_report.py` (FR-037, SC-008)
- [ ] T074 [US2] Render the report in `src/marchamp/web/app.js`, grouped so the user can sort cut cards without recognising them by sight (FR-015e)

**Checkpoint**: no pack is ever quietly short, and the report says which card and where it looked.

---

## Phase 5: User Story 3 — Find a card that is not where it should be (Priority: P2)

**Goal**: A pack card that lives in another hero's folder, or under `Aspects/`, is found anyway.

**Independent test**: Print Black Widow, whose `Quincarrier` is filed under Wasp. It succeeds when
the card is found and every pack card resolves.

- [ ] T075 [US3] Write failing tests for cascade step 2 (`library_position`, anywhere under the library root) and step 4 (`name`, matched only against the canonical name of the specific card being sought), in `tests/unit/test_resolve.py` (FR-021, FR-023)
- [ ] T076 [US3] Implement cascade steps 2 and 4 in `src/marchamp/assembly/resolve.py`
- [ ] T077 [US3] Write failing test that a card found outside the hero folder has its origin named, and a name match is reported **as a name match**, so a wrong match is visible rather than invisible, in `tests/unit/test_resolve.py` (FR-024, SC-005, US3 scenario 3)
- [ ] T078 [US3] Implement the provenance reporting for steps 2 and 4 in `src/marchamp/assembly/resolve.py` and `src/marchamp/assembly/report.py`
- [ ] T079 [US3] [P] Write the integration test for Black Widow (`Quincarrier` under Wasp) and Thor (`Teamwork` under `Aspects/Leadership/`) in `tests/integration/test_whole_library_search.py` (SC-003)
- [ ] T080 [US3] Write the integration test for Phoenix and Wonder Man in `tests/integration/test_name_fallback.py` — both use the copy-counting convention and carry no usable positions, so this is the acceptance case for the name path as the *primary* route rather than a safety net (SC-003c)

**Checkpoint**: every acceptance hero resolves completely, including the two that positional
matching cannot help at all.

---

## Phase 6: User Story 4 — Supply the last few cards by hand (Priority: P2)

**Goal**: Where automatic resolution fails, the user picks a file for that specific card
themselves, rather than being told the run failed and left to work out why.

**Independent test**: Assemble a hero whose library is missing one card. It succeeds when the tool
names that card, accepts a file the user chooses for it, and prints the pack.

- [ ] T081 [US4] Write failing contract test for `POST /api/assemblies/{run_id}/cards/{card_code}/image` in `tests/contract/test_assembly_contract.py`, including the `side` field for a double-sided card
- [ ] T082 [US4] Implement the upload route in `src/marchamp/api/routes.py`, streaming to a temporary file under the T011 byte ceiling **before** decode, then storing under the content SHA-256 in `runs/<id>/uploads/`
- [ ] T083 [US4] Write failing tests that an upload is rejected with a specific reason when it is not a decodable image or is below the print-resolution floor, and that the card **remains unresolved**, in `tests/integration/test_upload.py` (FR-028)
- [ ] T084 [US4] Implement upload validation in `src/marchamp/api/routes.py` by reusing `validate_source` from `src/marchamp/render/images.py` — manual choice bypasses discovery, never validation
- [ ] T085 [US4] Write failing tests that a manual resolution is distinguishable from every automatic one, and that **only the uploaded file's own name** is recorded — no path from outside the named library root reaches the report or the log — in `tests/integration/test_upload.py` (FR-027, FR-029, SC-006c)
- [ ] T086 [US4] Implement manual provenance recording in `src/marchamp/assembly/resolve.py` and `src/marchamp/store/runs.py`
- [ ] T087 [US4] Write failing tests that a run resolved with an uploaded file still prints that card after the source file is moved or deleted on disk, because the run holds the bytes, in `tests/integration/test_upload.py` (FR-026e, SC-006b, US4 scenario 4)
- [ ] T088 [US4] Write failing contract test for `POST /api/assemblies/{run_id}/cards/{card_code}/omission`, asserting the explicit `acknowledged` flag and the **`409` when the run has not yet reported which cards are unresolved**, in `tests/contract/test_assembly_contract.py` (FR-030, FR-030a)
- [ ] T089 [US4] Implement the omission route in `src/marchamp/api/routes.py` and its state guard in `src/marchamp/assembly/service.py`. A blanket permission offered up front is refused rather than honoured, and the run still stops on the first card it cannot resolve
- [ ] T090 [US4] Write failing test that an omitted card is named in the report, counted against the pack listing's card count, and written to the run's log, in `tests/integration/test_incomplete.py` (FR-030b, SC-006e)
- [ ] T091 [US4] Implement omission reporting in `src/marchamp/assembly/report.py` and the log record in `src/marchamp/observability/logging.py`
- [ ] T092 [US4] Write failing contract test for the **upload** half of `POST /api/assemblies/{run_id}/decklist`, and a test that a hero folder with no decklist scan — Hulk's and Phoenix's real case — names the gap and offers the Hall of Heroes address while the application **never fetches it**, in `tests/integration/test_decklist.py` (FR-013c, SC-006j)
- [ ] T093 [US4] Implement the decklist upload path in `src/marchamp/api/routes.py`, reusing T084's validation. Detection, the decision endpoint, and the report fields are US1's (T048a–T048d); a missing decklist never refuses the run
- [ ] T094 [US4] Extend `src/marchamp/web/app.js` to present each unresolved card individually with an upload control and an explicit omit action — never a failed run the user must diagnose (FR-026d)
- [ ] T095 [US4] Write failing test that supplying a file for the first of two unresolved cards keeps the folder, the pack, and every earlier choice, and asks only about the second, in `tests/integration/test_upload.py` (US4 scenario 8)

**Checkpoint**: no card the user can point at is unprintable.

---

## Phase 7: User Story 5 — Put a deck down and pick it up later (Priority: P2)

**Goal**: A user who cannot finish resolving a pack now saves it and comes back to it on a later
visit, finding it where they left it rather than starting again.

**Independent test**: Start an assembly that cannot resolve two cards, save it, restart the
application, and return. It succeeds when the run is listed as unfinished and resumes with the
folder, the pack, and the first card's resolution intact.

- [ ] T096 [US5] Write failing test that a run with cards unresolved survives an application restart and resumes with its library root, hero folder, confirmed pack, pinned snapshot revision, resolutions, and report intact, in `tests/integration/test_resume.py` (FR-026b, SC-006f)
- [ ] T097 [US5] Implement resume in `src/marchamp/assembly/service.py`
- [ ] T098 [US5] Write failing contract test for `GET /api/assemblies` distinguishing finished, waiting-on-a-card, and awaiting-confirmation runs without the caller recording an identifier, in `tests/contract/test_assembly_contract.py` (FR-026c, SC-006g)
- [ ] T099 [US5] Implement the list route in `src/marchamp/api/routes.py`
- [ ] T100 [US5] Write failing test that a resumed run whose library folder has moved or been unmounted reports that **against the run**, naming the folder — not as a wave of newly missing cards — and that a *finished* run downloads its PDF regardless, in `tests/integration/test_resume.py` (FR-026f, SC-006h)
- [ ] T101 [US5] Implement the moved-folder report in `src/marchamp/assembly/service.py`, checked on resume rather than during resolution
- [ ] T102 [US5] Write failing test that a resumed run keeps the snapshot revision it started with, so an explicit refresh cannot silently change composition or quantities under resolutions already made, in `tests/integration/test_snapshots.py` (FR-044b, FR-045)
- [ ] T103 [US5] [P] Write failing contract tests for `DELETE /api/assemblies/{run_id}`, `GET /api/pdfs`, `DELETE /api/pdfs/{pdf_id}`, and `GET /api/pdfs/{pdf_id}/document` in `tests/contract/test_pdfs_contract.py`
- [ ] T104 [US5] Implement those routes in `src/marchamp/api/routes.py`
- [ ] T105 [US5] Write failing tests that deleting a run reclaims **only** its uploads and a saved PDF it named, that a standard PDF survives and other runs still download it, and that deleting a standard PDF from the stored-PDF list reclaims the space and the next assembly rebuilds, in `tests/integration/test_retention.py` (FR-026g, FR-026g1, US5 scenarios 6, 6a, 6b)
- [ ] T106 [US5] Implement deletion in `src/marchamp/store/pdfs.py` and `src/marchamp/store/runs.py`. Assert the **freed bytes**, not just the absent file, and never touch the scan library (FR-001)
- [ ] T107 [US5] Write failing contract test that `save_as` is required when a run was customized and forbidden when it was not, in `tests/contract/test_assembly_contract.py` (FR-026h, FR-026i, US5 scenario 7)
- [ ] T108 [US5] Implement the standard-versus-saved decision in `src/marchamp/assembly/service.py`, tracking a `customized` flag on the run in `src/marchamp/store/runs.py`
- [ ] T109 [US5] Extend `src/marchamp/web/app.js` with the run list and the stored-PDF list, showing total bytes so reclaiming is an informed choice
- [ ] T110a [US5] Write the failing contract test for `GET` and `POST /api/packs/{pack_code}/snapshot` in `tests/contract/test_packs_contract.py`
- [ ] T110b [US5] Implement both in `src/marchamp/api/routes.py`, so FR-044b's manual refresh is reachable without a browser

**Checkpoint**: no user who leaves the wizard loses work, and storage grows only with PDFs they
chose to keep.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T111 Write the determinism test in `tests/integration/test_determinism.py` — assemble twice from the same library and snapshot **with reuse disabled** and compare bytes. Serving a stored PDF twice proves nothing, and FR-045 requires this to be verifiable independently of FR-026h (SC-007)
- [ ] T112 [P] Write the egress hardening test in `tests/integration/test_egress.py` — no request to any host other than `marvelcdb.com`, **every request path one of the three allowlisted JSON endpoints**, no response body consumed as image bytes, and `imagesrc` absent from every captured snapshot; plus no redirect followed, private and link-local ranges refused after resolution, and the `User-Agent` naming the application. The host allowlist alone cannot discharge FR-002 — MarvelCDB serves card art from the same host (FR-002, FR-003, FR-041, FR-038a, constitution egress gate)
- [ ] T113 [P] Write the request-count test in `tests/integration/test_snapshots.py` — assembling `cap` issues **three** requests (the pack index, `cards/cap`, and `cards/core` for its seven reprint links) and not 34, so the count follows the number of *distinct packs referenced* and never the card count; and a second run against a snapshot still inside `max-age` issues **zero** (FR-040, SC-006d, research R4)
- [ ] T114 [P] Extend `src/marchamp/observability/logging.py` with the assembly run record — pack, identified or user-selected, snapshot revision, resolutions with provenance, omissions, outcome — and test that it carries no path from outside the named library root (FR-009, FR-030b, Principle V)
- [ ] T115 Write the acceptance test for all ten heroes over the fixture library in `tests/integration/test_acceptance_heroes.py`, asserting that Hulk and Phoenix report the FR-013c gap with the Hall of Heroes address and still print, while the other eight print a decklist card — a run over Hulk that reported a decklist card would be silently wrong (SC-002, SC-002a, SC-003, SC-003c, SC-006j)
- [ ] T116 Write `specs/002-starter-deck-assembly/physical-uat.md` and the `physical`-marked test in `tests/integration/test_physical_pack.py` covering quickstart V12 — print, cut, sort from the report alone, build the starter deck from the printed decklist card, play it. Record the finished PDF's byte size and the wall-clock time from naming the folder to holding the PDF, against SC-001's five minutes of user time — the one criterion no automated test can carry (SC-001, SC-002a, SC-002b)
- [ ] T120 [P] Write the library-immutability test in `tests/integration/test_library_readonly.py` — capture the library root's file set, sizes, and mtimes, drive a full run through it (identify, confirm, upload for one card, omit another, render, then delete the run), and assert every one of them unchanged. The library is a synced Drive folder, which is what makes this the highest-consequence guarantee in the feature (FR-001, FR-008)
- [ ] T121 Write the `physical`-marked real-library acceptance test in `tests/integration/test_real_library.py` — the ten heroes against the mounted Drive folder, local only, never in CI. This is SC-002/SC-003's acceptance evidence; T115's fixture run is the regression guard, not a substitute (SC-003b)
- [ ] T117 [P] Update `CLAUDE.md` — feature 002's state, the new packages, `MARCHAMP_STATE_DIR`, that `MARCHAMP_IMAGE_DIR`/`MARCHAMP_CATALOG` are not required for the 002 paths, and that `SC-007` names 001's render target and 002's determinism criterion, which are different things
- [ ] T118 Run `uv run ruff check . && uv run ruff format --check .` and `uv run pytest -m "not physical"` — both clean
- [ ] T119 Write the security review notes for the PR body. The constitution requires **written** notes, not a checked box, when a change touches an outbound network call, image or PDF parsing, the asset adapter, the content store, or dependency additions — this change touches all five

---

## Dependencies & Story Completion Order

```
Phase 1 Setup
      │
      ▼
Phase 2 Foundational ── T009 contract-test merge gates every route task
      │                 T013 atomic.py gates T017/T019 (review as load-bearing)
      │                 T024–T027 refactor gates every render path
      ▼
Phase 3 US1 (P1) ──────────────► MVP: one hero's pack, printable
      │
      ▼
Phase 4 US2 (P1) ──────────────► the other half: nothing is ever quietly short
      │
      ├──► Phase 5 US3 (P2) ──► every acceptance hero resolves
      │
      ├──► Phase 6 US4 (P2) ──► no card the user can point at is unprintable
      │
      └──► Phase 7 US5 (P2) ──► no work is lost, storage is reclaimable
                  │
                  ▼
            Phase 8 Polish
```

**Story independence**: US3, US4, and US5 are independent of one another and can be built in any
order once US1 and US2 are done. US2 depends on US1 only because the report needs something to
report on. US1 depends on the whole of Phase 2.

**One coupling worth naming**: US4's upload path and US5's durability share the run store, so
whichever is built second gets its tests nearly free — but neither blocks the other.

---

## Parallel Execution Examples

**Phase 1** — after T003, these are independent files:

```
T006  reduced snapshot fixtures
T007  the no-card-data guard test
T008  conftest additions
```

**Phase 2** — after T011, three tracks touch disjoint packages:

```
Track A (durable state):  T012 → T013 → T014/T015 → T016/T017 → T018/T019 → T020/T021
Track B (upstream):       T028 → T029 → T030 → T031 → T032 → T033
Track C (library):        T034 → T035 → T036 → T037, then T038 → T039
```

`T026` is `[P]` against `T024`/`T025` — different modules, same refactor.

**Phase 4** — `T067` and `T069` are `[P]`: both add cases to `tests/unit/test_report.py` in
different sections, and neither depends on the other's implementation task.

**Phase 8** — `T112`, `T113`, `T114`, `T117`, and `T120` are all `[P]`. `T121` is `physical` and
runs only on the user's machine, as does the measurement half of `T116`.

---

## Implementation Strategy

**Ship US1 first and stop.** It is the whole barrier the feature exists to remove: today the
application is unusable by anyone who has not hand-authored a catalog, which is almost nobody.
Phase 2 plus Phase 3 is a tool that prints Captain America's pack from a folder, and that is worth
having before anything else lands.

**Then US2, immediately.** The spec is explicit that US2 is not a separate feature but the other
half of US1 — a pack silently missing three cards is worse than no pack, discovered at the table
after paying to print it. Shipping US1 without US2 ships the failure mode.

**Then US3, US4, US5 in whatever order the real library makes urgent.** US3 is the one the
fixtures say is load-bearing: without it almost no pack resolves complete, because the pack's
extra aspect cards live under `Aspects/` by design.

**Two things to resist.**

- **Do not optimise the render.** Feature 001's SC-007/SC-007a are knowingly missed at 48.9 s and
  202 MB, measured, reviewed, and accepted. Nothing in this feature reopens them.
- **Do not add a card total check.** `pack.total` disagrees with the summed quantity for two of
  three packs measured (research R12), and FR-018 forbids expecting a total or warning on one.

**Do not begin implementing before the test task above it is failing.** Principle I is
NON-NEGOTIABLE and is enforced in review, not on the honour system.
