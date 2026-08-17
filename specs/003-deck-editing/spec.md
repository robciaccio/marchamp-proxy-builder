# Feature Specification: Editing a Deck Before Printing

**Feature Branch**: `003-deck-editing`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Edit an assembled deck before printing it. Start from an
assembled deck or from nothing; remove a card, change how many copies print, replace a card
including with a different printing whose art you prefer, and add any card from the whole
pool rather than just the pack the deck came from. Browse and search that pool by name,
aspect, type, cost, traits, and pack. Keep the result — an edited deck outlives the run,
reopens, re-edits, reprints, and produces the same PDF when nothing has changed. Import a
deck someone else built by MarvelCDB decklist id or URL. See at any time which cards in the
deck have no image in the library."

## Why this exists

Feature 002 answers "what did this pack contain, and where are its images". It deliberately
cannot answer "what do I want on the page". Its composition comes from the scan library's
folder structure, and its one manual escape hatch — User Story 4 — only supplies a *file* for
a card already decided to belong. It changes no membership decision, by design.

Feature 002's own Assumptions section names this feature and names what it needs:

> An editor needs a mutable deck that outlives one run, an interface for browsing the whole
> card pool, and rules for what a deck may contain — none of which this feature needs and all
> of which would make it undeliverable.

Those three things are this feature. It is the other half of the same product: 002 gets a
deck onto the page correctly, 003 lets the user decide what that deck is.

Three properties make it worth building rather than telling the user to edit a catalog by
hand:

- **The pool is wider than the pack.** A pre-built starter deck already draws six of its
  forty cards from the Core Set. A user building their own reaches across every pack
  MarvelCDB knows. An editor confined to the source pack would be useless for the case it
  exists to serve.
- **An edit outlives the run that made it.** A deck the user spent an evening tuning and
  cannot reopen is a deck they will tune again from scratch, or not at all. Persistence is
  not a convenience here; without it the feature has no second use.
- **An edited deck can name cards that were never scanned.** 002 could assume every card it
  placed came from a folder the user owns. This feature cannot: the user may add a card from
  a pack they have never bought. That gap must be visible while editing, not discovered when
  generation stops.

What this feature does *not* do is decide what a deck is allowed to contain. This is a proxy
printer for personal play, not a tournament legality checker. It tells the user when a deck
breaks a deck-building rule and does not stand in their way.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Change what prints (Priority: P1) 🎯 MVP

Someone assembles a hero's starter deck, decides they do not want two copies of a card and do
not want another card at all, makes those two changes, and prints the result — without
reassembling from the library and without editing a file by hand.

**Why this priority**: This is the smallest change that turns a fixed deck into a chosen one,
and it is viable entirely on its own. Everything else in this feature widens what can be
chosen; this establishes that anything can.

**Independent Test**: Assemble any hero's starter deck, remove one card, reduce another to a
single copy, and generate. It succeeds when the PDF contains exactly the cards and counts the
user left behind, and nothing else changed.

**Acceptance Scenarios**:

1. **Given** an assembled deck, **When** the user removes a card, **Then** it no longer
   appears in the deck, the preview, or the generated PDF.
2. **Given** a card present in three copies, **When** the user sets it to one, **Then** it
   appears exactly once in the generated PDF.
3. **Given** a card present in one copy, **When** the user increases it to three, **Then** it
   appears exactly three times, from the same image.
4. **Given** a double-sided card, **When** the user changes its copy count, **Then** both
   faces follow that count together and neither is left behind.
5. **Given** any edit, **When** the user views the preview, **Then** the preview reflects the
   edit before any PDF is generated.
6. **Given** an edited deck, **When** the user generates, **Then** the PDF matches the
   preview page for page and card for card, as feature 001 already requires.
7. **Given** a deck the user has emptied entirely, **When** they attempt to generate, **Then**
   generation is refused naming the reason, and no empty PDF is produced.

---

### User Story 2 - Keep the deck (Priority: P2)

The user saves the deck they tuned, closes the application, comes back a week later, reopens
it, changes one more card, and reprints.

