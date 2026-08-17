# Implementation Plan: Hero Pack Printing from a Scan Library

**Branch**: `002-starter-deck-assembly` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-starter-deck-assembly/spec.md`

## Summary

Point the application at a hero folder in a scan library and get that hero's whole pack as one
print-ready PDF — every card in the quantities the pack ships, the identity card with every
face, the nemesis set, and the decklist card — with no catalog authored by hand.

The shape follows from four properties of the problem.

**Identity and quantity live upstream; images live locally.** MarvelCDB says what a pack
contains; the user's scans say what it looks like. The application therefore gains its first
outbound network call, and with it the constitution's egress, caching, and conduct
requirements — but never downloads an image (FR-002).

**The library is organised by someone else and is inconsistent.** A hero's cards are not all in
that hero's folder, three different filename conventions are in use, and for two of the ten
acceptance heroes the filename numbers are copy counts rather than positions. Resolution is a
cascade with a reported provenance per card, not a lookup.

**A run outlives a request.** Confirming the pack, supplying a file for a card the library
lacks, and coming back tomorrow are all steps in one run, so this feature introduces the first
durable state the project has had. Where it lives was decided by adversarial review and
recorded as [ADR 0001](../../docs/adr/0001-durable-run-state-on-the-filesystem.md): plain files,
one directory per run.

**Printing is feature 001's job and stays that way.** The resolved pack is expressed in 001's
catalog structures and handed to 001's pagination and PDF composition (FR-048). This feature
adds no output format and relaxes none of 001's print rules.

## Technical Context

**Language/Version**: Python 3.13 (unchanged)

**Primary Dependencies**: FastAPI + Uvicorn, ReportLab, Pillow, pypdfium2, Pydantic v2 — all
inherited from feature 001. **One addition: `httpx`**, promoted from dev to runtime for the
MarvelCDB client (research [R2](./research.md#r2--http-client-and-egress-containment); justified
in Complexity Tracking). **And `python-multipart`**, which FastAPI requires for `UploadFile` and
without which a route using one refuses to start (research R9).

**Storage**: Filesystem, in two disjoint trees. The **scan library** is read-only source
material named per run (FR-001, FR-005). The **state directory** (`MARCHAMP_STATE_DIR`,
defaulting to the platform data directory) is app-owned and holds run records, uploaded bytes,
pack snapshots, and stored PDFs, per ADR 0001. No database. The state directory MUST be
refused if it resolves inside a named library root.

**Testing**: pytest, as 001. New in this feature: a recorded-response fixture set for the
MarvelCDB client (no live network in CI), and a **derived library fixture** — the real library's
filenames and folder layout reproduced over generated placeholder images, carrying no card art
and no MarvelCDB card text (FR-038a).

**Target Platform**: macOS and Linux desktop, browser UI over `127.0.0.1` (unchanged)

**Project Type**: Local web application (single deployable, browser front end)

**Performance Goals**: SC-001 (a printable pack in under five minutes of *user* time) and
SC-006d (upstream requests do not grow with card count; a fresh snapshot issues none).
SC-006i sets the reuse target: a second assembly of an unchanged pack skips the ~49 s render
but still resolves. **001 SC-007/SC-007a (render time) are knowingly missed and are not reopened
here** — a real deck measures 48.9 s and 202 MB, reviewed and accepted. Note that 002's own SC-007
is byte-identical regeneration and is a different criterion entirely; the identifier is reused
across features and is always qualified here.

**Constraints**: Outbound access limited to `marvelcdb.com` and to metadata only (FR-002,
FR-003). Byte-identical regeneration against the same library and snapshot (FR-045). Every
asset read through the adapter (FR-004). No absolute path from outside the named library in any
record or log (FR-009). Loopback binding only. A run must survive an application restart.

**Scale/Scope**: One human user, one library of ~4,447 images, hero packs of 32–46 card records
and 56–60 physical cards. Run counts in the tens to low hundreds over the application's life —
an assumption ADR 0001 states rather than verifies. Roughly 7 pages per pack PDF. 001 measured ~202 MB for a 41-card deck; a pack is ~60 faces, so
**at least that and probably more** — measured for real in T116.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against constitution **v1.3.0**. Every gate that feature 001 passed still passes;
the rows below say what **changes** in this feature, because a gate that changes is the one
worth reading.

| Gate | Status | What this feature does about it |
|---|---|---|
| **I. Test-First** | PASS | Filename parsing, pack ranking, the resolution cascade, face expansion, and group classification are pure functions over fixtures, tested first. The derived library fixture (FR-038a) makes the ten acceptance heroes assertable in CI without card art. Output geometry stays 001's assertions, unchanged. |
| **II. Interface-First** | PASS | Every capability is an endpoint in [contracts/openapi.yaml](./contracts/openapi.yaml) before the wizard touches it (FR-049). An assembly run is an addressable resource with its own lifecycle, which is what makes FR-026a's multi-step flow expressible at all. FR-036's outcome is a field on the run, not an exit status — this feature ships **no CLI**. |
| **III. Content and Assets Are External Data** | PASS, and **strengthened** | The catalog stops being an authored file for this path: a pack listing is fetched, validated at capture (FR-047), versioned by revision (FR-044), and reversible by refresh (FR-044b) — Principle III's three content clauses, satisfied by the snapshot rather than by a file the user maintains. `compose()` and `validate_source()` move from `image_dir: Path` to `assets.Store` (research R8), which closes a standing gap where `render/` knew binaries were files. |
| **IV. Simplicity & YAGNI** | PASS with two justified items | No database, no queue, no cache tier, no auth, no plugin system. Two new runtime dependencies and one new storage seam, all in Complexity Tracking against requirements that exist today. HTTP caching is hand-rolled rather than adding `hishel` — the snapshot store already is the cache, and must be, because runs pin revisions. `pack.total` was available as a completeness cross-check and is deliberately **not** wired in (research R12). |
| **V. Observability & Reproducibility** | PASS | The run record is the log record: pack, whether identified or user-selected, snapshot revision, every resolution with its provenance, omissions, outcome. Determinism carries over from 001 and gains an ordering rule (research R10), and FR-045 is verified with reuse disabled so a served PDF cannot fake agreement. |
| **Security — egress allowlisted** | **Newly in force** | 001 made no outbound call and recorded that as deliberate so this moment would bring the requirement back. One host, `marvelcdb.com`; redirects not followed; the resolved address re-checked against loopback, link-local, and private ranges before connecting. Three endpoints, all documented in research R1 and R4: `cards/{pack_code}.json`, `packs/`, and `card/{code}.json` as the prefix-map fallback — bounded per unknown pack prefix, never per card (FR-040). No credentials exist to send (FR-003). |
| **Security — untrusted binaries** | PASS, **widened** | Uploaded files (FR-026e) are a new ingestion path and get the identical treatment: content-sniffed, decoded, checked against the byte, pixel, and resolution ceilings, rejected with a specific reason (FR-028). Manual choice bypasses discovery, never validation. Upstream JSON is validated on capture and on read (FR-047). |
| **Security — isolated parsing** | PASS | Decode and render keep 001's `ProcessPoolExecutor` with `RLIMIT_AS`/`RLIMIT_CPU`. Both store implementations pickle across that boundary. The HTTP client runs in the request process and parses only JSON. |
| **Security — expensive work bounded** | PASS | 001's per-generation ceilings apply unchanged. New bounds this feature owes: upload byte size, library scan file count, and a cap on concurrent renders. Retention is bounded by the user (FR-026g) rather than by policy, which the spec states and accepts. |
| **Security — rate limits key on a principal** | N/A | Loopback-only, one human user, no accounts. Unchanged from 001. The outbound direction is governed by FR-041–FR-043 instead. |
| **Security — content validated on read** | PASS | A snapshot is re-validated when read, not only when captured — it is a file on disk the user could edit. A `run.json` written by a newer schema version is **refused**, never best-effort parsed (ADR 0001 § Consequences). |
| **Security — failures close** | PASS | A card that resolves to no image stops the run (FR-017). No partial PDF, inherited from 001's FR-020b. A blanket permission to print incomplete offered before the gaps are known is refused rather than honoured (FR-030a). |
| **Security — supply chain** | PASS | `httpx` moves from the dev group to runtime and `python-multipart` is added; the lockfile is updated in the same commit and CI installs frozen. No new GitHub Action. |
| **Account controls** | N/A | Still no accounts. |

**Constitution amendments required by the design: none.** Nothing in this feature's technical
shape needs one — `httpx` is a client library rather than a component of comparable weight to the
Technology section's pillars, and `TODO(ASSET_TARGET)` stays open, narrowed in writing by ADR 0001
to source assets and their encodings (the run store is app-owned state in a different category and
does not sit behind `assets.Store`).

The constitution *was* amended to **v1.3.0** alongside this plan, for a process reason unrelated
to the design: feature 002 took five branches to refine one spec, and the one-branch-per-feature
naming rule made each invent a descriptive name that said nothing about which feature it belonged
to. v1.3.0 admits a numeric suffix, and narrows the requirement that a constitution amendment
arrive in its own PR so that it binds **MAJOR amendments only** — a MAJOR invalidates compliant
work and carries a migration path, so it keeps undivided review. A MINOR or PATCH may travel with
the work that motivates it, provided it is its own commit and is called out in the PR description,
which is the protection that made the old rule worth having.

### One contradiction found, and resolved in the spec

FR-005, FR-007, FR-021, and FR-031 could not all hold as written: FR-007 made the named folder
the containment boundary while FR-021 requires searching the whole library above it, and User
Story 3 exists entirely to exercise the second. Planning surfaced it; **the spec was amended on
2026-08-17** rather than the plan diverging from it.

A run now names a `library_root` (FR-007's boundary, FR-021's extent) and a `hero_folder` within
it (what FR-010 identifies from and FR-031 accounts for). Both are named per run, so FR-005 and
SC-003a are unchanged in substance. Thirteen requirements and criteria were reworded to say which
of the two they mean; the reasoning and the rejected alternative are in research
[R0](./research.md#r0--the-spec-names-one-folder-where-the-design-needs-two) and in the spec's
2026-08-17 clarification. No intent changed and no success criterion moved.

## Project Structure

### Documentation (this feature)

```text
specs/002-starter-deck-assembly/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── openapi.yaml     # 002's endpoints, merged into the one live document
└── tasks.md             # Created by /speckit-tasks, not here

