# LePhantomCite

Measures this project against
[LePhantomCite](https://huggingface.co/datasets/ai-law-society-lab/Legal_Phantom_Citation),
the benchmark released with *Who Checks the Citations? Benchmarking Legal
Hallucination Detection* ([arXiv:2606.21155](https://arxiv.org/abs/2606.21155)).

It is a different kind of set from [false-citation-bench](../README.md). Its
1,300 excerpts come from federal appellate briefs filed 2012–2021 with defects
**injected** into them; ours are filings whose defects a court found. Running
one system over both is the point: a score on injected errors and a score on
adjudicated ones are not the same measurement, and reporting only the first
overstates what a system does in practice.

## Get the dataset

Not redistributed here. It is CC BY 4.0:

```bash
hf download ai-law-society-lab/Legal_Phantom_Citation --repo-type dataset \
  --local-dir <dir>
```

## What the released data looks like

| field | what it is |
|---|---|
| `text` | one brief excerpt |
| `citations_in_segment` | the citation strings stated in it, full and short forms alike |
| `list_hallucinations` | span → defect type, plus `optional` spans the benchmark's own evaluator excludes |
| `list_hallucination_types` | citation → defect types |

The benchmark's own metric scores a *span*: a prediction counts when either
string contains the other. This project reports a verdict per citation
identifier, so [`dataset.py`](dataset.py) builds records from
`list_hallucination_types`, which is keyed the same way.

The eval split holds 390 excerpts and 1,334 citations, 311 of them labelled
defective:

| type | citations | decidable from |
|---|---:|---|
| `content_misrepresentation` | 129 | the cited page |
| `case_name_mismatch` | 57 | a locator lookup |
| `wrong_pincite` | 53 | the cited page |
| `misquote` | 41 | the cited page |
| `non_existent_citation` | 31 | a locator lookup |

## Extraction coverage

```bash
uv run python -m evaluations.lephantomcite.extraction_coverage  # via a script; see below
```

LePhantomCite's own system has no extraction stage: its agent reads the excerpt
and writes citations into a natural-language belief state, so a citation it
never noticed and one it noticed and judged wrongly are the same event in its
F1. Measuring the stage separately is the only way to tell those apart.

Each benchmark citation string is run through the same extractor as the excerpt
it came from, and the two are compared on the resulting identifier — volume,
reporter and page, punctuation and case removed — so a benchmark writing
`F.Supp.2d` and an excerpt writing `F. Supp. 2d` agree. Short forms count:
`755 N.E.2d at 598` is one of the benchmark's citation strings.

**1,236 of 1,237 identifiers recovered across 390 excerpts; 387 excerpts
recovered whole.** The single miss is a truncated duplicate in the released
data — `25 F. App'x at 541` stated beside the correct `425 F. App'x at 541` in
the same row — so extraction is right to find only the second. It is counted as
a miss rather than dropped: a coverage number that discards rows it dislikes is
not a coverage number.

## The identity probe

```bash
uv run --env-file .env python -m evaluations.lephantomcite.run_locator_probe \
  --dataset <dir>/eval.jsonl --output locator-probe.json
```

Resolves every citation against CourtListener and stops there. No model is
called. What it measures is how much of the benchmark is decidable before any
semantic judgement is attempted, and what that costs in abstention.

The outcome vocabulary is the reason to run it:

| outcome | what it establishes |
|---|---|
| `resolved` | one cluster; the authority exists and can be compared |
| `ambiguous` | several clusters; identity is not yet settled |
| `refuted` | the reporter series named does not exist, so no volume or page of it can. Established offline against the reporter database, before any request. Positive evidence of fabrication |
| `unresolved` | the series is real and the archive holds no case there. May only mean the citation is unindexed. Asserts nothing |
| `unparsed` | the string states no reporter locator at all |
| `failed` | the lookup itself broke |

`refuted` and `unresolved` are the distinction. A benchmark scored on a binary
label records them identically, and a system that treats the second as a defect
flags correct citations that happen to be missing from the archive — which the
LePhantomCite paper measures on its own systems at 24.0% for GPT-5 and 65.9%
for Qwen3.5.

Lookups are deduplicated on the parsed locator and retried with exponential
backoff on a rate limit, since a 429 says nothing about a citation. Point
`COURTLISTENER_BASE_URL` at a caching proxy before running the full split.

## Validation sweep

```bash
uv run --env-file .env python -m evaluations.lephantomcite.run_validation \
  --dataset <dir>/eval.jsonl --output-dir run-lephantomcite --label wrong_pincite
```

Runs the whole pipeline over selected excerpts, writing one serialized
`ValidatedDocument` per excerpt so a run resumes and a trace can be read back.
`--label` restricts the sweep to excerpts carrying one defect type, which is how
a single category is measured without paying for the rest:

| label | excerpts |
|---|---:|
| `content_misrepresentation` | 127 |
| `wrong_pincite` | 43 |
| `case_name_mismatch` | 42 |
| `misquote` | 36 |
| `non_existent_citation` | 29 |
