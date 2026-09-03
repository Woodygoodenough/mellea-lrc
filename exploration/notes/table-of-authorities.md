# The table of authorities, which cites nothing

## The distinction

A brief opens with an index of the cases it relies on:

```
Doe v. Megless , 654 F.3d 404 (3d Cir. 2011) ...................... 8, 12, 13
```

That entry is a *listing*. It attaches no proposition to the case, makes no
claim about any page of it, and the numbers trailing the dot leaders are pages
of the brief rather than of the reporter. There is nothing in it that can be
right or wrong beyond the case existing.

Extraction cannot see the difference, because by the time the document is text
the index reads like any other run of citations.

## How much of the corpus this is

On false-citation-bench, **113 of 302 citation occurrences** in the seven
filings that carry an index — **37% of them**, every one asserting nothing.

Counting those beside citations a brief actually argues from inflates any
coverage figure, and sending them to a pinpoint check spends retrieval on a
question nobody asked.

## How they are found

Docling already knows. It labels these tables `document_index`, distinctly from
an ordinary `table`, in 14 of the 20 tables across the corpus.
`index_table_spans` turns that label into character spans over the exported
text.

The spans are measured **by rendering twice and taking the difference**, not by
searching the output. An index entry can repeat verbatim in the body — that is
what an index is — and a search could not tell which occurrence it had found.

## Located, not removed

The index is independently useful: it is the document's own declaration of what
it cites, and therefore a free check on whether extraction found everything. An
identifier listed in the index and absent from the body is either a genuine
index-only entry or an extraction miss.

On this corpus that check finds a real one — `759 F.2d 1032` in document 007,
which reaches the text as `759\n\nF.2d 1032`.

## What is left open

`index_spans` is carried on `PreprocessedDocument` and nothing consumes it yet.
The two obvious consumers are a coverage figure that reports argued citations
separately from listed ones, and a validation pipeline that does not spend a
pinpoint check on a listing.

Six of the twenty tables were not labelled `document_index`, so a filing whose
index Docling labelled an ordinary table yields no spans. Empty means unknown,
not none — plain text carries no structure at all — and a consumer has to treat
it that way.
