# The pleading-paper margin

## The case that started it

`022__chelsea-montes...reply`, at the page 7/8 boundary:

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
the left-margin line-number column of California, Nevada and Arizona pleading
paper: Docling reads it as a block of its own, and when the page broke
mid-sentence the block landed inside the citation.

Nothing about the citation is damaged. It is **interrupted**, by material that
is not part of the sentence and is not part of the document's running text at
all.

## It is systematic, not incidental

| | |
|---|---:|
| documents with a margin | 8 of 26 |
| margin numbers | 4,854 |
| documents in the corpus with none | 18 |

## The rule

`src/mellea_lrc/preprocessing/margin_line_numbers.py`, working on the
`DoclingDocument` rather than on exported text.

Docling classifies page headers and footers as `furniture`, and
`export_to_text` keeps only the body — so headers and footers are already
dropped. The margin numbers are read correctly, one item per number with its
own bounding box, but filed under `body`. **That single misclassification is
the only reason they reach the text at all.** So the fix is not a filter but a
correction: reclassify them as the furniture they are, and the existing export
needs no change.

The margin is a column, and the object says so plainly:

| | margin right edge | prose left edge |
|---|---:|---:|
| document 022, page 7 | 60.0 | 72.0 |
| document 011, page 1 | 87.8 | 104.4 |

A run of numbers is a margin when it is a column of bare integers, aligned on
the right, at least five of them, sitting left of where the page's prose
begins. All three conditions carry weight: alignment separates a margin from
numbers that merely happen to be short, the count separates it from a stray
figure, and the position separates it from a numeric column inside a table.

The prose edge is a **median** rather than a minimum. Docling does not always
separate the margin cleanly — on some pages it absorbs the first few line
numbers into the text item beside them, as `1 JULIE A. TOTTEN (STATE BAR NO.
166470)`, and that item's box starts out in the margin. One such item drags a
minimum across the column boundary and defeats the test for the whole page. It
does not move a median.

## The result: preprocessing is what makes the tokenizer safe

The relaxed tokenizer joins volume to reporter across a blank line, but bounds
the reporter-to-page join to a single newline. That bound is not arbitrary — it
exists because of this exact artifact. Removing it and removing the margin are
each useless alone, and together they are the fix:

| | bounded join | symmetric join |
|---|---|---|
| **margin present** | 1 site (table of authorities only) | `214 F.3d` **`1`** — *the wrong page* |
| **margin removed** | 1 site (table of authorities only) | `214 F.3d` **`1058`** — correct, 2 sites |

The top-right cell is the whole argument. A more permissive tokenizer applied
to margin-bearing text does not miss the citation; it reports a **confident
verdict about a page nobody cited**, which is worse than silence and is why the
bound was there. Correct the rendering and the same relaxation becomes right.

This is the general claim the project makes, in one measurable instance:
**structure-aware preprocessing is what lets the downstream stage be simpler
and safer at once.** The alternative — a tokenizer defending itself against
artifacts of its own input — pays for that defence in recall on every document,
including the ones with no margin at all.

## What the benchmark says, and why it should change

The gold set does not contain the recovered occurrence, and that is not an
oversight. `derived/extraction.md` names this citation among its deliberate
exclusions:

| document | what the text has | what is missing |
|---|---|---|
| `022` | `214 F.3d` followed by a page break and margin line numbers `1..28` | the page — the true citation is 214 F.3d **1058** |
| `022` | `WL9137645` | the volume `2016`, which sits in a separate table cell |
| `025` | `WL6200979` | the volume, absent from the source entirely |

The stated rule is that an identifier is recorded only when the text states it
**completely in one run**. Read against the plain text, that is correct and the
exclusion is honest.

But the first two exclusions are artifacts of the **rendering**, not of the
filing. Document 022 does state `214 F.3d 1058` completely: the halves are
consecutive on the page, and what separates them in the rendering is a margin
the rendering should never have contained. The rule is sound; the coordinate
space it was applied to is what loses the citation.

