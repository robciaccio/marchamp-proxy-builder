# Feature Specification: Starter Deck Assembly from a Scan Library

**Feature Branch**: `002-starter-deck-assembly`

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

What makes this safe is that the tool can check its own work — but not, as an earlier draft
of this spec claimed, by requiring the deck to total 40. The deckbuilding rules permit 40 to
50 cards, and while every pre-built deck examined so far contains exactly 40, that has been
observed rather than proven across the whole card pool.

So the check is completeness, not arithmetic: every card the tool decides belongs in the deck
must resolve to an image, and one that does not stops the run by name. The total is reported
alongside, and a total other than 40 is flagged as a strong signal that something did not
resolve — because in every case measured so far, it was. That is a warning the user can
judge, not a gate that would refuse a legitimately larger deck.

Stopping is the default, not the last word. A user who knows a card is missing and wants the
other thirty-nine on paper anyway can say so and print. What the tool owes them is that the
gap is never invisible — named when it happens, and still named in the report and the log
afterwards. The failure this feature exists to prevent is a deck that is quietly wrong, not a
deck the user knowingly chose to print short.

## Clarifications

### Session 2026-08-16

- **Q: Which cards belong in the deck, given MarvelCDB does not record deck membership?**
  A: The hero folder's own contents say which. This was measured: summing a pack's hero set,
  main aspect, and basic cards yields 43, 43, 43, 43, 40, 43, 43, 43, 43, 43, 42, and 37
  across twelve packs, so membership is not derivable from pack contents. Official starter
  decklists exist on MarvelCDB only for the five Core Set heroes. This answers membership
  only — *how many* of each card and *where its image lives* are separate questions, answered
  below.
- **Q: How many copies of each card?**
  A: From MarvelCDB's `quantity` for the printing being assembled (FR-016). The scanner made
  one scan per distinct card, never one per physical copy, so the count can never come from
  counting files.
- **Q: What about cards the scanner skipped because they were already in the Core Set?**
  A: MarvelCDB records that two printings are the same card, so a pack card absent from the
  hero folder is recognised as belonging to the deck and its image is taken from the printing
  it duplicates (FR-014, FR-022). For Captain America that recovers Make the Call, The Power
  of Leadership, Mockingbird, Energy, Genius, and Strength — eight physical cards.
- **Q: How are a file and a MarvelCDB card matched?**
  A: On `(pack_code, position)`. The trailing number in the filename is exactly MarvelCDB's
  `position`. Card *names* in filenames are unreliable and MUST NOT be parsed cold.
- **Q: Where do copy counts come from when an image is borrowed from another printing?**
  A: From the printing being assembled, never from the printing the image came from.
- **Q: Does the application download card art from MarvelCDB?**
  A: No. MarvelCDB supplies metadata only; every image comes from the user's library.
- **Q: Is a pre-built starter deck always 40 cards?**
  A: Not established. The rules permit 40 to 50. All five official starter decklists on
  MarvelCDB are 40, and all eight hero folders reconstructed to 40, but that is thirteen
  observations against roughly sixty released packs. The spec therefore treats 40 as an
  expectation to report against, never as a gate (FR-017, FR-018).
- **Q: Can Hall of Heroes supply official pre-built contents instead?**
  A: No. It publishes each pack's starter deck as a photograph of the decklist card
  (`capamericadeck-1.jpg`), so using it would require the same optical recognition the
  library's own scanned decklist photos would. Investigated 2026-08-16 and rejected on that
  basis, not on quality.
- **Q: How does the user say which library to read?**
  A: By naming a folder when they ask for a deck. No environment variable, no pre-configured
  root (FR-005).
- **Q: Where does the user do all this, and what happens when they cannot finish in one
  sitting?**
  A: In the wizard. The user opens the local site, picks a hero folder, and the resolver runs.
  If every card resolves they get a PDF. If not, the wizard names each unresolved card and
  offers to choose a file for it, one card at a time, rather than reporting a failed run. A
  user who does not want to finish now saves the run and returns to it on a later visit, so
  the site lists what is finished and what is still waiting (FR-026b, FR-026c). Assembly runs
  are therefore durable, which feature 001's generation registry deliberately was not — and
  the assembly report lives on the run record, so an incomplete deck stays legible as
  incomplete without depending on a browser tab staying open (FR-030b).
- **Q: Does assembling a hero produce anything besides the 40-card deck?**
  A: Yes. A printed player deck alone cannot be played: the hero and alter-ego identity card
  and the hero's nemesis and obligation cards are not part of the 40, and without them the
  output is not a hero you can sit down with. Assembling produces all three — the player deck,
  the identity card, and the nemesis set — resolved by the same rules and held to the same
  completeness check. They remain excluded from the deck total, so the expectation of 40 is
  unaffected (FR-015, FR-015a, FR-015b).
- **Q: How are the eight named heroes verified, given the card art is not in the repository?**
  A: Against the real library, at the mounted Drive path the user will actually point the
  application at — a folder under its `Heros/` directory. Those runs are the acceptance
  evidence for SC-002 and SC-003 and are executed locally, because neither the art nor the
  path exists in CI. The same eight are additionally covered in CI by fixtures derived from
  that library's structure: its filenames and folder layout reproduced over generated
  placeholder images, with no card art and no MarvelCDB card text committed (FR-038a). The
  resolver matches on positions and names and never on pixels, so the derived fixtures
  exercise the real behaviour.
