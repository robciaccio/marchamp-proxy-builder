# Phase 0 Research: Hero Deck PDF Wizard

Resolves `TODO(TECH_STACK)` for this feature. Every decision below is driven by a specific
requirement in [spec.md](./spec.md) or a gate in the constitution, not by general
preference.

## R1 — Language and runtime

**Decision**: Python 3.13.

**Rationale**: The two hardest requirements are a PDF writer with exact physical placement
*and* a documented byte-identical mode (FR-009, FR-015), and a TIFF decoder that fails
safely on hostile input (FR-020). Python is the ecosystem where both exist as mature,
permissively-licensed libraries — ReportLab's `invariant` flag in particular has no
equivalent in the JavaScript PDF ecosystem, where reproducibility means manually stripping
metadata. `resource.setrlimit` in a worker process gives a real memory ceiling, which the
constitution's isolated-parsing gate requires. The repo is already configured for Python
Spec Kit scripts (`init-options.json: script: "py"`).

**Alternatives considered**:
- **TypeScript/Node with `sharp` + `pdf-lib`**: `sharp` (libvips) beats Pillow on large
  images, and would be the right call if throughput mattered. It does not here — a deck is
  ~41 card-sized images on one machine. Against it: no documented determinism switch in the
  PDF layer, and no straightforward in-process memory cap for the decoder.
- **Rust with `printpdf` + `image`**: best safety story for untrusted decode, and genuinely
  tempting. Rejected under Principle IV — the PDF tooling is less mature for precise
  typographic placement, and the build/iteration cost is not repaid for a single-user local
  tool.
- **Go**: PDF libraries are weakest of the four for exact placement.

## R2 — PDF generation

**Decision**: ReportLab, using `canvas.Canvas(..., invariant=1)`.

**Rationale**: ReportLab is the reference implementation for programmatic PDF layout with
absolute coordinate control, which is what FR-009 (±0.5 mm) and FR-011 (fixed grid) need.
Critically, `invariant=1` normalises the timestamp and document-id metadata that otherwise
vary per run, making output byte-identical for identical input — this is what turns SC-006
from an aspiration into a test that either passes or fails. Coordinates are in points; the
layout module converts from millimetres at a single boundary so that the physical unit is
the source of truth.

**Alternatives considered**:
- **fpdf2**: lighter and pleasant to use, but reproducibility requires manual metadata
  suppression rather than a supported flag.
- **PyMuPDF**: excellent renderer, but AGPL-3.0, and its strengths are extraction and
  rendering rather than composition.
- **HTML→PDF (WeasyPrint, headless Chromium)**: rejected outright. Physical accuracy would
  depend on a browser's print pipeline, which is the single largest source of the silent
  rescaling this feature exists to defeat.

## R3 — Image decoding

**Decision**: Pillow, with `Image.MAX_IMAGE_PIXELS` set to an explicit ceiling.

**Rationale**: Pillow reads the TIFF variants these scans are likely to use and exposes the
DPI and pixel dimensions needed to enforce FR-010 before any resampling happens. Its
decompression-bomb guard is the right default behaviour: above the threshold it raises
`DecompressionBombError` rather than allocating. The important detail is that the ceiling
must be **set deliberately**, not disabled — the common workaround of
`MAX_IMAGE_PIXELS = None` removes exactly the protection the constitution's untrusted-binary
gate is asking for. Validation is by content sniffing, never by file extension.

**Alternatives considered**:
- **pyvips**: markedly better on very large images and lower peak memory. Held in reserve —
  if real scans turn out to be far larger than expected, this is a drop-in change behind the
  decode boundary. Not adopted now because it adds a system library dependency for
  throughput this feature does not need.
- **ImageMagick via subprocess**: large CVE surface, and a shell boundary to get wrong.

## R4 — Preview rendering

**Decision**: pypdfium2, rasterising the actual generated PDF.

