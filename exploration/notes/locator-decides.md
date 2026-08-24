# The locator decides what is cited

23 August 2026. Written after a draft of this note went wrong, and the record
of how is the useful part.

## 1. There is no referent to adjudicate

A citation is an address plus a description of what is at it. `Anderson v.
Liberty Lobby, Inc., 447 U.S. 242, 106 S. Ct. 2505, 91 L. Ed. 2d 202 (1986)`
addresses page 242 of volume 447 of the United States Reports, and describes
what is there as *Anderson*, decided in 1986, also printed in two other
reporters.

**The address decides which document is cited.** The description does not get a
vote. That is what an address is for.

The earlier draft of this note proposed weighing the fields against each other
and calling the referent whichever document the most of them agreed on --
"the reading that leaves the fewest fields wrong". That is wrong twice over.
It invents an intent question where there is an address, and it answers it by
counting, on a corpus with no measured distribution to calibrate the count
against.

It also produces a worse output. Under field-counting, `447 U.S. 242` reports
as *Anderson with a wrong volume*, which is a guess about what the drafter
meant to type. Under the address rule it reports as **`447 U.S. 242` is not
*Anderson v. Liberty Lobby***, which is an observation, is checkable by the
reader, and is what a reader needs in order to act.

## 2. So the decision is a lookup, and then a comparison

```
does the locator resolve?
│
├── no ──> nothing is cited; every other check has no input
│
└── yes ─> this document is what is cited
           └── each remaining field either agrees with it or does not
```

The locator is decisive on its own, and that is the whole of the first stage.
Name, court, year, pin cite and parallel citations are then compared against
one known document rather than against each other.

Nothing above needs a taxonomy to state, and no part of it was derived from
anyone's label set.

## 3. Two asymmetries that are observed rather than designed

**The locator can refute and cannot confirm.** CourtListener normalises a page
that falls mid-case to the case covering it and reports the citation sound --
17 of 24 measured. So a "found" answer is not evidence the page is right,
while a page sitting inside another case is evidence that it is wrong.

**A name can confirm and cannot refute.** Absence of a case name from a corpus
is a fact about the corpus. 68 of 90 unresolved citations in this project are
real cases published only in Westlaw and LEXIS.

These two are the reason "does not resolve" is not the same claim as "does not
exist", and the gap between them cannot be closed by choosing better words for
it. It closes when a search can state what it covers, and no search here can.

## 4. One class that needs no lookup at all

A locator can name a namespace that was never published: `531 N.E.4th 224`,
`423 F.5th 938`, `671 F. Supp. 4th 395`. No document can sit at an address in a
reporter series that does not exist, and no corpus needs consulting to know it.

**126 of `aux_train`'s labels are this shape** -- the largest single class in
the file, the most certain, and the cheapest. They are currently invisible
because eyecite does not type an unknown series as a citation at all, so
nothing downstream ever sees them. Reaching them is a rule about the reporter
table.

The same rule catches an impossible combination of real fields: `F.2d` ended in
1993, so `739 F.2d 131 (4th Cir. 2014)` is refuted by arithmetic.
`unrecorded-defects.md` §3 has three of these that are real drafting errors.

## 5. Why no label scheme is proposed here

The only labelled distribution available is `aux_train`, and it is a sampling
plan rather than a measurement:

| label | `aux_train` | `eval` |
|---|---:|---:|
| `content_misrepresentation` | 36.3% | 40.8% |
| `non_existent_citation` | 16.0% | 10.0% |
| `case_name_mismatch` | 16.0% | 19.6% |
| `misquote` | 15.9% | 13.1% |
| `wrong_pincite` | 15.8% | 16.5% |

Four of the five classes sit within 0.2 points of each other across 786
labelled citations. Nothing in either file reports how often these defects
occur in filings that were actually served, so a scheme fitted to this is
fitted to the generator that produced it.

Two earlier drafts of this note did exactly that -- first seven labels, then
four -- and both were built by finding somewhere to put each of the five
existing classes. That is reverse-engineering a taxonomy from someone else's
construction, before the real distribution has been looked at.

The defects found by reading real filings do not look like the five classes.
The 17 in `unrecorded-defects.md` are single-digit and single-series slips with
court and year left consistent -- what a person or a drafting tool does. The
injector swaps a whole reporter and prints a contradicting court. Same file,
different generators, and only one of them is evidence about drafting.

## 6. What to do instead

1. **Build the reporter-series rule.** §4. Largest class in the corpus, needs no
   retrieval, and nothing downstream currently sees these at all.
2. **Read the locator first and let it decide.** The name check and the
   first-page check answer independently today, so a citation can be convicted
   twice for one error and a name can be compared against whatever sat at a
   wrong page.
3. **Read parallel citations.** Unused, offline, no allowance. `447 U.S. 242`
   prints `106 S. Ct. 2505` and `91 L. Ed. 2d 202`, which are 477 U.S. 242's --
   a second address in the same citation, disagreeing with the first.
4. **Collect the defects before naming them.** Every finding should record the
   locator's answer and which fields disagreed with the document it named. That
   is a record, not a label, and a scheme can be cut from it once there is
   enough of it to see a shape.
