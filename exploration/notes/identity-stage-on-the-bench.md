# The identity stage over false-citation-bench v2.0

What the stage concludes on 26 real filings, and what each run taught. The
numbers are from `evaluations/identity/run_extraction_artifacts.py` over the
extraction run in `data/extraction-v2.0`, which is 897 citations the
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

| outcome | roots |
|---|---:|
| established | 267 |
| established with defects | 14 |
| refuted | 20 |
| unresolved | 89 |
| deferred (docket) | 6 |
| ambiguous | 1 |

Of the 897 citations, 397 are roots and the other 500 inherit: 12 of those
inherit through a parallel citation the lookup folded into its neighbour, and
the rest through the citation tree extraction built. **One lookup per
authority is the whole cost.**

The 89 unresolved are 49 Westlaw numbers, 3 LEXIS numbers, 8 specialty
reporters and 24 printed reporters the archive holds nothing for, plus 6 roots
a judgement could not settle. That is open search's population on this corpus,
and it is dominated by vendor numbers, as it was on LePhantomCite.

## 2. What the refutations are

All 20 are a locator whose record names a different case from the one the
filing describes -- `Cadle Co. v. Ayala` cited at a page that holds `Ramirez v.
City of New York`. Nineteen are plainly that. The twentieth, `Lacey v. Maricopa
County` at 693 F.3d 896, is the same case under the archive's caption `Michael
Lacey v. Joseph Arpaio`, and nothing in the record says so; it is the one
false refutation left, and a docket fetch for the caption is what would settle
it.

The 14 established with defects are the same case with a field the filing
misstates: a court in 8, a year in 4, a party misspelt or dropped in 2.
`Hernandez v. Mario's Auto Sales` at 617 F. Supp. 2d 488 is that case whatever
district the filing wrote, and the stage now says so rather than calling it a
fabrication.

## 3. What five runs changed

The first run made 71 model calls and refuted 35 roots. Reading the
refutations by hand found three kinds of mistake, none of them the model's
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

## 4. What the corrections were

Thirteen corrections to the filing's reading, each attributed to the model
and pointing at the judgement node that made it: five plaintiffs, two
defendants and six courts. `Under Norton` became `Norton`; a defendant that
extraction read as `S.D.N.Y. May 12, 2020) ….6 |` from a table of authorities
became `Townes`; six courts the parenthetical did not state were read from the
reporter. The extracted citation stays beside each, unchanged.

## 5. Against the bench's own labels

The bench's 79 annotations are anchored to v1 text, so they were matched to
the stage's output by document and locator rather than by offset. 25 are
`misrepresented_authority`: the case exists and does not say what it is cited
for. Identity establishes 19 of them and does not see the other 6, which is
right -- that defect is the pinpoint stage's. The 54 `unverifiable_authority`
annotations are the ones identity should catch:

| what identity concluded | count |
|---|---:|
| refuted: the page holds a different case | 19 |
| unresolved: the archive holds nothing there, mostly Westlaw numbers | 27 |
| established with a court defect: the case exists, the filing names the wrong court | 5 |
| established | 1 |
| deferred: cited by docket number | 1 |
| no locator for extraction to read (`Kusulas v. GE/CO`) | 1 |

**No bench-labelled false citation is passed as clean but one**, and that one
is `In re Soundview Elite Ltd., 503 B.R. 571 (Bankr. S.D.N.Y. 2014)`, which
exists at that locator on that date. The court's correction points to a
different Soundview opinion, 543 B.R. 78 (2016), for the proposition, so the
defect is in what the citation is cited for, not in whether the case exists.
The five court-defect cases are `Hernandez v. Mario's Auto Sales` and its
kind: the bench calls them unverifiable because the citation as written names
a court that never decided them, and the stage reports that court as a defect
on an established identity, which is the more useful reading. Whether the
paper counts them as caught depends on which question it asks.

The 27 unresolved are not caught either. They are the open-search population,
and the bench's label says what a search would find: nothing.
