# Roadmap to a defensible result

Written 2026-08-21, after reading the Princeton implementation and downloading
their dataset. This supersedes the sequencing note at the end of
`03-directions.md`.

Two things changed the plan since the first pass. Every current number is stale
(see `07-architecture-comparison.md`), and benchmark scaling is now a **primary
track** rather than a background one, because the confidence problem is
statistical and only data fixes it.

---

## What "more confident" actually means, numerically

Worth being precise about this, because it decides how much data is enough and
which claims are already safe.

**The identity claim is already statistically defensible.** Zero confident
errors in 364 confident verdicts. By the rule of three, the 95% upper bound on
the confident-error rate is 3/364 ≈ **0.82%**. That is a real claim, publishable
today, and it does not need a bigger corpus:

> Across 364 confident verdicts we observed no case in which the system cleared
> a defective citation or asserted a defect without contradicting evidence;
> the 95% upper bound on that rate is 0.9%.

Say it that way rather than "100% precision," which reads as a small-sample
artifact and invites the objection.

**The recall claim is weak but survivable.** 36 mismatches gives roughly ±10
points on a recall estimate. Enough to say "over 90%," not enough to compare two
systems that differ by five points.

**The semantic claim is statistically empty.** Nine rendered verdicts. No
interval computed on nine observations means anything. This is the number that
data fixes and nothing else does — no prompt engineering, no architecture
change, no amount of careful analysis.

So the target is not "more data" in general. It is:

| layer | records now | needed for a real interval | why |
|---|---:|---:|---|
| extraction | 594 | sufficient | already tight |
| identity | 423 occurrences, 36 mismatches | ~150 mismatches | to compare systems, not just report one |
| **semantic / misrepresentation** | **25 annotated, 9 rendered** | **~150–200 annotated** | the binding constraint on every claim we want to make |

That third row is the whole argument for Track B.

---

## The gate structure

Four things block other things. Everything else is parallel.

```
Gate 0  fresh full-corpus run          → blocks every number in every paper
Gate 1  `contradicted` pinpoint outcome → blocks the head-to-head and Track C
Gate 2  frozen response cache           → unblocks cheap iteration on everything
Gate 3  annotation throughput           → sets the ceiling on Track B, and only wall-clock fixes it
```

Gates 0, 1 and 2 are days of work each and should all be done inside the next
two weeks. Gate 3 is a process, and it should start before the others finish
because it is the only one that cannot be accelerated later.

---

## Phase 0 — this week (21–27 August)

Nothing here is optional and nothing after it works without it.

| | work | why | est. |
|---|---|---|---|
| 0.1 | **Re-run the full corpus** on current `main` | six functional commits landed after the 2026-08-03 artifacts, including the pinpoint grounding-gate fix | 2 h compute + quota |
| 0.2 | Recompute extraction, identity, and pinpoint numbers; redo the 32-over-flag error analysis on the new run | the five diagnosed causes may have changed; `4d27e24` and `054fb10` both touch this | 2 d |
| 0.3 | **Frozen CourtListener response cache** — recording client, replay client | after this, every rerun is free and instant; it accelerates literally everything below | 3–4 d |
| 0.4 | Download and read the Charlotin CSV; confirm the CC BY 4.0 terms directly on the source, not from a summary | Track B depends on it | 1 h |
| 0.5 | Decide JURIX (see below) | 28 Aug abstract deadline | — |

Do 0.3 **before** 0.1 if the quota is tight — record the run as it happens and
you get both at once.

---

## The JURIX decision, honestly

Abstract 28 August, paper 5 September, and the numbers are stale until 0.1
lands. That is tight.

The case for going: a real conference publication in hand by December, a
presentation to the AI-and-Law community before the 2027 cycle, and a
journal-extension path to *Artificial Intelligence and Law*. The paper does
**not** need the head-to-head or the scaled benchmark to stand — identity
verification, the abstention framing, preprocessing, and cost are enough for ten
pages.

The case against: submitting something thin is worse than not submitting, and
the strongest version of this work is six months away.

