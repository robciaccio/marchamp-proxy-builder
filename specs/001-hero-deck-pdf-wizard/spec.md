# Feature Specification: Hero Deck PDF Wizard

**Feature Branch**: `001-hero-deck-pdf-wizard`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "Let's develop our webpage that has a wizard that allows you to select a marvel champions hero pack deck that you can easily download as pdf with high enough res to print and play with. the cards should be slightly smaller than standard cards when printed so that they can easily be pushed into standard penny sleeves in front of a dummy marvel champions card (which will be used as the cards back). the site should show you a preview of the pages that will be in your pdf and in a later feature we will likely allow you to select or deselect or even move around cards or replace them with others from the library. the underlying storage mechanism is currently a google drive with high res tiff files."

## Clarifications

### Session 2026-07-31

- Q: Once this site is live, who will be able to reach it and generate PDFs? → A: Local only — runs on the operator's own machine, never hosted. No authentication needed, because there is no remote access to authenticate.
- Q: How should the application get at the card images — read from a folder on disk, or call Google Drive directly? → A: A local folder on disk. The user syncs or downloads the Drive folder themselves; the application holds no credentials and makes no outbound calls for assets.
- Q: How should the application work out which image file belongs to which card? → A: A metadata catalog names each card's image file explicitly. Card identity is independent of filename, so the image folder can be renamed or reorganised without breaking decks.
- Q: Source scans are 2.7% taller in proportion than a standard card. How should the image fill the card? → A: Offer all three fit modes (crop / fit / stretch) as a user-selectable option, so the choice can be made from real printed evidence rather than on screen. Default is crop.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download a printable hero deck (Priority: P1)

A player wants to try a hero they do not own. They start the application on their machine,
pick that hero from a list, and download a PDF. They print it on their home printer, cut the cards out, and slide
each one into a penny sleeve in front of a spare Marvel Champions card. The spare card
supplies the back and the rigidity; the printed sheet supplies the face. They sit down and
play that evening.

**Why this priority**: This is the entire product. Every other story is an improvement on a
journey that must already work end to end. If only this ships, the site is useful.

**Independent Test**: Select any hero, download the PDF, print it, cut one card, and insert
it into a sleeved standard card. Value delivered when the card fits without forcing and the
face is legible at arm's length.

**Acceptance Scenarios**:

1. **Given** the hero list is displayed, **When** the user selects a hero and confirms,
   **Then** a PDF containing every card in that hero's deck is produced for download.
2. **Given** a generated PDF, **When** it is printed at 100% scale on Letter or A4,
   **Then** every card measures the target print size within ±0.5 mm on both axes.
3. **Given** a generated PDF, **When** any card face is examined at final print size,
   **Then** its effective resolution is at least 300 DPI and no image has been upscaled
   beyond its source resolution.
4. **Given** a deck whose card count is not a multiple of the cards-per-page count,
   **When** the PDF is generated, **Then** the final page is partially filled and contains
   no blank placeholder card outlines.
5. **Given** a card image that cannot be retrieved or decoded, **When** generation runs,
   **Then** generation fails with a message naming the specific card, and no partial PDF is
   offered for download.

---

### User Story 2 - Preview the pages before printing (Priority: P2)

Before committing paper and ink, the user sees exactly what they are about to print: each
page of the PDF rendered as a thumbnail they can enlarge, in order, with a page count.

**Why this priority**: Printing is the expensive, irreversible step. Preview converts a
wasted print run into a corrected click, and it is the surface every later editing feature
will attach to.

**Independent Test**: Select a hero, view the preview, then download and compare. Value
delivered when the preview and the PDF agree page for page and card for card.

**Acceptance Scenarios**:

1. **Given** a hero has been selected, **When** the preview loads, **Then** it shows one
   image per PDF page, in the same order as the PDF, with a visible page count.
2. **Given** a preview is displayed, **When** the user downloads the PDF, **Then** the
   number of pages, the order of cards, and the position of every card match the preview
   exactly.
3. **Given** a preview page, **When** the user enlarges it, **Then** each card is legible
   enough to identify by name and art.

---

### User Story 3 - Verify print scale before printing a whole deck (Priority: P3)

