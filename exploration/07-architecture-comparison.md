# Their implementation, read line by line

Read from a clone of `princeton-polaris-lab/legal-hallucination-agent`
(see the README for the command)
(`princeton-polaris-lab/legal-hallucination-agent`, last commit 3ca3249,
2026-04-27, ~17k lines of Python).

**No LICENSE file.** Public on GitHub, but unlicensed means all rights
reserved by default. We can read it, cite it, and reimplement from the paper.
We cannot vendor it, redistribute it, or copy code out of it. Ask them if we
want more than that; they are academics and will probably say yes.

Dataset: `huggingface.co/datasets/ai-law-society-lab/Legal_Phantom_Citation`.
Project page: `princeton-polaris-lab.github.io/legal-hallucination-webpage/`.

---

## What it actually is

`polaris_agents` is a general-purpose Bayesian Optimal Experimental Design
agent framework. Legal hallucination checking is one *environment* plugged into
it (`environments/legal_hallucination_checker.py`), alongside the machinery for
other tasks. The legal-specific content is roughly: one environment class, one
domain-knowledge prompt module (185 lines), and a CourtListener action module
(616 lines).

The loop, from `agents/boed.py`:

1. `update_beliefs(observation, action)` — an LLM call that rewrites a
   natural-language belief string, budgeted at **10,000 tokens**.
2. `select_action(observation)` — a second LLM call choosing one of nine
   actions, budgeted at 4,096 tokens.
3. Environment executes the action, returns an observation.
4. Repeat, to `environment.max_steps: 30`.
5. `get_current_prediction()` — a final LLM call emitting a JSON array of
   hallucinated text segments.

The nine actions: `THINK`, `OPEN_WEB_SEARCH`, `OPEN_COURTLISTENER_SEARCH`,
`COURTLISTENER_CITATION_LOOKUP`, `ACCESS_COURTLISTENER_OPINION`,
`SEARCH_LOCAL_OPINION`, `READ_DOCUMENT`, `EDIT_SCRATCHPAD`,
`PROVIDE_FINAL_RESPONSE`.

Config: `gpt-5`, **`temperature: 0.8`**, `seed: null`, `search.top_k: 3`.

---

## The seven differences that matter

### 1. There is no deterministic extraction stage

No eyecite. No parser of any kind. The agent reads the brief and writes
citations into a natural-language belief string, and the prompt teaches it
citation format in prose:

> "Typical format is Case Name, Volume Reporter Page (e.g., 557 F.2d 170). The
> part after the comma is the reporter citation; 'at' introduces a pincite."

Consequence for measurement, not just for accuracy: a citation the agent never
noticed and a citation it noticed and judged wrongly are **the same event** in
their metric. Their F1 cannot separate them. Ours is separated by construction,
which is exactly the argument already written in `evaluations/README.md` — a
system that never finds a citation and one that finds it and judges it wrongly
fail differently, and one combined score hides which happened.

Our extraction number (100% precision, 94.8% recall on 594 gold identifiers) has
no counterpart anywhere in their paper.

### 2. The locator lookup is advice, not structure

They have the same CourtListener citation-lookup endpoint we do
(`execute_courtlistener_citation_lookup`, `main.py:471`). The prompt marks it
important:

> "### Case-law search policy (important) — If a **reporter-style citation** is
> present, **use COURTLISTENER_CITATION_LOOKUP first**."

But it is one of nine actions the model may or may not select. In our pipeline
the exact locator lookup is unconditionally the first operation and its outcome
*determines the route* — found, not found, ambiguous, or unsupported. The same
API call is a **guarantee** in one architecture and a **suggestion** in the
other. That distinction is the whole thesis in miniature.

### 3. State is a regenerated string, not an append-only record

Their belief state is one natural-language blob, rewritten by an LLM every step.
Their README says the design makes the agent "less likely to forget previously
checked citations" — which concedes that forgetting is the failure mode being
managed.

The belief-update prompt asks for exactly that: *"a numbered or bulleted list.
For each item note: (1) the citation, quote, or holding, (2) status: pending,
verified as correct, or hallucinated."* Nothing enforces that item 7 survives
into the next rewrite.

Our node list is append-only with explicit `depends_on` edges and nothing
overwritten. Information monotonicity is a structural property here and a
prompt-level aspiration there. This is a real theoretical claim and it is
cheap to demonstrate empirically: instrument their belief string across steps
and count citations that enter and then vanish.

