# What a pinpoint check can and cannot assert

Written 22 August 2026, after the citation tree made every reference its own
claim rather than an alias of the first one. The question is what to do with
those claims.

## 1. Four questions, wrongly treated as one

A pinpoint citation — `550 U.S. 544, 555` — asserts that page 555 of that case
supports something the filing says. Checking that assertion is four separate
questions, and the current outcome vocabulary collapses them into `supports`:

| # | Question | How it is settled | Confidence |
|---|---|---|---|
| 1 | Does the cited page exist in the opinion? | Star-pagination markers in the retrieved HTML | Deterministic |
| 2 | Is the quoted text on that page? | String match against the page | Deterministic |
| 3 | Is the quotation accurate and not misleadingly cut? | Bluebook alteration rules, ellipsis handling | Mostly deterministic |
| 4 | Does the case support the proposition? | Reading | A judgement |

Questions 1 to 3 are already answered by code that does not call a model:
`reporter_page.py` slices the page, and `quotation/verbatim.py` compares the
quoted text against it. Question 4 is what the model is for, and it is the only
one where the answer can be argued with.

**Reporting all four as one verdict wastes the first three.** A citation whose
quoted sentence is absent from the retrieved page is refuted by string
comparison; saying "the model judged it unsupported" throws away the fact that
no judgement was needed.

## 2. Where the assertable boundary sits

The concern is real: a model asked whether a case supports a proposition will
answer, and its answer on a contested question of law is worth little. So the
boundary has to come from somewhere other than the model's confidence.

The 25 adjudicated misrepresentation records in false-citation-bench are that
somewhere. Every one is a case where a judge, after full briefing, found a
citation misrepresented. Read individually, they fall into three groups:

| Count | What the court found | Reachable by |
|---:|---|---|
| 2 | The quoted language is not in the opinion at all | String comparison |
| 2 | Both a bad quotation and a bad holding | String comparison, partly |
| 21 | The cited case is about a different subject, or holds the opposite | Judgement |

The 21 are the interesting group, and reading them settles the boundary. They
are not close calls:

- *Jimerson* held that ANCSA barred certain transfers of **stock**; the brief
  said it held that transactions affecting **land** were invalid.
- *Chugach Natives* was about "whether sand and gravel are part of the surface
  or subsurface estate". It was cited for the impropriety of a deed.
- *Bridgeport Music* "supports the opposite of what she argues".
- *Salyers* "concerns an appeal of summary judgment in a § 1983 claim and does
  not state, as Jones claims, that service may be upheld where…".

**Not one of the 25 is a case where reasonable lawyers would disagree about
whether the authority supports the proposition.** In every one the cited case
is about a different subject, or says the reverse. Courts do sanction
misrepresentation of holdings — the concern that they only punish invention is
wrong — but what they sanction is gross mismatch, not weak argument.

That gives a boundary that does not depend on trusting the model's judgement:

> Assert misrepresentation only where the retrieved page is **about a different
> subject** than the proposition, or **states the contrary**. Where the page is
> on the subject and the question is whether it goes far enough, abstain.

A poorly argued citation is a legal disagreement and belongs to the opposing
brief, not to a verifier. This is the same rule the project already applies to
absence: report what can be shown, decline what cannot.

## 3. Citations that assert nothing to check

The tree produces one claim per occurrence, but not every occurrence carries a
proposition. Four cases, and each needs a different answer rather than a
shared `inconclusive`:

**Listed, not argued.** An entry in the table of authorities makes no claim.
Section 11.2 of the report already locates these; they should be excluded
before a proposition is even sought, not run and then abandoned.

**Cited for the whole case.** `See Iqbal, 556 U.S. 662.` with no pin cite
attributes nothing to a page. Question 1 does not apply, and questions 2 to 4
have no page to apply to. The right outcome is that there is no pinpoint claim
here, which is different from failing to check one.

**The proposition is the sentence before, but implicit.** A brief writes a
sentence, then cites. Usually the preceding sentence is the proposition. When
it is a transition ("The Court disagrees.") the citation supports the paragraph
rather than the sentence, and extracting a proposition from the adjacent text
produces something the case was never cited for. Checking that invented
proposition against the page and reporting a mismatch would be a false
accusation manufactured by our own extraction step.