The user prints a single calibration page first. It contains a printed ruler and one card
outline at the exact target size. If the ruler measures true, their printer settings are
correct and the deck will fit the sleeves.

**Why this priority**: Consumer printers silently apply "fit to page" scaling, which
produces cards a few millimetres off — enough to not fit a sleeve, and not obvious until a
full deck has been printed. One page of paper protects against wasting forty. Lowest
priority because the deck PDF is still correct without it.

**Independent Test**: Print the calibration page, measure the ruler with a physical ruler.
Value delivered when a mis-scaled printer is detected before the real print run.

**Acceptance Scenarios**:

1. **Given** the calibration page is printed at 100% scale, **When** its ruler is measured,
   **Then** the printed length matches the stated length within ±0.5 mm.
2. **Given** the calibration page, **When** a real Marvel Champions card is laid over the
   printed outline, **Then** the outline matches the card's edges within ±0.5 mm on all
   four sides.
3. **Given** a card cut from the calibration page, **When** it is inserted into a penny
   sleeve in front of a standard card, **Then** the fit is recorded as the evidence for
   whether the target size in FR-009 needs adjusting.

---

### Edge Cases

- A card image is missing, unreadable, or not a valid image → generation fails naming the
  card; no partial or placeholder-filled PDF is delivered.
- An image file exists but cannot be opened — permissions, a lock held by another program,
  or a partially written file → the user sees an error distinguishing "cannot read this
  file right now" from "this card does not exist".
- A deck lists the same card multiple times → each copy is printed, in the listed quantity.
- A source image has a different aspect ratio than a standard card → it is handled by the
  selected fit mode (FR-009b). This is the normal case for the current scans, not an
  exception, so it is not reported per-card; the mode is stated once for the generation.
- A source image is below the resolution needed for 300 DPI at final size → generation
  fails or warns explicitly; it is never silently upscaled.
- A deck is large enough to span many pages → pagination continues correctly with no
  duplicated or dropped cards.
- The catalog is edited while the application is running → a generation uses one consistent
  catalog revision throughout, never a mixture of old and new.
- A user's browser cancels a slow download → no partially written PDF is presented as
  complete.
- The application is started while another program already holds its port → it reports the
  conflict clearly instead of failing silently or falling back to a public interface.
- The configured image directory is missing, unreadable, empty, or points at the wrong
  place → the user gets an actionable message naming the problem, not a generic failure.
- The catalog names an image file that is not present in the directory → validation fails
  naming the card and the expected filename, before any generation is attempted.
- Two different cards map to the same image file → this is reported, since it is far more
  often a copy-paste mistake than a deliberate choice.
- The directory contains image files no catalog entry references → these are ignored
  without error; an unreferenced file is not a fault.
- The catalog is malformed or unparseable → the application reports where, and refuses to
  operate on a partially understood catalog.
- The image directory is a cloud-sync folder whose files are placeholders not yet
  downloaded to disk → this is reported as an unreadable asset naming the card, not treated
  as a missing card.
- A single source image is pathologically large or malformed → the bounded-cost limits in
  FR-0A4 stop it rather than letting it consume the machine.

## Requirements *(mandatory)*

### Functional Requirements

**Deployment and access**

- **FR-0A1**: System MUST run entirely on the operator's own machine, with no hosted or
  publicly reachable deployment.
- **FR-0A2**: System MUST bind only to a loopback interface. It MUST NOT listen on an
  externally reachable address, and MUST NOT require a firewall rule or reverse proxy to
  stay private.
- **FR-0A3**: System MUST NOT include authentication, accounts, or sessions. The sole user
  is the person running it, and the trust boundary is the machine itself.
- **FR-0A4**: System MUST bound the cost of a single generation with explicit limits on
  decode time, memory, and total work, so that a malformed or oversized source image cannot
  exhaust the machine. This protects against bad data, not against a hostile user.

**Selection**

- **FR-001**: System MUST present the list of available hero decks with a recognizable
  name for each, sourced from the content catalog rather than hard-coded.
- **FR-002**: Users MUST be able to select exactly one hero deck per generation request.
- **FR-003**: System MUST guide the user through selection, preview, and download as an
  ordered sequence in which the user can return to a prior step without losing selection.
