# Feature Specification: Starter Deck Assembly from a Scan Library

**Feature Branch**: `002-catalog-scaffold`

**Created**: 2026-08-01

**Last revised**: 2026-08-16

**Status**: Draft

**Input**: User description: "Point it at a hero folder in the scan library and get that
hero's starter deck as a print-ready PDF. Card identity and quantities come from
marvelcdb.com; images come from the library, including the ones the scanner skipped because
they were already in the Core Set."

## Why this exists

Feature 001 turns a catalog into a printable sheet and leaves the catalog as an exercise for
the user. Authoring one by hand for a single hero means writing roughly two hundred lines of
JSON, and the earlier draft of this feature proposed generating that JSON from filenames and
then asking the user to type in every quantity by hand, because quantities were believed to
be unrecoverable.

They are not. MarvelCDB publishes the complete card list for every pack, with the number of
copies of each card the pack contains, under a public JSON API that needs no credentials.
What it does *not* publish is which of a pack's cards form the pre-built starter deck — that
is not a field, and it cannot be computed from pack contents. But the scan library already
encodes it: the person who scanned these cards put the starter-deck cards in the hero's
folder and everything else under `Aspects/`.

So the two halves fit together. The library says *which cards*; MarvelCDB says *what they
are and how many*. Neither alone is enough, and the user should not have to supply either.

The check that makes this safe is arithmetic. A Marvel Champions deck is exactly 40 cards.
A reconstruction that totals 40 is almost certainly right; one that does not has failed, and
can say precisely which cards it could not place. That turns the whole feature's correctness
into a number the tool can verify on every run.

## Clarifications

### Session 2026-08-16

- **Q: Where does deck composition come from, given MarvelCDB does not record it?**
  A: From the library's own structure — the hero folder holds the starter-deck cards. This
  was measured: summing a pack's hero set, main aspect, and basic cards yields 43, 43, 43,
  43, 40, 43, 43, 43, 43, 43, 42, and 37 across twelve packs, so composition is not derivable
  from pack contents. Official starter decklists exist on MarvelCDB only for the five Core
  Set heroes.
- **Q: How are a file and a MarvelCDB card matched?**
  A: On `(pack_code, position)`. The trailing number in the filename is exactly MarvelCDB's
  `position`. Card *names* in filenames are unreliable and MUST NOT be parsed cold.
- **Q: Where do copy counts come from when an image is borrowed from another printing?**
  A: From the printing being assembled, never from the printing the image came from.
- **Q: Does the application download card art from MarvelCDB?**
  A: No. MarvelCDB supplies metadata only; every image comes from the user's library.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print a hero's starter deck (Priority: P1) 🎯 MVP

Someone points the application at a hero's folder and receives a print-ready PDF of that
hero's 40-card starter deck, without writing a catalog, typing a quantity, or knowing that
six of the cards were never scanned.

**Why this priority**: This is the entire barrier. Today the application is unusable by
anyone who has not hand-authored a catalog, which is almost nobody.

**Independent Test**: Point the tool at `Heros/Steve Rogers_Captain America/` with no catalog
present. It succeeds when the PDF contains 40 cards, in the right quantities, including the
six sourced from the Core Set.

**Acceptance Scenarios**:

1. **Given** a hero folder and no catalog, **When** the user assembles, **Then** a deck of
   exactly 40 cards is produced, each card appearing as many times as the pack contains it.
2. **Given** a card the scanner omitted because it is a Core Set reprint, **When** the user
   assembles, **Then** its image is taken from the Core Set and it appears in the deck.
3. **Given** a card whose copies number more than one, **When** the user assembles, **Then**
   the single scanned image appears once per copy the pack contains.
4. **Given** a borrowed image whose own printing ships a different number of copies, **When**
   the user assembles, **Then** the count follows the pack being assembled, not the pack the
   image came from.
5. **Given** a completed assembly, **When** the user opens the report, **Then** every card is
   accounted for and every borrowed image is named alongside the printing it came from.