**Why this priority**: Without it the feature is a single-session toy — every edit is thrown
away when the process ends, and a user who wants the same deck twice does the same work
twice. It is P2 rather than P1 only because User Story 1 is demonstrably useful within one
session.

**Independent Test**: Edit a deck, save it, restart the application, reopen it. It succeeds
when every card, every count, and every printing choice is exactly as it was left, and
regenerating produces the same PDF as before.

**Acceptance Scenarios**:

1. **Given** an edited deck, **When** the user saves it and the application is restarted,
   **Then** the deck is listed and can be reopened.
2. **Given** a reopened deck, **When** the user compares it to what they saved, **Then** every
   card, quantity, and printing choice is identical.
3. **Given** a reopened, unchanged deck, **When** the user regenerates against the same
   library and the same upstream snapshot, **Then** the PDF is byte-identical to the one
   generated before.
4. **Given** a saved deck, **When** the user renames or deletes it, **Then** that takes effect
   and no other saved deck is affected.
5. **Given** two decks the user has given the same name, **When** both are saved, **Then**
   both exist and are distinguishable, rather than one overwriting the other.
6. **Given** a saved deck reopened against a newer upstream snapshot, **When** any card it
   references has been renamed, reprinted, or is no longer present, **Then** that is reported
   by name, and no card is silently substituted.
7. **Given** any save, **When** it completes, **Then** nothing has been written into the scan
   library.
8. **Given** a PDF generated from a saved deck, **When** the user consults the run's log,
   **Then** the deck, the snapshot revision, and the library it was generated against are all
   recorded, so the PDF traces back to the inputs that produced it.

---

### User Story 3 - Find and add any card in the pool (Priority: P2)

The user wants a card that is not in the pack their deck came from. They search the whole card
pool by name, or narrow it by aspect, type, cost, traits, or pack, find the card, and add it.
They can also start from an empty deck and build one this way from nothing.

**Why this priority**: This is what makes the deck genuinely theirs rather than a subtracted
version of someone else's. It is the widest single capability in the feature, and User Story 1
is deliverable without it.

**Independent Test**: Starting from a hero deck that came from one pack, find a Core Set basic
card by name and add it. It succeeds when the card is in the deck and prints.

**Acceptance Scenarios**:

1. **Given** a deck assembled from one pack, **When** the user searches for a card from a
   different pack, **Then** it is found and can be added.
2. **Given** a search by name fragment, **When** results are shown, **Then** they cover the
   whole known card pool, not only packs present in the user's library.
3. **Given** filters on aspect, type, cost, traits, and pack, **When** the user combines them,
   **Then** results satisfy all of them together.
4. **Given** the same search run twice, **When** results are shown, **Then** they are in the
   same order both times.
5. **Given** an empty deck, **When** the user adds cards by search alone, **Then** a complete
   deck can be built without starting from an assembled one.
6. **Given** any search or browse, **When** it runs, **Then** no card image is fetched from
   any remote source.

---

### User Story 4 - Know which cards will not print (Priority: P2)

At any point while editing, the user can see which cards in the deck have no image in their
library — because an edited deck can name cards they have never scanned.

**Why this priority**: Shares the editing surface with User Story 3 and is the other half of
it. Adding a card the user does not own is legitimate and expected; discovering it only when
generation stops is not. Without this, the wider pool becomes a trap.

**Independent Test**: Add a card from a pack the user does not own. It succeeds when the deck
shows that card as having no image, by name, before any attempt to generate.

**Acceptance Scenarios**:

1. **Given** a deck containing a card with no image anywhere in the library, **When** the user
   views the deck, **Then** that card is named as unresolved without the user having to
   attempt generation.
2. **Given** a card whose own printing has no image but another printing does, **When** the
   user views the deck, **Then** it is shown as resolvable from that other printing, and
   distinguished from a card with no image at all.
3. **Given** an unresolved card, **When** the user adds it anyway, **Then** the addition is
   permitted and flagged, never refused.
4. **Given** an unresolved card, **When** the user attempts to generate, **Then** the run
   stops naming that card, exactly as feature 002 requires, and prints only if the user
   explicitly asks to print without it.