- **FR-004**: System MUST reflect newly added hero decks without requiring a software
  release.

**Deck composition**

- **FR-005**: System MUST resolve a selected hero deck into an ordered list of card
  identifiers with quantities, defined by the content catalog.
- **FR-005a**: System MUST determine a card's image file from an explicit mapping in the
  content catalog. It MUST NOT infer the file from the card's name, its position, or the
  folder layout.
- **FR-005b**: Card identity MUST be stable and independent of filename, so that renaming a
  file or substituting a better scan of the same card does not change the card's identity
  or invalidate any deck referencing it.
- **FR-005c**: System MUST validate the catalog before use, checking that it parses, that
  every card a deck references exists, that every card maps to an image file, and that
  every mapped file is present in the configured directory.
- **FR-005d**: System MUST report all catalog validation failures together, naming each
  offending card or deck, rather than stopping at the first error.
- **FR-006**: System MUST include, for a selected hero, the full published pre-built player
  deck: the hero card, the hero-specific signature cards, and the aspect cards the pack
  ships with. The result MUST be playable without the user supplying additional cards. The
  hero's obligation card and nemesis encounter set are out of scope for this feature.
- **FR-007**: System MUST print one card face per listed copy, so that a deck listing three
  copies of a card yields three printed cards.

**Print output**

- **FR-008**: System MUST produce a single PDF containing every card in the resolved deck.
- **FR-009**: System MUST lay out every card in a slot of **63.5 × 88.9 mm** (2.5 × 3.5 in)
  — full standard Marvel Champions card size, 100% scale — measured on the printed page,
  within ±0.5 mm on both axes. A printed card face MUST NOT exceed the slot; it may be
  smaller only in the `fit` mode described in FR-009b.
- **FR-009a**: The target card size MUST be expressed as a single configurable value rather
  than distributed through the layout logic, so that changing it is a one-place change when
  beta printing shows an adjustment is needed.
- **FR-009b**: Because source scans do not share the standard card's proportions, the user
  MUST be able to choose how a card image fills its slot, per generation:
  - **`crop`** (default) — fill the slot completely, trimming the overflowing edges
    symmetrically. Prints at exactly 63.5 × 88.9 mm with no backing card visible.
  - **`fit`** — scale to fit entirely inside the slot, preserving proportions. Nothing is
    cropped; the printed face may be narrower or shorter than the slot.
  - **`stretch`** — scale each axis independently to fill the slot exactly. Nothing is
    cropped, but the image is distorted.
- **FR-009c**: The interface MUST state, at the point of choice, what each mode costs —
  that `crop` discards edges, and that `stretch` distorts the image. A user MUST NOT be able
  to select distortion without being told it is distortion.
- **FR-009d**: The chosen mode MUST be recorded with the generation and MUST be reflected in
  the preview, so that comparing printed results to settings is unambiguous.
- **FR-010**: System MUST render card faces at an effective resolution of at least 300 DPI
  at final print size, and MUST NOT upscale a source image to reach it.
- **FR-011**: System MUST lay out cards in a fixed grid that fits both US Letter and A4
  without scaling, and MUST NOT depend on printer "fit to page" behavior.
- **FR-012**: System MUST produce card faces only, with no card backs and no duplex
  pairing, because the physical card behind the proxy supplies the back.
- **FR-013**: System MUST include cut guides that allow accurate trimming and that do not
  overlap any card face.
- **FR-014**: System MUST preserve card aspect ratio in the `crop` and `fit` modes. The
  `stretch` mode of FR-009b is the sole exception: it MUST be explicitly selected by the
  user, MUST NOT be the default, and MUST be labelled as distorting wherever it is offered.
  Distortion MUST NOT occur in any other circumstance.
- **FR-015**: System MUST produce byte-identical output for the same deck against the same
  content and asset revisions.

**Preview**

- **FR-016**: System MUST display a page-by-page visual preview of the PDF before download.
- **FR-017**: The preview MUST match the generated PDF in page count, card order, and card
  position.
- **FR-018**: System MUST display the page count and the total number of cards before the
  user commits to downloading.