- **Q: Does this feature ship a command-line way to assemble a deck?**
  A: No. The wizard is the interface. FR-036's machine-readable outcome — clean, warnings, or
  refused — is a field on the run in the API rather than a process exit status, and anything
  scripting an assembly drives that API. No constitutional or repository rule required a CLI;
  only FR-036's wording implied one, and it has been corrected.
- **Q: How does the user hand the tool a file for a card it could not resolve?**
  A: Inside an assembly run the application remembers. Starting an assembly creates a run that
  resolves what it can and reports what it could not, producing no PDF; the user then supplies
  a file for a named card, or explicitly asks to print without it, against that same run; the
  PDF is produced only on a final confirmation (FR-026a). A request to print incomplete that
  arrives before the run has reported cannot be honoured, because it would be made before the
  gap it authorises is known (FR-030a).
- **Q: Does the user get one PDF or three?**
  A: One. The player deck, the identity card, and the nemesis set are distinct *sections* of a
  single PDF, each starting on a fresh page, not three separate files. Printing a chosen page
  range is easy enough that splitting the download buys nothing, and one file keeps the
  wizard's final step to a single download (FR-015d, FR-048).
- **Q: By what mechanism does the user supply that file — a path or an upload?**
  A: An upload through the browser, with the run keeping the uploaded bytes. Naming the library
  folder stays a matter of naming a path (FR-005), but an individual replacement card is
  uploaded, because typing a full path per missing card is worse than picking one, and because
  a run that owns its bytes stays resumable when the source file moves and can reproduce its
  PDF without depending on the filesystem being unchanged (FR-026e, FR-045). This also settles
  a contradiction between FR-009 and FR-027: no path from outside the named folder is recorded
  anywhere, only the uploaded file's own name and the fact that the choice was manual.
- **Q: What does the application fetch from MarvelCDB, and when does it refresh it?**
  A: One snapshot per pack, captured the first time a deck from that pack is assembled and
  reused by every run afterwards. It MUST NOT fetch the full card list: only the packs actually
  being assembled are retrieved, which keeps the stored footprint minimal and keeps the
  application clear of anything resembling a mirror (FR-038, FR-040). Refresh is automatic and
  driven by the cache headers MarvelCDB sends (FR-039), with an explicit manual refresh
  available as well — most packs have been out for years and their data does not move, but a
  recently released pack can pick up corrections, and waiting out an expiry is the wrong remedy
  when the user already knows (FR-044a, FR-044b).
- **Q: Does a finished run keep its PDF, or rebuild it on demand?**
  A: It keeps it. Re-downloading is then instant and works even when the library folder has
  since moved or been unmounted, which regeneration could not. The cost is real and accepted:
  feature 001 measured roughly 202 MB per deck, so stored PDFs accumulate. The application
  therefore MUST let the user delete one and reclaim that space (FR-026f, FR-026g).
- **Q: Is a stored PDF private to the run that made it, or reused?**
  A: It depends on whether the user changed anything. A run that resolved every card
  automatically with no user input produces the pack's *standard* PDF, stored under a name
  derived from the pack and served to any later request for that same pack, which gets the
  stored file rather than a ~49-second rebuild. A run the user touched at all — supplying a
  file for a card the tool could not find, printing without one, or any later editing
  capability — is not standard, so the user names its PDF and it is kept in a browsable list of
  saved PDFs instead (FR-026h, FR-026i). Reuse is keyed on the pack's snapshot revision as well
  as the pack, so refreshing card data cannot cause a PDF built from superseded data to be
  served.
- **Q: Does the user confirm the identified pack before assembly proceeds?**
  A: Yes, always. The wizard states the pack and the evidence and waits. FR-011 already refuses
  a match too weak to trust; confirmation covers the case FR-011 structurally cannot — an
  identification the tool is confident about and wrong about, which yields a deck that is
  entirely plausible. One click against forty misprinted cards (FR-012a).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print a hero's starter deck (Priority: P1) 🎯 MVP

Someone points the application at a hero's folder and receives that hero print-ready — the
40-card starter deck, the identity card, and the nemesis set — without writing a catalog,
typing a quantity, or knowing that six of the cards were never scanned.

**Why this priority**: This is the entire barrier. Today the application is unusable by
anyone who has not hand-authored a catalog, which is almost nobody.

**Independent Test**: Point the tool at `Heros/Steve Rogers_Captain America/` with no catalog
present. It succeeds when the deck contains 40 cards, in the right quantities, including the
six sourced from the Core Set, and the identity card and nemesis set are produced alongside it
without being counted in the 40.

**Acceptance Scenarios**:

1. **Given** a hero folder and no catalog, **When** the user assembles, **Then** a deck is
   produced in which every card resolved to an image and each card appears as many times as
   the pack contains it, and the deck's total is reported.
2. **Given** a card the scanner omitted because it is a Core Set reprint, **When** the user
   assembles, **Then** its image is taken from the Core Set and it appears in the deck.
3. **Given** a card whose copies number more than one, **When** the user assembles, **Then**
   the single scanned image appears once per copy the pack contains.
4. **Given** a borrowed image whose own printing ships a different number of copies, **When**
   the user assembles, **Then** the count follows the pack being assembled, not the pack the
   image came from.
5. **Given** a completed assembly, **When** the user opens the report, **Then** every card is
   accounted for and every borrowed image is named alongside the printing it came from.
6. **Given** no library configured anywhere and no environment variable set, **When** the user
   names a folder and asks for a deck, **Then** the deck is assembled from that folder.
7. **Given** a second request naming a different folder, **When** the user assembles, **Then**
   it reads that folder, with no restart and no reconfiguration.