### 4. Evidence grounding is much looser

Their quote check (`legal_hallucination_checker.py:57-60, 665-687`) slides a
window over the opinion with `difflib.SequenceMatcher`:

```
SEARCH_LOCAL_OPINION_FUZZY_MIN_RATIO = 0.6
SEARCH_LOCAL_OPINION_FUZZY_STEP = 30
SEARCH_LOCAL_OPINION_MAX_SNIPPETS = 3
```

A 0.6 similarity ratio accepts a window that differs substantially from the
query. Their own taxonomy defines a verbatim misquote as *"one or two words
replaced with semantic synonyms"* — which is a change well inside a 0.6
threshold. The grounding mechanism is loose enough to confirm the very error
type it is meant to catch, and the step of 30 characters means the window
boundaries are arbitrary relative to the passage.

Ours requires the model's evidence quote to ground in the retrieved text, stores
`evidence_span`, `evidence_match_method` and `evidence_match_score`, and
**discards a verdict the model cannot ground**. That gate has no counterpart in
their design.

(Ours is not perfect either — [`notes/further-improvements.md`](notes/further-improvements.md) records that our
fuzzy grounding returns the first highest-scoring window and can identify the
wrong occurrence of a repeated passage. The difference is that ours is a known,
documented, bounded defect and theirs is the default behavior.)

### 5. The answer space is binary, and they measured what that costs

Their final output is a JSON array of hallucinated text segments. A citation is
in the list or it is not. There is no third answer.

Their own error analysis then reports the consequence: for correct citations
that CourtListener does not index, **GPT-5 flagged 24.0% as hallucinated, and
Qwen3.5 flagged 65.9%.** They are penalized for it in precision, which is why
GPT-5's precision is 47.6% against 82.8% recall.

That failure class **cannot occur in our architecture**. The aggregation only
asserts a mismatch on positive contradicting evidence; missing evidence
abstains. `not_found` is its own outcome and never becomes a verdict. This is
not "we prompted better" — it is a different answer space, and it is the
strongest single argument the project has.

### 6. The scored unit is a string, matched by substring

`evaluation/hallucination_checker_evaluator.py`:

> "A ground truth item is a 'hit' if it is a substring of a predicted item (or a
> predicted item is a substring of it)."

Plus an ellipsis wildcard. So a prediction naming the whole sentence matches a
ground truth naming just the citation, and vice versa.

This is precisely the failure mode our dataset README argues against when it
rejects full citation extent as the annotation unit: *"reasonable systems
disagree, so a benchmark keyed on full extent penalises disagreement about
boundaries rather than about citations."* Their matching rule papers over that
by being permissive in both directions, which trades one bias for another —
over-long predictions are never penalized for imprecision.

Our unit is a normalized identifier plus an overlapping span. Make this point
carefully and without smugness; it is a methodological disagreement, not an
error on their part.

### 7. Cost

Their loop makes at least two LLM calls per step (belief update at 10k tokens,
action selection at 4k), plus a final prediction call. At the reported average
of 15.3 steps that is **roughly 31 LLM calls per excerpt**, on GPT-5.

Their 1,000 injected-error excerpts carry 4,499 citation instances — about 3.5
citations per excerpt — so call it **~9 frontier-model calls per citation**.

We run ~1,523 LLM calls for 894 citations across 26 full filings: **~1.7 calls
per citation**, on an 8B or 30B model, locally.

State the assumptions when you publish this arithmetic. It is an estimate from
their config and reported step count, not a measurement, and it should be
labelled as one.

Also: `temperature: 0.8`, `seed: null`. Their tables carry ± error bars for that
reason. Ours is fixed at 0.0 and the evaluation README forbids anything else.

---

## Where their design is genuinely better than ours

This section is not a formality. Two of these are serious.

**They have open web search; we do not.** `OPEN_WEB_SEARCH` via SerpAPI, plus
fallback logic that escalates to it when CourtListener is inconclusive. A real
citation absent from CourtListener is permanently `not_found` for us and
findable for them. Their 82.8% recall against our abstentions is largely this.

This is the honest shape of the head-to-head result: **we should expect much
higher precision and lower recall.** Predict it before running it, say so in the
paper, and frame it as the coverage/safety trade-off it is — which is exactly
Direction E, and exactly the limitation their own paper raises about database
access.

