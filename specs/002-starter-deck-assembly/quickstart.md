# Quickstart & Validation: Hero Pack Printing from a Scan Library

Runnable scenarios that prove the feature works end to end. Each names the requirements and
success criteria it discharges, so a scenario that cannot be run is a gap with an owner rather
than a gap.

Details are not repeated here — entity fields are in [data-model.md](./data-model.md), the
interface is in [contracts/openapi.yaml](./contracts/openapi.yaml), and the measurements behind
the design are in [research.md](./research.md).

## Prerequisites

```bash
uv sync --all-groups
```

**No environment variable is required to assemble a pack.** `MARCHAMP_IMAGE_DIR` and
`MARCHAMP_CATALOG` are feature 001's and are unset in every scenario below — that is SC-003a,
not an omission. `serve` must start without them for this feature's paths (FR-005).

```bash
uv run marchamp serve          # 127.0.0.1:8765
```

Two things the scenarios read, and where they come from:

| | |
|---|---|
| **The derived fixture library** | `tests/fixtures/library/` — the real library's filenames and folder layout over generated placeholder images. No card art, no MarvelCDB card text (FR-038a). What CI runs against. |
| **The real library** | The user's mounted Drive folder. Never named in this repository (it is public); supplied per run. Only V2 and V12 need it. |

Upstream responses are recorded fixtures in every scenario except V12. **CI makes no network
call**, which is both a correctness property and a courtesy to a volunteer-run service.

---

## V1 — Print a pack from a folder, with nothing configured

*Discharges: FR-005, FR-006, FR-013, FR-015, FR-016, SC-001, SC-003a, SC-002a*

```bash
unset MARCHAMP_IMAGE_DIR MARCHAMP_CATALOG

curl -s -X POST localhost:8765/api/assemblies \
  -H 'content-type: application/json' \
  -d '{"library_root":"'"$PWD"'/tests/fixtures/library",
       "hero_folder":"Heros/Steve Rogers_Captain America"}'
```

**Expect**: `202`, a `Location` header, `state: awaiting_pack`, `identification.pack_code: "cap"`
with its evidence — and **`unresolved: []` because nothing has been resolved yet**. Confirmation
comes first (V3).

After confirming and finishing the run:

- Every card in the `cap` listing is printed, each as many times as `quantity` records.
- **34 cards, 59 copies** — the measured figures for `cap`. No total is expected and none is
  warned on.
- One PDF, in the order player cards → identity → nemesis → decklist.

**Fails if** the service refuses to start without `MARCHAMP_IMAGE_DIR`, or if a second run
naming a different folder requires a restart or reconfiguration (US1 scenarios 6 and 7).

---

## V2 — The ten acceptance heroes

*Discharges: SC-002, SC-003, SC-003b, SC-003c*

```bash
uv run pytest tests/integration/test_acceptance_heroes.py     # fixtures, in CI
uv run pytest -m physical tests/integration/test_real_library.py   # real scans, local only
```

| Set | Heroes | What it proves |
|---|---|---|
| SC-002 | Captain America, Star-Lord, Wasp, Hulk | Resolve cleanly from their own folders plus reprint links |
| SC-003 | Thor, Black Widow, Ant-Man, Ms. Marvel | Need whole-library search and the name fallback |
| SC-003c | Phoenix, Wonder Man | **Carry no usable positions at all** — the copy-counting filename convention |

SC-003c is the one that decides whether the design is right. Those two folders resolve almost
nothing under positional matching, so they exercise FR-023's name fallback as the *primary*
path rather than as a safety net. A change that quietly weakens name matching passes every
other scenario here and fails this one.

The real-library runs are marked `physical` and never run in CI — neither the card art nor the
mount exists there (SC-003b). They are acceptance evidence, not a substitute for the fixture
runs, which is why both rows exist.

---

## V3 — The pack is confirmed before anything is resolved

*Discharges: FR-012a, FR-012b, SC-009, SC-009a*

```bash
RUN=$(curl -s -X POST .../api/assemblies -d '{...}' | jq -r .id)
V=$(curl -s .../api/assemblies/$RUN | jq -r .version)

# Confirm what the tool identified
curl -s -X POST .../api/assemblies/$RUN/pack -H "If-Match: $V" \
     -d '{"action":"confirm"}'
```

**Expect** before confirming: `state: awaiting_pack`, no resolutions, no PDF. Any attempt to
reach `/confirmation` from here is `409`.

Then the three ways the identification can be wrong, all of which must end in a printable pack:

| Case | Path | Expect |
|---|---|---|
| Identified and correct | `{"action":"confirm"}` | `resolving`; report says `identified` |
| Identified and **wrong** | `{"action":"select","pack_code":"..."}` | `resolving`; report says `user_selected` |
| Refused as too weak, or unidentifiable | `GET .../packs`, then `select` | Same as above — a refusal is a prompt, not a dead end |