**String citations.** `See, e.g., A; B; C.` offers three authorities for one
proposition, and the Bluebook signal says only that each is *an* example. A
single one failing to carry the whole proposition is not a defect.

The common thread: **when the proposition cannot be identified with confidence,
the failure is ours and must be reported as ours** — not converted into a
finding about the citation.

## 4. What the introducing signal permits

The Bluebook signal states what kind of support is claimed, and checking for
more than was claimed produces false accusations. Measured across the corpora:

| Signal | 26 test filings | 109 sampled |
|---|---:|---:|
| none (direct statement) | 474 | — |
| `see` | 140 | — |
| `see also` | 19 | — |
| `e.g.` | 26 raw | 163 raw |
| `see generally` | 0 | 19 |
| `compare` | 0 | 15 |
| `cf.` | 0 | 14 |
| `but see` | 0 | 2 |
| `contra` | 0 | 0 |

Counting these needs word boundaries: a first attempt reported 127 `contra` in
the test set, all of them inside the word *contract*, and 51 `accord` inside
*accordance*.

Signals that do not claim direct support are absent from the test filings and
rare elsewhere — roughly 50 occurrences per 109 filings. They still have to be
handled, because the failure mode is asymmetric: asking whether a page supports
a proposition it was cited to **contradict** (`but see`) turns a correct
citation into a reported defect. Rare and wrong is worse than common and
uncertain.

`cf.` is the same problem in weaker form: it claims analogy, not support, so
"the page does not state the proposition" is the expected condition rather than
a finding.

## 5. Proposed shape

Split the single check into a sequence that stops at the first thing it can
settle, so that every verdict names the evidence that produced it.

```
0.  Is this occurrence a claim at all?
       in a table of authorities        -> not_a_claim
       no pin cite                      -> no_pinpoint_claim
1.  Does the cited page exist?
       page absent from the opinion     -> page_not_found        (deterministic)
2.  Does the filing quote the case here?
       quoted text not on the page      -> quotation_not_on_page (deterministic)
       quoted text altered in meaning   -> quotation_altered     (deterministic)
3.  What does the signal permit?
       contradiction or analogy signal  -> support_not_claimed
4.  Can the proposition be identified?
       no, or only a transition         -> proposition_unclear   (our failure, stated as ours)
5.  Is the page on the proposition's subject?
       different subject                -> different_subject     (assertable)
       contrary holding                 -> states_the_contrary   (assertable)
       on subject, support arguable     -> inconclusive          (abstain)
       on subject, carries it           -> supports
```

Two properties this is meant to have. **Every deterministic answer is reached
before the model is asked anything**, so the cheap and certain checks are never
overwritten by a judgement. And **the two verdicts that accuse someone —
`different_subject` and `states_the_contrary` — are exactly the two the 25
adjudicated records describe**, so the system asserts the class of defect that
courts actually sanction and abstains on the class they debate.

## 6. How much is left after the cheap steps

Measured over the 26 test filings, applying steps 0 to 3 only:

| | count | share |
|---|---:|---:|
| citation occurrences found by the tree | 643 | |
| listed in a table of authorities, asserting nothing | 103 | 16% |
| no pin cite, so no claim about a page | 201 | 31% |
| **pinpoint claims remaining** | **339** | **53%** |
| — pin cite names a reporter page that can be fetched | 276 | |
| — star pagination, so no reporter page exists to fetch | 63 | |
| distinct authorities behind the 339 | 257 | |

**Nearly half of all occurrences need no model at all**, and that is settled by
structure rather than by asking one. No occurrence was removed by the signal
step, which matches section 4: the signals that do not claim support are absent
from these filings.

Two numbers worth holding on to. The semantic layer's real scope on this corpus
is **276 checkable pinpoint claims**, where the project has so far produced
nine semantic verdicts — the shortfall is not the model, it is that only full
citations were ever checked. And those 276 claims sit on **257 distinct
authorities**, so identity is resolved 257 times rather than 339, which is the
saving the tree was built for.

## 7. What to measure next
- Of the 25 adjudicated misrepresentation records, how many would be caught by
  `different_subject` or `states_the_contrary`, given the page. That is the
  recall ceiling for the semantic layer and it is currently unknown.
- Whether a model can tell "different subject" from "arguable" reliably enough
  to be trusted with the distinction, which is the assumption the whole design
  rests on and the one most likely to be wrong.
