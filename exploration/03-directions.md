# Research directions

Fifteen, ordered roughly by how much each would change what the project can
claim. Each has: the claim it would let us make, what has to be built, what
gets measured, why it is novel, and what could go wrong.

Ratings are effort in person-weeks assuming one person and a working
CourtListener quota, and risk that the direction fails to produce a result.

---

## A. Structured decomposition versus agentic search

**Effort** 2 weeks · **Risk** low · **Priority** highest

**Claim.** A fixed decomposition of citation verification into 21 typed checks,
run with an 8B open-weights model, produces safer verdicts than a frontier
model doing unbounded agentic search, at roughly two orders of magnitude lower
cost, and with a trace a human can audit.

**Build.** An adapter from LePhantomCite's format into our run-artifact format,
and a reverse adapter so our verdicts score under their metric. Both datasets
are public; their briefs come from CourtListener, which our client already
speaks. Then run four arms: ours-8B, ours-30B, a plain-prompt LLM baseline, and
a reimplementation of their agentic setup on whatever frontier model we can
afford.

**Measure.** Their metric (recall, F1) for comparability, plus ours (precision,
specificity, abstention rate, confident-error rate). Steps per excerpt, wall
clock per citation, dollars per document, API calls per document. We already
instrument all of the cost side per node type.

**Novelty.** Nobody has compared a structured pipeline to an agent on this
task. The generative-programming framing — that constraining the search space
in advance beats letting a model search — is exactly the thesis Mellea exists
to test, and this would be the first real-task evidence for or against it.

**Risk.** Their injected errors may be trivially caught by a locator lookup,
making our number uninformatively high. That is survivable and interesting: run
both benchmarks, report the gap between injected-error and natural-error
performance, and the contrast becomes the finding. The real risk is budget for
the frontier baseline; mitigate by citing their published numbers instead of
rerunning, and note the configuration difference honestly.

---

## B. Abstention-aware evaluation for verification systems

**Effort** 2 weeks (mostly writing and analysis) · **Risk** low · **Priority** highest

**Claim.** Citation verification against an incomplete record is a selective
prediction problem, not a binary classification problem. Every current
benchmark collapses "could not resolve" into one of the two labels, which
mis-scores systems and rewards a system for guessing. Under a selective
framing, the ranking of published systems changes.

**Build.** Mostly formalism plus re-analysis of runs we already have.
Define three answers — *corroborated*, *contradicted*, *unresolvable* — and the
safety property the system is designed around: never assert falsity without
positive contradicting evidence. Then define the metrics: coverage, selective
precision, risk–coverage curves, and **confident error rate**, the rate at
which the system asserts a verdict that is wrong. Re-score our own runs, and
re-score the published numbers of others where their reporting permits it.

**Measure.** Risk–coverage curve for the identity layer. Confident error rate
(currently 0 on `unverifiable_authority`, 0 of 364). Abstention rate reported
next to accuracy, always. Show what our 92% accuracy becomes under a binary
recoding in each direction, to demonstrate that the choice moves the number by
several points and is therefore not a reporting detail.

**Novelty.** This is the most defensible contribution in the document because
it is a framing the field is currently getting wrong, we already built the
system that way for independent reasons, and the argument generalizes past law
to any retrieval-grounded verification over an incomplete corpus. It also
explains *why* our design choices are right rather than merely describing them.

The legal argument reinforces it and should be in the paper: a court
sanctions a lawyer when a citation is *wrong*, not when it is merely *not
found in one database*. The system's epistemics should match the standard the
domain actually applies.

**Risk.** A reviewer says selective prediction is not new. It is not — the
contribution is the application, the safety property specific to this task, and
the demonstration that the existing benchmarks are miscalibrated for it. Frame
it that way from the first sentence. Also check `LegalHalluLens` first;
somebody is already using the word "calibrated" in this space.

---

## C. Proposition decomposition for misrepresentation

**Effort** 4–6 weeks · **Risk** medium · **Priority** highest

**Claim.** Misrepresentation detection fails structurally, not stochastically:
the check evaluates a compound legal proposition as one unit, so grounding any
part of it grants support to the whole. Decomposing the proposition into atomic
claims, grounding each independently, and aggregating under an explicit
semantics fixes a failure class rather than a failure.