---

### User Story 2 - Be told exactly what could not be resolved (Priority: P1)

An assembly that cannot reach 40 cards says which cards are missing and where it looked,
rather than producing a deck that is quietly short.

**Why this priority**: Shares P1 with User Story 1 because it is not a separate feature but
the other half of the same one. A deck that is silently 37 cards is worse than no deck: the
user discovers it at the table, having already paid to print it.

**Independent Test**: Assemble a hero whose folder omits a starter-deck card that exists in
no other printing. It succeeds when the run fails, names that card, and prints nothing.

**Acceptance Scenarios**:

1. **Given** a card with no image anywhere in the library, **When** the user assembles,
   **Then** the run fails naming that card, and no PDF is written.
2. **Given** a reconstruction that does not total 40, **When** the user assembles, **Then**
   the count is reported against the expected 40 and every unplaced card is named.
3. **Given** a file the naming convention cannot parse, **When** the user assembles, **Then**
   that file is named in the report rather than silently ignored.
4. **Given** two files in one folder claiming the same position, **When** the user assembles,
   **Then** both are named as a conflict and neither is chosen arbitrarily.

---

### User Story 3 - Find a card that is not where it should be (Priority: P2)

A starter-deck card that lives in another hero's folder, or under `Aspects/`, is found
anyway.

**Why this priority**: Without it, four of the eight heroes measured cannot be assembled at
all, because the library does not consistently place a hero's cards in that hero's folder.
With it, they can. It is second only because User Story 1 is demonstrable without it.

**Independent Test**: Assemble Black Widow, whose `Quincarrier` is filed under Wasp. It
succeeds when the card is found and the deck reaches 40.

**Acceptance Scenarios**:

1. **Given** a starter-deck card filed under another hero's folder, **When** the user
   assembles, **Then** it is found and its origin is named in the report.
2. **Given** a starter-deck card filed under `Aspects/`, **When** the user assembles, **Then**
   it is found and its origin is named in the report.
3. **Given** a card found by a name match rather than by position, **When** the user
   assembles, **Then** the match is reported as such, so a wrong match is visible rather than
   invisible.

---

### Edge Cases

- **A filename carrying no position at all.** Observed in the library
  (`Basic_Invulnerability_Event.tiff`). The card must still be findable, by name against the
  specific card being sought — never by parsing the name cold.
- **A second filename convention.** One folder numbers files
  `{position}_{set_position}.{set_total}`. Both forms must parse, and a form matching neither
  is reported.
- **The same card present as both `.tif` and `.tiff`.** One is chosen deterministically and
  the duplication is reported; the card is not printed twice.
- **Two files in one folder claiming the same position.** Reported as a conflict, not
  resolved by arbitrary choice.
- **A hero with three faces.** Ant-Man has a tiny form, a giant form, and an alter-ego where
  every other hero has two. Face count is read from the data, never assumed to be two.
- **A card name misspelled in the filename.** "Stength in Numbers", "Steve_s Apartament", and
  a type written "Upgarde" all occur. Display names come from MarvelCDB; the filename is
  never the authority on what a card is called.
- **MarvelCDB unreachable.** Assembly cannot proceed on library contents alone, because
  quantities and identities live only upstream. The run fails saying so, or proceeds from a
  previously captured snapshot if one exists — it must never guess.
- **A folder that is not a hero pack.** Reported as unidentifiable rather than assembled
  against a wrongly guessed pack.
- **A pack identified with low confidence.** Reported and refused. A wrong pack produces a
  deck that is entirely plausible and entirely wrong.

## Requirements *(mandatory)*

### Scope and safety

- **FR-001**: The tool MUST read the scan library and MUST NOT modify it in any way. The
  read-only guarantee feature 001 makes about the asset directory continues to hold without
  exception.
- **FR-002**: The tool MUST NOT download card images from MarvelCDB or any other remote
  source. MarvelCDB supplies metadata only; every image printed MUST come from the user's
  library.
