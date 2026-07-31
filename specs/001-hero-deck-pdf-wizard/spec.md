# Feature Specification: Hero Deck PDF Wizard

**Feature Branch**: `001-hero-deck-pdf-wizard`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "Let's develop our webpage that has a wizard that allows you to select a marvel champions hero pack deck that you can easily download as pdf with high enough res to print and play with. the cards should be slightly smaller than standard cards when printed so that they can easily be pushed into standard penny sleeves in front of a dummy marvel champions card (which will be used as the cards back). the site should show you a preview of the pages that will be in your pdf and in a later feature we will likely allow you to select or deselect or even move around cards or replace them with others from the library. the underlying storage mechanism is currently a google drive with high res tiff files."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download a printable hero deck (Priority: P1)

A player wants to try a hero they do not own. They open the site, pick that hero from a
list, and download a PDF. They print it on their home printer, cut the cards out, and slide
each one into a penny sleeve in front of a spare Marvel Champions card. The spare card
supplies the back and the rigidity; the printed sheet supplies the face. They sit down and
play that evening.

**Why this priority**: This is the entire product. Every other story is an improvement on a
journey that must already work end to end. If only this ships, the site is useful.

**Independent Test**: Select any hero, download the PDF, print it, cut one card, and insert
it into a sleeved standard card. Value delivered when the card fits without forcing and the
face is legible at arm's length.

**Acceptance Scenarios**:

1. **Given** the hero list is displayed, **When** a user selects a hero and confirms,
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
- The asset store is unreachable or rate-limits the request → the user sees a clear
  retryable error distinguishing "temporarily unavailable" from "this card does not exist".
- A deck lists the same card multiple times → each copy is printed, in the listed quantity.
- A source image has a different aspect ratio than a standard card → it is fitted without
  distortion and the discrepancy is reported rather than silently cropped.
- A source image is below the resolution needed for 300 DPI at final size → generation
  fails or warns explicitly; it is never silently upscaled.
- A deck is large enough to span many pages → pagination continues correctly with no
  duplicated or dropped cards.
- Two users request the same deck at the same time → both receive correct, identical PDFs.
- A user requests a deck while its content is being updated → the PDF reflects one
  consistent content revision, never a mixture.
- A user's browser cancels a slow download → no partially written PDF is presented as
  complete.

## Requirements *(mandatory)*

### Functional Requirements

**Selection**

- **FR-001**: System MUST present the list of available hero decks with a recognizable
  name for each, sourced from the content store rather than hard-coded.
- **FR-002**: Users MUST be able to select exactly one hero deck per generation request.
- **FR-003**: System MUST guide the user through selection, preview, and download as an
  ordered sequence in which the user can return to a prior step without losing selection.
- **FR-004**: System MUST reflect newly added hero decks without requiring a software
  release.

**Deck composition**

- **FR-005**: System MUST resolve a selected hero deck into an ordered list of card
  identifiers with quantities, defined by the content store.
- **FR-006**: System MUST include, for a selected hero, the full published pre-built player
  deck: the hero card, the hero-specific signature cards, and the aspect cards the pack
  ships with. The result MUST be playable without the user supplying additional cards. The
  hero's obligation card and nemesis encounter set are out of scope for this feature.
- **FR-007**: System MUST print one card face per listed copy, so that a deck listing three
  copies of a card yields three printed cards.

**Print output**

- **FR-008**: System MUST produce a single PDF containing every card in the resolved deck.
- **FR-009**: System MUST render every card at **63.5 × 88.9 mm** (2.5 × 3.5 in) — full
  standard Marvel Champions card size, 100% scale — measured on the printed page, within
  ±0.5 mm on both axes.
- **FR-009a**: The target card size MUST be expressed as a single configurable value rather
  than distributed through the layout logic, so that changing it is a one-place change when
  beta printing shows an adjustment is needed.
- **FR-010**: System MUST render card faces at an effective resolution of at least 300 DPI
  at final print size, and MUST NOT upscale a source image to reach it.
