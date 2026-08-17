# Feature Specification: Hero Pack Printing from a Scan Library

**Feature Branch**: `002-starter-deck-assembly`

**Created**: 2026-08-01

**Last revised**: 2026-08-16

**Status**: Draft

**Input**: User description: "Point it at a hero folder in the scan library and get that
hero's whole pack as a print-ready PDF — every card, plus the decklist card — so the starter
deck can be built by hand from what comes off the printer. Card identity and quantities come
from marvelcdb.com; images come from the library, including the ones the scanner skipped
because they were already in the Core Set."

> **Note on the directory name.** This feature is still filed under
> `002-starter-deck-assembly` because renaming it would break the branch-to-spec correspondence
> the constitution requires. The name is now historical: the feature prints a pack, and the
> user assembles the starter deck from it.

## Why this exists

Feature 001 turns a catalog into a printable sheet and leaves the catalog as an exercise for
the user. Authoring one by hand for a single hero means writing roughly two hundred lines of
JSON, and the earlier draft of this feature proposed generating that JSON from filenames and
then asking the user to type in every quantity by hand, because quantities were believed to
be unrecoverable.

They are not. MarvelCDB publishes the complete card list for every pack, with the number of
copies of each card the pack contains, under a public JSON API that needs no credentials.
That is enough to print a pack, and printing the pack is what this feature does.

Earlier drafts tried to do something harder: work out which of a pack's cards form the
pre-built starter deck, and print only those. MarvelCDB does not record deck membership, so
the folder structure of the scan library was pressed into service as a proxy for it. That
approach was abandoned on 2026-08-16 after two measurements disproved its foundations
(see Clarifications). The decisive one: **MarvelCDB's `quantity` is the number of copies in
the *pack*, not the number in the *deck***, and the two genuinely differ — War Machine's pack
holds two copies of Two Against the World and its starter deck uses one. A tool that derived
the deck and took counts from MarvelCDB would have printed a deck with one card too many and
had no way to notice.

Printing the whole pack dissolves the problem rather than solving it. Every quantity question
has a correct answer, because the pack listing is exactly a description of a pack. Nothing has
to be inferred from folder structure. And the pack's own decklist card — the printed card that
says which of those cards form the starter deck — is itself just a card, so the tool prints it
alongside the rest and the user reads it off paper.

What the tool still owes the user is completeness. Every card in the pack must resolve to an
image, and one that does not stops the run by name. Stopping is the default, not the last
word: a user who knows a card is missing and wants the rest on paper anyway can say so and
print. What the tool owes them is that the gap is never invisible — named when it happens, and
still named in the report and the log afterwards. The failure this feature exists to prevent
is a pack that is quietly incomplete, not one the user knowingly chose to print short.

## Clarifications

### Session 2026-08-16

- **Q: Which cards does the tool print?**
  A: **Every card in the pack** (FR-013). Deck membership is not derived at all. Two earlier
  answers here — that the hero folder's contents define membership, and that MarvelCDB's
  `quantity` gives the number of copies to print — were both superseded on 2026-08-16 by the
  measurements recorded in the next two bullets. Printing the pack makes every quantity
  question answerable from the pack listing alone.
- **Q: Is a pre-built starter deck always 40 cards?**
  A: **No — measured, not assumed.** Read directly off the physical decklist cards in the scan
  library: Vision's starter deck is **41** cards and Psylocke's is **42**. Both are legal; the
  deckbuilding rules permit 40 to 50. The earlier claim that all evidence pointed at 40 rested
  on eight hero folders that happen to be early packs. No 40-card expectation survives anywhere
  in this spec, and nothing warns against one.
- **Q: Does MarvelCDB's `quantity` give the number of copies in the starter deck?**
  A: **No. It is the number of copies in the pack**, and the two differ. War Machine's decklist
  card lists `24 Two Against the World` once, while MarvelCDB reports `quantity: 2` for that
  position; Valkyrie's lists `23 The Power of Aggression` once against a reported `quantity: 2`.
  A tool that derived the starter deck and took its counts from MarvelCDB would have printed
  41 cards for War Machine and had no way to detect it, because 41 is a legal deck size. This
  single finding is why the feature prints packs rather than decks. For printing a *pack*,
  `quantity` is exactly the right number and needs no correction (FR-016).
- **Q: Where does the decklist card come from?**
  A: From the user's own library when it holds a scan of one — 35 of the 60 hero folders do —
  and it is printed as a card alongside the rest (FR-013b). When the folder has none, the run
  names the gap and offers the Hall of Heroes URL; the user downloads the image and supplies it
  through the same upload path an unresolved card uses (FR-013c, FR-026e). The application
  never fetches it. This keeps FR-002's prohibition on downloading images intact and keeps the
  egress allowlist at a single host.
