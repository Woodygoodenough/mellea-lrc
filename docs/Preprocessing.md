---
tags: [preprocessing, docling, layout, offsets]
status: active
---

# Preprocessing

Preprocessing turns a filed document into the plain text every later stage
reads. That text is not a convenience: every span an extraction or a validation
produces is a character offset into it, so what preprocessing decides to keep
or remove defines the coordinate space the rest of the project works in. Two
renderings of the same PDF are two different documents.

---

## Running it

```python
from mellea_lrc.preprocessing import preprocess

document = preprocess("filing.pdf")
```

`preprocess(path)` picks a backend from the suffix:

| suffix | backend | what happens |
|---|---|---|
| `.txt` | `plain_text` | read as-is |
| `.pdf` `.docx` `.pptx` `.xlsx` `.html` `.htm` `.md` | `docling` | converted with [Docling](https://github.com/docling-project/docling) |
| anything else | — | `ValueError` |

Docling is an optional dependency: `uv sync --group preprocessing`. Importing
the backend without it raises with that instruction rather than failing
obscurely.

**A text file is its text.** A `.txt` file is read whole, with nothing split off
the front, so an offset into the file and an offset into the document are the
same number. Provenance — where the document came from, what converted it, which
rules ran — belongs beside the text, never inside it.

## What comes back

`PreprocessedDocument`:

| field | what it is |
|---|---|
| `text` | the document's text; every later offset indexes this |
| `source_metadata` | original path and `SourceFormat` |
| `preprocessing_metadata` | backend, version, which layout rules ran and how much each removed |
| `index_spans` | regions of `text` holding a table of authorities |

`text` may not be empty — a conversion that produced nothing raises rather than
handing an empty document downstream.

## Layout rules

A court filing is printed with furniture around the writing, and a converter
that reads the page faithfully reads the furniture too. A margin number lands
inside a citation; a filing stamp is read as a date. Each rule removes one kind,
and each selects by **where an item sits on the page**, not by what it says:

| `Rule` | what it does |
|---|---|
| `MARGIN_LINE_NUMBERS` | the numbered left margin of pleading paper |
| `REPEATED_FURNITURE` | running heads and page numbers the converter labelled inconsistently |
| `DOCKET_STAMP` | the stamp an ECF system prints across the top of a filed page |

All of them run by default. Pass a list to `preprocess` to run exactly those,
or an empty list for the converter's own reading. Which rules ran is
recorded in `preprocessing_metadata`, because a rule that ran and a rule that
found nothing produce the same text only by coincidence — and different rules
produce different offsets.

## Tables are read, not rebuilt

Docling's table structure model is off. A table is emitted as text in page
reading order rather than rebuilt as cells, so no cell separator enters the
text and a row that a filing prints as one line reads as one line. This matters
most in a table of authorities, where cell reconstruction routinely put a case
name and its citation in different cells, or in reversed order, leaving a
citation no parser could find.

Reading order is still Docling's, not the page's. A run of prose can be emitted
some distance from where the page prints it, so a window taken around a span is
a window in this text — not a guarantee about what physically surrounds it.

## The table of authorities

`index_spans` marks the regions holding an index of cited cases. An index entry
lists a case and attaches no proposition to it, so a citation inside one states
nothing to check; validation reads the field rather than re-deciding it. Empty
means unknown, not none — plain text carries no structure to judge from.
