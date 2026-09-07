# Agentic retrieval: make the whole search stage a loop

The brief for the validation side of this branch: what is built, what is
designed, and what has to be measured before the rest is built.
`agentic-search-population.md` carries the counts and `open-search-loop.md`
the loop's design.

## 1. Where this stands

The branch `validation-summary` is the validation side as of 2026-09-07,
based on `preprocessing-and-extraction-summary` (b176d3b), whose citation
tree, pin-cite spans and reporter and date objects it depends on. Two stages
are built, run and documented in `docs/Validation.md`; one is designed and
handed over here.

1. **Identity** (`validation/identity/`), built and run. Once per root of the
   citation tree it establishes which case the authority names: exact
   lookup, a rule guard on every record at the page (case name with variant
   and misspelling told apart, court with the reporter's family and the
   docket number as a second witness, date with the archive's other dates
   read when the plain date disagrees), one composite model judgement when
   the rules cannot settle it, and every correction written onto the record
   with the trace node that justifies it. Four outcomes: `confirmed_identity`,
   `wrong_identity` (with reason and fields), `ambiguous_identity`,
   `defer_to_search`. On `extraction-v2.0`: 397 roots, 270 confirmed, 36
   wrong, 1 ambiguous, 90 deferred. Every labelled `WRONG_IDENTITY` the
   archive holds a page for is caught.
2. **Pinpoint** (`validation/pinpoint/`), built and run, over the whole tree:
   every citation naming a page under an established identity -- the full
   citation and each `Id.`, short form and reference -- is read beside the
   reporter page cut from the archive. One model call per pin cite, both of
   its quotations located by the program before anything is believed; a
   second call over the whole opinion before irrelevance is called. Never
   says a page supports the filing. False on three facts, `irrelevant`,
   `wrong_page`, `misquote`, the last two not exclusive. On the bench: 300 in
   scope, about 35 called false, 11 of the 22 labelled `WRONG_PINCITE`
   caught, 6 shown side by side and not called because the court's finding
   was a judgement about the holding.
3. **Open search**, designed and not built. This is the handover. Its
   population and its contract are §1a and §1b below; `open-search-loop.md`
   is the loop's design and §§2-6 the constraints.

### 1a. The deferred population, from the committed identity run

`data/runs/extraction-v2.0-identified` (the datasets repo tracks it). Every
root the identity stage did not establish:

    defer_to_search  not_found        83     the lookup returns no cluster
    defer_to_search  docket            6     a docket number, no reporter locator
    defer_to_search  undeterminable    1     the judgement could not read a name
    ambiguous_identity  crowded_page   1     more records at the page than a
                                             judgement is shown, none agreeing

By what the filing wrote, the 91:

    Westlaw and LEXIS numbers         54     the archive has no lookup for these
    docket numbers                     6     `validation/identity/docket.py`
                                             documents the RECAP route, unbuilt
    printed reporters the archive
      holds nothing at                31     F. Supp. 3d 12, B.R. 4, A.D.3d 4,
                                             F.3d 2, F.R.D. 2, one each of F.4th,
                                             F.2d, F. App'x, U.S., S.E.2d,
                                             N.Y.S.3d, NY Slip Op

131 pin cites hang off the deferred roots and wait on them: the pinpoint
stage runs on any root the search route resolves, unchanged.

A population the counts above do not include, because it never enters the
tree: a case named with a court and a year and no locator at all --
`Akiachak Native Community v. U.S. Department of the Interior (D.D.C. 2016)`
in document 013. eyecite extracts nothing without a reporter, so no record
exists, and two of the 22 labelled `WRONG_PINCITE` entries are of this shape
(`authority: null` in `annotations.json`). Whether extraction should emit a
name-only citation as a `ReferenceCitation` carrying the court and year is
the extraction agent's call; if it does, the search route is what resolves
it, and the pinpoint stage then has a record to hang a finding on.

Read these against the labels before designing: 21 of the 51 labelled
`WRONG_IDENTITY` are deferred `not_found` -- fabricated Westlaw numbers and
pages that hold nothing -- and the archive cannot demonstrate a fabrication,
only fail to find it. The route's first question is which of the 83 the
archive's *search* (as against its lookup) can reach, and which are false
because nothing anywhere holds them. `agentic-search-population.md` counted
this on the earlier bench; the counts above supersede its identity numbers.

### 1b. The contract with the stages either side

The search route is a stage between identity and pinpoint, over the records
whose `IdentityResolutionNode` is `defer_to_search` or `ambiguous_identity`.
It touches nothing else.