8. **Given** a hero folder, **When** the user assembles, **Then** one PDF is produced carrying
   the player deck, then the identity card, then the nemesis set, each starting on a fresh
   page, and neither the identity card nor the nemesis set is counted in the deck total.
9. **Given** a hero with more than two faces, **When** the user assembles, **Then** every face
   the card data records is produced, rather than the first two.
10. **Given** a nemesis card that resolves to no image, **When** the user assembles, **Then**
    the run stops naming that card, exactly as it would for a missing deck card.
11. **Given** a folder whose pack the tool identifies confidently, **When** the user starts the
    run, **Then** the pack and its evidence are shown and nothing is resolved until the user
    confirms.
12. **Given** a pack whose standard PDF was already produced by an earlier clean run against
    the same snapshot, **When** a user assembles that pack again with no customization,
    **Then** the stored PDF is served rather than regenerated.
13. **Given** that pack's snapshot has since been refreshed, **When** a user assembles it
    again, **Then** the stored PDF is not served and the deck is rebuilt against the new
    revision.

---

### User Story 2 - Be told exactly what could not be resolved (Priority: P1)

An assembly that cannot resolve every card says which are missing and where it looked, rather
than producing a deck that is quietly short.

**Why this priority**: Shares P1 with User Story 1 because it is not a separate feature but
the other half of the same one. A deck that is silently 37 cards is worse than no deck: the
user discovers it at the table, having already paid to print it.

**Independent Test**: Assemble a hero whose folder omits a starter-deck card that exists in
no other printing. It succeeds when the run fails, names that card, and prints nothing.

**Acceptance Scenarios**:

1. **Given** a card with no image anywhere in the library, **When** the user assembles,
   **Then** the run fails naming that card, and no PDF is written.
2. **Given** a reconstruction that does not total 40, **When** the user assembles, **Then**
   the total is reported against that expectation as a warning, and every unplaced card is
   named — but the count alone does not refuse the run.
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

### User Story 4 - Supply the last few cards by hand (Priority: P2)

Where automatic resolution fails, the user picks a file for that specific card themselves,
rather than being told the run failed and left to work out why.

**Why this priority**: Without it, a single card the library genuinely lacks makes a whole
deck unprintable with no recourse. With it, the automatic path can stay strict — it never has
to guess, because there is somewhere for the hard cases to go.

**Independent Test**: Assemble a hero whose library is missing one card. It succeeds when the
tool names that card, accepts a file the user chooses for it, and prints the deck.

**Acceptance Scenarios**:

1. **Given** a card that resolved to nothing, **When** the user is asked, **Then** that card
   is named specifically and the user can choose a file for it.
2. **Given** an uploaded file that is not a decodable image, or is below the required print
   resolution, **When** the user uploads it, **Then** it is rejected on upload with the
   specific reason and the card remains unresolved.
3. **Given** a file the user uploads from outside the folder named for the run, **When** they
   upload it, **Then** it is accepted and recorded as a manual choice by its own filename, and
   no path from outside the named folder appears in the report or the log.
4. **Given** a run resolved with an uploaded file, **When** that file is later moved or deleted
   on disk and the run is reprinted, **Then** the run still prints that card, because the run
   holds the uploaded bytes.
5. **Given** a deck assembled with manual help, **When** the user opens the report, **Then**
   every manually chosen card is distinguishable from every automatically resolved one.
6. **Given** a card the user declines to resolve, **When** they take no further action,
   **Then** the run stops rather than printing a deck with that card missing.
7. **Given** a card the user declines to resolve, **When** they explicitly ask to print
   without it, **Then** the deck prints, and the omitted card is named in the report, counted
   against the expected total, and recorded in the run's log.
8. **Given** a run that reported two unresolved cards, **When** the user supplies a file for
   the first, **Then** the run keeps the folder, the identified pack, and every earlier
   choice, and asks only about the second.
9. **Given** a request to print without unresolved cards made before the run has reported any,
   **When** the user assembles, **Then** the blanket permission is refused and the run still
   stops on the first card it cannot resolve.

---

### User Story 5 - Put a deck down and pick it up later (Priority: P2)

A user who cannot finish resolving a deck now saves it and comes back to it on a later visit,
finding it where they left it rather than starting again.

**Why this priority**: Finding a file for a missing card can mean going and looking for it, and
a wizard that loses the other thirty-nine resolutions while the user does that is one they will
not use twice. It shares P2 with User Story 4 because it is what makes manual resolution
survivable rather than a separate capability.

**Independent Test**: Start an assembly that cannot resolve two cards, save it, restart the
application, and return. It succeeds when the run is listed as unfinished and resumes with the
folder, the pack, and the first card's resolution intact.

**Acceptance Scenarios**:

1. **Given** a run with cards still unresolved, **When** the user saves it and returns on a
   later visit, **Then** the run is listed as unfinished and can be resumed.
2. **Given** a saved run, **When** the application is restarted, **Then** the run, its
   resolutions, and its report survive.
3. **Given** several runs, **When** the user opens the site, **Then** finished and printable
   runs are distinguishable from ones still waiting on a card, without the user having to
   remember an identifier.
4. **Given** a resumed run, **When** the user opens it, **Then** the report shows what was
   already resolved and what remains, so they can tell where they left off.
5. **Given** a finished run whose library folder has since been moved or unmounted, **When**
   the user returns, **Then** its PDF still downloads, because the run retains it.
6. **Given** a run the user no longer wants, **When** they delete it, **Then** its stored PDF
   and uploaded files are reclaimed and the scan library is untouched.
