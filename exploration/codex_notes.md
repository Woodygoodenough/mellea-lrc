# Codex notes: understanding LePhantomCite and comparing it with mellea-lrc

Written 2026-08-29 after reading Liu, Stammbach, and Henderson, *Who Checks
the Citations? Benchmarking Legal Hallucination Detection*, arXiv:2606.21155v2
(2026-08-06), and the released dataset/code materials.

Primary paper: <https://arxiv.org/abs/2606.21155>

This note is a comparison aid, not a claim that the two projects measure the
same thing. The most important difference is that LePhantomCite is primarily a
controlled benchmark of detecting injected defects in short excerpts, while
mellea-lrc is being built around verification of real filings and court-found
defects.

## What their paper does

### 1. Establishes the broader problem

The paper opens with a longitudinal experiment over eight generations of
ChatGPT, using 92 legal-document prompts and more than 8,000 generated case
citations. Its headline is that citation hallucination rates do not decline
consistently as models improve. It also argues that the verification burden
grows because newer models produce more citations per document and cite a more
diverse, less canonical set of cases.

This is a problem-motivation result, not the main LePhantomCite evaluation.
The paper connects it to a Jevons-paradox-style effect: cheaper drafting can
increase the total amount of material that must be checked.

### 2. Defines a five-part hallucination taxonomy

Their taxonomy separates:

1. **Non-existent citation** — the reporter citation does not correspond to a
   real case.
2. **Case-name mismatch** — the written case name and reporter citation point
   to different real cases.
3. **Incorrect pincite** — the case is real, but the cited page does not
   support the quoted material or proposition.
4. **Verbatim misquote** — the quotation is changed, often by replacing one or
   two words with synonyms.
5. **Content misrepresentation** — the case exists, but the cited authority
   does not support the proposition attributed to it.

They deliberately treat these as different defect mechanisms. A citation can
contain multiple types in principle, although their injection/evaluation setup
introduces one type at a time for the synthetic portion.

### 3. Releases the LePhantomCite benchmark

The released benchmark contains 1,300 entries:

- 1,000 excerpts derived from 245 federal appellate briefs, filed from
  2012–2021 and drawn from 13 Courts of Appeals;
- 300 entries adapted from the LLM-generated central-holdings portion of Dahl
  et al. (2024), manually verified against Westlaw.

For the brief portion, they downloaded 323 PDFs, used CourtListener citation
lookup, converted PDFs with olmOCR, segmented sentences with a fine-tuned
RoBERTa model, grouped sentences into coherent segments with Llama-3.3-70B,
and sampled citation-containing excerpts. The final benchmark is deliberately
short-context: it standardizes the unit of work rather than asking an agent to
process a complete brief.

The synthetic defects are created by modifying existing citation components:

- impossible reporter/volume/page combinations for non-existent citations;
- names or reporter references borrowed from another real case for mismatches;
- altered pincites within the same opinion;
- synonym substitutions inside quotations;
- altered holdings for content misrepresentation.

They try to prevent easy leakage. For non-existent citations and case-name
mismatches, repeated occurrences of the same citation are changed globally so
the agent cannot find a correct occurrence elsewhere in the same brief.

### 4. Uses an agentic verification setup

Their main system is a Bayesian Optimal Experimental Design (BOED) agent. The
agent maintains a natural-language belief state, chooses actions, observes
tool results, and repeats for up to 30 steps. The belief state tracks the
citations/quotes/holdings it has identified and whether each is correct,
hallucinated, or pending.

The eight actions are:

- CourtListener citation lookup;
- CourtListener open search;
- web search through SerpAPI;
- fetch a CourtListener opinion;
- search within a retrieved opinion;
- read selected document lines;
- edit a scratchpad;
- think.

They compare agentic and non-agentic prompting across five models: GPT-5,
Gemini 2.5 Flash, GPT-OSS-120B, Qwen3-8B, and Qwen3.6-27B. They also evaluate
Claude Code with Opus 4.8 as a production-agent comparison. Agent runs use a
30-step budget and temperature 0.8; the runs are stochastic.

### 5. Scores span retrieval, not typed citation decisions

The model outputs a list of hallucinated text segments. A predicted segment is
counted as correct if either the prediction contains the gold span or the gold
span contains the prediction. They report precision, recall, and F1.

Because the final output does not include hallucination types, their per-type
tables report recall only. The primary unit is therefore a hallucinated text
span, not a citation identifier, a citation field, or a validation trace.

