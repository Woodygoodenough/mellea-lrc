# The margin line-number gutter

## The case that started it

`022__chelsea-montes...reply`, offset 17610:

```
Defendant misinterprets the Ninth Circuit's decision in Advanced Textile , 214 F.3d

1

2
...

28

1058 (9th Cir. 2000), as restricting
```

The citation is `214 F.3d 1058` — *Does I thru XXIII v. Advanced Textile Corp.*
Every character of it survived PDF extraction. What sits between the halves is
the left-margin line-number column of California/Nevada pleading paper, which
Docling emits as a block of its own; when the page broke mid-sentence, the block
landed inside the citation.

This is why the relaxed tokenizer's two joins are relaxed **asymmetrically**. An
unbounded `\s*` on the reporter→page join reads the page as `1` and then hands
the pipeline a confident verdict about a page nobody cited — worse than a miss.

## It is systematic, not incidental

| | |
|---|---:|
| documents with a gutter | 8 of 26 |
| total runs | 104 |
| runs that are a full `1..28` | 50 |
| runs ending at 23 or 28 (the two pleading-paper line counts) | ~all sampled |
| runs detected in the 18 non-pleading documents | 0 |

Short integers, alone on their lines, counting up by one, terminating at the
page's line count. Prose does not look like that. This is a layout artifact with
a signature, which is why a rule can have it.

## The rule

`src/mellea_lrc/experimental/line_number_gutter.py`. Runs are **blanked, not
deleted** — replaced by spaces of equal length, so no offset moves and every
span already measured against the text stays valid. The same choice the
benchmark makes when masking captions. What remains between the citation's
halves is ordinary horizontal whitespace, which the layout-tolerant tokenizer
already crosses.

Effect on the eight affected documents: 309 → 310 occurrences.

- `214 F.3d 1058` recovered at its true offset, with the correct page.
- `556 U.S. 662` gained both its pin cite (`678`) and its case name
  (`Ashcroft v. Iqbal`) — the gutter had been sitting between `See Ashcroft v.`
  and `Iqbal , 556 U.S. 662, 678 (2009)`, truncating the antecedent scan.
- `654 F.3d at 408` gained `Doe v. Megless` as its antecedent.

Nothing was lost.

## Scored on false-citation-bench

| arm | predicted | TP | FP | FN | precision | recall |
|---|---:|---:|---:|---:|---:|---:|
| eyecite | 526 | 526 | 0 | 68 | 100.0% | 88.6% |
| production | 563 | 563 | 0 | 31 | 100.0% | 94.8% |
| layout-tolerant | 581 | 581 | 0 | 13 | 100.0% | 97.8% |
| layout-tolerant+degutter | 582 | 581 | 1 | 13 | 99.8% | 97.8% |

Recall does not move, and precision falls. **The one extra occurrence is the
recovered `214 F.3d 1058`, and it scores as a false positive because the gold
set does not contain it.** Gold records that citation once in document 022, at
offset 10652 — the table of authorities — and not at 17482 where the brief
actually argues from it.

## The annotation blind spot

That is not a one-off:

```
gold occurrences in the 8 pleading-paper documents:   211
  whose span crosses a gutter run:                      0
```

Zero of 211. Yet a gutter-split citation demonstrably exists in those documents,
because we just read one. The gold was built with tooling that could not see
across a gutter either, so citations damaged by layout are missing from the
denominator as well as from the predictions.

Two consequences:

1. **Every system's recall on layout-damaged filings is optimistic**, this
   project's included. The 94.8% and 97.8% above are measured against a
   denominator that omits the hardest cases.
2. **Fixing the damage is penalised.** An extractor that recovers a real
   citation the annotator missed loses precision for it — which is the wrong
   incentive gradient for exactly the failure mode this work is about.

## Recommendation

Keep `layout-tolerant+degutter` as an experimental arm for now; do not promote
the tokenizer chain to production on the strength of a number that a gold gap
is suppressing. The correct order is: add the missing gutter-split occurrences
to the benchmark first, re-score, and promote against a denominator that
contains them.

This is a concrete, defensible correction to make while growing the benchmark,
and it is more interesting in a paper than a recall delta: it is evidence that
extraction-quality benchmarks in this area are self-confirming unless the
annotation pipeline is independent of the extractor.

## Why not an LLM here

A model would read this page correctly — the gutter is obvious to a reader. But
the artifact has a signature that fits in a regex, it recurs 104 times in 26
documents, and the fix is a text substitution that preserves offsets. Paying for
a model call per site would buy no accuracy and would put a generative step
underneath the span arithmetic that everything downstream depends on.

The model earns its place on the *unsystematic* residue — damage with no
repeatable shape — which is what `grounded_adjudication` already handles through
the `production+recovery` and `layout-tolerant+recovery` arms. Structured
decomposition first; adjudication for what structure cannot reach.
