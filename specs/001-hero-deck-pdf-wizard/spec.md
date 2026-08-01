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
2. **Given** a generated PDF, **When** it is printed at 100% scale on the page size it was
   generated for, **Then** every card *slot* measures 63.5 × 88.9 mm within ±0.5 mm on both
   axes, and the printed face fills that slot exactly in `crop` and `stretch` mode, or
   measures 61.8 × 88.9 mm within ±0.5 mm in `fit` mode.
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
  **fails**, naming the card. It is never upscaled and never printed at reduced quality.
- Several cards fail in the same generation → all failures are reported together, not one
  per attempt.
- A deck resolves to zero printable cards → this is a catalog validation error, not an empty
  PDF.
- The catalog is valid but defines no decks → the selection step says so plainly rather than
  presenting an empty list that looks like a loading failure.
- Source images differ slightly in proportion from one another → each is fitted on its own
  measurements; no single ratio is assumed for the whole deck.
- A file in the image directory is a format other than TIFF → it is accepted if the decoder
  supports it, identified by content rather than extension.
- A deck is large enough to span many pages → pagination continues correctly with no
  duplicated or dropped cards.
- The catalog is edited while the application is running → a generation uses one consistent
  catalog revision throughout, never a mixture of old and new.
- A download is interrupted part-way → the generated document remains retrievable and can be
  requested again without regenerating it.
- The application is started while another program already holds its port → it reports the
  conflict clearly instead of failing silently or falling back to a public interface.
- The configured image directory is missing, unreadable, empty, or points at the wrong
  place → the user gets an actionable message naming the problem, not a generic failure.
- The catalog names an image file that is not present in the directory → validation fails
  naming the card and the expected filename, before any generation is attempted.
- Two different **printings** reference the same image file → reported as a warning, not an
  error. Usually a copy-paste mistake, but legitimate often enough not to block generation.
- A deck's preferred printing is unavailable but another printing of the same card is → the
  stand-in is used and the substitution is reported before printing (FR-005g, FR-005h).
- A card has exactly one printing and its image is missing → generation fails naming the
  card; there is nothing to fall back to (FR-005i).
- Several printings of a card are available as stand-ins → the choice is deterministic, so
  regenerating the same deck yields the same file (FR-005j).
- The same card appears in two decks with different preferred printings → each deck prints
  its own pack's art; the card's identity is unchanged.
- A double-sided card's second face is missing → the card cannot be printed usefully, so the
  generation fails naming the card and the missing side.
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
- **FR-0A4**: System MUST bound the cost of a single generation with these explicit limits,
  so that a malformed or oversized source image cannot exhaust the machine. This protects
  against bad data, not against a hostile user.
  - **Per image**: decode completes within **10 seconds** and **512 MB** of memory, and the
    image is rejected above **80 megapixels** before decode is attempted.
  - **Per generation**: **200 card faces** maximum, and **120 seconds** total wall clock.
  - Exceeding any limit MUST fail the generation naming the limit and, where applicable, the
    card that hit it — never a silent truncation or a partial document.
  - These figures are starting values chosen to sit far above real decks (~41 cards, ~3 MP
    scans) and far below anything that would destabilise a laptop. They are expected to be
    tuned from observed behaviour.

**Selection**

- **FR-001**: System MUST present the list of available hero decks with a recognizable
  name for each, sourced from the content catalog rather than hard-coded.
- **FR-002**: Users MUST be able to select exactly one hero deck per generation request.
- **FR-003**: System MUST guide the user through selection, preview, and download as an
  ordered sequence in which the user can return to a prior step without losing selection.
- **FR-003a**: Returning to a prior step while a generation is running MUST be permitted.
  The running generation is either still available on return or simply abandoned; it MUST
  NOT block the interface or prevent starting another.
- **FR-003b**: Explicit cancellation of a running generation is **not required**. Bounded by
  FR-0A4's 120-second ceiling, abandoning one is sufficient. An abandoned generation MUST NOT
  hold resources indefinitely.
- **FR-003c**: While the catalog is being validated at startup, the system MUST indicate that
  it is doing so rather than presenting an empty or apparently broken deck list.
- **FR-003d**: Each empty state MUST be presented as an explanation with a next action, not
  as a blank region: no catalog configured, catalog present but defining no decks, and a
  deck resolving to no printable cards are each distinguishable from one another.
- **FR-003e**: A validation report listing many problems MUST remain readable — grouped by
  the deck or card concerned, and not truncated to an arbitrary first few.
