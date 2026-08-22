# Candidate case-name annotation, awaiting review

**This is not part of the benchmark.** It is a proposed addition to it, produced
automatically and not yet adjudicated by a person. Nothing here should be used
to score anything until the rows in `review-shortlist.txt` have been read.

## Why it exists

`data/false-citation-bench-v2/derived/extraction.jsonl` records, for each of its
585 locator rows, the volume, the reporter and the page. Nothing else — no case
name, no pin cite, no year, no court.

That gap is not cosmetic. Comparing the extractor's case names against the
CourtListener record over the 26 filings leaves 33 disagreements, and 20 of
them **cannot be classified at all**: a confident, well-formed case name that
shares no word with the record at that page is either a real defect — the
filing named a case that is not there — or the extractor took the name from a
neighbouring citation. The evidence is identical either way. Telling them apart
requires knowing what the filing actually wrote, independently of what the
extractor read, and that is what this file records.

See `exploration/notes/case-name-extraction.md` for the full argument.

## What is in it

One row per locator row in the benchmark, joining on `id`:

| field | meaning |
|---|---|
| `id`, `document`, `span`, `matched_text` | copied from the benchmark row |
| `case_name_written` | the case name **as the filing wrote it**, verbatim |
| `case_name_span` | where that text sits in the document |
| `evidence` | which method found it |
| `needs_review`, `review_reason` | whether a person should look, and why |

**`case_name_written` is always text that literally occurs in the document**,
with the filings' damaged spacing preserved exactly — `'Boeser  v.  Sharp'`,
`'Doe v. Colgate Univ .'`. That is the property that makes the file usable: a
name is recorded because the filing contains it, never because an archive
supplied it. No CourtListener string was written into this field at any point.
An archive record was consulted only to decide whether to flag a row for
review.

Verified independently of the code that wrote it:

- 585 of 585 rows join to a benchmark locator row on `id`, `document` and `span`
- 585 of 585 slice correctly: `text[case_name_span] == case_name_written`
- 585 of 585 name spans end at or before the locator begins
- 0 rows have a null name — every locator in this corpus has at least a
  short-form party name before it

## What it changes

Against the same CourtListener records, under the same comparison rule:

| | agree | disagree |
|---|---:|---:|
| the extractor's own parties | 321 | 34 |
| this annotation | **330** | **25** |

The nine recovered rows are cases where the extractor truncated a party
(`Estate  McCall` for `Estate of McCall v. United States`), swallowed a docket
number into the defendant, or attached the previous citation's parties to a
short form.

## What still needs a person

184 rows carry `needs_review`, but 128 of those carry only bookkeeping flags —
the row sits in a table of authorities, or its name span is shared with an
adjacent parallel citation, which is correct rather than wrong. The genuinely
contestable population is about **56 rows**, and `review-shortlist.txt` holds
the top 22 with surrounding document text.

Two groups in that shortlist matter most:

**Rows that look like real defects.** `In re Amica Mut. Ins. Co.` at a page the
archive gives to `Leto v. Amrex Chemical Co.`; `Bank of Am., N.A. v. Gruff` at
`Bachvarov v. Lawrence Union Free School District`. If a person confirms these,
they stop being review items and become ground truth for a defect class the
benchmark cannot currently express.

**Rows where the convention is undecided.** A filing writes `Gucci America,
768 F.3d 122` — a short form naming one party — where the full case name is
`Gucci America, Inc. v. Bank of China`. This file records what the filing
wrote. Whether the benchmark should record that, or the full name, is a
decision about the annotation and not about any particular row.

## Known problems

- Three locators were not in the request cache when this was built and are
  marked `archive_status: "not cached"`. They are absent from the agreement
  counts above.
- 73 rows resolve to more than one archive record and are excluded from the
  comparison under the "exactly one record" rule. Widening it to "one distinct
  case name" gives 394 comparable, 367 agreeing against the extractor's 356.
- One value is structurally broken: `006:1557` yields `'v. Mo. Pac. R.R. Co .'`,
  from a reproduced case caption where the plaintiff sits on its own line above
  a docket block. It is flagged.
- The 11 `docket` rows are not annotated.
