---

description: "Task list for Hero Deck PDF Wizard implementation"
---

# Tasks: Hero Deck PDF Wizard

**Input**: Design documents from `/specs/001-hero-deck-pdf-wizard/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/openapi.yaml](./contracts/openapi.yaml)

**Tests**: **MANDATORY, not optional.** The template treats tests as opt-in; the project
constitution's Principle I (Test-First, NON-NEGOTIABLE) overrides that. Every test task
below MUST be written and observed failing before the implementation task it covers.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3, matching spec.md user stories
- Exact file paths are given in every task

## Path Conventions

Single Python project per plan.md: `src/marchamp/` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization

- [X] T001 Create source tree `src/marchamp/{catalog,assets,layout,render,api,generations,observability,web}/` and `tests/{contract,integration,unit}/`, each with `__init__.py` where it is a package
- [X] T002 Initialize uv project in `pyproject.toml` — Python 3.13; runtime deps fastapi, uvicorn, reportlab, pillow, pypdfium2, pydantic; dev deps pytest, pypdf, ruff
- [X] T003 Generate and commit `uv.lock`, and confirm `uv sync --locked` fails if the lockfile would change
- [X] T004 [P] Configure ruff (lint + format) in `pyproject.toml`
- [X] T005 [P] Configure pytest in `pyproject.toml` — `testpaths`, and markers `slow` and `physical` for tests needing a printer
- [X] T006 [P] Add `.github/workflows/ci.yml` running `uv sync --locked`, `ruff check`, `ruff format --check`, and `pytest`, with all actions pinned to full commit SHAs
- [X] T007 [P] Create `tests/conftest.py` with a synthetic fixture catalog and **generated** placeholder TIFFs at 1446×2079 — real card art MUST NOT enter the repository under any circumstances

**Checkpoint**: `uv run pytest` runs and collects zero tests without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core shared by every user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Configuration, errors, logging

- [X] T008 Write failing test for settings resolution and its "not configured" vs "configured but wrong" distinction in `tests/unit/test_config.py` (FR-005c3, FR-019b)
- [X] T009 Implement `src/marchamp/config.py` — image directory, catalog path, host/port, and the FR-0A4 limits as named constants
- [X] T010 [P] Write failing test for the six failure kinds and the single retryable one in `tests/unit/test_errors.py` (FR-021)
- [X] T011 [P] Implement `src/marchamp/api/errors.py` — failure taxonomy with `retryable` and card naming (FR-019b1, FR-021)
- [X] T012 [P] Write failing test asserting generation records carry fit mode and page size, and exclude outside paths, in `tests/unit/test_logging.py` (FR-022, FR-022a, FR-022b)
- [X] T013 [P] Implement `src/marchamp/observability/logging.py` — structured records to stdout or a configured file

### Asset store (the adapter seam)

- [X] T014 Write failing test for path containment, read-only behaviour, and content-sniffed format detection in `tests/unit/test_assets.py` (FR-019c, FR-019d)
- [X] T015 Implement the `Store` protocol in `src/marchamp/assets/store.py` — `exists` / `open` / `describe`, with refs opaque to callers
- [X] T016 Implement `src/marchamp/assets/local_dir.py` — reads from the configured local directory with no credentials and no network call; the only implementation today; rejects absolute paths and `..` escapes (FR-019)

### Catalog

- [X] T017 Write failing test for the card/printing split and `double_sided` in `tests/unit/test_catalog_models.py` (FR-005e)
- [X] T018 Implement `src/marchamp/catalog/models.py` — Card, Printing, HeroDeck, CardEntry with Pydantic v2
- [X] T019 Write failing test that catalog revision is content-derived and stable across reorderings and file moves in `tests/unit/test_catalog_loader.py` (FR-005c2)
- [X] T020 Implement `src/marchamp/catalog/loader.py` — parse, reject unknown `schema_version`, compute revision (FR-005c1)
- [X] T021 Write failing test that validation reports **all** errors at once, never first-and-stop, and that image files are found only via explicit mapping rather than by name or folder, in `tests/unit/test_catalog_validation.py` (FR-005a, FR-005b, FR-005b1, FR-005c, FR-005d)
- [X] T022 Implement `src/marchamp/catalog/validation.py` — the ten checks in data-model.md, with duplicate image mapping as a warning not an error
- [X] T023 Write failing test that preferred printings win, stand-ins are deterministic, and a card with no usable printing fails, in `tests/unit/test_printings.py` (FR-005f–j)
- [X] T024 Implement `src/marchamp/catalog/printings.py` — resolution ordered by printing id, never by directory or hash iteration

### Layout geometry

- [X] T025 Write failing test asserting slot size 63.5×88.9 mm ±0.5, Letter and A4 margins, portrait, and cut guides outside every slot in `tests/unit/test_geometry.py` (FR-008a, FR-008b, FR-009, FR-011, FR-013)
- [X] T026 Implement `src/marchamp/layout/geometry.py` — mm↔pt at a single boundary, slot size as one configurable value (FR-009a)
- [X] T027 Write failing test that quantities expand to one face per copy, that a 40-card deck plus a double-sided hero yields **42** faces on 5 pages, and that the hero's two faces are adjacent, in `tests/unit/test_paginate.py` (FR-007, FR-012, FR-012a, FR-012b, FR-012c)
- [X] T028 Implement `src/marchamp/layout/paginate.py` — ordered faces to positioned slots, last page partially filled with no placeholder outlines

### Isolated decoding

- [X] T029 Write failing test that a worker exceeding memory, CPU, or wall-clock limits fails the generation naming the limit in `tests/unit/test_workers.py` (FR-0A4)
- [X] T030 Implement `src/marchamp/render/workers.py` — `ProcessPoolExecutor` with `RLIMIT_AS`, `RLIMIT_CPU`, and a wall-clock timeout
- [X] T031 Write failing test for the three fit modes' output geometry, the 300 DPI floor measured post-crop, and rejection of oversized or malformed images, in `tests/unit/test_images.py` (FR-009b, FR-009b1, FR-009b2, FR-010, FR-014)
- [X] T032 Implement `src/marchamp/render/images.py` — content sniffing, explicit `Image.MAX_IMAGE_PIXELS`, pinned resampling filter (FR-015a), runs inside a worker

### Service skeleton

- [X] T033 Write failing test that the service binds loopback only, is unreachable from a non-loopback address, and exposes no authentication or session surface in `tests/integration/test_binding.py` (FR-0A1, FR-0A2, FR-0A3, SC-001a)
- [X] T034 Implement `src/marchamp/api/app.py` — FastAPI app bound to `127.0.0.1`, never `0.0.0.0`, serving `src/marchamp/web/` statically

**Checkpoint**: Foundation ready — user stories can begin.

---

## Phase 3: User Story 1 - Download a printable hero deck (Priority: P1) 🎯 MVP

**Goal**: Select a hero deck and download a print-ready PDF at exact card size.

**Independent Test**: Select any deck, download the PDF, print at 100%, cut one card, and
insert it into a sleeved standard card. Succeeds when the card fits and the face is legible.

### Tests for User Story 1 ⚠️ Write first, observe failing

- [X] T035 [P] [US1] Contract test asserting the live OpenAPI matches `contracts/openapi.yaml` in `tests/contract/test_openapi_matches.py` (Principle II, merge gate)

  > **Drift measured 2026-08-01, reconciled the same day.** Resolved as recommended below,
  > plus two disagreements the original survey did not catch.
  >
  > | Area | Resolution |
  > |---|---|
  > | Path params | Contract adopted snake_case (`{deck_id}`, `{generation_id}`, `{page_number}`). The JSON bodies were already snake_case, so the camelCase paths were the inconsistency |
  > | Preview endpoint | Kept in the contract; implemented by T054 |
  > | `Generation.progress` / `pages_ready` | Implemented by T055 |
  > | `/api/health` `problems` | Added to the contract, with a named `ConfigProblem` schema |
  > | Response schemas | Named Pydantic models added in `src/marchamp/api/schemas.py`; every route declares one, so the advertised components now actually generate |
  > | **`page_size` was unusable** — not in the original survey | `PageSize` was an `Enum` whose *values* were millimetre pairs, so the API asked clients to POST `[215.9, 279.4]` rather than `"LETTER"`. Now a `StrEnum` with a `dimensions_mm` property, which also leaves one place where the name and the geometry can disagree instead of two |
  > | **Errors were not RFC 9457** — not in the original survey | The contract promised `application/problem+json`; the service returned FastAPI's `{"detail": …}` as `application/json`. Exception handlers in `api/app.py` now give every error one shape |
  >
  > The test compares the interface *surface* — paths, methods, parameters, bodies,
  > statuses, media types, and response-schema shapes — rather than doing byte equality,
  > because `openapi.yaml` carries the design reasoning and that prose is the reason to keep
  > it hand-authored. Its one deliberate blind spot is FastAPI's automatic `422`, which is
  > framework behaviour rather than designed interface.
- [X] T036 [P] [US1] Integration test generating a full deck end to end from the fixture catalog, and that a deck added to the catalog becomes selectable after restart with no rebuild, in `tests/integration/test_generate_deck.py` (FR-004, FR-006, SC-009)
- [X] T037 [P] [US1] Integration test asserting PDF geometry — MediaBox, slot size, 3×3 grid, guides outside slots — for all three fit modes in `tests/integration/test_print_geometry.py` (SC-003)
- [X] T038 [P] [US1] Integration test that regeneration is byte-identical across 20 attempts including one in a separate process in `tests/integration/test_determinism.py` (FR-015, SC-006)
- [X] T039 [P] [US1] Integration test that all failing cards are reported together, that no document is downloadable, that a card with no usable printing fails rather than falling back, and that nothing retries on its own in `tests/integration/test_failure_reporting.py` (FR-005i, FR-020, FR-020a, FR-020b, FR-021a)
- [X] T040 [P] [US1] Integration test that stand-ins are used and reported before download in `tests/integration/test_printing_fallback.py` (FR-005g, FR-005h, SC-012)
- [X] T041 [P] [US1] Integration test that a full generation succeeds with networking unavailable in `tests/integration/test_offline.py` (FR-019a, SC-001b)

### Implementation for User Story 1

- [X] T042 [US1] Implement `src/marchamp/render/document.py` — ReportLab composition with `invariant=1`, placing faces per the layout (FR-008, FR-015)
- [X] T043 [P] [US1] Implement `src/marchamp/generations/registry.py` — in-memory store living only for the process lifetime (FR-021b)
- [X] T044 [US1] Implement `src/marchamp/generations/service.py` — orchestrate resolve → decode → compose, capture catalog revision at creation, collect substitutions and failures (depends on T024, T028, T032, T042)
- [X] T045 [US1] Implement deck endpoints `GET /api/decks` and `GET /api/decks/{deckId}` in `src/marchamp/api/routes.py` (FR-001, FR-005, FR-018)
- [X] T046 [US1] Implement `POST /api/generations`, `GET /api/generations/{id}`, and `GET /api/generations/{id}/document` in `src/marchamp/api/routes.py` (FR-008, FR-020)
- [X] T047 [US1] Implement `GET /api/health` and `GET /api/catalog/validation` in `src/marchamp/api/routes.py` (FR-003c, FR-005d)
- [X] T048 [US1] Set the download `Content-Disposition` filename to deck, fit mode, and page size in `src/marchamp/api/routes.py`, so the mode is identifiable from the document itself (FR-008c, FR-009d)
- [X] T049 [US1] Emit the structured generation record on every terminal outcome in `src/marchamp/generations/service.py` (FR-022)
- [X] T050 [US1] Build the minimal wizard — deck list, fit mode and page size selection with their stated costs, generate, download — in `src/marchamp/web/` (FR-002, FR-003, FR-009c)

**Checkpoint**: A deck downloads as a correct, printable PDF. MVP complete.

---

## Phase 4: User Story 2 - Preview the pages before printing (Priority: P2)

**Goal**: See exactly what will print before committing paper and ink.

**Independent Test**: Select a deck, view the preview, download, and compare — page count,
card order, and card position must agree exactly.

### Tests for User Story 2 ⚠️ Write first, observe failing

- [X] T051 [P] [US2] Integration test that the preview matches the PDF page for page and card for card in `tests/integration/test_preview_matches.py` (FR-017, SC-005)
- [X] T052 [P] [US2] Integration test that pages become viewable progressively and progress advances during a run in `tests/integration/test_progress.py` (FR-016a, FR-016b)

### Implementation for User Story 2

- [X] T053 [US2] Implement `src/marchamp/render/preview.py` — rasterise the generated PDF with pypdfium2, never re-draw from the layout model (FR-017)
- [X] T054 [US2] Implement `GET /api/generations/{id}/pages/{pageNumber}` with a bounded width parameter in `src/marchamp/api/routes.py` (FR-016d)
- [X] T055 [US2] Report `progress` and `pages_ready` on the generation resource in `src/marchamp/generations/service.py` (FR-016a, FR-016b)
- [X] T056 [US2] Add the preview pane in `src/marchamp/web/`, invalidating a preview whenever fit mode or page size changes, and allowing the user to move back a step while a generation runs without blocking the interface or needing a cancel control (FR-003a, FR-003b, FR-016, FR-016c)
- [X] T057 [US2] Show the substitution list and total face count alongside the preview, before download, in `src/marchamp/web/` (FR-005h, FR-018, FR-018a)

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 - Verify print scale before printing a whole deck (Priority: P3)

**Goal**: Catch a mis-scaled printer for the cost of one sheet of paper.

**Independent Test**: Print the calibration page and measure the ruler with a physical ruler.

### Tests for User Story 3 ⚠️ Write first, observe failing

- [X] T058 [P] [US3] Integration test that the calibration ruler and card outline measure exactly, and the outline equals the slot rather than a fit-mode face, in `tests/integration/test_calibration.py` (FR-023)

### Implementation for User Story 3

- [X] T059 [US3] Implement `src/marchamp/render/calibration.py` — one page, measurable ruler, one 63.5×88.9 mm outline
- [X] T060 [US3] Implement `GET /api/calibration` with a page size parameter in `src/marchamp/api/routes.py`
- [ ] T061 [US3] Surface calibration in the interface so it needs no URL knowledge, in `src/marchamp/web/` (FR-003f)

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T062 [P] Add an architecture test asserting no imaging, PDF, or filesystem-path import appears outside `assets/` and `render/` in `tests/unit/test_adapter_boundary.py` (merge gate 5)
- [ ] T063 [P] Implement the distinguishable empty states — no catalog, no decks, deck with no cards — in `src/marchamp/web/` (FR-003d)
- [ ] T064 [P] Make the validation report readable when it lists many problems, grouped by deck or card, in `src/marchamp/web/` (FR-003e)
- [ ] T065 [P] Verify and fix keyboard operability across the whole flow in `src/marchamp/web/` (FR-003g)
- [ ] T066 [P] Add `README.md` covering setup, configuration, and catalog authoring
- [ ] T067 Measure SC-007 and SC-007a on a real ~41-card deck and record the numbers in `specs/001-hero-deck-pdf-wizard/quickstart.md`
- [ ] T068 Add `ci` to the required status checks on the `main` branch ruleset so merge gate 1 is actually enforced
- [ ] T069 Run every scenario in [quickstart.md](./quickstart.md) against a real catalog and record the results

### Physical validation — cannot be automated

- [ ] T070 Print the calibration page at 100%, confirm the ruler measures true within ±0.5 mm, and record the result in `specs/001-hero-deck-pdf-wizard/quickstart.md` (SC-003)
- [ ] T071 Print one page in each of the three fit modes, sleeve one card from each in front of a real card, and record which is acceptable in `specs/001-hero-deck-pdf-wizard/quickstart.md` (SC-002, SC-009a)
- [ ] T072 Set the winning fit mode as the default in `src/marchamp/config.py`, and record in `specs/001-hero-deck-pdf-wizard/spec.md` whether the other modes are kept or removed — the toggle exists to answer this question, not to persist (spec Assumptions, plan Complexity Tracking)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **User Stories (Phases 3–5)**: all depend on Foundational; independent of each other afterwards
- **Polish (Phase 6)**: depends on the stories it touches; T070–T072 depend on US1 and US3

### User Story Dependencies

- **US1 (P1)**: after Foundational. No dependency on other stories.
- **US2 (P2)**: after Foundational. Rasterises whatever US1 produces, but is testable on any generated PDF.
- **US3 (P3)**: after Foundational. Needs only `layout/geometry.py`, not the generation pipeline — the most independent of the three.

### Within Each Story

Tests written and failing → models → services → endpoints → interface. Never the reverse:
Principle I rejects a pull request whose tests were authored after the code they verify.

### Parallel Opportunities

- T004–T007 in Setup
- T010–T013 in Foundational (errors and logging are independent of each other)
- All of T035–T041 — every US1 test is a separate file
- T043 alongside T042
- T051 and T052; T062–T066 in Polish
- With more than one person: US1, US2, and US3 can proceed simultaneously once Phase 2 lands

---

## Parallel Example: User Story 1

```bash
# All seven US1 tests are independent files — write them together, watch them all fail:
Task: "Contract test OpenAPI matches contracts/openapi.yaml in tests/contract/test_openapi_matches.py"
Task: "Integration test full deck generation in tests/integration/test_generate_deck.py"
Task: "Integration test PDF geometry for three fit modes in tests/integration/test_print_geometry.py"
Task: "Integration test byte-identical regeneration in tests/integration/test_determinism.py"
Task: "Integration test all failures reported together in tests/integration/test_failure_reporting.py"
Task: "Integration test stand-ins reported before download in tests/integration/test_printing_fallback.py"
Task: "Integration test offline generation in tests/integration/test_offline.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup
2. Phase 2 Foundational — the long pole; nothing works before it
3. Phase 3 US1
4. **Stop and validate**: print a deck, cut a card, sleeve it
5. That is a usable product

### Incremental Delivery

Foundation → US1 (MVP, printable decks) → US2 (stop wasting paper on mistakes) → US3
(stop wasting paper on printer settings). Each adds value without breaking the last.

### Notes

- Tests are mandatory here, unlike the template default — Principle I is NON-NEGOTIABLE
- Fixture images MUST be synthetic; real card art never enters the repository
- Commit after each task or logical group
- Per the plan's Artifact Update Rule, a change to a requirement is not done until every
  artifact it touches moves in the same commit
- **T071 and T072 are the point of the whole fit-mode experiment.** Until they are done, the
  three modes are an open question, not a feature