**Their architecture generalizes and ours does not.** `polaris_agents` is
task-agnostic; legal citation checking is an environment plugged into it.
Adding statutes to their system is a prompt and a tool. Adding statutes to ours
is a new subgraph of typed nodes. A reviewer will call our fixed graph brittle
and they will be partly right. The answer is that the graph is a *specification*
of what verification means for this citation type, and that specification is the
source of the safety properties — but that answer concedes generality, so
concede it plainly rather than arguing.

**They evaluate five models plus Claude Code; we evaluate ours.** Their
experimental design is simply broader than ours today.

---

## The two results that decide whether the thesis survives

### Claude Code scores 76.1% precision, 68.8% F1 — the best in their paper

With a general-purpose agent harness and no legal-specific engineering. That is
a direct threat to "structured decomposition beats agentic search": it suggests
a sufficiently good general agent beats a specialized pipeline.

Our answer cannot be F1. It has to be precision and cost together:

- if our precision on their benchmark exceeds **76.1%**, the safety claim holds;
- if our cost per citation is far under theirs, the efficiency claim holds;
- if neither, the thesis needs rewriting, and better to learn that in September
  than in a review.

Run this before committing to the framing.

### On incorrect pincites, GPT-5 agentic gets 18.2% recall

Their own summary: *"no models can reliably detect wrong pincites."* Every other
category is 82–95%; this one collapses.

That is precisely the category our pinpoint check exists for. And our pinpoint
check is currently 3-of-9 wrong. **We do not yet have any evidence that we are
better at the hard category**, and it is the only category where being better
would be decisive.

So the first experiment is not the full head-to-head. It is:

> Run our pinpoint check against the incorrect-pincite subset of LePhantomCite,
> and compare to 18.2%.

That subset is small, the dataset is public, and it is roughly a day of adapter
work rather than a week. It has the highest information value per hour of
anything in the plan:

- **Beat 18.2% clearly** → that is the paper's headline, and Direction C
  (proposition decomposition) becomes the extension rather than the rescue.
- **Lose or tie** → Direction C is mandatory, the JURIX paper stays scoped to
  identity verification and abstention, and nothing is claimed that cannot be
  defended.

Either outcome is worth having before 5 September.

---

## What to write in the paper

Not "our architecture is better." The defensible sentence is narrower and
stronger:

> Agentic verification and structured verification fail in different directions.
> An agent that decides for itself when to look something up will assert falsity
> when it cannot find a source — measurably, 24% of the time for the strongest
> model tested, and 66% for a mid-sized open one. A pipeline that makes the
> lookup unconditional and treats absence as its own outcome cannot make that
> error at all, and pays for it in recall on authority the archive does not
> hold. The choice between them is not accuracy but which error a legal user can
> tolerate, and the answer in this domain is not symmetric.

That claim is supported by *their* published numbers plus *our* architecture, it
survives losing the head-to-head on F1, and it is not a claim anyone has made.

Then add the cost figure, and the pincite result if it goes our way.

---

# Addendum: pincite is not a support question, and that is our opening

Written after downloading the dataset (**CC BY 4.0**,
390 eval + 910 aux_train, full generation code included).

## They have both, as separate categories

| type | what is injected | eval records | GPT-5 agentic recall |
|---|---|---:|---:|
| non-existent citation | `133 S. Ct. 1017` → `446 Cal. Rptr. 4th 183` | 32 | ~95% |
| case name mismatch | `Cinel v. Connick, 15 F.3d 1338` → `Boone v. Vinson, 15 F.3d 1338` | 63 | ~90% |
| **incorrect pincite** | **`830 F.3d at 514` → `830 F.3d at 511`** | **53** | **18.2%** |
| verbatim misquote | one or two words replaced with synonyms | 42 | 82.6% |
| **content misrepresentation** | **holding altered to change its legal meaning** | **131** | **84.0%** |

So the support question is `content_misrepresentation`, and GPT-5 already does
well on it — 84%. Attacking that category head-on is not where the opening is.

`incorrect_pincite` is not a support question at all. It is a **page-number
mutation**: same case, same quote, one digit changed. The system has to decide
that the material is not on the page the brief names.

## Their 18.2% is an architectural absence, not a model limitation

