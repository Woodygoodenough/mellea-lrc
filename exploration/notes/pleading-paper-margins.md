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

Reconverting all 26 `false-citation-bench` PDFs with the rule on removed
**4,854 margin numbers**, and took the count of documents carrying a gutter
**from 8 to 0**.

A gutter here is four or more consecutive ascending integers, each standing
alone on its own line, read off the exported text. Loosening that to three
leaves one run in one document; to two, a handful of pairs in three documents,
and reading them shows a numbered list and some table cells rather than margin
residue. `214 F.3d 1058` reads intact in document 022.

`data/false-citation-bench-v2.0/` holds the regenerated text and the
per-document report. **The published annotations do not transfer to it** —
removing a margin moves every offset after it — so it is a new dataset version
and not a replacement.

An earlier draft of this note said the rule took the count from 8 to **2**, and
that two survivors were the first thing to look at. That does not reproduce.
The removal count is identical to the figure that draft reported, so the rule
is the same; whatever the "2" counted, it was not gutter runs in the exported
text. **On this corpus the rule is complete**, and the case for changing it is
not recall.

## Where it is still narrow

The eight gutter documents are all California/Nevada/Arizona pleading paper,
and the rule's geometry is written for exactly that: a left margin, judged one
page at a time, on position alone. The corpus cannot say what happens to a
right-hand margin, a two-column layout, or a page where Docling absorbs enough
line numbers to drop it under the count threshold, because it contains none of
those.

`exploration/margin_rules/` scores candidate rules against a cached layout of
this corpus. The bar it sets is deliberately conservative: since the current
rule is already perfect here, a candidate earns its place only by matching it
exactly while closing a failure this corpus does not contain. What that
measurement found:

| rule | removed | docs with residue | overreach |
|---|---:|---:|---:|
| current | 4,854 | 0 | 3 |
| + strict ascending sequence | 4,194 | **1** | 0 |
| + *mostly* ascending sequence | 4,854 | 0 | 3 |
| + cross-page confirmation | 4,854 | 0 | 3 |
| position widened to either margin | 4,872 | 0 | **27** |

Two results decided it.

**A strict sequence test is unusable, and the reason is worth keeping.**
Document 013 is scanned, and its OCR reads the 9 of every margin as a 6. All 28
numbers are present, in place, correctly positioned, and the sequence still
reads `7, 8, 6, 10`. One misread digit rejects the page; the same digit is
misread on every page; 24 of 70 columns are refused and 660 numbers stay in the
body. Requiring only that the *longest increasing subsequence* cover most of
the column keeps 27 of those 28 and costs nothing measurable.

**Widening the position test to either margin is a regression.** It removes 18
items the current rule does not, in documents 021 and 023, and the overreach
count goes from 3 to 27 — right-hand numeric columns in tables, which the
left-hand assumption was silently excluding. Generality bought that way costs
precision.

The three items the proxy flags against the current rule are all in document
013 and are its misread digits, not a numbered list wrongly taken.

## What would earn v2.1

The mostly-ascending test and cross-page confirmation are both exact no-ops on
this corpus and both close a failure it does not contain — a numeric table
column mistaken for a margin, and a page whose margin Docling partly absorbed.
That is the shape a change should have here. Neither has been made to the
shipped rule.

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