- **Q: Does a pack card that resolves to no image still stop the run?**
  A: Yes, and every pack card is held to the same bar (FR-017). With membership derivation gone
  the tool has no basis for calling one pack card more important than another, so a two-tier
  rule would be arbitrary. The consequence is accepted: runs will stop more often than a
  deck-only tool would, because the pack's extra aspect cards are scattered across `Aspects/`
  and may not all be scanned. The explicit override (FR-030) is unchanged.
- **Q: What about cards the scanner skipped because they were already in the Core Set?**
  A: MarvelCDB records that two printings are the same card, so a pack card absent from the
  hero folder still gets printed and its image is taken from the printing it duplicates
  (FR-014, FR-022). For Captain America that recovers Make the Call, The Power of Leadership,
  Mockingbird, Energy, Genius, and Strength — eight physical cards. Reprint links are not
  confined to the Core Set: Wasp's `13020` duplicates a card in Ant-Man's pack and its `13025`
  one in Black Widow's, so the link is followed wherever it points.
- **Q: How are a file and a MarvelCDB card matched?**
  A: On `(pack_code, position)`. The trailing number in the filename is exactly MarvelCDB's
  `position`. Card *names* in filenames are unreliable and MUST NOT be parsed cold.
- **Q: Where do copy counts come from when an image is borrowed from another printing?**
  A: From the printing being assembled, never from the printing the image came from.
- **Q: Does the application download card art from MarvelCDB?**
  A: No. MarvelCDB supplies metadata only; every image comes from the user's library.
- **Q: Can Hall of Heroes supply official pre-built contents?**
  A: It publishes each pack's starter deck as a photograph of the decklist card
  (`capamericadeck-1.jpg`). An earlier answer rejected this because *reading* the photograph
  would require optical recognition. That objection no longer applies, because nothing reads
  it: the photograph is printed as a card and the user reads it off paper. Hall of Heroes is
  therefore the fallback *source of the image* when the library has no decklist scan — fetched
  by the user, not by the application (FR-013c).
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
- **Q: What does the printed output contain?**
  A: Everything the pack contains, in four groups the report names: the pack's player cards
  (every copy, ~52 for a typical hero pack), the identity card with every face its data
  records, the nemesis and obligation set, and the decklist card. All four are resolved by the
  same rules and held to the same completeness check (FR-015, FR-015a, FR-015b, FR-013b).
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
- **Q: Does the user get one PDF or several?**
  A: One, packed into as few pages as it will go. The player cards, the identity card, the
  nemesis set, and the decklist card follow one another with no page break between them: a page
  carrying the last player cards and the first nemesis cards is the intended result. Paper is
  the cost being minimised, and separate files or padded page boundaries both spend it for
  nothing. What keeps the groups distinguishable is the report, not the layout (FR-015d,
  FR-015e, FR-048).
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
- **Q: What happens when the user rejects the identified pack, or when identification is
  refused as too weak?**
  A: The user names the pack themselves. Declining the confirmation opens pack selection — the
  tool's ranked candidates, or a search across all packs by name — and the run proceeds against
  the chosen pack, recorded as user-selected (FR-012b). The same path is the remedy for an
  FR-011 refusal, so a weak or absent match is a prompt rather than a dead end. Without this,
  the two failure modes the spec is most careful about both terminate with the user holding a
  perfectly good folder and no way to print it. Selecting a pack is not customization under
  FR-026i: what gets printed follows from the pack and its snapshot, so a run that selected its
  pack and then resolved every card automatically still produces that pack's standard PDF.
- **Q: What must match before a stored standard PDF is served instead of being rebuilt?**
  A: The pack, its snapshot revision, **and the identity of the images actually resolved**
  (FR-026h). Keying on the pack and snapshot alone was wrong: FR-005 lets each run name a
  different folder, so a second scan library would have been served the first library's PDF,
  built from images the user never chose and with nothing in the report able to reveal it.
  Keying on the resolved images rather than on the folder's path is deliberate — a path-based
  key would break reuse every time the Drive mount moves, which SC-006h already treats as
  routine, and would put a user's filesystem path into stored state against FR-009. The
  consequence is that a run must resolve before it can decide to reuse, so reuse skips the
  ~49 s render but not the resolve; SC-006i is worded accordingly.
- **Q: Does deleting a run delete the standard PDF it produced, when other runs were served
  that same PDF?**
  A: No. A standard PDF belongs to the **pack**, not to the run that happened to build it
  (FR-026g1). Deleting a run reclaims only what is private to that run — its uploaded files and
  a *saved* PDF it named — and standard PDFs are deleted from the stored-PDF list instead. The
  alternative readings both fail: making deletion reference-counted means the user cannot
  predict whether discarding a run frees 202 MB, and deleting the producing run's PDF outright
  breaks FR-026f for every other run that was served it. Deleting a deck attempt and reclaiming
  disk space are different acts and the spec now keeps them apart.