- **FR-003f**: The calibration page MUST be reachable from the interface itself. It MUST NOT
  require knowing a URL.
- **FR-003g**: Keyboard operation MUST be possible for the whole flow — selecting a deck,
  choosing options, and starting a generation. Conformance to a formal accessibility
  standard is **out of scope** for this feature; this is a deliberate scope decision for a
  single-user local tool, not an oversight.
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

**Printings and art provenance**

The same card — same title, same rules — is published in several packs with different
artwork suited to each pack's theme. A deck is meant to be printed with the artwork that
shipped in *its* pack, so the model must distinguish a card from a particular printing of it.

- **FR-005e**: The catalog MUST model a **card** (title and rules) separately from a
  **printing** of that card (the artwork from one specific pack, with its own image file).
  One card MAY have many printings.
- **FR-005f**: Each deck entry MUST name the **preferred printing** — the one that shipped
  in that deck's own pack — rather than only naming the card.
- **FR-005g**: When a preferred printing's image is unavailable, the system MUST fall back
  to another available printing of the same card rather than failing the generation. A
  stand-in is a correct card with different art; it is playable, and refusing to print the
  deck over it would be worse than printing it.
- **FR-005h**: Every substitution MUST be reported before the user commits to printing,
  naming the card, the printing that was wanted, and the printing used instead. Falling back
  silently is prohibited — a user comparing a printed deck against the pack must be able to
  tell which cards differ and why.
- **FR-005i**: When no printing of a card has an available image, the generation MUST fail
  naming that card, per FR-020. Fallback covers missing *art*, never a missing card.
- **FR-005j**: Fallback selection MUST be deterministic: the same catalog and the same
  available files MUST always choose the same stand-in, so FR-015's byte-identical guarantee
  survives substitution.
- **FR-005b1**: Card identifiers MUST be assigned by the catalog, treated as opaque by the
  application, and unique within a catalog. The application MUST NOT parse meaning out of an
  identifier or require it to follow any particular format.
- **FR-005c**: System MUST validate the catalog before use, checking that it parses, that
  its declared format version is one the application recognises, that every card identifier
  is unique, that every card a deck references exists, that every card maps to an image
  file, that every mapped file is present in the configured directory, that every quantity
  is at least 1, and that no mapped path escapes the configured directory.
- **FR-005c1**: The catalog MUST declare a format version. An unrecognised version MUST be
  refused outright rather than parsed on a best-effort basis.
- **FR-005c2**: System MUST derive a **catalog revision** from the catalog's content, such
  that any change to cards, decks, or image mappings yields a different revision and an
  unchanged catalog yields the same one. The revision MUST NOT depend on file timestamps or
  on where the catalog is stored.
- **FR-005c3**: The catalog's location MUST be user-configurable. When it is unset,
  unreadable, or absent, the system MUST say which of those is the case and what to do about
  it, rather than presenting an empty deck list as though the catalog were valid.
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
- **FR-008c**: The downloaded file's name MUST identify the deck, the fit mode, and the page
  size, so that sheets printed from different settings remain distinguishable after the
  application has been closed.
- **FR-008a**: The user MUST be able to choose the page size the PDF is generated for — US
  Letter or A4 — and the PDF MUST be emitted at that size so the print needs no rescaling.
  Letter is the default.
- **FR-008b**: Pages MUST be portrait.
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

  Each mode's printed result MUST be independently verifiable: `crop` and `stretch` produce
  a face of 63.5 × 88.9 mm ±0.5 mm; `fit` produces a face that touches the slot on its
  constraining axis and is smaller on the other, with neither dimension exceeding the slot.
- **FR-009b1**: In `fit` mode, the unused area of the slot MUST be left blank — no frame,
  border, fill, or shadow. Cut guides continue to mark the slot, not the smaller face, so
  that every card is cut to the same size regardless of mode.
- **FR-009b2**: The fit mode MUST be applied to each card independently. Source images vary
  slightly in proportion from one another, and each is fitted on its own measurements rather
  than against a single ratio assumed for the whole deck.
- **FR-009c**: The interface MUST state, at the point of choice, what each mode costs —
  naming that `crop` discards part of the image's edges, that `fit` leaves the card smaller
  than a standard card, and that `stretch` distorts the image. A user MUST NOT be able to
  select distortion without being told it is distortion.
- **FR-009d**: The chosen mode MUST be recorded with the generation, reflected in the
  preview, and identifiable from the generated document itself — so a printed sheet can be
  matched to the mode that produced it without relying on memory.
