# Feature Specification: Catalog Scaffolding from a Card Image Directory

**Feature Branch**: `002-catalog-scaffold`

**Created**: 2026-08-01

**Status**: Draft

**Input**: User description: "Catalog scaffolding from a card image directory. A
command-line tool that walks the configured card image directory and writes a starter
catalog JSON file, so that authoring a catalog by hand stops being the main barrier between
a folder of scans and a printable sheet."

## Why this exists

Feature 001 built everything needed to turn a catalog into a printable sheet, and then left
the catalog itself as an exercise for the user. Authoring one by hand for a single hero pack
means writing roughly two hundred lines of JSON: thirty cards, each with an identifier, a
display name, a pack, a number, and an exact relative path, plus a deck listing every entry.

The work divides cleanly in two, and that division is the whole point of this feature:

- **Mapping files to cards is mechanical.** The identity, the pack, the number, the path,
  and the pairing of a double-sided card's two faces are all recoverable from the directory
  and the filenames. A person doing this by hand is doing a machine's job, badly — one
  mistyped path is a card that fails to print.
- **Quantities are not recoverable.** Nothing in a filename says that Heroic Strike is ×3.
  That number lives on the physical decklist card in the pack, and a human has to read it.

So the tool does the first half completely, and refuses to pretend it can do the second.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a catalog from a folder of scans (Priority: P1) 🎯 MVP

Someone has a directory of card scans and no catalog. They run one command and get a
catalog naming every card, every printing, and every image path, together with a report of
exactly what a human still has to supply.

**Why this priority**: This is the barrier. Without it the application is unusable by anyone
who has not already written a catalog by hand, which today is almost nobody.

**Independent Test**: Point the tool at a directory of scans with no catalog present. It
succeeds when the output names every card correctly and the only work left is typing
quantities off the decklist card.

**Acceptance Scenarios**:

1. **Given** a directory of scans and no catalog, **When** the user scaffolds, **Then** a
   catalog is written containing one card per distinct card, each with its pack, its number,
   and the exact relative path to its image.
2. **Given** a card whose front and back are separate files following the pack's front/back
   convention, **When** the user scaffolds, **Then** one double-sided card is produced
   carrying both faces, not two single-sided cards.
3. **Given** the same card published in two packs, **When** the user scaffolds, **Then** one
   card is produced with two printings, not two cards sharing a name.
4. **Given** a finished run, **When** the user opens the output, **Then** every entry that
   needs a quantity is visibly unfilled, and the tool has already reported how many there
   are.
5. **Given** a scaffold whose quantities have not been filled in, **When** the application
   loads it, **Then** it is rejected as invalid and names the entries still outstanding — an
   unfinished catalog MUST NEVER load as though it were finished.

---

### User Story 2 - Grow the library without losing work (Priority: P2)

The user buys another pack, drops the scans in, and scaffolds again. Everything they typed
by hand the first time is still there.

**Why this priority**: Without it the tool is a one-shot. The second time it runs it becomes
destructive, and a tool that destroys an afternoon of typing gets run once and never again.

**Independent Test**: Scaffold, fill in quantities by hand, add more scans, scaffold again.
It succeeds when the new cards appear and not one hand-entered value has changed.

**Acceptance Scenarios**:

1. **Given** a catalog with quantities filled in, **When** the user scaffolds over it,
   **Then** every existing quantity is preserved exactly.
2. **Given** a catalog whose identifiers or deck names the user has renamed, **When** the
   user scaffolds over it, **Then** those edits survive rather than reverting to generated
   values.
3. **Given** a directory that has not changed, **When** the user scaffolds twice, **Then**
   the two results are identical, so a re-run can be diffed to see only what genuinely
   changed.
4. **Given** an image that has been deleted from the directory, **When** the user scaffolds
   over an existing catalog, **Then** the tool reports what is now missing rather than
   silently dropping the card or silently keeping a path that resolves to nothing.

---

### User Story 3 - Find out what the tool could not read (Priority: P3)

A file whose name does not follow the convention is named in the report, so the user can
rename it or accept that it needs a hand-written entry.

