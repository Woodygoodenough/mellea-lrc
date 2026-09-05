# Agentic retrieval: make the whole search stage a loop

The brief for the validation side of this branch: what is built, what is
designed, and what has to be measured before the rest is built.
`agentic-search-population.md` carries the counts and `open-search-loop.md`
the loop's design.

## 1. Where this stands

The branch is based on `preprocessing-and-extraction-summary`, whose citation
tree and date and reporter objects the validation side now depends on. The
stages, in the order they run and the order they are being built:

1. **Identity**, built. `validation/identity/` runs once per root of the
   citation tree, establishes which case each authority names, and writes
   corrections onto a mutable record with the trace node that justifies each.
   `docs/Validation.md` describes it.
2. **Pinpoint**, not yet reworked. Runs per occurrence, including every return
   visit, once identity is established. Whether the existing pinpoint route
   changes is open.
3. **Secondary citations**, not started. Primarily a pinpoint check per return
   visit; a pinpoint that fails on a return visit is how a misattribution in
   the citation tree shows up.
4. **Open search**, designed and not built. Its population is every root the
   identity stage left `unresolved` or `ambiguous`. `open-search-loop.md` is
   the design, and section 4 of it names the measurement that has to come
   first: whether a full-text search for opinions that quote the locator
   recovers the vendor-number citations the cluster search cannot reach.

The counts in `agentic-search-population.md` still hold and are the reason the
loop is last. Nothing in the ambiguous route wanted a query, and the unresolved
route on LePhantomCite is mostly vendor numbers. The citing-opinion move is the
first thing that could change that reading, and it costs 85 requests to find
out.

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

- `validation/record.py` -- `CitationRecord`, the one mutable object
- `validation/identity/` -- the stage, the rule guard, the composite judgement,
  the docket stub
- `serialization/identified_document.py` -- the artifact, and
  `mellea-lrc identify --from-artifact` to produce one from extraction's
- `evaluations/identity/run_extraction_artifacts.py` -- the stage over a whole
  extraction run, stopping when uncached responses exceed a budget
- `validation/duplicate_clusters.py` and the merge in `candidate_selection.py`
- `search/narrowing.py`, unwired, waiting on the search-route measurement
- `experimental/web_refutation/domains.py` -- the domain tiers, 12 tests
- `evaluations/agentic_search/` -- the two population counts, free of the API
  allowance
- this brief, `agentic-search-population.md`, and `open-search-loop.md`

Inherited from the extraction branch: the citation tree, co-location, the
reporter and date objects, and the adjudication layer whose model half is
unfinished. Inherited from `main`: `courtlistener/`, `validation/case_search/`
with the single-shot query, and the pinpoint route.

Not here: `caselaw/cap_index.py` and `evaluations/lephantomcite/locator_probe.py`,
on `experiment/general-explorations`.

## 8. Where to read what already exists

- `exploration/notes/open-ended-search.md` — what the current fallback does,
  what it requires before running at all, and what it refuses to do
- `exploration/notes/caselaw-archive.md` — why the domain tiers are scoped by
  jurisdiction, and how the archive displaced the first attempt at this
- `exploration/AUDIT.md` §4 — the request budget and its two throttling windows

Both notes are on `experiment/general-explorations`.

## 9. Standing constraints

Nothing is committed or pushed to `origin` without asking; work goes to
`woody-fork`. No dataset is pushed anywhere, and run artifacts stay in the
git-ignored working directory.
