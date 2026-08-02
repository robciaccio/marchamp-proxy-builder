# Marchamp Proxy Builder

Turns a Marvel Champions hero deck into a print-ready PDF at exact physical card size —
nine cards to a sheet, with cut guides, previewable page by page before you commit paper.

Runs entirely on your own machine. It binds to `127.0.0.1`, has no login, and makes no
outbound network calls: card images come from a folder you point it at, and nothing leaves
the machine.

## Requirements

- **Python 3.13** and [uv](https://docs.astral.sh/uv/)
- **A folder of card scans.** The application never downloads these.
- **A catalog file** describing which cards and decks exist. See
  [Authoring a catalog](#authoring-a-catalog) — this is the part you have to write.

Scans must be at least **750 × 1050 px**, which is 300 DPI at 63.5 × 88.9 mm. Anything
smaller fails the generation rather than being quietly upscaled. Check a few before you
start:

```bash
sips -g pixelWidth -g pixelHeight "/path/to/images/some-card.tiff"
```

## Install

```bash
uv sync --locked
```

`--locked` fails rather than silently updating `uv.lock`.

## Configure

Two settings are required; the application refuses to start without them and tells you
which is missing.

| Variable | Required | Default | What it is |
|---|---|---|---|
| `MARCHAMP_IMAGE_DIR` | yes | — | Folder holding your card scans. Read-only; never written to. |
| `MARCHAMP_CATALOG` | yes | — | Path to your catalog JSON file. |
| `MARCHAMP_PORT` | no | `8765` | Port to listen on. |
| `MARCHAMP_HOST` | no | `127.0.0.1` | Must be a loopback address. A public address is refused. |

## Run

```bash
export MARCHAMP_IMAGE_DIR="$HOME/marchamp/card-images"
export MARCHAMP_CATALOG="$HOME/marchamp/catalog.json"

uv run marchamp serve
```

Then open **<http://127.0.0.1:8765>**.

`uv run marchamp serve --port 9000` overrides the port for one run. There is no `--host`
flag on purpose: staying private should not depend on remembering to leave a flag off.

Stop it with `Ctrl-C`. Nothing persists — generated documents live in memory for the life
of the process, so download anything you want to keep before quitting.

## Using it

1. **Choose a deck.** The list comes from your catalog; adding a deck needs only a catalog
   edit and a restart, never a code change.
2. **Choose paper and fitting.** Letter or A4. The three fit modes exist because card scans
   are about 2.7% taller in proportion than a real card, so something has to give — each
   option says what it costs at the point you choose it:
   - **Crop** — trims ~1.2 mm from top and bottom. Prints at exact card size.
   - **Fit** — keeps the whole image, but the printed face is 61.8 mm wide instead of 63.5.
   - **Stretch** — exact size and nothing trimmed, but the art is distorted ~2.7%.
3. **Generate.** Pages appear in the preview as they render. Any art substitutions and the
   page and face counts are shown before the download button, so you find out about them
   before printing rather than after.
4. **Print at 100%.** Turn off "fit to page" / "shrink oversized pages", or the cards come
   out the wrong size no matter what this tool does.

### Check your printer first

A single-page calibration sheet — a ruler and one card outline at exact size — is at
<http://127.0.0.1:8765/api/calibration> (add `?page_size=A4` for A4). Print it at 100% and
measure the ruler. If 100 mm does not measure 100 mm, fix that before printing a deck.

> This is a URL for now; surfacing it in the interface is still an open task.

## Laying out the image directory

The layout is yours to choose. **Nothing is inferred from folder names or filenames** —
every image is found only through an explicit path in the catalog, so you can organise
however you like and rename freely without breaking anything.

What follows is one workable convention, not a requirement:

```
card-images/
├── Core Set/
│   └── Aspects/
│       ├── Basic-Grey/
│       │   └── Grey_Energy_Resource_88.tiff
│       └── Leadership/
│           └── Leadership_Make the Call_Event_71.tiff
└── Heros/
    └── Steve Rogers_Captain America/
        ├── Steve Rogers_Captain America_Hero_1a.tiff
        ├── Steve Rogers_Captain America_Alter-Ego_1b.tiff
        └── Captain America_Agent 13_Ally_2.tiff
```

Paths in the catalog are relative to `MARCHAMP_IMAGE_DIR`. Absolute paths and `..` are
rejected. Files you never reference are ignored — an extra file is not an error.

## Authoring a catalog

The catalog is a JSON file describing **cards** (a title and its rules), **printings** (one
pack's artwork for a card), and **decks** (an ordered list of entries with quantities).

The card/printing split matters because the same card is reprinted with different art in
different packs, and a deck should print with its own pack's version where you have it.

```json
{
  "schema_version": "1",
  "cards": [
    {
      "id": "captain-america",
      "name": "Captain America",
      "double_sided": true,
      "printings": [
        {
          "id": "captain-america@cap",
          "pack": "Captain America Hero Pack",
          "number": "1a",
          "image": "Heros/Steve Rogers_Captain America/Steve Rogers_Captain America_Hero_1a.tiff",
          "image_back": "Heros/Steve Rogers_Captain America/Steve Rogers_Captain America_Alter-Ego_1b.tiff"
        }
      ]
    },
    {
      "id": "energy",
      "name": "Energy",
      "double_sided": false,
      "printings": [
        {
          "id": "energy@core",
          "pack": "Core Set",
          "number": "88",
          "image": "Core Set/Aspects/Basic-Grey/Grey_Energy_Resource_88.tiff"
        }
      ]
    }
  ],
  "decks": [
    {
      "id": "captain-america",
      "name": "Captain America (Steve Rogers)",
      "hero_card_id": "captain-america",
      "entries": [
        { "card_id": "captain-america", "preferred_printing_id": "captain-america@cap", "quantity": 1 },
        { "card_id": "energy", "preferred_printing_id": "energy@core", "quantity": 1 }
      ]
    }
  ]
}
```

### Field reference

**Card** — `id` (unique, stable, independent of any filename), `name` (what you see named
in an error), `double_sided` (default `false`; when `true` the card prints **two** faces),
`printings` (at least one).

**Printing** — `id` (unique across the whole catalog), `pack`, `image` (path relative to
the image directory), `image_back` (**only** for double-sided cards), `number` (optional
and informational — it is pack-scoped, so it can never identify a card: Make the Call is
16 in the Captain America pack and 71 in the Core Set).

**Deck** — `id`, `name`, `hero_card_id` (must exist in `cards`), `entries` (order is
preserved into the PDF).

**Entry** — `card_id`, `preferred_printing_id` (must be a printing *of that same card*),
`quantity` (≥ 1; each copy prints as its own face).

### Things that trip people up

- **The hero card must be an entry too.** `hero_card_id` names the hero, but only `entries`
  decide what prints. A 40-card deck plus a double-sided hero entry is 42 faces, 5 pages.
- **`image_back` is only for double-sided cards.** A back on a single-sided card is a
  validation error, not a harmless extra — it is nearly always a modelling mistake.
- **Missing art is not always fatal.** If a card's preferred printing has no file but
  another printing does, the other is used and reported to you as a *substitution* before
  you print. It fails only when no printing of that card is usable.
- **`schema_version` must be `"1"`.** An unrecognised version is refused outright rather
  than parsed on a best-effort basis.

### Writing one is currently manual

There is no tool that generates a catalog for you yet. Building one by hand means listing
every card, pointing each at a file, and getting the quantities right — for a 40-card deck
that is real work, and it is the main thing standing between a folder of scans and a
printable sheet.

Two parts of it are awkward in different ways. Mapping files to cards is mechanical and
could be automated from a naming convention. Quantities cannot be: they come from the
decklist card in the pack, and nothing in a filename tells you that Heroic Strike is ×3.

### Checking your catalog

Every problem is reported at once rather than one per attempt:

```bash
curl -s http://127.0.0.1:8765/api/catalog/validation | python3 -m json.tool
```

`valid: false` comes back as a normal `200` — the request succeeded, the catalog did not.
`GET /api/health` gives a shorter answer, including whether configuration is missing.

## Driving it without a browser

Everything the interface does goes through the HTTP API, so the whole tool is scriptable.

```bash
# Start a generation; returns immediately with an id.
curl -s -X POST http://127.0.0.1:8765/api/generations \
  -H 'Content-Type: application/json' \
  -d '{"deck_id":"captain-america","page_size":"LETTER","fit_mode":"CROP"}'

# Poll it — status, progress, pages_ready, substitutions, failures.
curl -s http://127.0.0.1:8765/api/generations/<id>

# Download once status is "succeeded".
curl -s -o deck.pdf http://127.0.0.1:8765/api/generations/<id>/document
```

The full contract is in
[`specs/001-hero-deck-pdf-wizard/contracts/openapi.yaml`](specs/001-hero-deck-pdf-wizard/contracts/openapi.yaml),
and the running service serves its own at `/openapi.json` with interactive docs at `/docs`.

## Troubleshooting

| What you see | What it means |
|---|---|
| `Cannot start — the application is not configured yet` | `MARCHAMP_IMAGE_DIR` or `MARCHAMP_CATALOG` is unset. The message names which, and only the ones actually missing. |
| `Cannot start — the configuration points at something that is not there` | Both are set, but a path is wrong. A different problem with a different fix, so it reads differently. |
| `address already in use` | Something is already on the port. Use `--port`, or stop the other process. |
| Deck list is empty | The catalog parsed but defines no decks. Check `/api/catalog/validation`. |
| Generation fails naming several cards | Every failing card is listed at once, deliberately, so you fix them in one pass rather than one per run. |
| Cards print the wrong size | Printer scaling. Print the calibration page and measure it before blaming the PDF. |

## Development

```bash
uv run pytest              # full suite
uv run ruff check .        # lint
uv run ruff format .       # format
```

Tests are mandatory here, not optional — see
[`.specify/memory/constitution.md`](.specify/memory/constitution.md), Principle I. Test
fixtures generate their own synthetic card images; **real card art must never enter this
repository**, which is why `card_directory/`, `*.tif`, `*.tiff`, and `*.pdf` are all
gitignored.

Contributing conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); security reporting is
in [SECURITY.md](SECURITY.md).
