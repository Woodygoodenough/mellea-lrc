# Engineering roadmap

Every item is mapped to the paper claim it serves. Anything that serves no
claim is listed at the bottom as maintenance, and should not compete for time
against anything above it this fall.

## Before 5 September — JURIX

**Item 0, ahead of everything below.** Re-run the full corpus. Every figure in
[`notes/presentation-notes.md`](notes/presentation-notes.md) was produced on 2026-08-03, and six functional
commits landed after it — including `4d27e24` (court conflicts now count as
mismatches), `054fb10` (damaged-citation recovery) and `11b5778` (the pinpoint
check no longer discards its own correct verdicts, 3/3 failures to 3/3
successes on the case that reproduced it). The identity recall and the 3-of-9
pinpoint figure are both stale, and the pinpoint one was partly measuring a
grounding-gate defect rather than the semantic check. Nothing goes into a paper
from the August 3 artifacts. See `07-architecture-comparison.md`.

**Item 0b.** Add a `contradicted` outcome to the pinpoint check, gated on the
reporter page having actually been retrieved. Without it the system cannot emit
a misrepresentation finding at all, only fail to confirm one — which means there
is no way to score against LePhantomCite without destroying the precision
advantage. Rationale in `07-architecture-comparison.md`.

| # | work | serves | est. |
|---|---|---|---|
| 1 | Finish the ablation grid: accuracy per arm, not just timing | Plan A §6, Directions F, G | 2 d |
| 2 | Risk–coverage and confident-error-rate computation over existing run artifacts | Plan A §3, §6, Direction B | 2 d |
| 3 | Per-node repair analysis: which requirements fire, repair success rate, latency cost | Direction G | 2 d |
| 4 | One worked trace rendered as a paper figure | Plan A figure 4 | 1 d |
| 5 | LePhantomCite adapter — attempt, abandon by 1 Sep if it fights back | Direction A | 3 d |

Item 1 is the critical path. Nothing else in Plan A is blocked on code.

Item 5 is explicitly optional. It is the only item that can consume the
deadline, so it goes last and has a hard abandon date.

## September to mid-October — the anchor paper

| # | work | serves | est. |
|---|---|---|---|
| 6 | LePhantomCite adapter, both directions, plus baseline arms | Direction A | 1 w |
| 7 | Claim decomposition node: atomic claims plus connective structure | Direction C | 1.5 w |
| 8 | Per-claim grounding, reusing the evidence-quote machinery | Direction C | 1 w |
| 9 | Compositional aggregation semantics over per-claim verdicts | Direction C | 3 d |
| 10 | Hand-annotate claim structure for the 25 misrepresentation records | Direction C | 3 d |
| 11 | Misrepresentation taxonomy, drafted from those 25 and the audit notes | Directions C, D | 2 d |
| 12 | Split every abstention into archive-absent versus lookup-failed | Direction E | 1 w |

Items 7–9 are the research content of the anchor paper. Start them the day the
JURIX paper is submitted.

## Running in parallel, starting now

| # | work | serves | est. |
|---|---|---|---|
| 13 | Frozen CourtListener response cache: recording client, replay client, ship with dataset | Direction O, every reproducibility claim | 1 w |
| 14 | Licensing conversation with Charlotin | Direction D | — |
| 15 | Tracker scrape to RECAP docket resolution to filing retrieval | Direction D | 2 w |
| 16 | Label Studio pre-annotation at the new scale; annotator recruitment | Direction D | ongoing |

Item 13 pays for itself immediately: every subsequent evaluation run becomes
free and instant instead of costing two hours and a quota. Do it first, not
last — it accelerates items 1, 5, 6 and 12.

Item 14 has external latency and no cost. Send the email this week.

## Next cycle

| # | work | serves |
|---|---|---|
| 17 | Caselaw Access Project adapter | Direction E |
| 18 | Verbatim quotation check | Direction J |
| 19 | Short-form antecedent resolution as a scored node | Direction K |
| 20 | Negative-treatment detection over the citation graph | Direction H |
| 21 | Calibration over trace features; risk-ranked review queue | Direction I |
| 22 | Frontend to demo quality: node graph, spans, evidence highlighting | Plan D |
| 23 | Adversarial suite | Direction M |
| 24 | IRB submission for the human study | Direction N |

Item 24 has the longest external latency of anything on this list. If the human
study is wanted at all, the paperwork starts months before the study does.

## Known defects, from [`notes/further-improvements.md`](notes/further-improvements.md)

These are bookkeeping, not roadmap. Two of them affect a paper number and are
therefore worth fixing; the rest are not.

**Worth fixing before submission:**
- The case-name comparison gap on short bankruptcy captions ("Rubin" versus
  "In re Rubin"). 19 of the 32 false mismatches, by itself. Fixing it moves the
  recall number from 91.2% to somewhere near 95%, which is the single
  highest-value line of code available this month.
- The table-of-authorities span bug — citation spans landing on a
  table-of-authorities entry rather than the citing sentence. It produces
  garbage input to the semantic layer and inflates the pinpoint check's failure
  rate for a reason that has nothing to do with the pinpoint check.

**Not worth fixing now:** the eyecite court-code defect (`2nd Cir.` mapping to
`bap2`), the docket-selection bug, the pinpoint-recovery gap where eyecite
leaves a numeric pin cite in `extra`. Document each as a known cause in the
error analysis. A diagnosed error is a stronger paper artifact than a silently
fixed one, and fixing them changes numbers without changing conclusions.

**Do not fix at all:** the Whitehaven compound-proposition failure. It is the
motivating example for Direction C and patching it destroys the motivation.

**Open question worth one day's work:** the Beery case, where CourtListener's
own docket metadata appears to be wrong and we report a confident mismatch
against a brief that was probably right. If that is a pattern rather than a
one-off, it is a measured error rate on the underlying data — which is a
finding, and a reason for Direction E's second source. If it is a one-off, it
is a sentence in the limitations. Either way it is cheap to check and it is the
only known case where the system's confident-error rate might not actually be
zero.

## Structural work explicitly deferred

The separation of validation decisions from graph operations, described in
[`notes/further-improvements.md`](notes/further-improvements.md), is real technical debt and the right call
architecturally. It is also a coordinated refactor across the whole validation
package touching every node test, and it changes no paper number. Not this
semester.
