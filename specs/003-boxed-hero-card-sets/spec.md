# Feature Specification: Print a hero that ships inside a box

**Feature Branch**: `003-boxed-hero-card-sets`

**Created**: 2026-08-20

**Status**: Draft

**Input**: Reported from real use, 2026-08-19. A user pointed the tool at `Heros/Clint Barton_Hawkeye` and was told the folder matched no pack, with a list of alternatives none of which was Hawkeye.

## Why this exists

Feature 002 prints **a pack**. That works because most heroes ship in a hero pack named after
them, so a folder called `Steve Rogers_Captain America` matches the pack `Captain America` and
the pack's contents are exactly that hero's cards.

A large minority of heroes do not ship that way. Hawkeye is in **The Rise of Red Skull**, a
176-record box he shares with Spider-Woman, five villains and several encounter sets. The
Core Set is a 205-record box holding **five** heroes. For these, both halves of 002's design
fail at once:

- **Identification cannot succeed.** It compares the folder's name to the 61 pack *names*, and
  no pack is called Hawkeye. The run is refused and offered alternatives, which is 002 working
  correctly on a question it cannot answer.
- **Selecting the box by hand is worse than the refusal.** It would print all 176 records —
  two heroes, five villains, the encounter sets — when the user asked for one hero.

The data to fix this is already in every card record and is currently discarded. MarvelCDB
carries `card_set_name`, and inside The Rise of Red Skull its values include `Hawkeye`,
`Hawkeye Nemesis`, `Spider-Woman`, `Crossbones` and `Red Skull`. Feature 002 reduces each
record to eleven fields and this is not one of them.

**The same field fixes a second, independent bug.** A hero pack that ships a modular encounter
set has nowhere to put it. In a real Wolverine run, `Lady Deathstrike` (minion),
`Seeking Vengeance` (side scheme), `Adamantium Upgrades` (attachment) and `Hack 'n' Slash`
(treachery) were all reported under **"Player cards (32)"**. All four carry
`card_set_name: "Deathstrike"` and are an encounter set. Since the report is what the user
sorts their cut cards by, today it tells them to put four encounter cards in their deck.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print a hero who has no pack of his own (Priority: P1)

A user names `Heros/Clint Barton_Hawkeye`. The tool works out that this is the `Hawkeye` card
set inside The Rise of Red Skull, tells them so along with what it is basing that on, and —
once they confirm — prints Hawkeye's cards and nothing else. Spider-Woman, Crossbones and the
Hydra encounter sets, all sitting in the same box, do not appear.

**Why this priority**: It is the reported failure and the whole reason for the feature. Every
hero who ships in a box is unprintable today, and the tool's answer — "this folder matches no
pack" — sends the user off to check filenames that were never wrong.

**Independent Test**: Point a run at a boxed hero's folder against the fixture library and
assert it prints that hero's cards and no other card set from the same box. Delivers the
whole of the reported value on its own.

**Acceptance Scenarios**:

1. **Given** a folder for a hero who ships inside a box, **When** a run is started, **Then**
   the run identifies the hero's card set and names both the set and the box it is in.
2. **Given** that identification, **When** the user confirms it, **Then** the printed document
   carries that hero's cards and no card belonging to another card set in the same box.
3. **Given** a folder for a hero who ships in a hero pack of his own, **When** a run is
   started, **Then** it behaves exactly as it does today — a hero pack is a box with one hero
   in it, and nothing about that case may regress.
4. **Given** a boxed hero, **When** the report is produced, **Then** it reports the card count
   of the *hero's card set*, never the box's.

---

### User Story 2 - Sort a modular encounter set into its own pile (Priority: P1)

A user prints Wolverine, whose pack ships the Deathstrike modular encounter set. The report
lists those cards as their own group, named, so that when the user sorts the cut cards they
put the encounter cards where encounter cards go.

**Why this priority**: Also P1, and not because it is part of the same change. It is a
correctness bug in shipped output: the report currently tells the user to put four encounter
cards into their player deck, and a player who follows it builds an illegal deck. It is
smaller than User Story 1 and can ship first.

