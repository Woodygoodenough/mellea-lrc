# 1. Relevant papers

## 1.1 *Who Checks the Citations? Benchmarking Legal Hallucination Detection*

Liu, Stammbach, and Henderson. arXiv preprint, arXiv:2606.21155v2 [cs.CL],
August 2026. It is not a conference paper.

## 1.2 *Large Legal Fictions: Profiling Legal Hallucinations in Large Language Models*

Dahl, Magesh, Suzgun, and Ho. *Journal of Legal Analysis*, 16(1), 64–93,
2024. DOI: 10.1093/jla/laae003.

It systematically measured legal hallucinations in public-facing LLMs across
jurisdictions, courts, time periods, and cases, by giving models case names and
citations, asking legal questions, and checking their answers against external
records or contradictions between repeated answers.

**The study therefore tests the models’ parametric knowledge of case law rather
than their ability to analyze a case supplied in context.**

**Conclusion:** *Who Checks the Citations? Benchmarking Legal Hallucination
Detection* is the most comparable paper for our project.

# 2. Benchmark

## 2.1 LePhantomCite benchmark

The paper introduces the LePhantomCite benchmark.

LePhantomCite contains 1,300 short entries. The underlying cases and some source text are real, but the benchmark defects are constructed: 1,000 are injected into brief excerpts, and 300 are LLM-generated propositions manually checked against real cases. It does not contain naturally occurring, court-adjudicated citation defects.

The full benchmark contains **4,499 citation instances** and **1,107 labelled defects**. The 300-entry subset contains **300 citation instances**, one per unique case.

| hallucination type | total | how it is obtained |
|---|---:|---|
| non-existent citation | 158 | Replace the reporter, volume, or page with an implausible citation. |
| case-name mismatch | 189 | Replace the case name or reporter citation with that of another real case. |
| incorrect pincite | 177 | Replace an existing pinpoint with a different page from the same opinion. |
| verbatim misquote | 167 | Use Qwen3-32B to replace one or two quoted words with synonyms. |
| content misrepresentation | 416 (258 from 300) | Use Qwen3-32B to change the holding or proposition. |
| **total** | **1,107** | |

The 300 proposition entries come from a separate central-holding task. An LLM
was given a real case citation and year and asked for the case's primary
holding. LePhantomCite selected one entry per case, reformatted the output with
the case name, citation, and year, and checked it against Westlaw. Of the 300,
258 were judged hallucinated and 42 were not.

## 2.2 Our benchmark plan

**Primary conclusion:** Our dataset consists only of real legal documents with
naturally occurring defects, while LePhantomCite is constructed from injected
defects and LLM-generated propositions.

We will scale the benchmark to several hundred real filings whose false
citations were identified in court proceedings. We will build a miner over
CourtListener's full-text search to find orders discussing fabricated or
nonexistent citations, resolve each order to the offending docket filing, and
use the order's quoted citation to pre-align candidate spans for human
verification. The existing tracker can serve as a recall check, while the
corpus remains independently recoverable from public records.

The problem types need to be reconsidered for naturally occurring,
court-adjudicated false citations rather than copied from LePhantomCite's
injected defect design.

# 3. Architecture

## 3.1 Their architecture

LePhantomCite uses a sequential agent rather than a fixed validation graph.
The agent receives a brief excerpt containing citations, keeps a running
assessment of those citations, chooses what to investigate next, observes the
result, updates its assessment, and repeats until it submits a final list of
hallucinated segments or reaches the 30-step limit.

Their intended route for a reporter-style citation is citation lookup first,
then opinion access and local text search when a result is found. CourtListener
search and open-web search provide fallbacks when the direct lookup is
inconclusive or the citation is not available. The agent can read the opinion
in line windows, but the interface does not provide a dedicated page-aware
pinpoint operation.

### 3.1.1 State management

The primary state management is belief rewriting and execution history, rather
than naïve context appending. BOED guides the choice of the next action.

The released implementation uses separate prompts for belief updates, action
selection, and the final prediction. After each action, a belief-update call
rewrites the agent's cumulative task beliefs. An action-selection call then
chooses exactly one next action in structured JSON. The environment executes
that action and returns an observation. The action, parameters, observation,
and updated beliefs are kept in the episode history. On the final step, the
prediction prompt forces `PROVIDE_FINAL_RESPONSE`.

The agent's action space includes:

- `COURTLISTENER_CITATION_LOOKUP` for reporter-citation resolution;
- `OPEN_COURTLISTENER_SEARCH` for case or citation search;
- `ACCESS_COURTLISTENER_OPINION` for fetching an opinion;
- `SEARCH_LOCAL_OPINION` for searching fetched opinion text;
- `READ_DOCUMENT` for reading selected line windows;
- `OPEN_WEB_SEARCH` for open-web fallback searches;
- `EDIT_SCRATCHPAD` for notes;
- `THINK` for internal reasoning; and
- `PROVIDE_FINAL_RESPONSE` for the final hallucination list.

### 3.1.2 Open web search

Their `OPEN_WEB_SEARCH` is shallow: it immediately delegates retrieval to
Google/SerpAPI. The query is the only substantive control; the other controls
are minor search parameters. It returns search results and snippets without
domain restrictions, source vetting, deep page reading, or evidence-to-claim
provenance.

We will include open web search, but our approach will be more complex and will
involve domain-priority designs.

## 3.2 Pinpoint citation handling

Our pinpoint citation route resolves page structure explicitly, while their
handling is implicit in the agent's opinion search and line-window reading.
We should run a few cases to observe the behavior of `pinpoint_cite` in their
system.

## 3.3 Tracing

LePhantomCite traces an agent trajectory. Its BOED agent maintains a natural-
language belief state about the citations and updates it after each
observation. Its actions include citation lookup, CourtListener search and
opinion access, local opinion search, line-windowed document reading, web
search, `THINK`, scratchpad editing, and final response submission. The
implementation records the action sequence, tool parameters, observations,
beliefs, and step count. The paper reports action distributions and a few
example trajectories, but not a complete evidence-linked reasoning trace for
every case.

Our system has near-complete provenance tracing:

`citation span → lookup → candidate → field checks → page evidence → proposition → semantic verdict → final aggregation`

Each node carries an ID, dependencies, outcomes, source spans, evidence
quotes, and concise reasoning. This records the evidence needed to reproduce
and justify a conclusion rather than hidden chain-of-thought.
