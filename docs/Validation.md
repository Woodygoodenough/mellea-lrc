---
tags: [validation, courtlistener, hallucination-detection, pinpoint]
status: active
---

# Validation

Validation is the last stage. It takes the citations
[extraction](./Extraction.md) found and asks, of each one, whether the authority
it names exists and matches how the filing cites it — down to whether the page
cited actually says what it is cited for.

It never answers "this citation is fake." It reports what it could establish and
what it could not, and keeps those two apart. Why that distinction is the whole
design is the first section below.

---

## Running it

```python
import asyncio
from mellea_lrc.extraction import extract_from_raw_document
from mellea_lrc.validation import validate_document

document = extract_from_raw_document(Path("filing.pdf"))
validated = asyncio.run(validate_document(document))
```

It is async because every step is I/O — CourtListener over HTTP, then a model.
Credentials come from the environment: `COURTLISTENER_API_TOKEN` and
`MELLEA_LRC_LLM_*`. See
[the client doc](./courtlistener-client.md#getting-an-api-token) for the token,
and [its rate-limit notes](./courtlistener-client.md#rate-limits) before running
anything at scale — a free-tier quota will not carry a real workload.

Both dependencies are injectable:

```python
validate_document(document, client=my_client, session=my_session)
```

`client` is anything satisfying `CourtListenerServiceClient`, which is the seam
for a cache or a fixture. `session` is a Mellea session. Leave the model
temperature at `0.0`.

The `mellea-lrc validate` command wraps exactly this.

---

## Absence is not falsity

The single most important thing about this stage.

A citation that CourtListener cannot resolve has not been shown to be
fabricated. It may simply not be there, and the reasons are structural:

- **CourtListener's archive is crowdsourced.** RECAP mirrors PACER only for
  documents someone already paid to download. A docket can be fully indexed
  while the filing itself was never uploaded.
- **Trial-level state material is largely absent.** Coverage is strong for
  federal and state appellate opinions, thinner below that, and varies by court.
- **Sealed and restricted filings never reach PACER at all**, so they cannot
  reach RECAP.
- **Unpublished opinions** appear only if scraped from a court's own site.

So `not_found` means *not found*. Treating it as evidence of invention is the
exact error this stage is built to avoid, and it is why the outcome vocabulary
below keeps abstentions as their own answers rather than folding them into a
verdict. When you report results, report the abstention rate next to the
accuracy; recoding abstentions inflates whichever number they land in.

---

## What comes back

A `ValidatedDocument`: one `CitationValidation` per extracted citation, each
holding an ordered tuple of **nodes**.

A node is one check. It records what was asked, what came back, and what that
means:

| field | what it is |
|---|---|
| `node_id` | stable identifier, derived from the path that produced it |
| `status` | `succeeded`, `skipped`, or `failed` |
| `outcome` | the finding — vocabulary depends on the node |
| `depends_on` | the nodes this one consumed |
| `status_message` / `outcome_message` | prose for each |
| `error` | set when `status` is `failed` |

Nothing is overwritten and nothing is summarised away. A citation's history is
the list, in order, and `citation_validation.aggregation` returns its terminal
summary node when the route produced one.

**`status` and `outcome` answer different questions.** `status` is whether the
check ran; `outcome` is what it found. A `succeeded` node with outcome
`mismatch` did its job and found a problem. A `failed` node found nothing
because the step itself broke. Reading a `failed` as a negative finding is the
same category error as reading `not_found` as fabrication.

---

## The identity stage

`identify_document` answers one question for a whole filing: which case does
each authority it cites name? It runs beside `validate_document`, takes the same
`client` and `session`, and returns an `IdentifiedDocument`.

```python
from mellea_lrc.validation.identity import identify_document

identified = asyncio.run(identify_document(document, client=my_client, session=my_session))
```

### Once per root, not once per citation

Extraction's citation tree resolves every `Id.`, short form and repeated full
citation to the **root** that introduced its authority. The stage looks up the
roots and nothing else. A filing citing one case ten times costs one lookup;
the nine return visits inherit the answer, and `identified.resolution_of(id)`
follows the tree to it. Their own pages are pinpoint claims for a later stage,
and a return visit extraction attributed wrongly is found where its pinpoint
fails rather than here.

Two kinds of root are checked differently. A reporter locator goes through the
route below. A **docket number** is a root too — the docket and the court name
a case on their own — but it has no volume or page, so it defers to search,
with its RECAP route described in `validation/identity/docket.py`.

### The record

Each citation gets a `CitationRecord`, the one mutable object in validation:

| field | what it is |
|---|---|
| `source` | the extracted citation, never changed |
| `citation` | the pipeline's current reading of what the filing states |
| `authority_id` | which root this refers to, after any merge |
| `resolution` | what the archive holds: cluster, name, date, court |
| `corrections` | every change to `citation` or `authority_id`, each naming the trace node that justified it and who made it — a rule by module name, or a model by name |
| `trace` | the ordered nodes, as in a `CitationValidation` |

Two rules keep the record honest. A correction with no node in the trace is
refused. And the archive's values never reach `citation`: a filing that cites
the right case under the wrong year keeps its year, gets the right one on
`resolution`, and the disagreement between them is the finding.

### The route

```
identity scope ── non-root, or not a case → stop, inheriting or out of scope
└── exact locator lookup
    ├── not found → DEFER_TO_SEARCH
    └── every record at the locator: the rule guard
        ├── some record agrees on every field → CONFIRMED_IDENTITY, the page disclosed
        ├── none agrees, one record → the single-candidate judgement
        │   ├── same case, fields agree  → CONFIRMED_IDENTITY
        │   ├── same case, a field wrong → WRONG_IDENTITY, reason field_disagreement
        │   ├── different case           → WRONG_IDENTITY, reason different_case_at_locator
        │   └── undeterminable           → DEFER_TO_SEARCH
        ├── none agrees, several records → one judgement over all of them
        │   ├── chooses a record         → CONFIRMED_IDENTITY, or WRONG_IDENTITY by its fields
        │   ├── every record is not it   → WRONG_IDENTITY, reason different_case_at_locator
        │   └── undeterminable           → DEFER_TO_SEARCH
        └── none agrees, more records than a judgement is shown → AMBIGUOUS_IDENTITY
```

**Several records at one locator** is the ordinary case for a decision the
archive holds twice, and the occasional case for a page of unpublished
dispositions. Nothing decides which records are one decision by a heuristic.
Every record gets the rule guard, any full agreement confirms, and the
resolution says how many records sat at the page and which of them agreed,
so two copies of one decision confirm with both listed. When no record
agrees, the model is shown all of them at once: it reads the filing once,
with evidence, answers for each record whether it is the filing's case, and
chooses one or none. A requirement holds the choice to the answers: a chosen
record must be one the model called the same case, and a refutation needs
every record called not the filing's case. A page with more records than the
judgement is shown at once (six) is ambiguous, and no court is fetched for
it, since each costs a request.

**The rule guard** is three comparisons that cost no model call, each reading
the record's current citation. The case name is compared by containment, one
side at a time: every distinctive word the filing wrote on a side must appear
on the matching side of the record's name, sides may swap, and what the filing
did not write is not held against it, so `Golden` agrees with `Bobby Ray
Golden` and `Reyes v. Pac. Bell` with `Victor Reyes v. Pacific Bell`. Either
side may be the abbreviated one, since the archive writes `Dept. of Social
Servs.` as readily as a filing does, and a record side also offers its adjacent
words run together, so `JPMorgan` covers `JP Morgan`. The date
is compared at the precision the filing stated, by year for `(2007)` and by
day for `(E.D.N.Y. Oct. 31, 2024)`. When it disagrees, the archive's other
dates for the record are read before the disagreement is believed: the
cluster's `other_dates`, and failing that the first opinion's header, for a
dated event — decided, amended, filed, reissued — that states the filing's
year. A lookup record's one date is the filing date of the opinion the
archive holds, and a reporter citation to an opinion amended into the next
year states the year of the print, so a correct citation disagrees with the
record by design. A match is `compatible` and the node carries the phrase;
argued and submitted dates do not count; nothing found leaves the mismatch
standing with everything that was read on the node. This costs one or two
requests, on the few records that disagree. The court is compared by courts-db
identifier, which costs one docket fetch per candidate because the lookup
endpoint returns no court. A filing that states no court is not compared
against nothing: the reporter holds only some courts — `N.C. App.` holds North
Carolina's appellate courts, `So. 3d` the courts of five states — and the
record's court is checked against that family, `compatible` when it is one of
them and a mismatch when it is not. The family comes from reporters-db's
jurisdiction list mapped onto courts-db identifiers, and it is a superset, so
it can only catch a conflict, never supply a reading. Any other absent field
on either side is `unavailable`, never a disagreement.

**The composite judgement** runs only when a rule disagrees, and it sees the
filing's own text rather than two strings, because a disagreement has three
possible sources — the filing is wrong, the extractor misread it, or the two
are the same thing written differently — that strings cannot tell apart. The
model is a reader that must show its evidence. Two windows bound what it may
read, both fixed by the citation's non-co-located neighbours: the text before
the locator for the case name, and the parenthetical after it for the court
and the date. A parallel citation shares one name window and reads its
parenthetical past its co-located members.

Each reading is checked deterministically and repaired in a further turn if it
fails, up to three. The case name needs one place in its window it could have
been read from, matched fuzzily, so the model is not punished for writing
`Suffolk` where the filing wrote `Suffock`. A court read from the parenthetical
comes with its evidence string, which must be in the window and must resolve
to the same courts-db identifier; a court implied by the reporter is allowed
only where the reporter holds exactly one, which `U.S.` does and `F.3d` does
not. Where the model reads no court, the reporter's family stands in for the
comparison, as in the rule guard. A date comes with its evidence string, which must be in the window and
must contain the year, and the day when one is read.

Court and date agreement are then computed from the reading and the record, at
the precision the filing stated. The model's one judgement is the case name:
`agree`, `variant` for the same case written defectively, `disagree`, or
`undeterminable`. The verdict must follow from the agreements: all agree forces
`same_case`; `different_case` needs the case name to disagree, because a wrong
court or year on an agreeing name is a defect of the filing and not a
different case; with no name to compare the verdict is `undeterminable`.

When the requirements are still unmet after three turns, the judgement is
recorded as failed with the model's last answer and what it failed, the
readings whose evidence passed are kept and written onto the record as
corrections, and the root defers to search. A good reading of the case name is
not lost because the court could not be grounded.

**Parallel citations** arrive as separate roots sharing a `colocation_id`,
because extraction leaves identity to the lookup. When both resolve to one
cluster, the later root is re-attributed to the earlier one, and so is every
citation that referred to it. When they resolve differently, both stay.

### Reading an identity result

Four outcomes, each with a reason under it:

| outcome | reason | means |
|---|---|---|
| `confirmed_identity` | | the locator names one case and every field the filing states agrees |
| `wrong_identity` | `field_disagreement` | the locator names the case, and a field the filing states disagrees; `fields` lists each with the filing's value and the record's |
| `wrong_identity` | `different_case_at_locator` | the one case at the page is not the one the filing names; `record_case_name` says which it is |
| `ambiguous_identity` | `crowded_page` | more records at the locator than a judgement is shown at once, none agreeing with the filing on every field |
| `defer_to_search` | `not_found`, `lookup_failed`, `undeterminable`, `docket` | nothing the lookup route can decide; the search route's population |

`wrong_identity` is deliberately wide: a filing citing the right case to the
wrong court and a filing citing a page that holds some other case are both
citing something other than what they say, and the reason and fields under
the node keep them apart. A `field_disagreement` still resolves the record --
the case was found -- so a later stage can decide whether to check its
pinpoint.

`different_case_at_locator` needs every record the archive holds at the page
to have been judged not the filing's case, by a judgement that saw them all.
A page too crowded to judge is `ambiguous_identity` rather than a refutation,
because the filing's case may be among the records nobody read. That is the
same rule as *Absence is not falsity*, applied one level down.

`serialize_identified_document` writes the whole thing — source citation,
current reading, corrections, resolution and trace — and reads it back.

---

## The route

Everything begins with an exact locator lookup — volume, reporter, page — and
the result of that one call decides which of three paths the citation takes.

```
exact locator lookup
├── found      → the field checks, then the pinpoint check
├── not found  → recover a case name, then search
├── ambiguous  → candidate selection, then the field checks per candidate
└── unsupported / incomplete / failed → stop
```

The last row matters: a short-form citation, or one whose locator is missing a
field, cannot be looked up at all and ends immediately. That is a property of
what extraction produced, not a finding about the citation.

### When the locator resolves

The main path. The cited authority is in hand, so every remaining question is a
comparison between what the filing says and what the record says.

```
found locator
└── locator candidate evaluation
    ├── exact case-name check ── mismatch → case-name recovery
    ├── year check
    ├── docket court retrieval → court check
    ├── reporter-page retrieval
    │   └── citing-proposition extraction → pinpoint check
    └── locator candidate assessment → citation summary
```

The three field checks are independent and each reports `match`, `mismatch`, or
`unavailable`. `unavailable` means the filing or the record did not state the
field — not that they disagreed.

**Case-name recovery** is what happens when the names do not match. Rather than
concluding `mismatch`, the pipeline tries again: a model compares the names
semantically (abbreviations, party ordering, `et al.`), and if extraction gave
it nothing to work with, a second model pass re-reads the document text to
recover the parties directly. Only then is the disagreement taken at face value.

**`locator candidate assessment`** folds the field checks into one verdict —
`match`, `partial_match`, or `mismatch`.

### The pinpoint check

The substantive one, and the only step that reads the cited opinion's text.

Two model calls, in order. **Citing-proposition extraction** reads the citing
document around the citation and states the proposition being attributed to it.
**The pinpoint check** then reads the retrieved reporter page and decides
whether that page supports it — `supports` or `inconclusive`.

Neither is asked to recall anything. Both work from text supplied to them, and
the answer must be grounded: a `supports` verdict has to quote the page, and the
quote is located back in the retrieved text before the verdict is accepted. A
quote that cannot be found uniquely is rejected and the model asked again; a
verdict that never grounds is reported as `failed` rather than as a finding.

That is the reason for `evidence_span` and `evidence_match_method` on the
result — an offset into the page that was actually retrieved, and how it was
matched (`exact`, `normalized`, or `fuzzy`). The verdict is always checkable
against the source.

By design the model can only say `supports` or `inconclusive`. It is never asked
to conclude that a page *contradicts* a proposition, because one retrieved page
is not enough evidence to condemn a citation.

### When the locator does not resolve

The fallback. Without a locator there is nothing to look up, so the pipeline
works from the case name instead.

```
not-found locator
└── local party re-extraction
    └── case-name query preparation
        ├── CourtListener opinion search → candidate selection → per candidate
        └── CourtListener RECAP search   → candidate selection → per candidate
```

Two searches, because the two corpora differ: opinions covers published
decisions, RECAP covers filings. Candidates from either are assessed the same
way as a resolved locator, except the verdict vocabulary is narrower —
`possible_match` or `mismatch`. Nothing found by search is ever called a
`match`, because a search hit is a resemblance, not an identification.

This route deliberately does not run the pinpoint check. Without a confirmed
authority there is no page to read.

### When the locator is ambiguous

One locator resolving to several clusters. Each is evaluated as its own
candidate through the same field-check subtree, and selection is capped —
`deferred_over_limit` records that some candidates were not pursued rather than
silently dropping them.

---

## Reading a result

The summary vocabulary, across both routes:

| outcome | means |
|---|---|
| `match` | the record agrees with the filing |
| `possible_match` | a candidate resembles it, unconfirmed |
| `mismatch` | the record contradicts the filing |
| `not_found` | nothing was found — see *Absence is not falsity* |

Two cells deserve attention when you look at aggregate results. A `mismatch`
against a genuine citation is a false alarm and costs a reader's trust. A
`match` against a bad one is the dangerous cell — a citation waved through — and
is the number worth minimising.

The per-node detail is where the reasoning lives. A citation that came back
`mismatch` has a specific node that said so, with the retrieved value beside the
filing's; a pinpoint result carries the quote it rested on. Nothing requires you
to trust the summary.

---

## How it is measured

Against the frozen validation set, with the scoring rules, the confusion matrix,
and how to reproduce a run documented alongside the code that does it, in
[the validation evaluation](../evaluations/validation/README.md).

One property of that benchmark follows directly from the first section:
occurrences CourtListener cannot decide are **absent from it** rather than
labelled. Inferring `mismatch` from a failed lookup is the error the set exists
to expose, so it is not built into the labels.