This is a reasonable choice for their task, but it makes extraction and
validation errors inseparable: a citation the agent never noticed and a
citation it noticed but judged incorrectly are both simply missed spans.

### 6. Reports model, agent, and access limitations

Their main results are:

- GPT-5 BOED: 84.4% recall, 40.8% precision, 55.0% F1;
- Claude Code with Opus 4.8: 62.8% recall, 76.1% precision, 68.8% F1;
- agentic prompting improves recall over non-agentic prompting for the tested
  models;
- GPT-5 recall by type is approximately 100% for non-existent citations and
  case-name mismatches, 52.8% for incorrect pincites, 95.2% for verbatim
  misquotes, and 83.2% for content misrepresentation.

Their error analysis is particularly relevant to us:

- 19.9% of retrieved opinions lack usable text or pagination;
- GPT-5 falsely flags 25.0% of citations absent from CourtListener, while
  Claude Code flags 10.9%;
- 36.7% of GPT-5 false negatives occur after exhausting the 30-step budget;
- duplicate citation lookups occur in 39.7% of GPT-5 episodes, duplicate
  opinion searches in 26.4%, and re-search after a successful hit in 8.2%;
- GPT-5 spends more effort searching within retrieved opinions, which appears
  to explain its relative strength on content-based defects.

The discussion then turns to public access to case law, incomplete CourtListener
coverage, missing official pagination, the disproportionate effect on pro se
litigants, AI-literacy guidance, and the need to test systems on longer,
citation-dense briefs and naturally occurring defects.

## Direct comparison with mellea-lrc

| Dimension | LePhantomCite paper | mellea-lrc | Comparison consequence |
|---|---|---|---|
| Data origin | Mostly real brief text with injected defects, plus 300 manually checked LLM holding examples | Real filings whose defects were identified in court orders, currently a small set | We should not claim larger benchmark scale; we can claim stronger ecological validity for the adjudicated subset |
| Input unit | Short excerpt/segment | Full document through preprocessing and extraction, then citation-level validation | Their short-context score and our full-document score answer different workload questions |
| Detection unit | Hallucinated text span | Normalized citation identifier plus overlapping source span and typed validation nodes | We can separate extraction misses from identity/semantic misses |
| Defect taxonomy | Five categories listed above | Existing identity/semantic nodes, with the same categories being mapped into our evaluator | Use their labels for interoperability; do not invent incompatible names without a reason |
| Core architecture | Dynamic BOED agent; model decides what to inspect next | Fixed typed graph; deterministic extraction and lookup route, with model calls at constrained nodes | The useful claim is an empirical safety/coverage trade-off, not that one architecture is universally superior |
| Lookup policy | Citation lookup is one possible action | Locator lookup is a required first operation and its outcome controls the route | This is the cleanest structural comparison |
| Evidence | Agent searches whole opinion and uses fuzzy matching | Page-aware retrieval, evidence quotes/spans, and a grounding gate on model verdicts | Our key head-to-head hypothesis is that page-delimited retrieval enables pincite checking |
| Unknowns | Binary hallucinated/not hallucinated output; pending state exists internally but is not a scored third answer | Explicit unresolved/ambiguous/unsupported outcomes and abstention-aware scoring | Compare precision and coverage, not F1 alone |
| External access | CourtListener plus web search | CourtListener plus local/open archives; no general web-search fallback in the core route | Their recall advantage may come from broader access, not only model reasoning |
| Scale | 1,300 entries; 390 evaluation examples | 26 filings and 79 adjudicated records at the time of the audit | The immediate comparison should be category-level and cautious; benchmark scaling is a separate project |
| Model breadth | Five models plus Claude Code | Primarily local 8B/30B validation arms, with a provider/API arm | Run at least a plain-prompt baseline and report local quality/cost separately |
| Metrics | Span precision/recall/F1 | Extraction precision/recall, identity precision/recall, semantic outcomes, coverage, selective precision, confident-error rate, and risk–coverage | Preserve their metrics for comparability, but retain our safety metrics |
| Cost | GPT-5 averages 15.3 agent steps per excerpt; exact dollar cost depends on token/tool accounting | Fixed graph and local models; existing artifacts measure node calls and wall-clock time | Report cost and latency as first-class results, with assumptions clearly labeled |

## What their paper gives us