7. **Given** a deck the user completed by supplying a file for one card, **When** they finish
   it, **Then** they are asked to name the PDF and it appears in the saved-PDF list under that
   name, not as the pack's standard PDF.

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
  every other hero has two. Face count is read from the data, never assumed to be two
  (FR-015a).
- **A card name misspelled in the filename.** "Stength in Numbers", "Steve_s Apartament", and
  a type written "Upgarde" all occur. Display names come from MarvelCDB; the filename is
  never the authority on what a card is called.
- **MarvelCDB unreachable.** Assembly cannot proceed on library contents alone, because
  quantities and identities live only upstream. The run fails saying so, or proceeds from a
  previously captured snapshot of that pack if one exists — reporting that it ran against a
  stale revision (FR-044a). It must never guess.
- **A pack assembled for the first time while offline.** No snapshot for it exists yet, so the
  run is refused naming the pack, even though other packs assemble fine from their own stored
  snapshots. Snapshots are per pack, not one global cache (FR-044a, FR-046).
- **A folder that is not a hero pack.** Reported as unidentifiable rather than assembled
  against a wrongly guessed pack.
- **A pack identified with low confidence.** Reported and refused. A wrong pack produces a
  deck that is entirely plausible and entirely wrong.
- **A named folder that does not exist, is a file, or cannot be read.** Refused when named,
  naming the folder and the reason — never surfacing later as a missing card.
- **A named folder containing no card images at all.** Reported as empty rather than
  identified as some pack on no evidence.
- **A deck totalling more than 40.** Permitted by the rules, so reported and printed rather
  than refused. Only a card that resolves to no image stops a run.
- **A saved run whose folder has moved or been deleted by the time it is resumed.** Reported
  against the run when it is reopened, naming the folder — not surfaced as a wave of newly
  missing cards. This affects only a run still resolving cards; a finished run holds its own
  PDF and downloads regardless (FR-026f).
- **A saved run resumed after the upstream snapshot has been refreshed.** The run keeps the
  snapshot revision it started with, so resuming it cannot silently change the deck's
  composition or quantities under the resolutions already made (FR-044, FR-045).

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

### Naming the library

- **FR-005**: The user MUST be able to name any readable folder on their machine when asking
  for a deck. The application MUST NOT require a library location to be configured in advance,
  and MUST NOT refuse to start because one is unset.
- **FR-006**: The named folder MUST be validated when it is named — that it exists, is a
  directory, and is readable — and MUST fail immediately and specifically when it is not,
  rather than surfacing as a missing card later.
- **FR-007**: For the duration of a run, the named folder MUST be the containment boundary:
  every asset reference MUST resolve inside it, and a reference that escapes it MUST be
  refused. Feature 001's containment guarantee is preserved; what changes is that the boundary
  is chosen per run rather than fixed at startup.
- **FR-008**: The named folder MUST NOT be written to, moved, renamed, or deleted from, which
  is FR-001 restated for a boundary the user picks each time.
- **FR-009**: Diagnostic and log records MUST NOT carry absolute filesystem paths from outside
  the named folder, preserving feature 001's FR-022b under per-run boundaries.

### Identifying the pack

- **FR-010**: The tool MUST determine which pack a hero folder represents, from the folder's
  contents and MarvelCDB's card data, without a hand-maintained folder-to-pack table.
- **FR-011**: Pack identification MUST be verified rather than assumed. The tool MUST check
  the folder's positions against the identified pack and MUST refuse to proceed when
  agreement is too weak to be confident.
- **FR-012**: The tool MUST state which pack it identified and on what evidence, so a wrong
  identification is visible before a PDF is printed rather than after.
- **FR-012a**: The user MUST explicitly confirm the identified pack before the run resolves any
  card. A run MUST hold in an awaiting-confirmation state until they do, and MUST NOT resolve
  images or produce a PDF from an unconfirmed identification. FR-011 refuses a match too weak
  to trust; FR-012a covers the case FR-011 cannot — an identification the tool is confident
  about and wrong about, which yields a deck that is entirely plausible and entirely wrong. The
  cost is one confirmation per run against forty misprinted cards.

### Composing the deck

- **FR-013**: Deck composition MUST be derived from the hero folder's contents together with
  MarvelCDB's pack listing. The tool MUST NOT attempt to compute composition from pack
  contents alone, which is not possible.
- **FR-014**: A pack card absent from the hero folder that carries a reprint link MUST be
  treated as part of the deck and sourced from the printing it duplicates.
- **FR-015**: Encounter cards, obligation cards, nemesis cards, and the hero's identity card
  MUST be excluded from the player deck and from the deck total FR-018 reports. They MUST be
  produced alongside it (FR-015a, FR-015b), because a player deck on its own is not a hero
  anyone can play.
- **FR-015a**: Assembling a hero MUST produce the hero's identity card. Its faces MUST be read
  from the card data and MUST NOT be assumed to number two, since a hero may have more.
- **FR-015b**: Assembling a hero MUST produce that hero's nemesis and obligation cards as a
  section distinct from the player deck, so the two are printed and cut as the separate decks
  they are.
- **FR-015d**: The player deck, the identity card, and the nemesis set MUST be delivered as one
  PDF, in that order, each beginning on a fresh page so no page carries cards from two of them.
  They MUST NOT be split across separate files: printing a chosen page range is easy enough
  that separate downloads buy nothing, and one file keeps the wizard's final step to a single
  download. "Distinct outputs" throughout this spec means distinct sections of that PDF, never
  distinct files.