**Rationale**: FR-017 and SC-005 require the preview to match the PDF exactly. The only way
to guarantee that structurally, rather than by discipline, is to render the very bytes the
user will download. pypdfium2 wraps PDFium (the engine in Chrome's PDF viewer) under
Apache-2.0/BSD-3-Clause, so it carries no copyleft obligation.

**Alternatives considered**:
- **PyMuPDF**: faster, but AGPL-3.0. For a local personal tool that is legally fine, since
  nothing is distributed — rejected anyway to keep the licence story simple if this is ever
  hosted or shared.
- **pdf2image + Poppler**: works, but shells out to a system binary that must be installed
  separately, which worsens the quickstart for no gain.
- **Drawing the preview from the layout model**: rejected on principle. See Complexity
  Tracking in [plan.md](./plan.md) — a second rendering path is the defect FR-017 guards
  against.

## R5 — Local web service

**Decision**: FastAPI + Uvicorn, bound to `127.0.0.1`.

**Rationale**: Principle II requires an OpenAPI document *generated from or verified
against* the running service; FastAPI derives it from the same Pydantic models used for
validation, so it cannot drift by hand. Binding explicitly to `127.0.0.1` (never `0.0.0.0`)
satisfies FR-0A2 without depending on a firewall, and is directly testable from a second
machine (SC-001a).

**Alternatives considered**:
- **Flask**: needs a separate schema layer to produce an equivalent OpenAPI document.
- **Desktop shell (Tauri/Electron)**: heavier, and adds a packaging problem for a tool the
  user starts from a terminal.
- **Pure CLI**: would satisfy generation but not the wizard and preview the spec centres on.

## R6 — Page size and the fixed grid

**Decision**: One fixed 3×3 grid; page size is a per-generation parameter (Letter or A4),
defaulting to Letter.

**Rationale**: FR-011 requires a grid that fits both without scaling. Nine full-size cards
occupy exactly 190.5 × 266.7 mm, which fits inside both page sizes:

| Page | Size (mm) | Horizontal margin | Vertical margin |
|---|---|---|---|
| US Letter | 215.9 × 279.4 | 12.70 mm | 6.35 mm |
| A4 | 210 × 297 | 9.75 mm | 15.15 mm |

The binding constraints are A4's width and Letter's height, and both clear with margin to
spare. Emitting the PDF at the user's actual paper size — rather than one size and hoping
the printer centres it — is what keeps "no scaling" true in practice.

**Alternatives considered**:
- **Letter-only output printed on A4**: content fits, but relies on printer centring
  behaviour, reintroducing the variability this feature exists to remove.
- **Choosing a grid per page size**: rejected — a variable grid means two layouts to test
  and no fixed card count per page.

## R7 — Determinism, end to end

**Decision**: `invariant=1`, plus a pinned resampling filter, sorted iteration over any
mapping, and no wall-clock value written into the document.

**Rationale**: SC-006 requires byte-identical regeneration, and determinism leaks from more
places than the PDF writer. Resampling must name its filter explicitly, since a library
default can change between versions. Any dict or set iteration that reaches output ordering
must be sorted. The verification is a test that generates the same deck twice in one run
and asserts equal bytes — plus a slower test that does it across two processes, which
catches hash-ordering effects the single-process test cannot.

## Unverified — carried into implementation

**Source image resolution.** FR-010 needs ≥300 DPI at final size, i.e. **≥750 × 1050 px**
per card. The Drive folder is still downloading, so no real file has been measured. This is
the one open question that could invalidate a requirement rather than a design choice, and
it is recorded as a prerequisite in [plan.md](./plan.md).

## Sources

- [ReportLab canvas source — `invariant` parameter](https://content.schrodinger.com/Docs/r2021-4/python_api/_modules/reportlab/pdfgen/canvas.html)
- [ReportLab User Guide, ch.2 pdfgen graphics](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/)
- [Pillow Image module — MAX_IMAGE_PIXELS and DecompressionBombError](https://pillow.readthedocs.io/en/stable/reference/Image.html)
- [Pillow image file formats — TIFF support](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)
- [Python PDF library comparison, 2026](https://www.nutrient.io/blog/best-python-pdf-libraries/)
- [The Python PDF ecosystem — pypdfium2 licensing](https://martinthoma.medium.com/the-python-pdf-ecosystem-in-2024-2cad87732e49)