- **FR-011**: System MUST lay out cards in a fixed grid that fits both US Letter and A4
  without scaling, and MUST NOT depend on printer "fit to page" behavior.
- **FR-012**: System MUST produce card faces only, with no card backs and no duplex
  pairing, because the physical card behind the proxy supplies the back.
- **FR-013**: System MUST include cut guides that allow accurate trimming and that do not
  overlap any card face.
- **FR-014**: System MUST preserve card aspect ratio, never stretching or distorting a card
  face to fill its slot.
- **FR-015**: System MUST produce byte-identical output for the same deck against the same
  content and asset revisions.

**Preview**

- **FR-016**: System MUST display a page-by-page visual preview of the PDF before download.
- **FR-017**: The preview MUST match the generated PDF in page count, card order, and card
  position.
- **FR-018**: System MUST display the page count and the total number of cards before the
  user commits to downloading.

**Assets and failure behavior**

- **FR-019**: System MUST retrieve card images from the operator-configured asset store
  without requiring the end user to authenticate to it or supply credentials.
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
  name, a hero identity, and an ordered list of card entries. Defined in the content store.
- **Card Entry**: One line of a deck — a reference to a Card plus a quantity.
- **Card**: A single distinct Marvel Champions card. Has a stable identifier, a display
  name, and a reference to its face image asset.
- **Card Image Asset**: The high-resolution source image for one card face, held in the
  external asset store. Has a resolution and a format; not stored in this project.
- **Print Layout**: The rules turning an ordered card list into pages — target card size,
  grid arrangement, margins, and cut guides. The same layout drives both preview and PDF.
- **Generation Request**: One user request to produce a PDF. Has a selected deck, a content
  revision, an outcome, and a resulting document or a named failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor goes from landing on the site to a downloaded PDF in
  under 2 minutes and no more than 4 interactions.
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
- **SC-009**: A new hero deck becomes selectable on the live site without a software
  release, within 15 minutes of being added to the content store.

## Assumptions

**Scope**

- Card selection, deselection, reordering, and substitution are explicitly **out of scope**
  for this feature and are deferred to a later one, per the feature description. This
  feature produces the complete published deck as-is.
- User accounts, saved decks, and sharing are out of scope. Every visit is anonymous and
  every generation is self-contained.
- Only hero pack decks are in scope. Villains, modular sets, and scenarios are out of scope
  for this feature despite being in the product's longer-term ambition.
- Only single-deck generation is in scope; batch or multi-hero downloads are out of scope.

**Print and physical fit**

- **Cards print at full standard size (63.5 × 88.9 mm), not reduced.** This is a deliberate
  beta decision: ship at 100%, print real decks, and adjust from evidence rather than
  guessing a reduction up front. The known risk is that a proxy the same size as the card
  behind it fits the sleeve tightly; User Story 3 exists to surface this cheaply, and
  FR-009a keeps the adjustment to a one-place change.
- A user-selectable or per-deck card size is **out of scope** for this feature and is a
  candidate follow-up if beta printing shows one size does not suit every sleeve and
  printer combination.
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

- Card images are read from an operator-configured asset store. End users never
  authenticate to it, never see it, and never supply credentials — access is the operator's
  own.
- The asset store today is a Google Drive of high-resolution TIFFs. This is transitional;
  the feature must not assume Drive-specific or TIFF-specific behavior outside the asset
  adapter.
- Source images are assumed to be complete, correctly oriented card faces at sufficient
  resolution for 300 DPI at final size. Where they are not, FR-020 governs.
- Deck composition and card metadata live in the content store, not in this repository, and
  can be changed without a deploy.

**Users and environment**

- Users are Marvel Champions players printing for personal play. They own the game and are
  proxying cards they do not have or wish to preserve.
- Users have a modern desktop or mobile browser and a consumer inkjet or laser printer.
- Traffic is hobby-scale. Concurrency in the low tens, not thousands.
