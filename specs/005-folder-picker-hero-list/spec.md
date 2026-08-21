# Feature Specification: Choose a folder, then choose a hero

**Feature Branch**: `005-folder-picker-hero-list`

**Created**: 2026-08-21

**Status**: Shelved 2026-08-21 — specified and decided, not scheduled. Nothing here is
blocked or unresolved; the feature was deprioritised. To resume, start at
[ADR 0002](../../docs/adr/0002-the-service-opens-the-native-folder-dialog.md) and verify the
front-most premise it names before writing any code. The pre-existing defect found while
researching this feature is **not** shelved with it — it is
[issue #38](https://github.com/robciaccio/marchamp-proxy-builder/issues/38).

**Input**: Reported from real use, 2026-08-21. "In the UI when a user is asked for the base
directory and the hero directory, they are currently forced to type out the whole path on the
user's computer (or paste it in). I need this to be like a select button… you click a button
then use the computer's Finder dialog to find the directory… THEN it creates a list of heroes
prepopulated based on the fact that all the heroes are in the `Heros` folder right under that
base dir. You just click the one that you want rather than also typing in the path to the hero
folder. I'm OK with the list names just being the hero folder names."

## Why this exists

Every pack run starts with two free-text boxes. **Scan library folder** wants an absolute path
on the user's machine; **Hero folder** wants a path relative to it. Both are typed. The
placeholders — `/Users/you/Marvel Champions` and `Heros/Steve Rogers_Captain America` — are the
only documentation of the format, and the second one carries a separator, a space, an
underscore and a spelling (`Heros`) that all have to be reproduced exactly.

This is the first thing a user touches and the only step where a typo is silently fatal rather
than obviously wrong. A mistyped library root fails the containment check. A mistyped hero
folder produces "this folder matched no pack" — the same message a genuinely unidentifiable
hero produces (feature 003), so the user goes off to check their scan filenames when the real
fault was a missing underscore. Nothing about the run tells them which of the two happened.

The information needed to remove both boxes is already on the user's disk and already trusted
by the application. **Feature 002 deliberately declined to guess the layout** — it rejected
deriving the library root by walking up to "the nearest ancestor containing `Heros/`" because
that "is a guess about someone else's directory layout, it fails silently when wrong, and it
would put a path the user never named into a containment decision"
([002 spec, Clarifications](../002-starter-deck-assembly/spec.md)). That reasoning still holds
and this feature does not overturn it: **the user still names the library root**, by choosing it
rather than typing it. The layout assumption is then used only to *offer a list*, never to
decide containment, and a wrong guess is visible on screen instead of silent.

### One thing the description asks for that cannot be built as described

The buttons the user is comparing this to — the ones that supply a scan the wizard did not find,
and the deck list image — work because a web page only needs the file's **bytes**. It never
learns where the file came from, and the spec says so on screen: *"only the file's own name is
recorded."*

A folder is different. What this feature needs from the picker is the **path**, and a web page
is not permitted to learn one. A browser's own directory chooser hands back names relative to
the folder chosen, with no way to reconstruct `/Users/you/…`. So the outcome the user asked for
— click a button, get a real folder chooser, never type a path — is achievable, but not by the
page doing it alone. It requires the part of the application already running on the user's
machine to be involved. **How it does so was settled by panel and is recorded in
[ADR 0002](../../docs/adr/0002-the-service-opens-the-native-folder-dialog.md)**: the service
opens the platform's own dialog as a subprocess, gated to macOS, and never enumerates the
filesystem. See Decisions below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose the scan library instead of typing it (Priority: P1) 🎯 MVP

A user starting a pack run clicks a button beside **Scan library folder**, a folder chooser
opens, they select their scan library and confirm. The chosen folder is shown back to them in
full, and the run proceeds exactly as it does today. They never type or paste a path.

**Why this priority**: It is half the reported friction and the prerequisite for the other half
— the hero list cannot be built until a library root is known. It is also independently
valuable: a user who picks the library and still types the hero folder is already better off,
because the typo that survives today's form is the *absolute* one, and it is the one this story
removes.

**Independent Test**: Start a run choosing the library folder through the picker and typing the
hero folder as before. It succeeds when the run produces the same result as a run whose library
root was typed, and when no absolute path was entered by hand.

**Acceptance Scenarios**:

1. **Given** the pack form, **When** the user activates the library folder control and confirms
   a folder, **Then** that folder becomes the run's library root and its full path is displayed.
2. **Given** a library root already chosen, **When** the user activates the control again and
   confirms a different folder, **Then** the run's library root is the newly chosen one and any
   hero already selected under the previous root is cleared.
3. **Given** the user opens the chooser and cancels it, **When** they return to the form,
   **Then** the previously chosen library root — if any — is unchanged and no error is shown.
4. **Given** a folder the user chooses that cannot be read, **When** they confirm it, **Then**
   the form says so at the point of choice and does not accept it as the library root.

---

### User Story 2 - Pick a hero off a list (Priority: P1)

Once the library folder is chosen, the form replaces the **Hero folder** text box with the
heroes it found — the folder names directly under `Heros/`, listed as they appear on disk. The
user clicks one. The run's hero folder is set from that choice.

**Why this priority**: It is the other half of the reported friction, and it is the half that
produces the misleading failure. It cannot ship before Story 1, but it carries most of the
value: it removes the separator, the spelling of `Heros`, and the exact reproduction of a folder
name like `Steve Rogers_Captain America`.

**Independent Test**: Choose a fixture library whose `Heros/` directory holds a known set of
folders, and assert the list offered is exactly those folder names, that selecting one starts a
run against that folder, and that the resulting run is identical to one that named the same
folder by hand.

**Acceptance Scenarios**:

1. **Given** a chosen library folder containing `Heros/` with hero folders inside, **When** the
   form loads the list, **Then** every immediate subfolder of `Heros/` is offered, named exactly
   as it is on disk, in a stable order.
2. **Given** the offered list, **When** the user selects one entry and starts the run, **Then**
   the run's hero folder is that entry beneath `Heros/`, expressed relative to the library root.
3. **Given** a chosen folder with no `Heros/` directory inside it, **When** the form tries to
   build the list, **Then** it says plainly that it found no `Heros` folder there — naming the
   folder it looked in — and offers a way to proceed anyway.
4. **Given** a `Heros/` directory that is present but empty, **When** the form builds the list,
   **Then** it says the folder holds no hero folders rather than showing an empty list with no
   explanation.
5. **Given** the list is long, **When** the user is looking for one hero, **Then** they can
   narrow it by typing part of the name without that text becoming the path.
6. **Given** files and hidden entries sitting alongside the hero folders, **When** the list is
   built, **Then** only real subfolders appear and nothing hidden does.

---

### User Story 3 - Come back to the library you used last time (Priority: P2)

The next time the user opens the wizard, the library folder they last ran against is already
filled in, with the hero list already built from it. They pick a hero and go.

**Why this priority**: Raised from P3 to ship alongside Stories 1 and 2, on the panel's
finding (ADR 0002). The reported friction is *per run* — a user printing four heroes in an
evening chooses the same library four times — and a remembered root is what turns the chooser
from a per-run action into a per-machine one. It is also nearly built: every run already
records its library root, and the wizard already writes both fields back into the form when
resuming a run.

**Independent Test**: Complete a run, reload the wizard, and assert the library root is
pre-filled and the hero list is populated without the user opening a chooser.

**Acceptance Scenarios**:

1. **Given** a previous run against a library folder, **When** the wizard is next opened,
   **Then** that folder is offered as the starting library root and can be replaced in one
   action.
2. **Given** a remembered folder that no longer exists or can no longer be read, **When** the
   wizard opens, **Then** it says so and asks the user to choose again rather than failing at
   run time.

---

### Edge Cases

- **`Heros/` under a different spelling or case.** The library the tool was built against spells
  it `Heros`. A user whose folder is `Heroes` — or `heros` on a case-sensitive volume — must be
  told what was looked for and where, not shown an empty list.
- **The user chooses the `Heros` folder itself, or a single hero's folder, as the library root.**
  Both are plausible mistakes given the label. The form must not silently produce an empty list;
  it should say what it found at that level.
- **A hero folder that is a symbolic link, or one that leaves the library root.** Selecting from
  a list must not become a way to name a folder outside the root the user chose — the
  containment rule that governs a typed path governs a picked one identically.
- **A very large library.** Building the list must not require reading card files; it needs
  folder names only.
- **A synced library that is not fully downloaded.** A cloud-synced folder can list names for
  files whose contents are not local. Listing hero folders must not force any download.
- **Two runs in two browser tabs.** Choosing a library in one must not change what the other is
  pointed at mid-run.
- **The chooser opens behind the browser window, or the user leaves it open.** The form must not
  be left in a state where it looks frozen with no way back.

## Requirements *(mandatory)*

### Functional Requirements

**Choosing the library folder**

- **FR-001**: The pack form MUST let the user set the library root by choosing a folder through
  a chooser, without typing or pasting a path.
- **FR-002**: The chosen library root MUST be displayed back to the user in full before the run
  starts, so the folder a run is about to read is visible at the point of choice.
- **FR-003**: Cancelling the chooser MUST leave the form exactly as it was, with no error and no
  change to any previously chosen folder.
- **FR-004**: A chosen folder that does not exist or cannot be read MUST be refused at the point
  of choice, naming the folder, rather than being carried into a run that fails later.
- **FR-005**: Choosing a different library root MUST clear any hero selection made under the
  previous one. A hero chosen under one root MUST NOT be able to travel to another.

**Offering the heroes**

- **FR-006**: Once a library root is set, the form MUST offer the immediate subfolders of
  `Heros/` beneath it as the choices for the run's hero folder.
- **FR-007**: The entries MUST be labelled with the folder names exactly as they appear on disk.
  No normalisation, re-spelling, or mapping to card-data names is performed.
- **FR-008**: The order of the entries MUST be stable and predictable across loads of the same
  library.
- **FR-009**: Only directories MUST be offered. Files, hidden entries, and system metadata
  entries MUST NOT appear.
- **FR-010**: Selecting an entry MUST set the run's hero folder to that entry beneath `Heros/`,
  expressed relative to the library root, matching what a correctly typed path produces today.
- **FR-011**: The user MUST be able to narrow a long list by typing part of a name. That text is
  a filter over the offered entries and MUST NOT be usable as a path.
- **FR-012**: When the chosen library root contains no `Heros` directory, the form MUST say so,
  naming the folder it looked in and the folder name it looked for, and MUST still let the user
  proceed by naming a hero folder themselves.
- **FR-013**: When `Heros/` exists but holds no subfolders, the form MUST say that rather than
  presenting an empty list.
- **FR-014**: Building the list MUST read folder names only. It MUST NOT open, decode, or
  download any card file, and MUST NOT depend on the run having started.

**Boundaries this does not move**

- **FR-015**: The library MUST NOT be written to, including by anything this feature adds. The
  chooser and the listing are read-only operations (002 FR-001).
- **FR-016**: A run's library root and hero folder MUST continue to be named per run. Neither is
  configured in advance, and this feature MUST NOT introduce an environment variable, setting, or
  default that supplies either one (002 FR-005, SC-003a).
- **FR-017**: The hero folder MUST continue to reach the run as a path relative to the library
  root, never an absolute one, and containment MUST continue to be enforced against the root the
  user chose (002 FR-007).
- **FR-018**: Nothing this feature adds may reach the network. Folder names come from the user's
  own disk (002 FR-002).
- **FR-019**: Enumeration MUST be confined to what the user's choice implies — the folder they
  chose and `Heros/` within it. This feature MUST NOT provide a general means of listing
  arbitrary locations on the machine.
- **FR-020**: Typing a path MUST remain possible as a fallback for the cases FR-012 covers. The
  picker becomes the default route, not the only one.
- **FR-021**: This feature changes the pack form only. The catalog-deck path (feature 001) and
  its configuration are untouched.

**The chooser itself**

- **FR-024**: Opening the chooser MUST NOT be able to wedge the service. One chooser may be
  outstanding at a time; a second request MUST be refused rather than queued, and a chooser
  nobody dismisses MUST be abandoned after a bounded wait.
- **FR-025**: The chooser MUST come to the front when it opens. A dialog the user cannot see is
  indistinguishable from a frozen page.
- **FR-026**: No stored or user-supplied string may be interpolated into the instructions that
  open the chooser. The remembered root of FR-022 is the case this exists for.
- **FR-027**: A folder the chooser returns MUST be probed for readability by the service
  immediately, before it is accepted (FR-004). The chooser can be granted access the service
  does not have.
- **FR-028**: Where no chooser is available, the wizard MUST fall back to the typed path
  (FR-020) and say why, rather than offering a button that does nothing.

**Remembering (Story 3)**

- **FR-022**: The wizard MUST offer the library root used by the most recent run as a starting
  point, replaceable in a single action.
- **FR-023**: A remembered root that no longer resolves MUST be reported when the wizard opens
  and MUST NOT be carried into a run.

### Key Entities

- **Library root**: The folder the user chooses. Unchanged in meaning from 002 — the containment
  boundary and the extent of the search. What changes is only how it is named.
- **Hero folder list**: The immediate subfolders of `Heros/` under the chosen library root,
  offered as labels identical to their names on disk. Derived at choosing time, never stored as
  part of the run.
- **Hero selection**: One entry from that list, which becomes the run's hero folder relative to
  the library root. Invalidated whenever the library root changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can start a pack run without typing or pasting any file path, in every case
  where the library has a `Heros` folder with hero folders in it.
- **SC-002**: Starting a run takes two pointing actions and one confirmation — choose the
  library, choose the hero, start — with no keyboard entry required.
- **SC-003**: Runs started through the picker and the list produce results identical to runs
  whose paths were typed correctly, for the same library and hero.
- **SC-004**: Every hero folder present under `Heros/` is offered, and nothing that is not a
  hero folder is offered.
- **SC-005**: The list appears within 2 seconds of the library folder being confirmed, for a
  library holding at least 60 hero folders.
- **SC-006**: A library folder with no `Heros` directory produces a message that names both the
  folder inspected and what was sought; it is never reported as "no heroes found" with no reason.
- **SC-007**: A wrong hero choice is no longer possible to make silently — the user selects from
  what exists, so "this folder matched no pack" can only mean identification failed, never that
  the folder name was mistyped.
- **SC-008**: A whole run started this way leaves the library's files, sizes, and modification
  times unchanged.
- **SC-009**: No path outside the chosen library root can be reached through the list.

## Decisions

- **OD-001 — How the folder chooser is presented. RESOLVED**, by panel and recorded in
  [ADR 0002](../../docs/adr/0002-the-service-opens-the-native-folder-dialog.md). The chooser is
  **the platform's own folder dialog, opened by the local service as a subprocess and gated to
  macOS**; the typed path (FR-020) remains the route everywhere else. An in-page folder browser
  over a directory-listing endpoint was considered and rejected: it cannot be built without
  repealing FR-019, and the enumeration capability it would add is permanent. The panel split
  2-2; the dissent is recorded in the ADR rather than paraphrased away.

  Two findings from that panel bind this spec:

  - **An in-process GUI toolkit is forbidden.** Called from a request thread it terminates the
    process with an uncatchable ObjC exception; called from the main thread it freezes the
    event loop for the dialog's lifetime. The dialog is a subprocess or it is nothing.
  - **The dialog must be verified to come to the front before implementation begins.** The
    platform documents `choose folder` opening behind other windows with no indication it
    appeared. This is the one unverified premise the decision rests on, and ADR 0002 names it
    as the trigger that reverses the decision.

## Assumptions

- **The layout is `<library root>/Heros/<hero folder>`**, as the current placeholder already
  states and as the user confirmed. This is used only to build a list; it is never used to infer
  a library root, and 002's rejection of that inference stands.
- **`Heros` is the literal folder name**, spelled that way. A differently spelled folder falls to
  FR-012 rather than being searched for under variants.
- **The user's machine is where the wizard and the service both run.** The application is
  loopback-only by design, so "the user's Finder" and "the service's filesystem" are the same
  machine. This feature does not work, and is not expected to work, against a remote library.
- **Hero folders are shallow.** Only the immediate children of `Heros/` are offered; no recursion.
- **Sorting is by name**, in a stable, locale-independent order. Nothing about pack identity,
  card counts, or previous runs re-orders the list.
- **The scan-supply and deck-list upload controls are unchanged.** Those hand over file bytes and
  are already the right shape; this feature adds a folder chooser beside them, it does not
  replace them.
- **Story 3's memory lives with the application's existing durable state**
  ([ADR 0001](../../docs/adr/0001-durable-run-state-on-the-filesystem.md)) and is a convenience
  only — it never supplies a library root to a run the user did not confirm (FR-016).

## Dependencies

- **The loopback service's Host and Origin hardening must land before this feature.** ADR 0002
  records that the service currently accepts any `Host` header and installs no middleware, and
  that a run request against an arbitrary absolute path returns both a directory-existence
  signal and path fragments discovered by walking that path. Neither is caused by this feature
  and neither is fixed by it, but this feature adds a second reason a hostile page would want
  to reach the service. It is a separate, smaller PR and it goes first.

## Out of Scope

- Normalised or prettified hero names, artwork, or card counts in the list. The user explicitly
  accepted raw folder names.
- Choosing villains, modular sets, or scenarios this way. The pack form is the only one that
  takes folder paths today.
- Any change to feature 001's catalog and image-directory configuration.
- Browsing or searching the library for anything other than the hero folder — the resolution
  cascade's whole-library search (002 FR-021) is untouched.
- Multi-select, or queueing several heroes into one run.