**Fails if** a run in `unidentified` has no route forward. That leaves the user holding a
perfectly good folder and no way to print it, which is the failure FR-012b exists to prevent.

---

## V4 — Cards the scanner skipped are recovered from the printing they duplicate

*Discharges: FR-014, FR-022, FR-024, SC-005, US1 scenarios 2 and 4*

Captain America's folder omits eight physical cards that were already in the Core Set. They
must still print, sourced from the printing they duplicate.

```bash
curl -s .../api/assemblies/$RUN | jq '.report.resolutions[] | select(.provenance=="reprint")'
```

**Expect**: Make the Call, The Power of Leadership, Mockingbird, Energy, Genius, Strength —
each naming the file and the printing it came from.

**And the count follows the pack being printed, not the pack the image came from** (FR-016).
Make the Call is `quantity: 2` in `cap`; it prints twice here regardless of how many copies the
Core Set ships. This is the assertion that would have caught the design error the whole feature
was respecified around.

**Fails if** any resolution with `provenance != "folder_position"` is missing from the report.
SC-005 is 100%: no substitution is silent.

---

## V5 — Faces come from two mechanisms, and both are needed

*Discharges: FR-015a, FR-015f, FR-018, SC-006a, US1 scenarios 10, 10a, 10b*

```bash
uv run pytest tests/unit/test_faces.py
```

| Case | Card | Expect |
|---|---|---|
| Linked codes | `cap` `03001a` → `03001b` | 1 card, 2 faces |
| Three faces | `ant` `12001a`(→`12001b`) and `12001c`, **both at position 1** | 2 records, 3 faces |
| `double_sided` flag | `vision` `26002` Intangible | 1 card, 2 faces |
| Missing back | Intangible with only its `_2a` file | **Run stops**, naming the card |

The first and third rows use different upstream mechanisms. A face expansion that handles only
one of them prints Captain America front-only, reports the run clean, and is caught by no other
scenario here — which is why this one asserts both.

The report states **34 cards / 59 copies / N faces** for `cap`: FR-018's unit is cards, with the
face count alongside because the page count follows from it.

---

## V6 — A card that resolves to nothing stops the run

*Discharges: FR-017, FR-025, FR-030, FR-030a, FR-030b, SC-006, SC-006e*

```bash
uv run pytest tests/integration/test_incomplete.py
```

| Given | Then |
|---|---|
| A pack card with no image anywhere | `state: awaiting_cards`, the card named, **no PDF** |
| A *nemesis* card with no image | Identical treatment — every pack card is held to the same bar |
| The user asks to print without it, explicitly | Prints; the card is named in the report, counted against `cards_in_pack`, and written to the log |
| That request arrives **before** the run has reported | `409` — a blanket permission is refused, not honoured |

The last row is FR-030a and is easy to lose: a decision taken before the gap is known is not an
informed one. The test asserts the `409` *and* that the run still stops on the first card it
cannot resolve afterwards.

SC-006 is 100%: no combination of inputs yields a pack printed with a card missing and no one
having said so.

---

## V7 — Reuse, and the three things that invalidate it

*Discharges: FR-026h, FR-026i, SC-006i, SC-006k, US1 scenarios 15, 15a, 15b, 16*

```bash
uv run pytest tests/integration/test_reuse.py
```

| Scenario | Expect |
|---|---|
| Same pack, same snapshot, same resolved images | Stored PDF served; **no render** (~49 s avoided) |
| Library folder **moved or renamed**, images identical | Still served — the key is content, not path (SC-006h) |
| A second library resolving **one** card differently | **Rebuilt** (SC-006k) |
| Snapshot refreshed to a new revision | **Rebuilt** |
| The run was customized at all | Never becomes the pack's standard PDF; user names it |

Reuse skips the render, **not the resolve** — the third row is only decidable by resolving
first, and FR-026h says so in terms. A test asserting that reuse is instant end to end is
asserting the wrong thing and will fail correctly.

---

## V8 — Determinism, verified without reuse

*Discharges: FR-045, SC-007, constitution Principle V*

```bash
uv run pytest tests/integration/test_determinism.py
```

Assemble the same pack twice from the same library and snapshot **with reuse disabled**, and
compare bytes.

**This scenario is worthless if it runs with reuse on**: serving one stored file twice proves
only that a file was stored. FR-045 requires determinism to be verifiable independently of
FR-026h, and disabling reuse is what makes the test say what it claims.

---

## V9 — Put a run down, restart, pick it up

*Discharges: FR-026b, FR-026c, FR-026e, SC-006b, SC-006f, SC-006g, US5*

```bash
uv run pytest tests/integration/test_resume.py
```

1. Start a run whose library lacks two cards → `awaiting_cards`, both named.
2. Upload a file for the first (`POST .../cards/{code}/image`).
3. **Restart the application.**
4. `GET /api/assemblies` → the run is listed as unfinished, without the caller having recorded
   an identifier anywhere (SC-006g).
