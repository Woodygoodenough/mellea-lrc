# Presentation notes

Structure: architecture → demo → dataset (+ numbers) → evaluation (two layers) → future work.
You own the validation pipeline; extraction is someone else's section — keep the
architecture review light on extraction, just enough to establish what it hands off.

## 1. Architecture

- Two-stage pipeline: **extraction** (raw document text → `ExtractedCitation` objects with
  spans, matched text, canonical citation fields) hands off to **validation** (that citation
  → a graph of nodes that progressively check identity, then semantic support).
- One sentence on extraction, then move on: eyecite-backed, with a whitespace-recovery layer
  we added this cycle (Docling PDF extraction leaves justified-text spacing that breaks
  eyecite's tokenizer outright — collapsing it before extraction and remapping spans back
  recovers real citations eyecite would otherwise silently drop).
- Validation is a node-graph, not a monolithic function. Each citation gets its own
  progression: locator lookup → candidate evaluation → parallel field checks (case name,
  year, court) → assessment → (for the found-locator route) reporter-page retrieval →
  Mellea proposition extraction → Mellea pinpoint check → citation summary. 21 distinct
  node types, all independently inspectable — this is what makes the audit work in the eval
  section possible at all: every verdict traces back to a specific, named step, not a black
  box.
- The identity-check layer (case name / year / court) is mechanical field comparison.
  The semantic layer (does the retrieved page actually support the claim) is where Mellea's
  IVR loop does the real work — instruct, validate, repair.
- One fix worth mentioning if there's time: the identity-check aggregation logic used to
  collapse "we couldn't check this field" and "we checked it and it disagrees" into the
  same verdict. Fixed this cycle — now only an actual disagreement asserts a problem;
  missing evidence just abstains. This is the fix behind the 100%-precision number in the
  eval section, so it's worth a one-line callback later rather than explaining it twice.

## 2. Demo

(You know this better than I can script it — a few suggestions on what to show, not a
script.)

- Pick one `unverifiable_authority` example and one `misrepresented_authority` example, and
  walk the SAME document through both outcome paths, so the audience sees the graph
  actually branch differently depending on what's wrong.
- Good unverifiable_authority candidate: Ginter (`1-1`) — real case name, real reporter,
  wrong court. Clean, easy to explain in 30 seconds, and it's literally the pattern behind
  the "100% specificity" claim you'll make two slides later.
- Good misrepresented_authority candidate: Whitehaven (`26-2`, `further-improvements.md`)
  — the compound-proposition case. Slightly more advanced, good if you want to preview the
  future-work section: the pinpoint check grounds half of a two-part claim and credits the
  whole thing. Only use this if you want to set up future work; otherwise pick a cleaner
  `supports`/correct example instead and save Whitehaven for section 5.

## 3. Dataset

- Lead with what it is, then what you did with it, in that order: *False Citation Bench* —
  26 real court filings with AI-hallucinated or misrepresented citations, each independently
  flagged either by the court itself (a sanctions/show-cause order) or by our own
  verification. 79 annotated records, published on Hugging Face
  (`gt-csse/false-citation-bench`) and on its own dedicated branch in this repo.
- What we did with it: this isn't just a label set we consumed — we found and independently
  verified 2 new records ourselves during the evaluation audit (Hernandez v. Mario's Auto
  Sales, United States v. Sarno — both real cases cited with the wrong court, verified
  against outside sources, not just internal consistency). Good concrete beat: "we didn't
  just evaluate against the dataset, we improved it."
- Then the numbers slide (below) right after this, before moving into evaluation.

### Numbers slide

Pull these into whatever visual format you're using — suggested groupings:

**The dataset**
| | |
|---|---|
| Source documents | 26 |
| Annotated false-citation records | 79 |
| — fabricated / unverifiable authority | 54 |
| — real authority, misrepresented | 25 |

**What the pipeline did with them**
| | |
|---|---|
| Citations extracted | 894 |
| Independently validated | 561 |
| Distinct validation operations (node types) | 21 |
| Total operations executed | 7,555 |
| — backed by a live CourtListener call | ~2,020 |
| — backed by a Mellea/LLM call | ~1,523 |

The "independently validated" vs. "extracted" gap (894 → 561) is worth a one-line
explanation if asked: the remainder are `Id.`/short-form citations that resolve through an
earlier full citation rather than being checked on their own — not a gap in coverage, a
property of how citations work in legal writing.