**Assets and failure behavior**

- **FR-019**: System MUST read card images from a local directory the user configures, and
  MUST NOT require credentials, sign-in, or any network call to retrieve them.
- **FR-019a**: System MUST complete a full generation with no network connection available.
- **FR-019b**: System MUST report a clear, actionable error when the configured image
  directory is missing, unreadable, or empty, distinguishing "not configured yet" from
  "configured but wrong".
- **FR-019c**: System MUST NOT write to, move, rename, or delete anything in the configured
  image directory. It is read-only source material.
- **FR-020**: System MUST fail generation with a message naming the specific card when an
  image is missing, unreadable, or below the required resolution, and MUST NOT substitute a
  placeholder or silently omit the card.
- **FR-021**: System MUST distinguish, in user-facing errors, between a temporary retryable
  failure and a permanent one such as a card that does not exist.
- **FR-022**: System MUST record, for each generation, the deck requested, the card
  identifiers used, the content revision in effect, and the outcome.

**Calibration** *(supports User Story 3)*

- **FR-023**: System MUST offer a single-page calibration PDF containing a measurable
  printed ruler and one card outline at the exact target print size.

### Key Entities

- **Hero Deck**: A named, published pre-built deck associated with one hero. Has a display
  name, a hero identity, and an ordered list of card entries. Defined in the content catalog.
- **Card Entry**: One line of a deck — a reference to a Card plus a quantity.
- **Content Catalog**: The authored metadata defining every hero deck and every card, and
  mapping each card to its image filename. Lives outside the application as editable data,
  is validated before use, and carries a revision so a generated PDF can be traced to the
  catalog state that produced it.
- **Card**: A single distinct Marvel Champions card. Has a stable identifier independent of
  any filename, a display name, and an explicit reference to its face image file.
- **Card Image Asset**: The high-resolution source image for one card face, held as a file
  in the user's configured local image directory. Has a resolution and a format. Read-only,
  and never stored in this project.
- **Print Layout**: The rules turning an ordered card list into pages — target card size,
  grid arrangement, margins, and cut guides. The same layout drives both preview and PDF.
- **Generation Request**: One user request to produce a PDF. Has a selected deck, a content
  revision, an outcome, and a resulting document or a named failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the application running, a user goes from opening it to a downloaded PDF
  in under 2 minutes and no more than 4 interactions.
- **SC-001a**: The running application is not reachable from another device on the same
  network, verified by attempting to connect from a second machine.
- **SC-001b**: A full deck generates successfully with networking disabled on the machine.
- **SC-002**: Sleeve fit is measured, not assumed. A printed card is inserted into a
  standard penny sleeve in front of a standard Marvel Champions card across at least 3
  printer models and the outcome recorded. Success is either that it seats without forcing
  or bending, or that a specific size reduction is identified for FR-009. An untested
  assumption about fit is a failure of this criterion.
- **SC-003**: Printed card dimensions measure within ±0.5 mm of target on both axes on
  100% of test prints made at 100% scale.
- **SC-004**: Every card face is legible enough that a player can identify the card by name
  and read its rules text at normal play distance, confirmed by at least 3 testers.
- **SC-005**: The preview matches the downloaded PDF in page count, card order, and card
  position on 100% of generations.
- **SC-006**: Regenerating the same deck against unchanged content and assets produces an
  identical file on 100% of attempts.
- **SC-007**: 95% of deck generations complete within 30 seconds of confirmation.
- **SC-008**: 100% of generation failures name the specific card or condition responsible;
  no failure surfaces as a generic error and none produces a partial PDF.
- **SC-009**: A new hero deck becomes selectable without rebuilding or reinstalling the
  application — adding it to the catalog and restarting is sufficient.
- **SC-009a**: The same deck can be generated in all three fit modes and the printed results
  compared side by side, with each printed sheet identifiable as to which mode produced it.
- **SC-010**: 100% of catalog problems — a missing image file, an unknown card reference, a
  malformed entry — are caught by validation and reported together with the offending card
  or deck named, before any generation begins.

## Assumptions

**Scope**

- Card selection, deselection, reordering, and substitution are explicitly **out of scope**
  for this feature and are deferred to a later one, per the feature description. This
  feature produces the complete published deck as-is.
