# What we already have

Before deciding what to build, an honest inventory of what is already
publishable. Everything here is in the repository or on Hugging Face today.

## 1. A dataset with adjudicated labels

`gt-csse/false-citation-bench`:

| | |
|---|---:|
| source filings | 26 |
| annotated false-citation records | 79 |
| — `unverifiable_authority` | 54 |
| — `misrepresented_authority` | 25 |
| extraction spans (derived) | 594 |
| validation occurrences (derived) | 423 |
| mismatches among those, spread over 14 filings | 36 |

The property that matters is `annotation_source`. Records carry either
`court_ruling` — a sanctions or show-cause order in which a judge found the
citation defective, identified by docket and verified against the ruling's own
text — or `manual_check`. Nobody else's benchmark has that. Every competing
dataset either injects errors synthetically or labels model output.

Two records in it are ours: Hernandez v. Mario's Auto Sales and United States
v. Sarno, both found during the evaluation audit and verified against outside
sources. That is a small but real "we improved the resource we evaluate on"
beat.

## 2. A verification system with an inspectable trace

21 node types. One citation produces an ordered list of nodes, each recording
what was asked, what came back, what it means, and which nodes it consumed.
Nothing is overwritten or summarized away. Every semantic verdict carries an
`evidence_quote` and an `evidence_span` into the retrieved page, and a verdict
the model cannot ground in a quote is discarded rather than reported.

The outcome vocabulary is the design decision worth writing about. `status`
(did the check run) and `outcome` (what did it find) are separate, and
`not_found` is its own answer rather than being folded into a verdict. The
project never says "this citation is fake."

## 3. Results

Extraction, against 594 gold identifiers:

| | |
|---|---:|
| precision | 100.0% |
| recall | 94.8% |
| occurrences returned | 563 |

Identity verification, against 423 occurrences, `match` as positive:

| | |
|---|---:|
| precision | 100% |
| specificity | 100% |
| recall | 91.2% |
| accuracy | 92% |

All error is in the safe direction: the system over-flags, it never confidently
clears a broken citation. The 32 over-flagged cases were each traced by hand to
one of five mechanical causes, 19 of them to a single case-name comparison gap
on short bankruptcy captions ("Rubin" vs "In re Rubin").

Corpus-wide: **zero false `match` on `unverifiable_authority`**, 0 of 364
confident verdicts.

Pinpoint check, the semantic layer: **3 of 9 rendered verdicts wrong**, and 6
of 15 real misrepresentation cases never got an evidence check attempted at
all. This is the weak result and it should be reported as one.

## 4. A preprocessing measurement

Same eyecite extractor over two renderings of the same 26 PDFs:

| rendering | gold locators recovered |
|---|---:|
| Docling | 563 / 583 (96.6%) |
| CourtListener `plain_text` | 527 / 583 (90.4%) |

46 of the 56 lost locators are still present in the CourtListener text and
reappear once whitespace is collapsed. The mechanism is identified: a line
break inserted inside `347 U.S.` / `483` does not degrade the citation, it
deletes it, silently, from every rule-based extractor simultaneously — and
nothing downstream reports a problem, because nothing downstream was told a
citation was there.

Both renderings ship, so the comparison is reproducible rather than asserted.

## 5. An ablation with per-node cost accounting

[`timing/`](timing/) holds four runs: 8B and 30B, repair on and off, over all 26
filings.

| | |
|---|---:|
| citations extracted | 894 |
| independently validated | 561 |
| total node executions | 7,555 |
| — backed by a CourtListener call | ~2,020 |
| — backed by an LLM call | ~1,523 |
| 30B + repair, validation wall clock | 7,213 s |
| 8B, no repair, validation wall clock | 2,575 s |

Per-node timings and status counts are recorded for every node type. This is
enough for a real cost/quality frontier, which most papers in this area do not
report at all. The 894 → 561 gap is short-form citations resolving through an
antecedent, not missing coverage.

## 6. The infrastructure nobody sees but reviewers care about

- A portable run-artifact format with no project types in it, so any system can
  be scored against the benchmark. That is what makes the evaluators a
  contribution rather than a script.
- Span coordinates defined against the document body with an explicit marker
  and a self-check that all 594 spans still slice to their own text.
- A Label Studio annotation pipeline (`scripts/label_studio/`) with
  pre-annotation, so scaling the dataset is an existing workflow rather than a
  new project.
- A typed CourtListener client with separate DTOs per endpoint.
- A `mellea-lrc` CLI.
- A frontend under `frontend/`, on Vercel, in progress — the basis of a demo
  track submission.

## What is missing

- Any statute, rule, or regulation handling. The corpus cites plenty; we look
  at none of them.
- Any check of whether the cited case is still good law.
- Any verbatim-quotation check.
- Any second database. Every confident verdict is bounded by CourtListener's
  index, and we have not measured how tight that bound is.
- Any calibrated confidence. Verdicts are categorical.
- Any human-subject evidence that the tool helps a reviewer.
- Any comparison against another system, on our benchmark or theirs.

The last one is the most damaging omission for a paper.