**Why this priority**: A scaffolder that quietly skips what it does not understand produces
a catalog that looks complete and is not. The user finds the gap when a deck fails to print,
which is the worst possible moment.

**Independent Test**: Include a deliberately misnamed file. It succeeds when that file is
named in the report and the exit status reflects that something needs attention.

**Acceptance Scenarios**:

1. **Given** a file whose name the convention cannot parse, **When** the user scaffolds,
   **Then** that file is named in the report and never silently omitted.
2. **Given** two files claiming the same pack and number, **When** the user scaffolds,
   **Then** both are named as a conflict rather than one arbitrarily winning.
3. **Given** a directory where no file matches the convention at all, **When** the user
   scaffolds, **Then** the tool says the convention did not match rather than writing an
   empty catalog.

---

### Edge Cases

- **A double-sided card missing its back.** A front with no matching back is a card that
  cannot print. Reported as an incomplete pair, never emitted as a single-sided card.
- **A back with no front.** The same problem from the other side; reported, not guessed at.
- **The output already exists.** The tool must not overwrite hand-entered work as a side
  effect of being run. Merging is the deliberate behaviour (User Story 2); replacing is not
  the default.
- **A file that is not a card**, such as the decklist photo that ships in the same folder.
  Excluded from the catalog, and the exclusion is stated rather than silent.
- **A scan below the resolution the application requires.** The scaffold's job is mapping,
  not gatekeeping — but writing an entry certain to fail at print time helps nobody, so
  under-resolution scans are warned about at scaffold time.
- **Names holding characters a filesystem will not.** "Captain America's Shield" reaches the
  disk with its apostrophe substituted; the display name must come back as the card is
  really called.
- **Cards a deck uses from another pack.** A deck proposed from one pack's folder cannot
  know the deck also draws on the Core Set. Those additions are manual, and the tool must
  say so rather than implying the deck is complete.
- **An empty directory.** Reported as empty. No file is written.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and safety**

- **FR-001**: The tool MUST read the card image directory and MUST NOT modify it in any way.
  The read-only guarantee feature 001 makes about the asset directory continues to hold
  without exception.
- **FR-002**: The tool MUST make no outbound network call. It works entirely on local files.
- **FR-003**: The tool MUST write exactly one file — the catalog — at a location the user
  names, and MUST NOT write anything else anywhere.
- **FR-004**: The tool MUST NOT replace an existing catalog by default. Overwriting
  hand-entered work MUST require the user to have asked for it explicitly.

**What it infers**

- **FR-005**: The tool MUST derive, for every card image it recognises: a stable identifier,
  a display name, the publishing pack, the pack-scoped number, and the exact relative path
  to the file.
- **FR-006**: The emitted catalog MUST continue to state every image path explicitly.
  Inference happens once, at scaffold time, and produces explicit data — the application
  itself MUST NOT gain any ability to find images by name, folder, or convention.
- **FR-007**: The tool MUST pair the two faces of a double-sided card into a single card
  carrying both, using the pack's front/back numbering convention.
- **FR-008**: The tool MUST represent one card published in several packs as a single card
  with several printings, never as duplicate cards.
- **FR-009**: The tool MUST recover display names as the card is really named, reversing
  substitutions the filesystem forced onto the filename.
- **FR-010**: The tool MUST propose at least one deck, so the output is usable rather than a
  bare list of cards.

**What it refuses to infer**

- **FR-011**: The tool MUST NOT invent quantities. Every proposed deck entry MUST carry a
  quantity that is visibly unfilled.
- **FR-012**: A scaffold whose quantities are not filled in MUST NOT load as a valid
  catalog. Unfinished and invalid MUST be the same state, so an incomplete catalog cannot
  quietly produce a deck with the wrong number of cards.
- **FR-013**: The tool MUST report, as a count, how many entries still need a quantity.
- **FR-014**: The tool MUST state that a proposed deck covers only the cards found in the
  pack it was built from, and that cards drawn from other packs must be added by hand.

**Reporting**

- **FR-015**: Every file in the directory MUST be either represented in the output or named
  in the report. Silent omission is prohibited.
- **FR-016**: The tool MUST report every file whose name it could not interpret, naming each
  one.