- **FR-003**: Outbound network access MUST be limited to MarvelCDB's public JSON API. No
  credentials are required and none MUST be requested.
- **FR-004**: All library reads MUST go through the existing asset adapter (constitution
  principle III). Assembly logic MUST NOT learn where a binary lives.

### Identifying the pack

- **FR-005**: The tool MUST determine which pack a hero folder represents, from the folder's
  contents and MarvelCDB's card data, without a hand-maintained folder-to-pack table.
- **FR-006**: Pack identification MUST be verified rather than assumed. The tool MUST check
  the folder's positions against the identified pack and MUST refuse to proceed when
  agreement is too weak to be confident.
- **FR-007**: The tool MUST state which pack it identified and on what evidence, so a wrong
  identification is visible before a PDF is printed rather than after.

### Composing the deck

- **FR-008**: Deck composition MUST be derived from the hero folder's contents together with
  MarvelCDB's pack listing. The tool MUST NOT attempt to compute composition from pack
  contents alone, which is not possible.
- **FR-009**: A pack card absent from the hero folder that carries a reprint link MUST be
  treated as part of the deck and sourced from the printing it duplicates.
- **FR-010**: Encounter cards, obligation cards, nemesis cards, and the hero's identity card
  MUST be excluded from the player deck. They MAY be offered as a separate output.
- **FR-011**: The number of copies of a card MUST come from the printing being assembled,
  never from the printing an image was borrowed from.
- **FR-012**: An assembled player deck MUST contain exactly 40 cards. A reconstruction that
  does not MUST fail, MUST report the total against the expected 40, and MUST name every card
  it could not place.
- **FR-013**: The tool MUST NOT invent a card, a quantity, or a substitution to reach 40.

### Resolving images

- **FR-014**: A card MUST be matched to a file by `(pack_code, position)` wherever the
  filename carries a position and the folder's pack is known.
- **FR-015**: When that fails, the tool MUST search the whole library, because the library
  does not reliably file a hero's cards under that hero.
- **FR-016**: When that fails, the tool MUST follow reprint links in both directions and
  accept an image of any other printing of the same card.
- **FR-017**: A name match MUST only ever be made against a specific card the tool is already
  looking for, with its canonical name known from MarvelCDB. Parsing a card's identity out of
  a filename is prohibited.
- **FR-018**: Every image resolved by anything other than an exact positional match in the
  identified folder MUST be reported, naming the card, the file chosen, and why.
- **FR-019**: A card with no image anywhere in the library MUST fail the run, naming the card.
  Substituting a placeholder or omitting the card is prohibited.

### Reporting

- **FR-020**: Every file in the folders consulted MUST be either used, or named in the report
  as unused and why. Silent omission is prohibited.
- **FR-021**: The tool MUST report every file whose name it could not interpret, naming each.
- **FR-022**: The tool MUST report position conflicts, naming both sides, and MUST NOT resolve
  them by arbitrary choice.
- **FR-023**: The tool MUST report duplicate renditions of one card, naming which was chosen.
- **FR-024**: The tool MUST report scans below the resolution the application requires at
  print size, as a warning rather than a refusal.
- **FR-025**: The tool's exit status MUST distinguish "assembled cleanly" from "assembled with
  warnings" from "refused", so it is usable from a script without parsing prose.
- **FR-026**: Failures MUST name the specific card or file at fault, never a generic error
  (constitution principle V).

### Upstream data

- **FR-027**: MarvelCDB responses MUST be captured as a snapshot with a recorded revision, so
  a generated PDF can be traced to the card data that produced it.
- **FR-028**: Assembling twice from the same library and the same snapshot MUST produce a
  byte-identical PDF (constitution principle V).
- **FR-029**: The tool MUST NOT proceed when MarvelCDB is unreachable and no snapshot exists.
  It MUST say which is missing.
