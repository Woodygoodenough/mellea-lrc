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

## What the benchmark says about it

The gold set does not contain the recovered occurrence, and that is not an
oversight. `derived/extraction.md` names this exact citation among the
deliberate exclusions:

| document | what the text has | what is missing |
|---|---|---|
| `022` | `214 F.3d` followed by a page break and margin line numbers `1..28` | the page — the true citation is 214 F.3d **1058** |
| `022` | `WL9137645` | the volume `2016`, which sits in a separate table cell |
| `025` | `WL6200979` | the volume, absent from the source entirely |

The stated rule is that a citation is recorded only when the text states its
identifier **completely in one run**. Read against the plain text, that is a
correct reading and the exclusion is honest.

But two of the three exclusions are artifacts of the plain-text serialization
rather than of the filing. Document 022 does state `214 F.3d 1058` completely:
the two halves are consecutive on the page, and what separates them in the
*rendering* is a margin the rendering should not have contained. The rule is
sound; the coordinate space it is applied to is what loses the citation.

That is the argument for working from the structured document, and it is
sharper than a recall delta: **the plain-text rendering is what makes the
exclusion necessary.** Change the rendering and the citation qualifies under
the benchmark's own existing rule, unamended.

The third exclusion does not benefit. `2016 WL 9137645` is split across two
rows of a table Docling parsed badly -- badly enough that other rows merge
text from different entries outright (`2023 WL 3568691, at 3 - 4 (W.D. Wash.
May Doe v. Bell Atl. Bus. Sys. Servs., Inc. ,`). Structure does not help when
the structure itself is wrong, and table parsing is where these conversions
are least reliable.

## Two implementations, and why both exist

`experimental/line_number_gutter.py` works on the exported text and blanks each
run in place, preserving every offset. `preprocessing/margin_line_numbers.py`
works on the `DoclingDocument` and reclassifies the margin items as furniture,
which is what they are.

The structural rule is the better one, and by a clear margin:

- **It reads the column instead of inferring it.** Line numbers share a right
  edge and sit left of the prose. Nothing about digits has to be guessed.
- **It does not need the numbers to be contiguous or ascending.** On document
  011 the text rule found 21 numbers and the geometry found 25 -- the text rule
  needs an unbroken run between blank lines, and the column does not oblige.
- **It cannot mistake a numbered list for a margin**, because a list sits in
  the text column.

The text rule remains useful for one reason: the benchmark ships text, and its
gold spans address that text. Blanking preserves those offsets; reclassifying
does not, because dropping the margin moves everything after it.

## Reproducibility, and why the dataset ships text

Re-converting document 022 with Docling 2.115 does not reproduce the shipped
rendering byte for byte -- 99.86% similar, and the differences are almost
entirely **table cell boundaries** in the table of authorities. Text-item
geometry, which is all the margin rule reads, is far more stable than table
structure inference.

So shipping the text rather than the conversion was the right call, and the
structural path carries an obligation with it: regenerating the corpus means
pinning the Docling version, and re-deriving every gold span against the new
rendering.

## Why not an LLM here

A model would read this page correctly — the margin is obvious to a reader. But
it is not a judgement call. In the structured document the margin is a column
with its own coordinates, recurring 104 times across 26 documents, and removing
it is a reclassification. Paying for a model call per site would buy no accuracy
and would put a generative step underneath the span arithmetic that everything
downstream depends on.

The model earns its place on the *unsystematic* residue — damage with no
repeatable shape — which is what `grounded_adjudication` already handles through
the `production+recovery` and `layout-tolerant+recovery` arms. Structured
decomposition first; adjudication for what structure cannot reach.


## Where this leaves things

1. Neither rule is on by default. The text rule is an evaluation arm; the
   structural rule is an opt-in flag on the Docling backend, because it moves
   offsets and the shipped gold spans address the current rendering.
2. The next step is the benchmark, not the extractor: regenerate the corpus
   with the margin dropped, re-derive the gold spans, and admit the two
   citations the plain-text rendering currently forces out. The exclusion rule
   does not need to change — the same rule admits them once the rendering stops
   interleaving a margin into the sentences.
3. Only then is it meaningful to promote the layout-tolerant tokenizer, and to
   ask whether its reporter-to-page join still needs its one-newline bound. That
   bound exists to defend against exactly the margin junk this removes; with the
   margin gone structurally, the defence may be redundant. Removing the margin
   alone does *not* recover the citation — a blank line still separates
   `214 F.3d` from `1058` — so the two changes only pay off together, and that
   pairing is the result worth reporting: **structure-aware preprocessing is
   what makes the simpler, more permissive tokenizer safe.**