- **FR-015c**: The identity card and the nemesis set MUST be resolved by the same rules as the
  deck — the same matching, the same reporting of substitutions, and the same completeness
  check (FR-017). A card missing from either MUST stop the run by name exactly as a missing
  deck card does, subject to the same explicit override (FR-030).
- **FR-016**: The number of copies of a card MUST come from the printing being assembled,
  never from the printing an image was borrowed from.
- **FR-017**: Every card the tool places in the deck MUST resolve to an image. A card that
  does not MUST stop the run by name, subject to the user's explicit override (FR-030).
  Completeness of resolution, not the card total, is what the tool verifies.
- **FR-018**: The tool MUST report the assembled deck's total, counting the player deck alone —
  the identity card and the nemesis set are separate outputs and MUST NOT be added to it
  (FR-015). A total other than 40 MUST be
  reported as a warning, because a pre-built deck is expected to be 40 and every shortfall
  measured so far was an unresolved card. A total outside the legal 40-to-50 range MUST be
  reported more strongly still. Neither MUST refuse the run on the count alone — the rules
  permit up to 50, and no exhaustive check of released packs has been made.
- **FR-019**: The tool MUST NOT invent a card, a quantity, or a substitution to reach any
  particular total.

### Resolving images

- **FR-020**: A card MUST be matched to a file by `(pack_code, position)` wherever the
  filename carries a position and the folder's pack is known.
- **FR-021**: When that fails, the tool MUST search the whole library, because the library
  does not reliably file a hero's cards under that hero.
- **FR-022**: When that fails, the tool MUST follow reprint links in both directions and
  accept an image of any other printing of the same card.
- **FR-023**: A name match MUST only ever be made against a specific card the tool is already
  looking for, with its canonical name known from MarvelCDB. Parsing a card's identity out of
  a filename is prohibited.
- **FR-024**: Every image resolved by anything other than an exact positional match in the
  identified folder MUST be reported, naming the card, the file chosen, and why.
- **FR-025**: A card with no image anywhere in the library MUST NOT be silently omitted or
  replaced by a placeholder. It MUST be reported by name, and the run MUST stop unless the
  user supplies a file for it (FR-026) or explicitly chooses to print without it (FR-030).
  What is prohibited is the omission passing unnoticed, not the omission itself.

### Resolving the rest by hand

- **FR-026**: When a card cannot be resolved automatically, the user MUST be able to choose a
  file for it themselves, naming that card specifically rather than being told the run failed.
- **FR-026a**: An assembly MUST be an addressable run that outlives a single request. Starting
  one MUST identify the pack and wait for the user's confirmation (FR-012a); once confirmed it
  MUST resolve what it can and report what it could not without producing a PDF; the user
  MUST be able to supply a file for a named card, or make the FR-030 decision to print without
  it, against that same run; and the PDF MUST be produced only on an explicit final
  confirmation. The user MUST NOT have to restate the folder, the pack, or their earlier
  choices to answer a second unresolved card.
- **FR-026b**: An assembly run MUST survive the user leaving. A run with cards still
  unresolved MUST be resumable on a later visit, with the folder, the identified pack, the
  resolutions already made, and the report intact. Restarting the application MUST NOT
  discard it.
- **FR-026c**: The user MUST be able to see their runs without remembering an identifier —
  which are finished and printable, which are waiting on a card, and which are waiting for the
  pack to be confirmed — and MUST be able to resume any unfinished one from that list.
- **FR-026d**: The wizard MUST present each unresolved card individually, naming it and
  offering the user a way to supply a file for that specific card. It MUST NOT present a
  failed run and leave the user to work out which cards were at fault.
- **FR-026e**: A manually supplied file MUST be uploaded to the run through the browser, and
  the run MUST retain the uploaded bytes. The user MUST NOT have to type a filesystem path for
  an individual card. Retaining the bytes is what lets a resumed run keep a manual resolution
  when the source file has since moved (FR-026b) and lets that run reprint identically
  (FR-045).
- **FR-026f**: A run that has produced a PDF MUST retain it. The user MUST be able to download
  it again on a later visit without regenerating it, and that MUST hold when the library folder
  has since moved, been renamed, or been unmounted — a finished run depends on nothing outside
  itself.
- **FR-026g**: The user MUST be able to delete a stored PDF, whether standard (FR-026h) or
  saved by name (FR-026i), and deleting it MUST reclaim the space it held. Retention under
  FR-026f is otherwise unbounded, and feature 001 measured roughly 202 MB for a single deck's
  PDF. Deleting MUST NOT touch the scan library (FR-001).
- **FR-026h**: A run that resolved every card automatically, with no user customization of any
  kind, MUST store its PDF under a standard name derived from the pack. A later assembly of the
  same pack that likewise needs no customization MUST be served that stored PDF rather than
  regenerating it. Reuse MUST be keyed on the pack's snapshot revision (FR-044a) as well as the
  pack, so a refreshed snapshot (FR-044b) invalidates the stored PDF rather than serving one
  built from superseded card data.
- **FR-026i**: A run the user customized MUST NOT be stored as the pack's standard PDF. The
  user MUST be able to give it a name, and it MUST be kept under that name in a list of saved
  PDFs they can browse and retrieve on a later visit, separate from the standard per-pack PDFs.
  Customization means any user input that changes what is printed — supplying a file for an
  unresolved card (FR-026), choosing to print without one (FR-030), or any later capability
  that alters the deck's contents.
