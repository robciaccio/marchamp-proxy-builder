# Quickstart & Validation: Hero Deck PDF Wizard

How to run the feature and prove it works. Scenarios map to acceptance criteria in
[spec.md](./spec.md); entity and endpoint detail lives in [data-model.md](./data-model.md)
and [contracts/openapi.yaml](./contracts/openapi.yaml) rather than being repeated here.

## Prerequisites

1. **Python 3.13** and [uv](https://docs.astral.sh/uv/).
2. **A local card image directory.** Sync or download the Drive folder of TIFFs first. The
   application never fetches these itself (FR-019).
3. **A content catalog file** mapping cards and decks to image filenames. Authoring it is
   outside this feature's scope.

### Verify source resolution before anything else

FR-010 requires ≥300 DPI at final print size — **at least 750 × 1050 px** per card at
63.5 × 88.9 mm. If the scans fall short, the requirement fails and either the DPI floor or
the card size has to change. This is a spec decision, so find out before writing render
code:

```bash
sips -g pixelWidth -g pixelHeight -g dpiWidth "/path/to/images/some-card.tif"
```

Check a handful across different packs, not just one.

## Setup

```bash
uv sync --locked          # frozen install; a build that would alter the lockfile must fail

export MARCHAMP_IMAGE_DIR="$HOME/path/to/card-images"
export MARCHAMP_CATALOG="$HOME/path/to/catalog.json"

uv run marchamp serve     # binds 127.0.0.1:8765
```

Open <http://127.0.0.1:8765>.

## Validation scenarios

### V1 — Catalog validation reports everything at once (FR-005c, FR-005d, SC-010)

```bash
curl -s http://127.0.0.1:8765/api/catalog/validation | jq
```

**Expect**: `valid: true` for a good catalog. For a broken one, `valid: false` with *every*
problem listed — a missing image file, an unknown card reference, and a bad quantity all
appear together, each naming the offending card or deck. Stopping at the first error is a
failure of this scenario.

### V2 — Deck list comes from the catalog, not the code (FR-001, FR-004, SC-009)

```bash
curl -s http://127.0.0.1:8765/api/decks | jq '.decks[] | {id, name, card_count}'
```

**Expect**: every deck in the catalog. Now add a deck to the catalog file, restart, and
re-run — it appears with no rebuild and no reinstall.

### V3 — Generate a deck end to end (US1, FR-008)

```bash
GEN=$(curl -s -X POST http://127.0.0.1:8765/api/generations \
        -H 'content-type: application/json' \
        -d '{"deck_id":"captain-america","page_size":"LETTER"}' | jq -r .id)

curl -s http://127.0.0.1:8765/api/generations/$GEN | jq '{status, page_count, card_count}'
curl -s -o deck.pdf http://127.0.0.1:8765/api/generations/$GEN/document
```

**Expect**: status reaches `succeeded`; `card_count` counts quantities, not distinct cards;
`page_count` is `ceil(card_count / 9)`; `deck.pdf` opens.

### V4 — Printed geometry is correct (FR-009, FR-011, SC-003)

Automated check on the PDF itself, which is what the constitution requires instead of
looking at it:

```bash
uv run pytest tests/integration/test_print_geometry.py -v
```

**Expect**: MediaBox equals the selected page size in points, portrait (Letter =
612 × 792 pt); every **slot** measures 63.5 × 88.9 mm within ±0.5 mm; nine slots per full
page in a 3 × 3 grid, centred; no cut guide enters a slot.

Printed **face** size depends on the fit mode, and the assertions differ accordingly:

| Mode | Expected face | Also assert |
|---|---|---|
| `CROP` | 63.5 × 88.9 mm ±0.5 | Fills the slot; overflow trimmed equally top and bottom |
| `FIT` | 61.8 × 88.9 mm ±0.5 | Neither dimension exceeds the slot; unused area blank, no frame |
| `STRETCH` | 63.5 × 88.9 mm ±0.5 | Fills the slot; nothing trimmed |

Then the physical check that no test can perform — print page 1 at **100% scale with page
scaling off** and measure a card with a ruler.

### V4b — Compare fit modes on paper (FR-009b, SC-009a)

The scans are 2.7% taller in proportion than a standard card, and which compromise looks
right cannot be judged on screen. Generate all three and print one page of each:

```bash
for MODE in CROP FIT STRETCH; do
  ID=$(curl -s -X POST http://127.0.0.1:8765/api/generations \
        -H 'content-type: application/json' \
        -d "{\"deck_id\":\"captain-america\",\"fit_mode\":\"$MODE\"}" | jq -r .id)
  curl -s -o "deck-$MODE.pdf" "http://127.0.0.1:8765/api/generations/$ID/document"
  echo "$MODE -> deck-$MODE.pdf"
done
```

**Expect**, measuring page 1 of each after printing at 100%:

| Mode | Card face | Look for |
|---|---|---|
| `CROP` | 63.5 × 88.9 mm | Is anything important lost at the top or bottom edge? |
| `FIT` | 61.8 × 88.9 mm | Does the backing card showing at the sides bother you? |
| `STRETCH` | 63.5 × 88.9 mm | Can you actually see the 2.7% squash? |

Sleeve one card from each in front of a real card before deciding. **When a winner emerges,
make it the default and reconsider removing the others** — this toggle exists to answer a
question, not to persist.

> The step-by-step protocol for actually doing this on paper — what to measure, what each
> mode costs in millimetres, and where to record the answer — is
> [physical-uat.md](./physical-uat.md), Session B.

### V4c — Pack art preferred, stand-ins reported (FR-005f–j, SC-012)

The Captain America pack folder is missing six cards that exist in the Core Set under
different numbers, so this path is exercised by the very first real deck.

```bash
curl -s http://127.0.0.1:8765/api/generations/$GEN | jq '.substitutions'
```

**Expect**: with complete pack art, `[]`. With the six Core Set stand-ins in place, six
entries naming each card, the pack whose art was wanted, and the pack used instead — visible
*before* downloading, not afterwards in a log.

Then confirm determinism survives it (FR-005j): regenerate and diff. A card with several
available stand-ins must pick the same one every time.

```bash
uv run pytest tests/integration/test_printing_fallback.py -v
```

**Expect**: preferred printing wins when present; a deterministic stand-in when absent; a
**failure naming the card** when no printing of it is usable — falling back covers missing
art, never a missing card.

### V4d — Double-sided hero yields two faces (FR-012a–c, SC-013)

```bash
curl -s http://127.0.0.1:8765/api/decks/captain-america | jq '.card_count'
```

**Expect**: **42**, not 41 — 40 single-sided player cards plus a double-sided hero counting
twice. The hero and alter-ego faces appear in adjacent slots.

Physically: cut both faces, sleeve them back-to-back around one dummy card, and confirm the
card flips in play like the real one, with each side showing outward.

### V5 — Preview matches the PDF exactly (FR-017, SC-005)

```bash
curl -s -o page1.png "http://127.0.0.1:8765/api/generations/$GEN/pages/1?width=800"
```

**Expect**: page count from the preview endpoint equals the PDF's; card order and position
match page for page. They are rasterised from the same bytes, so a mismatch means a real
defect, not a rendering difference.

### V6 — Byte-identical regeneration (FR-015, SC-006)

```bash
uv run pytest tests/integration/test_determinism.py -v
```

**Expect**: the same deck at the same catalog revision produces identical bytes, both
within one process and across two — the cross-process run is what catches hash-ordering
effects.

### V7 — Works with no network (FR-019a, SC-001b)

Turn networking off entirely, then re-run V3.

**Expect**: full success. Any failure here means something is reaching out that should not
be.

### V8 — Failures name the specific card (FR-020, FR-021, SC-008)

Temporarily rename one image file referenced by the deck, then re-run V3.

**Expect**: status `failed`; `failure.card_name` names the card; `failure.kind` is
`asset_missing`; `retryable` is `false`; **no document is downloadable**. A partial PDF, a
placeholder card, or a generic error each fail this scenario.

For the retryable case, point `MARCHAMP_IMAGE_DIR` at a cloud-sync folder whose files are
placeholders not yet materialised: expect `asset_unreadable` with `retryable: true`.

### V9 — Not reachable from another machine (FR-0A2, SC-001a)

From a second device on the same network:

```bash
curl -m 5 http://<this-machine-ip>:8765/api/health
```

**Expect**: connection refused or timeout. A response is a defect — the service must bind
loopback, not depend on a firewall.

### V10 — Calibration page (US3, FR-023)

```bash
curl -s -o calibration.pdf http://127.0.0.1:8765/api/calibration
```

**Expect**: printed at 100%, the ruler measures true within ±0.5 mm and a real Marvel
Champions card laid over the outline matches within ±0.5 mm on all four sides. Print this
*before* a full deck.

> This is Session A of [physical-uat.md](./physical-uat.md), and it gates every other
> physical measurement — if the scale is wrong, every millimetre measured later is wrong by
> the same factor.

### V11 — Live API matches the contract (Principle II)

```bash
uv run pytest tests/contract/ -v
```

**Expect**: the running service's generated OpenAPI matches
[contracts/openapi.yaml](./contracts/openapi.yaml). This test failing means the contract
drifted and one of the two must be corrected — it is a required merge gate.

### V12 — Measured generation performance (SC-007, SC-007a)

Measured on a real ~41-card hero deck on the development laptop, default fit mode, Letter.

| Measure | Target | Measured | Verdict |
|---|---|---|---|
| First preview page viewable (SC-007a) | 5 s | **10.5 s** | missed, 2.1× |
| Whole deck generated (SC-007) | 30 s | **48.9 s** | missed, 1.6× |
| Peak resident memory for the run | *(no target)* | **202 MB** | within FR-0A4's 512 MB per-image ceiling |

**Both targets are missed, and both misses were reviewed and accepted.** This is recorded
as a known trade-off rather than left open as a defect, on this reasoning:

- The tool is **local-only** (FR-0A1). The wait is one person's own machine doing one
  person's own job, once per deck — not a shared service where queuing costs compound
  across users.
- The generation stays well inside FR-0A4's hard ceilings — 48.9 s against the 120 s
  cutoff, 202 MB against the 512 MB per-image limit — so nothing here risks destabilising
  the machine or truncating output. SC-007 is a target for typical work; FR-0A4 is the
  limit that actually fails a generation, and it is not close.
- The work being paid for is real: full-resolution decode of ~42 source faces at 600 DPI,
  which is what FR-010's 300 DPI floor and the no-upscaling rule require.

**Do not optimise this unprompted.** Reopening it means re-running this measurement and
changing this table, not treating the numbers as a bug report. If a future change makes a
generation *slower* than the figures above, that is a regression worth raising; matching
them is the expected result.

## Full gate before opening a PR

```bash
uv run pytest                        # all tests, including geometry and determinism
uv run ruff check . && uv run ruff format --check .
gitleaks git . --redact -v --log-opts="--all"
```
