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
| [`specs/002-starter-deck-assembly/`](specs/002-starter-deck-assembly/) | Planned, not built. Spec, plan, research, data model, contract, quickstart, and a 119-task `tasks.md` all exist; **no code yet**. Respecified 2026-08-16 — it was `002-catalog-scaffold`, and the earlier premise that card quantities must be typed in by hand is disproved in that spec's Clarifications. The storage decision is [ADR 0001](docs/adr/0001-durable-run-state-on-the-filesystem.md). |

For either one, `tasks.md` is the live work list and `spec.md` holds the FR/SC identifiers
that source comments cite.

## Commands

```bash
uv sync --all-groups              # install; CI uses --locked and must not update the lock
uv run pytest -m "not physical"   # the suite CI runs
uv run pytest -m physical         # needs a printer and a ruler; never in CI
uv run ruff check . && uv run ruff format --check .
uv run marchamp serve             # wizard + API on 127.0.0.1:8765
```

Running the app needs both env vars set, or `serve` refuses to start and says which is
missing:

```bash
export MARCHAMP_IMAGE_DIR="$PWD/card_directory"
export MARCHAMP_CATALOG="$PWD/card_directory/catalog.json"
```

## Layout

| Path | Holds |
|---|---|
| `src/marchamp/api/` | FastAPI app, routes, Pydantic schemas, error mapping |
| `src/marchamp/catalog/` | Catalog loading, printing selection, validation |
| `src/marchamp/assets/` | Storage-agnostic asset adapter; `local_dir.py` is today's backend |
| `src/marchamp/layout/` | Page geometry and pagination |
| `src/marchamp/render/` | PDF document, image decode, preview rasterisation, workers |
| `src/marchamp/generations/` | Generation registry and orchestration |
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
- **SC-007 and SC-007a are knowingly missed.** A real ~41-card deck measures 48.9 s and
  202 MB against the 30 s target, and the first preview page takes 10.5 s against the 5 s
  target. Measured, reviewed, accepted, and left as-is because the tool is local-only and
  the run stays well inside FR-0A4's hard ceilings. Do not optimise it unprompted. The
  numbers and the reasoning are in
  [`quickstart.md` V12](specs/001-hero-deck-pdf-wizard/quickstart.md).
- Source comments cite requirement IDs (`FR-005c3`, `SC-007a`). When changing behaviour
  those comments describe, change the spec too — a spec/code divergence is a review
  failure, not a detail.

## Git

`CONTRIBUTING.md` is authoritative. The parts most often gotten wrong: branch from `main`
using the pattern it specifies (`NNN-short-name` for Spec Kit features, `type/short-name`
otherwise), Conventional Commits with the body explaining *why*, and merge by squash or
rebase — merge commits must not land on `main`.

Open the PR and stop there. I merge.
