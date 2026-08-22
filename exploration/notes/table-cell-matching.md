# Turning off Docling's cell matching does not pay for itself

Written 22 August 2026. Recorded because it was the only remaining lead on the
last extraction gap, and it fails.

## The gap

Two citations in the test corpus are printed plainly on the page and cannot be
recovered from the text, because Docling's table reader cuts them apart. In
document 022 the index line reads `2016 WL 9137645, at 3 (C.D. Cal. July 25,
2016)` and the text holds `2016` in one cell and `WL 9137645` in the next.
Nothing in the citation reader reaches them, and they are the difference
between 583 of 585 and a clean sweep.

## What was tried

Docling exposes two relevant settings: `do_table_structure`, which turns table
detection off entirely, and `table_structure_options.do_cell_matching`, which
matches the model's predicted cells against the text cells in the PDF. Mode is
already `ACCURATE`.

On document 022, both alternatives fix the split citation:

| setting | the index line, as extracted |
|---|---|
| tables on, cell matching on (current) | `16 \| \| \| WL 9137645, at 3` — split |
| tables on, cell matching **off** | `Doe v. Rose , \| \| \| 2016 WL 9137645, at 3` — whole |
| tables **off** | `Doe v. Rose , 2016 WL 9137645, at 3` — whole and readable |

So cell matching is what cuts the citation.

## Why it is not worth taking

Turning it off costs more than it recovers. Counting full case citations
across ten filings — the seven holding an index table and three controls:

| document | now | cell matching off | change |
|---|---:|---:|---:|
| 007 | 22 | 19 | −3 |
| 008 | 40 | 38 | −2 |
| 021 | 50 | 41 | −9 |
| 022 | 52 | 49 | −3 |
| 023 | 30 | 29 | −1 |
| 013, 025 | | | 0 |
| 001, 006, 019 (no index table) | | | 0 |

**Eighteen citations lost to recover two.** The three documents without an
index table are unaffected, which confirms the change acts only on tables, and
that within tables it does more harm than good: without cell matching the model
predicts the text as well as the layout, and its reading of a dense table of
authorities is worse than the PDF's own text.

## What is left

The two citations stay unrecovered and stay in the denominator, which is where
report section 12 leaves them.

One option is not ruled out: keep cell matching on for the document, and render
the index tables a second time without it, using that second reading only to
recover citations from those regions. That is two renderings and a span
reconciliation between them, for two citations in 26 filings, so it is recorded
as possible rather than recommended.
