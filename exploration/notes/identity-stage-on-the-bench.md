# The identity stage over false-citation-bench v2.0

What the stage concludes on 26 real filings, and what each run taught. The
numbers are from `evaluations/identity/run_extraction_artifacts.py` over the
extraction run in `data/runs/extraction-v2.0`, which is 897 citations the
deterministic extractor read with `Relaxation.FULL`. Every CourtListener
response was served from the proxy's cache, so the runs spent no request
allowance; the model was `openai/gpt-5.6-luna`.

## 1. The result

| | count |
|---|---:|
| citations | 897 |
| roots, one lookup each | 397 |
| roots decided by rule alone | 353 |
| model calls | 47 |
| parallel citations merged into one authority | 8 |

| outcome | reason | roots |
|---|---|---:|
| confirmed identity | | 268 |
| wrong identity | a different case at the locator | 23 |
| wrong identity | a field the filing states disagrees | 15 |
| ambiguous identity | crowded page | 1 |
| defer to search | nothing at the locator | 83 |
| defer to search | undeterminable | 1 |
| defer to search | docket citation | 6 |

Of the 897 citations, 397 are roots and the other 500 inherit: 12 of those
inherit through a parallel citation the lookup folded into its neighbour, and
the rest through the citation tree extraction built. **One lookup per
authority is the whole cost.**

The 90 deferred to search are 49 Westlaw numbers, 3 LEXIS numbers, 8
specialty reporters and 23 printed reporters the archive holds nothing for, 1
root a judgement could not settle, and 6 docket citations. Two runs of the
same code differ by one or two roots in the confirmed and field-disagreement
rows, which is the model's variance on the calls the rules leave it. That is open
search's population on this corpus, and it is dominated by vendor numbers, as
it was on LePhantomCite.

## 2. What the wrong identities are

Twenty-three are a locator whose record names a different case from the one the
filing describes -- `Cadle Co. v. Ayala` cited at a page that holds `Ramirez v.
City of New York`. Twenty-two are plainly that. The other, `Lacey v. Maricopa
County` at 693 F.3d 896, is the same case under the archive's caption `Michael
Lacey v. Joseph Arpaio`, and nothing in the record says so; it is the one
false wrong-identity left, and a docket fetch for the caption is what would settle
it.

The other 15 are the same case with a field the filing misstates: a court, a
year, or a party misspelt or dropped. Both kinds are
`wrong_identity`; the reason and the fields under the node keep them apart,
and the second kind still resolves the record, since the case was found.
`Hernandez v. Mario's Auto Sales` at 617 F. Supp. 2d 488 is that case whatever
district the filing wrote, and the node says which field is wrong rather than
calling the citation a fabrication.

## 3. What five runs changed

The first run made 71 model calls and called 35 roots a different case.
Reading those by hand found three kinds of mistake, none of them the model's
alone.

**The rules compared one way.** `Monell v. Department of Social Services`
against the archive's `Monell v. New York City Dept. of Social Servs.` was a
mismatch, because the abbreviation test only let the filing be the short side.
The archive abbreviates as readily as a filing does, and the test now runs
both ways.

**Contractions never fired.** Apostrophes were replaced with spaces before the
contraction table was consulted, so `Ass'n` arrived as `ass` and `n`. Removing
them instead, and adding the contractions the bench wrote (`P'ship`, `Eng'rs`,
`Commc'ns`, `Mfg.`, `Mtge.`, `Grp.`, `Bldg.`, `Prof'l`, `Gov't`, `Fed'n`), took
the name-only model calls from 47 to 23. A written word set in capitals is now
also the record's initials, so `FDIC`, `ICC`, `CFTC` and `LAPD` settle by rule.

**Identity is the case, not its fields.** The model called a court or year
disagreement on an agreeing name a different case, eleven times. The verdict
requirement now refuses `different_case` unless the case name disagrees, and a
misspelt party is a `variant`: the same case, reported as a defect. Refutations
went from 35 to 20, and every one left names a different case at the page.

Two more came from reading traces. On a page of two cases, the model was asked
about the first before the rules had looked at the second, which matched
exactly; the rules now run on every candidate first, and a model is asked only
when none settled. And the merge that treats one date as one decision folded
`Lewis v. Clarke` into `Williams v. Kelley` on a Supreme Court orders page,
which holds many cases with one date; records sharing a date now stay apart
when both are named and share no word.

## 4. What the judgement reads, and with what evidence

Every field the model reads comes with the string it read it from, checked
against the window the field must come from: the text before the locator for
the name, the parenthetical after it for the court and date. Over the 47
judgements, all 47 grounded every field they read; 43 did so on the first
answer and 4 after one repair turn, each time for a reading outside its
window; none exhausted the budget. The court was read from a stated
parenthetical 33 times, implied by a Supreme Court reporter 6 times, and left
null 8 times where a regional reporter implies a family of courts and the
parenthetical states none.

A court the filing does not state is not compared against nothing. The
reporter holds only some courts, and the record's court is checked against
that family: 44 roots on this bench state no court, and every one's record is
from a court its reporter holds. The check found no conflict here; what it
found was the one gap in the mapping, the Northern Mariana Islands district
that courts-db names `nmid`, which is now looked up by place.

Thirteen corrections to the filing's reading followed, each attributed to the
model and pointing at the judgement node and its evidence: nine plaintiffs,
three defendants and one court. `Under Norton` became `Norton`, `Justice`
became `Sikhs for Justice`, `Rudy-Glanzer` became `Doe ex rel. Rudy-Glanzer`,
each a name extraction cut short and the model read whole from the name
window. The one court, `dcd`, was read from `D.D.C.` in the parenthetical. The
extracted citation stays beside each, unchanged.

## 5. Against the bench's own labels

`data/validation-v2.0/annotations.json` labels 49 authorities `WRONG_IDENTITY`
and 19 `WRONG_PINCITE`, by the same classification rule the stage applies.
Matched by document and locator span:

| what identity concluded, over the 49 | count |
|---|---:|
| wrong identity, a different case at the locator | 21 |
| wrong identity, the filing misstates the court | 5 |
| defer to search, the archive holds nothing at the locator | 21 |
| no authority to check: a docket number, or a name with no locator | 2 |

**Where the archive holds the page, every one of the 49 is caught**, and none
is confirmed. The 21 deferred are 16 Westlaw or LEXIS numbers and 5 printed
locators at which no opinion starts in the archive; the sanctioning courts
found them through Westlaw. Two labelled entries needed the refutation rule
corrected to be reached: a page the archive holds twice, and a page holding
two cases both judged different. The rule is now that a refutation needs
every case the archive holds at the page to have been examined and judged a
different case, and a page narrowed by the filing's own name still defers.

The stage also reports 12 wrong identities the labels do not carry: ten
defects the sanctioning courts did not mention, a parallel citation of a
labelled entry, and one false alarm, `Lacey v. Maricopa County`, which the
archive captions by the sheriff's name. The per-entry reading is untracked in
the dataset directory, `data/validation-v2.0/audit-identity-stage-vs-labels.md`.
