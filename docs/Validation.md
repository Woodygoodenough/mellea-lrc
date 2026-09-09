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

## The words

Extraction's four, and this side produces the third.

| word | means |
|---|---|
| **occurrence** | one place in a filing where a case is referred to |
| **root** | an identifier the filing states, plus the returns that inherit it. A claim, checkable |
| **authority** | the identity a root is established to have. This side's word |
| **cluster** / **docket** | what an archive holds: one decision, and the court file that produced it |

A record carries both: `root_id` is what extraction read and is never written
to, and `authority_id` is empty until a lookup finds that two roots name one
case. Reading `record.authority` gives the second where there is one and the
first otherwise; `IdentifiedDocument.authority_record` walks from any citation
to the record holding its identity, root then merge. So `roots` counts what the
filings state and `authorities` counts what they reach, and the two differ by
exactly the merges.

`case` is not used for a thing: a court file can produce several decisions and
a decision can hold several opinions.

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

### The pinpoint stage

`validation/pinpoint/`. Identity settled which case a filing cites; this
stage takes every citation that also names a page and puts the filing's words
beside the page's. It runs over the whole citation tree: the full citation,
and each `Id. at 570`, `556 U.S. at 678` and `Iqbal at 678` that returns to
the same authority, since each is its own claim about its own page.

    uv run python -m evaluations.pinpoint.run_identified_artifacts data/runs/extraction-v2.0-identified

Four nodes per citation, appended to the record's trace after the identity
nodes.

**Scope** (`PinpointScopeNode`). The citation states a pin cite; its authority
resolved to a cluster (`confirmed_identity`, or `wrong_identity` on a field,
which still found the case); and the pin names a reporter page. A star page
(`*3`) counts an electronic report, a paragraph (`¶ 26`) an opinion's or an
indictment's numbering, a section a statute: none is a reporter page and each
is named for what it is. A range (`180-81`) is every page it spans, up to
four.

**Page** (`PageRetrievalNode`, `pinpoint/pages.py`). CourtListener's
`html_with_citations` marks where each reporter's pages turn, indexed by
parallel citation, and the same opinion paginated by S. Ct. turns at
different places -- so the page is cut for the reporter the filing wrote. The
marker index is read from the page numbers themselves, because the cluster's
citation list and the HTML's `citation-index` do not always count the same
way. An opinion's opening pages often carry no marker at all (`814 F.2d 565`
is marked only from 568), so a page between the case's first page and the
first marker is the head of the text, cut as one run. The archive may hold the
page under several clusters that agree on the case, and the one identity
settled on need not be the one whose text is paginated: every agreeing cluster
is tried. Every opinion of the cluster is read and paginated, the court's
first, and the page comes with the tail of the page before and the head of
the page after, because a sentence pinned to 678 often begins on 677. An
opinion the archive holds with no page markers at all -- its own scrape of a
recent decision -- cannot be cut, and the whole of it stands in for the page
(up to a hundred and twenty thousand characters), which changes what an absence means: not
"not on this page" but "not in this opinion". Which
opinion the page came from travels with it: words on the cited page in a
dissent are a different fact from the same words in the opinion of the court.

**Quotes** (`QuoteCheckNode`, `pinpoint/citing.py`). Every quotation the
filing writes in the sentence the citation belongs to, in the citation's own
parenthetical, or after the citation in the same sentence, is lifted with its
span -- double or single marks, an apostrophe told from a quotation mark by
what stands on either side -- and searched by the program: on the page, on
the pages beside it, then through every opinion of every cluster that
agrees on the case, since the archive holds a case twice as often as not and
the words may be in the copy the page was not cut from. `[n]eglect`
is searched as `neglect`; a quotation written with ellipses is searched
fragment by fragment. A quotation shorter than four words is searched exactly,
never fuzzily. The finding is `on_page`, `adjacent`, `elsewhere` with the
page it was found on, or `absent` from every opinion. A quotation in a
sentence a string cite shares proves nothing about one member by its absence
and is marked `shared`; one shorter than six words decides nothing on its own,
since a parenthetical's `'failed to show any prejudice'` is as often a close
paraphrase as a quotation.

**Reading** (`MelleaPinpointReadingNode`, `pinpoint/mellea_reading.py`). One
model call, shown the filing around the citation with the target marked
between `«` and `»` -- enough of it to see a string cite and which member the
target is -- and the page with its neighbours. It answers with quotations
from each: the words in the filing that state what the target is cited for
(`attribution`, with whether they are the citation's own, shared by a string,
or no page-level claim at all), and the passage on the page on that subject
(`passage`, with where it is), the factual relation between them
(`same_content`, `related_subject`, `none`), whose words the passage is
(`voice`: the court, a dissent or concurrence, a party's argument, a lower
court, a quoted authority, a headnote), the signal word, and one sentence on
what the page discusses. Both quotations are located by the program before
anything is believed, with `mellea_lrc.text.fuzzy`; a reading whose quotations
are not in the texts it was shown is rejected and asked for again, and after
three turns is recorded as failed with whatever was located. No field asks
whether the page supports the filing, and the instruction says not to answer
that question.