- **FR-030**: Upstream data MUST be validated on capture, and a response that does not carry
  the fields this feature depends on MUST fail loudly at that point rather than at print time.

### Output

- **FR-031**: The resolved deck MUST be expressed in the catalog structures feature 001
  already defines, so page layout, resolution enforcement, and PDF generation are reused
  rather than reimplemented. This feature adds no new output format.
- **FR-032**: The capability MUST be exposed through the HTTP API before any UI consumes it
  (constitution principle II).

## Key Entities

- **Scan library**: The user's directory of card images, organised by someone else and not
  rearranged. Its folder structure is the only record of which cards form a starter deck.
- **Hero folder**: One folder under `Heros/`, holding that hero pack's starter-deck cards,
  deduplicated, with the Core Set reprints absent and nemesis cards in a subfolder.
- **Pack listing**: MarvelCDB's record of a pack — every card, its position, its type, and how
  many copies the pack contains. The authority on identity and quantity.
- **Reprint link**: MarvelCDB's statement that two printings are the same card. The mechanism
  by which an unscanned card is sourced from elsewhere.
- **Resolution**: The pairing of one card with one file, carrying how it was found, so a
  substitution is auditable.
- **Assembly report**: What a run produced — the pack identified, cards placed, images
  borrowed, files unused or uninterpretable, conflicts, low-resolution warnings, and the
  card total against the expected 40.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a scan library and no catalog can produce a printable starter deck
  in under five minutes, against the half-day it takes to author a catalog by hand.
- **SC-002**: Captain America, Star-Lord, Wasp, and Hulk each assemble to exactly 40 cards
  with no manual intervention. These four were measured to reconstruct cleanly and are the
  acceptance set.
- **SC-003**: Thor, Black Widow, Ant-Man, and Ms. Marvel each assemble to exactly 40 cards.
  These four require whole-library search and name fallback, and are the harder acceptance
  set.
- **SC-004**: 100% of files in the folders consulted are either used or named in the report.
  Zero are silently ignored.
- **SC-005**: 100% of images resolved by anything other than an exact positional match are
  reported as such. No substitution is silent.
- **SC-006**: A deck that cannot reach 40 cards fails 100% of the time. No combination of
  inputs yields a short deck that prints.
- **SC-007**: Assembling twice from the same library and snapshot produces a byte-identical
  PDF.
- **SC-008**: A user whose library is missing a card can tell which card, and where the tool
  looked, from the report alone — without reading source code.

## Assumptions

- **The library is not rearranged.** Its structure is what it is, including the
  inconsistencies. The tool adapts to the library; the user does not adapt the library to the
  tool.
- **A hero folder holds that hero's starter-deck cards.** Verified across eight heroes. Where
  a card is filed elsewhere, whole-library search recovers it (FR-015) rather than the
  assumption being abandoned.
- **The trailing number in a filename is MarvelCDB's `position`.** Verified 18/18 for the
  Captain America pack and across eight hero folders. Files not matching are reported, not
  guessed at (FR-021).
- **A starter deck is exactly 40 cards.** A game rule, and the feature's correctness check.
- **MarvelCDB's public card endpoints are available and stable.** This feature uses only the
  documented card and pack endpoints; it does not depend on the undocumented decklist
  endpoints, and does not require an account.
- **The library is a local directory.** The user's Google Drive folder is mounted locally, so
  no Drive-specific client is needed. A remote backend remains out of scope here, as it is in
  feature 001, and would arrive through the existing adapter.
- **Depends on feature 001** for the catalog structures, the validation rules, the resolution
  floor, and PDF generation. This feature introduces no new output format and relaxes none of
  those rules.
- **Aspect cards and modular sets are out of scope.** The library files them separately and
  the user can print them as a later feature. This feature assembles starter decks.
- **Reading the pack's physical decklist card was considered and excluded.** The scanned
  decklist photos are the only printed record of deck composition, but the folder structure
  already carries the same information without optical recognition.
