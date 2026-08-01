# Phase 1 Data Model: Hero Deck PDF Wizard

Entities from [spec.md](./spec.md) § Key Entities, with the fields, validation rules, and
state transitions implementation needs. Nothing here is stored in a database — the catalog
is an authored data file and everything else is derived at runtime.

## Content Catalog

The authored file defining all cards and decks. Lives outside the repository (Principle III)
and is editable without rebuilding the application (SC-009).

| Field | Type | Rules |
|---|---|---|
| `schema_version` | string | Required. Rejected if unrecognised — never best-effort parsed. |
| `cards` | Card[] | Required, non-empty. |
| `decks` | HeroDeck[] | Required, non-empty. |
| `revision` | derived | Content hash of the canonical serialisation. Not authored; computed at load and recorded on every generation (FR-022). |

**Validation (FR-005c, FR-005d)** — all errors collected and reported together, never
first-error-and-stop:

1. File parses and `schema_version` is known.
2. Every `Card.id` is unique.
3. Every `Card.image` resolves to a file present in the configured directory.
4. Every `CardEntry.card_id` in every deck refers to an existing card.
5. Every `CardEntry.quantity` is ≥ 1.
6. No two cards reference the same image file (warning, not error — usually a copy-paste
   mistake, occasionally deliberate).
7. Unreferenced files in the image directory are ignored silently; an extra file is not a
   fault.

Validation runs at load. A catalog that fails does not become live, and the application
serves an actionable error rather than operating on a partial understanding of it.

## Card

| Field | Type | Rules |
|---|---|---|
| `id` | string | Required, unique, stable. Independent of filename (FR-005b) so re-scanning or renaming does not change identity. |
| `name` | string | Required. Display and error messages — this is what a user sees named in a failure (FR-020). |
| `image` | string | Required. Explicit relative path within the image directory. Never inferred from name, position, or folder layout (FR-005a). |

Path values are constrained to the configured directory: no absolute paths and no `..`
traversal. The catalog is authored data, but it is data, and it is validated like data.

## Hero Deck

| Field | Type | Rules |
|---|---|---|
| `id` | string | Required, unique. |
| `name` | string | Required. Shown in the selection list (FR-001). |
| `hero_card_id` | string | Required. Must exist in `cards`. |
| `entries` | CardEntry[] | Required, non-empty. Order is significant and preserved into the PDF. |

Composition is the full published pre-built player deck — hero, signature, and aspect cards
(FR-006). Obligation and nemesis encounter sets are out of scope.

## Card Entry

| Field | Type | Rules |
|---|---|---|
| `card_id` | string | Required. Must exist in `cards`. |
| `quantity` | integer | Required, ≥ 1. Each copy prints as its own card face (FR-007). |

## Card Image Asset

Not authored — the runtime view of a file, produced by the asset store.

| Field | Type | Rules |
|---|---|---|
| `ref` | string | Opaque to callers. The adapter alone knows it is a path today and may be an object key later. |
| `width_px`, `height_px` | integer | Read from the decoded image. |
| `byte_size` | integer | Checked against the ceiling before decode is attempted. |

**Rules**: content-sniffed, never trusted by extension or declared MIME. Rejected if it
exceeds the byte or pixel ceiling. Rejected if below the resolution FR-010 requires at final
print size (**750 × 1050 px** at 63.5 × 88.9 mm and 300 DPI). Aspect ratio departing from
the standard card is fitted without distortion and reported, never silently cropped
(FR-014). Read-only — the application never writes to this directory (FR-019c).

## Print Layout

Pure derived geometry. No I/O, which is what makes it directly unit-testable — the
constitution requires these values be asserted, not inspected.

| Field | Type | Value / Rules |
|---|---|---|
| `card_size_mm` | (float, float) | `(63.5, 88.9)`. **Single configurable value** (FR-009a) so a change from beta print evidence touches one place. |
| `page_size` | enum | `LETTER` (215.9 × 279.4 mm) or `A4` (210 × 297 mm). Per-generation parameter. |
| `grid` | (int, int) | Fixed `(3, 3)` — nine per page for both page sizes (FR-011). |
| `margins_mm` | derived | Centred: Letter 12.70 × 6.35, A4 9.75 × 15.15. |
| `cut_guides` | derived | Marks in the margin only; never overlapping a card face (FR-013). |
| `fit_mode` | enum | `CROP` (default), `FIT`, or `STRETCH` (FR-009b). Per-generation parameter. |

**Fit-mode geometry.** Source scans are 1.4378 (h/w) against the slot's 1.4000, so all three
modes are exercised by real data — none is a theoretical branch:

| Mode | Scale | Printed face at 63.5 × 88.9 mm slot | Ratio preserved |
|---|---|---|---|
| `CROP` | `max(sw/iw, sh/ih)` | 63.5 × 88.9 mm, ~1.16 mm trimmed from top and bottom | Yes |
| `FIT` | `min(sw/iw, sh/ih)` | 61.8 × 88.9 mm, nothing trimmed | Yes |
| `STRETCH` | axes independently | 63.5 × 88.9 mm, 2.7% vertical compression | **No** |

`CROP` trims symmetrically — half the overflow from each edge, never all from one side.
`STRETCH` is the only path permitted to distort, and only when explicitly selected (FR-014).

## Page and Slot

| Entity | Fields | Rules |
|---|---|---|
| `Page` | `index`, `slots[]` | Ordered. The last page is partially filled with no placeholder outlines (US1 scenario 4). |
| `Slot` | `row`, `col`, `origin_mm`, `card_id` | Position derived from grid and margins; independent of which card occupies it. |

## Generation Request

The addressable resource Principle II requires, rather than a side effect of a page render.

| Field | Type | Rules |
|---|---|---|
| `id` | string | Server-assigned. |
| `deck_id` | string | Required, must exist. |
| `page_size` | enum | Defaults to `LETTER`. |
| `fit_mode` | enum | Defaults to `CROP`. Recorded with the generation so a printed sheet can be traced to the mode that produced it (FR-009d). |
| `catalog_revision` | string | Captured at creation. Fixes the generation to one consistent catalog state even if the file is edited mid-run. |
| `status` | enum | See below. |
| `page_count`, `card_count` | integer | Available before download (FR-018). |
| `failures` | Failure[] | Empty unless `status = failed`. Carries **every** failing card, not just the first (FR-020a). |

**State transitions**:

```
pending ──► running ──► succeeded
                └─────► failed
```

Terminal states are final; a generation is never retried in place. There is no `partial`
state by design — a failure yields no downloadable document at all (FR-020).

## Failure

Errors are values, because FR-020 and FR-021 require them to be specific and to distinguish
retryable from permanent.

| Field | Type | Rules |
|---|---|---|
| `kind` | enum | `catalog_invalid`, `asset_missing`, `asset_unreadable`, `asset_too_small`, `limit_exceeded`, `internal`. |
| `retryable` | boolean | True for transient conditions such as a locked or still-syncing file. |
| `card_id`, `card_name` | string? | Populated whenever the failure concerns one card, so the message can name it. |
| `detail` | string | Actionable text. Never a stack trace, per the constitution's fail-closed gate. |

## Generation Record

Emitted once per generation for observability (FR-022, Principle V).

Fields: `request_id`, `deck_id`, `resolved_card_ids[]`, `catalog_revision`, `page_size`,
`page_count`, `duration_ms`, `outcome`, `failure_kind?`.

Contains no file paths from outside the configured directory and no secrets — there are none
to leak in this feature, and the record should stay safe to paste into an issue.