**Independent Test**: Run any hero whose pack carries a modular set and assert those cards
appear under their own named group rather than among the player cards.

**Acceptance Scenarios**:

1. **Given** a pack that ships a modular encounter set, **When** the run reports, **Then**
   that set's cards appear under their own group carrying the set's name.
2. **Given** the same run, **When** the report is read, **Then** none of those cards appears
   among the player cards.
3. **Given** a pack that ships no modular set, **When** the run reports, **Then** no empty
   group appears.

---

### User Story 3 - Choose a different card set when the tool guesses wrong (Priority: P2)

A user's folder is ambiguous, or the tool picks the wrong card set from a box. They are shown
the sets that box holds and can choose the right one, exactly as they can choose a different
pack today.

**Why this priority**: The escape hatch. FR-012b already establishes that a refusal is a
prompt rather than a dead end, and this extends the same promise one level down. It is P2
because User Story 1 has to work first for there to be anything to correct.

**Independent Test**: Start a run, select a card set other than the identified one, and assert
the run resolves and prints that set.

**Acceptance Scenarios**:

1. **Given** a run that has identified a card set, **When** the user asks for the alternatives,
   **Then** they are offered the card sets of the box, not the 61 packs.
2. **Given** that list, **When** the user selects a different set, **Then** the run resolves
   against it and the report records that the user chose it rather than the tool.
3. **Given** a box holding several heroes, **When** the user names the box rather than a hero,
   **Then** they are asked which card set to print rather than being given the whole box.

---

### Edge Cases

