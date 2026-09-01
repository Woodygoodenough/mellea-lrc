# Page furniture Docling labelled inconsistently

## The problem

Docling labels the running head and foot of a page `page_header` and
`page_footer`, and `export_to_text` drops both. It does not always apply those
labels to the same thing on every page.

In one filing the identical string

```
Case 2:26-cv-05379-JAT   Document 13   Filed 08/07/26   Page 3 of 9
```

sits at the same coordinates on six pages and is labelled `page_header` on one
of them and `section_header` on the other five. The five stay in the body, and
one of them landed inside a citation's parenthetical, where eyecite read the
`9` of "Page 3 of 9" together with the date that followed and reported a
citation of `9 Mar. 10`.

## The rule

The document contains the evidence needed to fix this. Docling got the label
right *somewhere*, and page furniture is by definition printed at the same
place on every page. So an item sitting at coordinates where this document has
a recognised header or footer is a header or footer, whatever label it was
given.

Boxes must agree on all four edges, not merely overlap. Running furniture is
printed from the same template on every page, so its coordinates repeat to
within a fraction of a point; anything needing a looser test is not the same
element, and a looser test would start matching first lines of body text.

## What it finds

Across the two corpora: **43 items in 13 of the 26 benchmark filings**, and
**286 in 51 of the 109 harvested ones**. Three kinds of thing:

- running heads that were labelled `section_header` or `text` on some pages;
- page numbers at the foot, labelled `page_footer` on one page and `text` on
  the rest;
- a firm name set sideways in the margin, in a box 7 points wide and 108 tall,
  labelled `page_header` on one page and `text` on another.

## It is not wired into preprocessing

`preprocess_with_docling` does not call it. The rule and its measurement are
here; applying it is a separate decision, because **removing an item moves the
offset of everything after it**. Text produced with the rule and without it are
different coordinate spaces, exactly as with the pleading-paper margin, and any
corpus already annotated against the current output would have its spans
invalidated.

Turning it on should therefore come with the same treatment the margin rule
got: a field on `PreprocessingMetadata` recording whether it ran, so a document
says which coordinate space it is in.