1. **A common taxonomy and public test set.** We can map our typed findings to
   their five labels instead of arguing about nomenclature.
2. **A strong baseline.** Claude Code's 76.1% precision/68.8% F1 and GPT-5's
   84.4% recall/55.0% F1 are the numbers any comparison must acknowledge.
3. **A decisive hard case.** Incorrect pincites are the place where their
   system struggles most. Their tools do not actually provide page-delimited
   retrieval, so our page-aware pinpoint route has a testable architectural
   hypothesis.
4. **An access argument.** Their paper identifies missing public pagination and
   incomplete repositories as system constraints. Our coverage work can turn
   that observation into a measured ceiling and marginal benefit of additional
   open sources.
5. **A warning about efficiency.** Their duplicate-action analysis gives us a
   useful baseline for showing what a typed, append-only graph avoids, but we
   should measure this rather than infer it from architecture.
6. **A clear limitation to inherit.** They explicitly ask for naturally
   occurring examples and longer documents. Our adjudicated miner and full-file
   pipeline are direct answers to those two future-work directions.

## What we must not claim

- Not that LePhantomCite is the wrong benchmark. It is a controlled lower-bound
  benchmark with useful category isolation and public evaluation materials.
- Not that their 55% F1 can be compared directly with our current accuracy or
  confident-error numbers.
- Not that their agent is simply careless about missing citations. Their paper
  explicitly analyzes missing CourtListener coverage, and Claude Code uses
  alternative searches more successfully than the BOED agents.
- Not that abstention or selective prediction is new. Our contribution would
  be the legal verification application, the positive-evidence safety rule,
  and the demonstration that binary recoding changes conclusions.
- Not that all of our current numbers are final. The full-corpus run must be
  refreshed after the post-August-3 fixes before publication.

## Fair comparison protocol

The minimum defensible comparison is:

1. Freeze the exact LePhantomCite version and record its dataset/hash.
2. Run our extractor and report extraction coverage separately.
3. Run the identity layer over every citation before any semantic model call;
   report resolved, ambiguous, refuted, unresolved, and failed outcomes.
4. Add the pinpoint `contradicted` outcome so an affirmative page-level defect
   can be scored without mapping abstention to hallucination.
5. Map our findings back to their five labels and compute their relaxed span
   precision/recall/F1 on covered citations.
6. Report our native metrics beside those numbers: coverage, selective
   precision, confident-error rate, risk–coverage, wall-clock time, model
   calls, and cost.
7. Start with the 53 incorrect-pincite records. This is the highest-value
   decision experiment because it tests the distinctive page-aware capability
   against the category where their GPT-5 recall is only about 52.8% in v2.
8. Then evaluate misquote and content misrepresentation, while clearly
   separating page retrieval failures from semantic failures.
9. Finally, run the comparison on our adjudicated filings. The important
   result may be a performance gap between injected defects and court-found
   defects, not a single winner.

## Codex assessment

The most promising combined thesis is:

> LePhantomCite shows that agentic systems can find many deliberately injected
> citation defects, but also exposes the central constraints: incomplete
> public records, missing pagination, redundant search, and binary scoring.
> Mellea-lrc tests a different design: fixed, typed, evidence-grounded checks
> that abstain when the record is insufficient, then evaluates the same defect
> taxonomy against both controlled injections and court-adjudicated filings.

The first near-term experiment should therefore be the incorrect-pincite
comparison, not a full benchmark sweep. If page-aware retrieval materially
improves recall while preserving abstention safety, it gives the project a
sharp architectural contribution. If it does not, the paper should narrow its
claim to identity verification, abstention, and auditability rather than
claiming that structured decomposition beats agentic search overall.

## Source and version cautions

- The paper HTML is v2 dated 2026-08-06; local notes and harness artifacts were
  produced at different dates and may use updated dataset fields.
- The paper describes hallucinations as introduced into 50% of sampled
  excerpts, while Appendix §8.2 describes injecting hallucinations into 80% of
  briefs before sampling. These are different denominators, but the paper
  should be quoted with the unit made explicit.
- The released data contains both span-keyed and citation-keyed label fields.
  Our harness uses the citation-keyed field for citation-level scoring and
  intentionally keeps the span-level distinction visible.
- The paper reports stochastic agent runs with temperature 0.8 and no fixed
  seed. Any head-to-head should preserve that fact and avoid treating one
  reported run as a deterministic system property.
