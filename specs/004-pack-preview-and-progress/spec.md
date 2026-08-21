# Feature Specification: See a pack before you print it

**Feature Branch**: `004-pack-preview-and-progress`

**Created**: 2026-08-20

**Status**: Draft

**Input**: Noticed in real use, 2026-08-20. A user working through the pack-assembly path asked
what the "preview" tab did, having never seen one — because that half of the wizard has none.

## Why this exists

Feature 001's third step is called **"Check it before you print"**, and it earns the name: a
progress bar while the document builds, pages appearing as they render, and a rasterised image
of every sheet before the download button is offered. Feature 002 prints a far more
interesting document — a whole pack, assembled from a library nobody curated, with
substitutions on a third of its cards — and offers none of it. You press *Make the PDF*, wait,
and get a file.

The gap is not symmetric in one direction only. 002 reports things 001 never could: where
every image came from, which files went unused and why, which scans are too soft to print,
which cards could not be found. What it cannot do is **show you the page**. A report saying
`Battle Fury — reprint: Heros/Odinson_Thor/…` tells you a substitution happened; only a
picture tells you the borrowed art is the wrong colour.

Two things are missing and they are not the same size.

**Preview is additive.** 002 already stores its PDF durably, so a page image can be rasterised
from it on demand — where 001 had to keep pages in memory because its generations do not
survive the process. This is the smaller half and it works for a reused document as well as a
freshly rendered one.

**Progress needs the render to actually become asynchronous.** Today `POST /confirmation`
calls the render inline and returns `202 Accepted` when the work is already finished. For a
real pack that is a request that blocks for around fifty seconds and then reports a status
code meaning "started". No client can show progress against that, and the wizard's
"Building the PDF…" line is a message with nothing behind it. 001 does this properly, with a
worker pool and a run the client polls.

The lifecycle already anticipates this. `RunState.RENDERING` exists, and `resume()` already
handles a run whose process died mid-render by returning it to `ready`. What is missing is the
render actually happening somewhere the request is not waiting on.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Look at the sheets before spending paper (Priority: P1)

A user finishes assembling a pack and, before printing, pages through images of the actual
sheets — nine cards to a page, cut marks, in the order they will come out of the printer.
They spot that a borrowed reprint is visibly a different colour from the rest, and go back and
supply their own scan instead.

**Why this priority**: It is the reported gap and the one that saves paper. A pack is around
seven sheets of card stock and the substitutions this feature makes are exactly the things
worth looking at before committing to them.

**Independent Test**: Assemble a pack, request each page image, and assert an image comes back
for every page the report counts. Delivers the whole of the value on its own, with no change
to how the document is built.

**Acceptance Scenarios**:

1. **Given** a run that has produced a document, **When** the user asks for page *n*,
   **Then** an image of that sheet is returned.
2. **Given** the same run, **When** the user asks for a page beyond the document's page count,
   **Then** the request is refused and says how many pages there are.
3. **Given** a run whose document was **reused** rather than rendered (FR-026h), **When** the
   user asks for a page, **Then** it is returned exactly as for a freshly rendered one.
4. **Given** a run that has not produced a document, **When** the user asks for a page,
   **Then** the request is refused and says the run has not printed yet.
5. **Given** any preview request, **When** the document is later downloaded, **Then** its bytes
   are identical to what they would have been had no preview been requested.

---

### User Story 2 - Watch a pack being built (Priority: P2)

A user confirms a pack and sees it building: which page is being composed, how far along it is,
and pages appearing as they finish rather than a spinner and a wait.

**Why this priority**: P2 because a slow silent wait is bad but not wrong, where the missing
preview lets a user print something they would have rejected. It is also much the larger
change — it makes rendering asynchronous, which touches the run lifecycle, the API's polling
shape, and the meaning of a status code the contract already publishes.

**Independent Test**: Confirm a pack and poll the run while it renders, asserting the reported
progress advances and the run reaches `complete` without the confirming request having waited
for it.

**Acceptance Scenarios**:

1. **Given** a run in `ready`, **When** the user confirms it, **Then** the request returns
   promptly and the run is in `rendering`.
2. **Given** a run in `rendering`, **When** the user reads it, **Then** it reports how far
   through the document it is.
3. **Given** a run in `rendering`, **When** the render finishes, **Then** the run reaches
   `complete` with no further request from the user.
4. **Given** a run whose document is reused rather than rendered, **When** the user confirms
   it, **Then** it reaches `complete` without a rendering phase the user has to wait through.
5. **Given** a run that was rendering when the process stopped, **When** the user reopens it,
   **Then** it is back in `ready` and can be confirmed again — the behaviour `resume()`
   already provides, which must survive the change.

---

### User Story 3 - See a page while it is still building (Priority: P3)

Pages appear one at a time as they are composed, so the first sheet can be inspected before
the last is drawn.

**Why this priority**: The luxury tier, and only worth building on top of both stories above.
001 does it, and the render already has the hook — `compose` takes an `on_page` callback whose
docstring says it is "purely additive: with it omitted, nothing extra is computed and the
bytes are identical". So the mechanism exists; what is missing is somewhere to put the pages
while the run is still going.

