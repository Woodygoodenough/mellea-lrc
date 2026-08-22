# When to search openly instead of within CourtListener

Written 22 August 2026. The pipeline has one fallback search. This note records
exactly what it does, what it requires before it will run at all, and what
evidence there is for widening it — either to more CourtListener queries or to
the open web.

## 1. What the fallback search does now

It runs after an exact locator lookup fails to find a case. Three steps:

1. **Re-extract the parties.** `field_checks/mellea_case_name_reextraction.py`
   takes 320 characters before the locator and 160 after, and asks a model for
   the plaintiff and defendant. The answer is guarded: each party must occur
   verbatim, allowing for whitespace damage, in the text *before* the locator.
   A party the model invents is rejected and the step retries twice.
2. **Broaden the terms.** `case_search/mellea_case_name_query_preparation.py`
   asks a model for the shortest distinctive term for each party — dropping
   generic corporate words, expanding an unambiguous abbreviation. It is
   explicitly told not to use outside knowledge, not to add alternatives, and
   not to emit query syntax.
3. **Run one query.** The syntax is built in code, not by the model:

       caseName:("<plaintiff term>" AND "<defendant term>") AND court_id:<court>

That is the whole search. One query, one field, two terms joined by AND, and a
hard court filter.

## 2. What it refuses to run on

The preconditions are strict, and each one silently removes a citation from the
search path entirely:

| requirement | what happens without it |
|---|---|
| the citation parses as a full case citation | no search |
| re-extraction returns **both** parties | no search |
| the citation carries a court identifier | no search |

The court requirement is the sharpest. `court_id` comes from the citation's own
parenthetical — `(10th Cir. 2020)`. A citation written without a court, or one
whose court eyecite did not parse, cannot be searched at all no matter how
well-known the case is. A short-form citation never carries one.

The two-party requirement removes every `In re` citation, every `Matter of`
citation, and every case cited by one name.

## 3. What the query can and cannot express

Everything the pipeline knows about the citation is available at this point,
and almost none of it is used:

| known | used in the query |
|---|---|
| plaintiff and defendant | yes, both, ANDed |
| court | yes, as a hard filter |
| year the citation states | no |
| reporter series | no |
| volume and page | no |
| the pin cite | no |
| the proposition the filing attaches | no |

The year is the omission worth noting first. A citation states `(10th Cir.
2020)`, CourtListener indexes `dateFiled`, and a year range would cut most
false matches without any risk of excluding the right case — a date the filing
states is evidence, and if the case at that name has a different date, that is
itself a finding rather than a reason to hide the result.

Nothing here retries. If the one query returns nothing, the branch ends.

## 4. The argument for staying inside CourtListener

Two reasons, and both are about what a result *means* rather than about cost.

**A CourtListener result is a record, not a web page.** It carries a cluster
identifier, a court, a filing date, a docket, and the opinion text. Every later
step — the pin cite retrieval, the quotation check — needs those fields. A
search result from the open web is a claim by a third party that a case exists,
and nothing downstream can consume it.

**The project's central commitment depends on knowing the corpus.** The system
never reports "not found" as evidence of fabrication, because the free record
is incomplete. That commitment is only meaningful when the boundary of the
corpus is known. CourtListener publishes what it holds. The open web has no
boundary, so "I searched and found nothing" has no defined meaning there, and
"I searched and found something" may be a citation to a court record that
itself came from an AI.

## 5. The argument for going outside it

**State law is where the free record thins out.** The corpora cite New York
Appellate Division, California Court of Appeal, and Indiana appellate decisions
heavily, and those are exactly where a lookup returns nothing.

**A well-known case is verifiable from many sources.** For a Supreme Court case,
the open web is not a weaker source than CourtListener — the citation appears in
the court's own published slip opinion, in the U.S. Reports, and in every
secondary treatment. The risk of a fabricated web result is smallest exactly
where the free record is most complete, which is the wrong way round for it to
be useful.

**The case that matters most is the one CourtListener cannot settle.** The
`unresolved` bucket — 98 locators in the last probe — is where this project
declines to draw a conclusion. Any evidence that moves one of those to a real
answer is worth more than another confirmation of a case already found.

## 6. What decides between them

The choice is not "scoped or open". It is **what a search is allowed to
conclude**, and that differs by source:

- A CourtListener hit at the cited locator **confirms** the citation.
- A CourtListener miss **concludes nothing**, because the corpus is incomplete.
- An open-web hit **cannot confirm** a citation, because the web contains
  AI-written text and reproduces fabricated citations. It can at most say the
  citation is *attested somewhere*, which is weaker.
- An open-web result *can* refute, in one specific case: if a search for the
  case name returns an authoritative record with a **different** locator, that
  is positive evidence that the filing's locator is wrong. Refutation from an
  authoritative source is sound where confirmation from an unknown source is
  not.

That asymmetry is the design rule. **The open web is a refutation channel, not
a confirmation channel.** It answers "does this name belong to a different
citation?" and never "does this citation exist?"

## 7. What an agent is for, and what it is not for

The current search is one query with no room to react. An agent is worth
introducing where the next action genuinely depends on the previous result, and
not where a fixed sequence would do.

Where it does depend on the result:

- The one query returned nothing. Whether to drop the court filter, widen the
  party term, or try the other party alone depends on *why* it returned
  nothing, which is only knowable from the result.
- The query returned 200 results. Which field to add depends on what those
  results have in common.
- Re-extraction produced one party. Whether that is an `In re` case (search on
  the one party) or a failed extraction (fix the extraction) is decidable from
  the text, and the two need opposite next steps.

Where it does not:

- Building the query string. That is deterministic and belongs in code, where
  it is today, so that a model cannot emit search syntax.
- Deciding whether a hit confirms a citation. That is the rule in section 6,
  and it must not be a judgement.

So the shape is a **bounded agent with a fixed budget of queries, a fixed set of
allowed moves, and no authority over the conclusion**. It chooses which query to
run next; the rules decide what the result means.

## 8. What to measure before building it

Nothing here should be built before these are known, and none of them costs a
model:

1. How many of the 98 unresolved locators are refused by the preconditions in
   section 2 rather than searched and missed. A citation that never reached the
   search is not evidence that the search is too narrow.
2. How many resolve if the court filter is dropped. This is one query per
   citation and settles whether the hard filter is the constraint.
3. How many state-court citations are unresolved compared with federal. This
   settles whether the open web is worth reaching for at all, or whether the
   gap is somewhere else.
