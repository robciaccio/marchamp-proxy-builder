# Phase 0 Research: Starter Deck Assembly from a Scan Library

Every decision below is driven by a requirement in [spec.md](./spec.md) or a gate in the
constitution. Upstream facts were measured against the live MarvelCDB API on **2026-08-16**,
not recalled; the commands are reproducible from [quickstart.md](./quickstart.md).

The stack is already fixed by constitution v1.2.0, so this is not a stack-selection pass. What
was genuinely open: how to read MarvelCDB conservatively, how to identify a pack, where durable
state lives, and how to reuse feature 001's pipeline without a second rendering path.

**R6 is the section to read first.** It records the measurement that ended this feature's
original design — deriving which cards form the pre-built starter deck — and sent the spec to
printing whole packs instead.

**R0, R12, R13, and R14 were added on 2026-08-17** during the planning pass. R0 records a
contradiction between four requirements that planning surfaced and the spec then absorbed; R12
records a second measurement pass against the live API that changed two design details.

---

## R0 — The spec names one folder where the design needs two

**Raised during planning; resolved in the spec on 2026-08-17** rather than left as a divergence.
Four requirements could not all hold together.

- **FR-005** — the user names a folder per run; nothing is configured in advance.
- **FR-007** — "the named folder MUST be the containment boundary: every asset reference MUST
  resolve inside it".
- **FR-021** — when a positional match fails, "the tool MUST search the **whole library**".
- **FR-031** — the report accounts for "every file in the folder named for the run" in full, and
  explicitly says accounting for all 4,447 library files would be unreadable and untestable.
- **User Story 1's independent test** points the tool at `Heros/Steve Rogers_Captain America/`.

FR-031 settles that "the named folder" is the *hero folder*. But then FR-021's whole-library
search reads files outside FR-007's containment boundary on every run — and User Story 3 exists
entirely to require that (`Quincarrier` under Wasp, `Teamwork` under `Aspects/Leadership/`).
Both cannot be true.

**Decision**: a run names **two** paths, and neither is configured in advance, so FR-005 and
SC-003a hold unchanged:

| Input | Role |
|---|---|
| `library_root` | FR-007's containment boundary, and the extent of FR-021's search. The mounted Drive folder. |
| `hero_folder` | A path **relative to** `library_root`. What FR-010 identifies the pack from, and the folder FR-031 accounts for file-by-file. |

Every asset reference still resolves inside a boundary chosen per run — the boundary is the
library root rather than the hero folder. Nothing widens what the application reads beyond what
FR-021 already requires it to read, and the spec's own assumption that naming a folder per run
"widens what the application will read, deliberately" covers it on the same grounds: the service
is loopback-only, and the person naming the folder is the person running the process.

**Carried into the spec on 2026-08-17.** FR-005, FR-006, FR-007, FR-008, FR-009, FR-013b,
FR-013c, FR-026h, FR-027, FR-031, FR-032, SC-003a, and SC-004 were reworded to say which of the
two they mean, and the Key Entities gained a **Library root**. This was a wording defect rather
than a design disagreement — no requirement's intent was in question and no success criterion
moved — but a spec/artifact divergence is a review failure by this repository's own rule, so it
was not left standing.

**Alternative rejected**: deriving the library root by walking up from the hero folder to the
nearest ancestor containing `Heros/`. It is a guess about someone else's directory layout, it
fails silently when wrong, and it would put a path the user never named into a containment
decision.

---

## R1 — MarvelCDB: endpoints, caching, and the fields this feature needs

**Decision**: Use `GET /api/public/cards/{pack_code}.json` as the only bulk endpoint, plus
`GET /api/public/packs/` to validate a pack code and `GET /api/public/card/{code}.json` as a
narrow fallback (R4). Revalidate with `If-Modified-Since`.

**Measured** — response headers for `cards/cap.json`:

```text
cache-control: max-age=600, public
last-modified: Wed, 10 Jun 2026 14:21:35 GMT
```

