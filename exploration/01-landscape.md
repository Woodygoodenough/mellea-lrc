# The landscape, as of August 2026

Searched 2026-08-21. This section exists because the answer to "is what we did
novel" changed during the last four months, and the paper has to be planned
around that rather than around where the field was in spring.

## The work that constrains us

### Liu, Stammbach & Henderson — *Who Checks the Citations? Benchmarking Legal Hallucination Detection* (arXiv 2606.21155, June 2026)

The closest paper to ours, from the Princeton group in the same lineage as
Dahl et al. and Magesh et al.

- **LePhantomCite**: 1,300 entries. 1,000 excerpts from 245 federal appellate
  briefs pulled from 13 circuits via the CourtListener API, filed 2012–2021 so
  the sources predate generative AI, with hallucinations *injected*
  systematically. Plus 300 entries from Dahl et al.'s LLM-generated holdings.
  4,499 citation instances, 1,107 hallucinated.
- A five-type taxonomy of citation hallucination, said to be grounded in real
  filings.
- Evaluates five models in agentic and non-agentic configurations, including
  Claude Code. Best result: GPT-5, **84.4% recall, 55.0% F1**, averaging
  **15.3 agent steps per excerpt**.
- Their own stated limitation: "restricted information access limits the
  efficacy of even the best agents," and this "disadvantages both AI systems
  and litigants who lack subscriptions to commercial legal databases."

What this does to us: the "there is no benchmark for legal citation
verification" sentence is gone. We cannot open with it.

What it hands us, though, is more than it takes:

1. **Their errors are injected; ours occurred.** An injected wrong volume
   number is caught by a locator lookup and nothing else. A citation a federal
   judge sanctioned a lawyer over is a different object. The interesting
   experiment is running one system over both and reporting the gap — if
   performance on natural errors is materially worse than on injected ones,
   that is a finding about the benchmark, not just about the system, and it is
   ours to report because we hold the natural set.
2. **55% F1 with an unbounded agent at 15.3 steps** is a baseline we can
   attack directly with a fixed 21-node graph and an 8B local model. If a
   structured decomposition beats a frontier agent at a fraction of the cost,
   that is a systems result with a clear thesis.
3. **F1 over a binary label is the wrong metric** and their own limitation
   section says why without following it through: when the database is
   incomplete, "could not resolve" is a third answer, and scoring it as a
   miss punishes the only honest behavior. This is the opening described in
   [03-directions.md](03-directions.md) as Direction B.
4. **Their limitation is our thesis.** Open-access verification, quantified,
   is exactly the access-to-justice question they raise and do not answer.

### Magesh, Surani, Dahl, Suzgun, Manning & Ho — *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools* (JELS 2025, arXiv 2405.20362)

Lexis+ AI hallucinates at 17%, Westlaw AI-Assisted Research at 33%, against
vendor claims of "hallucination-free." Preregistered. Introduces a typology
separating complete fabrications, temporal inversions, and source
misattributions.

Relevance: this is the paper that establishes the problem is real at the top of
the market, and its typology is one we should adopt or explicitly extend rather
than invent a competing one. Our `misrepresented_authority` category is close
to their "source misattribution" but not identical, and reconciling the two is
cheap and buys credibility.

### Dahl, Magesh, Suzgun & Ho — *Large Legal Fictions* (JLA 2024)

The origin paper. 58–82% hallucination rates on legal queries to general
models. Its LLM-generated central-holdings set is reused inside LePhantomCite.

### The rest of the 2026 wave

- *Source or It Didn't Happen: A Multi-Agent Framework for Citation
  Hallucination Detection* (2605.08583). Argues that existing auditors emit
  binary Real-or-Fake labels and leave venue, year, pages and publisher
  unaudited. That is precisely the per-field decomposition we already do, on
  the legal side. Worth citing as convergent evidence that field-level
  verdicts are the right unit.
- *Citation Grounding: Detecting and Reducing LLM Citation Hallucinations via
  Legal Citation Graphs* (2606.00898). 13–21% hallucination in generated legal
  citations; a citation-graph grounding metric. Generation-side, not
  verification-side — complementary, not competing.
- *LegalHalluLens: Typed Hallucination Auditing and Calibrated Multi-Agent
  Debate* (2606.18021). Note the word "calibrated" — someone is already in the
  calibration space. Read before committing to Direction I.
- *LegalCiteBench* (2605.10186), rubric-based citation reliability.
- A bilingual fabrication study (2607.11127).
- Legal citation *prediction* on AusLaw (Artificial Intelligence and Law,
  2026) — different task, useful for the related-work paragraph on
  jurisdictional generalization.

Read the actual PDFs of 2606.21155, 2605.08583 and 2606.18021 before writing
related work. The summaries above are from search results and abstracts.

## The non-academic baseline we are also compared to

Westlaw KeyCite, Lexis Shepard's, Clearbrief, CiteCheck-style tools, and now
Charlotin's tracker of sanctioned filings. A reviewer will ask what we do that
KeyCite does not. The answer has to be specific:

- KeyCite tells you a case exists and how later courts treated it. It does not
  read the sentence in *your* brief and ask whether the page you cited supports
  the proposition you attached to it. That is our pinpoint check, and it is the
  thing that catches `misrepresented_authority`.
- KeyCite is behind a subscription. Our verdicts come from a public API and a
  local open-weights model, which is the access-to-justice argument.
- KeyCite emits a signal, not a trace. We emit spans and quotes.

Say this explicitly in the paper. It will otherwise be the first question.

## Where that leaves the positioning

The sentence to defend is not "we can detect fake citations." It is closer to:

> Citation verification against an incomplete public record is a *selective*
> prediction problem with an auditable-evidence requirement, and treating it as
> binary classification — as every current benchmark does — both mis-measures
> systems and rewards the wrong behavior. Under the correct framing, a fixed
> decomposition running an 8B open model produces safer verdicts than a
> frontier agent doing unbounded search, at two orders of magnitude less cost,
> and the residual error concentrates entirely in one place: judging whether a
> retrieved page supports a compound legal proposition.

Every direction in the next document is a piece of that sentence or an
alternative to it.

## Sources

- [Who Checks the Citations? Benchmarking Legal Hallucination Detection](https://arxiv.org/abs/2606.21155)
- [Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools](https://arxiv.org/abs/2405.20362) — [JELS version](https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413)
- [Source or It Didn't Happen: A Multi-Agent Framework for Citation Hallucination Detection](https://arxiv.org/pdf/2605.08583)
- [Citation Grounding: Detecting and Reducing LLM Citation Hallucinations via Legal Citation Graphs](https://arxiv.org/pdf/2606.00898)
- [LegalHalluLens: Typed Hallucination Auditing and Calibrated Multi-Agent Debate](https://arxiv.org/pdf/2606.18021)
- [LegalCiteBench](https://arxiv.org/html/2605.10186v1)
- [AI Hallucination Cases Database — Damien Charlotin](https://www.damiencharlotin.com/hallucinations/)
- [Mellea documentation — the requirements system](https://docs.mellea.ai/concepts/requirements-system)
