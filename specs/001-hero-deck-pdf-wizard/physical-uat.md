# Physical UAT: print, cut, sleeve, decide

**Purpose**: get printed evidence for the three questions the spec cannot answer on screen.
Nothing here is automated — that is the point. The automated geometry checks
([quickstart.md](./quickstart.md) V4) already prove the PDF is correct; this document proves
the *paper* is.

**Print this file, or keep it open, and fill in the tables as you go.** The blank tables are
the deliverable — an unrecorded observation is the failure mode this document exists to
prevent (SC-002 fails on an untested assumption, not only on a bad result).

Covers tasks **T069, T070, T071, T072** and gathers the evidence for the open FR-011 /
FR-013 gutter decision.

## What you are trying to find out

| # | Question | Blocks | Session |
|---|---|---|---|
| 1 | Is my printer actually printing at 100%? | everything below | A |
| 2 | Which fit mode looks right on paper? | T071, T072 | B |
| 3 | How accurately can I actually cut? | the FR-011 gutter decision | C |
| 4 | Does a proxy fit a penny sleeve in front of a real card? | SC-002, FR-009 | D |

Do them in that order. Sessions B, C and D are all worthless if A fails, because every
measurement below assumes the sheet came out at true size.

## Before you start

**Materials**: ~6 sheets of your normal paper, the cutting tool you actually intend to use
for decks, a ruler with millimetre markings (steel preferred — plastic rulers are commonly
1–2% out), 3 penny sleeves, and 3 spare real Marvel Champions cards.

**Do not use a fresh cutting tool or your best ruler.** The point of Session C is to measure
*your real process*, not the best case.

```bash
uv sync --locked
export MARCHAMP_IMAGE_DIR="$HOME/path/to/card-images"
export MARCHAMP_CATALOG="$HOME/path/to/catalog.json"
uv run marchamp serve
```

**Printer settings, every time**: scale **100%**, page scaling **off** ("Actual size", never
"Fit to page" or "Shrink oversized pages"), correct paper size selected, and borderless mode
**off**. Best available quality. Record the exact settings — a result from unknown settings
is not a result.

---

## Session A — Prove the print scale (T070, SC-003)

Everything downstream is measured in millimetres off a printed sheet. If the printer is
silently scaling, every later number is wrong by the same factor and you will draw a
confident wrong conclusion.

```bash
curl -s -o calibration-letter.pdf "http://127.0.0.1:8765/api/calibration?page_size=LETTER"
```

Print it at 100%. Then measure, **with the sheet flat and the ruler on the paper**:

| Measure | Target | Measured | Pass? |
|---|---|---|---|
| Printed ruler, full stated length | as stated ±0.5 mm | | |
| Card outline, width | 63.5 mm ±0.5 | | |
| Card outline, height | 88.9 mm ±0.5 | | |
| Real card laid over outline — top edge | flush ±0.5 | | |
| Real card laid over outline — bottom edge | flush ±0.5 | | |
| Real card laid over outline — left edge | flush ±0.5 | | |
| Real card laid over outline — right edge | flush ±0.5 | | |

**If the ruler is out**: do not proceed. Find the setting causing it (almost always page
scaling), fix it, reprint. If you cannot make it measure true, record the scale factor —
that is a finding about consumer printers that belongs in the spec, and it makes the
calibration page more important, not less.

**If the outline is true but the real card does not match it**: that is a much more
interesting result — it means 63.5 × 88.9 mm is not actually the card's size. Record the
real card's measured dimensions, because FR-009's target would then be wrong.

> Measured print scale: ______ %  ·  Printer/model: ____________  ·  Settings: ____________

---

## Session B — Choose the fit mode (T071, T072, SC-009a)

You have already said you dislike `crop` from looking at the PDF. This session is to confirm
that on paper and, more importantly, to find out whether either alternative is actually
better — "I dislike crop" does not by itself make `fit` or `stretch` acceptable.

**What each mode actually costs.** These are computed from the real scan proportion (source
scans are 2.7% taller in proportion than a standard card), not estimated:

| Mode | What it does to the image | Exact cost |
|---|---|---|
| `crop` | Fills the slot, trims the overflow top and bottom | **1.20 mm of art destroyed off the top edge and 1.20 mm off the bottom** of every card |
| `fit` | Scales to fit inside, nothing lost | Face is 61.83 mm wide in a 63.5 mm slot — a **0.83 mm white strip down each side** |
| `stretch` | Scales each axis to fill the slot | Width squeezed by exactly **2.7%**, nothing lost, no white |

Worth knowing before you look: **2.7% is a small distortion.** "Stretch" sounds like the
disqualifying option and may well not be — on a 63.5 mm card the difference is under 2 mm of
apparent width, on artwork you have no undistorted copy of sitting beside it. Judge it on the
paper, not on the word. Equally, `crop`'s 1.2 mm is small in the abstract but lands exactly
on the card's border and title area, which is where it hurts.

Generate one page of each:

```bash
for MODE in CROP FIT STRETCH; do
  ID=$(curl -s -X POST http://127.0.0.1:8765/api/generations \
        -H 'content-type: application/json' \
        -d "{\"deck_id\":\"captain-america\",\"fit_mode\":\"$MODE\",\"page_size\":\"LETTER\"}" | jq -r .id)
  curl -s -o "deck-$MODE.pdf" "http://127.0.0.1:8765/api/generations/$ID/document"
  echo "$MODE -> deck-$MODE.pdf"
done
```

Print **page 1 only** of each, same printer, same settings, same session. Lay the three
sheets side by side under the same light.

| Check | `crop` | `fit` | `stretch` |
|---|---|---|---|
| Measured face width (mm) | *(63.5)* | *(61.8)* | *(63.5)* |
| Measured face height (mm) | *(88.9)* | *(88.9)* | *(88.9)* |
| Is anything important lost at the top/bottom edge? | | n/a | n/a |
| Is the white strip at the sides noticeable? | n/a | | n/a |
| Can you actually see the squash, without being told? | n/a | n/a | |
| At arm's length, does it read as a real card? | | | |
| Rank 1–3 | | | |

**The test that decides it**: cut one card from each sheet, sleeve each in front of a real
card, and lay the three sleeved cards in a row with a genuine card at the end. Look at them
as you would across a table mid-game, not up close.

> **Winner**: ____________  ·  **Why**: ______________________________________
>
> **Are the other two worth keeping?** ____________
> (The spec's Assumptions say this toggle exists to answer a question, not to persist. If one
> mode clearly wins, T072 makes it the default and the others become candidates for removal.)

**A fourth possibility to keep in mind.** If none of the three is acceptable, the problem is
not the fit mode — it is that the slot's proportion does not match the scans. The fix would
be changing the slot to the scans' own proportion, which FR-009a deliberately made a
one-place change. Record it as a finding rather than forcing a choice between three options
you dislike.

---

## Session C — Measure how accurately you cut (the gutter decision)

**This is the session that answers the open spec question**, and it does not exist in
quickstart.md yet, because until now the layout had no gutter to size.

Today every card shares its cut lines with its neighbours: one line separates two cards, so
a cut that wanders by 1 mm takes 1 mm off one card *and* leaves 1 mm of that card attached to
the other. A gutter turns each shared line into a band of white with slack in it. The
question is how wide that band has to be — and the honest answer is **whatever your actual
cutting error turns out to be**, which is why this is measured rather than argued about.

Take one printed sheet from Session B — ideally the winning mode — and cut all nine cards out
the way you normally would, at your normal pace. **Do not be careful.** Being careful
produces a number that does not describe how you will cut forty cards on a Tuesday evening.

Record which tool: ☐ scissors  ☐ craft knife + steel rule  ☐ rotary trimmer  ☐ guillotine

Now measure all nine cut cards:

| Card | Width (target 63.5) | Height (target 88.9) | Any sliver of a neighbour's art on any edge? | Worst edge error (mm) |
|---|---|---|---|---|
| 1 (top-left) | | | | |
| 2 (top-centre) | | | | |
| 3 (top-right) | | | | |
| 4 (mid-left) | | | | |
| 5 (mid-centre) | | | | |
| 6 (mid-right) | | | | |
| 7 (bottom-left) | | | | |
| 8 (bottom-centre) | | | | |
| 9 (bottom-right) | | | | |