- **FR-010**: System MUST render card faces at an effective resolution of at least 300 DPI
  at final print size, and MUST NOT upscale a source image to reach it. The measurement MUST
  be taken over the region actually printed: in `crop` mode, the cropped portion, since
  discarded pixels do not contribute to the printed result.
- **FR-011**: System MUST lay out cards in a fixed 3 × 3 grid, identical for both supported
  page sizes, centred with equal margins, and MUST NOT depend on printer "fit to page"
  behavior.
- **FR-012**: System MUST place every printed face in its own slot on the front of the
  sheet. Duplex printing MUST NOT be required, because for ordinary cards the physical card
  behind the proxy supplies the back.
- **FR-012a**: A card the catalog marks as **double-sided** — the hero identity, whose two
  sides are the hero and the alter-ego — MUST contribute **both** faces as two separate
  slots. The user sleeves the two printed faces back-to-back around a dummy card, so each
  side shows outward and the card flips in play exactly as the real one does.
- **FR-012b**: The two faces of a double-sided card MUST be laid out adjacently, so they are
  cut and sleeved as a pair without hunting across pages.
- **FR-012c**: The total printed face count MUST account for double-sided cards contributing
  two faces each. A deck of 40 single-sided cards plus one double-sided hero is 42 faces,
  not 41.
- **FR-013**: System MUST include cut guides marking every slot boundary, as short marks
  positioned outside the slot in the surrounding margin or gutter. A guide MUST NOT enter
  any slot, and therefore MUST NOT overlap a card face. Guides MUST be fine enough not to
  survive a cut made along them, and dark enough to be visible on a consumer printer.
- **FR-014**: System MUST preserve card aspect ratio in the `crop` and `fit` modes. The
  `stretch` mode of FR-009b is the sole exception: it MUST be explicitly selected by the
  user, MUST NOT be the default, and MUST be labelled as distorting wherever it is offered.
  Distortion MUST NOT occur in any other circumstance.
- **FR-015**: System MUST produce byte-identical output for the same deck at the same
  catalog revision, the same asset files, the same fit mode, and the same page size. Those
  five inputs together define the output; changing any of them may change the bytes, and
  changing none of them MUST NOT. This holds **on one machine with one set of pinned
  dependency versions**, across separate runs and separate processes. Identical output
  across differing library versions is explicitly NOT claimed.
- **FR-015a**: Every operation that could vary between runs MUST be pinned rather than left
  to a library default — in particular the image resampling filter, iteration order wherever
  it reaches output, and any timestamp or document identifier the format would otherwise
  generate. A library default changing between versions MUST NOT be able to alter output
  silently.

**Preview**

- **FR-016**: System MUST display a page-by-page visual preview of the PDF before download.
- **FR-016a**: While a generation is running, the system MUST show that work is in progress
  and MUST convey advancement rather than only a static indicator — a generation is allowed
  to run for up to 120 seconds, and an interface that looks frozen for two minutes is
  indistinguishable from one that has failed.
- **FR-016b**: Preview pages MUST become viewable as they become available rather than only
  once every page is ready.
- **FR-016c**: Changing the fit mode or page size MUST invalidate any displayed preview. A
  preview MUST NOT remain on screen describing settings that are no longer selected.
- **FR-016d**: Preview raster resolution MUST be sufficient to identify a card by name and
  art, and MUST be capped so that requesting a preview cannot approach the cost of the
  generation itself. Preview resolution MUST NOT affect the PDF in any way.
- **FR-017**: The preview MUST match the generated PDF in page count, card order, and card
  position.
- **FR-018**: System MUST display the page count and the total number of printed faces
  before the user commits to downloading, counting double-sided cards as two.
- **FR-018a**: System MUST list any art substitutions (FR-005h) alongside the preview,
  before the user commits paper to the job — not afterwards in a log.

**Assets and failure behavior**

- **FR-019**: System MUST read card images from a local directory the user configures, and
  MUST NOT require credentials, sign-in, or any network call to retrieve them.
- **FR-019a**: System MUST complete a full generation with no network connection available.
- **FR-019b**: System MUST report a clear, actionable error when the configured image
  directory is missing, unreadable, or empty, distinguishing "not configured yet" from
  "configured but wrong".
- **FR-019b1**: Every user-facing error MUST name the specific thing that failed — the card,
  the deck, the file, or the limit — and state what the user can do about it. A message that
  states only that something went wrong does not satisfy any requirement in this spec.
- **FR-019d**: System MUST accept any image format its decoder supports, identified by
  inspecting file contents rather than by file extension or declared type. TIFF is what the
  current source uses; it MUST NOT be assumed to be the only format.
- **FR-019c**: System MUST NOT write to, move, rename, or delete anything in the configured
  image directory. It is read-only source material.
- **FR-020**: System MUST fail generation with a message naming the specific card when
  **no printing** of it has a usable image — missing, unreadable, or below the required
  resolution — and MUST NOT substitute a placeholder or silently omit the card. Falling back
  to a different *printing* of the same card is not substitution in this sense and is
  governed by FR-005g–j; substituting a placeholder image, or a different card, remains
  prohibited. A resolution shortfall is a **failure, not a
  warning** — proceeding would either upscale, which FR-010 forbids, or print a face that
  cannot be read at play distance.
- **FR-020a**: When several cards fail, the system MUST report all of them together, in the
  same way FR-005d requires for catalog validation. Fixing one problem at a time across
  repeated attempts is a failure of this requirement.
- **FR-020b**: A failed generation MUST leave no downloadable document. There is no partial
  output.
- **FR-021**: System MUST distinguish, in user-facing errors, between a temporary retryable
  failure and a permanent one. The failure conditions are: **catalog invalid**, **image file
  missing**, **image unreadable**, **image below required resolution**, **a cost limit
  exceeded**, and **an unexpected internal error**. Of these, only *image unreadable* — a
  lock, a permission problem, or a cloud-sync placeholder not yet materialised — is
  retryable.
- **FR-021a**: System MUST NOT retry automatically. Retrying is the user's action, and
  re-requesting the same deck MUST be sufficient to retry; no cache invalidation or restart
  may be required.
- **FR-021b**: Generated documents MUST remain retrievable for as long as the application
  keeps running, and MUST NOT be expected to survive a restart. Nothing in this feature
  requires generated output to be durable.
- **FR-022**: System MUST record, for each generation, the deck requested, the card
  identifiers used, the catalog revision in effect, the fit mode, the page size, and the
  outcome.
- **FR-022a**: Records MUST be written as structured, machine-readable lines to the
  application's standard output or a user-configured file. Retention is the user's concern;
  the application MUST NOT rotate, prune, or manage log storage.
- **FR-022b**: Records MUST NOT contain absolute filesystem paths outside the configured
  directories, environment values, or anything else a user would not want to paste into a
  bug report. A generation record is expected to be shareable as-is.

**Calibration** *(supports User Story 3)*

- **FR-023**: System MUST offer a single-page calibration PDF containing a measurable
  printed ruler and one card outline at the exact slot size of 63.5 × 88.9 mm. The outline
  is the slot, not a fit-mode face, so a real card laid over it should match on all four
  sides regardless of which fit mode a deck is later generated with.

### Key Entities

- **Hero Deck**: A named, published pre-built deck associated with one hero. Has a display
  name, a hero identity, and an ordered list of card entries. Defined in the content catalog.
- **Card Entry**: One line of a deck — a reference to a Card, the preferred Printing for
  this deck, and a quantity.
- **Printing**: One published version of a card's artwork, belonging to a pack, with its own
  image file. A card may have several; a deck prefers the one from its own pack and accepts
  another as a stand-in (FR-005e–j).
- **Content Catalog**: The authored metadata defining every hero deck and every card, and
  mapping each card to its image filename. Lives outside the application as editable data,
  is validated before use, and carries a revision so a generated PDF can be traced to the
  catalog state that produced it.
- **Card**: A single distinct Marvel Champions card — one title with one set of rules. Has a
  stable identifier independent of any filename, a display name, a flag for whether it is
  double-sided, and one or more Printings. The card is the thing a deck lists; a printing is
  the artwork it gets.
- **Card Image Asset**: The high-resolution source image for one card face, held as a file
  in the user's configured local image directory. Has a resolution and a format. Read-only,
  and never stored in this project.
- **Print Layout**: The rules turning an ordered card list into pages — target card size,
  grid arrangement, margins, and cut guides. The same layout drives both preview and PDF.
- **Generation Request**: One user request to produce a PDF. Has a selected deck, a fit
  mode, a page size, the catalog revision captured at creation, an outcome, and a resulting
  document or one or more named failures.

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
- **SC-003**: Printed card dimensions measure within ±0.5 mm of the target for the selected
  fit mode, on both axes, for **all nine cards on at least one full page from each of the
  three fit modes**, printed at 100% scale.
