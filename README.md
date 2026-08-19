# Marchamp Proxy Builder

Turns Marvel Champions cards into a print-ready PDF at exact physical card size — nine
cards to a sheet, with cut guides, previewable page by page before you commit paper.

There are two ways in, and they need very different amounts of work from you:

- **Print a hero's whole pack.** Point it at your folder of scans and a hero's folder inside
  it. It works out which pack that is, fetches the pack's card list, matches your scans to
  it, tells you about anything it could not find, and prints. **No catalog to write.**
- **Print a prebuilt deck.** Choose from a list you defined yourself in a catalog file. More
  control over exactly what prints, at the cost of authoring the catalog by hand.

The first is what most people want. The second came first and still works.

## What leaves your machine

The service binds to `127.0.0.1` and has no login. Your card scans never leave — they are
read from a folder you name, and are never uploaded, never sent anywhere, and never written
to.

**Pack assembly does make outbound requests**, and this is the only part of the application
that does. It asks [MarvelCDB](https://marvelcdb.com) which cards are in a pack, because
that list is not derivable from a folder of images. Specifically:

- three JSON endpoints only — `/api/public/packs/`, `/api/public/cards/{pack}.json`, and
  `/api/public/card/{code}.json`;
- **no card artwork is ever fetched**, even though MarvelCDB serves it from the same host;
- the response is reduced to eleven fields before it is stored — no card text, no flavour
  text, no image URLs;
- answers are cached, so a second run of the same pack asks for nothing at all;
- one request at a time, at most one per second, with a `User-Agent` naming the project.
  MarvelCDB is run by volunteers and publishes no rate limit; its absence is not permission.

If you print only from a catalog you wrote, nothing goes out at all.

## Requirements

- **Python 3.13** and [uv](https://docs.astral.sh/uv/)
- **A folder of card scans.** The application never downloads these and never writes to the
  folder.
- **A catalog file** — only for the prebuilt-deck path. Pack assembly needs none. See
  [Authoring a catalog](#authoring-a-catalog).

Scans must be at least **750 × 1050 px**, which is 300 DPI at 63.5 × 88.9 mm. Anything
smaller is refused with the reason rather than quietly upscaled. Check a few first:

```bash
sips -g pixelWidth -g pixelHeight "/path/to/scans/some-card.tiff"
```

## Install

```bash
uv sync --locked
```

`--locked` fails rather than silently updating `uv.lock`.

## Configure

Nothing is required to assemble a pack. Everything below is optional.

| Variable | Needed for | Default | What it is |
|---|---|---|---|
| `MARCHAMP_STATE_DIR` | both | platform data dir | Where runs, cached card lists and kept PDFs live. Refused if it sits inside a scan library. |
| `MARCHAMP_IMAGE_DIR` | prebuilt decks | — | Folder holding the scans your catalog refers to. Read-only. |
| `MARCHAMP_CATALOG` | prebuilt decks | — | Path to your catalog JSON file. |
| `MARCHAMP_PORT` | — | `8765` | Port to listen on. |
| `MARCHAMP_HOST` | — | `127.0.0.1` | Must be a loopback address. A public address is refused. |

The default state directory is `~/Library/Application Support/marchamp` on macOS,
`$XDG_DATA_HOME/marchamp` (or `~/.local/share/marchamp`) on Linux.

## Run

```bash
uv run marchamp serve
```

Then open **<http://127.0.0.1:8765>**.

With no catalog configured it starts anyway and says so:

```
The prebuilt deck list is not configured yet:

  • No card image directory configured. Set MARCHAMP_IMAGE_DIR to …
  • No catalog configured. Set MARCHAMP_CATALOG to your catalog file.

Pack assembly needs neither and is available.
```

That is not an error and the server is running. A missing catalog stops the prebuilt-deck
list from working; it stops nothing else.

`--port 9000` overrides the port for one run. There is no `--host` flag on purpose: staying
private should not depend on remembering to leave a flag off.

Stop it with `Ctrl-C`. Unlike the prebuilt-deck path, **pack assembly persists** — a run you
walked away from is still there when you come back, and PDFs you chose to keep survive
restarts. See [What is kept on disk](#what-is-kept-on-disk).

---

## Printing a whole pack

This is the path that needs no catalog.

1. **Name two folders.** Your scan library — the whole thing, wherever it lives — and the
   hero's folder inside it, like `Heros/Steve Rogers_Captain America`. Cards are searched
   for anywhere under the library root, not only in the folder you named.
2. **Confirm the pack.** It tells you which pack it thinks that folder is, and what it is
   basing that on, *before* resolving anything. Wrong guess? Pick the right one from the
   list. A confident wrong answer prints a complete-looking pack of the wrong hero, so it
   asks rather than assumes.
3. **Answer what it could not find.** Each missing card is named individually, with where it
   looked. For each one you can supply a file yourself, or say print without it — an
   omission is always explicit and always reported.
4. **Accept the deck list card.** If your hero's folder holds a scan of the pack's decklist,
   it proposes that file and you accept it. If it holds none — 25 of 60 hero folders do not
   — it says so and gives you the [Hall of Heroes](https://hallofheroeslcg.com/deck-lists/)
   address. It never fetches it for you. The pack still prints without one.
5. **Print at 100%.** Then cut, sort using the report, and build the starter deck by reading
   the printed decklist card.

The report tells you which cards are player cards, which is the identity, which form the
nemesis set, and which is the decklist — the groups print packed together with no page
break, so the report is what tells them apart on the table.

### It never tells you what belongs in the deck

The tool prints **packs**, not decks. Working out which cards form the starter deck is done
by reading the printed decklist card, on paper, by you.

That is deliberate and was measured: deriving deck membership from card data produces a
deck that is confidently wrong, and a silently wrong deck is worse than no answer. MarvelCDB
quantities are *copies in the pack*, not copies in the deck, and pre-built decks were
measured at 40, 41 and 42 cards. Nothing here checks for a total, or warns about one.

### How your scans are matched to cards

Every substitution is reported. In order:

1. an exact position match inside the folder you named — the only one that needs no
   explanation;
2. the same position anywhere else under the library root;
3. a **reprint** — the card was already printed in another pack and your scan of it lives in
   that pack's folder. Captain America's folder omits eight physical cards that were in the
   Core Set, and this is how they still print;
4. a name match, for filenames carrying no usable position at all.

Three filename conventions were found in a real library and all three work:

```
Leadership_Make the Call_Event_16.tiff          position 16
Wasp_Pym Particles_Resource_7_12.15.tiff        position 7
Captain America_Captain America_Hero_1a.tiff    position 1, identity face a
2_Active Altruism_Event.tif                     no position — the 2 counts copies
captain america decklist.tif                    the deck list scan
```

The third is why the name-match step exists: reading that leading `2` as a position is
confidently wrong, which is worse than not reading it at all.

Anything in the folder you named that matches none of these is listed as uninterpretable
rather than silently ignored — every file is either used or accounted for.

### One workable library layout

```
Marvel Champions Scans/
├── Heros/
│   └── Steve Rogers_Captain America/
│       ├── Captain America_Captain America_Hero_1a.tiff
│       ├── Captain America_Steve Rogers_Alter-Ego_1b.tiff
│       ├── Captain America Nemesis/
│       │   └── Captain America Nemesis_Baron Zemo_Minion_28.tiff
│       └── captain america decklist.tif
├── Core Set/
│   └── Aspects/Basic-Grey/Basic_Energy_Resource_88.tiff
└── Aspects/
    └── Leadership/Leadership_Strength in Numbers_Event.tiff
```

Your library is **never written to.** Files you supply for missing cards are stored with the
run, not beside the scan they stand in for. This matters because a scan library is usually a
synced Drive folder, where a stray write propagates to every device before anyone notices.

### What is kept on disk

In the state directory, never in your library:

- **runs** — a pack you started is still there tomorrow, with every answer you gave;
- **cached pack card lists**, so a repeat run asks MarvelCDB for nothing;
- **PDFs.** A pack printed without changes produces that pack's *standard* PDF, reused for
  every later run of it — these are ~200 MB and take ~50 s to build, so this is worth a lot.
  A run where you supplied a file or left a card out is yours alone and you give it a name.

Discarding a run frees the files you uploaded to it, not the pack's shared PDF. Kept PDFs
are listed and deleted individually.

---

## Printing a prebuilt deck

The original path. Needs `MARCHAMP_IMAGE_DIR` and `MARCHAMP_CATALOG`.

```bash
export MARCHAMP_IMAGE_DIR="$HOME/marchamp/card-images"
export MARCHAMP_CATALOG="$HOME/marchamp/catalog.json"
uv run marchamp serve
```

1. **Choose a deck**, from your catalog.
2. **Choose paper and fitting.** Letter or A4. The three fit modes exist because card scans
   are about 2.7% taller in proportion than a real card, so something has to give — each
   says what it costs where you choose it:
   - **Crop** — trims ~1.2 mm from top and bottom. Prints at exact card size.
   - **Fit** — keeps the whole image; the printed face is 61.8 mm wide instead of 63.5.
   - **Stretch** — exact size, nothing trimmed, art distorted ~2.7%.
3. **Generate.** Pages appear as they render; substitutions and the page and face counts are
   shown before the download button.
4. **Print at 100%.**

Generated documents here live in memory for the life of the process — download anything you
want to keep before quitting. (Pack assembly is the opposite; see above.)

### Check your printer first

A single-page calibration sheet — a ruler and one card outline at exact size — is at
<http://127.0.0.1:8765/api/calibration> (add `?page_size=A4` for A4). Print it at 100% and
measure the ruler. If 100 mm does not measure 100 mm, fix that before printing anything
else. Turn off "fit to page" and "shrink oversized pages", or the cards come out the wrong
size no matter what this tool does.

> This is a URL for now; surfacing it in the interface is still an open task.

## Authoring a catalog

Only for the prebuilt-deck path. **If you want to print a pack, skip this section entirely
— that is the whole point of it.**

The catalog is a JSON file describing **cards** (a title and its rules), **printings** (one
pack's artwork for a card), and **decks** (an ordered list of entries with quantities).

The card/printing split matters because the same card is reprinted with different art in
different packs, and a deck should print with its own pack's version where you have it.

Paths are relative to `MARCHAMP_IMAGE_DIR`; absolute paths and `..` are rejected. Nothing is
inferred from folder names or filenames here — every image is found through an explicit
path, so you can organise however you like. Files you never reference are ignored.

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

### Checking your catalog

Every problem is reported at once rather than one per attempt:

```bash
curl -s http://127.0.0.1:8765/api/catalog/validation | python3 -m json.tool
```

`valid: false` comes back as a normal `200` — the request succeeded, the catalog did not.
`GET /api/health` gives a shorter answer, including whether configuration is missing.

## Driving it without a browser

Everything the interface does goes through the HTTP API, so the whole tool is scriptable.

**Assembling a pack:**

```bash
BASE=http://127.0.0.1:8765

# Start a run. Returns immediately with an id, a version, and what pack it thinks this is.
RUN=$(curl -s -X POST $BASE/api/assemblies -H 'Content-Type: application/json' \
  -d '{"library_root":"/Volumes/Drive/Marvel Champions Scans",
       "hero_folder":"Heros/Steve Rogers_Captain America"}')
ID=$(jq -r .id <<<"$RUN"); V=$(jq -r .version <<<"$RUN")

# Confirm the identification — or {"action":"select","pack_code":"cap"} to override it.
curl -s -X POST $BASE/api/assemblies/$ID/pack -H "If-Match: $V" \
     -H 'Content-Type: application/json' -d '{"action":"confirm"}' | jq '.state, .unresolved'

# Accept the deck list scan it proposed, if there was one.
curl -s -X POST $BASE/api/assemblies/$ID/decklist -H "If-Match: <version>" \
     -H 'Content-Type: application/json' -d '{"action":"confirm"}' > /dev/null

# Build it. Add {"save_as":"a name"} if you supplied a file or omitted a card.
curl -s -X POST $BASE/api/assemblies/$ID/confirmation -H "If-Match: <version>" \
     -H 'Content-Type: application/json' -d '{}' | jq .state

curl -s -o cap.pdf $BASE/api/assemblies/$ID/document
```

Every mutating call carries `If-Match` with the run's current version — two tabs answering
two questions about one run is a lost update otherwise. `page_size` and `fit_mode` go on the
initial `POST` and default to `LETTER` and `CROP`.

**Generating a prebuilt deck:**

```bash
curl -s -X POST $BASE/api/generations -H 'Content-Type: application/json' \
  -d '{"deck_id":"captain-america","page_size":"LETTER","fit_mode":"CROP"}'
curl -s $BASE/api/generations/<id>                       # status, progress, substitutions
curl -s -o deck.pdf $BASE/api/generations/<id>/document   # once status is "succeeded"
```

The running service serves its own contract at `/openapi.json`, with interactive docs at
`/docs`. The reviewed contracts live in
[`specs/002-starter-deck-assembly/contracts/openapi.yaml`](specs/002-starter-deck-assembly/contracts/openapi.yaml)
and
[`specs/001-hero-deck-pdf-wizard/contracts/openapi.yaml`](specs/001-hero-deck-pdf-wizard/contracts/openapi.yaml).

## Troubleshooting

| What you see | What it means |
|---|---|
| `The prebuilt deck list is not configured yet` | `MARCHAMP_IMAGE_DIR` or `MARCHAMP_CATALOG` is unset. **Not fatal** — pack assembly is unaffected and the server starts. |
| `The prebuilt deck list points at something that is not there` | Both are set, but a path is wrong. A different problem with a different fix, so it reads differently. |
| `address already in use` | Something is already on the port. Use `--port`, or stop the other process. |
| Deck list is empty | The catalog parsed but defines no decks. Check `/api/catalog/validation`. |
| The pack it identified is wrong | Pick the right one from `GET /api/assemblies/{id}/packs`. A refusal to guess is a prompt, not a dead end. |
| Cards it could not find | Each is named with where it looked. Supply a file, or print without it — but it will not print one silently. |
| `card data could not be retrieved and none is stored` | MarvelCDB is unreachable and this pack has never been fetched. It refuses rather than guessing what the pack contains. With a cached copy it runs and tells you the data is stale. |
| The state directory and library overlap | Your state directory is inside your scan library. Move it — the library is a synced folder and must never be written to. |
| Cards print the wrong size | Printer scaling. Print the calibration page and measure it before blaming the PDF. |

## Development

```bash
uv run pytest -m "not physical"   # the suite CI runs
uv run pytest -m physical         # needs the mounted library, a printer, a ruler
uv run ruff check .               # lint
uv run ruff format .              # format
```

The `physical` tests are skipped unless `MARCHAMP_REAL_LIBRARY` points at a real scan
library; one of them also needs a printer, and is scored against
[`specs/002-starter-deck-assembly/physical-uat.md`](specs/002-starter-deck-assembly/physical-uat.md).

Tests are mandatory here, not optional — see
[`.specify/memory/constitution.md`](.specify/memory/constitution.md), Principle I. Test
fixtures generate their own synthetic card images; **real card art must never enter this
repository**, which is why `card_directory/`, `*.tif`, `*.tiff`, and `*.pdf` are all
gitignored.

Contributing conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); security reporting is
in [SECURITY.md](SECURITY.md).
