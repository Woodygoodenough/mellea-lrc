# What a search loop would have to work on

The search stage's target is the ambiguous locator, not the unresolved one.
This note is the count behind that, and it is what section 2 of
`agentic-search-handoff.md` rests on. Written 1 September 2026, before any of
the loop was written.

Two buckets are in question. A locator is `unresolved` when CourtListener holds
no case at the cited volume, reporter and page; it is `ambiguous` when
CourtListener returns more than one case there and something has to decide which
one the filing meant.

## 1. Where the numbers come from

One run of `evaluations/lephantomcite/locator_probe.py` over 390 LePhantomCite
excerpts, 1,334 case citations, on 31 August 2026. The probe looks each citation
up by volume, reporter and page and records what the lookup alone established.
No model is involved and no search is run. Its output is a run artifact rather
than a tracked file.

The counts below are produced by
`evaluations/agentic_search/search_population.py`, which reads that file, parses
each citation with eyecite and counts. It sends no requests, so re-running it
costs nothing against the allowance:

    uv run python -m evaluations.agentic_search.search_population <probe.json>

Two limits apply to every number in this note.

**The corpus is defect-injected.** A label distribution over LePhantomCite
describes how the benchmark was generated as much as it describes filings.
Section 7.1 of `caselaw-archive.md` works through a case where that distinction
changed the reading of a result, and the same caution applies to every label
count below. Section 5.1 says where it bites hardest.

**The probe stores each citation's locator span, not the citation as written.**
A court parenthetical survives only where eyecite's span happened to include it.
Any count of how many citations carry a court is therefore a lower bound, and
section 7 says what measuring that gate properly would take.

## 2. The unresolved bucket is 97% sound citations

| locator outcome | count | share |
|---|---:|---:|
| resolved | 746 | 55.9% |
| short form, whose page is a pin cite | 331 | 24.8% |
| ambiguous | 120 | 9.0% |
| unresolved | 94 | 7.0% |
| refuted, an impossible reporter series | 31 | 2.3% |
| out of scope | 12 | 0.9% |

Of the 94 unresolved, **91 are labelled `sound` and 3 are labelled
`case_name_mismatch`**. The citation is correct and CourtListener does not hold
the record.

That is the finding this note exists for. Resolving the unresolved bucket by
search would confirm 91 citations that nothing was wrong with, and could reach
at most 3 defects. The work is a coverage improvement, not a detection one.

## 3. Most of the bucket is unreachable by search anyway

| what the unresolved locator is | count | share |
|---|---:|---:|
| a Westlaw or LEXIS record | 70 | 74.5% |
| a statute, regulation or agency document | 9 | 9.6% |
| a printed reporter a name search could reach | **15** | **16.0%** |

Section 11 of `open-ended-search.md` established that CourtListener's search
endpoint returns nothing for a vendor number even where its citation-lookup
endpoint holds the cluster, because the two endpoints are backed by different
corpora. The 70 are closed to search for that reason and not for want of a
better query. The 9 name Oklahoma Statutes, FERC orders, the Massachusetts Code
of Regulations and an Office of Legal Counsel opinion, which `reporters-db` maps
to case reporters; section 5 of `open-ended-search.md` identifies each.

**Fifteen citations remain.** A loop that reformulates against a miss is a loop
built for fifteen citations in 1,334, of which the labels say at most three
carry a defect.

Section 9 of `open-ended-search.md` estimated 25 reaching the search and said 19
of those were Westlaw and 3 LEXIS. Both halves of that estimate move here: the
population is smaller, and the vendor share of it is zero rather than most,
because the vendor citations are excluded before the search rather than at it.
The two counts are not measuring the same thing — that one counted citations
passing the preconditions, this one counts citations a search could act on — but
the conclusion each supports is the same and this one is sharper.

## 4. The ambiguous bucket is larger and carries more labelled defects

| label of the 120 ambiguous locators | count | share |
|---|---:|---:|
| sound | 94 | 78.3% |
| case_name_mismatch | 15 | 12.5% |
| content_misrepresentation | 7 | 5.8% |
| wrong_pincite | 4 | 3.3% |

An ambiguous locator is one where the exact lookup returned more than one
cluster for the same volume, reporter and page, and the pipeline has to decide
which one the filing meant. 95 of the 120 have two clusters. The remaining 25
have between three and 32, and 12 of those have twenty or more.

Set against the corpus base rate — 1,023 of 1,334 citations are labelled
`sound`, so 23% carry a defect — the ambiguous bucket's 22% is not enriched. The
argument for it is not a higher defect rate. It is that 26 labelled defects sit
behind ambiguity against 3 behind an unresolved locator, and that choosing among
32 clusters is a question a further query can answer where "CourtListener does
not hold this record" is not.

Where the whole corpus's defects sit:

| label | total | resolved | ambiguous | short form | unresolved |
|---|---:|---:|---:|---:|---:|
| content_misrepresentation | 129 | 91 | 7 | 31 | — |
| wrong_pincite | 53 | 32 | 4 | 17 | — |
| case_name_mismatch | 57 | 34 | 15 | 5 | 3 |
| misquote | 41 | 9 | — | 32 | — |
| non_existent_citation | 31 | — | — | — | — |

