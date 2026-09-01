# The pleading-paper margin, and what removing it leaves

## The problem

Pleading paper numbers its lines down the left margin. Docling reads that
column correctly but files it under the body layer, so it survives into the
exported text as a run of integers landing wherever the page broke — often
inside a citation:

```
Advanced Textile, 214 F.3d

1

2

...

28

1058 (9th Cir. 2000)
```

The citation is `214 F.3d 1058`. A tokenizer that crosses blank lines reads
page **1**. That is not a missed citation, it is a wrong one, and it sends
verification to a different case and returns a confident verdict about it.

## The rule

`reclassify_margin_line_numbers` finds the column geometrically rather than by
pattern: numeric text items that form a right-aligned column left of the median
prose edge, at least `MIN_MARGIN_NUMBERS` of them on a page. Reclassifying them
out of the body layer is what removes them from `export_to_text`.

It runs on every Docling conversion, so it reads the text layer defensively: a
document shape it does not recognise yields no margin rather than stopping
preprocessing.

**Removing the margin moves every offset after it.** Text rendered with and
without the rule are different coordinate spaces, which is why
`PreprocessingMetadata.margin_line_numbers_dropped` records which was used.
`None` means the rule did not run, and is not the same as zero.

## What it is worth

Regenerating the eight `false-citation-bench` documents that carry a gutter,
with the rule on, removed **4,854 margin numbers** and took the count of
documents with a gutter from 8 to 2.

So the rule is good but not complete. **The two survivors are the first thing
to look at** — they are the sharpest available test of the geometric heuristic.

## What it does not fix

Removing the margin does not make an unbounded whitespace relaxation safe. On a
mined corpus of real filings, relaxing the reporter-to-page join across blank
lines produced four errors; only one was a margin case, and the other three
occurred in text this rule had already cleaned:

- a reporter eating a digit off the page number: `206 P. 327` → `206 P.3 27`
- two adjacent citations gluing across a break, destroying the second:
  `607 F.3d 355` → `130 S.Ct. 607`
- a procedural rule read as a case: `Fed. R. Civ. P. 11(b)(2)` → `1 Fed.R. 1`

"We will handle it in preprocessing" is true about the margin case and wrong
about the rest.

## A versioning question this branch does not answer

`data/false-citation-bench/documents_txt/` is the artefact the published
annotations are anchored to. Regenerating it with this rule on shifts every
offset in those eight documents and invalidates their spans. That is a
versioning decision, not a preprocessing one, and it should not happen as a
side effect.
