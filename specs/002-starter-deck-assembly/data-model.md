# Phase 1 Data Model: Hero Pack Printing from a Scan Library

Entities from [spec.md](./spec.md) § Key Entities, with the fields, validation rules, and state
transitions implementation needs. Feature 001's entities (Card, Printing, HeroDeck, Page, Slot,
Print Layout, Cost Limits) are unchanged and are not restated — see
[001/data-model.md](../001-hero-deck-pdf-wizard/data-model.md). What this feature adds is
everything upstream of them.

Two conventions hold throughout:

- **Nothing here is a database table.** Run records and snapshots are JSON files under the
  state directory, per [ADR 0001](../../docs/adr/0001-durable-run-state-on-the-filesystem.md).
- **No field ever holds an absolute filesystem path from outside the named library root**
  (FR-009, FR-027). Where a path is needed it is relative to a root the run names.

---

## Run Inputs

What the user supplies to start a run. Both are named per run; neither is configured in advance
(FR-005, SC-003a).

| Field | Type | Rules |
|---|---|---|
| `library_root` | path | Required. Must exist, be a directory, and be readable — validated when named, failing specifically rather than surfacing as a missing card later (FR-006). **The containment boundary for the run** (FR-007) and the extent of the whole-library search (FR-021). Never written to (FR-001, FR-008). |
| `hero_folder` | relative path | Required. Relative to `library_root`; must resolve inside it. The folder the pack is identified from (FR-010) and the folder the report accounts for file-by-file (FR-031). Refused if it contains no card images at all, reported as empty rather than identified on no evidence. |
| `page_size`, `fit_mode` | enum | Feature 001's parameters, defaults `LETTER` and `CROP`. Recorded on the run so a printed sheet traces to the mode that produced it (001 FR-009d). |