- **FR-027**: A manually supplied file MAY originate anywhere on the user's machine, including
  outside the folder named for the run. Supplying it is an explicit act by the person running
  the process, and MUST be recorded as a manual choice in the report and the log — the
  containment boundary of FR-007 governs what the tool resolves on its own, not what the user
  hands it. What is recorded MUST be the uploaded file's own name and the fact that the choice
  was manual, never a filesystem path from outside the named folder, so FR-009 holds without
  exception.
- **FR-028**: A manually supplied file MUST be validated on upload as an image the application
  can decode at the required print resolution, and MUST be rejected with a specific reason when
  it is not, leaving the card unresolved. Manual choice bypasses discovery, never validation.
- **FR-029**: Every manual choice MUST be reported and MUST be distinguishable from an
  automatic resolution, so a deck assembled with human help is auditable as such.
- **FR-030**: The user MUST be able to leave a card unresolved and still print, by saying so
  explicitly. The default when a card cannot be resolved is to stop; proceeding anyway is the
  user's decision to make, and the tool MUST NOT overrule it.
- **FR-030a**: Proceeding with an incomplete deck MUST require an explicit act. It MUST NOT be
  the default, MUST NOT be reachable by dismissing a prompt or ignoring a warning, and MUST
  NOT be inferred from silence. It MUST NOT be granted in advance of the run reporting which
  cards are unresolved: a decision taken before the gap is known is not an informed one, and
  the tool MUST refuse a blanket permission offered up front rather than honouring it.
- **FR-030b**: An incomplete deck MUST be legible as incomplete after the fact. The report
  MUST name every omitted card, the deck total MUST be stated against what was expected, and
  the omission MUST appear in the log record for the run. The report MUST be retrievable from
  the run record itself on a later visit (FR-026b), not only from the response that produced
  it. A user who prints one and returns to it a week later MUST NOT have to rediscover what is
  missing.

### Reporting

- **FR-031**: Every file in the folders consulted MUST be either used, or named in the report
  as unused and why. Silent omission is prohibited.
- **FR-032**: The tool MUST report every file whose name it could not interpret, naming each.
- **FR-033**: The tool MUST report position conflicts, naming both sides, and MUST NOT resolve
  them by arbitrary choice.
- **FR-034**: The tool MUST report duplicate renditions of one card, naming which was chosen.
- **FR-035**: The tool MUST report scans below the resolution the application requires at
  print size, as a warning rather than a refusal.
- **FR-036**: A run's outcome MUST be machine-readable, distinguishing "assembled cleanly" from
  "assembled with warnings" from "refused", so a consumer can act on it without parsing prose.
  A run that has not yet reached an outcome MUST be distinguishable as such — awaiting
  confirmation of the pack (FR-012a) or waiting on a card (FR-026b) is not a failure.
  This feature adds no command-line interface: starting the server remains the only command,
  and anything driving an assembly without a browser uses the HTTP API, which constitution
  principle II already requires be sufficient on its own.
- **FR-037**: Failures MUST name the specific card or file at fault, never a generic error
  (constitution principle V).

### Conduct toward MarvelCDB

- **FR-038**: The application MUST stay within the use MarvelCDB states its API is provided
  for — tools that complement playing Marvel Champions. It MUST NOT be used to mirror,
  republish, or redistribute their data, whose text is copyrighted by Fantasy Flight Games.
- **FR-038a**: This repository is public, so FR-038 governs its test fixtures as well as its
  runtime behaviour. Committed fixtures MUST NOT carry card artwork, and MUST NOT carry
  MarvelCDB card text. A fixture snapshot MUST be reduced to the fields this feature actually
  resolves against — pack, position, quantity, name, type, and reprint links — for the packs
  under test, never a full mirror of the upstream response.
- **FR-039**: The application MUST honour the HTTP caching MarvelCDB explicitly asks for. Its
  public responses carry `max-age` and `last-modified`; the application MUST respect both and
  MUST NOT re-request data it has been told is still fresh.
- **FR-040**: The application MUST minimise requests by design, fetching a pack's card list in
  one request rather than a request per card. Assembling a deck MUST NOT issue one request per
  card in it. It MUST NOT fetch the full card list: only packs it is actually assembling from
  are retrieved, so the stored footprint stays proportional to what the user has used and the
  application stays clear of anything resembling a mirror (FR-038).
- **FR-041**: Requests MUST identify the application in a descriptive `User-Agent`, so the
  operator can attribute and contact rather than only block.
- **FR-042**: The application MUST back off when the service signals overload or throttling,
  and MUST NOT retry in a way that increases load on a service already failing.
- **FR-043**: MarvelCDB publishes no rate limit. Its absence MUST NOT be treated as
  permission for unlimited requests; the application MUST behave conservatively regardless.
  No specific numeric limit is specified here because none is published and inventing one
  would misrepresent the operator's terms.

### Upstream data

- **FR-044**: MarvelCDB responses MUST be captured as a snapshot with a recorded revision, so
  a generated PDF can be traced to the card data that produced it.
- **FR-044a**: A snapshot MUST be scoped to one pack. It MUST be captured the first time a deck
  from that pack is assembled, stored, and reused by every later run of that pack rather than
  refetched per run. Refresh MUST be automatic and governed by the cache headers MarvelCDB
  sends (FR-039): a stored snapshot still fresh MUST be reused without a request, and one that
  is not MUST be refetched. When a refetch fails, the stored snapshot MUST be used and the run
  MUST report that it ran against a stale revision.
