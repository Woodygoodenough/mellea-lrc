# The pinpoint check, and where legal reasoning stops

A brief for whoever takes this on. `pinpoint-design.md` is on this branch and
is the substantive document; this one says what to build and what not to.

## 1. The scope decision, stated plainly

**We do not answer whether a citation legally supports a proposition.** That is
a question lawyers argue and a model asked it will answer anyway, confidently
and worthlessly.

We answer a narrower question: **is the cited content invented, or so far from
what the page says that no reading connects them.** A citation whose quoted
sentence is not in the opinion, or whose page is about a different subject
entirely, is a defect of fact. A citation that is on point but arguably does
not go far enough is a legal disagreement, and it belongs to the opposing
brief.

## 2. Why that boundary is defensible rather than timid

It is not a hedge chosen to avoid hard cases. It came out of reading the
evidence.

The 25 adjudicated misrepresentation records in false-citation-bench are cases
where a judge, after full briefing, found a citation misrepresented. Read
individually:

| count | what the court found | settled by |
|---:|---|---|
| 2 | the quoted language is not in the opinion at all | string comparison |
| 2 | both a bad quotation and a bad holding | partly string comparison |
| 21 | the cited case is about a different subject, or holds the opposite | judgement |

**Not one of the 25 is a case where reasonable lawyers would disagree.** They
are gross mismatches:

- *Jimerson* held ANCSA barred transfers of **stock**; the brief said it held
  transactions affecting **land** were invalid.
- *Chugach Natives* was about whether sand and gravel belong to the surface or
  subsurface estate. It was cited for the impropriety of a deed.
- *Bridgeport Music* "supports the opposite of what she argues".

So courts do sanction misrepresented holdings — the worry that they only punish
outright invention is wrong — but what they sanction is gross mismatch, not
weak argument. The rule follows from that:

> Assert misrepresentation only where the retrieved page is **about a different
> subject** than the proposition, or **states the contrary**. Where the page is
> on the subject and the question is whether it goes far enough, abstain.

## 3. Four questions, not one

A pinpoint like `550 U.S. 544, 555` asserts that page 555 supports something.
Checking it is four questions, and today's vocabulary collapses them:

| # | question | settled by | confidence |
|---|---|---|---|
| 1 | does the cited page exist in the opinion? | star-pagination markers | deterministic |
| 2 | is the quoted text on that page? | string match | deterministic |
| 3 | is the quotation accurate and not misleadingly cut? | Bluebook alteration rules | mostly deterministic |
| 4 | does the case support the proposition? | reading | a judgement |

**Reporting all four as one verdict wastes the first three.** A citation whose
quoted sentence is absent from the page is refuted by string comparison; saying
"the model judged it unsupported" throws away the fact that no judgement was
needed.

Questions 1 to 3 already have code that calls no model: `reporter_page.py` on
main slices the page, and `validation/quotation/verbatim.py` on this branch
compares the quoted text against it. Question 4 is the only place a model
belongs, and section 2 is its leash.

## 4. Citations that assert nothing to check

The citation tree produces one claim per occurrence, but not every occurrence
carries a proposition. Four cases, each needing its own answer rather than a
shared `inconclusive`:

**Listed, not argued.** A table-of-authorities entry claims nothing. Exclude
before a proposition is sought, not after.

**Cited for the whole case.** `See Iqbal, 556 U.S. 662.` attributes nothing to
a page. There is no pinpoint claim here — different from failing to check one.

**The proposition is implicit.** A brief states something, then cites. Usually
the preceding sentence is the proposition; when it is a transition ("The Court
disagrees.") the citation supports the paragraph instead. Extracting a
proposition from adjacent text there produces something the case was never
cited for, and reporting a mismatch against it would be **a false accusation
manufactured by our own extraction step**.

**String citations.** `See, e.g., A; B; C.` offers three authorities for one
proposition, and the signal says each is *an* example. One failing to carry the
whole proposition is not a defect.

The common thread: **when the proposition cannot be identified with confidence,
the failure is ours and must be reported as ours** — never converted into a
finding about the citation.

## 5. The signal states what is claimed

The Bluebook introducing signal says what kind of support is asserted, and
checking for more than was claimed manufactures false accusations. `see
generally` claims background relevance, not support for the sentence. `cf.`
claims an analogy. `but see` and `contra` claim the *opposite* — a check that
reports "this does not support the proposition" has restated the signal as a
defect.

Frequencies across the corpora are in `pinpoint-design.md` §4. The long tail is
small but `e.g.` is not: 163 raw occurrences in the sampled set.

## 6. Why this matters now

The reference dataset labels three citation-shaped defect classes at roughly
even weight, and **wrong pincite is the largest at 39%**. It is also the one
class the hallucination miner cannot see at all — a court's order quotes the
fabricated citation, never the passage — so nothing measures it today. See
§8.9 of `exploration/AUDIT.md` on `experiment/general-explorations`.

## 7. Worth considering: read the whole opinion, not just the cited page

Everything above checks the **cited page**. That answers "is the proposition
there" and nothing else, so two very different filings get the same verdict:

- the case does not discuss this at all — a misrepresentation
- the case discusses it squarely, at page 570, and the brief wrote 555 — a
  wrong pincite

The second is a smaller sin and a different finding. Today both come back as
"the page does not support it", which tells the reader less than we know.

Retrieving the whole opinion and asking where the support actually sits would
separate them, and would let the tool say something more useful than a verdict:
*the proposition is supported, at page 570, not the page you cited.*

**The structure needed is nearly there already.** `extract_reporter_page`
parses `html_with_citations` and walks its star-pagination markers, collecting
`(citation index, page label, offset)` for the whole document — then returns a
single slice. Keeping the map instead of discarding it gives a page-addressed
view of the entire opinion, which is what lets a model answer *where* rather
than only *whether*, in the reporter's own page numbers rather than character
offsets a reader cannot use.

Three cautions, in the spirit of section 4:

- **Widening the search widens the false-accusation surface.** A model given
  the whole opinion and asked "is this supported anywhere" will find something
  in a long opinion more often than it should. The section 2 boundary still
  binds: different subject, or states the contrary.
- **A right proposition at a wrong page is a defect the corpus barely
  measures.** It is the largest labelled class at 39% and the miner cannot see
  it at all, so this is where the evaluation is thinnest and where a new
  capability is hardest to check. Build the measurement alongside it.
- **Cost.** A pinpoint check against one page is cheap; against a full opinion
  it is not, and opinions run long. Decide early whether this runs always, or
  only after the cited page fails.

## 8. What is on this branch

- `src/mellea_lrc/validation/quotation/` — `verbatim.py` and `quotation_check.py`,
  the deterministic answer to questions 2 and 3, with 16 tests
- the three node types they need in `validation/types.py`
- `exploration/notes/pinpoint-design.md` — the substantive document, including
  the measured signal frequencies and the four-question analysis in full

On main already: `pinpoint_retrieval/` with `reporter_page.py`,
`evidence_quote.py`, and the current single `mellea_pinpoint_check.py` whose
`supports`/`inconclusive` vocabulary is what section 3 argues should be split.

**A prerequisite lives elsewhere.** Making each occurrence its own pinpoint
claim needs the citation tree, which is on `experiment/citation-tree` with its
own brief. Read that first — the tree is what turns one authority into several
checkable claims about several pages.

## 9. Standing constraints

Nothing is committed or pushed to `origin` without asking; work goes to
`woody-fork`. No dataset is pushed anywhere; `local/` is git-ignored.