**Recommendation: commit, but scope it to what Phase 0 supports, and use the
short/poster categories as the hedge.** JURIX takes long (10pp), short (5pp) and
poster (2pp). If the full paper converges by 2 September, submit long. If the
error analysis is still moving, submit a 5-page short paper on the abstention
framing plus the identity result — which is a genuinely good short paper — and
save the rest.

Frame it this way: every hour spent on the JURIX paper is an hour spent on work
Phase 0 requires anyway. There is no wasted effort in the downside case.

**Decide on 27 August**, on one criterion: did 0.1 and 0.2 land.

---

## Track B — the benchmark (primary, runs continuously)

This is the track that makes everything else conclusive, and it should start
now, in parallel with Phase 0.

### Do not just scrape the tracker

The obvious move is to take Charlotin's CSV (1,934 cases as of August 2026, CC
BY 4.0, CSV export available) and work down it. Do that — but do not make it the
method, for three reasons: it is someone else's compiled list, it is worldwide
while our reach is US federal via RECAP, and "we scraped a list" is not a
methodological contribution.

**Build a miner over CourtListener's own full-text search instead, and use the
tracker as a recall check on it.**

That inverts the relationship in our favour. The corpus becomes independently
reproducible from public APIs, the method becomes a contribution, and the
tracker becomes *validation*: "our miner recovers N% of the tracker's US federal
entries, plus M entries the tracker does not list." That second half — finding
cases a careful human curator missed — is a strong result on its own.

### The pipeline

1. **Mine.** CourtListener search over opinions and RECAP documents for the
   language courts actually use when they catch this: *nonexistent case*,
   *cases do not exist*, *fictitious citation*, *fabricated citation*,
   *hallucinated*, *artificial intelligence* near *Rule 11*, *show cause* near
   *citations*, *could not be located in any reporter*. Iterate the query set
   against the tracker's known entries — every tracker case the miner misses
   tells you which phrasing you are not covering.
2. **Resolve.** Order → docket → the filing the order is about. Orders almost
   always name the ECF number. Our RECAP client already does this.
3. **Retrieve.** Pull the offending filing's PDF, run it through the existing
   Docling + eyecite path.
4. **Pre-align — this is the step that makes it tractable.** The order usually
   *quotes the bad citation*. So string-match the case names and reporter
   citations appearing in the order against the extracted citations of the
   filing. That produces a candidate span automatically, and the human is
   confirming a proposal rather than reading a brief cold.
5. **Annotate.** Existing Label Studio workflow with pre-annotation
   (`scripts/label_studio/`), extended with the misrepresentation taxonomy from
   Direction C.
6. **Verify.** Second annotator on a sample; report inter-annotator agreement.

### Throughput

Step 4 is what changes the economics. Blank-slate annotation of a filing is
30–60 minutes. Confirming a pre-aligned candidate that the court itself quoted
is closer to **5–10 minutes per document**.

| target | documents | annotation hours | realistic by |
|---|---:|---:|---|
| pilot — validate the miner and the pre-alignment | 25 | 4 | mid-September |
| **v2 release — the statistical target** | **200** | **~30** | **December** |
| v3 — if it keeps working | 500+ | ~80 | spring 2027 |

Thirty hours is one person for a week, or two people for two afternoons a week
across a semester. That is the realistic path to ~150–200 misrepresentation
records, which is the number the semantic claim needs.

### Gate 3 is people

This is the only item on the roadmap that money and cleverness cannot
accelerate. If there is any possibility of recruiting annotators — law students,
a paid RA, an Emory Law collaboration — start that conversation in September,
not November. Everything else on this page is one person at a keyboard.

### What Track B unlocks

- A real interval on the semantic claim, which is the point.
- The "26 documents" objection disappears.
- The resource paper (Plan C) becomes writable.
- A second, non-NLP paper: which courts, which parties, which sanctions, over
  time. That is a JELS or law-review submission from the same asset.
- Re-running every existing result on the larger set. A finding that overturns
  one of our own is the strongest possible evidence the corpus was worth
  building.

---

## Track A — the paper spine (September to mid-October)

Gated on Phase 0, not on Track B.