- **FR-044b**: The user MUST be able to refresh a pack's snapshot explicitly, without waiting
  for its cached copy to expire. Most packs are years old and their data does not change, but a
  recently released pack can pick up corrections upstream, and a user who already knows that
  MUST NOT have to wait out an expiry to act on it. An explicit refresh MUST NOT alter any
  existing run, which keeps the revision it started with (FR-045).
- **FR-045**: Assembling twice from the same library and the same snapshot MUST produce a
  byte-identical PDF (constitution principle V). This MUST hold of regeneration itself and MUST
  be verifiable independently of FR-026h's reuse — serving a stored PDF MUST NOT be the reason
  two runs agree.
- **FR-046**: The tool MUST NOT proceed when MarvelCDB is unreachable and no snapshot exists.
  It MUST say which is missing.
- **FR-047**: Upstream data MUST be validated on capture, and a response that does not carry
  the fields this feature depends on MUST fail loudly at that point rather than at print time.

### Output

- **FR-048**: The resolved deck MUST be expressed in the catalog structures feature 001
  already defines, so page layout, resolution enforcement, and PDF generation are reused
  rather than reimplemented. This feature adds no new output format.
- **FR-049**: The capability MUST be exposed through the HTTP API before any UI consumes it
  (constitution principle II).

## Key Entities

- **Scan library**: The user's directory of card images, organised by someone else and not
  rearranged. Its folder structure is the only record of which cards form a starter deck.
- **Hero folder**: One folder under `Heros/`, holding that hero pack's starter-deck cards,
  deduplicated, with the Core Set reprints absent and nemesis cards in a subfolder.
- **Pack listing**: MarvelCDB's record of a pack — every card, its position, its type, and how
  many copies the pack contains. The authority on identity and quantity.
- **Pack snapshot**: One pack's listing as captured at a point in time, with a revision. The
  unit of upstream storage and refresh: fetched on first use of that pack, reused afterwards,
  and pinned by every run that starts against it (FR-044a).
- **Reprint link**: MarvelCDB's statement that two printings are the same card. The mechanism
  by which an unscanned card is sourced from elsewhere.
- **Resolution**: The pairing of one card with one file, carrying how it was found, so a
  substitution is auditable.
- **Assembly run**: One attempt to assemble one deck from one named folder. Durable across
  visits and application restarts, carrying the identified pack, every resolution made
  automatically or by hand, the bytes of every file uploaded to it (FR-026e), the PDF once it
  has produced one (FR-026f), the report, and its state — awaiting confirmation of the pack,
  waiting on a card, or finished. The thing the user resumes and the thing the report hangs
  off.
- **Stored PDF**: A generated PDF kept for reuse. Either *standard* — produced by a run that
  needed no user input, named from the pack, and served to later requests for that pack against
  the same snapshot (FR-026h) — or *saved*, produced by a run the user customized, named by
  them, and listed separately (FR-026i). Both are deletable to reclaim space (FR-026g).
- **Assembly report**: What a run produced — the pack identified, cards placed, images
  borrowed, files unused or uninterpretable, conflicts, low-resolution warnings, and the
  card total with a warning when it is not the expected 40.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a scan library and no catalog can produce a printable starter deck
  in under five minutes, against the half-day it takes to author a catalog by hand.
- **SC-002**: Captain America, Star-Lord, Wasp, and Hulk each assemble with every card
  resolved and no manual intervention, and each totals 40. These four were measured to
  reconstruct cleanly and are the acceptance set.
- **SC-003**: Thor, Black Widow, Ant-Man, and Ms. Marvel each assemble with every card
  resolved, and each totals 40. These four require whole-library search and name fallback, and
  are the harder acceptance set. Their totals were 37, 39, 36, and 37 with a resolver confined
  to the hero folder.
- **SC-003a**: The user MUST be able to assemble a deck by naming a folder, with no
  environment variable set and no library configured in advance.
- **SC-003b**: SC-002 and SC-003 are verified against the real library — the mounted Drive
  folder, one directory per hero under `Heros/` — on the user's own machine, since neither the
  card art nor that folder is available to automated verification elsewhere. The same eight
  heroes MUST also assemble against fixtures derived from that library's filenames and folder
  layout, so a resolver regression is caught without the real scans present.
- **SC-002a**: Each of the eight acceptance heroes produces one PDF carrying its deck, an
  identity card with every face its card data records, and a nemesis set, in that order and on
  page boundaries — and neither the identity card nor the nemesis set appears in the deck
  total. A user can print one hero and play it without owning the pack.
- **SC-004**: 100% of files in the folders consulted are either used or named in the report.
  Zero are silently ignored.
- **SC-005**: 100% of images resolved by anything other than an exact positional match are
  reported as such. No substitution is silent.
- **SC-006**: A deck containing a card that resolves to no image stops 100% of the time unless
  the user explicitly asks to print without it. No combination of inputs yields a deck that
  prints with a card missing and no one having said so.
- **SC-006e**: 100% of decks printed with a card omitted name that card in the report and in
  the run's log. An incomplete deck is never indistinguishable from a complete one.
- **SC-006a**: A deck whose total is not 40 is reported as such 100% of the time, whether or
  not the run succeeds.
- **SC-006b**: A deck missing exactly one card from the library can be completed by the user
  uploading one file, and prints. No card the user can point at is unprintable, and the deck
  still reprints identically after that file is moved or deleted on disk.
- **SC-006c**: 100% of manually chosen cards are distinguishable from automatically resolved
  ones in the report.
- **SC-006f**: A run saved with cards unresolved survives an application restart and resumes
  with its folder, its pack, its resolutions, and its report intact, 100% of the time. No user
  who leaves the wizard loses work they have already done.