**Build.**
1. A claim decomposition step: given the citing sentence's proposition, emit
   atomic claims and the connective structure joining them. Conjunction ("X
   and Y"), causation ("X because Y"), qualification ("X unless Y"), and
   stacked holdings each need different aggregation.
2. Per-claim grounding against the retrieved page, each with its own quote and
   span — the existing evidence-quote machinery already does this for one
   claim.
3. An aggregation semantics: a page supports a conjunction only if it supports
   every conjunct; supports a causal claim only if it supports both relata and
   the link; and a partial result reports *which* component failed, which is
   far more useful to a reviewer than a verdict.
4. A misrepresentation taxonomy, grounded in the 25 `misrepresented_authority`
   records and expanded as the corpus grows. Candidate types: proposition
   absent from the page; holding versus dictum; the case says the opposite;
   holding narrower than asserted; quote altered; wrong pinpoint page, right
   case; procedural posture mismatch; non-binding in the citing court;
   superseded or overruled. This taxonomy is a contribution in its own right —
   Magesh et al. have one for generated citations, nobody has one for
   *misrepresentation in filed briefs*.

**Measure.** Per-component grounding accuracy, aggregate verdict accuracy, and
the diagnostic value: on the 25 misrepresentation records, does the system
identify the *right reason*? Compare against the current atomic check on the
same records. The Whitehaven case (`26-2`) is the worked example.

**Novelty.** This is textual entailment specialized to legal propositions with
a defined compositional semantics, evaluated on real misrepresentations. It is
the direction most likely to carry a main-conference paper, because it is a
genuine NLP problem rather than a systems-engineering result.

**Risk.** 25 records is a thin evaluation set. Decomposition may introduce its
own errors that outweigh what it fixes. Mitigate by measuring the decomposition
step in isolation against hand-annotated claim structures — which is a small,
tractable annotation job on 25 records and worth doing regardless.

Do not patch the Whitehaven example directly. [`notes/further-improvements.md`](notes/further-improvements.md)
already records why: a targeted instruction fix would not generalize.

---

## D. Scale the benchmark from court sanctions orders

**Effort** 6–10 weeks · **Risk** medium · **Priority** high

**Claim.** A benchmark of several hundred filings whose false citations were
adjudicated by a judge, rather than injected by a script, and which grows as
the sanctions record grows.

**Build.** Charlotin's AI Hallucination Cases database catalogued roughly 1,600
cases by mid-2026 and grows by five or six a day. Each entry names court,
docket, the nature of the fabrication, and the sanction. The pipeline:

1. Scrape the tracker; check licensing and contact Charlotin before
   redistributing anything derived from it. He is a research fellow at HEC
   Paris and a collaboration is more likely than a refusal.
2. Resolve each entry's docket in RECAP — our client already does this.
3. Pull the offending filing and the court's order.
4. Align the court's findings to citation spans in the filing, using the
   existing extraction and the Label Studio pre-annotation workflow.
5. Human-verify. This is the cost, and it is why the number lands in the
   low hundreds rather than the full 1,600.

**Measure.** Corpus size, per-document annotation cost, inter-annotator
agreement on the taxonomy from Direction C. And then re-run every result in
the paper on the larger set — a benchmark that overturns one of our own
findings would be the strongest possible evidence it was worth building.

**Novelty.** Judicially adjudicated labels at scale. Nobody has this and it is
hard to replicate, because it requires the RECAP plumbing plus the annotation
discipline plus the willingness to do the boring part. It is also the answer to
the "26 documents" objection, which we will otherwise get from every reviewer.

**Second paper for free.** The same corpus supports an empirical-legal-studies
question that has nothing to do with NLP: which courts, which kinds of party
(pro se versus represented), which practice areas, what sanctions, what
trajectory over time. That is a JELS or law-review paper reaching an audience
that changes practice, and it costs almost nothing extra once the corpus is
built.

**Risk.** Licensing and redistribution. PACER filings are redistributable on
the argument already made in the dataset README; the tracker's own compiled
data may not be. Ask early. Also: annotation throughput is the binding
constraint, so start it in parallel with everything else rather than after.

---

## E. Coverage: how far can open-access verification actually go?

**Effort** 3 weeks · **Risk** low · **Priority** high

**Claim.** A quantified ceiling on what can be verified against public sources,
and a measurement of what each additional open database buys.

**Build.** Two halves.

*Measure the ceiling.* Take every `not_found` verdict and every one of the 171
extraction records CourtListener cannot decide, and determine by hand or by a
second source how many are genuinely absent from CourtListener versus
recoverable with a better query. That splits our abstentions into "the archive
does not have it" and "we failed to find it," which are completely different
problems and are currently conflated.

*Attack it.* Add adapters. The Caselaw Access Project (Harvard, 6.7M cases
through 2020) is fully open and is the obvious second source. Then Google
Scholar, Justia, state-level databases. Measure marginal coverage per adapter
— how many previously unresolvable citations each one resolves, and whether
any of them disagree with CourtListener.

**Measure.** Resolution rate per source, marginal gain per added source,
inter-source disagreement rate. That last one matters more than it sounds:
[`notes/further-improvements.md`](notes/further-improvements.md) already records a case (Beery) where
CourtListener's own docket metadata appears to be wrong, and we report a
confident mismatch against a brief that was probably right. A second source
turns that from an anecdote into a measured error rate on the underlying data,
which nobody has quantified.

**Novelty.** This answers, with numbers, the limitation Henderson's group
stated and left open: whether litigants without commercial subscriptions can
verify their own citations. It is the access-to-justice result, and both JURIX
and NLLP reward that framing explicitly.

**Risk.** Low. The measurement half produces a result regardless of what the
adapters turn up. CAP's 2020 cutoff limits it for recent citations — say so.

---

## F. Local, private verification

**Effort** 1 week (the data mostly exists) · **Risk** low · **Priority** high

**Claim.** The whole verification runs on hardware a firm can own, against a
public API, with no document ever leaving the building — and we can state the
quality cost of that choice exactly.

**Build.** Finish the ablation grid: 8B and 30B, repair on and off, plus a
frontier-API arm for the ceiling. Report the frontier as quality per second
and per dollar, not as a single accuracy number.

**Measure.** Already instrumented: 7,555 node executions, ~1,523 LLM calls,
30B-with-repair at 7,213s versus 8B-without at 2,575s over 26 filings. Add
accuracy per arm and it is a frontier plot.

**Novelty.** The framing, more than the numbers. Attorney work product and
privileged drafts cannot be uploaded to a third-party API — that is a
professional-responsibility constraint, not a preference, and every paper in
this space evaluates by calling GPT-5. "Verification you can run on the
document you are not allowed to upload" is a sentence with real force in a
legal venue, and it makes the small-model result a headline rather than a
concession.

**Risk.** None to speak of. This is packaging work on data we have.

---

## G. Does instruct-validate-repair actually buy reliability?

**Effort** 2 weeks · **Risk** low · **Priority** medium-high

**Claim.** A measured account of where a constraint-and-repair loop helps on a
real task, and where it cannot help in principle.

**Build.** Per-node analysis of the repair-on versus repair-off runs. Which
requirements fire, how often, how many repairs succeed within budget, what the
latency cost is, and what the accuracy delta is per node type.

**Measure.** Repair success rate by requirement type; latency cost per repair;
accuracy delta by node. The hypothesis worth testing, and which our existing
failure notes already suggest: repair fixes *grounding* violations — the model
produced text that is not in the source — and cannot fix *semantic* errors —
the model understood the task and was wrong. [`notes/further-improvements.md`](notes/further-improvements.md)
records both patterns already: re-extraction repair correctly rejects a model
"correcting" `$.A.` to `S.A.`, and exhausts its budget without ever fixing the
`Cnty.` to `County` expansion, because there was nothing to fix by retrying.

**Novelty.** The generative-programming community asserts that a repair budget
drives satisfaction probability toward 1. That is true for checkable
requirements and vacuous for unhealthy ones, and nobody has measured the split
on a real task with real requirements. This is the section IBM Research would
most want to co-author, and it makes the Mellea dependency a contribution
rather than an implementation detail.

**Risk.** The answer might be "repair does very little," which is still
publishable and still honest. Do not let it become a section that oversells.

---

## H. Negative treatment — is the cited case still good law?

**Effort** 4–6 weeks · **Risk** medium · **Priority** medium-high

**Claim.** Detecting that a cited authority has been overruled, vacated,
abrogated or superseded, from the text of later citing opinions, against a
public citation graph.

**Build.** CourtListener exposes citing relationships. Given a validated
citation, walk to opinions that cite it, and classify the treatment language.
This is a well-defined classification task over a bounded vocabulary and it
maps directly onto what KeyCite and Shepard's sell.

**Measure.** Against a hand-labelled set of known-overruled cases, precision
and recall of negative-treatment detection. Then, on the corpus: how many
filed citations are to authority that is no longer good law? That number, if
non-trivial, is a finding on its own.

**Novelty.** The task is not new in the abstract — the commercial products do
it — but doing it openly, measurably, and integrated with span-grounded
verification is. It also closes a real gap: today a fabricated case and an
overruled case both look like problems to a reader and neither of our layers
catches the second.

**Risk.** The commercial editorial process behind KeyCite is decades of human
labor. Automating it partially is realistic; matching it is not. Scope the
claim to detection with high precision and explicit abstention, consistent with
Direction B.

---

## I. Calibrated confidence and a risk-ranked review queue

**Effort** 3 weeks · **Risk** medium · **Priority** medium

**Claim.** The node graph's evidence can be turned into a calibrated
probability that a citation is defective, and a reviewer working the ranked
queue finds the defects in a fraction of the reading.

**Build.** Features from the node trace — which checks fired, which abstained,
evidence match scores, candidate ambiguity. A simple model on top; simple is
better here because the trace is the explanation and a complex model destroys
it. Then a ranking.

**Measure.** Expected calibration error, risk–coverage, and the operational
metric: what fraction of the 79 known defects surfaces in the top *k* of a
document's citations.

**Novelty.** Moderate. Check `LegalHalluLens` first. The distinctive part is
calibrating over a *structured trace* rather than over model logprobs, which
means the confidence stays explainable.

**Risk.** 79 records is thin for calibration. This direction improves a lot
once Direction D lands, and is probably better sequenced after it.

---

## J. Quotation verification

**Effort** 1 week · **Risk** very low · **Priority** medium

**Claim.** A separate, near-deterministic check: is the quoted string actually
present, verbatim, in the cited opinion at the cited page?

**Build.** Extract quoted spans from the filing, retrieve the opinion text,
match. The evidence-quote and fuzzy-grounding machinery in
`pinpoint_retrieval/evidence_quote.py` already does the hard half.

**Measure.** Precision and recall over quoted citations in the corpus, and a
count of how many filed quotations are altered.

**Novelty.** Low as a technique, real as a result. Altered quotations are a
distinct and common failure that neither the identity layer nor the pinpoint
check currently catches, and they are the most legally serious kind — a
fabricated case is embarrassing, a doctored quotation attributed to a real
court is worse. Cheap to build, adds an annotation category, and produces a
number for the paper.

**Risk.** Star pagination and reporter-versus-slip-opinion text differences
will cause false alarms. The fuzzy grounding already handles some of this;
budget time for the rest.

---

## K. Short-form and antecedent resolution as a first-class task

**Effort** 2 weeks · **Risk** low · **Priority** medium

**Claim.** Resolving `Id.` and short-form citations to their antecedents is a
coreference problem with its own metric, and its errors are currently invisible
because they are silently inherited.

**Build.** Make the resolution explicit as a node with its own outcome
vocabulary, annotate antecedent links in the corpus, and evaluate.

**Measure.** Antecedent resolution accuracy over the 333 citations currently
resolved this way (894 extracted, 561 independently validated). Plus the
failure mode nobody discusses: a short form whose antecedent was itself
fabricated, which inherits a verdict it never earned.

**Novelty.** Modest but clean, and it closes a hole in the evaluation story —
right now a third of extracted citations are outside the scored set and we
explain that away in a footnote. Making it a measured task turns a caveat into
a result.

**Risk.** Low.

---

## L. Statutes, rules, and regulations

**Effort** 6+ weeks · **Risk** high · **Priority** medium-low for this cycle

**Claim.** Extending verification past case law to the other half of what
briefs cite.

**Build.** A different identity model entirely. There is no case-name / court /
year triad; a statute is identified by title and section, and the hard part is
*temporal*: was that section in force, in that form, at the time that mattered?
Sources are heterogeneous — the U.S. Code, the CFR, state codes, court rules —
and versioning is inconsistent across all of them.

**Measure.** Coverage first. How many of the corpus's unannotated statutory
references can be resolved at all.

**Novelty.** High. Temporal validity of statutory citation is genuinely
under-researched and a real failure mode: citing a repealed provision is a
different error than citing a fabricated case, and neither our system nor
anyone else's catches it.

**Risk.** High, and it is a whole second project. It belongs in the future-work
section of the anchor paper and as a proposal for next year, not in this cycle.
Say explicitly in the paper that the corpus contains statutory references we do
not touch — reviewers respect a stated scope boundary far more than a silent
one.

---

## M. Adversarial robustness

**Effort** 2 weeks · **Risk** low · **Priority** medium-low

**Claim.** A verification system is a target. Here is what passes it and why.

**Build.** Construct citations designed to survive each layer: a real case
cited for a proposition it nearly supports; a real locator with a party name
close enough that the case-name check tolerates it; a pinpoint one page off; a
proposition that is true and on the page but is dictum. Run them.

**Measure.** Attack success rate per layer, and which layer catches which
attack.

**Novelty.** Red-teaming your own verifier is uncommon in this literature and
is a strong signal of seriousness. It also produces a defensible statement of
what the system does *not* protect against, which is a much better limitations
section than a list of TODOs.

**Risk.** Low. Keep it a section, not a paper.

---

## N. Does it help a human?

**Effort** 4 weeks including IRB · **Risk** medium · **Priority** medium

**Claim.** Reviewers using the tool find more defective citations, faster, than
reviewers without it.

**Build.** A within-subjects study: law students or practitioners review
filings with and without the tool, counterbalanced. n=12–20 is enough for a
workshop-grade result. GT has no law school; Emory Law is in Atlanta, and a
collaboration there is worth pursuing on its own merits regardless of this
study.

**Measure.** Time per document, defects found, false alarms accepted, and —
the one that matters and that nobody measures — automation bias: how often does
a reviewer accept a wrong verdict from the system that they would have caught
alone?

**Novelty.** High for this literature, which is entirely offline. It also
converts "we built a tool" into "we showed the tool helps," which is a
categorically stronger claim and one that a workshop reviewer cannot dismiss as
incremental.

**Risk.** IRB timing and recruitment. Start the IRB paperwork now if this is
wanted at all, because it is the only item here with a hard external latency.

---

## O. Reproducibility: ship a frozen response cache

**Effort** 1 week · **Risk** very low · **Priority** medium-high, disproportionate value

**Claim.** Anyone can reproduce every validation number in the paper with no
API key, no quota, and no network.

**Build.** Record every CourtListener response the benchmark run touches, freeze
it, and ship it with the dataset. The client already has an injectable seam
(`validate_document(document, client=...)`), so this is a recording client plus
a replay client plus a large blob.

**Measure.** Nothing. It is infrastructure.

**Novelty.** Not a research contribution, and it will still be one of the most
valuable things on this list. Today the evaluation README says a free-tier token
will not finish the run and it takes up to two hours — which means nobody
outside the project will ever reproduce our numbers, and reviewers know that.
Removing that barrier is cheap and buys real credibility, and it makes the
benchmark usable by people who would otherwise never try it.

It also fixes a scientific problem: CourtListener's index changes over time, so
today's numbers are not reproducible even *by us* a year from now.

---

## Sequencing

**For JURIX, by 5 September**: A (partial — cite their published numbers rather
than rerunning), B, F, G, plus the existing extraction, identity, and
preprocessing results. No new research required, only writing and analysis.

**For the anchor paper, by mid-October ARR**: A in full, B formalized, C built
and measured, E's measurement half. This is the six-week block after JURIX.

**Running in parallel from now**: D, because annotation throughput is the
binding constraint on everything downstream, and O, because it is a week and it
makes everything else more credible.

**Next cycle**: H, I, J, K, L, M, N.