There is **no `ETag`**. FR-039 therefore means: honour `max-age` (600 s) by not requesting at
all while fresh, and revalidate a stale copy with `If-Modified-Since` expecting `304`. Both
validators must be stored on the snapshot.

**Fields the feature resolves against** (the whole of what a snapshot may retain, per FR-038a):

| Field | Use |
|---|---|
| `pack_code`, `position` | The join key against filenames (FR-020) |
| `code` | Card identity, e.g. `03001a`. Its first two digits are the pack's numeric prefix — used in R4 |
| `name` | Display name and the *only* legitimate basis for a name match (FR-023) |
| `quantity` | Copies **in the pack** — see the warning below (FR-016) |
| `type_code` | Deck vs nemesis vs identity classification (FR-015) |
| `duplicate_of_code` | The reprint link (FR-014, FR-022) |
| `linked_to_code`, `linked_card.code` | The identity card's second face (FR-015a) |

`real_text`, `flavor`, `text`, `traits`, and `imagesrc` are **discarded on capture**. That is
FR-038a enforced at the point of ingest rather than at the point of commit: card text never
enters the process, so it cannot reach a fixture by accident.

> **`quantity` is a pack count, not a deck count.** Measured against the physical decklist cards
> on 2026-08-16: War Machine's pack holds two copies of Two Against the World and its pre-built
> deck uses one; Valkyrie's holds two of The Power of Aggression and its deck uses one. Because
> this feature prints *packs*, `quantity` is exactly the right number and needs no correction.
> Any future feature that outputs a starter deck directly MUST take its counts from the decklist
> card instead — using `quantity` there produces a deck with the wrong number of cards and no
> way to detect it. See R6.

**Alternatives considered**: `GET /api/public/cards/` returns every card in one request and
would be simpler. Rejected by FR-040 — it is a mirror of the whole database in all but name,
and the spec is explicit that only packs actually being assembled are retrieved. The
undocumented `/api/public/decklist/{id}.json` endpoints carry official starter decklists, but
only for the five Core Set heroes, and being undocumented they can disappear without notice.

## R2 — HTTP client and egress containment

**Decision**: `httpx` promoted from a dev dependency to a runtime one. One module owns every
outbound call, with `follow_redirects=False`, a fixed host allowlist of `marvelcdb.com`, a
descriptive `User-Agent`, a connect/read timeout, and `Retry-After`-aware backoff on 429/503.

**Rationale**: This is the first feature to make an outbound call, so the constitution's egress
gate moves from N/A to in force. Its requirements map directly: the destination is a constant,
not user-influenced, and the only user-derived component is `pack_code`, which is validated
against `^[a-z0-9_]{1,32}$` **and** against the pack list before it reaches a URL. Redirects
stay off, so a redirect to a private range is not a hole that needs closing — a `3xx` is an
error. `httpx` is already in `[dependency-groups] dev` for the API tests, so this promotes a
library the project already builds against rather than introducing a new one; `requests` would
be a genuinely new dependency for no gain.

**Caching is hand-rolled, deliberately.** Storing `max-age` and `Last-Modified` on the snapshot
record and comparing two timestamps is roughly thirty lines. `hishel` or `requests-cache` would
add a dependency and a second cache with its own eviction policy, when the snapshot store
(R7) already *is* the cache and must be, because runs pin revisions (FR-045).

**Alternatives considered**: `urllib.request` from the standard library avoids the dependency
entirely and is adequate for four call sites. Rejected because the test suite already uses
`httpx`'s transport mocking, and hand-rolling timeout and backoff on `urllib` is more code than
the dependency saves.

## R3 — Pack identification, and what makes it verifiable

**Decision**: Identify from the identity card, then verify by position agreement, then require
the user's confirmation regardless (FR-012a).

The algorithm, in order:

1. Parse positions from the folder's filenames (R5). The identity card is the file at
   position 1 whose name carries an `a` suffix or whose type word reads `Hero`.