- **A card in a box belongs to no card set.** Measured in Wolverine's own pack: `Command
  Center` and `Longshot` carry `card_set_name: null` while every other card carries one. These
  are the pack's aspect and basic cards, which belong to the hero for printing purposes but
  are not part of a named set. A design that keys printing solely off `card_set_name` drops
  them, and dropping a card silently is the one outcome FR-006 forbids.
- **Two card sets in one box share a hero's name.** `Hawkeye` and `Hawkeye Nemesis` both begin
  with the same word. Ranking a folder called `Clint Barton_Hawkeye` must not match the nemesis
  set instead of the hero.
- **The Core Set.** Five heroes in 205 records, and it is also the pack most other packs borrow
  reprints from. It is the largest case and the most likely to be pointed at by accident.
- **A hero folder holds cards from another hero in the same box.** Scanners file by folder, and
  a box arrives as one pile.
- **A box whose sets are not yet known.** Card set names live in the card records, so they
  cannot be ranked against until that pack has been retrieved at least once.
- **A card set name that is not a hero at all** — `Hydra Patrol`, `Expert Campaign`. These must
  be offerable when the user asks for them and must never be identified *as* a hero folder.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-101**: The application MUST retain each card's card set name from the upstream record.
  This is the enabling change and it widens the reduction FR-038a specifies; the field is a
  name like `Hawkeye` or `Deathstrike`, and carries no card text, artwork reference or rules.
- **FR-102**: The application MUST be able to identify a hero folder as a **card set within a
  pack**, not only as a pack.
- **FR-103**: A run MUST print exactly one card set's cards, together with the cards of that
  box that belong to no set and are attributable to it (see FR-107). It MUST NOT print cards
  belonging to another named set in the same box.
- **FR-104**: A run over a hero who ships in a hero pack of his own MUST produce byte-identical
  output to what feature 002 produces today. A hero pack is the degenerate case of a box, and
  this feature MUST NOT change it.
- **FR-105**: The report MUST state which card set was printed and which pack it came from.
  "Hawkeye" alone does not tell the user the box they need to own.
- **FR-106**: Card counts in the report MUST be counts of the printed card set, never of the
  containing pack. A Hawkeye run reporting 176 cards in the pack would be true of the box and
  useless about the deck.
- **FR-107**: Cards in a pack carrying no card set name MUST be attributed to a printed set
  rather than dropped, and the report MUST make clear they were included.
  TODO(clarify): in a *hero pack* these are the hero's own aspect and basic cards and clearly
  belong to it. In a multi-hero box the same cards may be shared between heroes, and it is not
  established from data whether they should print with every hero, with none, or be offered as
  a choice.
- **FR-108**: Modular encounter sets MUST be reported as their own group, named by the set,
  and MUST NOT be reported as player cards.
- **FR-109**: The print order MUST place a modular encounter set after the nemesis set and
  before the deck list card, so that the order still runs from what the player uses most to
  what they use least.
- **FR-110**: When identification cannot choose a card set confidently, the run MUST be refused
  and offered the candidate sets, in the same shape FR-012b already requires for packs.
- **FR-111**: The user MUST be able to select a card set other than the identified one, and the
  report MUST distinguish an identified set from a user-selected one.
- **FR-112**: Identifying a card set MUST NOT increase the request count in proportion to the
  number of packs. The budget FR-040 and SC-006d establish — single digits for a whole run —
  MUST continue to hold.
  TODO(clarify): card set names are only knowable from a pack's card records, so ranking a
  folder against every set in the catalogue would mean holding every pack. Whether this is
  solved by ranking packs first and sets second, by learning sets lazily from packs already on
  disk, or by another route is a design question for the plan.
- **FR-113**: Everything feature 002 refuses to do, this feature MUST also refuse. The library
  is never written to; card images come only from the user's library or their own uploads and
  are never fetched; the egress allowlist remains one host and the three JSON endpoints; the
  tool prints card sets and never derives deck membership.

### Key Entities

- **Card set**: A named group of cards within a pack — a hero and his signature cards, a
  nemesis set, a modular encounter set, a villain. The unit a user actually wants to print.
  Identified by its name, which is unique within its pack but not across the catalogue.
- **Pack**: What FFG ships in one box. Holds one card set for a hero pack, and many for a
  campaign or expansion box. Remains the unit of retrieval and of snapshot pinning.
- **Unattributed card**: A card in a pack carrying no card set name. Measured in Wolverine's
  pack as the aspect and basic cards.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-101**: Hawkeye prints from a folder named after him, with no card from Spider-Woman,
  Crossbones, Red Skull or any Hydra encounter set in the document.
- **SC-102**: All five Core Set heroes print individually from their own folders, each
  document carrying only that hero's cards.
- **SC-103**: The ten acceptance heroes of feature 002 produce byte-identical documents to
  those they produce today. This is the regression bar for the whole feature and it is
  absolute: a change that improves boxed heroes at the cost of hero packs is not shippable.
- **SC-104**: 100% of cards in a printed document belong to the card set the run reports, or
  are unattributed cards the report names. No card appears that the report does not account
  for.
- **SC-105**: Every modular encounter set is reported under its own name, and 0% of its cards
  appear among the player cards. Verified against a hero whose pack ships one.
- **SC-106**: A run for a boxed hero issues no more requests than a run for a hero pack of
  comparable size, measured as it is for SC-006d.
- **SC-107**: A user who is shown the wrong card set can reach the right one without restarting
  the run or editing anything on disk.

## Assumptions

- **Card set names are stable enough to match against.** They are display names maintained by
  a volunteer-run database, so they may be renamed. Matching them is a name comparison and
  inherits the tolerance FR-023 already established for card names.
- **A hero pack is a box with one hero in it.** The feature unifies the two rather than adding
  a parallel path, which is what makes FR-104 and SC-103 achievable rather than aspirational.
- **The user owns the box.** The tool prints proxies of cards from a product the user owns;
  this feature does not change that and printing one hero out of a box does not imply
  otherwise.
- **Existing committed snapshot fixtures do not carry card set names.** They were reduced to
  the eleven fields feature 002 retains, so they must be regenerated before any of this can be
  tested. This is real work and belongs in the plan.
- **Deck list cards behave as they do today.** A boxed hero's deck list scan, where one exists,
  is found in the hero's folder by the mechanism FR-013b already specifies.
- **The physical card count of a pack remains unknowable.** Established while investigating
  this report: MarvelCDB's own `total` field takes only the values 56 and 60 and disagrees with
  its summed per-card quantities by between −2 and +4 across the twelve packs measured, while
  FFG markets several packs as "60 cards" that sum to 58 or 59. FR-018 already forbids
  expecting or warning about a total, and nothing here changes that.