The 7,555 total operations number is the "look how much actual work happens per document"
beat — worth pairing with something like "that's ~290 operations per document, for what
looks to a reader like a handful of citations."

## 4. Evaluation — two layers

Present in this order, not the reverse — lead with the strong claim, then the honest one.

### Layer 1: identity verification

- The question: does the citation resolve to the case it claims to be?
- The confusion matrix (`evaluations/eval-report.md`, chapter 1), `match` = positive:
  - **100% precision** — every citation the system calls `match` is genuinely fine.
  - **100% specificity** — every genuinely broken citation gets flagged.
  - **91.2% recall**, 92% overall accuracy.
- The framing that lands: all the error lives in one, safe direction. The system never
  gives a confidently wrong answer — worst case, it over-cautiously flags something fine
  and costs a human a second look.
- Then the honest follow-up: of the 32 over-flagged cases, all 32 were manually traced to
  5 concrete, mostly mechanical causes (not a mystery error rate) — the biggest single one
  being a case-name-comparison gap on bankruptcy-style short captions ("Rubin" vs. "In re
  Rubin"), responsible for 19 of the 32 by itself. Good proof point that "over-flagged"
  means diagnosed and fixable, not an unexplained ceiling — save the roadmap-level future
  work for section 5, this is just evidence the 32 aren't mysterious.

### Layer 2: fabrication vs. misrepresentation

- Different question: even when the citation *is* real, does it actually support the claim?
- Strong claim: **zero false `match` on unverifiable_authority**, corpus-wide (0 of 364
  confident verdicts). A fabricated or misattributed citation never gets a clean pass.
- Honest limitation, stated plainly, not hedged into obscurity: the pinpoint-check layer
  (the part that catches *misrepresentation* specifically) is a much earlier-stage result —
  3 of 9 rendered verdicts wrong, small sample, and 6 of 15 real misrepresentation cases
  never even got an evidence check attempted. Say directly: identity verification is a
  load-bearing claim, misrepresentation detection is a first attempt, not a reliable one
  yet.

## 5. Future work

Roadmap-level, in priority order — each one widens what the system can confidently say,
not just patches a known bug:

1. **Database adapters beyond CourtListener — Westlaw and others.** Right now every
   confident verdict is bounded by what CourtListener has indexed; a citation genuinely
   real but absent from CourtListener's coverage can only come back `not_found`, not
   `match`. Adding adapters for other legal databases directly grows the confident-verdict
   bucket rather than just cleaning up existing verdicts — this is the highest-leverage
   item because it's a coverage problem, not an accuracy problem.
2. **Semantic inference for misrepresentation — extending the pinpoint-check workflow.**
   This is the real open research problem, not a bug fix. The honest 3-of-9 finding in the
   eval section is where this points to: reliably judging whether a page *supports* a
   claim (as opposed to whether a citation *exists*) is a much harder problem, and the
   Whitehaven compound-proposition failure (grounds half a two-part claim, credits the
   whole thing) shows the current instruction-following approach hits a structural
   ceiling. Likely needs a domain-finetuned model for legal judgment specifically, not
   further prompt tuning on a general-purpose model.
3. **Scale the benchmark up as its own independent project.** 26 documents and 79 records
   is enough to prove the methodology works and find real bugs (which it did this cycle),
   but not enough to make strong statistical claims. Growing False Citation Bench past a
   spot-check dataset into something with real evaluative power is worth treating as its
   own deliverable, not a side effect of pipeline work.
4. **Statute checking.** The pipeline and dataset are both explicitly case-citation-only
   right now (see the dataset README) — statutes and rules are a structurally different
   verification problem (no case name/court/year identity triad to check against), and are
   completely out of scope today. A real gap for any legal document, not a hypothetical
   one — plenty of source documents in the corpus already cite statutes we just don't look
   at.

Known, already-diagnosed system bugs (not roadmap items, just bookkeeping) are documented
in `further-improvements.md` if anyone wants to pick one up between larger efforts —
worth a passing mention, not a slide: a case-name-comparison gap on short-form/bankruptcy
captions (the single biggest source of false mismatches this cycle), an eyecite
court-code disambiguation defect, a table-of-authorities span-extraction bug, and a
docket-selection bug.

The ablation work in progress as of this writing (model size × Mellea's repair loop,
on/off) isn't finished — mention it's coming, don't present numbers from it yet.