> **Worst single edge error across all nine: ______ mm**
>
> **How many of the nine show a visible sliver of a neighbour: ______ / 9**
>
> **Is the error worse on the long cuts (full sheet width) than the short ones?** ______
> (Rotary trimmers and knives commonly drift over a long cut; this decides whether you need
> more slack between rows than between columns, which matters because Letter can only afford
> slack between columns.)

### What the number means

Read your worst-edge-error figure against this. The gutter has to be about **twice** the
worst error, so a cut that wanders either way still lands in white:

| Worst error | Gutter you need | Which layout options survive |
|---|---|---|
| ≤ 0.5 mm | ~1 mm | Everything, including a small gutter on both axes. Edge-to-edge is nearly fine already and this is a comfort change. |
| 0.5–2 mm | ~4 mm | Columns can have it on both page sizes. **Rows can only have it on A4** — Letter has just 12.7 mm of total vertical slack and a 4 mm row gutter would push the outer cards into the printer's non-printable zone and clip them. |
| > 2 mm | > 4 mm both axes | Only a **3×2 grid** delivers it, at 7 sheets per deck instead of 5. |

The measurement in Session A matters here too: if your printer has a large non-printable
margin, the vertical budget on Letter is even tighter than the 12.7 mm figure assumes.

> **Non-printable margin of your printer** (measure from the paper edge to where ink actually
> starts on the calibration sheet): top ____ mm · bottom ____ mm · left ____ mm · right ____ mm

That last measurement is worth taking properly. Letter's vertical margin is 6.35 mm today. If
your printer cannot print within 6.35 mm of the edge, **the current layout is already
clipping the top and bottom rows** and the gutter question is not the only problem.

---

## Session D — Sleeve fit across printers (SC-002, FR-009)

SC-002 explicitly fails on an untested assumption, and needs **at least 3 printer models**.
This is the one session you probably cannot finish in one sitting — a work printer, a
friend's, or a library printer all count.

For each printer: print page 1 of the winning fit mode, cut one card, sleeve it in front of a
real Marvel Champions card in a penny sleeve.

| Printer / model | Scale verified? | Seats without forcing? | Bends or buckles? | Notes |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

**The known risk**: the proxy is printed at exactly the same size as the card behind it, so
the sleeve has to take two full-size cards. The spec chose this deliberately — ship at 100%,
print, and adjust from evidence rather than guessing a reduction up front.

> **Outcome** — tick one:
>
> ☐ Seats fine at 100%. FR-009 stands as written, no change.
>
> ☐ Too tight. Required size reduction: ______ mm on width, ______ mm on height.
> (FR-009a keeps this to a one-place change in `SLOT_SIZE_MM`. Note that reducing the
> *height* also frees vertical slack, which directly loosens the Session C gutter
> constraint — these two findings interact, so report both together.)

---

## What to bring back

Five answers unblock the spec work. Everything else is detail:

1. **Did the calibration page measure true?** (If no, nothing else counts yet.)
2. **Which fit mode won, and do the losers get removed?** → T071, T072
3. **Worst cut error in millimetres, and whether long cuts are worse.** → sizes the gutter
4. **Your printer's real non-printable margin.** → says whether Letter can afford a row gutter
5. **Did the sleeve fit at 100%?** → confirms or changes FR-009, and may free vertical space

With 3 and 4 in hand the FR-011 / FR-013 gutter decision stops being a judgement call between
options and becomes arithmetic.

## Recording the results

Fill the tables above in place and commit this file — the spec's own success criteria require
the outcome to be *recorded*, not merely observed. Then:

- T070 → the Session A table
- T071 → the Session B table and its winner
- T072 → change the default in `src/marchamp/config.py`, and record in
  [spec.md](./spec.md) whether the other modes are kept or removed
- T069 → run the rest of [quickstart.md](./quickstart.md) against the same real catalog
- The gutter decision → re-run `/speckit-clarify` on this feature with Sessions C and D in
  hand