That is the case for treating the corpus as revisable. A benchmark whose
exclusions encode one converter's failures will keep encoding them, and every
system measured on it inherits the same blind spot — including the systems that
have fixed the underlying problem. *Stated completely in one run* is a good
rule. It is not a reason to keep a rendering that interleaves a page margin
into the middle of sentences.

The third exclusion does not benefit. `2016 WL 9137645` is split across two
rows of a table Docling parsed badly — badly enough that other rows merge text
from different entries outright (`2023 WL 3568691, at 3 - 4 (W.D. Wash. May Doe
v. Bell Atl. Bus. Sys. Servs., Inc. ,`). Structure does not help when the
structure is itself wrong, and table parsing is where these conversions are
least reliable.

## Re-deriving the corpus

Offsets move when the margin goes, and that is a cost of the fix rather than an
argument against it: the offsets in question address a rendering that is wrong
about the document. The corpus is regenerated from the cached conversions with
the margin dropped, and the gold spans are re-derived by aligning the old text
against the new and projecting each span through the equal blocks.

Two causes of movement have to be told apart, so each document is rendered
twice — once with the margin rule and once without — and both are aligned
against the shipped text. Failures present in *both* are Docling version drift;
only the difference is attributable to the rule.

## The text rule, and why it was removed

An earlier version of this work inferred the margin from the exported text: a
run of short integers, alone on their lines, ascending by one. Measured against
the geometry across all 26 documents, the comparison ended it.

The two rules agree exactly on *which* filings are pleading paper — the same
eight, no disagreement in either direction — and not at all on how much of the
margin they see:

| doc | pages | items | geometry | text rule |
|---|---:|---:|---:|---:|
| 011 | 7 | 97 | 25 | 21 |
| 013 | 70 | 2384 | **1930** | 356 |
| 018 | 10 | 417 | 277 | 275 |
| 019 | 17 | 519 | 391 | 390 |
| 020 | 32 | 1147 | **864** | 17 |
| 021 | 21 | 766 | 587 | 526 |
| 022 | 16 | 586 | 446 | 414 |
| 023 | 12 | 453 | 334 | 274 |
| **total** | | | **4854** | **2273** |

The text rule misses 53%. Where the rendering is clean the two agree closely
(018: 277 vs 275). Where it is not, the text rule collapses, and document 020
shows why in one line — its margin reaches the text as

```
1  2  3  4  5  6  7  8  9  10  12  13  14  ...
```

with `11` missing, and a rule requiring a run ascending by exactly one sees 864
margin numbers as 17.

That is the general shape of the failure. The text rule reconstructs the margin
from properties that are *consequences* of being one — consecutive integers,
isolated on their lines — and every one of those is destroyed by ordinary
rendering noise, worst in exactly the documents where the margin does the most
damage. The geometric rule reads the property that *defines* a margin, which is
what the rendering discards.

A rule whose recall depends on whether the converter happened to drop a number
is not one to defend, so it was removed rather than kept as a fallback.

## Why not an LLM here

A model would read this page correctly — the margin is obvious to a reader. But
it is not a judgement call. In the structured document the margin is a column
with its own coordinates, recurring thousands of times, and removing it is a
reclassification. Paying for a model call per site would buy no accuracy and
would put a generative step underneath the span arithmetic that everything
downstream depends on.

The model earns its place on the *unsystematic* residue — damage with no
repeatable shape — which is what `grounded_adjudication` handles through the
`production+recovery` and `layout-tolerant+recovery` arms. Structured
decomposition first; adjudication for what structure cannot reach.

## Reproducibility

Re-converting document 022 with Docling 2.115 does not reproduce the shipped
rendering byte for byte — 99.86% similar, with the differences almost entirely
**table cell boundaries** in the table of authorities. Text-item geometry, which
is all the margin rule reads, is far more stable than table structure
inference.

Regenerating the corpus therefore means pinning the Docling version and
recording it with the corpus, so that the rendering the gold spans address is
reproducible from the PDFs.