docs/adr/
└── 0001-durable-run-state-on-the-filesystem.md   # decided before this plan
```

### Source Code (repository root)

New packages are marked `+`; existing ones show only what this feature changes.

```text
src/marchamp/
├── upstream/                 + MarvelCDB: the only outbound path in the project
│   ├── client.py             + allowlist, no redirects, User-Agent, backoff (FR-003, FR-041-043)
│   ├── models.py             + PackIndexEntry, PackCard — reduced fields only (FR-038a)
│   └── snapshots.py          + capture, revision hash, freshness, refresh (FR-044, FR-044a/b)
├── library/                  + reading the scan library
│   ├── filenames.py          + the three conventions; unparseable is reported (FR-032)
│   ├── index.py              + one os.walk per resolve; position, name, and decklist
│   │                           indexes (FR-021, FR-013d)
│   └── identify.py           + rank the pack index, verify one pack, score (FR-010, FR-011)
├── assembly/                 + the feature's core
│   ├── faces.py              + linked chain + double_sided -> faces; groups (FR-015a/b/f)
│   ├── resolve.py            + the FR-020..FR-025 cascade, with provenance per card
│   ├── catalog.py            + resolved pack -> feature 001's Catalog/HeroDeck (FR-048)
│   ├── report.py             + the assembly report (FR-031..FR-037)
│   └── service.py            + run lifecycle: identify, resolve, render, reuse
├── store/                    + durable state, per ADR 0001
│   ├── layout.py             + MARCHAMP_STATE_DIR; refuses a path inside a library root
│   ├── atomic.py             + fsync ordering, F_FULLFSYNC, os.replace  <- LOAD-BEARING
│   ├── runs.py               + run.json with optimistic version; per-run lock
│   ├── pdfs.py               + standard vs saved; os.link refcounting (FR-026g/g1/h/i)
│   └── sweep.py              + startup orphan sweep (ADR 0001 § Consequences)
├── assets/
│   ├── store.py                unchanged protocol
│   ├── local_dir.py            unchanged
│   └── overlay.py            + `upload:`-prefixed refs to the run dir, else the library (R8)
├── catalog/
│   ├── printings.py          ~ usability check goes through the Store, not image_dir / ref
│   └── validation.py         ~ likewise
├── render/
│   ├── document.py           ~ compose() takes a Store, not image_dir: Path
│   └── images.py             ~ validate_source() takes a Store and a ref
├── api/
│   ├── routes.py             ~ + the assembly, pack, and stored-PDF endpoints
│   └── schemas.py            ~ + their request and response models
├── config.py                 ~ + state dir, upstream host, upload and scan ceilings
└── web/                      ~ the wizard gains folder naming, pack confirmation,
                                per-card upload, the run list, and the stored-PDF list

