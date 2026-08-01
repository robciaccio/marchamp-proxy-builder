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

**Performance Goals**: 95% of deck generations (~41 cards) complete within 30 s (SC-007);
preview first page visible within 5 s of confirmation

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
│   ├── geometry.py     # mm↔pt, card box, grid, margins, cut guides
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

## Open Risk Carried Into Implementation

**Source image resolution is unverified.** FR-010 requires ≥300 DPI at final print size,
which at 63.5 × 88.9 mm means **at least 750 × 1050 pixels** per card face. The Drive
folder is not available locally yet, so this has not been checked against real files. If
the scans fall short, FR-010 fails immediately, and either the DPI floor or the card size
has to change — a spec question that implementation cannot paper over.

Check it as soon as the download completes:

```bash
sips -g pixelWidth -g pixelHeight -g dpiWidth "/path/to/a/card.tif"
```

Treat "a representative sample of cards is ≥750 × 1050 px" as a prerequisite to starting
the render module.