- **Q: How far does the report's file accountability extend once the tool searches the whole
  library?**
  A: To the **named folder**, in full, and no further (FR-031). Outside it, only files actually
  used or in conflict with one are named. FR-031 was written when the tool looked in one hero
  folder, and read literally against FR-021's whole-library search it would require a report for
  one hero to account individually for 4,447 files that were never candidates for it —
  unreadable for the user and untestable as SC-004. The harm FR-031 exists to prevent is bounded
  to the folder the user pointed at: a scan sitting there, ignored, with no explanation. Files
  under other heroes are index entries, not candidates. FR-032 narrows to match; outside the
  named folder an unparseable filename reaches the user through the card that failed to resolve,
  which is the thing they can act on.
- **Q: Are both faces of a genuinely double-sided *player* card printed, and does a missing back
  stop the run?**
  A: Yes to both (FR-015f). FR-015a settled face count for the identity card and said nothing
  about the rest, which left room to build a double-sided player card front-only — a proxy blank
  where the real card carries game text, with FR-017 reporting the run clean. Feature 001
  already rules that a double-sided card missing its second face cannot be printed usefully, and
  FR-048 adopts 001's structures, so treating a missing back as a warning would contradict an
  inherited rule rather than extend it. Counting stays in cards: the pack listing counts cards,
  so FR-018 must, or the user's comparison against it breaks. The report states the face count
  as well, which is what SC-002b's page-count claim needs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print a hero's whole pack (Priority: P1) 🎯 MVP

Someone points the application at a hero's folder and receives that entire pack print-ready —
every player card in the quantities the pack ships, the identity card, the nemesis set, and the
decklist card — without writing a catalog, typing a quantity, or knowing that several of the
cards were never scanned. They cut the sheets and build the starter deck by reading the printed
decklist.

**Why this priority**: This is the entire barrier. Today the application is unusable by
anyone who has not hand-authored a catalog, which is almost nobody.

**Independent Test**: Point the tool at `Heros/Steve Rogers_Captain America/` with no catalog
present. It succeeds when every card the `cap` pack contains is printed in the pack's
quantities — including the eight physical cards sourced from the Core Set — together with the
identity card, the nemesis set, and the decklist card.

**Acceptance Scenarios**:

1. **Given** a hero folder and no catalog, **When** the user prints the pack, **Then** every
   card the pack listing records is produced, each appearing as many times as the pack contains
   it, and every card resolved to an image.
2. **Given** a card the scanner omitted because it is a Core Set reprint, **When** the user
   prints, **Then** its image is taken from the Core Set and it appears in the output.
3. **Given** a card whose copies number more than one, **When** the user prints, **Then**
   the single scanned image appears once per copy the pack contains.
4. **Given** a borrowed image whose own printing ships a different number of copies, **When**
   the user prints, **Then** the count follows the pack being printed, not the pack the
   image came from.
5. **Given** a completed run, **When** the user opens the report, **Then** every card is
   accounted for and every borrowed image is named alongside the printing it came from.
6. **Given** no library configured anywhere and no environment variable set, **When** the user
   names a folder and asks for a pack, **Then** it is printed from that folder.
7. **Given** a second request naming a different folder, **When** the user prints, **Then**
   it reads that folder, with no restart and no reconfiguration.
8. **Given** a hero folder, **When** the user prints, **Then** one PDF is produced carrying
   the player cards, then the identity card, then the nemesis set, then the decklist card,
   packed into the fewest pages that hold them.
9. **Given** that PDF, **When** the user inspects it, **Then** no page is left part-empty to
   start one of the groups on a fresh page, and the report says which cards belong to which
   group.
10. **Given** a hero with more than two faces, **When** the user prints, **Then** every face
    the card data records is produced, rather than the first two.
10a. **Given** a double-sided player card, **When** the user prints, **Then** both its faces are
    produced, and the report counts it as one card and two faces.
10b. **Given** a double-sided player card whose back resolves to no image, **When** the user
    prints, **Then** the run stops naming that card, exactly as it would for a missing front.
11. **Given** a nemesis card that resolves to no image, **When** the user prints, **Then**
    the run stops naming that card, exactly as it would for a missing player card.
12. **Given** a folder whose pack the tool identifies confidently, **When** the user starts the
    run, **Then** the pack and its evidence are shown and nothing is resolved until the user
    confirms.
13. **Given** a hero folder holding a decklist scan, **When** the user prints, **Then** the
    decklist card is printed with the rest, so the starter deck can be built from paper alone.
14. **Given** a hero folder holding no decklist scan, **When** the user prints, **Then** the
    run names that gap and offers the Hall of Heroes address, and the user can supply the image
    by upload — the application never fetches it.
15. **Given** a pack whose standard PDF was already produced by an earlier clean run against
    the same snapshot and the same images, **When** a user prints that pack again with no
    customization, **Then** the stored PDF is served rather than rendered again.
15a. **Given** a second scan library whose folder resolves one card to a different image,
    **When** the user prints that same pack from it, **Then** the stored PDF is not served and
    the pack is rebuilt from the images this run resolved.