5. **Given** an unresolved card, **When** the user chooses a file for it themselves, **Then**
   it resolves, using feature 002's manual resolution unchanged.
6. **Given** a saved deck whose image has disappeared from the library since it was saved,
   **When** it is reopened, **Then** the card is shown as unresolved rather than appearing to
   be fine until generation.

---

### User Story 5 - Choose the card, and choose the art (Priority: P3)

The user swaps one card for another, or keeps the card and swaps which printing supplies its
art because they prefer that version.

**Why this priority**: Swapping one card for another is reachable by removing and adding, so
it is convenience. Choosing among printings of the *same* card is not reachable that way and
is the real content of this story — but it is a preference, not a blocker, so it ranks below
the capabilities that decide whether a deck can be built at all.

**Independent Test**: Take a card the library holds in two printings and switch which one
supplies the image. It succeeds when the deck's composition is unchanged and the generated PDF
shows the other art.

**Acceptance Scenarios**:

1. **Given** a card in the deck, **When** the user replaces it with a different card, **Then**
   the deck's other entries are untouched and the copy count carries over unless the user
   changes it.
2. **Given** a card the library holds in more than one printing, **When** the user chooses a
   different printing, **Then** the card's identity, name, and copy count are unchanged and
   only the image differs.
3. **Given** a printing choice, **When** the deck is saved and reopened, **Then** the same
   printing is still selected.
4. **Given** a card with only one printing available in the library, **When** the user looks
   for alternatives, **Then** none are offered, rather than being offered a printing that
   cannot produce an image.

---

### User Story 6 - Import a deck someone else built (Priority: P3)

The user has a MarvelCDB decklist id or URL for a deck someone published. They import it and
edit it like any other deck.

**Why this priority**: It is a shortcut into the editor, not a capability the editor needs. It
also rests on an endpoint MarvelCDB does not document, so it is the part of this feature most
likely to need changing later — a good reason to keep it last and keep it isolated.

**Independent Test**: Import a known public decklist by id. It succeeds when the deck's cards
and quantities match the published list exactly and the deck can then be edited and printed.

**Acceptance Scenarios**:

1. **Given** a MarvelCDB decklist id, **When** the user imports it, **Then** the resulting
   deck's cards and quantities match the published decklist exactly.
2. **Given** a MarvelCDB decklist URL rather than a bare id, **When** the user imports it,
   **Then** it is accepted and yields the same deck as the id would.
3. **Given** an imported deck, **When** the user edits it, **Then** every editing capability
   in this feature applies to it unchanged.
4. **Given** an id that does not exist, is not a decklist, or is not publicly readable,
   **When** the user imports it, **Then** the failure names which of those it was and no
   partial deck is created.
5. **Given** an imported decklist referencing a card code the snapshot does not contain,
   **When** the import runs, **Then** that code is reported and the import does not silently
   drop it.
6. **Given** an imported deck, **When** the user saves it, **Then** the decklist it came from
   is recorded alongside it.
7. **Given** the decklist endpoint being unavailable, **When** the user imports, **Then**
   import fails saying so, and every other capability in this feature continues to work.

---

### User Story 7 - Be told when the deck breaks a rule (Priority: P3)

The deck the user has built is 52 cards, or holds four copies of a card, or mixes two aspects.
The tool says so, names the cards involved, and lets them print it.

**Why this priority**: It is the feature's smallest surface and the one the user is least
blocked by — a deck that breaks a rule still prints. It is worth building because a user
proxying a deck for real play usually *wants* to know, and worth building last because getting
it wrong by blocking would be worse than not having it.

**Independent Test**: Build a deck that breaks a rule. It succeeds when the tool names the
rule and the cards, and the deck still prints.

**Acceptance Scenarios**:

1. **Given** a deck outside the legal card-count range, **When** the user views it, **Then**
   the count and the range are stated.
2. **Given** more copies of a card than its copy limit permits, **When** the user views the
   deck, **Then** that card is named specifically, not reported as a generic illegality.
3. **Given** any rule advisory, **When** the user chooses to print anyway, **Then** the deck
   prints.