- The application is **local-only**: it runs on the operator's own machine and is never
  hosted. It is a web application in form — a browser UI over a local service — not in
  deployment.
- Authentication, accounts, and sessions are out of scope, and their absence is a
  consequence of local-only operation rather than an omission. The constitution's account
  security controls stay deferred, because no accounts exist to govern.
- Because nothing is publicly reachable, the application does not redistribute card
  artwork to third parties, which keeps it within the constitution's distribution scope.
- Saved decks, sharing, and multi-user features are out of scope.
- **Hosting this publicly later is a scope change, not a deployment step.** It would
  reintroduce access control, per-principal rate limiting, and the redistribution question
  the local-only decision currently avoids, and MUST be specified as its own feature.
- Only hero pack decks are in scope. Villains, modular sets, and scenarios are out of scope
  for this feature despite being in the product's longer-term ambition.
- Only single-deck generation is in scope; batch or multi-hero downloads are out of scope.

**Print and physical fit**

- **Cards print at full standard size (63.5 × 88.9 mm), not reduced.** This is a deliberate
  beta decision: ship at 100%, print real decks, and adjust from evidence rather than
  guessing a reduction up front. The known risk is that a proxy the same size as the card
  behind it fits the sleeve tightly; User Story 3 exists to surface this cheaply, and
  FR-009a keeps the adjustment to a one-place change.
- A user-selectable or per-deck card **size** remains out of scope; only the **fit mode**
  (FR-009b) is selectable.
- The fit-mode choice exists to settle an open question with printed evidence, not as a
  permanent preference. Source scans are 2.7% taller in proportion than a standard card, and
  which compromise looks right cannot be judged on screen. **Once a winner is established
  it should become the default and the other modes should be reconsidered for removal** —
  this is a deliberate, time-limited exception to the project's preference for one correct
  default over a toggle.
- "Penny sleeve" means a standard trading-card sleeve sized for that card. The printed
  proxy sits in front of a full-size card inside that sleeve.
- Users print at 100% scale with scaling disabled. The calibration page (User Story 3)
  exists because this assumption is unreliable in practice.
- A 3 × 3 grid of nine cards per page is assumed. Nine full-size cards occupy
  190.5 × 266.7 mm, which fits US Letter (12.7 mm side margins) and A4 (9.75 mm side
  margins) without scaling.
- Users supply their own spare Marvel Champions cards to act as backs. The site neither
  provides nor prints card backs.

**Assets and content**

- Card images are read from a **local directory** the user points the application at. The
  application holds no credentials and makes no outbound request to fetch an asset.
- Getting images onto disk is the user's job and is outside this feature — Google Drive's
  desktop sync, a one-time download, or any other means. The application neither performs
  nor supervises that sync, and does not detect whether the folder is current.
- The Google Drive of high-resolution TIFFs is the upstream source of that folder, not a
  runtime dependency. Nothing in the feature may assume Drive-specific or TIFF-specific
  behavior outside the asset adapter, so a later move to object storage or a different
  encoding remains an adapter change.
- Because assets involve no outbound calls, this feature exercises none of the
  egress-allowlist surface the constitution requires. Reintroducing remote asset fetching
  would bring that requirement back into play.
- Source images are assumed to be complete, correctly oriented card faces at sufficient
  resolution for 300 DPI at final size. Where they are not, FR-020 governs.
- Deck composition, card metadata, and the card-to-filename mapping all live in the content
  catalog — authored data outside the application, editable without rebuilding or
  redeploying it.
- Authoring and maintaining that catalog is the user's responsibility. Producing it from
  the existing Drive folder, whether by hand or with a one-off helper, is outside this
  feature's scope.
- Card identifiers are assumed to follow a stable published scheme rather than being
  invented per-deck, so the same card referenced by two decks resolves to one entry.

**Users and environment**

- Users are Marvel Champions players printing for personal play. They own the game and are
  proxying cards they do not have or wish to preserve.
- Users have a modern desktop or mobile browser and a consumer inkjet or laser printer.
- Traffic is hobby-scale. Concurrency in the low tens, not thousands.