15b. **Given** a library folder that has been moved or renamed since the standard PDF was
    stored, **When** the user prints that pack from its new location and every image resolves
    identically, **Then** the stored PDF is still served.
16. **Given** that pack's snapshot has since been refreshed, **When** a user prints it
    again, **Then** the stored PDF is not served and the pack is rebuilt against the new
    revision.
17. **Given** a folder whose pack the tool identifies wrongly, **When** the user declines the
    confirmation, **Then** they can name the correct pack themselves and the run proceeds
    against it, reported as a user-selected pack.
18. **Given** a folder whose pack cannot be identified, or is identified too weakly to be
    trusted, **When** the user is told so, **Then** they are offered the same pack selection
    rather than a run that has ended.

---

### User Story 2 - Be told exactly what could not be resolved (Priority: P1)

A run that cannot resolve every card says which are missing and where it looked, rather
than producing a pack that is quietly short.

**Why this priority**: Shares P1 with User Story 1 because it is not a separate feature but
the other half of the same one. A pack that is silently missing three cards is worse than no
pack: the user discovers it at the table, having already paid to print it — and with no deck
total to check against, the report is the *only* thing that can tell them.

**Independent Test**: Print a hero whose folder omits a pack card that exists in
no other printing. It succeeds when the run stops, names that card, and prints nothing.

**Acceptance Scenarios**:

1. **Given** a card with no image anywhere in the library, **When** the user prints,
   **Then** the run stops naming that card, and no PDF is written.
2. **Given** a run that could not place every pack card, **When** the user prints, **Then**
   every unplaced card is named individually, and the count of cards printed is reported
   against the count the pack listing records.
3. **Given** a file in the named folder that the naming convention cannot parse, **When** the
   user prints, **Then** that file is named in the report rather than silently ignored.
3a. **Given** a library of several thousand images searched to resolve one pack, **When** the
   user opens the report, **Then** it accounts for every file in the named folder and lists
   files from elsewhere only where they were used or conflicted.
4. **Given** two files in one folder claiming the same position, **When** the user prints,
   **Then** both are named as a conflict and neither is chosen arbitrarily.

---

### User Story 3 - Find a card that is not where it should be (Priority: P2)

A pack card that lives in another hero's folder, or under `Aspects/`, is found anyway.

**Why this priority**: Without it almost no pack can be printed complete, because the library
does not consistently place a hero's cards in that hero's folder — and printing the whole pack
makes this *more* load-bearing than it was, since the pack's extra aspect cards live under
`Aspects/` by design rather than by accident. It is second only because User Story 1 is
demonstrable without it.

**Independent Test**: Print Black Widow, whose `Quincarrier` is filed under Wasp. It
succeeds when the card is found and every pack card resolves.

**Acceptance Scenarios**:

1. **Given** a pack card filed under another hero's folder, **When** the user
   prints, **Then** it is found and its origin is named in the report.
2. **Given** a pack card filed under `Aspects/`, **When** the user prints, **Then**
   it is found and its origin is named in the report.
3. **Given** a card found by a name match rather than by position, **When** the user
   prints, **Then** the match is reported as such, so a wrong match is visible rather than
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
   without it, **Then** the pack prints, and the omitted card is named in the report, counted
   against the pack listing's card count, and recorded in the run's log.
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
6. **Given** a run the user no longer wants, **When** they delete it, **Then** its uploaded
   files and any PDF it saved under its own name are reclaimed, and the scan library is
   untouched.
6a. **Given** a run that produced a pack's standard PDF and other runs that were served it,
   **When** the user deletes that run, **Then** the standard PDF survives and the other runs
   still download it.
6b. **Given** a standard PDF the user wants the space back from, **When** they delete it from
   the stored-PDF list, **Then** the space is reclaimed and the next assembly of that pack
   rebuilds it.
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
- **A third convention, where the number counts physical copies rather than positions.**
  Observed in the Phoenix and Wonder Man folders on 2026-08-16:
  `2_Active Altruism_Event.tif`, `3_Active Altruism_Event.tif`, and
  `4_Active Altruism_Event.tif` are three files for one card, numbered by copy. This disproves
  the earlier assumption that the scanner made one scan per distinct card; for these folders,
  the leading number is not a MarvelCDB `position` and must not be read as one. Both folders
  resolve to almost nothing under position matching alone and depend entirely on the name
  fallback (FR-023).
- **A filename carrying the wrong position.** Observed: Vision's `Vision_Vivian_Ally_2.tiff` —
  Vivian is position 3 — which additionally collides with the double-sided `Intangible` filed
  as `_2a` and `_2b`. A position conflict in real data, not a hypothetical one (FR-033).
- **A hero folder with no decklist scan.** 25 of 60 folders have none. Reported as a named gap
  with the Hall of Heroes address offered, never fetched by the application, and never a reason
  to refuse the run — the rest of the pack still prints (FR-013c).
- **The same card present as both `.tif` and `.tiff`.** One is chosen deterministically and
  the duplication is reported; the card is not printed twice.
