# Physical UAT — print one pack and build the deck from paper

*Discharges: SC-001, SC-002a, SC-002b, FR-013b, FR-015d, FR-015e, SC-006j. Expands
[`quickstart.md`](quickstart.md) V12.*

Everything else in this feature is verified by a test. This is the part that is not, and it is
not a formality: the tool's entire claim is that a person can print a pack, cut it, sort it,
build the starter deck from the printed decklist card, and play a game without owning the
product. Nothing about that claim is visible in a PDF's bytes.

Run it once per release that touches layout, pagination, grouping, or the decklist card.

---

## Before you start

You need the mounted scan library, a colour printer, a guillotine or a craft knife and a
straight edge, and about forty minutes — most of it cutting.

```bash
MARCHAMP_REAL_LIBRARY="/Volumes/GoogleDrive/My Drive/Marvel Champions Scans" \
MARCHAMP_UAT_OUTPUT="$HOME/Desktop/marchamp-uat" \
    uv run pytest -m physical tests/integration/test_physical_pack.py -s
```

That drives Captain America against the real library, writes `cap.pdf` and
`cap-measurements.json` into the output directory, and asserts the two things a machine can
check: the page count is the fewest the card count allows (SC-002b), and all four groups are
present (SC-002a). It prints the measurements you will need below.

Captain America rather than any other hero because its folder omits eight physical cards that
were already in the Core Set. Those cards are recovered by the reprint cascade, and this is
the only procedure that confirms they came out as cards a person can hold rather than as rows
in a report (FR-014, SC-005).

Keep the run's report open in the wizard while you work. Step 3 depends on it.

---

## The procedure

### 1. Print

Print `cap.pdf` at **100% scale — no fitting, no shrinking, no "fit to printable area"**. Every
scaling option a print dialog offers is wrong here; the card size is the point and a 96%
reduction produces cards that look right and do not match a real one.

- [ ] Printed at 100% scale on the printer's best photo setting
- [ ] Paper: __________________________  Printer: __________________________

### 2. Cut

Cut on the crop marks.

- [ ] Every card cut
- [ ] **Measure three cards from different pages with a ruler: 63.5 × 88.9 mm.** If they are
      short by a few millimetres the print dialog scaled after all — go back to step 1 rather
      than adjusting anything in the tool.
- [ ] Cards from the *first* page and the *last* page measure the same

### 3. Sort, using the report alone

Put the report where you can read it and the cards where you cannot see the PDF. Sort the pile
into four: player cards, the identity card, the nemesis set, the decklist card.

This is the step that fails informatively. FR-015d packs the groups together with **no page
break**, so a sheet carrying the last few player cards and the first nemesis cards is correct
— and it means the report is the only thing that tells them apart (FR-015e). If you find
yourself guessing from the card art, the report is not doing its job, and that is a finding
whatever the tests say.

- [ ] Sorted into four piles from the report alone, without guessing
- [ ] The identity card has every face its report entry lists (two for Captain America)
- [ ] The nemesis pile matches the report's `nemesis` entries exactly
- [ ] Every card in the pile appears in the report; every report entry is in the pile

### 4. Build the starter deck from the printed decklist card

Read the decklist card. Build the deck from it.

**Do not ask the tool what belongs in the deck.** It does not know and must not claim to:
deriving deck membership was attempted, measured, and found to produce a silently wrong deck,
which is why FR-013a puts this step on paper. The decklist card is a photograph of the
official list, and reading it is the whole mechanism.

- [ ] Built the starter deck by reading the printed decklist card
- [ ] Every card the decklist names was in the printed pack
- [ ] Card count built: ______   (There is no expected total. Pre-built decks measured 40, 41
      and 42, and FR-018 forbids warning on any total — if you find yourself wanting to check
      this against 40, that is the bug the requirement exists to prevent.)

### 5. Play

One game against a villain, with the deck you built.

- [ ] Played a full game
- [ ] No card was unreadable, mis-cut, or ambiguous in play
- [ ] Sleeved alongside real cards without being identifiable by feel or thickness (optional,
      but it is the sharpest test of step 1)

---

## The hero with no decklist scan

25 of 60 hero folders hold no decklist scan, and Hulk is one of them — inside the SC-002 set
that must print with **no manual intervention**. Run it too; it is one extra run and it covers
the other half of FR-013c.

Point the wizard at `Heros/Bruce Banner_Hulk`.

- [ ] The run names the missing decklist specifically, rather than reporting the pack as
      complete (SC-006j)
- [ ] It offers the Hall of Heroes address
- [ ] **It does not fetch it.** The application never retrieves the image; you do (FR-013c)
- [ ] The pack still prints without one, and the report says it printed without one
- [ ] Downloading the decklist image from Hall of Heroes and supplying it through the upload
      path prints it as the last card

---

## Measurements

Copy these from `cap-measurements.json`. Recorded, not asserted — see the note in
`test_physical_pack.py` on why there is no threshold here.

| Measurement | Value | Note |
|---|---|---|
| Cards printed / in pack | ____ / ____ | Must be equal |
| Faces printed | ____ | Higher than the card count; double-sided cards are one card, two faces |
| Page count | ____ | Asserted by the test as the fewest the face count allows (SC-002b) |
| PDF size | ____ MB | For comparison with 001's measured 202 MB |
| Wall clock, folder named → PDF in hand | ____ s | The machine's share of SC-001 |
| **Total user time, start to printable PDF** | ____ min | **SC-001's criterion: under five minutes** |

The last row is the one that is a criterion, and it is the one only a person can measure.
Start the clock when you open the wizard and stop it when the PDF is on disk — including
reading the report and confirming the decklist, and excluding printing and cutting.

001's SC-007 and SC-007a are knowingly missed (48.9 s and 202 MB against a 30 s target),
measured, reviewed and accepted because the tool is local-only. This feature does not reopen
them. If the numbers above are in that neighbourhood, that is the expected outcome and not a
finding.

---

## Result

- Date: ____________  Tester: ____________  Commit: ____________
- Outcome: ☐ pass  ☐ pass with notes  ☐ fail
- Notes:
