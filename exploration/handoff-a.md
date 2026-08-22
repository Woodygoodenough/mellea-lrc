# Track A handoff

Newest entry first. Written by Track A for Track B. See
`exploration/parallel-work.md` for the boundary.

---

## 2026-08-22 — opening state

Branch `experiment/lephantomcite` at `a4c7bff`. Everything below is already
committed and pushed to `woody-fork`.

**What is finished on A's side and will not move under you:**

- Extraction reads 583 of 585 case citations in the 26 test filings, at 100%
  precision. The two it misses are split across table cells and are not
  reachable by any change to the citation reader.
- The layout rules (page margin, repeated page furniture) are on by default in
  `preprocess_with_docling`. If you call preprocessing, you get cleaned text.
- `data/false-citation-bench-v2/` is the corrected corpus, local and
  gitignored. Its `derived/extraction_locators.jsonl` holds the 585 case
  citations; `extraction.jsonl` holds those plus 11 docket numbers. **Use the
  locator file** unless you specifically want dockets, which eyecite does not
  model.

**Three things you will want that already exist:**

- `mellea_lrc.extraction.citation_tree.build_citation_tree` groups every
  reference under the case it points at, so a short form or an `Id.` becomes
  its own claim with its own pin cite. Its `out_of_scope` field holds statutes
  and unparsed spans, kept apart from `unattributed`, which is genuine failure.
  On the test filings `unattributed` is 20 and 19 of those are `Id.` carrying a
  paragraph pin cite.
- `mellea_lrc.preprocessing.document_index.index_table_spans` marks the regions
  holding a table of authorities. 103 of 643 citation occurrences sit in one and
  assert nothing, so pin-cite work should exclude them before looking for a
  proposition.
- `mellea_lrc.experimental.page_crops.crop_span` turns a character span back
  into an image of the page region it was printed in. It is how every disputed
  citation in this corpus was settled, and it will answer questions about a
  proposition faster than reading extracted text will.

**Numbers you can rely on for planning the pin-cite work** (report section
17.3): 643 citation occurrences, 103 in an index, 201 with no pin cite, leaving
339 pinpoint claims. 276 of those name a page that can be fetched; 63 are star
pagination into a slip opinion and have no reporter page. The 339 rest on 257
distinct cases, so identity resolves 257 times.

**One thing I would like from you, when convenient:** the two table-split
citations in report section 12 are the only extraction losses left, and both
are Docling table-parsing defects. If your work on the miner or statutes turns
up anything about Docling's table settings, put it in `handoff-b.md` — it is
the last open extraction question and I have no lead on it.

**One caution.** I have spent CourtListener quota today. The allowance is
yours from here; I will not run anything against the API without writing an
entry here first.
