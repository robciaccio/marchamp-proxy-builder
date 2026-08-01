# Implementation Plan: Hero Deck PDF Wizard

**Branch**: `001-hero-deck-pdf-wizard` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-hero-deck-pdf-wizard/spec.md`

## Summary

A locally-run web application that turns a selected Marvel Champions hero deck into a
print-ready, 9-up PDF at exact physical card size, with a page preview beforehand.

The technical shape follows from three properties of the problem. Print correctness is
physical, so page geometry is computed in millimetres and asserted against the generated
file rather than eyeballed. Byte-identical regeneration is a requirement, so the PDF
writer must have a documented determinism mode. And card images are third-party binaries,
so decoding happens in a resource-capped worker process rather than inline.

Chosen stack: **Python 3.13**, **FastAPI** (local HTTP API + generated OpenAPI),
**ReportLab** (PDF, `invariant=1` for reproducibility), **Pillow** (TIFF decode),
**pypdfium2** (rasterises the real PDF for preview, so preview cannot drift from output).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: FastAPI + Uvicorn (local service, OpenAPI generation), ReportLab
(PDF composition), Pillow (TIFF/image decode), pypdfium2 (PDF→raster for preview),
Pydantic v2 (catalog schema validation)

**Storage**: Filesystem only. Content catalog is a versioned data file outside the
repository; card images are a read-only local directory. No database.

**Testing**: pytest, with `pypdf` for reading back PDF geometry and pypdfium2 for
pixel-level verification of rendered pages

**Target Platform**: macOS and Linux desktop, browser UI over `127.0.0.1`

**Project Type**: Local web application (single deployable, browser front end)

**Performance Goals**: SC-007 (95% of ~41-card decks within 30 s) and SC-007a (first preview
page within 5 s). Hard ceilings are FR-0A4's, not goals: 10 s / 512 MB / 80 MP per image,
200 faces and 120 s per generation — exceeding one fails the generation.

**Constraints**: Fully offline — no outbound network calls; card faces at ≥300 DPI at final
print size with no upscaling; byte-identical output for identical inputs; bind loopback only

**Scale/Scope**: Single user, one generation at a time. Catalog on the order of thousands of
cards and tens of decks. Roughly 40–50 cards per deck, 5–6 pages per PDF.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against constitution **v1.1.0**.

| Gate | Status | How this design satisfies it |
|---|---|---|
| **I. Test-First** | PASS | Layout maths, catalog validation, and deck resolution are pure functions with fixture-based tests written first. Output geometry is asserted programmatically (MediaBox + placed-image transforms via `pypdf`, pixel verification via pypdfium2) — never by looking at a PDF. |
| **II. Interface-First** | PASS | FastAPI generates OpenAPI from the running service, so the document cannot drift by hand. Every capability is an endpoint; the browser UI is purely a client. PDF generation is a `POST /generations` resource, not a side effect of a page render — the wording Principle II asks for. Sufficient to drive headless, so an MCP layer needs no new application logic. |
| **III. Content and Assets Are External Data** | PASS | Catalog is a data file outside the repo; adding a deck needs no rebuild (SC-009). Schema + referential integrity validated at load (FR-005c/d). Assets reached only through `assets.Store`, which knows nothing about directories vs. object storage. No binaries committed. |
| **IV. Simplicity & YAGNI** | PASS | No database, no queue, no cache tier, no auth. Five modules. One adapter implementation. Justifications for the two non-obvious pieces are in Complexity Tracking below. |
| **V. Observability & Reproducibility** | PASS | Structured log per generation carrying request id, deck, resolved card ids, catalog revision, outcome (FR-022). Determinism via ReportLab `invariant=1` plus fixed resampling filter and sorted iteration; verified by a test that generates twice and compares bytes. |
| **Security — egress allowlist** | N/A | This feature makes no outbound calls. Deliberate: recorded in the spec so that reintroducing remote fetching brings the requirement back into force. |
| **Security — untrusted binaries** | PASS | Content-sniffed via Pillow (not extension or declared MIME), with explicit ceilings on byte size and pixel count. `Image.MAX_IMAGE_PIXELS` is set deliberately rather than disabled, so decompression bombs raise instead of exhausting memory. |
| **Security — isolated parsing** | PASS | Decode and render run in a `ProcessPoolExecutor` worker with `RLIMIT_AS` and `RLIMIT_CPU` set, plus a wall-clock timeout. No credentials exist to expose. |
| **Security — cost bounds** | PASS | Per-generation ceilings on card count, total pixels, and wall-clock time (FR-0A4). Local-only means no anti-automation is needed — there is no hostile caller, only bad data. |
| **Security — fail closed** | PASS | Catalog validation refuses partial catalogs; a missing or unreadable asset aborts the whole generation (FR-020). No partial PDF is ever offered. |
| **Security — supply chain** | PASS | Lockfile committed, CI installs frozen. This feature introduces no new GitHub Actions. |
| **Account controls** | N/A | Local-only, no accounts. The constitution's deferred account section stays deferred. |

**Constitution amendment required before merge**: this plan resolves `TODO(TECH_STACK)`.
That is a **MINOR** amendment (v1.1.0 → v1.2.0) recording Python, FastAPI, ReportLab,
Pillow, and pypdfium2 in the Asset Pipeline section. Per the constitution's own rule, that
amendment PR must change nothing else. `TODO(ASSET_TARGET)` stays open — a local directory
is this feature's answer, not the durable object store the constitution anticipates.

## Project Structure

### Documentation (this feature)

```text
specs/001-hero-deck-pdf-wizard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit-tasks, not here
```

### Source Code (repository root)

```text
src/marchamp/
├── catalog/            # Load + validate the content catalog
│   ├── models.py       # Pydantic schema for cards, decks, image mapping
│   ├── loader.py       # Parse, compute revision hash
│   └── validation.py   # Referential integrity; collects ALL errors (FR-005d)
├── assets/             # Storage adapter — the seam Principle III requires
│   ├── store.py        # Protocol: exists(ref) / open(ref) / describe(ref)
│   └── local_dir.py    # The only implementation today; read-only
├── layout/             # Print geometry. Pure functions, no I/O.
│   ├── geometry.py     # mm↔pt, slot size, grid, margins, cut guides
│   └── paginate.py     # Ordered card list → pages of positioned slots
├── render/
│   ├── images.py       # Decode, validate, fit — runs in worker process
│   ├── document.py     # ReportLab composition (invariant=1)
│   ├── preview.py      # Rasterise the real PDF via pypdfium2
│   ├── calibration.py  # Ruler + outline page (User Story 3)
│   └── workers.py      # ProcessPoolExecutor with rlimits + timeouts
├── api/
│   ├── app.py          # FastAPI application, loopback binding
│   ├── routes.py       # Endpoints per contracts/openapi.yaml
│   └── errors.py       # Named, actionable failures (FR-020, FR-021)
├── observability/
│   └── logging.py      # Structured generation records (FR-022)
└── web/                # Static browser UI — a client of the API, nothing more

