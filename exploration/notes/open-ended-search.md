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

## 5. What the unresolved citations actually are

Measured after this note was first written, and it removes the main argument
for going outside CourtListener. The first version said state law is where the
free record thins out. That is not what the unresolved bucket is.

Of the 98 locators the probe recorded as unresolved:

| | count | share |
|---|---:|---:|
| Westlaw (`WL`) | 45 | 46% |
| federal reporters | 34 | 35% |
| state and regional reporters | 10 | 10% |
| LEXIS | 7 | 7% |
| other specialty | 2 | 2% |

A Westlaw number is assigned by Thomson Reuters and a LEXIS number by
RELX. They are not reporters, they identify a record in a paid database, and
**no free source can resolve one — nor can the open web, since the databases
are paywalled.** Together they are 53% of the bucket. The unresolved rate for a
Westlaw locator is 90%, against 6% for a federal reporter.

Of the 10 state entries, 7 evaporate on reading: 4 are short forms (see below),
and 3 are `70 O.S. 5` and `70 O.S. 6`, which are **Oklahoma Statutes** misread
as Ohio State Reports because `reporters-db` lists `O.S.` as a variation of
that reporter. Similarly `209 CMR 32` is the Massachusetts Code of Regulations
read as Court Martial Records, and three `FERC ¶ 61,xxx` entries are agency
orders. Roughly 7 of the 98 are not case citations at all.

**Genuine unresolved state-court case citations: 3 of 98.** Nothing here
justifies reaching outside CourtListener for state coverage.

A further 30 of the 98 were never citations to look up. They are short forms —
`132 S.Ct. at 1300` — whose page is a pin cite, and the probe was asking
whether a case *begins* on that page. The production pipeline never asks that.
Fixed in `evaluations/lephantomcite/locator_probe.py`, which now reports short
forms separately; it was 331 of the probe's 1,334 records.

## 6. The argument that survives for going outside it

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

## 7. What decides between them

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

Tested against three citations from the corpus whose case name disagrees with
the CourtListener record, searching only `nycourts.gov` — the New York courts'
own site, which publishes the official reports:

- `183 A.D.3d 649`: the official bound-volume index gives `Goodine, Matter of,
  v Evans`. The filing wrote `Cornhill LLC v. Sowers`. **Refuted**, and it
  matches CourtListener exactly.
- `139 A.D.3d 695`: the official index gives `Cadle Co. v Ayala` at
  **47 A.D.3d 919**, a different volume entirely from the filing's.
- `131 A.D.3d 1185` and `85 A.D.3d 1510`: the right index PDF came back both
  times, but the answer was not in the snippet.

So the mechanism works and its reliability is uneven, for a reason worth
recording: **every page on `nycourts.gov` returns 403 to a program.** The whole
site is behind bot protection, so the official reports are reachable only
through a search engine's index of them, and the evidence is whatever the
snippet happened to contain. A verification result that depends on a search
snippet is not reproducible next year, which is a problem for a project whose
whole point is that its results can be checked.

That is what sent this work to `caselaw-archive.md` instead.

## 8. What an agent is for, and what it is not for

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

## 9. What the preconditions actually cost

Measured over the same 98. Each row is what survives the previous one:

| gate | passes | fails |
|---|---:|---:|
| parses as a full case citation | 68 | 30 (all short forms) |
| both parties recoverable | 32 to 39 | 36 to 29 |
| carries a court | **25 to 30** | 7 to 9 |

**Only about a quarter of the unresolved citations ever reach the search.** The
range comes from the party gate being measured with eyecite rather than with
the model that actually runs it; eyecite is a lower bound, because it loses a
party to the benchmark's `*emphasis*` markup in 7 cases and to an intervening
docket number in others, both of which the model's prompt explicitly tolerates.
A `v.` appears in the window for 50 of the 68, but that is a ceiling rather than
an estimate: in a string citation the nearby `v.` usually belongs to a different
citation, and borrowing across citations is what the prompt forbids.

Of the 25 that do reach the search, 19 are Westlaw and 3 are LEXIS. That is the
right population for a name search — CourtListener very likely holds the opinion
under a reporter citation or none, and the vendor number will never resolve.

**Every one of the 25 states a year.** So does every one of the 30 under the
looser party rule. The query dropping the year is a filter given away for free,
in 100% of the cases where it could be used. That is the cheapest change
available and it needs no agent at all.

## 10. What is still worth measuring

1. How many of the 25 resolve if the court filter is dropped. One query each.
2. Whether adding the year as a date range changes what the existing query
   returns.
3. Whether the 150 short forms the probe recorded as `resolved` resolved to the
   right case. The lookup matches a first page only, so each of those found
   whatever case begins at the pin page, which is not the case cited.