`non_existent_citation` is settled offline by the reporter-series check and
never reaches a lookup, so all 31 are `refuted`. `content_misrepresentation`,
`wrong_pincite` and `misquote` are decided by reading the retrieved page, not by
searching. **`case_name_mismatch` is the only label a search stage can act on**,
and 15 of its 57 occurrences sit behind an ambiguous locator.

## 5. Twenty-three ambiguous locators get no verdict at all

`validation/candidate_selection.py` sets `CANDIDATE_SELECTION_LIMIT = 3`. A
locator returning more clusters than that is deferred with **zero** candidates
selected, so no case-name check, year check or court check runs against any of
them. The node's own message states the gap: "further refinement is needed
before selecting candidates."

| label of the 23 deferred locators | count | share |
|---|---:|---:|
| case_name_mismatch | 12 | 52.2% |
| sound | 10 | 43.5% |
| content_misrepresentation | 1 | 4.3% |

Two ways to read the same 23 citations, and both are reasons to work on them.

The first is a count of what the pipeline produces: **for 23 of 1,334 citations
it evaluates nothing**, not because the evidence is absent but because there is
too much of it. That holds whatever the labels say.

The second is the label distribution, which is 52% `case_name_mismatch` against
a corpus rate of 4.3% for that label — twelve of the 57 occurrences in the whole
corpus, in 23 citations. Section 5.1 is why that number should not be used to
size anything yet.

### 5.1 The enrichment is probably an artefact of the injector

A page with twenty to thirty-two clusters is very likely a table-of-decisions
page, where a reporter prints a list of unpublished dispositions rather than one
opinion. Section 11 of `open-ended-search.md` records that those dispositions
are reachable by citation lookup and absent from search.

Section 7.1 of `caselaw-archive.md` established that LePhantomCite's
`case_name_mismatch` defects were injected by perturbing a page number rather
than by borrowing another real citation. A perturbed page lands on a
table-of-decisions page at whatever rate such pages occur in a volume, so the
correlation between a high cluster count and that label may be measuring the
generator. The same argument invalidated a 61% figure in that note, and section
8 of it then found the corresponding check fired zero times on 135 real filings.

**So the 52% is a lead, not a rate.** What is not in doubt is the first reading:
23 citations reach no verdict, and the mechanism producing that is a constant in
the code rather than anything about the corpus.

## 6. The question the loop answers

The loop's shape is the brief's: issue a query, read the result, decide the next
move, stop on a budget. The counts above do not touch that shape; they fix which
question it is applied to.

The question is **"the locator found more cases than the pipeline will look at,
and the text around the citation is not enough to say which one the filing
meant."** With 32 clusters on one page, which field to add depends on what those
32 have in common, and that is knowable only from having seen them. That is the
test the brief's section 2 sets for where a loop earns its place.

The question is **not** "the locator found nothing, find the case." That is 15
citations, and for 70 more the corpus makes it impossible.

Two consequences for the design.

**The first move is not a request.** The clusters are already in hand from the
locator lookup, so narrowing 32 candidates to 3 by case name, year or court
costs nothing. The budget in the brief's section 5 therefore covers only the
moves taken after the free one fails to separate them.

**Nothing here depends on the search corpus.** A disambiguating query runs
against clusters the lookup endpoint already returned, so section 11 of
`open-ended-search.md` — the search endpoint holding less than the lookup
endpoint — does not constrain it.

## 7. What is still unmeasured, and what it would take

Four counts this note cannot produce from the probe file.

1. **Whether an ambiguous locator's candidates are separable without a
   request.** For the 95 two-cluster cases and the 23 deferred ones, the
   clusters were already returned by the lookup. The measurement is how often
   the candidates at one locator differ in case name, court or year, and it
   costs nothing beyond re-reading cached lookup responses.
2. **How many citations pass the search preconditions.** The gates are that the
   citation parses as a full case citation, that re-extraction returns both
   parties, and that the citation carries a court. Six of the 94 unresolved
   locators carry a court eyecite can read, but the probe stores locator spans,
   so that is a lower bound rather than the gate's pass rate. Measuring it needs
   the excerpt text and one eyecite pass over it, which costs nothing.
3. **What the archive says about the deferred pages.** `caselaw/cap_index.py` on
   `experiment/general-explorations` returns every case the Caselaw Access
   Project puts at a volume and page, offline and free. If those pages are
   table-of-decisions pages, the archive will show it, and that settles section
   5.1 one way or the other. Section 8 says why it cannot be run from here.
4. **What the ambiguous bucket looks like in real filings.** Every count here is
   from a defect-injected corpus. Section 8 of `caselaw-archive.md` found a
   check with 61% label agreement on this corpus fired zero times on 135 real
   filings. The same run should be made over those filings before any of these
   numbers sizes an effort.

Items 1, 2 and 3 cost no requests and all three should be done before the loop
is written.

## 8. This branch does not carry what section 7 needs

`search/agentic-retrieval` is branched from `main`. Three modules the work above
refers to are on `experiment/general-explorations` and not here:

| module | what it does |
|---|---|
| `caselaw/cap_index.py` | the Caselaw Access Project reader, offline and free |
| `caselaw/case_name_check.py`, `first_page_check.py` | the checks built on it |
| `evaluations/lephantomcite/locator_probe.py` | the probe that produced the counts above |

Item 3 of section 7 cannot be run from this branch without them. Merging
`experiment/general-explorations` into this branch is the obvious fix and has
not been done, because that branch is the primary track's working branch and the
merge direction is the primary track's decision rather than this one's.
