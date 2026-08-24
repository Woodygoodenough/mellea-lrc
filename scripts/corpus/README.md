# Corpus regeneration

Re-renders false-citation-bench from its PDFs with the pleading-paper margin
and the mislabelled page furniture removed, and carries every gold span onto
the new rendering. Writes `derived/extraction.jsonl` and, beside it,
`derived/extraction_locators.jsonl` holding only the volume-reporter-page
records — eyecite does not model docket numbers, so a tokenizer scored against
a denominator containing them takes a constant penalty that says nothing about
the tokenizer.

```bash
uv run python -m scripts.corpus.regenerate \
  --benchmark data/false-citation-bench \
  --output data/false-citation-bench-v2
```

## Why the rendering changes

The shipped corpus is a Docling rendering of the filings, and the annotations
are offsets into that rendering — so the rendering is part of the dataset's
contract, and changing it is a deliberate act.

Docling reads the numbered left margin of pleading paper correctly, one item
per number with its own bounding box, but files those items under the `body`
content layer rather than `furniture`. `export_to_text` keeps the body, so the
margin survives into the text and lands wherever the page broke — including
inside a citation:

```
... decision in Advanced Textile , 214 F.3d

1

2
...
28

1058 (9th Cir. 2000), as restricting
```

Eight of the twenty-six filings are laid out this way, 4,854 numbers between
them. The corpus documents three citations excluded for not being stated
"completely in one run", and two of them *are* stated completely in the filing
and broken only by the rendering.

## What the run reports

Two different things move the text, and only one of them is under test, so
each filing is rendered twice — with the margin rule and without — and both are
aligned against the shipped text.

| column | meaning |
|---|---|
| `margin` | margin items reclassified as furniture |
| `carried` | gold spans projected onto the new rendering and verified |
| `drift_fail` | spans that also fail without the margin rule — Docling version drift |
| `total_fail` | spans that fail with it |

`total_fail - drift_fail` is what the margin rule costs. On the corpus at
Docling 2.115 it is **zero**. 574 of 594 spans carry over exactly, and the 20
that do not were read one by one:

| how many | what differs | example |
|---:|---|---|
| 17 | one space | shipped `2016 WL1448829`, here `2016 WL 1448829` |
| 1 | one period | shipped `455 US. 363`, here `455 U.S. 363` |
| 2 | OCR output, in body text | shipped `U.S. Fid. & Guar. Co.`, here `U.S. Fidelity & Guaranty Co.` |

The last two are in a scanned filing, not a table. The shipped rendering also
reads `(N.D. Fila. 2016)` where this one reads `(N.D. Fla. 2016)`.

## Pin the version

The rules here read text-item geometry, which is stable across versions.
Character-level rendering and OCR are not, and between them they account for
every span this process cannot carry over. Record the Docling version
alongside any regenerated corpus, so the rendering the spans address is
reproducible from the PDFs.

## Carrying spans over

Old and new text are aligned with `difflib`, and each span is projected through
the blocks the two renderings share. Two rules keep a silent mistake from being
possible:

- a span whose **either** end falls inside a changed region is reported, not
  guessed at;
- a span that projects cleanly is still rejected unless the text at the new
  offsets equals the annotation's own `matched_text`.

The second matters more than it looks. An offset can project cleanly and still
land on the wrong thing when the rendering changed nearby, and comparing the
string is what turns a misplaced annotation into a reported one.

## The case-name annotation

`derived/case_names.jsonl` holds one row per row of
`derived/extraction_locators.jsonl`, recording the case name **as the filing
wrote it**. `regenerate.py` rebuilds it at the end of every run, because the
names address offsets into the text that run just wrote. It can also be built
on its own against an existing corpus:

```bash
uv run python -m scripts.corpus.build_case_names data/false-citation-bench-v2
```

### Why the corpus needs it

`extraction.jsonl` records where a citation's volume, reporter and page sit and
nothing else. That scores whether a citation was *found*, never whether it was
*understood* — and a name check has nothing to compare against. Twenty
citations in this corpus could not be classified for exactly that reason: a
name disagreeing with the archive is either a real defect or a misreading, and
without the filing's own text there is no way to tell which.

### The name always comes out of the document

Every name is text that occurs in the filing, copied at a recorded span, never
supplied by an archive or a lookup. A name taken from an external source would
agree with that source by construction and could never evidence a defect. Every
row is checked by slicing the document at `case_name_span` and comparing; the
build fails rather than writing a row that does not slice out, and rejects a
name whose span ends after the locator begins.

| field | meaning |
|---|---|
| `id`, `document`, `span`, `matched_text` | the locator row this name belongs to |
| `case_name_written` | the name as the filing wrote it, or `null` |
| `case_name_span` | `start`/`end` into `documents_txt/<document>` |
| `evidence` | which reader produced it |
| `needs_review` | a person should look before this is used as ground truth |
| `review_reason` | why, `;`-separated |

### Two readers, and where they disagree

Two independent readers run on every row. `extractor_parties` (466 rows) is
eyecite's parsed caption, located in the text rather than trusted. `backward_scan`
(74 rows) reads back from the locator for an `X v. Y`, `In re X` or `Matter of
X`, and is the only reader that works where eyecite parsed the citation without
a caption. `extractor_partial` (36 rows) is eyecite naming one party.

Where both answer and name different cases, the row is flagged rather than one
being trusted silently — a disagreement here is exactly the misreading that
would otherwise become ground truth. Checked against a separately produced
annotation of the same 585 rows, the two agree on 447 and differ outright on
25; the built-in cross-check flags **all 25**.

| rows | `review_reason` |
|---:|---|
| 102 | `table-of-authorities row` — correct far more often than not, but the reader is known to struggle there |
| 36 | `only one party found` |
| 22 | `the two readers disagree` |
| 9 | `no case name found` |
| 5 | `name is far from the citation` |

156 of 585 rows carry at least one reason. The flag is not a claim the row is
wrong.

### Spans

`case_name_span` is recorded so a name can be scored the way a locator is, and
so any row can be re-read in context. Whether name spans should be *scored* as
spans is open: a caption has no single correct extent — `Vance ex rel. Wood v.
Midwest Coast Transport` and `Wood v. Midwest Coast Transport` name the same
case — so span-exact scoring would penalise readings that are not wrong. 124 of
the 129 differences between the two annotations are one name contained in the
other, which is the size of that effect measured rather than assumed.