> Both terms come from the spec's 2026-08-17 amendment, which split the single "named folder"
> that FR-007 and FR-021 could not share. Reasoning and the rejected alternative are in
> [research R0](./research.md#r0--the-spec-names-one-folder-where-the-design-needs-two).

**Both paths are retained on the run record.** FR-026b requires a resumed run to still know which
folder it was reading, and the moved-folder edge case requires it to be able to name that folder
when the mount has gone. FR-009 does not forbid this: it forbids paths from *outside* the named
library root, and the root itself is not outside it.

What must not depend on either path is the **reuse key** (FR-026h), so that reuse survives the
Drive mount moving (SC-006h). And SC-006h's other half — a finished run's PDF downloading with
the library unmounted — holds because a finished run never reads the library again, not because
it forgot where the library was.

---

## Pack Index Entry

One row of `GET /api/public/packs/`, reduced. Cached with the same freshness rules as a snapshot
(FR-039) and used only to generate identification candidates.

| Field | Type | Rules |
|---|---|---|
| `code` | string | Required. The `pack_code` every card carries. |
| `name` | string | Required. What a hero folder is ranked against (research R3). |

61 entries, ~9 KB. Everything else the endpoint returns — `known`, `total`, `available`, `url`,
`position`, `id` — is dropped. **`total` in particular is dropped on purpose**: it disagrees with
the summed card quantity for two of the three packs measured, so using it as a completeness
check would fire a false alarm on most packs (research R12, FR-018, FR-019).

---

## Pack Snapshot

One pack's card listing as captured at a point in time. The unit of upstream storage and
refresh (FR-044a). Stored at `snapshots/<pack_code>.json`.

| Field | Type | Rules |
|---|---|---|
| `schema_version` | string | Required. An unrecognised value is **refused**, never best-effort parsed. |
| `pack_code` | string | Required. |
| `revision` | string | Derived, not authored: `sha256` of the canonical serialisation of `cards`, truncated to 16 hex. Changes exactly when something printable changes — **not** derived from `Last-Modified` (research R10). |
| `cards` | PackCard[] | Required, non-empty. |
| `last_modified` | string? | The upstream `Last-Modified` header verbatim. The only validator MarvelCDB serves — there is no `ETag` (research R1). |
| `fresh_until` | timestamp | Capture time plus the response's `max-age` (measured: 600 s). Within it, no request is issued at all (FR-039, SC-006d). |
| `captured_at` | timestamp | UTC. |
| `stale` | derived | True when the snapshot was served after a failed refetch. A run started against a stale snapshot reports it (FR-044a). |

**Validation on capture and on read** (FR-047, and the constitution's "content validated on
read" — this is a file the user could edit):

1. `schema_version` recognised, else refuse.
2. Every retained field present and well-typed on every card.
3. `pack_code` on every card equals the snapshot's.
4. At least one record with `type_code == "hero"` — a pack with no identity card cannot satisfy
   FR-015a and is a truncated response, not a printable pack.
5. At least one record with `card_set_type_name_code == "nemesis"` — FR-015b requires the group.
6. Every `quantity` ≥ 1.
7. Every `duplicate_of_code` that names a card resolves, when followed, to a pack this
   application can fetch. A dangling link is a warning, not a refusal: it only matters if that
   card also fails to resolve locally, and then FR-025 names it.

Failure at capture aborts the capture and reports the pack, never surfacing later at print time.

### PackCard

Reduced to the fields this feature resolves against, and no further (FR-038a). Card text,
flavour, traits, and `imagesrc` are dropped at capture — that is what keeps a committed fixture
clear of FFG-copyrighted text and the application clear of anything resembling a mirror (FR-038).

| Field | Type | Rules |
|---|---|---|
| `code` | string | Required. The card's identity. Suffixed (`03001a`) where a physical card has linked codes. |
| `pack_code` | string | Required. |
| `position` | integer | Required. **Not unique within a pack** — Ant-Man has two records at position 1 (research R12). Never treated as an identifier. |
| `name` | string | Required. The canonical display name. Every name the user sees comes from here, never from a filename (FR-023). |
| `type_code` | string | Required. `hero` marks the identity card (FR-015a). |
| `card_set_type_name_code` | string? | `hero`, `nemesis`, or absent. Drives the FR-015 grouping. |
| `quantity` | integer | Required, ≥ 1. **Copies in the pack** — exactly what FR-016 needs, and explicitly *not* copies in the starter deck (spec § Clarifications). |
| `double_sided` | bool | One code, two faces. Independent of `linked_codes`. |
| `linked_codes` | string[] | The `linked_card` chain, flattened to codes. Each contributes further faces. |
| `duplicate_of_code` | string? | This printing duplicates that one (FR-014, FR-022). |
| `duplicated_by` | string[] | The reverse direction. Both are followed, wherever they point — not only to the Core Set. |

---

## Face

The printable unit. Derived from a PackCard, never from a filename.

| Field | Type | Rules |
|---|---|---|
| `card_code` | string | The code this face belongs to. |
| `side` | enum | `front` or `back`. |
| `group` | enum | `player`, `identity`, `nemesis`, or `decklist` (FR-015). |

**Face expansion** — both mechanisms apply, and either alone is wrong (research R12):

```
faces(record) = for each code C in [record.code, *record.linked_codes]:
                    front(C)
                    back(C)  if C is double_sided
```

| Pattern | Example | Faces |
|---|---|---|
| Linked codes | `03001a` → `03001b` (Captain America / Steve Rogers) | 2 |
| `double_sided` flag | `26002` Intangible (Vision), back `26002b` | 2 |
| Two records, one position | Ant-Man `12001a` (→ `12001b`) and `12001c` | 3 |

**Group classification**, from the card data alone:

| Group | Rule |
|---|---|
| `identity` | `type_code == "hero"` |
| `nemesis` | `card_set_type_name_code == "nemesis"` |
| `player` | everything else |
| `decklist` | Not present in the card data at all. Found by filename in `hero_folder` and accepted by the user (FR-013d), or uploaded (FR-013c), or absent and reported (SC-006j). Carries the pseudo-code `decklist`, has one face, and is never counted among the pack's cards (FR-013b, FR-018). |

**Counting.** FR-018's unit is **cards**, because that is the unit the pack listing counts in.
The report states the face count alongside it, because that is what the page count follows from
(SC-002b). A double-sided card is one card and two faces; Ant-Man's identity is one card and
three faces.

---

## Resolution

The pairing of one card with one image, carrying how it was found. The audit record FR-024,
FR-029, and SC-005 are asserted against.

| Field | Type | Rules |
|---|---|---|
| `card_code`, `card_name` | string | Name from the snapshot, never from the filename. |
| `side` | enum | `front` or `back`. A back that resolves to nothing stops the run exactly as a front does (FR-015f). |
| `provenance` | enum | See the cascade below. Anything other than `folder_position` **must** be reported (FR-024, SC-005). |
| `source` | enum | `library` or `upload`. |
| `ref` | string | Relative to `library_root`, or the upload's content digest. Never an absolute path from outside (FR-009, FR-027). |
| `original_filename` | string? | For an upload only: the file's own name, and nothing else about where it came from (FR-027). |
| `content_digest` | string | `sha256` of the bytes. Feeds the reuse key (FR-026h, research R14). |
| `note` | string? | Why this file, in the user's terms. Carries into the report. |

**The cascade** (FR-020 → FR-025), first match wins, and the step that matched is the
`provenance`:

| Step | `provenance` | Rule |
|---|---|---|
| 0 | `decklist_name` | **Decklist only.** A `deck\s*list` stem match inside `hero_folder`, proposed to the user and printed only once accepted (FR-013d). Never reaches steps 1–4: the decklist card has no `pack_code`, no `position`, and no canonical name, and this is a literal substring test rather than FR-023's name match. Candidates differing only by extension are one candidate (FR-034); different stems are a conflict the user resolves (FR-033); none is FR-013c's gap. `card_code` is the literal `decklist` and is not a MarvelCDB code. |
| 1 | `folder_position` | Exact `(pack_code, position, code suffix)` match inside `hero_folder`. The only provenance that is *not* reported as a substitution. Two different cards at one position is a *failure to match*, so the cascade continues to step 2 rather than stopping; the clash is still reported, derived from the library rather than from this run's failures (FR-033). |
| 2 | `library_position` | The same `(position, code suffix)` anywhere under `library_root`, **narrowed by the canonical name of the card being sought** (FR-021, FR-023). Position alone spans the whole library — position 33 occurs in more than a dozen packs — so on its own it would pair a card with confidently wrong art; requiring both is what makes the widened search safe. Origin named in the report. |
| 3 | `reprint` | Follow `duplicate_of_code` / `duplicated_by` in both directions and accept any other printing of the same card (FR-014, FR-022). |
| 4 | `name` | Match a normalised filename against **the canonical name of the specific card being sought** (FR-023). Never parses identity out of a filename. `hero_folder` and its subtree are searched before the rest of the library, for the same reason step 1 precedes step 2 — four folders hold a `Hawkeye`. Carries the whole of Phoenix and Wonder Man (SC-003c). |
| 5 | `manual` | A file the user uploaded for this card (FR-026, FR-026e). Distinguishable from every automatic resolution (FR-029, SC-006c). |
| 6 | `omitted` | The user explicitly chose to print without it (FR-030). Named in the report, counted against the pack's card count, and written to the run's log (FR-030b, SC-006e). |
| — | *unresolved* | None matched and the user has not decided. The run **stops** (FR-017, FR-025). |

Copy counts always come from the pack being printed, never from the printing an image was
borrowed from (FR-016, US1 scenario 4).

---

## Library Index

Built by one `os.walk` of `library_root` at the start of each resolve pass, held for that pass
only, never persisted (research R13). A resumed run re-indexes, which is the point — the user
went away to find the missing file.

| Field | Type | Rules |
|---|---|---|
| `by_position` | map | `(pack_hint, position, suffix) -> [entry]`. `pack_hint` comes from the containing hero folder; absent under `Aspects/`, where a position means nothing without a pack. |
| `by_name` | map | `normalised name -> [entry]`. Casefolded, punctuation and underscores stripped, whitespace collapsed, then compared with an **edit distance ≤ 2**, tightened to **≤ 1** for canonical names under 8 characters. Stripping alone is not enough and never was: "Stength in Numbers" is a dropped letter. **A swap of two adjacent characters counts as one edit** (Damerau's restricted variant): "Pheonix" is two edits from "Phoenix" under plain Levenshtein and so falls outside the bound a 7-character name gets, but the tightening exists because two *independent* edits on a short name can reach a different card, which one transposed pair cannot. A match MUST be **unique** after the narrowing below — anything still ambiguous is a conflict (FR-033), never an arbitrary pick — and every hit is reported as a name match (FR-024). |
| `decklist_candidates` | entry[] | Files anywhere in `hero_folder` whose normalised stem contains `deck\s*list` (FR-013d). A candidate is **not** an `unparseable` entry and is never reported as unused (FR-031, FR-032). Candidates sharing a stem and differing only by extension collapse to one under FR-034. |
| `unparseable` | entry[] | Files matching none of the three conventions. Reported when inside `hero_folder` (FR-032); outside it they surface only through the card that failed to resolve. |

### Filename conventions

| Form | Example | Trailing number |
|---|---|---|
| A | `Leadership_Make the Call_Event_16.tiff` | `position`, optional `a`/`b`/`c` suffix |
| B | `Wasp_Pym Particles_Resource_7_12.15.tiff` | `position`, then `set_position`.`set_total` |
| C | `2_Active Altruism_Event.tif` | **a copy number, not a position** |

Form C is detected per folder — leading numbers that are small, repeat across different names,
and fail to line up with the candidate pack's positions — and positional matching is dropped
for that folder rather than allowed to match wrongly.

A Form C filename may *also* carry a trailing suffix — `0_Pheonix_Hero_1B`,
`1_Phoenix Force_Upgrade_2A`/`_2B` — and that suffix **is** read even though the folder's
positions are not. The two numbers are answering different questions, and the trailing one is
frequently the only thing separating two faces of a card whose name the card data gives
identically to both. The trailing *position* is still discarded: this folder has already been
judged to number by copy, and trusting one of its two numbers over the other is a guess.

**A suffix is evidence, never identity.** Vision's `_2a`/`_2b` are the two faces of the single
code `26002`; Captain America's `_1a`/`_1b` are the two distinct codes `03001a`/`03001b`. Which
one a suffix means is decidable only from the card data.

**Narrowing an ambiguous name match** (step 4). The bound has to be loose enough to absorb
`Battlefild Benevolence`, and a bound that loose puts `Wonder Man` within reach of
`Wonder Fans`. Two further facts settle those, and both are read from the card data rather
than out of a filename, which is the direction FR-023 permits:

1. **The face the code asks for**, applied as a *filter* rather than a tie-breaker. A name
   identifies a card; what is being resolved is a face, and one card's two faces carry one
   name. A face left with no candidate is a gap — never a reason to relax back to the name
   and answer "where is the back?" with the front.
2. **The card's type**, matched against whole filename segments, so `Ally` does not match
   `Allying` and `Hero` does not match `Heroic Conditioning`.

**Conflicts** (FR-033, FR-034): two files claiming the same position are reported naming both
sides and neither is chosen (US2 scenario 4). A `.tif`/`.tiff` pair of one card is a duplicate
rendition — one is chosen deterministically by sorted filename, the duplication is reported, and
the card prints once.

---

## Pack Identification

| Field | Type | Rules |
|---|---|---|
| `pack_code` | string? | Null when nothing could be identified. |
| `source` | enum | `identified` or `user_selected`. Reported and distinguishable, exactly as a manual card resolution is (FR-012b, SC-009a). |
| `confidence` | float | Share of the hero folder's *interpretable* files whose filename matches the canonical **name** of a card in the candidate pack. See the correction below — this originally read "by position or name". |
| `evidence` | string[] | What the figure rests on, shown to the user before they confirm (FR-012). |
| `candidates` | ranked[] | Offered when the user declines or identification is refused (FR-012b). |

**Threshold** — **≥ 0.75 with at least 5 matched cards**, measured in T042 and asserted by
`test_the_threshold_sits_in_the_measured_gap`. Below it, the run is refused as too weak *and
offered selection* (FR-011, FR-012b): a refusal is a prompt, never a dead end.

### T042 calibration, measured 2026-08-17

Every acceptance hero's folder scored against every pack holding a committed snapshot. `core` is
excluded from the false-positive column: it is not a hero pack but the place a shared card's other
printing lives, so a hero folder scoring against it is the reprint relationship working (FR-014).

| | Score |
|---|---|
| Weakest correct identification | **0.87** — Wasp, 20 of 23 interpretable files |
| Next weakest | 0.97 — Phoenix, 28 of 29 |
| Strongest **incorrect** identification | **0.65** — Ant-Man's folder against the *Wasp* pack |
| Fewest cards matched by a correct identification | 17 |

0.75 sits inside that gap with margin either side. Two findings from the measurement changed the
design, and both are recorded here because the original text is what a reader would otherwise
trust:

- **The provisional 0.60 was below the false-positive ceiling.** Ant-Man and Wasp each contain the
  other hero as an ally and share basic cards, so Ant-Man's folder genuinely scores 0.65 against
  the Wasp pack. A threshold of 0.60 would have admitted it.
- **Position agreement is not evidence of pack identity, and the confidence figure no longer uses
  it.** Every hero pack numbers its cards from 1, so every hero folder's positions match every
  hero pack's positions: measured on positions, Star-Lord's folder verifies **100%** against Thor.
  Name agreement separates the same pair completely (1.00 against Star-Lord, 0.00 against Thor).
  Positions are still counted and shown as corroboration in the evidence list, because they are
  meaningful to a human reading it, but they do not move the number.

The identity card was evaluated as an additional hard requirement and **rejected**: Ant-Man's
folder contains a card named "Wasp", which is the Wasp pack's identity card, so the check fires
on exactly the false positive it was meant to catch. The name share alone is the cleaner
discriminator.

Confirmation is unconditional (FR-012a). No card is resolved from an unconfirmed identification,
because the case the threshold structurally cannot catch is an identification that is confident
and wrong, which yields a deck that is entirely plausible (SC-009).

Selecting a pack is **not** customization under FR-026i: what is printed follows from the pack
and its snapshot, so a run that selected its pack and then resolved everything automatically
still produces that pack's standard PDF.

---

## Assembly Run

One attempt to assemble one pack from one hero folder. Durable across visits and application
restarts. Stored at `runs/<run_id>/run.json`, written by atomic replace.

| Field | Type | Rules |
|---|---|---|
| `schema_version` | string | A run written by a **newer** version is refused, never misread (ADR 0001). |
| `id` | string | Server-assigned. |
| `version` | integer | Optimistic concurrency. Every mutating request carries the version it read; a mismatch is `409`, never a silent overwrite (ADR 0001, and the dissent that argued for it). |
| `library_root` | path | Retained, so a resumed run knows which library it was reading and can name it if the mount has gone (FR-026b). Excluded from the reuse key (FR-026h). |
| `hero_folder` | relative path | Retained, relative to `library_root`. |
| `identification` | PackIdentification | Above. |
| `snapshot_revision` | string | Pinned at the moment the pack is confirmed. A resumed run keeps it, so refreshing card data cannot change a deck's composition under resolutions already made (FR-044b, FR-045). |
| `page_size`, `fit_mode` | enum | 001's parameters. |
| `resolutions` | Resolution[] | Grows as the user answers. |
| `state` | enum | See below. |
| `outcome` | enum? | `clean`, `warnings`, or `refused`. **Null until terminal** — FR-036 requires a run that has not reached an outcome to be distinguishable as such. |
| `report` | AssemblyReport | Lives on the run, so an incomplete pack stays legible as incomplete on a later visit without a browser tab staying open (FR-030b). |
| `pdf` | ref? | `standard` (a hardlink into `pdfs/standard/`) or `saved` (into `pdfs/saved/`), or absent. |
| `created_at`, `updated_at` | timestamp | UTC. |

Uploaded bytes live beside the record at `runs/<id>/uploads/<sha256>`, which is what lets a
resumed run keep a manual resolution after the source file moves (FR-026e) and lets that run
reprint identically (FR-045, US4 scenario 4).

### States

```
                    ┌──────────────► unidentified ──┐
                    │                               │  (user selects a pack, FR-012b)
   identifying ─────┼──────────────► awaiting_pack ◄┘
                                          │  confirm (FR-012a)
                                          ▼
                                      resolving
                                          │
                        ┌─────────────────┴──────────────┐
                        ▼                                ▼
                  awaiting_cards ───────────────────►  ready
                  (FR-026d; upload,                     │  final confirmation (FR-026a)
                   or omit per FR-030)                  ▼
                                                    rendering
                                                        │
                                                ┌───────┴───────┐
                                                ▼               ▼
                                            complete         failed
```

Rules the transitions encode:

- **Nothing resolves before `awaiting_pack` is confirmed** (FR-012a, SC-009).
- **`ready` is not `complete`.** A PDF is produced only on an explicit final confirmation
  (FR-026a). Reaching `ready` with every card resolved does not print by itself.
- **`awaiting_cards` and `awaiting_pack` are not failures** (FR-036). Both are resumable across
  a restart with the folder, the pack, the resolutions, and the report intact (FR-026b,
  SC-006f).
- **A request to omit unresolved cards before the run has reported any is refused** (FR-030a):
  the run has not reached `awaiting_cards`, so there is no named gap for the permission to be
  informed about, and a blanket permission is not an informed decision.
- **An undecided decklist candidate holds the run in `awaiting_cards`** (FR-013d). It is a card
  waiting on the user like any other, needs no state of its own, and `skip` is the FR-030-shaped
  escape. Accepting the tool's candidate leaves the run uncustomized (FR-013e).
- **`complete` and `failed` are terminal.** A run is never retried in place; there is no partial
  state, inherited from 001's FR-020b.

---

## Stored PDF

A generated PDF kept for reuse. Two kinds, and the difference is whether the user changed
anything.

| Field | Type | Rules |
|---|---|---|
| `kind` | enum | `standard` or `saved`. |
| `path` | string | `pdfs/standard/<pack_code>@<snapshot_revision>@<image_identity>.pdf`, or `pdfs/saved/<uuid>.pdf`. |
| `name` | string | Derived from the pack for `standard`; supplied by the user for `saved` (FR-026i). |
| `byte_size` | integer | 001 measured ~202 MB for a 41-card deck; a pack is ~60 faces, so **at least that and probably more** — measured for real in T116. What FR-026g's deletion reclaims. |

**Reuse key** (FR-026h) — all three together:

1. `pack_code`
2. `snapshot_revision` — a refresh invalidates rather than serving a PDF built from superseded
   card data (US1 scenario 16)
3. `image_identity` — `sha256` over the sorted list of `(card_code, side, content_digest)`,
   **the decklist included as `("decklist", "front", digest)`** and its absence as
   `("decklist", "front", "")`. Without it, two libraries holding different decklist scans — or one
   holding none — key identically and the second run is served the first's PDF, which is precisely
   the failure SC-006k forbids.

The key deliberately excludes the library folder's path: reuse must survive that folder moving
or being renamed (SC-006h, US1 scenario 15b), and FR-009 forbids retaining such a path anyway.
It follows that **a run must resolve before it can establish whether reuse applies** — reuse
skips the ~49 s render, not the resolve (SC-006i). A second library resolving even one card to
different bytes rebuilds (SC-006k, US1 scenario 15a).

**Standard versus saved.** A run that resolved every card automatically with no user input of
any kind produces the pack's `standard` PDF. Any customization — an uploaded file (FR-026), an
omission (FR-030), or any later editing capability — makes it `saved`, named by the user
(FR-026i). Selecting the pack is not customization (FR-012b), and neither is accepting the
decklist candidate the tool proposed (FR-013e). Picking a different decklist file, uploading one,
or skipping the decklist **is** customization — each changes what is printed. Were acceptance
itself customization, no run would ever be standard and reuse would never fire once.

**Ownership and deletion.** A standard PDF belongs to the **pack**, not to the run that built it
(FR-026g1). `os.link` gives kernel-maintained refcounting, so:

| Act | Reclaims |
|---|---|
| Delete a run | That run's uploads and its *saved* PDF. **Never** a standard PDF (SC-006h, US5 scenario 6a). |
| Delete a standard PDF from the stored-PDF list | The bytes, once the last link goes. The next assembly of that pack rebuilds (FR-026g, US5 scenario 6b). |

Deleting never touches the scan library (FR-001).

---

## Assembly Report

What a run produced. Lives on the run record, retrievable on a later visit (FR-030b).

| Section | Contents | Requirements |
|---|---|---|
| Pack | The pack, and whether it was identified or user-selected, with the evidence | FR-012, FR-012b, SC-009a |
| Groups | Which cards are player cards, which is the identity card, which form the nemesis set, which is the decklist card — because FR-015d lets one page carry cards from more than one group, the report is what tells them apart | FR-015e |
| Counts | Cards printed against the number the pack listing records, **in cards**, with the face count alongside. No expected total, and no warning on one | FR-018, SC-006a |
| Decklist | Whether one was printed; if not, the gap named with the Hall of Heroes address | FR-013b, FR-013c, SC-006j |
| Substitutions | Every image resolved by anything other than `folder_position`, naming card, file, and why | FR-024, SC-005 |
| Manual choices | Every uploaded file, by its own filename, distinguishable from automatic resolutions | FR-027, FR-029, SC-006c |
| Omissions | Every card printed without, counted against the pack's total and written to the log | FR-030b, SC-006e |
| Unused files | **Every** file in `hero_folder` either used or named as unused with a reason. Outside it, only files used or in conflict | FR-031, SC-004 |
| Uninterpretable | Files in `hero_folder` matching none of the three conventions. Outside it, surfaced through the card that failed instead | FR-032 |
| Conflicts | Position conflicts naming both sides; duplicate renditions naming which was chosen | FR-033, FR-034 |
| Warnings | Scans below the resolution required at print size — a warning, never a refusal | FR-035 |
| Upstream | Snapshot revision, and whether it was stale | FR-044, FR-044a |

**Scope of file accountability** is bounded to `hero_folder` on purpose. FR-031 read literally
against FR-021's whole-library search would require one hero's report to account individually
for 4,447 files that were never candidates — unreadable for the user and untestable as SC-004.
The harm it exists to prevent is a scan sitting in the folder the user pointed at, ignored and
unexplained.

---

## Bridge to Feature 001

FR-048 requires the resolved pack to be expressed in 001's structures so pagination, resolution
enforcement, and PDF generation are reused rather than reimplemented. The mapping is total and
introduces no new output format:

| 002 | 001 |
|---|---|
| PackCard | `Card` — `id` = the MarvelCDB `code`, `name` from the snapshot, `double_sided` from face expansion |
| Resolution | `Printing` — `image` / `image_back` are refs the run's `Store` understands |
| Pack + resolutions, ordered | `HeroDeck` — `entries` in `(group, position, code)` order: player cards, identity, nemesis, decklist |
| `quantity` | `CardEntry.quantity`, from the pack being printed (FR-016) |
| `snapshot_revision` | `Catalog.revision` |

The synthesised catalog is **in memory only** and is never written to disk — it is derived from
the snapshot plus the resolutions, both of which are already durable, and writing it would
create a third thing that can disagree with them.

**One change to 001 is required** (research R8): `render.document.compose`,
`catalog.printings`, `catalog.validation`, and `render.images.validate_source` take an
`assets.Store` rather than an `image_dir: Path`, because
a run's faces come from two roots — the library and the run's own uploads — and a finished run
must render with the library unmounted (SC-006h). `assets.OverlayStore` composes the two. This
closes a standing Principle III gap where `render/` computed `image_dir / ref`; 001's tests are
the guard that the refactor is behaviour-preserving.

**Ordering is FR-015d's, not a grouping convenience**: player cards, identity, nemesis, decklist,
packed into as few pages as will hold them, with **no page break between groups**. A page
carrying the last player cards and the first nemesis cards is the intended result. What keeps
the groups distinguishable is the report, not the layout (FR-015e, SC-002b).

---

## Configuration

Added to `config.Settings`. `MARCHAMP_IMAGE_DIR` and `MARCHAMP_CATALOG` remain feature 001's and
are **not** required by this feature — FR-005 forbids refusing to start because a library
location is unset, and SC-003a requires assembly with no environment variable set at all.

| Setting | Default | Rules |
|---|---|---|
| `MARCHAMP_STATE_DIR` | Platform data directory (`~/Library/Application Support/marchamp` on Darwin, `$XDG_DATA_HOME/marchamp` otherwise) | Created on first use. **Refused if it resolves inside a named `library_root`** — the library is a synced Drive folder, and writing run state into it would break FR-001 and hand the user's PDFs to a sync client. |
| Upstream host | `marvelcdb.com` | The whole allowlist. Redirects not followed; the resolved address re-checked against loopback, link-local, and private ranges before connecting. |
| `User-Agent` | Names the application and a contact URL | FR-041 — so the operator can attribute and contact rather than only block. |
| Upload byte ceiling | Inherits 001's per-image ceilings | An upload is an untrusted binary and gets the identical treatment (FR-028). |
| Library scan ceiling | File count cap on one `os.walk` | Bounds a run against a mistakenly named root such as `/`. |
| Backoff and pacing | Exponential with jitter, at most two retries. **At most one request in flight, and at least 1 s between requests** | FR-042, FR-043. MarvelCDB publishes no rate limit; its absence is not permission. The pacing figures are self-imposed and stated here rather than left to inference — an assembly makes two or three requests, so they cost nothing and make "conservative" testable. |
