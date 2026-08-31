# Track A handoff

Newest entry first. Written by Track A for Track B. See
`exploration/parallel-work.md` for the boundary.

---

## 2026-08-22 — opening state

Branch `experiment/reference-dataset` at `a4c7bff`. Everything below is already
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

---

## 2026-08-22 — statutes, tables, and a note about worktrees

**A United States Code index now exists**, at `src/mellea_lrc/statutes/us_code.py`
with tests. It answers, for a title and section, whether the provision exists
and whether it is in force, from the Office of the Law Revision Counsel's bulk
XML. Written by a supporting agent and merged onto this branch at `b36e094`.

Measured against the 26 test filings: of the 52 federal statute citations in
titles 28 and 42, **52 exist and are in force and none is missing**. So there
is no base rate of fabricated federal statute citations in this corpus to
report — which is worth knowing before anyone builds a verdict around it.

**A gap that was not known before, and that changes the statute numbers.**
eyecite cannot parse a statute section whose number carries a letter or a dash.
`42 U.S.C. § 1983` parses; `42 U.S.C. § 2000e-2`, `15 U.S.C. § 1681g` and
`29 U.S.C. § 794a` do not — they come out as an unparsed `§`. Counting statute
citations as written against those parsed:

| corpus | written in the text | parsed | not parsed |
|---|---:|---:|---:|
| 26 test filings | 85 | 75 | 10 (12%) |
| 109 sampled filings | 529 | 413 | 116 (22%) |

Every miss in the test filings is a letter-suffixed section. The statutes
affected are not obscure: Title VII employment discrimination is `2000e-2`, the
Fair Credit Reporting Act is `1681` with letter suffixes throughout, and the
Securities Acts are `77` and `78` likewise. Any statute work should treat this
as the first problem rather than the existence check, because 12% to 22% of the
citations never reach a checker at all.

**The last extraction gap stays open.** Docling's cell matching is what cuts
the two table-split citations apart, and turning it off loses 18 case citations
to recover 2. Written up in `exploration/notes/table-cell-matching.md`. I have
no further lead; the two stay in the denominator.

**If you are a subagent with an isolated worktree, check your base.** Worktrees
created by the Agent tool branch from the default branch, not from
`experiment/reference-dataset`. See section 2 of `parallel-work.md`.
