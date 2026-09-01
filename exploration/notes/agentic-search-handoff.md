# Agentic retrieval: make the whole search stage a loop

The design brief for the search loop. `agentic-search-population.md` carries the
counts it rests on and should be read alongside it, because those counts have
not yet found the loop a population worth its cost.

## 1. What is being built, and what has not yet earned it

The search stage becomes a loop that owns **the whole stage**, CourtListener
included: issue a query, read what came back, and decide what to do next —
narrow the candidates already in hand, reformulate, widen, switch index, or go
to the open web. It stops when it has an answer or has spent its budget.

Two candidate populations have been measured over 659 distinct locators, and
neither justifies the loop on its own.

**The unresolved locator**, where CourtListener holds nothing at the cited page,
is 94 citations. 91 are labelled sound, 70 name a Westlaw or LEXIS record the
search endpoint cannot reach at all, and 15 are reporter citations a name search
could act on. Sections 2 and 3 of `agentic-search-population.md`.

**The ambiguous locator**, where CourtListener returns more cases at the page
than the pipeline will look at, is 94 citations, and three moves that send no
request settle 85 of them. The nine left over are tables of unpublished
decisions, and section 5.1 of `agentic-search-population.md` argues that six of
those nine are decidable from records the lookup already returned.

What remains untested is the **search route** itself: the 79 locators the lookup
found nothing for, and what a query returns when it runs. A search result set
carries a court and a filing date where a lookup record carries neither, and a
query returning 111 results is deferred whole today. Section 7 of
`agentic-search-population.md` item 2 is the measurement that would settle it,
and unlike everything else here it costs request allowance.

**Do not build the loop before that measurement.** Everything the ambiguous
route needed turned out to be free, and a loop written for it would have been a
loop for nine citations.

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