- **Two files in one folder claiming the same position.** Reported as a conflict, not
  resolved by arbitrary choice.
- **A hero with three faces.** Ant-Man has a tiny form, a giant form, and an alter-ego where
  every other hero has two. Face count is read from the data, never assumed to be two
  (FR-015a).
- **A double-sided player card whose back was never scanned.** Vision's `Intangible` is filed as
  `_2a` and `_2b`; a folder holding only the `a` face leaves a card that cannot be printed
  usefully. The run stops naming it, like any other unresolved card (FR-015f, FR-017).
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
  against a wrongly guessed pack, and the user is offered pack selection rather than an ended
  run (FR-012b).
- **A pack identified with low confidence.** Reported and refused, then offered for selection
  (FR-011, FR-012b). A wrong pack produces a deck that is entirely plausible and entirely
  wrong, so the tool never resolves the weak match itself — but the user, who knows which pack
  they are holding, can say so.
- **A pack identified confidently and wrongly.** Caught only by the user declining the
  confirmation (FR-012a), which is what FR-012b's selection path exists to serve. The tool has
  no way to detect this case on its own; that is why confirmation is unconditional.
- **A named folder that does not exist, is a file, or cannot be read.** Refused when named,
  naming the folder and the reason — never surfacing later as a missing card.
- **A named folder containing no card images at all.** Reported as empty rather than
  identified as some pack on no evidence.
- **A pack whose card count differs from its neighbours.** Pack sizes vary and no total is
  expected, so the count is reported and printed rather than checked. Only a card that resolves
  to no image stops a run.
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
  agreement is too weak to be confident. A refusal MUST NOT end the run: it MUST offer pack
  selection (FR-012b), so the threshold can stay strict without leaving the user stranded.
- **FR-012**: The tool MUST state which pack it identified and on what evidence, so a wrong
  identification is visible before a PDF is printed rather than after.
- **FR-012a**: The user MUST explicitly confirm the identified pack before the run resolves any
  card. A run MUST hold in an awaiting-confirmation state until they do, and MUST NOT resolve
  images or produce a PDF from an unconfirmed identification. FR-011 refuses a match too weak
  to trust; FR-012a covers the case FR-011 cannot — an identification the tool is confident
  about and wrong about, which yields a deck that is entirely plausible and entirely wrong. The
  cost is one confirmation per run against forty misprinted cards.
- **FR-012b**: Rejecting the identified pack MUST NOT end the run. The user MUST be able to name
  the pack themselves — choosing among the candidates the tool ranked, or searching all packs by
  name — and the run MUST proceed against the pack they choose. This same path MUST be offered
  when FR-011 refuses a match as too weak and when no pack can be identified at all, so neither
  a confidently wrong identification nor an unidentifiable folder leaves the user with no way to
  print. A user-selected pack MUST be recorded as such in the report and MUST be distinguishable
  from one the tool identified, exactly as a manual card resolution is (FR-029). Selecting the
  pack MUST NOT count as customization under FR-026i: what is printed follows from the pack
  listing and its snapshot, so a run that selected its pack and then resolved every card
  automatically still produces that pack's standard PDF (FR-026h).

### Composing the output

- **FR-013**: The tool MUST print **every card the pack listing records**, in the quantities it
  records. Composition MUST NOT be derived from the hero folder's contents, from card
  positions, or from any other inference about which cards form the pre-built starter deck. The
  folder determines *where images are found* (FR-020, FR-021), never *what is printed*.
- **FR-013a**: The tool MUST NOT attempt to identify the pre-built starter deck. Selecting the
  starter deck from the printed cards is the user's task, performed against the printed decklist
  card. This is a deliberate reversal: deriving membership was attempted, measured, and found to
  produce a silently wrong deck (see Clarifications).
- **FR-013b**: The pack's decklist card MUST be printed alongside the pack's cards when the
  named folder holds a scan of it, because it is what makes the printed pack usable — without
  it the user has the cards but not the instructions for building the deck. It MUST be reported
  as its own group (FR-015e) and MUST NOT be counted among the pack's cards.
- **FR-013c**: When the named folder holds no decklist scan, the run MUST name that gap
  specifically and MUST offer the address at which Hall of Heroes publishes that pack's
  decklist photograph. The application MUST NOT fetch it: the user downloads the image and
  supplies it through the same upload path an unresolved card uses (FR-026e). A missing
  decklist MUST NOT refuse the run — the rest of the pack still prints, reported as printed
  without one. This preserves FR-002 and keeps the egress allowlist at a single host.
- **FR-014**: A pack card absent from the hero folder that carries a reprint link MUST still be
  printed, with its image sourced from the printing it duplicates. Reprint links MUST be
  followed wherever they point, not only to the Core Set.
- **FR-015**: The output MUST be organised into four reported groups: the pack's player cards,
  the identity card (FR-015a), the nemesis and obligation set (FR-015b), and the decklist card
  (FR-013b). Every group MUST be produced; none is optional, and a player card on its own is not
  a hero anyone can play.