4. **Given** an edit that resolves an advisory, **When** the user makes it, **Then** the
   advisory clears without the deck being reopened.
5. **Given** a deck that breaks no rule, **When** the user views it, **Then** no advisory is
   shown and the absence is not ambiguous with the check not having run.

---

### Edge Cases

- **A quantity set to zero.** Indistinguishable in outcome from removing the card, so it must
  be defined as one behaviour rather than leaving a zero-count entry that prints nothing and
  confuses the count.
- **A negative or absurd quantity.** Refused at entry with the specific reason, never stored.
- **A card added that has no image in any printing.** Permitted and flagged (User Story 4),
  because refusing it would silently prevent the user building what they want.
- **A saved deck whose library folder no longer exists.** The deck still opens and is still
  editable; every card reports as unresolved, naming the folder, rather than the deck
  becoming unopenable.
- **A saved deck reopened against a newer upstream snapshot** where a card was renamed,
  errata'd, reprinted, or removed. Reported by name; never silently resolved to whatever now
  holds that code.
- **A saved deck reopened against a *different* library** from the one it was built against.
  Image availability is recomputed against the library in use, not remembered from the save.
- **An imported decklist containing a hero, obligation, or nemesis card.** 002 excludes these
  from the player deck; this feature does not gatekeep, so they are included and flagged as
  advisories rather than dropped.
- **A card whose chosen printing later disappears from the library.** Reported as unresolved
  against that choice, not silently re-resolved to a different printing behind the user's
  back.
- **Two entries for the same card arriving from different sources** — one from the assembled
  deck, one added by hand. Merged into one entry with a combined count, so the deck never
  holds the same card twice under two entries.
- **A search matching nothing.** Reported as no matches, distinguishable from the pool being
  unavailable.
- **MarvelCDB unreachable while browsing.** The pool serves from 002's captured snapshot. With
  no snapshot at all, browsing fails saying which is missing — it never guesses.
- **A search that would match most of the pool.** Results must remain usable and bounded
  rather than attempting to present several thousand cards at once.
- **An edit made while a generation for the same deck is in flight.** The generated PDF
  reflects the deck as it was when generation started, and which state that was must be
  recoverable from the run's log.

## Requirements *(mandatory)*

### Scope and safety

- **FR-001**: The application MUST NOT download card artwork from MarvelCDB or any other
  remote source. Every printed image MUST come from the user's local library. Feature 002's
  FR-002 is restated here because this feature makes it possible to reference cards the user
  has never scanned, which is exactly when downloading art would be tempting.
- **FR-002**: Outbound network access MUST remain limited to MarvelCDB's public JSON API,
  including the decklist endpoint this feature adds.
- **FR-003**: All library reads MUST go through the existing asset adapter (constitution
  principle III). Editing logic MUST NOT learn where a binary lives.
- **FR-004**: The scan library MUST remain read-only. No editing, saving, or import operation
  MUST write to it, move within it, or delete from it.

### Editing a deck

- **FR-005**: The user MUST be able to remove a card from a deck entirely.
- **FR-006**: The user MUST be able to set how many copies of a card print.
- **FR-007**: Setting a card's copy count to zero MUST be defined as removing it. A deck MUST
  NOT hold an entry that prints nothing.
- **FR-008**: A copy count that is negative or not a whole number MUST be refused at entry
  with the specific reason, and MUST NOT be stored.
- **FR-009**: The user MUST be able to add any card in the known pool to a deck, regardless of
  which pack it belongs to and regardless of whether the deck came from that pack.
- **FR-010**: The user MUST be able to replace a card with a different card. The replacement
  MUST carry over the copy count unless the user changes it.
- **FR-011**: The user MUST be able to choose which printing of a card supplies its image,
  among printings the library actually holds an image for. The choice MUST change the image
  and MUST NOT change the card's identity, its name, or its copy count.
- **FR-012**: The user MUST be able to start from an empty deck and build one entirely by
  adding cards.
- **FR-013**: The user MUST be able to start from a deck feature 002 assembled, without
  reassembling it from the library.
