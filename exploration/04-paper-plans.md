# Four paper plans

Concrete enough to start writing from. Plan A is the one to act on this week.

---

## Plan A — JURIX 2026 long paper, due 5 September

**Working title.** *Absence Is Not Falsity: Abstention-Aware Verification of
Legal Citations Against the Public Record*

**The claim.** Verifying a citation against an incomplete public archive admits
three answers, not two, and building the third one in — rather than recoding it
away at scoring time — is what makes a verification system safe enough to put
in front of a lawyer. We present a system built on that principle, evaluated on
26 filings whose defective citations were identified by the courts themselves,
and show that it never once clears a defective citation while running entirely
on an 8B open-weights model against a public API.

**Why this and not "we built a citation checker."** The second version competes
on scale with a Princeton group that has 1,300 excerpts to our 79 records. The
first version competes on a framing they got wrong.

**Sections, with target pages (10 total).**

1. *Introduction* (1). The sanctions record — roughly 1,600 documented cases by
   mid-2026, five or six a day — establishes the problem without argument. Then
   the pivot: the question a court asks is not "is this citation in a database"
   but "is this citation wrong," and those differ.
2. *Related work* (1). Dahl et al.; Magesh et al.; Liu, Stammbach & Henderson;
   the 2026 wave. Position against LePhantomCite explicitly and generously —
   injected versus adjudicated errors, agentic versus structured, binary versus
   selective. Do not hedge; state the differences and let them stand.
3. *Task formulation* (1.5). The three-answer formulation. The safety property:
   never assert falsity without positive contradicting evidence. The metrics
   that follow — coverage, selective precision, confident error rate,
   risk–coverage. This section is the contribution; give it the space.
4. *System* (2). The node graph. The route: locator lookup branching to found /
   not found / ambiguous / unsupported. Field checks as mechanical comparison,
   the pinpoint check as the semantic layer, evidence grounding as the gate on
   every model verdict. One figure: the route diagram. One table: the node
   types and their outcome vocabularies.
5. *Benchmark* (1). 26 filings, 79 records, the `court_ruling` versus
   `manual_check` distinction, the minimum sufficient case identifier and why
   spans are keyed on it, the two derived sets and why they are kept apart.
6. *Results* (2.5).
   - Extraction: 100% precision, 94.8% recall.
   - Preprocessing: Docling 96.6% versus CourtListener plain text 90.4%, with
     the silent-disappearance mechanism. Short, self-contained, memorable.
   - Identity: 100% precision, 100% specificity, 91.2% recall, and the
     diagnosis of all 32 over-flags into five mechanical causes.
   - Corpus-wide: 0 false `match` on `unverifiable_authority`, 0 of 364.
   - Cost: the 8B/30B x repair grid, wall clock, call counts.
   - The honest one: pinpoint check, 3 of 9 wrong, 6 of 15 never attempted.
     Report it in the results, not the limitations. Reviewers reward this and
     it sets up the next paper.
7. *Limitations and future work* (0.5). Corpus size; case law only, no
   statutes; single database; the semantic layer as the open problem.

**Figures.**
- The validation route as a branching diagram.
- A risk–coverage curve for the identity layer.
- The cost/quality frontier across the four ablation arms.
- One worked trace — a single citation, its nodes in order, with the evidence
  quote and span. This is the figure that sells the auditability claim and it
  should be on page 1 or 2, not buried.

**What has to happen before 5 September.**
- Finish and tabulate the ablation runs. Highest priority; the runs exist, the
  accuracy numbers per arm may not.
- Write the formalism in section 3. This is new writing, not new code.
- Recompute risk–coverage from existing artifacts.
- Decide whether the LePhantomCite comparison fits. If it does not run cleanly
  by 1 September, cite their published numbers in related work and drop the
  head-to-head to the anchor paper. Do not let it sink the deadline.

**What to deliberately leave out.** Proposition decomposition, the scaled
benchmark, coverage adapters. They are the next paper, and a JURIX paper that
promises them is better positioned than one that half-delivers them.

---

## Plan B — the anchor paper, ARR mid-October, for ACL 2027 or ICAIL 2027

**Working title.** *Decomposition Beats Search: Structured, Abstention-Aware
Citation Verification with Small Open Models*

**The claim.** Three results in one arc.

1. A fixed 21-check decomposition running an 8B open model matches or beats a
   frontier model doing unbounded agentic search on LePhantomCite, at two
   orders of magnitude less cost, with an auditable trace.
2. The same system's performance drops substantially when moved from injected
   errors to adjudicated ones — which is a measured statement about what
   synthetic benchmarks in this area do and do not tell you.
3. The residual error concentrates in one place, and it has a structural cause:
   compound legal propositions evaluated atomically. Decomposing them and
   grounding each component fixes a failure class.

**Why it holds together.** Each result motivates the next. Decomposition beats
search; but the benchmark that shows it is too easy; and on the harder
benchmark the remaining failure is itself a decomposition failure, one level
up. The paper's argument is the same idea applied twice, which is what a good
paper looks like.

**Experiments.** Directions A, C, and the measurement half of E, from
[03-directions.md](03-directions.md).

**Risk.** Result 1 depends on the adapter landing and on their errors not being
trivially easy. If they are trivially easy, result 2 gets stronger and result 1
gets weaker; the paper survives either way, which is a good property to have
designed in.

---

## Plan C — the resource paper

**Working title.** *False Citation Bench: Adjudicated Citation Defects in
Filed Legal Documents*

**Venue.** NeurIPS Datasets & Benchmarks, ACL resource track, or LREC.
Conditional on Direction D landing.

**The claim.** Several hundred filings, labelled by the fact that a court found
the citation defective, with span-aligned annotations, a misrepresentation
taxonomy, a frozen response cache making every evaluation reproducible offline,
and evaluators that score any system through a portable artifact format.

**What makes it a resource paper rather than a dataset dump.** The
methodology: the minimum sufficient case identifier as the annotation unit, and
the argument for why it and not full citation extent; the deliberate separation
of extraction, identity, and falsity into three non-nesting label sets; the
caption-masking decision and why it is a masking rather than a filtering
decision; the coordinate-space discipline. That reasoning already exists in the
dataset README and is better than most published resource papers' methodology
sections. It only needs the scale behind it.

**Prerequisite.** Direction D, and the licensing conversation with Charlotin.
Start both now; this paper is gated on wall-clock, not on ideas.

---

## Plan D — the demo paper

**Venue.** ACL or EMNLP demo track, or a JURIX demo session.

**The claim.** A working interface where a lawyer pastes a draft and gets, per
citation, a verdict, the evidence that produced it, and the span it came from —
with every intermediate check visible and inspectable.

**What it needs.** The `frontend/` work finished to the point where the node
graph is legible: the route as it branched for this citation, each node's
outcome, the evidence quote highlighted in the retrieved page, and the citation
highlighted in the source. That view *is* the demo; the verdict alone is not
interesting and every commercial product already shows one.

**Why it is worth the time.** Demo papers are low-risk publications that reward
exactly what this project has and that a system paper cannot convey — the
auditability claim is much more convincing when someone can click through it.
It is also the artifact to show IBM, and the thing most likely to get the work
used.

---

## Which to commit to

Plan A this week. Plan B is the fall. Plans C and D run in parallel on longer
clocks and neither blocks the other.

If only one thing gets done: Plan A. A JURIX long paper is a materially better
outcome than the workshop paper the feedback suggested, it is reachable from
what exists, and it establishes the work in the AI-and-Law community before the
2027 cycle.