- **Input**: an `IdentifiedDocument` (`serialization/identified_document.py`
  reads the artifact back, records and traces intact). `document.roots`,
  `document.resolution_of(citation_id)`, and each record's `trace.nodes`
  carry what identity already did: the lookup node with every cluster the
  page returned, the candidate evaluations, the judgement and its grounded
  readings. Do not redo any of it.
- **Writing a result**: append nodes to the record with `record.append(node)`
  (a node's `depends_on` must name nodes already on that trace), then
  `record.resolve(Resolution(...))` once, and finally append an
  `IdentityResolutionNode` with `decided_by` naming the node that settled it.
  A field the search corrects on the filing's reading goes through
  `record.correct_field(...)`; a citation that turns out to belong to another
  authority through `record.reattribute(...)`. The pinpoint stage reads the
  resolution node's `resolved` property and the resolution's `cluster_id`,
  and needs the cluster's record (with its `citations` and `sub_opinion_ids`)
  on the trace, as identity's `CandidateEvaluationNode` or
  `ExactLocatorLookupNode` carries it -- put yours there in the same shape.
- **New node types** register in `serialization/validated_document.py`
  (`_NODE_TYPES`, `_OUTCOME_TYPES`, and a branch in `_deserialize_node` for
  any nested field), or the artifact will not read back. Tests in
  `tests/test_identity_stage.py` show a document built by hand and a fake
  archive; `tests/test_pinpoint_stage.py` shows a fake model.
- **Outcomes**: a search that establishes the case is `confirmed_identity`
  or `wrong_identity` with reason and fields, as identity writes them, so the
  pinpoint stage and the scores need no new case. A search that establishes
  the archive holds nothing -- which is not the same as the citation being
  false -- needs an outcome of its own; name it, do not reuse
  `defer_to_search`.
- **Run and score**: `evaluations/identity/run_extraction_artifacts.py` is
  the pattern (budgeted client, tally, `summary.txt`, `manifest.json` naming
  the commit); `evaluations/pinpoint/run_identified_artifacts.py` scores
  against `data/validation-v2.0/annotations.json` by authority span. Runs
  are committed in the datasets repo under `runs/`, never deleted; findings
  and questions go in `data/NOTE.md`, appended, with evidence per claim, and
  never edit another agent's entry.

## 2. Why search is the one stage that earns this

The rest of the pipeline is deterministic on purpose. Extraction and exact
lookup are functions: same input, same output, and dynamism buys nothing but
variance.

Search is different in kind. **The next query depends on what the last one
returned.** With 32 clusters at one page, which field separates them depends on
what those 32 have in common, and that is knowable only from having seen them.
That is the shape a loop exists for.

The loop's cheapest move costs no request, and on the ambiguous route the free
moves turned out to be the whole of it. Section 4 of
`agentic-search-population.md` measures them: merging duplicate records settles
84 of 94, the case name the filing wrote settles one more, and comparing the
court and year settles none, because the lookup endpoint returns no court field
at all. A loop is worth its cost only where a free move has been tried and
failed, which is why section 1 asks for the search route to be measured first.

So this is not a retreat from the project's architecture. It sharpens it:
deterministic where the answer is a lookup, agentic where the answer requires
search. Against the reference paper — dynamic everywhere — the claim becomes
"we measured where dynamism pays", which is stronger than either pole and is an
empirical result rather than a preference.

## 3. Open-endedness is the point, so do not design around reproducibility

An earlier note, `caselaw-archive.md`, rejected open web search partly because
a verdict resting on a search snippet cannot be reproduced. **Do not carry that
objection into this design.** It was the right standard for the deterministic
route and it is the wrong one here.

The reason is what open search is *for*. The printed archive covers everything
it holds, free and unmetered, and the fallback exists precisely for what it
cannot reach — chiefly 2019 onward, since the digitisation ends around 2020.
In that regime the alternative to non-reproducible evidence is **no evidence**,
and insisting on reproducibility collapses the component into the thing it was
built to go beyond.

What to do instead: **record provenance and let the reader judge.** Every
finding should carry where it came from, when, and what kind of source it was,
so a consumer can tell a bound-volume index from a search snippet. That is a
labelling obligation, not a gate.

Reproducibility then becomes a property worth *measuring* — run the same input
twice, see whether the verdict holds even though the trajectory differs — and a
divergence is a finding about the agent, not a bug to design against in
advance.

## 4. What the agent may trust

`experimental/web_refutation/domains.py` is on this branch with its 12 tests.
Its rule is not a ranking, and it matters:

**Trust is scoped by jurisdiction, not by hostname.** A court's site is
authoritative for its *own* decisions and says nothing about anyone else's. The
Ninth Circuit publishing Ninth Circuit opinions is the record; its silence
about a New York case means nothing.

| tier | who | may support a refutation |
|---|---|---|
| 1 | the deciding court, publishing its own decision | yes |
| 2 | another arm of government republishing official text | yes |
| 3 | an established archive transcribing official text | no |
| 4 | a commercial legal publisher | no |

Commercial sites are excluded deliberately: several now print generated
summaries beside transcribed text, and a result page does not say which is
which.

## 5. The constraint to design for from the first commit

**CourtListener search is not cacheable.** The query is model-generated, so
every reformulation is a fresh request against a budget of roughly 500 a day
across four tokens, arriving in staggered windows.

An agent that reformulates three times has tripled the cost of every unresolved
citation. Almost everything in this project's recent work has been
budget-bound, so:

- cap iterations explicitly rather than letting the model decide when to stop
- cache by normalised query, so two reformulations that differ in whitespace
  or term order cost once
- make the remaining budget an **input** to the agent, not something it
  discovers by being refused

Read section 4 of `exploration/AUDIT.md` on `experiment/general-explorations`
before designing the loop. In particular: CourtListener throttles on two
windows whose 429 bodies look nearly identical, one clearing in thirty seconds
and one in hours, and treating them alike costs most of a day.

## 6. LangGraph, for the loop only

The open-search loop is a state graph in LangGraph. The reason is not
persistence -- `CitationValidation` already gives an append-only, replayable
trace, and every node the loop runs is written back into it -- but enforced
transitions and model-chosen branching. The next move depends on what the last
query returned and on what kind of citation this is, so a model chooses it,
and the graph is what keeps the model to the moves that exist and the budget
each may spend. Written as a hand-coded decision tree the same logic would be
wrong at every leaf the tree did not anticipate.

Nothing before the loop uses it. The identity stage is a fixed sequence and a
plain function expresses it. Mellea makes every model call inside a graph node.

## 7. What is on this branch

- `validation/record.py` -- `CitationRecord`, the one mutable object, with
  `Resolution`, `Correction` and the date exploration
- `validation/identity/` -- the stage: `stage.py`, the rule guard, the
  composite judgement (`mellea_judgment.py`, `mellea_candidates.py`), case
  names, windows, dates, the reporter families, the docket number as a
  second witness to the court, and the docket stub
- `validation/pinpoint/` -- the stage: `pages.py` (the page along the
  reporter's pagination), `citing.py` (the filing window, strings, signals,
  quotations), `mellea_reading.py` (the one reading, grounded),
  `stage.py` (scope, retrieval, quotes, reading, the three kinds)
- `serialization/identified_document.py` -- the artifact both stages write,
  and `mellea-lrc identify --from-artifact`
- `evaluations/identity/` and `evaluations/pinpoint/` -- the runs and scores
- `text/fuzzy.py` -- the matcher that locates every quotation
- `search/narrowing.py`, unwired; `experimental/web_refutation/domains.py`,
  the domain tiers with 12 tests; `evaluations/agentic_search/`, the earlier
  population counts
- `docs/Validation.md`, this brief, `agentic-search-population.md`,
  `open-search-loop.md`, `identity-stage-on-the-bench.md`

Inherited from the extraction branch: the citation tree, co-location, the
reporter, date and pin-cite objects. Inherited from `main`: `courtlistener/`
(the client, cached through a proxy; the people, cluster, opinion and docket
endpoints), `validation/case_search/` with the single-shot query, and the
old pinpoint route under `validation/pinpoint_retrieval/`, superseded.

## 8. Where to read what already exists

- `docs/Validation.md` -- both stages, what each node means, how a result reads
- `exploration/notes/identity-stage-on-the-bench.md` -- the identity run read
  against the labels
- `data/NOTE.md` -- the note log between agents: the leg vocabulary for the
  archive (`lookup`, `cluster`, `docket`, `opinion`), what the datasets carry,
  every measurement to date with its evidence
- `data/validation-v2.0/pinpoint-domain-brief.md` -- the domain, for the
  pinpoint side
- `exploration/AUDIT.md` §4 on `experiment/general-explorations` -- the request
  budget and its two throttling windows; `caselaw-archive.md` and
  `open-ended-search.md` there too

## 9. Standing constraints

Nothing is committed or pushed to `origin` without asking; work goes to
`woody-fork`. No dataset is pushed anywhere. Run artifacts are committed in
the datasets repo (`data/`, a symlink in every worktree) and never deleted.
Never put dataset examples into a prompt. Never call a page or a case
"supported"; every finding is a fact the trace can show.