- **FR-015a**: Assembling a hero MUST produce the hero's identity card. Its faces MUST be read
  from the card data and MUST NOT be assumed to number two, since a hero may have more.
- **FR-015f**: A pack card the card data marks as double-sided MUST be printed with both faces,
  whichever group it belongs to. This is not confined to the identity card: the library holds
  genuinely double-sided player cards, filed as `_2a` and `_2b`. A back face that resolves to no
  image MUST stop the run by name exactly as a missing front does (FR-017), subject to the same
  explicit override (FR-030) — feature 001 already holds that a double-sided card missing its
  second face cannot be printed usefully, and FR-048 adopts that rule rather than relaxing it.
- **FR-015b**: Printing a pack MUST produce that hero's nemesis and obligation cards, kept
  distinct from the player cards in the report so the user can separate them after cutting.
  They are not separated on the page — FR-015d packs everything as tightly as it will go.
- **FR-015d**: All four groups MUST be delivered as one PDF, in the order player cards,
  identity card, nemesis set, decklist card, packed into as few pages as possible. Every page
  MUST be filled to its card capacity before the next is started, and the groups MUST NOT be
  padded apart onto separate pages — a page carrying the last player cards and the first nemesis
  cards together is the intended result, not a defect. Paper is the cost being minimised. They
  MUST NOT be split across separate files either: one file keeps the wizard's final step to a
  single download. "Distinct outputs" throughout this spec means distinct in the report, never
  distinct files and never distinct pages.
- **FR-015e**: Because FR-015d lets one page carry cards from more than one group, the
  report MUST be what tells them apart. It MUST state which cards are player cards, which is
  the identity card, which form the nemesis set, and which is the decklist card, so the user can
  sort the cut cards without recognising them by sight.
- **FR-015c**: Every group MUST be resolved by the same rules — the same matching, the same
  reporting of substitutions, and the same completeness check (FR-017). A card missing from any
  group MUST stop the run by name, subject to the same explicit override (FR-030). The decklist
  card is the single exception: its absence is reported and the run proceeds (FR-013c).
- **FR-016**: The number of copies of a card MUST come from the pack being printed, never from
  the printing an image was borrowed from. MarvelCDB's `quantity` is the number of copies **in
  the pack**, which is exactly what printing a pack requires. It is *not* the number of copies
  in the pre-built starter deck, and MUST NOT be used as though it were — that mistake is what
  this feature's earlier design made (see Clarifications).
- **FR-017**: Every card the tool prints MUST resolve to an image. A card that does not MUST
  stop the run by name, subject to the user's explicit override (FR-030). Completeness of
  resolution is the whole of what the tool verifies; there is no card total to check against.
  Every pack card is held to this bar equally — with membership derivation gone, the tool has no
  basis for treating one pack card as more important than another.
- **FR-018**: The tool MUST report how many cards it printed against how many the pack listing
  records, so an incomplete run is visible as a number as well as a list. The unit MUST be
  cards, not faces, because that is the unit the pack listing counts in — a double-sided card
  (FR-015f) is one card and two faces. The report MUST state the face count as well, since that
  is what the page count follows from (SC-002b). The tool MUST NOT
  expect any particular total and MUST NOT warn on one. Pre-built deck sizes were measured to
  vary — Vision's is 41 cards and Psylocke's is 42 — and pack sizes vary independently of that,
  so any expected total would produce false alarms.
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
- **FR-026g1**: A standard PDF belongs to the pack, not to the run that produced it. Deleting a
  run MUST reclaim only what is private to that run — the files uploaded to it (FR-026e) and a
  *saved* PDF it named (FR-026i) — and MUST NOT delete a standard PDF, which is removed only
  through the stored-PDF list (FR-026g). Otherwise deleting one run would revoke FR-026f's
  guarantee for every other run that was served the same file, and the user could not tell
  whether discarding a run reclaims 202 MB or nothing. Deleting a deck attempt and reclaiming
  disk space are separate acts and MUST stay separate.
- **FR-026h**: A run that resolved every card automatically, with no user customization of any
  kind, MUST store its PDF under a standard name derived from the pack. A later assembly of the
  same pack that likewise needs no customization MUST be served that stored PDF rather than
  regenerating it. Reuse MUST be keyed on three things together: the pack, the pack's snapshot
  revision (FR-044a), and the identity of the images the run resolved. A refreshed snapshot
  (FR-044b) therefore invalidates the stored PDF rather than serving one built from superseded
  card data, and a run whose named folder (FR-005) yields even one different image MUST rebuild
  rather than be served a PDF assembled from scans it did not resolve. The key MUST NOT include
  the named folder's path: reuse MUST survive that folder being moved or renamed (SC-006h), and
  FR-009 forbids retaining such a path. It follows that a run MUST resolve its cards before it
  can establish whether reuse applies; what reuse avoids is the render, not the resolve.
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
- **FR-030b**: An incomplete pack MUST be legible as incomplete after the fact. The report
  MUST name every omitted card, the number of cards printed MUST be stated against the number
  the pack listing records (FR-018), and the omission MUST appear in the log record for the run. The report MUST be retrievable from
  the run record itself on a later visit (FR-026b), not only from the response that produced
  it. A user who prints one and returns to it a week later MUST NOT have to rediscover what is
  missing.

