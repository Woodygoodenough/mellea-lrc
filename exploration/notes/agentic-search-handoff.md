# Agentic retrieval: make the whole search stage a loop

The design brief for the search loop. `agentic-search-population.md` carries the
counts it rests on and should be read alongside it.

## 1. What is being built

The search stage becomes a loop that owns **the whole stage**, CourtListener
included: issue a query, read what came back, and decide what to do next —
narrow the candidates already in hand, reformulate, widen, switch index, or go
to the open web. It stops when it has an answer or has spent its budget.

The case it exists for is the **ambiguous locator**: CourtListener returns more
cases at the cited page than the pipeline will look at, and something has to
decide which one the filing meant. `validation/candidate_selection.py` caps
candidate evaluation at three, so a locator with more clusters than that is
deferred with zero candidates evaluated. That is 23 of the 1,334 citations in
the corpus measured in `agentic-search-population.md`, and the node's own
message names what is missing: "further refinement is needed before selecting
candidates."

The case it does **not** exist for is the unresolved locator — CourtListener
holding nothing at the cited page. Section 2 of `agentic-search-population.md`
counts that bucket at 94, of which 91 are labelled sound, 70 name a Westlaw or
LEXIS record that the search endpoint cannot reach at all, and 15 are reporter
citations a name search could act on.

## 2. Why search is the one stage that earns this

The rest of the pipeline is deterministic on purpose. Extraction and exact
lookup are functions: same input, same output, and dynamism buys nothing but
variance.

Search is different in kind. **The next query depends on what the last one
returned.** With 32 clusters at one page, which field separates them depends on
what those 32 have in common, and that is knowable only from having seen them.
That is the shape a loop exists for.

The loop's cheapest move costs no request. The clusters are already in hand from
the locator lookup, so narrowing them by case name, year or court is free, and
the budget in section 5 covers only what follows when that fails to separate
them.

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

## 6. No LangGraph

The loop is four or five states and a plain `while` expresses that. The one
thing worth a dependency would be **trajectory persistence and replay** —
storing what the agent did and re-running it — because given section 3 that is
what makes an agentic component auditable at all: the search cannot be
reproduced, but the record of it can be kept.

The project already has that. `CitationValidation` is an append-only sequence of
frozen typed nodes, each with a `node_id` and a `depends_on` tuple, and `append`
refuses a duplicate identifier or an unknown dependency. Every node round-trips
through `serialization/validated_document.py` on a type-name registry. A loop
written as nodes in that model is persisted, replayable and type-checked without
a second orchestration model beside Mellea.

What the node model does not do is resume a run from a checkpoint partway
through. Nothing in this design needs that.

## 7. What is on this branch

- `src/mellea_lrc/experimental/web_refutation/` — the domain tiers, 12 tests
- `evaluations/agentic_search/search_population.py` — the counts in
  `agentic-search-population.md`, re-runnable against a probe file and free of
  the API allowance
- this brief and `agentic-search-population.md`

Inherited from `main`: `courtlistener/search.py` and the transport beneath it,
`validation/case_search/` with the single-shot query preparation and the opinion
and RECAP searches, and `validation/candidate_selection.py` with the limit
section 1 names. Those are what the loop wraps rather than replaces.

Not here, and needed by section 7 of `agentic-search-population.md`:
`caselaw/cap_index.py` and the checks built on it, and
`evaluations/lephantomcite/locator_probe.py`, all on
`experiment/general-explorations`.

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