2. Candidate packs are those whose snapshot has a `type_code: hero` card at position 1 whose
   `name` matches the folder's hero name — the folder is named `<Alter ego>_<Hero>`, and both
   halves are checkable against `name` and the linked `alter_ego` card's `name`.
3. **Verify**: of the folder's parseable positions, what fraction exist in the candidate pack
   with a compatible type? Agreement below a threshold refuses the run (FR-011).
4. Report the pack, the agreement figure, and the evidence; resolve nothing until the user
   confirms (FR-012a).

Step 2 needs candidate snapshots, which is a chicken-and-egg problem against FR-040's "only
packs being assembled". Resolved by fetching `GET /api/public/packs/` — 61 records, names and
codes only, no card data — and matching the folder's hero name against pack names first, which
narrows to one or two candidates before any card list is fetched.

**Measured**: all 61 packs, of which the eight acceptance heroes are `cap`, `stld`, `wsp`,
`hlk`, `thor`, `bkw`, `ant`, `msm`. Note the codes are abbreviations (`wsp`, not `wasp`;
`hlk`, not `hulk`; `msm`, not `msmarvel`), so a code cannot be guessed from a folder name and
the pack list is not optional.

## R4 — Reprint links, and resolving a borrowed image without a request per card

**Decision**: Follow `duplicate_of_code` to a card code, map its two-digit prefix to a pack,
and fetch **that pack's snapshot** — one request per pack, cached forever, never one per card.

**Measured**, the reprint links in the eight acceptance packs:

| Pack | Positions carrying `duplicate_of_code` | Physical copies |
|---|---|---|
| `cap` | 12, 16, 18, 20, 21, 22, 23 | 9 |
| `stld` | 16, 18, 31 | 6 |
| `wsp` | 15, 20, 21, 22, 23, 25 | 7 |
| `hlk` | 17, 20, 21, 22, 23, 24 | 7 |
| `thor` | 13, 16, 22, 23, 24, 25 | 8 |
| `bkw` | 14, 15, 16, 19, 20, 21, 22 | 10 |
| `ant` | 19, 21, 22, 23 | 5 |
| `msm` | 13, 16, 19, 20, 21, 22 | 8 |

Two findings that shape the design:

- **Reprints do not all point at the Core Set.** Wasp's `13020` duplicates `12020` (Ant-Man's
  pack) and `13025` duplicates `08023` (Black Widow's). FR-022's "both directions" is not
  hypothetical, and a Core-Set-only special case would be wrong.
- **`duplicated_by` is null on these records.** The link is one-directional in the pack
  response, so the reverse direction — "is this Core Set card reprinted in the pack I am
  assembling?" — is answered from the assembled pack's own records, never by searching upstream.

The prefix→pack map is learned lazily from snapshots already held (every `cap` card code starts
`03`), with `GET /api/public/card/{code}.json` as the fallback when a prefix is still unknown.
Request count per assembled pack is therefore bounded by the number of *distinct packs*
referenced — typically two — and is zero on every later run of that pack. This is what SC-006d
measures.

## R5 — Filenames: three conventions, one of which carries no position

**Decision**: Parse the trailing numeric component with two patterns, report anything matching
neither (FR-032), and never parse a card *name* out of a filename (FR-023).

The conventions, verified across eight hero folders:

| Form | Example | Position |
|---|---|---|
| `{faction}_{Name}_{Type}_{position}` | `Leadership_Teamwork_Event_16.tiff` | `16` |
| `{faction}_{Name}_{Type}_{position}_{set_position}.{set_total}` | `Wasp_Pym Particles_Resource_7_12.15.tiff` | `7` |
| Suffixed identity face | `..._Hero_1a`, `..._Alter-Ego_1b`, `..._Hero_Giant_1c` | `1`, face `a`/`b`/`c` |
| No position at all | `Basic_Invulnerability_Event.tiff` | none — name-matched only |
| **Leading number counting physical copies** | `2_Active Altruism_Event.tif`, `3_Active Altruism_Event.tif`, `4_Active Altruism_Event.tif` | **none** — the number is a copy index |
| **Decklist scan** | `Captain America Decklist.tif`, `0A_Wonder Man Deck List.tif`, `psylocke decklist.jpg` | **none** — see below |

**The decklist scan matches none of the conventions above**, measured 2026-08-17 across the
folders that hold one. The form is `<hero name> decklist.<ext>` or `<hero name> deck list.<ext>`,
space-separated, in `.jpg`, `.tif`, and `.tiff`. There is no position, no faction
prefix, and no type token, so a resolver following only this section files every decklist scan
under `unparseable` and reports it as an uninterpretable file in the one folder where FR-031
demands every file be accounted for. FR-013d therefore matches it on the stem containing
`deck\s*list` and excludes the match from both the unused and uninterpretable lists. The hero name
in the filename is deliberately not part of the rule: `iceman deck list.tiff` sits under
`Bobby Drake_Iceman`, so requiring agreement would fail on exactly the folders the rule exists to
serve. `.tif`/`.tiff` pairs of one stem are FR-034 duplicate renditions, not FR-033 conflicts.

**Corrected 2026-08-17 when T005 derived the fixture from the mounted library.** This section
originally transcribed the decklist filenames in lowercase (`captain america decklist.tif`). They
are not lowercase on disk — the real files are title-cased (`Captain America Decklist.tif`,
`Thor Decklist.tiff`) — so the match must be case-insensitive, which the `deck\s*list` stem rule
already implies but the examples above previously argued against. Two further observations the
original measurement missed, both load-bearing for T048a:

- **A decklist filename may carry a leading token.** Wonder Man's is `0A_Wonder Man Deck List.tif`.
  A rule anchored at the start of the stem misses it; the stem must be searched, not matched whole.
- **`iceman deck list.tiff` is not in the fixture.** Iceman is not one of the ten acceptance heroes,
  so the `deck list` spelling is carried into `tests/fixtures/library/` by Wonder Man's file
  instead. Both spellings do survive derivation, as T005 requires — but a test written against the
  Iceman filename asserts on a file that is not there.

The last form is the one that most easily produces a wrong answer rather than no answer, and it
was found late. The Phoenix and Wonder Man folders number files by *physical copy*: three files
for one card, numbered 2, 3, 4. Read as positions those numbers are confidently wrong. Both
folders resolve to almost nothing under position matching and depend entirely on the name
fallback, which is why SC-003c makes them an acceptance case in their own right.

Two folders also mix conventions: Phoenix and Wonder Man use copy-numbering for hero-set cards
while their aspect and basic cards carry no number at all. And a position can simply be wrong —
Vision's `Vision_Vivian_Ally_2.tiff` records position 2 for a card at position 3, colliding with
the genuinely double-sided `Intangible` filed as `_2a` / `_2b`. A resolver that trusts a parsed
position without checking it against the card it lands on will pick the wrong file here.

A file with no position is not an error and is not ignored: it enters a name index keyed on a
normalised form of the whole filename, consulted **only** when looking for a specific card whose
canonical MarvelCDB name is already known (FR-023). Normalisation must be lenient about the
observed typos — "Stength in Numbers", "Steve_s Apartament", "Upgarde" — which argues for a
case-folded, punctuation-stripped comparison with a **Levenshtein distance ≤ 2** (≤ 1 for
canonical names under 8 characters), the bound recorded in data-model.md § Library Index. All
three observed typos sit at distance 1–2, and stripping alone reaches none of them: "Stength" is a
dropped letter. Two candidates inside the bound are a conflict, not a pick. Reported as a name
match whenever it fires (FR-024, User Story 3 scenario 3).

`.tif`/`.tiff` duplicate pairs are resolved by sorting on `(extension, name)` and taking the
first, deterministically, with the duplication reported (FR-034). Two files claiming one
position in one folder are a conflict, reported with both sides and resolved by neither
(FR-033).

## R6 — Why deck-membership derivation was abandoned

**Decision**: print every card the pack listing records (FR-013). Do not attempt to identify
the pre-built starter deck (FR-013a). Print the pack's decklist card so the user selects the
deck from paper (FR-013b).

This reverses the feature's original design, and the reversal was driven by measurement rather
than preference. Recorded here in full because the next person to look at this will have the
same idea the first design did.

**Step 1 — an apparent regularity.** For all eight acceptance packs, the player-type cards
positioned before the first encounter-type card total exactly 40 copies. Eight for eight. The
packs looked to be laid out starter-deck-first, then the nemesis set, then the extra aspect
cards.

**Step 2 — it does not generalise.** Fetching all 61 packs killed it. Of the 26 single-hero
packs with a contiguous nemesis block, 18 give 40 and 8 do not: `warm`, `valk`, `vision`,
`phoenix`, `x23` and `wonder_man` give 41, `psylocke` 42, `iceman` 46. A further 16 single-hero
packs interleave encounter cards among player cards, so no band exists to measure — Hercules has
an encounter card at position 2. The eight acceptance heroes are all early packs, which is the
entire reason the pattern looked universal.

**Step 3 — the decklist cards settle it, and disprove two more things.** Read directly from the
scans in the library:

| Pack | Band predicted | Actual deck, from the printed decklist card |
|---|---:|---:|
| `warm` | 41 | **40** |
| `valk` | 41 | **40** |
| `vision` | 41 | **41** |
| `psylocke` | 42 | **42** |

Two conclusions, both fatal to the original design:

- **Pre-built decks are not always 40.** Vision ships 41 and Psylocke 42. Both legal — the rules
  permit 40 to 50. Any check that expects 40 produces false alarms on real packs.
- **MarvelCDB's `quantity` is a pack count, not a deck count.** War Machine's decklist lists
  `24 Two Against the World` once against a reported `quantity: 2`; Valkyrie's lists
  `23 The Power of Aggression` once against `quantity: 2`. That single discrepancy explains both
  41s. A tool that derived the deck and took counts from MarvelCDB would have printed War
  Machine as 41 cards — a plausible, legal, silently wrong deck.

**Why printing the pack is the answer rather than a workaround.** Every quantity question
becomes answerable from the pack listing, because the listing is precisely a description of a
pack. Nothing is inferred from folder structure. And the decklist card — the only authoritative
record of deck composition — is itself just a card, so the tool prints it and the user reads it
off paper. The earlier rejection of Hall of Heroes ("would require optical recognition") is
irrelevant once nothing reads the card.

**What this cost and what it bought.** Cost: ~60 faces per hero instead of ~48, so roughly 7
pages rather than 5–6, and a stricter completeness bar since the pack's extra aspect cards live
under `Aspects/` and must all resolve (FR-017). Bought: the deletion of membership inference,
the 40-card expectation, and the quantity-correction problem — none of which now exist to get
wrong.

**Classification still needed**, for grouping in the report (FR-015e) rather than for
membership: `hero` plus its linked `alter_ego` is the identity card; `obligation`, `side_scheme`,
`minion`, `treachery`, `attachment`, `environment` form the nemesis set; the decklist scan is its
own group; everything else is a player card.

## R7 — Durable state

**Decision**: One directory per run on the local filesystem, with an optimistic version field,
hardlinked shared PDFs, and blob-before-record write ordering. Recorded in full, with the
minority position, as [ADR-0001](../../docs/adr/0001-durable-run-state-on-the-filesystem.md).

Summarised here because the plan depends on it: a four-expert panel split 2–2 between plain
files and SQLite-for-metadata. Unanimous, and therefore load-bearing: blobs never go in SQL
rows (FR-026g's "reclaim the space" against 202 MB PDFs is decisive), the state directory lives
on local disk outside the Drive mount (SC-006h requires a finished run to survive the library
being unmounted), and the run store does **not** sit behind `assets.Store`.

`TODO(ASSET_TARGET)` stays open and is narrowed in writing to source assets and their
encodings. This feature chooses no object store and adds no output format.

## R8 — Reusing feature 001's pipeline instead of building a second one

**Decision**: Build an in-memory `Catalog` and one `HeroDeck` from the resolved assembly, then
call the existing `paginate` and `compose`. FR-048 requires exactly this; two findings make it
practical and one makes it a prerequisite.

- **Tight packing is already the behaviour.** `layout/paginate.py:95` chunks a flat face list
  nine at a time with no notion of groups, so feeding one ordered list of *player faces, then
  identity faces, then nemesis faces, then the decklist card* satisfies FR-015d and SC-002b **by
  construction**. There is nothing to build and nothing that could pad a boundary; the test
  asserts the property rather than a new code path.
- **The identity card's faces come from the data.** Measured: the identity is `type_code: hero`
  at position 1 with `linked_to_code` → an `alter_ego` card nested under `linked_card`. Wasp and
  Ant-Man carry a **second** `hero` record at position 1 (`13001c`, `12001c`) with no link —
  that is the third face FR-015a exists for. Note that `double_sided` is `false` on all of
  them: 001's `double_sided`/`image_back` pair models the hero/alter-ego pair, and a third face
  is a further card entry. Face count is read, never assumed.
- **Prerequisite: reads must go through the asset adapter.** FR-004 requires it, and the code
  does not do it today — `assets/local_dir.py` is exercised only by `tests/unit/test_assets.py`,
  while `render/document.py:130`, `catalog/printings.py:43`, and `catalog/validation.py` all
  join `image_dir / ref` directly. This is not tidying: an uploaded file (FR-026e) lives in the
  run's own directory, outside the named library, so composition must read through a store that
  can overlay the two. Routing 001's three call sites through the `Store` protocol is what makes
  uploads possible without a second read path — and it finally makes the Principle III seam
  load-bearing rather than decorative.

The overlay is a small composite store: refs prefixed `upload:` resolve inside the run
directory, everything else inside the named library folder, each with its own containment check
(FR-007 for the library; the run directory needs no user-supplied path at all).

## R9 — Uploads

**Decision**: `multipart/form-data` to a per-card endpoint. `python-multipart` is added as a
runtime dependency — FastAPI requires it for `UploadFile` and refuses to start a route using
one without it.

The same endpoint carries the decklist card when the folder has no scan of one (FR-013c), so
that path needs no new mechanism — the run names the gap, offers the Hall of Heroes address, and
accepts the file the user fetched. The application makes no request for it, which is what keeps
FR-002 intact and the egress allowlist at one host. A Hall of Heroes photograph will very
likely fall below the print-resolution floor and trip FR-035's warning; that is the correct
outcome and must not be special-cased into silence.

Validation reuses `render/images.validate_source`, which already enforces decode-by-content and
the print-resolution floor, so FR-028's "manual choice bypasses discovery, never validation" is
satisfied by calling the code 001 already has. The upload is streamed to a temporary file under
a byte ceiling before decode, so a hostile file is bounded before Pillow sees it; the stored
name is the content SHA-256, and the record keeps only the **uploaded file's own name** — never
a path — which is what lets FR-027 and FR-009 both hold.

## R10 — Determinism with uploads, snapshots, and reuse

**Decision**: SC-007's byte-identical guarantee is verified by *regeneration*, explicitly not by
serving a stored PDF (FR-045 says so directly).

Three new non-determinism sources appear in this feature and each is closed: the deck's card
order is sorted on `(pack_code, position, code)` rather than on directory listing or dict
iteration; the snapshot revision is a content hash of the reduced snapshot, computed the way
`catalog/loader.py` already computes the catalog revision, so it is stable across refetches
that changed nothing; and an uploaded file participates by content, since its ref is its
SHA-256. The determinism test assembles the same run twice with the reuse path disabled and
compares bytes.

## R11 — CI fixtures derived from the real library (FR-038a)

**Decision**: A generator script reproduces the acceptance heroes' **filenames and folder
layout** over synthetic images, alongside reduced snapshot fixtures carrying only the seven
fields in R1. The set is the original eight plus **Phoenix and Wonder Man** (SC-003c), which
carry the copy-counting convention from R5 and are the only fixtures that exercise the name
fallback as the sole resolution path.

The set is not only hero folders. A reprint resolves to an image of *another* printing, so the
Core Set folder is fixture material in its own right, and the pack's extra aspect cards live under
`Aspects/` by design — both are derived alongside the ten heroes, or the reprint path (T043, T058)
and the whole-library search (T079) have nothing to assert against.

Eight of the ten hold a decklist scan and **Hulk and Phoenix hold none** (measured 2026-08-17), so
the derived fixture covers both FR-013d's match and FR-013c's gap without contriving either. The
filenames must survive derivation verbatim — `deck list` and `decklist` are different spellings
and the pattern is only tested if both appear.

`tests/conftest.py` already establishes the pattern and the reason — every image is generated,
never copied. The extension is that filenames are now data under test, so the fixture must
carry the real awkwardness verbatim: the typos, the two conventions, the missing positions, the
`.tif`/`.tiff` pairs, Ant-Man's duplicate position 7, and Quincarrier filed under Wasp. None of
that is card artwork or card text, so none of it is prohibited — and the resolver matches on
positions and names, never on pixels, so a fixture built this way exercises the real behaviour.

The generator reads the real library and writes fixtures; it is run by the user on their own
machine and its **output** is committed, not the library. Committed snapshot fixtures carry
`name` (needed for the name-match path) but no `text`, `flavor`, `traits`, or `imagesrc`.

## R12 — Second measurement pass, 2026-08-17: two findings that change the design

Re-measured against the live API while writing the plan. Both findings contradict something an
implementer would otherwise reasonably assume.

### `pack.total` disagrees with the summed quantity — do not cross-check it

`GET /api/public/packs/` carries a `total` per pack, which looks like a free way to catch a
truncated snapshot. Measured, it is not:

| Pack | Records | Summed `quantity` | `pack.total` |
|---|---:|---:|---:|
| `cap` | 34 | **59** | 56 |
| `vision` | 36 | **59** | 56 |
| `ant` | 34 | **60** | 60 |

Whatever `total` counts, it is not the sum of `quantity` over the pack's cards. Wiring it in as
a completeness check would have fired a false alarm on two of the three packs checked — exactly
what FR-018 and FR-019 prohibit. `total` is therefore **discarded on capture** along with
`known`, `available`, `url`, and `position`; the pack index retains `code` and `name` only.

This is a case where the spec's blanket prohibition on expected totals turns out to be
protecting against a concrete defect rather than a hypothetical one.

Truncated or malformed upstream data is caught instead by FR-047 validation at capture: every
retained field present and well-typed, at least one `type_code: hero` record, and at least one
`card_set_type_name_code: nemesis` record.

### A face comes from one of **two** mechanisms, and R8 named only one

R8 records that `double_sided` is `false` on every identity card and that the hero/alter-ego
pair is expressed by `linked_to_code`. True, and incomplete. Measured:

| Mechanism | Example | Shape |
|---|---|---|
| Linked codes | `cap` `03001a` → `linked_card` `03001b` | Two **codes**, one physical card, two faces. `double_sided` is `false`. |
| `double_sided` flag | `vision` `26002` Intangible, `double_sided: true`, `backimagesrc: /bundles/cards/26002b.png` | One **code**, two faces. No linked card. |
| Two records at one position | `ant` `12001a` (→ `12001b`) *and* `12001c`, both `position: 1`, both `type_code: hero` | Three faces across two records. |

So face expansion is: for each code in a record's linked chain, one front plus one back if
**that code** is `double_sided`. An implementation reading only the linked chain prints Vision's
Intangible front-only — a proxy blank where the real card carries game text — and FR-017 reports
the run clean. That is precisely the failure FR-015f was added to close, and it is invisible to
every other check in this feature.

Two consequences worth stating separately:

- **`position` is not unique within a pack.** Ant-Man has two records at position 1. The
  `(pack_code, position)` join of FR-020 is many-to-one and must be disambiguated by the
  filename's code suffix, which matches MarvelCDB's `code` suffix rather than its `position`.
- **A filename's `a`/`b` suffix is ambiguous between the two mechanisms.** Vision's `_2a`/`_2b`
  are the two faces of the single code `26002`; Captain America's `_1a`/`_1b` are the two
  distinct codes `03001a`/`03001b`. Which one a suffix means is decidable only from the card
  data — FR-023 restated in concrete terms.

### Confirmed, not changed

`If-Modified-Since` against `cards/cap.json` returns **`304` with 0 bytes**, so R1's
revalidation plan works as written. `cache-control: max-age=600, public` and `last-modified`
are unchanged; there is still no `ETag`.

## R13 — Library index: one scan per resolve, held in memory, never persisted

**Decision**: build the whole-library index with `os.walk` over `library_root` at the start of
each resolve pass and keep it for that pass only.

**Rationale**: ~4,447 files. Persisting it would create a second source of truth that goes stale
the moment the user adds a scan — and a resumed run (FR-026b) must see the library as it is
*now*, since going away to find a missing file is the whole reason resuming exists. One pass of
`os.scandir` entries is tens of milliseconds against a ~49 s render.

Index shape: `(pack_hint, position, suffix) -> [entry]` and `normalised_name -> [entry]`, where
`pack_hint` comes from the containing hero folder and is absent under `Aspects/` — positions
there are meaningless without a pack, which is why the name index is not optional.

**Operational note**: BSD `find` does not traverse this Drive mount; `os.walk` and `Path.rglob`
do. Any diagnostic tooling written for this feature must use the latter.

## R14 — The reuse key is a digest of resolved image **content**

**Decision**: `image_identity = sha256` over the sorted list of
`(card_code, face_side, sha256(file bytes))`. FR-026h's key is
`(pack_code, snapshot_revision, image_identity)`.

**Rationale**: FR-026h names the three components and rules out the folder path explicitly. A
path-based key breaks reuse every time the Drive mount moves — SC-006h treats that as routine —
and FR-009 forbids retaining such a path anyway. Content digests give SC-006k directly: a second
library resolving even one card to different bytes produces a different key and rebuilds.

An uploaded file participates by the same digest it is stored under (R9), so no separate rule is
needed for a customized run.

The stated cost, which FR-026h accepts in terms: a run must **resolve** before it can establish
whether reuse applies, so reuse skips the render and not the resolve (SC-006i). Hashing ~40
files of ~3 MB adds ~120 MB of reads to a pass that already opens all of them.

## Sources

- [MarvelCDB API documentation](https://marvelcdb.com/api/doc) — endpoints and the request to honour HTTP caching
- Live responses from `marvelcdb.com/api/public/{packs,cards,card}` — measured 2026-08-16, see the tables above
- [SQLite: Internal Versus External BLOBs](https://www.sqlite.org/intern-v-extern-blob.html) — the ~100 KB crossover cited in ADR-0001
- [SQLite: How To Corrupt An SQLite Database File](https://www.sqlite.org/howtocorrupt.html) — network and synced filesystems
- `fsync(2)` and `fcntl(2)` on Darwin — `F_FULLFSYNC` versus `fsync`
- [Starlette / FastAPI request files](https://fastapi.tiangolo.com/tutorial/request-files/) — the `python-multipart` requirement
- Live responses from `marvelcdb.com/api/public/{packs,cards}` — re-measured 2026-08-17 for R12
  (`packs/`, and `cards/{cap,ant,vision}.json`), including a verified `304` on `If-Modified-Since`