- **FR-017**: The tool MUST report conflicts — two files claiming one identity — naming both
  sides, and MUST NOT resolve them by arbitrary choice.
- **FR-018**: The tool MUST report incomplete double-sided pairs, naming the face present
  and the face missing.
- **FR-019**: The tool MUST report scans below the resolution the application requires at
  print size, as a warning rather than a refusal.
- **FR-020**: The tool's exit status MUST distinguish "wrote a catalog with nothing
  outstanding but quantities" from "wrote a catalog but something needs attention" from
  "wrote nothing", so it is usable from a script without parsing prose.
- **FR-021**: The tool MUST state the naming convention it applied, so a user whose files do
  not match can see what was expected instead of guessing.

**Re-running**

- **FR-022**: Scaffolding over an existing catalog MUST preserve every quantity already
  entered.
- **FR-023**: Scaffolding over an existing catalog MUST preserve user edits to identifiers
  and display names rather than reverting them to generated values.
- **FR-024**: Scaffolding twice over an unchanged directory MUST produce identical output.
- **FR-025**: Scaffolding over an existing catalog MUST report cards whose images have since
  disappeared, and MUST NOT silently drop them nor silently keep a dead path.

### Key Entities

- **Card image file**: One file in the directory. Its name and location either carry enough
  to recover a card's identity, pack, and number — or they do not, in which case it is
  reported rather than skipped.
- **Naming convention**: The stated pattern by which a filename is read. An assumption the
  tool checks and reports against, never hidden behaviour.
- **Scaffold report**: What a run produced — cards found, files not understood, conflicts,
  incomplete pairs, low-resolution warnings, and the count of quantities outstanding.
- **Catalog**: The output. The format feature 001 already defines and validates; this
  feature adds no new schema and changes no existing rule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a folder of scans and no catalog can produce a loadable catalog,
  with nothing left but entering quantities, in under five minutes — against the half-day it
  takes to write one by hand.
- **SC-002**: 100% of files in the directory are either represented in the output or named
  in the report. Zero are silently ignored.
- **SC-003**: For a reference hero pack of about thirty cards, every identity, pack, number,
  image path, and double-sided pairing is correct with no manual correction beyond
  quantities.
- **SC-004**: An unfinished scaffold is rejected by catalog validation 100% of the time.
  No combination of inputs yields a silently-wrong deck.
- **SC-005**: Re-running over an unchanged directory produces a byte-identical file.
- **SC-006**: Re-running after the library grows preserves 100% of previously entered
  quantities and identifier edits.
- **SC-007**: A user whose filenames do not match the convention can tell that from the
  report alone, without reading source code or documentation.

## Assumptions

- **The naming convention is the one the user's library already uses**: a pack-scoped number
  at the end of the filename, and a front/back suffix distinguishing the two faces of a
  double-sided card. Supporting arbitrary user-defined patterns is **out of scope** — the
  convention is stated and checked, and files that do not match are reported for hand entry.
- **Deck proposals are per pack folder.** One deck is proposed per hero pack directory,
  holding the cards found there. This is a starting point, not a finished deck: the
  reference pack's own deck draws six of its forty cards from the Core Set, and no tool can
  infer that from a directory listing.
- **A proposed deck includes every card found in the pack folder,** obligation and nemesis
  cards included, even though those are not part of a player deck. Pruning is the user's,
  because the distinction is a rules fact and not a filesystem fact.
- **Quantities are entered by hand from the pack's decklist card.** Reading that card
  automatically — by optical recognition or otherwise — was considered and deliberately
  excluded: a misread digit produces a deck that is wrong and validates cleanly, which is
  precisely the failure this feature exists to prevent.
- **This is a command-line tool**, not an interface in the browser. The application's
  guarantee that it never writes to disk during normal operation stays intact, because the
  only thing that writes is a separate command the user runs deliberately.
- **Depends on feature 001** for the catalog format, the validation rules, and the
  resolution floor. This feature introduces no new schema and relaxes none of those rules.
- **The directory is a local folder.** Remote or object storage is out of scope here, as it
  is in feature 001.