### Reporting

- **FR-031**: Every file in the folder named for the run MUST be either used, or named in the
  report as unused and why. Silent omission is prohibited within that folder. Beyond it, the
  whole-library search (FR-021) reaches files that were never candidates for this pack, and the
  report MUST name only those it actually used or that conflicted with one it used (FR-033,
  FR-034). Accounting individually for every file in a 4,447-image library would produce a
  report no user can read and a criterion no test can assert; the harm this requirement exists
  to prevent — a scan sitting in the folder the user pointed at, ignored and unexplained — is
  bounded to that folder.
- **FR-032**: The tool MUST report every file **within the named folder** whose name it could
  not interpret, naming each. Outside that folder an uninterpretable filename MUST NOT be
  listed on its own; it surfaces through the card that failed to resolve (FR-025), which is
  what the user can act on.
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
  rearranged. It is a place to find images and nothing more: its folder structure carries no
  record of which cards form a starter deck, which is what the decklist card is for (FR-013a).
- **Hero folder**: One folder under `Heros/`, holding most of that hero pack's cards, usually
  deduplicated, with the Core Set reprints absent, nemesis cards in a subfolder, and the pack's
  extra aspect cards filed under `Aspects/` instead. It is a place to look for images, not a
  statement about what belongs in a deck.
- **Decklist card**: The card printed in the pack listing which cards form the pre-built starter
  deck and in what numbers. The only authoritative record of that, and the reason the tool can
  stop trying to derive it. Present as a scan in 35 of 60 hero folders; otherwise supplied by
  the user from Hall of Heroes (FR-013b, FR-013c).
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
  the same snapshot revision and the same resolved images (FR-026h) — or *saved*, produced by a
  run the user customized, named by them, and listed separately (FR-026i). Both are deletable to
  reclaim space (FR-026g).
- **Assembly report**: What a run produced — the pack, and whether the tool identified it or the
  user selected it (FR-012b), cards placed by group, images
  borrowed, files unused or uninterpretable within the named folder, conflicts, low-resolution
  warnings, whether a decklist card was printed, and the number of cards printed against the
  number the pack listing records, with the face count alongside it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a scan library and no catalog can produce a printable pack
  in under five minutes, against the half-day it takes to author a catalog by hand.
- **SC-002**: Captain America, Star-Lord, Wasp, and Hulk each print with every card in the pack
  listing resolved and no manual intervention. These four were measured to resolve cleanly from
  their own folders plus reprint links, and are the acceptance set.
- **SC-003**: Thor, Black Widow, Ant-Man, and Ms. Marvel each print with every card in the pack
  listing resolved. These four require whole-library search and name fallback, and are the
  harder acceptance set.
- **SC-003c**: Phoenix and Wonder Man each print with every card resolved. These two use the
  copy-counting filename convention and carry no usable positions at all, so they are the
  acceptance case for the name-match path (FR-023) and for the third convention recorded in Edge
  Cases. Under position matching alone they resolve almost nothing.
- **SC-003a**: The user MUST be able to assemble a deck by naming a folder, with no
  environment variable set and no library configured in advance.
- **SC-003b**: SC-002 and SC-003 are verified against the real library — the mounted Drive
  folder, one directory per hero under `Heros/` — on the user's own machine, since neither the
  card art nor that folder is available to automated verification elsewhere. The same heroes,
  plus Phoenix and Wonder Man (SC-003c), MUST also print against fixtures derived from that
  library's filenames and folder layout, so a resolver regression is caught without the real
  scans present.
- **SC-002a**: Each acceptance hero produces one PDF carrying its player cards, an identity card
  with every face its card data records, its nemesis set, and its decklist card, in that order.
  A user can print one hero, build the starter deck from the printed decklist, and play it
  without owning the pack.
- **SC-002b**: That PDF occupies the fewest pages its card count allows: no page before the
  last is partly empty, and adding the identity card, nemesis set, and decklist card costs no
  more pages than their card count requires.
- **SC-004**: 100% of files in the folder named for the run are either used or named in the
  report. Zero are silently ignored. Files elsewhere in the library appear in the report when
  they were used or conflicted, and are otherwise not listed (FR-031).
- **SC-005**: 100% of images resolved by anything other than an exact positional match are
  reported as such. No substitution is silent.
- **SC-006**: A deck containing a card that resolves to no image stops 100% of the time unless
  the user explicitly asks to print without it. No combination of inputs yields a deck that
  prints with a card missing and no one having said so.
