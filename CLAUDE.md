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
/speckit-implement`. Do not start implementing before a plan exists. The active feature is
[`specs/001-hero-deck-pdf-wizard/`](specs/001-hero-deck-pdf-wizard/); `tasks.md` there is
the live work list and `spec.md` holds the FR/SC identifiers that source comments cite.

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
- **SC-007 is knowingly missed.** A real ~41-card deck measures ~49 s and ~202 MB against
  the 30 s target. That was measured, accepted, and left as-is. Do not optimise it
  unprompted. (T067 still owes those numbers to `quickstart.md`.)
- Source comments cite requirement IDs (`FR-005c3`, `SC-007a`). When changing behaviour
  those comments describe, change the spec too — a spec/code divergence is a review
  failure, not a detail.

## Git

`CONTRIBUTING.md` is authoritative. The parts most often gotten wrong: branch from `main`
using the pattern it specifies (`NNN-short-name` for Spec Kit features, `type/short-name`
otherwise), Conventional Commits with the body explaining *why*, and merge by squash or
rebase — merge commits must not land on `main`.

Open the PR and stop there. I merge.