There is **no pagination handling anywhere in their codebase**. Grepping the
whole repo for pagination, star pages, or page numbers returns nine hits and
every one of them is inside a prompt string. One of those prompts asks the model
to *"determine whether the pincite (page number) accurately reflects the location
of the quoted language or proposition within the cited opinion."* Another tells
it to **strip** the pincite before searching: *"Never include pincites or page
numbers following 'at' (they are pinpoint pages, not identifiers)."*

The only retrieval tools it has are `ACCESS_COURTLISTENER_OPINION` (fetch the
whole opinion) and `SEARCH_LOCAL_OPINION` (fuzzy-search the whole opinion,
returning character offsets). Neither knows where page 511 ends and page 514
begins. The agent is asked in prose to answer a question its tools cannot
answer, so it confirms the quote exists somewhere in the case and moves on.

Ours answers it by construction. `_ReporterPageParser` in
`validation/pinpoint_retrieval/reporter_page.py:202` walks CourtListener's
opinion HTML, collects every anchor carrying `citation-index` and `label`, and
slices the text between marker *N* and the next marker **with the same
citation-index** — so parallel reporters do not contaminate each other's
pagination. What reaches the semantic check is the cited page, delimited, and
nothing else.

That is the sharpest claim available to this project:

> The strongest agent tested detects a wrong pinpoint page 18% of the time, not
> because the model cannot reason about pages, but because nothing in its
> toolset can locate one. Page-delimited retrieval is a structural
> precondition for pinpoint verification, and supplying it changes the result
> more than changing the model does.

Testable, cheap, and supported by their published number plus our existing code.

## The gap that has to close first

`MelleaPinpointCheckOutcome` is `supports | inconclusive | unavailable |
failed`. **There is no outcome meaning "the page does not support it."**

That is the abstention discipline applied consistently, and on their benchmark
it is disabling. Scoring against LePhantomCite requires emitting a flag, and
there are only two ways to get one:

- map `inconclusive` → hallucinated, which reproduces exactly the failure mode
  we criticize them for and throws away the precision advantage; or
- flag only affirmative contradictions, of which the semantic layer currently
  produces none, giving recall near zero.

Neither is acceptable, so this is a design change and it should be made anyway
because the epistemics actually demand it:

> Absence from a **database** is not evidence — the archive is incomplete.
> Absence from a **retrieved page** is evidence — we have the page in hand.

Those are different situations and the current vocabulary collapses them. Add a
`contradicted` outcome to the pinpoint check, gated on
`ReporterPageRetrievalNode` having returned `found`, meaning: the cited page was
retrieved, and the attributed proposition is affirmatively not on it. Keep
`inconclusive` for everything else — page unavailable, proposition unclear,
model uncertain.

This is the enabling feature for competing on both semantic categories, it is
consistent with the three-answer framing rather than an exception to it, and it
is the natural place for the compound-proposition decomposition (Direction C) to
attach: a conjunction whose second conjunct is affirmatively absent from a
retrieved page is `contradicted`, not `inconclusive`.

**Do this before the head-to-head.** Without it there is no head-to-head to run.

## Every current number is stale

The evaluation figures in [`notes/presentation-notes.md`](notes/presentation-notes.md) were produced on
2026-08-03. Functional changes landed after that date:

| commit | date | effect |
|---|---|---|
| `b163c03` | 08-05 | four bug fixes |
| `d287f3e` | 08-06 | case-name recovery triggers on missing extraction, not just mismatch |
| `dec51b8` | 08-06 | search-route summary reports `possible_match` / `not_found` |
| `4d27e24` | 08-07 | court conflicts treated as citation mismatches |
| `054fb10` | 08-11 | damaged citations recovered by adjudicating hunted sites |
| `11b5778` | 08-13 | pinpoint check no longer discards its own correct verdicts |

The last one matters most for the honest result. The model was reaching a
correct `supports` verdict and then quoting the page the way a lawyer would —
eliding with an ellipsis, adding quotation marks the page does not carry — so
`resolve_evidence_quote` found nothing and the grounding gate threw the verdict
away. Both repair turns reproduced the same quote. Measured on the Brown v.
Board pinpoint that reproduced it: **3/3 failures before, 3/3 first-attempt
successes after, with no repair turns.**

So the 3-of-9 figure was partly measuring a grounding-gate defect rather than
the semantic check, and the 91.2% identity recall predates the court-conflict
and citation-recovery changes.

**A fresh full-corpus run is now the top item on the critical path**, ahead of
everything in `05-engineering.md`. Nothing should be written into a paper from
the August 3 artifacts.
