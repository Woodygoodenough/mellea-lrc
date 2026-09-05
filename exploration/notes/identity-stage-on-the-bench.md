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
| confirmed identity | | 267 |
| wrong identity | a different case at the locator | 20 |
| wrong identity | a field the filing states disagrees | 16 |
| ambiguous identity | crowded page | 1 |
| defer to search | nothing at the locator | 83 |
| defer to search | undeterminable | 4 |
| defer to search | docket citation | 6 |

Of the 897 citations, 397 are roots and the other 500 inherit: 12 of those
inherit through a parallel citation the lookup folded into its neighbour, and
the rest through the citation tree extraction built. **One lookup per
authority is the whole cost.**

The 93 deferred to search are 49 Westlaw numbers, 3 LEXIS numbers, 8
specialty reporters and 23 printed reporters the archive holds nothing for, 4
roots a judgement could not settle, and 6 docket citations. Two runs of the
same code differ by one or two roots in the confirmed and field-disagreement
rows, which is the model's variance on the calls the rules leave it. That is open
search's population on this corpus, and it is dominated by vendor numbers, as
it was on LePhantomCite.

## 2. What the wrong identities are

Twenty are a locator whose record names a different case from the one the
filing describes -- `Cadle Co. v. Ayala` cited at a page that holds `Ramirez v.
City of New York`. Nineteen are plainly that. The twentieth, `Lacey v. Maricopa
County` at 693 F.3d 896, is the same case under the archive's caption `Michael
Lacey v. Joseph Arpaio`, and nothing in the record says so; it is the one
false wrong-identity left, and a docket fetch for the caption is what would settle
it.

The other 16 are the same case with a field the filing misstates: a court, a
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

The bench's 79 annotations are anchored to v1 text, so they were matched to
the stage's output by document and locator rather than by offset. 25 are
`misrepresented_authority`: the case exists and does not say what it is cited
for. Identity confirms 19 of them and does not see the other 6, which is
right -- that defect is the pinpoint stage's. The 54 `unverifiable_authority`
annotations are the ones identity should catch:

| what identity concluded | count |
|---|---:|
| wrong identity, a different case at the locator | 19 |
| defer to search, nothing at the locator, mostly Westlaw numbers | 27 |
| wrong identity, the filing names the wrong court | 5 |
| confirmed identity | 1 |
| defer to search, cited by docket number | 1 |
| no locator for extraction to read (`Kusulas v. GE/CO`) | 1 |

**No bench-labelled false citation is passed as clean but one**, and that one
is misclassified by the bench rather than missed by the stage. `In re
Soundview Elite Ltd., 503 B.R. 571 (Bankr. S.D.N.Y. 2014)` exists at that
locator on that date, and the court's correction points to a different
Soundview opinion, 543 B.R. 78 (2016), for the proposition. The rule is that a
locator identifying one case whose fields agree with the filing is a sound
identity, and whatever is wrong is in what it is cited for: a
misrepresentation, for the pinpoint stage, however plainly the proposition
belongs to another case. The five court-defect cases are `Hernandez v. Mario's
Auto Sales` and its kind: the case exists, the filing names the wrong court,
and the stage reports a wrong identity with the court as the disagreeing field. The audit
of every label the rule reads differently is untracked in the dataset
directory, `data/false-citation-bench/audit-identity-vs-misrepresentation.md`.

The 27 deferred to search are not caught either. They are the open-search population,
and the bench's label says what a search would find: nothing.