- **FR-014**: Two entries resolving to the same card MUST be merged into one entry carrying
  the combined count. A deck MUST NOT hold the same card under two entries.
- **FR-015**: Editing MUST NOT alter card identity data — codes, names, types, costs, traits,
  aspects. That data comes from MarvelCDB and the user edits deck membership, not cards.
- **FR-016**: Every edit MUST be reflected in the page preview before any PDF is generated,
  reusing feature 001's preview rather than a second rendering path.
- **FR-017**: A deck containing no cards MUST NOT produce a PDF. Generation MUST be refused
  naming the reason.
- **FR-018**: Both faces of a double-sided card MUST follow one copy count together. It MUST
  NOT be possible to leave a deck holding a front without its back.

### Browsing the card pool

- **FR-019**: The user MUST be able to browse the entire card pool the upstream snapshot
  knows, not only the packs present in their library.
- **FR-020**: The user MUST be able to search and filter that pool by name, aspect, type,
  cost, traits, and pack, and MUST be able to combine those filters.
- **FR-021**: Every result MUST state whether the user's library holds an image for that card,
  so the decision to add is made with that known rather than discovered afterwards.
- **FR-022**: Results MUST be deterministically ordered. The same query against the same
  snapshot MUST return the same results in the same order.
- **FR-023**: A query matching nothing MUST be reported as no matches, distinguishably from
  the pool being unavailable.
- **FR-024**: Results MUST be bounded so that a broad query stays usable, and the bound MUST
  be visible rather than silently truncating.