**Independent Test**: Confirm a pack and assert a page image can be fetched before the run
reaches `complete`.

**Acceptance Scenarios**:

1. **Given** a run in `rendering` that has completed at least one page, **When** the user asks
   for that page, **Then** its image is returned.
2. **Given** the same run, **When** the user asks for a page not yet composed, **Then** the
   request is refused as not ready rather than as absent.

---

### Edge Cases

- **A document that is reused rather than rendered.** FR-026h means confirming a pack often
  produces no render at all. Both preview and progress must be correct when the work takes no
  time, which is the case a progress model is most likely to get wrong.
- **The library disappears mid-render.** A synced folder can stall or unmount between
  resolution and composition; this is a live condition, fixed once already for the synchronous
  path. Whatever runs the render asynchronously has to report it as well as the request did.
- **Two tabs confirming one run.** Every mutating call already carries `If-Match`; a render
  started twice must not produce two documents or two log records.
- **A very wide preview request.** The image width is a number from the client and is a
  memory cost on the server.
- **A pack whose PDF is around 200 MB.** Rasterising a page from it must not mean holding all
  of it, and the render target 001 misses is already documented as accepted.
- **Deleting a run while it renders.**

## Requirements *(mandatory)*

### Functional Requirements

- **FR-201**: A user MUST be able to retrieve an image of any page of a run's document.
- **FR-202**: A preview MUST NOT change the document. The bytes downloaded MUST be identical
  whether or not any page was ever previewed (002's SC-007).
- **FR-203**: Previewing MUST work identically for a document that was reused and one that was
  freshly rendered (FR-026h).
- **FR-204**: A request for a page that does not exist, or for a run that has produced no
  document, MUST be refused with which of the two it is.
- **FR-205**: The requested image width MUST be bounded, and a request outside the bounds
  refused rather than served at a size the server chose silently.
- **FR-206**: Confirming a pack MUST return without waiting for the document to be composed,
  and the run MUST report `rendering` until it is done.
- **FR-207**: A run being composed MUST report its progress in terms of the document — pages
  finished against pages expected — not as an opaque percentage.
- **FR-208**: A run whose document is served from storage MUST reach `complete` without a
  rendering phase.
- **FR-209**: A render that fails MUST leave the run in a state the user can act on, naming
  the cause, and MUST NOT leave a partial document retrievable.
- **FR-210**: A run interrupted mid-render MUST return to `ready` when reopened, as it does
  today.
- **FR-211**: The API's published status codes and states MUST mean what they say. `202` on
  confirmation currently indicates work that has already finished.
- **FR-212**: Everything feature 002 refuses to do, this feature MUST also refuse. The library
  is never written to; card images come only from the user's library or their own uploads;
  the egress allowlist is unchanged; previews are rendered locally and never fetched.
- **FR-213**: Preview images MUST NOT be retained in a way that grows storage without bound.
  TODO(clarify): 002 already stores documents deliberately and sweeps orphans at startup
  (ADR 0001). Whether page images are cached at all, and if so whether they are swept with
  their run, is a storage decision the plan should take rather than a requirement.

### Key Entities

- **Page image**: A rasterisation of one sheet of a run's document, at a requested width.
  Derived, never authoritative — the document is the artefact.
- **Render progress**: What a run reports while composing. Pages finished against pages
  expected, which is a number the user can hold against the report they have already read.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-201**: A user can see every page of an assembled pack without downloading it or opening
  a PDF reader.
- **SC-202**: A document's bytes are identical with and without previewing, verified the same
  way 002's determinism is.
- **SC-203**: Confirming a pack returns in well under a second whether the document is
  rendered or reused, against the tens of seconds a real pack takes to compose today.
- **SC-204**: A user watching a pack build can tell at any moment how much is left, in pages.
- **SC-205**: The ten acceptance heroes produce byte-identical documents to those they produce
  today.
- **SC-206**: No run is left in a state a user cannot leave, including when the render fails or
  the process stops during it.

## Assumptions

- **The document is the source for a preview.** 002 stores it durably, so a page can be
  rasterised on demand and nothing extra needs keeping. This is what makes User Story 1 much
  smaller than User Story 2, and it is why they are separable.
- **The existing rasteriser is reused.** Feature 001 already renders a page of a PDF to an
  image with bounded widths; nothing here needs a second way to do that.
- **Render timing targets are not reopened.** 001's SC-007 and SC-007a are knowingly missed —
  48.9 s for a deck against a 30 s target and 10.5 s to the first preview page against 5 s —
  measured, reviewed and accepted. This feature makes the wait *visible*, which is a different
  claim from making it shorter, and no criterion here asserts a duration for composing.
- **Asynchronous rendering is a change to 002, not a new subsystem.** `RunState.RENDERING`
  already exists, `resume()` already recovers a run interrupted in it, and feature 001 already
  runs its renders on a worker pool. The work is connecting those, not inventing them.
- **Paper size and fit mode are being wired into the pack path separately.** They are a
  prerequisite for a preview to be worth looking at — a preview of the wrong fit mode is
  misleading — but the API has always carried both and only the wizard omits them, so that is
  a fix rather than part of this feature.
