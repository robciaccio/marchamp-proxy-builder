# Marchamp Proxy Builder

Local-only web app that assembles print-ready proxy PDFs for Marvel Champions. A user
picks a hero deck, villain, modular set, or scenario; the service gathers card images from
an external directory and emits PDFs that cut into a playable deck.

Python 3.13 · FastAPI · ReportLab · Pillow · pypdfium2 · Pydantic · `uv`.

## Governing documents

Read these before proposing a change; they are the rules, not background.

- [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — principles and
  merge gates. Test-first is non-negotiable and enforced in review.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — branch naming, Conventional Commits, PR procedure.
- [`SECURITY.md`](SECURITY.md) — secret-scanning and leak remediation.

Work follows Spec Kit: `/speckit-specify → /speckit-plan → /speckit-tasks →
/speckit-implement`. Do not start implementing before a plan exists.

**Which feature is "active" has two answers, and they mean different things.**
[`.specify/feature.json`](.specify/feature.json) names the feature the Spec Kit commands
operate on by default — the scripts rewrite it on every `/speckit-specify`, so it tracks
the most recently *specified* feature, not the one with the most work left. It currently
points at `002`. Do not read it as a statement of priority, and do not hand-edit it to
express one; pass an explicit feature path to a command instead.

Where the features actually stand:

| Feature | State |
|---|---|
| [`specs/001-hero-deck-pdf-wizard/`](specs/001-hero-deck-pdf-wizard/) | Implemented and shipped. `tasks.md` still has open items: UI polish (T061–T065), an architecture test (T062), and physical print validation (T069–T072) that needs a printer and a ruler. |
| [`specs/002-starter-deck-assembly/`](specs/002-starter-deck-assembly/) | Implemented. All eight phases of its 126-task `tasks.md` are done; the two `physical`-marked tests (T116, T121) need the mounted library and a printer and are run by hand. Respecified 2026-08-16 — it was `002-catalog-scaffold`, and the earlier premise that card quantities must be typed in by hand is disproved in that spec's Clarifications. The storage decision is [ADR 0001](docs/adr/0001-durable-run-state-on-the-filesystem.md). |

For either one, `tasks.md` is the live work list and `spec.md` holds the FR/SC identifiers
that source comments cite.

## Commands

```bash
uv sync --all-groups              # install; CI uses --locked and must not update the lock
uv run pytest -m "not physical"   # the suite CI runs
uv run pytest -m physical         # needs the mounted library, a printer, a ruler; never in CI
uv run ruff check . && uv run ruff format --check .
uv run marchamp serve             # wizard + API on 127.0.0.1:8765
```

**The two features need different configuration, and this is the thing most often gotten
wrong.** 001 needs a catalog and an image directory; 002 needs neither, because a run names
its library root and hero folder per request (FR-005, SC-003a). Setting 001's variables does
not enable 002's paths and unsetting them does not disable them — a test that configures them
for a 002 test has stopped proving SC-003a.

```bash
# Feature 001 only. `serve` **starts without these** — 002 removed the refusal (FR-005,
# SC-003a) and reports them as "the prebuilt deck list is not configured yet" instead.
export MARCHAMP_IMAGE_DIR="$PWD/card_directory"
export MARCHAMP_CATALOG="$PWD/card_directory/catalog.json"

# Optional, both features. Where run records, snapshots and stored PDFs live (ADR 0001).
# Defaults to the platform data directory; refuses to sit inside a named library root.
export MARCHAMP_STATE_DIR="$HOME/Library/Application Support/marchamp"

# The `physical` tests only, and never in CI.
export MARCHAMP_REAL_LIBRARY="/Volumes/GoogleDrive/My Drive/Marvel Champions Scans"
export MARCHAMP_UAT_OUTPUT="$HOME/Desktop/marchamp-uat"   # where T116 leaves the PDF
```

## Layout

| Path | Holds |
|---|---|
| `src/marchamp/api/` | FastAPI app, routes, Pydantic schemas, error mapping |
| `src/marchamp/catalog/` | Catalog loading, printing selection, validation (001) |
| `src/marchamp/assets/` | Storage-agnostic asset adapter; `local_dir.py` and `overlay.py` (a run's uploads over its library) |
| `src/marchamp/layout/` | Page geometry and pagination |
| `src/marchamp/render/` | PDF document, image decode, preview rasterisation, workers |
| `src/marchamp/generations/` | Generation registry and orchestration (001) |
| `src/marchamp/library/` | Reading a scan library — filename conventions, the index, pack identification (002) |
| `src/marchamp/upstream/` | The **only** outbound path. MarvelCDB client, reduced card records, pack snapshots (002) |
| `src/marchamp/store/` | Durable state on the filesystem — atomic writes, run records, stored PDFs, retention (ADR 0001) |
| `src/marchamp/assembly/` | A run: identification → resolution cascade → decklist → report → PDF (002) |
| `src/marchamp/observability/` | The two log records, `GenerationRecord` (001) and `AssemblyRecord` (002) |
| `src/marchamp/web/` | The wizard — plain `index.html` / `app.js` / `styles.css`, no build step |
| `tests/{unit,integration,contract}/` | Contract test verifies the live OpenAPI against `specs/.../contracts/openapi.yaml` |

## Things that bite

- **`card_directory/` is gitignored** and holds the real card art plus the generated
  `catalog.json`. Never commit images, PDFs, or any derived rendition — the `.gitignore`
  is a safety net, review is the control. If you need card data, ask for it; do not go
  hunting the filesystem for it.
- **`.gitignore` asset rules are root-anchored on purpose.** An unanchored `assets/` also
  matched `src/marchamp/assets/` and silently excluded that package from every commit —
  local tests passed and CI could not import it. Keep the leading slashes.
- **The host is loopback-only by design** (FR-0A2). `Settings` rejects a non-loopback
  address, so there is deliberately no `--host` flag. Do not add one.
- **Ruff's `known-first-party` is declared explicitly.** Inferring it from `src` depended
  on whether the package happened to be installed, which made lint pass locally and fail
  in CI.
- **The API comes first** (constitution II). The web UI is a client of the HTTP API and
  must not reach around it into internal modules.
- **`SC-007` means two different things and neither is the other.** In **001** it is a render
  *time* target — 30 s for a deck — and it is knowingly missed: a real ~41-card deck measures
  48.9 s and 202 MB, and the first preview page takes 10.5 s against SC-007a's 5 s. Measured,
  reviewed, accepted, and left as-is because the tool is local-only and the run stays well
  inside FR-0A4's hard ceilings. Do not optimise it unprompted; the numbers and the reasoning
  are in [`001/quickstart.md` V12](specs/001-hero-deck-pdf-wizard/quickstart.md). In **002**
  the same identifier is a *determinism* criterion — the same library and snapshot produce
  byte-identical PDFs (`tests/integration/test_determinism.py`) — and it is met. Always say
  which feature's SC-007 you mean.
- **002 never fetches an image.** MarvelCDB serves card art from the host its card data comes
  from, so the egress allowlist cannot discharge FR-002 on its own; `tests/integration/
  test_egress.py` asserts the *paths* and that `imagesrc` reaches no stored snapshot. Card
  images come from the user's library or from a file they supplied, never from the network.
- **The library is never written to** (FR-001). It is a synced Drive folder, which makes a
  stray write irreversible and invisible — it propagates before anyone knows to look.
  `tests/integration/test_library_readonly.py` drives a whole run and compares the file set,
  sizes, and mtimes. Uploads go to the run's own directory, content-addressed.
- Source comments cite requirement IDs (`FR-005c3`, `SC-007a`). When changing behaviour
  those comments describe, change the spec too — a spec/code divergence is a review
  failure, not a detail.

## Git

`CONTRIBUTING.md` is authoritative. The parts most often gotten wrong: branch from `main`
using the pattern it specifies (`NNN-short-name` for Spec Kit features, `type/short-name`
otherwise), Conventional Commits with the body explaining *why*, and merge by squash or
rebase — merge commits must not land on `main`.

Open the PR and stop there. I merge.