- **SC-006e**: 100% of decks printed with a card omitted name that card in the report and in
  the run's log. An incomplete deck is never indistinguishable from a complete one.
- **SC-006a**: Every run reports the number of cards printed against the number the pack listing
  records, 100% of the time, whether or not the run succeeds, counting a double-sided card as
  one card and reporting the face count alongside it. No run reports an expected total of 40 or
  warns against one.
- **SC-006j**: Every run states whether a decklist card was printed. A pack printed without one
  is never indistinguishable from a pack printed with one.
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
  has chosen to keep. Deleting a run never removes a pack's standard PDF from under another run.
- **SC-006i**: Assembling a pack whose standard PDF already exists against the current snapshot
  and the same resolved images returns that PDF without rendering it again, so the second and
  later requests for a pack avoid the ~49 s render — they still resolve, which is what
  establishes that the images match. A customized deck never overwrites a pack's standard PDF.
- **SC-006k**: A run naming a library folder that resolves any card to a different image than
  the stored standard PDF was built from rebuilds rather than being served that PDF, 100% of the
  time. No user is handed a PDF assembled from scans their run did not resolve.
- **SC-009**: No deck is resolved against a pack the user has not confirmed, 100% of the time.
- **SC-009a**: A user whose folder is identified as the wrong pack, identified too weakly to
  proceed, or not identified at all can still print it by naming the pack themselves. No folder
  the user can correctly name a pack for is unprintable, and every user-selected pack is
  reported as user-selected.
- **SC-006d**: Printing a full pack issues a number of upstream requests that does not grow
  with the number of cards in it, and a second run against a pack whose snapshot is still
  fresh issues none at all.
- **SC-007**: Assembling twice from the same library and snapshot produces a byte-identical
  PDF.
- **SC-008**: A user whose library is missing a card can tell which card, and where the tool
  looked, from the report alone — without reading source code.

## Assumptions

- **The library is not rearranged.** Its structure is what it is, including the
  inconsistencies. The tool adapts to the library; the user does not adapt the library to the
  tool.
- **A hero folder holds many of that hero pack's cards, but not all of them and not only
  them.** The pack's extra aspect cards are filed under `Aspects/` by design, and individual
  cards are misfiled under other heroes. Whole-library search (FR-021) is what makes the pack
  resolvable; the folder is a starting point, not a boundary.
- **The trailing number in a filename is usually MarvelCDB's `position`.** Verified 18/18 for
  the Captain America pack and across eight hero folders — but *not* universal: the Phoenix and
  Wonder Man folders number by physical copy instead, and Vision carries at least one number
  that is simply wrong. Files not matching are reported, not guessed at (FR-032), and the name
  fallback (FR-023) carries the folders where positions are unusable.
- **No deck size is expected, because deck sizes vary.** The deckbuilding rules permit 40 to 50,
  and pre-built decks measured from their own printed decklist cards include 40 (Captain
  America, War Machine, Valkyrie), 41 (Vision), and 42 (Psylocke). The tool prints packs and
  never asserts a deck size, so no total needs defending (FR-018).
- **MarvelCDB's `quantity` is pack copies, not deck copies.** Measured 2026-08-16 against the
  physical decklist cards. This is safe for this feature precisely because the feature prints
  packs; it would be unsafe for any later feature that tries to produce a starter deck directly,
  and such a feature MUST take its counts from the decklist card rather than from MarvelCDB.
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
- **Printing aspect card pools and modular sets in their own right is out of scope.** The
  library files them separately and the user can print them as a later feature. A hero pack's
  own aspect cards are *not* excluded by this — they are pack cards and FR-013 prints them,
  wherever in the library they are filed. What is out of scope is printing an aspect or a
  modular set as the thing the user asked for.
- **Editing an assembled deck is out of scope and belongs in its own feature.** Deleting a
  card, swapping one for another, and adding cards that were never in the pack are all
  wanted, but they are a different capability: this feature answers "what did this pack
  contain and where are its images", while an editor answers "what do I want on the page".
  An editor needs a mutable deck that outlives one run, an interface for browsing the whole
  card pool, and rules for what a deck may contain — none of which this feature needs and all
  of which would make it undeliverable. Manual resolution (User Story 4) is deliberately *not*
  that: it is bounded to pack cards the tool could not find an image for, and it changes nothing
  about what is printed. **The pivot to printing packs raises the value of that editor**: a user
  who wants only the starter deck on paper, rather than the whole pack, needs one — and any such
  feature MUST take its card counts from the decklist card, never from MarvelCDB's `quantity`.
- **The pack's physical decklist card is the only authoritative record of deck composition, and
  the tool prints it rather than reading it.** An earlier draft excluded it on the grounds that
  reading it would require optical recognition, and asserted the folder structure carried the
  same information. The second half of that was disproved on 2026-08-16. The resolution is not
  to read the card but to put it in the user's hands: nothing parses it, so no recognition is
  needed, and the one source that is actually authoritative ends up where it is useful.