| | work | serves |
|---|---|---|
| A.1 | Formalize the three-answer task, the safety property, and the metrics — coverage, selective precision, confident error rate, risk–coverage | the contribution |
| A.2 | Rule-of-three intervals on every headline number; abstention rate reported adjacent to accuracy everywhere | credibility |
| A.3 | Re-score our runs under a binary recoding in both directions, to show the recoding moves the number by several points | proves the framing matters |
| A.4 | **A plain-prompt LLM baseline on our own corpus** | one day; there is no excuse for its absence |
| A.5 | Per-node repair analysis from the ablation: which requirements fire, repair success by type, latency cost | Direction G, the Mellea contribution |
| A.6 | The worked-trace figure — one citation, its nodes in order, evidence quote and span | sells auditability better than any prose |

---

## Track C — the pincite experiment (highest value per hour)

Gated on Gate 1. Do it as soon as the `contradicted` outcome exists.

| | work | est. |
|---|---|---|
| C.1 | **Add `contradicted` to `MelleaPinpointCheckOutcome`**, gated on `ReporterPageRetrievalNode` returning `found` | 2–3 d |
| C.2 | Adapter: LePhantomCite `{text, hallucinations}` → our extraction input; our verdicts → their segment-list format | 2–3 d |
| C.3 | Run the 53 `incorrect_pincite` eval records. Compare to GPT-5's 18.2% | 1 d |
| C.4 | If it goes well, run the 131 `content_misrepresentation` records against their 84.0% | 1 d |
| C.5 | Full eval split (390 records) for a precision/cost comparison against Claude Code's 76.1% / 68.8% | 3 d |

C.3 is the decision point for the whole framing. Beat 18.2% clearly and the
paper has a headline that is architectural rather than incremental. Tie or lose
and Direction C (proposition decomposition) becomes mandatory and the framing
narrows to identity plus abstention — which is still a paper, just a smaller
one.

Predict the shape in writing before running: **higher precision, lower recall**
than their agent, because they have web-search fallback and we do not.

---

## Track D — system features (as capacity allows)

Ordered by paper value, not by engineering appeal.

| | work | serves |
|---|---|---|
| D.1 | Case-name comparison on short/bankruptcy captions (`"Rubin"` / `"In re Rubin"`) | 19 of 32 false mismatches; the single highest-value line of code |
| D.2 | Table-of-authorities span bug | feeds garbage to the semantic layer and inflates its failure rate for unrelated reasons |
| D.3 | Split abstentions into archive-absent vs lookup-failed | Direction E; the access-to-justice number |
| D.4 | Caselaw Access Project adapter | second source; also measures CourtListener's own metadata error rate (the Beery question) |
| D.5 | Verbatim quotation check | a whole taxonomy category, one week |
| D.6 | Proposition decomposition | Direction C; mandatory if C.3 disappoints |
| D.7 | Frontend to demo quality | Plan D |

Leave the eyecite court-code defect, the docket-selection bug, and the pin-cite
residual gap alone. Document them as diagnosed causes.

---

## Calendar

| when | gate / milestone |
|---|---|
| 21–27 Aug | Phase 0. Fresh run, cache, error analysis. Charlotin CSV. Miner prototype started. |
| 27 Aug | **Decide JURIX** — long, short, or skip |
| 28 Aug | JURIX abstract |
| 28 Aug – 4 Sep | Write. A.1–A.4 in parallel. |
| 5 Sep | JURIX submission |
| 8–15 Sep | Gate 1: `contradicted` outcome. Track C adapter. |
| mid-Sep | **C.3 — the pincite result.** Framing decision for the anchor paper. Track B pilot (25 docs) complete. |
| Sep – Oct | Track A completed; Track C.4–C.5; annotators recruited and running |
| mid-Oct | **ARR submission** — anchor paper |
| 8 Oct | JURIX notification |
| Oct – Dec | Track B to 200 documents; Track D as capacity allows; frontend |
| 8 Dec | JURIX, Toulouse |
| Dec – Jan | Re-run everything on the v2 benchmark. Resource paper drafted. |
| Jan – Feb 2027 | ICAIL 2027; demo track; journal extension |

---

## The one-sentence version

Fix the numbers this week, add the one outcome that lets the system say "the
page does not support this," run the pincite experiment in mid-September to
decide the framing, and spend the rest of the semester turning 26 documents into
200 — because the identity claim is already defensible and the semantic claim
cannot be defended by anything except data.