tests/
├── contract/                 ~ live OpenAPI still matches contracts/openapi.yaml
├── integration/              + ten acceptance heroes over the derived fixture library;
│                               resume across restart; reuse and its three invalidations;
│                               determinism with reuse disabled
└── unit/                     + filenames, ranking, cascade, faces, freshness, atomic write
```

**Structure Decision**: same single Python package and static browser UI as feature 001 — one
process serving the API and the UI files, no build step. The four new packages split on the
axis this feature's failures actually fall along: what upstream said (`upstream/`), what the
disk holds (`library/`), what the two make together (`assembly/`), and what survives a restart
(`store/`). A failure belongs to exactly one of them, which is what makes FR-037's "name the
specific card or file at fault" answerable without tracing.

## Complexity Tracking

> Three items exceed the obvious minimum. Each is justified against a requirement that exists
> today, per Principle IV. Durable state itself is not listed: it is mandated by FR-026b and
> FR-026f and settled by ADR 0001, not chosen for convenience.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `httpx` promoted from dev to a runtime dependency | The constitution's egress clause is a MUST: backend clients must not follow redirects and must re-validate after one. `httpx` defaults `follow_redirects=False` and demands an explicit timeout; both are the safe direction by default rather than by remembering. Already in the lockfile for 001's contract tests, so no new transitive surface. | `urllib.request` with a redirect-blocking handler is ~15 lines and genuinely defensible. Rejected narrowly: it follows redirects **by default**, so the control lives in a subclass someone can delete without a test noticing. If a reviewer prefers it, `upstream/client.py` is the only module that changes. |
| `python-multipart` added as a runtime dependency | Not a choice: FastAPI requires it for `UploadFile` and refuses to start a route that declares one without it. FR-026e requires uploads. | None exists. Parsing multipart by hand to avoid a dependency would be strictly worse on every axis, including the security one. |
| A second storage seam (`store/`) alongside `assets.Store` | `assets.Store` is read-only, image-shaped (`AssetInfo` carries `width_px`), and rooted at a boundary that changes every run. Run records, snapshots, and PDFs are written, are not images, and live somewhere stable. Forcing them through one protocol would widen it to a general read-write blob API that nothing else wants. | One protocol for both was rejected as the abstraction Principle IV's third clause warns about — extracted from two examples that differ in every property that matters. ADR 0001 records the same conclusion. |

## Requirement-to-Module Traceability

| Module | Requirements |
|---|---|
| `upstream/client.py` | FR-003, FR-038, FR-040, FR-041, FR-042, FR-043 |
| `upstream/snapshots.py` | FR-039, FR-044, FR-044a, FR-044b, FR-046, FR-047 |
| `upstream/models.py` | FR-038a, FR-047 |
| `library/filenames.py` | FR-032, FR-033, FR-034 |
| `library/index.py` | FR-013d, FR-020, FR-021, FR-031 |
| `library/identify.py` | FR-010, FR-011, FR-012 |
| `assembly/faces.py` | FR-015, FR-015a, FR-015b, FR-015e, FR-015f, FR-018 |
| `assembly/resolve.py` | FR-013, FR-013a, FR-014, FR-016, FR-017, FR-020–FR-025, FR-030 |
| `assembly/catalog.py` | FR-015d, FR-048 |
| `assembly/report.py` | FR-012, FR-018, FR-024, FR-029, FR-030b, FR-031–FR-037 |
| `assembly/service.py` | FR-012a, FR-012b, FR-013e, FR-026a, FR-030a, FR-036, FR-045 |
| `store/layout.py` | FR-001, FR-008, FR-009 |
| `store/atomic.py` | FR-026b, FR-026f |
| `store/runs.py` | FR-026b, FR-026c, FR-026e, FR-044, FR-045 |
| `store/pdfs.py` | FR-026f, FR-026g, FR-026g1, FR-026h, FR-026i |
| `assets/overlay.py` | FR-004, FR-007, FR-026e |
| `render/document.py`, `render/images.py` | FR-004, FR-028, FR-048 |
| `api/` | FR-005, FR-006, FR-026, FR-026c, FR-026d, FR-027, FR-036, FR-037, FR-049 |
| `config.py` | FR-005, FR-007 |
| `web/` | FR-012a, FR-012b, FR-013c, FR-013d, FR-026c, FR-026d, FR-026e |

## Artifact Update Rule

Feature 001 adopted this locally after requirements passes found spec-to-artifact drift twice.
It carries forward unchanged and gains three rows for what this feature introduces.

**A change to a functional requirement is not complete until every artifact it touches has been
updated in the same commit.**

| If you change… | Also check |
|---|---|
| A requirement with a numeric limit | data-model.md, this plan's Technical Context |
| Anything the API exposes or returns | contracts/openapi.yaml, and the quickstart scenario exercising it |
| A recorded or logged field | data-model.md § Assembly Run, § Assembly Report |
| A print-geometry rule | 001's data-model.md § Print Layout — this feature adds no geometry |
| A performance target | this plan's Performance Goals; targets live in the spec as SC items |
| **A retained upstream field** | data-model.md § Pack Snapshot, and the fixture reduction (FR-038a) |
| **A run state or transition** | data-model.md § Assembly Run, contracts/openapi.yaml, quickstart § V5 |
| **The reuse key** | data-model.md § Stored PDF, quickstart § V7, and SC-006h/i/k |

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1. **No new violations, and no gate weakened.** Three movements worth
recording:

- **Principle III moved from "satisfied by intent" to "satisfied by structure."** Feature 001
  passed this gate with a catalog file the user maintained; the adapter existed but `render/`
  still computed `image_dir / ref`, so assembly code did know where a binary lived. Taking a
  `Store` closes that, and the pack snapshot supplies the versioned, validated, reversible
  content store the principle asks for without anyone authoring JSON.
- **The egress gate is in force for the first time**, and the design keeps it small on purpose:
  one host, two documented endpoints, no redirects, no credentials, no image bytes. Feature 001
  recorded its N/A specifically so this would be noticed rather than inherited.
- **Principle IV's exposure grew and was contained.** Four new packages is the most structure
  this project has added at once. The containment is that none of them is speculative: every
  module in the traceability table above has at least one FR, and the items that are not
  strictly forced are in Complexity Tracking with the alternative named and the flip condition
  stated.

No open items. The FR-005/FR-007/FR-021/FR-031 contradiction that planning surfaced was carried
back into the spec on 2026-08-17, so spec and artifacts agree.