5. Resume: the hero folder, the confirmed pack, the pinned snapshot revision, the first card's
   resolution, and the report are all intact. Only the second card is asked about (US4 sc. 8).
6. Move or delete the uploaded source file on disk, then reprint → **the card still prints**,
   because the run holds the bytes (FR-026e, US4 scenario 4).

Step 6 is the reason uploads exist rather than paths, and it is the step that fails if the run
records a path and reads it later.

---

## V10 — Deleting a run and reclaiming space are different acts

*Discharges: FR-026f, FR-026g, FR-026g1, SC-006h, US5 scenarios 5, 6, 6a, 6b*

```bash
uv run pytest tests/integration/test_retention.py
```

| Act | Expect |
|---|---|
| Unmount the library, re-download a finished run's PDF | Succeeds — a finished run depends on nothing outside itself |
| Delete a run that produced a pack's **standard** PDF | Its uploads go; **the standard PDF survives** and other runs still download it |
| Delete that standard PDF from `/api/pdfs` | The bytes return to the operating system; the next assembly rebuilds |
| Delete a run that produced a **saved** PDF | Both go |

Row two is FR-026g1 and is the one an implementation gets wrong by treating a PDF as owned by
its producing run. `os.link` refcounting makes it a property of the layout rather than an
invariant someone maintains — the test asserts the freed bytes, not just the absent file.

---

## V11 — Conduct toward MarvelCDB

*Discharges: FR-003, FR-038, FR-038a, FR-039, FR-040, FR-041, FR-042, FR-043, FR-044a, FR-046, SC-006d*

```bash
uv run pytest tests/unit/test_upstream.py tests/integration/test_snapshots.py
```

| Assertion | Requirement |
|---|---|
| Assembling a 34-card pack issues **2** requests (pack index, pack cards) — not 34 | FR-040, SC-006d |
| A second run against a snapshot inside `max-age` issues **zero** | FR-039, SC-006d |
| Past `max-age`, one conditional `If-Modified-Since`; a `304` keeps the revision | FR-039, R8 |
| No request is ever made to a host other than `marvelcdb.com` | FR-003 |
| Redirects are not followed; loopback, link-local, and private ranges are refused after resolution | Constitution egress |
| The `User-Agent` names the application and a contact | FR-041 |
| A `429` or `5xx` backs off, retries at most twice, and never increases load | FR-042, FR-043 |
| Unreachable **with** a stored snapshot → runs, reporting a stale revision | FR-044a |
| Unreachable **without** one → refused, naming the pack | FR-046 |
| Committed fixtures carry no card art and no card text | FR-038a |

The last row is checkable mechanically and should be: the repository is public, and FR-038a
governs fixtures as much as runtime. A grep for retained-but-forbidden fields in
`tests/fixtures/` belongs in this test, not in a reviewer's memory.

---

## V12 — Print one and build the deck from paper

*Discharges: SC-002a, SC-002b, FR-013b, FR-015d, FR-015e, SC-006j*

Local only, against the real library, with a printer.

```bash
uv run pytest -m physical tests/integration/test_physical_pack.py
```

1. Assemble Captain America and print the PDF.
2. Cut the sheets.
3. **Sort the cut cards using the report alone** — which are player cards, which is the
   identity card, which form the nemesis set, which is the decklist. FR-015d packs the groups
   together with no page break, so a page carrying the last player cards and the first nemesis
   cards is correct; the report is the only thing that tells them apart (FR-015e).
4. **Build the starter deck by reading the printed decklist card**, not by asking the tool.
   That is FR-013a: deriving deck membership was attempted, measured, and found to produce a
   silently wrong deck.
5. Play it without owning the pack.

**Page count** must be the fewest the card count allows: no page before the last is partly
empty, and the identity card, nemesis set, and decklist cost no more pages than their card
count requires (SC-002b).

For a hero folder holding no decklist scan (25 of 60), the run names the gap and offers the
Hall of Heroes address, the user downloads the image and uploads it, and **the application
never fetches it** (FR-013c). A pack printed without one still prints, and says so (SC-006j).

---

## What this quickstart deliberately does not test

- **Render time.** Feature 001's SC-007 and SC-007a are knowingly missed — 48.9 s and 202 MB
  against a 30 s target, measured, reviewed, and accepted. This feature does not reopen them and
  no scenario here asserts a duration.
- **Deck size.** Nothing checks for 40 cards, or any total. Pre-built decks measured 40, 41, and
  42; pack sizes vary independently. FR-018 forbids expecting a total and forbids warning on one,
  and `pack.total` from the upstream index was measured to disagree with the summed quantity for
  two of three packs — a check would have produced a false alarm on most of them (research R12).
- **Deck membership.** The tool prints packs. Selecting the starter deck is the user's task,
  performed against the printed decklist card (FR-013a).