tests/
├── contract/           # Live OpenAPI matches contracts/openapi.yaml
├── integration/        # Catalog → PDF end to end, incl. determinism + offline
└── unit/               # Geometry, pagination, validation, image rules
```

**Structure Decision**: Single Python package with a static browser UI, not a split
frontend/backend tree. There is one deployable process serving both the API and the UI
files, the UI needs no build step, and Principle II is satisfied by the UI consuming only
public endpoints — a separate frontend project would add tooling without adding separation
that matters at this scale.

## Complexity Tracking

> Two design elements exceed the obvious minimum. Both are justified against a requirement
> that exists today, per Principle IV.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Worker-process isolation for image decode | The constitution mandates isolated parsing under hard limits, and image decoders are the most CVE-dense dependency here. The TIFFs are third-party files, not the user's own work. | Decoding inline in the request process was rejected: a malformed TIFF takes down the app, and a decompression bomb exhausts the machine, with no memory ceiling available in-process. |
| Rasterising the actual PDF for preview | FR-017 requires the preview to match the PDF exactly, and SC-005 sets that at 100%. | Rendering the preview from the layout model was rejected: it creates a second rendering path that can silently disagree with the PDF, which is exactly the defect the requirement exists to prevent. |
| Three selectable fit modes (FR-009b) instead of one default | Source scans are 2.7% taller in proportion than a standard card. Each candidate policy breaks a different requirement, and which looks acceptable is a physical question answerable only from printed output. This is a live experiment, not speculative configurability. | Picking one policy up front was rejected because there is no evidence to pick on — the decision would be a guess that costs a full print run to discover was wrong. **This exception is time-limited:** once printed evidence names a winner it becomes the default and the others are reconsidered for removal. |

## Artifact Update Rule

Requirements-quality passes found spec-to-artifact drift twice — page size and `failures[]`
in the first pass, four more in the second. The drift was not carelessness in any single
edit; it was the absence of a stated expectation about what moves together. So:

**A change to a functional requirement is not complete until every artifact it touches has
been updated in the same commit.** Concretely:

| If you change… | Also check |
|---|---|
| A requirement with a numeric limit | data-model.md (does it constrain the model?), this plan's Technical Context |
| Anything the API exposes or returns | contracts/openapi.yaml, and the quickstart scenario that exercises it |
| A recorded or logged field | data-model.md § Generation Record |
| A print-geometry rule | data-model.md § Print Layout, quickstart § V4 |
| A performance target | this plan's Performance Goals — targets belong in the spec as SC items, and the plan references them rather than inventing its own |

This is a feature-local rule for now. If it holds up, it belongs in the constitution's
Development Workflow section as a MINOR amendment.

## Requirement-to-Module Traceability

| Module | Requirements |
|---|---|
| `catalog/` | FR-004, FR-005, FR-005a–d, FR-005b1, FR-005c1–c3 |
| `assets/` | FR-019, FR-019a–d |
| `layout/` | FR-008a–c, FR-009, FR-009a–d, FR-011, FR-012, FR-013 |
| `render/images.py` | FR-009b1, FR-009b2, FR-010, FR-014, FR-0A4 |
| `render/document.py` | FR-008, FR-015, FR-015a |
| `render/preview.py` | FR-016, FR-016a–d, FR-017 |
| `render/calibration.py` | FR-023 |
| `api/` | FR-001–003, FR-003a–g, FR-018, FR-020, FR-020a–b, FR-021, FR-021a–b |
| `observability/` | FR-022, FR-022a–b |
| `api/app.py` | FR-0A1, FR-0A2, FR-0A3 |

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1. **No new violations, and no gate weakened.** Two gates moved
from "satisfied by intent" to "satisfied by structure", which is the stronger position:

- **Principle II** — modelling generation as a `POST /generations` resource with its own
  identity, rather than a synchronous download, is the literal wording of the principle. The
  whole product is now drivable from the nine endpoints in
  [contracts/openapi.yaml](./contracts/openapi.yaml) with no browser, so an MCP wrapper
  needs no application logic. The contract test makes drift a build failure rather than a
  code-review responsibility.
- **Principle I** — rasterising preview from the generated PDF means FR-017 is enforced by
  construction: there is only one rendering path, so preview and document cannot disagree.

Complexity Tracking still lists exactly two justified items. Nothing in Phase 1 added a
dependency, service, cache, or abstraction beyond them.

## Source Asset Findings

Measured against a real Captain America hero pack sample on 2026-07-31 (26 files).

### RESOLVED — resolution comfortably clears the bar

Scans are **~1446 × 2079 px** at 600 DPI metadata. FR-010 needs ≥750 × 1050 px, so there is
**1.93× linear headroom** — roughly 578 × 594 effective DPI at final print size. No
upscaling will ever be needed, and the DPI floor is not at risk. This risk is closed.

It also means downscaling is the norm, so the resampling filter must be pinned explicitly
(R7) — a library default change would silently alter output bytes.

### OPEN — source aspect ratio does not match a standard card

Every scan is **1.4378** (h/w) against a standard card's **1.4000**: about **2.7% taller in
proportion**. Visual inspection confirms the scans are **full-bleed, edge to edge** — no
white border and no trim margin, so the excess is not bleed that can simply be discarded.

This makes the spec's "different aspect ratio → fit without distortion and report the
discrepancy" edge case fire on **100% of cards**, which turns a signal into noise. A
standing policy is required instead, and each candidate breaks a different requirement:

| Policy | Result | Cost |
|---|---|---|
| Fit width, crop height | Exactly 63.5 × 88.9 mm | Discards 1.16 mm from top and bottom edges |
| Fit inside, preserve ratio | 61.8 × 88.9 mm | Narrower than standard — breaks FR-009 as written |
| Scale non-uniformly | Exactly 63.5 × 88.9 mm | 2.7% vertical squash — breaks FR-014 |

**Resolved 2026-07-31**: all three become user-selectable per generation (FR-009b), default
`crop`, so the choice is settled from printed evidence rather than guessed. `stretch` is
labelled as distorting wherever offered and can never be the default. See Complexity
Tracking for why this configurability is justified and why it should expire.

### Structure observations

- Nemesis and obligation cards (26–30) live in a `Captain America Nemesis/` subfolder,
  which lines up cleanly with FR-006 placing them out of scope.
- A `Captain America Decklist.tif` sits alongside the cards. It is not a card face and must
  not be printed — a good example of why the catalog maps files explicitly (FR-005a) rather
  than treating every file in a folder as a card.
- Filenames follow `{Set}_{CardName}_{Type}_{Number}` but underscores also appear *inside*
  names (`Steve_s Apartament`, `Captain America_s Shield`), and the source contains typos
  (`Stength in Numbers`). Deriving identity by parsing filenames would be fragile in exactly
  the way FR-005b anticipates.
- The sample is **incomplete**: player cards 16, 18, 20–23 are absent. Catalog validation
  (FR-005c) will catch this as `missing_image_file`, which is the correct behaviour — but it
  means no end-to-end deck generation is possible until the download finishes.