- **SC-004**: Every card face is legible enough that a player can identify the card by name
  and read its rules text at normal play distance, confirmed by at least 3 testers.
- **SC-005**: The preview matches the downloaded PDF in page count, card order, and card
  position on 100% of generations.
- **SC-006**: Regenerating the same deck against unchanged content and assets produces an
  identical file on **20 consecutive attempts**, including at least one in a separate
  process, on the same machine with unchanged dependency versions.
- **SC-007**: 95% of deck generations complete within 30 seconds of confirmation, measured
  on a full ~41-card deck on a consumer laptop of the era. This is a target for typical
  work; FR-0A4's 120-second ceiling is a hard cutoff that fails the generation, not a
  second target.
- **SC-007a**: The first preview page becomes viewable within 5 seconds of confirmation,
  independent of how long the remaining pages take.
- **SC-008**: 100% of generation failures name the specific card or condition responsible;
  no failure surfaces as a generic error and none produces a partial PDF.
- **SC-009**: A new hero deck becomes selectable without rebuilding or reinstalling the
  application — adding it to the catalog and restarting is sufficient.
- **SC-009a**: The same deck can be generated in all three fit modes and the printed results
  compared side by side, with each printed sheet identifiable as to which mode produced it
  from the sheet alone, without consulting the application (FR-009d).
- **SC-011**: Every failure condition named in FR-021 can be deliberately provoked and
  produces its own distinct, correctly-classified message — no condition falls through to
  the generic internal error.
- **SC-012**: When a deck's own pack art is complete, 100% of printed faces use it. When it
  is not, every stand-in is listed before printing, and a user can identify each substituted
  card from that list without comparing images.
- **SC-013**: A double-sided card yields two faces that, cut and sleeved back-to-back around
  a dummy card, flip in play indistinguishably from the real card.
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
- The hero identity card is double-sided in play. Its two printed faces sleeve back-to-back
  around one dummy card, so each side shows outward — the dummy supplies rigidity rather
  than a back. This is why FR-012a exists and why duplex printing is still not needed.
- Card numbering is **pack-scoped, not global**. The same card is numbered differently in
  each pack that publishes it — Make the Call is 16 in the Captain America pack and 71 in
  the Core Set. Numbers are therefore properties of a printing, never of a card, and never
  an identifier.

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
- Source images are assumed to be complete, correctly oriented card faces. **Resolution is
  no longer assumed:** a real Captain America pack sample measured ~1446 × 2079 px at 600
  DPI on 2026-07-31, against the 750 × 1050 the 300 DPI floor requires — 1.93× linear
  headroom. Where a future scan falls short, FR-020 governs.
- Source scans are assumed to be **full-bleed**, with card art running to all four edges and
  no trim margin. This is why the aspect-ratio difference cannot simply be discarded and
  requires the fit modes of FR-009b.
- The application does **not** detect whether the image directory is stale relative to its
  upstream source. Keeping it current is the user's responsibility; a file that has not
  synced yet surfaces as a retryable unreadable-asset failure, not as a sync warning.
- The user is assumed to have authored a catalog before first use. Until one is configured,
  the application is expected to explain what is missing rather than appear broken
  (FR-005c3).
- Deck composition, card metadata, and the card-to-filename mapping all live in the content
  catalog — authored data outside the application, editable without rebuilding or
  redeploying it. **Restarting the application to pick up catalog changes is acceptable**;
  live reload is not required by FR-004 or SC-009.
- Authoring and maintaining that catalog is the user's responsibility. Producing it from
  the existing Drive folder, whether by hand or with a one-off helper, is outside this
  feature's scope.
- Card identifiers are assumed to follow a stable published scheme rather than being
  invented per-deck, so the same card referenced by two decks resolves to one entry — with
  each deck free to prefer a different printing of it.
- Art substitution is assumed to be acceptable to users: a stand-in printing is the correct
  card with different artwork, and playing with it is normal practice. What is not
  acceptable is not being told, which is why FR-005h requires the list up front.

**Users and environment**

- Users are Marvel Champions players printing for personal play. They own the game and are
  proxying cards they do not have or wish to preserve.
- Users have a modern desktop or mobile browser and a consumer inkjet or laser printer.
- The machine running the application is assumed to be a contemporary consumer laptop or
  desktop — multiple cores and at least 8 GB of RAM. FR-0A4's absolute limits are set against
  that baseline; on a substantially smaller machine they would need lowering.
- Only one person uses the application at a time, and only one generation runs at a time.
  Concurrency is not a design concern for this feature.