- **FR-025**: Browsing and searching MUST be served from the captured snapshot and MUST NOT
  issue upstream requests that grow with the number of cards examined or searches performed
  (feature 002's FR-040, restated for a surface that invites repeated querying).

### Knowing what will not print

- **FR-026**: At any time while editing, the deck MUST state which of its cards have no image
  in the library in use, naming each.
- **FR-027**: A card whose own printing lacks an image but which is resolvable from another
  printing through a reprint link MUST be distinguished from a card with no image anywhere.
- **FR-028**: Adding a card with no available image MUST be permitted and flagged. It MUST NOT
  be refused — refusing would silently prevent the user building what they want.
- **FR-029**: Generating a deck containing an unresolved card MUST follow feature 002 without
  relaxation: the run stops by name, and prints only on the user's explicit act, with the
  omission named in the report and the log. This feature MUST NOT introduce any path that
  prints a deck short without someone having said so.
- **FR-030**: Feature 002's manual resolution MUST remain available for edited decks, so a
  card the library lacks can be supplied by file.
- **FR-031**: Image availability MUST be computed against the library in use at the time, not
  read back from what was recorded when the deck was saved.

### Keeping a deck

- **FR-032**: A deck MUST be able to be saved so that it survives the application process
  ending.
- **FR-033**: Saved decks MUST be able to be listed, reopened, further edited, renamed, and
  deleted.
- **FR-034**: Reopening a saved deck MUST reproduce exactly what was saved — every card, every
  copy count, and every printing choice.
- **FR-035**: A saved deck MUST record the upstream snapshot revision and the library it was
  built against, so a generated PDF traces to the inputs that produced it (constitution
  principle V; feature 002's FR-044).
- **FR-036**: Regenerating an unchanged saved deck against the same library and the same
  snapshot MUST produce a byte-identical PDF (constitution principle V).
- **FR-037**: Reopening a saved deck against a different snapshot MUST report every card whose
  identity has changed or is no longer present, naming each. A card code MUST NOT be silently
  resolved to whatever now holds it.
- **FR-038**: Saving MUST NOT write anything into the scan library (FR-004 restated for the
  one operation in this feature that writes at all).
- **FR-039**: A saved deck MUST store card references, copy counts, and printing choices only.
  It MUST NOT store card text or card images, which are not the project's to keep (feature
  002's FR-038; constitution *Distribution scope*).
- **FR-040**: Decks MUST be identified by a stable identifier the application assigns. A
  user-supplied name MUST be a label, so two decks MAY share a name without one destroying the
  other.

### Importing a deck

- **FR-041**: The user MUST be able to import a deck by MarvelCDB decklist id or by a
  MarvelCDB decklist URL, and both MUST yield the same deck.
- **FR-042**: An imported deck's cards and copy counts MUST match the published decklist
  exactly. The application MUST NOT add, drop, or reorder entries silently.
- **FR-043**: An imported deck MUST be editable by every capability in this feature, with no
  exceptions arising from how it was created.
- **FR-044**: An id or URL that does not exist, is not a decklist, or is not publicly readable
  MUST fail naming which of those it was, and MUST NOT leave a partial deck behind.
- **FR-045**: A card code in the decklist that the snapshot does not contain MUST be reported
  by code. It MUST NOT be silently dropped.
- **FR-046**: An imported deck MUST record the decklist it came from, so its origin survives
  alongside it.
- **FR-047**: The decklist endpoint is undocumented. Its unavailability MUST fail import alone
  and MUST NOT degrade editing, browsing, saving, or generation.
- **FR-048**: Feature 002's conduct requirements toward MarvelCDB (FR-038 through FR-043 —
  stated purpose, HTTP caching, bulk over per-item fetching, descriptive `User-Agent`,
  backoff, conservative behaviour absent a published rate limit) MUST apply unchanged to every
  endpoint this feature adds.
- **FR-049**: Imported decklists are another person's content, viewed for the user's personal
  use. The application MUST NOT mirror, aggregate, index, or republish them.

### Deck-building advisories

- **FR-050**: The application MUST report when the deck breaks a deck-building rule, naming
  the rule and the specific cards involved.
  [NEEDS CLARIFICATION: which rules are checked — deck size range and per-card copy limits
  only, or also aspect legality, or also hero-specific eligibility? Each step widens the
  upstream data required and the work substantially.]
- **FR-051**: A rule advisory MUST NOT prevent the user from building the deck they want.
  This is a proxy printer for personal play, not a legality checker.
  [NEEDS CLARIFICATION: the posture when printing a rule-breaking deck — warn only and print;
  or warn and require an explicit acknowledgement first, matching feature 002's FR-030a
  pattern for printing an incomplete deck; or warn only, except hard-refuse the physically
  impossible.]
- **FR-052**: An advisory MUST name the specific cards at fault. A generic "this deck is
  illegal" is not acceptable (constitution principle V).
- **FR-053**: Advisories MUST be recomputed as the deck changes and MUST be visible before
  printing, not only afterwards.
- **FR-054**: A deck that breaks no rule MUST be distinguishable from one where the check did
  not run.
- **FR-055**: Rule data — copy limits, aspects, and card eligibility — MUST come from
  MarvelCDB. The application MUST NOT carry a hand-maintained table of deck-building rules.

### Interface and output

- **FR-056**: Every capability in this feature MUST be exposed through the HTTP API before any
  UI consumes it, and the wizard MUST reach it only through that API (constitution principle
  II).
- **FR-057**: Generation MUST reuse feature 001's layout, resolution enforcement, and PDF
  path. This feature adds no new output format.
- **FR-058**: Every generation MUST log the resolved deck, the snapshot revision, the library
  in use, and the outcome (constitution principle V).
- **FR-059**: A generation MUST be produced from the deck as it stood when generation started,
  and which state that was MUST be recoverable from the run's log.

## Key Entities

- **Deck**: A mutable, named collection of card references with copy counts and printing
  choices, which outlives the run that created it. The thing 002 explicitly does not have.
- **Deck entry**: One card in a deck, carrying its copy count and, where the user has made
  one, the printing chosen to supply its image. At most one entry per card.
- **Card pool**: Every card the captured MarvelCDB snapshot knows, independent of what the
  user's library holds. The set a user may add from.
- **Printing choice**: A user's selection of which printing of a card supplies its art, among
  those the library can actually produce an image for.
- **Image availability**: Per deck entry, whether the library in use can produce an image —
  directly, through a reprint link, or not at all. Recomputed against the current library, not
  remembered.
- **Rule advisory**: A statement that the deck breaks a named deck-building rule, naming the
  cards. Information, not a gate.
- **Imported decklist**: A deck obtained from MarvelCDB by id or URL, together with the record
  of where it came from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can take an assembled starter deck, remove a card, change another card's
  copy count, and generate the result in under two minutes, without reassembling from the
  library and without editing any file by hand.
- **SC-002**: A user can find a card from a pack their deck did not come from — a Core Set
  basic card into a non-Core hero deck — and add it, using search alone, in under one minute.
- **SC-003**: 100% of deck cards with no image available in the library in use are named while
  editing, before any generation is attempted. Zero are first discovered at print time.
- **SC-004**: Reopening a saved deck reproduces every card, copy count, and printing choice
  exactly, 100% of the time.
- **SC-005**: Regenerating an unchanged saved deck against the same library and snapshot
  produces a byte-identical PDF.
- **SC-006**: Importing a publicly readable MarvelCDB decklist yields a deck whose card codes
  and copy counts match the published list exactly, for 100% of decklists tested.
- **SC-007**: A user can build a complete 40-card deck from an empty start using only search
  and add.
- **SC-008**: Zero image bytes are fetched from any remote source by any operation in this
  feature. Every printed image comes from the local library.
- **SC-009**: Browsing and searching the pool issues a number of upstream requests that does
  not grow with the number of cards examined or the number of searches performed.
- **SC-010**: Reopening a saved deck against a newer snapshot names 100% of the cards whose
  identity changed or disappeared. Zero silent substitutions.
- **SC-011**: No rule advisory prevents a deck from being built. 100% of decks a user assembles
  can be built, whatever advisories they carry.
- **SC-012**: No editing operation results in a PDF that is short a card without the user
  having explicitly said to print without it, matching feature 002's SC-006 under a wider set
  of inputs.
- **SC-013**: The decklist endpoint being unavailable affects import alone. Editing, browsing,
  saving, and generation continue to work.

## Assumptions

- **Depends on feature 002** for the captured MarvelCDB snapshot, pack and card data, reprint
  links, image resolution against the library, and manual resolution of a card the library
  lacks. This feature adds one upstream endpoint — the decklist endpoint — and no new
  resolution logic.
- **Depends on feature 001** for the catalog structures, page layout, the resolution floor,
  the page preview, and PDF generation. This feature adds no new output format and relaxes no
  existing rule.
- **The card pool is the snapshot, not the library.** A user may add a card they have never
  scanned. That is intended, and FR-026 through FR-029 exist to keep it from being a surprise.
- **Saved decks live in an application-managed local store** on the user's own machine —
  never inside the scan library, never in the repository, and never committed. This is the
  first thing the application writes during normal operation, and the read-only guarantee it
  makes about the library is unaffected.
- **Printing choice is limited to printings the library can actually produce an image for.**
  Offering a printing that cannot print would be a false choice.
- **The decklist endpoint is undocumented.** MarvelCDB publishes decklists at an endpoint that
  works today but is not part of its documented API. It is used with the same restraint as the
  documented ones, and FR-047 confines the cost of its disappearance to import alone.
- **Deck-building rule data comes from MarvelCDB fields**, not from a rules engine this
  project maintains. Which fields, and therefore which rules can be checked, is the open
  question in FR-050.
- **Single user, single machine, loopback-only** (feature 001's FR-0A2). There are no
  accounts, no concurrent editors, and no access control on saved decks, because there is
  nobody else to control access against.
- **An edited deck may contain anything the user chooses**, including encounter, obligation,
  and nemesis cards that feature 002 excludes from a player deck. The editor reports; it does
  not gatekeep.
- **Out of scope**: sharing or publishing decks anywhere, uploading a deck back to MarvelCDB,
  deck ratings or comments, collaboration, and anything that redistributes card artwork or
  MarvelCDB's card text. The application prints from the user's own scans of cards they own,
  and publishes nothing — matching the constitution's *Distribution scope* clause.
- **Aspect cards and modular sets remain out of scope as their own printable products**, as
  they are in feature 002. Nothing stops a user adding an aspect card to a deck here; what is
  out of scope is a separate "print this modular set" capability.
