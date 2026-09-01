# Agentic retrieval: make the whole search stage a loop

A brief for whoever builds this. The branch carries the domain tiers and
nothing else — the work is ahead of you, not behind.

## 1. What is being proposed

Today the pipeline searches once. It prepares query terms from the case name,
asks CourtListener, and takes what comes back. If that returns nothing useful,
the citation ends unresolved.

The proposal is to replace that with a loop that owns **the entire search
stage**, CourtListener included: issue a query, read what came back, and decide
what to do next — reformulate, widen, narrow, switch index, or go to the open
web. Then stop when it has an answer or has spent its budget.

## 2. Why search is the one stage that earns this

The rest of the pipeline is deterministic on purpose. Extraction and exact
lookup are functions: same input, same output, and dynamism buys nothing but
variance.

Search is different in kind. **The next query depends on what the last one
returned**, and "no results" is information that should change the query rather
than end the attempt. That is the shape a loop exists for.

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

## 6. On LangGraph

Justified, but not for the obvious reason. The loop is four or five states and
a plain `while` would express that.

What it actually buys is **trajectory persistence and replay** — being able to
store what the agent did and re-run it. Given section 3, that is the feature
that makes an agentic component auditable at all: you cannot reproduce the
search, but you can keep the record of it.

So: use it for the checkpointing, or do not use it. If the branch ends up
treating LangGraph as a decorated loop, drop the dependency — it is a second
orchestration model alongside Mellea and it should earn that.

## 7. What is on this branch

- `src/mellea_lrc/experimental/web_refutation/` — the domain tiers, 12 tests
- this brief

Everything else is on `main`: `courtlistener/search.py` and the transport
beneath it, `validation/case_search/` with the current single-shot query
preparation and the opinion and RECAP searches. Those are what the loop should
wrap rather than replace.

## 8. Where to read what already exists

- `exploration/notes/open-ended-search.md` — what the current fallback does,
  what it requires before running at all, and what it refuses to do
- `exploration/notes/caselaw-archive.md` — why the domain tiers are scoped by
  jurisdiction, and how the archive displaced the first attempt at this
- `exploration/AUDIT.md` §4 — the request budget and its two throttling windows

Both notes are on `experiment/general-explorations`.

## 9. Standing constraints

Nothing is committed or pushed to `origin` without asking; work goes to
`woody-fork`. No dataset is pushed anywhere. Everything under `local/` is
git-ignored.
