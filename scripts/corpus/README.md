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