- **SC-006g**: A returning user can tell which of their decks are printable and which are
  still waiting on a card, from the site alone, without recording an identifier anywhere.
- **SC-006h**: A finished run's PDF downloads again on a later visit with the library folder
  unmounted, and deleting it reclaims the space it held. Storage grows only with PDFs the user
  has chosen to keep.
- **SC-006i**: Assembling a pack whose standard PDF already exists against the current snapshot
  returns that PDF without regenerating it, so the second and later requests for a pack avoid
  the ~49 s build entirely. A customized deck never overwrites a pack's standard PDF.
- **SC-009**: No deck is resolved against a pack the user has not confirmed, 100% of the time.
- **SC-006d**: Assembling a full deck issues a number of upstream requests that does not grow
  with the number of cards in the deck, and a second deck from a pack whose snapshot is still
  fresh issues none at all.
- **SC-007**: Assembling twice from the same library and snapshot produces a byte-identical
  PDF.
- **SC-008**: A user whose library is missing a card can tell which card, and where the tool
  looked, from the report alone — without reading source code.

## Assumptions

- **The library is not rearranged.** Its structure is what it is, including the
  inconsistencies. The tool adapts to the library; the user does not adapt the library to the
  tool.
- **A hero folder holds that hero's starter-deck cards.** Verified across eight heroes. Where
  a card is filed elsewhere, whole-library search recovers it (FR-021) rather than the
  assumption being abandoned.
- **The trailing number in a filename is MarvelCDB's `position`.** Verified 18/18 for the
  Captain America pack and across eight hero folders. Files not matching are reported, not
  guessed at (FR-032).
- **A pre-built starter deck is expected to be 40 cards, but this is not assumed.** The
  deckbuilding rules permit 40 to 50. Thirteen observations support 40 — the five official
  starter decklists published on MarvelCDB, and eight hero folders that each reconstruct to
  40 — against roughly sixty released packs, so it is an expectation the tool reports against
  (FR-018) rather than a rule it enforces. If a pack ships a larger pre-built deck, the tool
  warns and proceeds; it does not refuse.
- **MarvelCDB's public card endpoints are available and stable.** This feature uses only the
  documented card and pack endpoints; it does not depend on the undocumented decklist
  endpoints, and does not require an account.
- **The scope is personal use, and the requirements exist to keep it there.** The application
  runs locally, prints from the user's own scans of cards they own, and publishes nothing.
  It does not redistribute card artwork, does not mirror or republish MarvelCDB's data, and
  has no sharing, hosting, or export-to-others path — matching the constitution's Distribution
  scope clause. FR-038 to FR-043 are written to keep the application a well-behaved client of
  a volunteer-run service, not because anything here is in tension with that scope.
- **The acceptance library is the user's mounted Drive folder**, whose `Heros/` directory holds
  one folder per hero named `<Alter ego>_<Hero>`. That is the exact structure the application
  will be pointed at in use — a folder under `Heros/` — and it is the source both for the
  acceptance runs and for the filenames the CI fixtures reproduce. Its absolute path is not
  recorded here: this repository is public, and the folder is named per run (FR-005) rather
  than configured.
- **The library is a local directory the user names at the time they ask.** Their Google Drive
  folder is mounted locally, so no Drive-specific client is needed. A remote backend remains
  out of scope here, as it is in feature 001, and would arrive through the existing adapter.
- **Naming a folder per run widens what the application will read, deliberately.** It will
  open any directory the user names, where before it read one directory fixed at startup.
  This is judged acceptable because the service is loopback-only by design (feature 001's
  FR-0A2) and the person naming the folder is the person running the process, so it grants
  them nothing they did not already have. The containment guarantee is preserved in kind
  rather than dropped: it now binds to the folder named for that run (FR-007).
- **Depends on feature 001** for the catalog structures, the validation rules, the resolution
  floor, and PDF generation. This feature introduces no new output format and relaxes none of
  those rules.
- **Assembly runs and their PDFs are durable, where feature 001's generations were not.**
  Feature 001 keeps generations in memory on the stated grounds that nothing there required
  durable output and a user who wants a PDF has already downloaded it. Both halves of that
  premise are retired here: an unfinished deck must be resumable on a later visit, and a
  finished PDF is kept and reused rather than rebuilt (FR-026f, FR-026h). Run state and
  generated PDFs must therefore outlive the process. Where they live is a plan decision; that
  they survive a restart is not. The storage cost is known and accepted — roughly 202 MB per
  deck, bounded by the user deleting what they no longer want (FR-026g).
- **Aspect cards and modular sets are out of scope.** The library files them separately and
  the user can print them as a later feature. This feature assembles starter decks.
- **Editing an assembled deck is out of scope and belongs in its own feature.** Deleting a
  card, swapping one for another, and adding cards that were never in the pack are all
  wanted, but they are a different capability: this feature answers "what did this pack
  contain and where are its images", while an editor answers "what do I want on the page".
  An editor needs a mutable deck that outlives one run, an interface for browsing the whole
  card pool, and rules for what a deck may contain — none of which this feature needs and all
  of which would make it undeliverable. Manual resolution (User Story 4) is deliberately *not*
  that: it is bounded to cards the tool already decided belong in the deck and could not find,
  and it changes no membership decision.
- **Reading the pack's physical decklist card was considered and excluded.** The scanned
  decklist photos are the only printed record of deck composition, but the folder structure
  already carries the same information without optical recognition.