**Resolution** (`PinpointResolutionNode`). What was found, with both sides
located: the attribution's span in the filing and the passage's span in the
page text, the opinion and page it is on, and the voice.

| outcome | means | false |
|---|---|---|
| `quote_on_page` | the filing's quoted words are on the cited page | |
| `quote_elsewhere` | in the opinion, on another page, which is named | yes |
| `quote_absent` | in none of the cluster's opinions, and the page carries no passage with the same content | yes |
| `quote_altered` | not the opinion's words as written, though the cited page carries the same content: a misquotation, shown side by side | yes |
| `quote_in_opinion` | in the opinion, whose text carries no page markers, so the page cannot be told | |
| `passage_on_page` | the page carries a passage on the filing's subject; both shown | |
| `passage_adjacent` | the passage is a turn away, on the page before or after | |
| `passage_elsewhere` | the filing's own sentence, copied without quotation marks, is in the opinion on another page, which is named | yes |
| `passage_contradicts` | the page states the opposite of the filing's words, plainly from the two texts; both shown | yes |
| `passage_absent` | nothing on the cited page or beside it concerns the subject | yes |
| `passage_in_opinion` | the opinion, read whole for want of page markers, carries a passage on the subject | |
| `passage_absent_from_opinion` | nothing in the whole opinion concerns the subject | yes |
| `not_testable` | no page-level claim of the citation's own: `see generally`, a `citing` parenthetical, a bare string share | |
| `undetermined` | the reading did not pass its guards, or the evidence points both ways | |
| `not_retrieved` | out of scope, or no page could be cut | |

Nothing here says a page supports a proposition. A pin cite is called false
only on a fact, and `defect_kinds` names it in three words, the last two of
which may both apply: `irrelevant` (nothing in the cited opinion, read
whole, concerns what the filing cites it for), `wrong_page` (the thing is in
the opinion on a page other than the one cited, which is named), `misquote`
(what the filing attributes to the page differs from what the page says:
words in quotation marks that are not the court's, a passage that says the
opposite, or a claim the page only partly carries, with the missing words
checked against the whole opinion). `outcome_message` says how. When the
page reading finds nothing, the whole opinion is read once more before
irrelevance is called, and a passage found elsewhere names its page. The
program decides the quotations before the model is consulted, and a
quotation absent from every opinion of the case decides however short it is.

## The route

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

The docket's court is the one field the record states in a single place, and
it is sometimes wrong: `Beery v. Hitachi`, 157 F.R.D. 477, is filed under
`cand` with the docket number `No. CV 93-4868 DT (Ex)`, the Central District
of California's form. So every docket read gets a second witness, in
`validation/identity/docket_number.py`: the number's format, printed by the
deciding court and copied with the opinion. It reads the level a form fits
(`18-CV-4418` is a district court's; a bare `13-2316` is a court of appeals'
or a bankruptcy court's, which print the same form), a court where the
convention is distinctive (the First Circuit's `P`, the Second Circuit's
`-cv`, the Federal Circuit's four-digit year, the five-digit sequences of the
Fifth, Ninth and Eleventh, C.D. Cal.'s lowercase-`x` magistrate token, S.D.
Tex.'s division letter), and the judge's initials where the number carries
them. State appellate numbers carry `CV` too, so a type token alone reads as
nothing. The node records `match`, `mismatch` or `unavailable` between the
number and the court field and decides nothing: it is there so the two
witnesses can be measured against each other over a corpus. courts-db types
39 federal district courts `appellate`, so the federal level is read from the
court's name.

**A root cited by docket number** -- `Reyes v. Pac. Bell, No.
1:25-cv-05745-RPK (E.D.N.Y. Oct. 31, 2024)` -- has no page to look up, and
its court and docket number are a key instead. `validation/docket_lookup/`
asks two archives the key, deterministically and without a model:
CourtListener's docket index, scoped to the court, and the Government
Publishing Office's United States Courts Opinions (`govinfo/`, needing
`GOVINFO_API_KEY`), fed by the court itself under the E-Government Act. They
are fed oppositely -- one holds the docket sheet and what somebody bought
from PACER, the other the opinions the court deposited, publication aside --
so each answers what the other cannot, and a decision one holds on a day is
a fact the other's silence does not undo. A docket number without a court is
refused rather than guessed, since every district has one like it. The
caption that comes back is compared with the filing's parties by the same
rule a reporter record gets: the case confirms, or it is a different case
under that key (`1:19-CV-362` in the Middle District of North Carolina is
Peerless Insurance v. Innovative Textiles, not Calderon v. GEICO), and
nothing under the key in any archive defers the root to search. The
`DocketIdentityNode` carries every archive's answer and every decision they
hold, dated, and the resolution carries the docket id and the package id.

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
cluster, the later root records the earlier one as its authority; both stay
roots, since what the filing stated does not change, and every return still
points at the root whose identifier it restates. When they resolve
differently, they remain two authorities.

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
