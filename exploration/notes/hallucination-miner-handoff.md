# The hallucination miner

Everything the miner needs, on top of `main` and nothing else. A brief for
whoever runs it next.

## 1. What it is for

The project needs filings whose citations a court found to be fabricated —
real documents with a judicial finding attached saying which citations were
invented. That pairing is what makes them usable as ground truth.

It does not work from a published tracker of AI-fabrication cases. It builds
the corpus from CourtListener's own search, so the corpus is reproducible from
a public API and the search is itself the method. A tracker becomes a way to
measure recall rather than the source.

## 2. What is on this branch

| module | does |
|---|---|
| `discover.py` | searches for orders discussing fabricated citations |
| `harvest.py` | downloads and reads them |
| `resolve.py` | works out which docket entry an order accuses |
| `rank_candidates.py` | ranks candidates when an order names no entry |
| `quoted_citations.py` | takes the fabricated citations from the orders, which quote them |
| `archive_check.py` | checks citations against the printed reporters, offline and free |
| `assess.py` | separates offending filings from court documents and replies |
| `promote.py` | converts a mined filing into the corpus, with provenance and labels |
| `validate.py` | validates promoted filings, waiting out refusals |
| `score.py` | scores each filing against the citations its court named |

`mellea_lrc.caselaw` is carried too — `cap_index` and `case_name_check` only.
`first_page_check` is deliberately left out: it is the one module that reaches
into `extraction.citation_tree` and `validation.duplicate_clusters`, neither of
which is on `main`, and the miner never uses it.

## 3. The data, none of which is in git

Everything lives under `local/`, which is git-ignored and stays that way.

| path | what | how to get it |
|---|---|---|
| `local/orders/` | 452 order PDFs | `harvest.py`, free from RECAP |
| `local/accused/` | 91 accused filing PDFs | free from RECAP, given the manifest |
| `local/cap/` | 3,757 reporter volumes, 5.5 GB | `CapIndex` fetches from `static.case.law` on demand — no key, no rate limit |
| `local/cap-reporters.json` | the archive's own list of its 401 reporters | `static.case.law/ReportersMetadata.json` |
| `local/mined-corpus/` | 77 filings as text, plus `manifest.json` | `promote.py` |
| `local/mined-serialized/` | validated runs, one per document | `validate.py` |
| `local/accused-ocr/` | text recovered from the seven scans | OCR, ad hoc |

**Keep this separate from `data/false-citation-bench/`.** That is a 26-file
annotated bench whose offsets are anchored to its published text. Mined filings
are a different corpus with a different kind of label, and merging them would
invalidate the bench's annotations.

**Add `local/.metadata_never_index`** or Spotlight will index 5.5 GB of case law
that nothing will ever search from Finder.

## 4. The one thing that binds everything

**Four CourtListener tokens, about 500 requests a day, in staggered windows.**
Every other part of the miner is free: the archive, the RECAP PDFs, the
preprocessing, the offline checks. Only the lookups cost.

Two facts about that, both learned expensively:

- **CourtListener throttles on two windows and the 429 bodies look alike.** A
  short one clears in about thirty seconds; a daily one takes hours. Treating
  both as fatal quits about thirty requests in, having spent a fraction of the
  day. Treating both as waitable hangs for hours. `validate.py` waits out the
  short and stops on the long.
- **A refused lookup is not a verdict.** An earlier runner recorded refusals as
  failed nodes and carried on: 833 of 1,769 citations were refused, and the
  runs looked complete. `score.py` therefore reports only documents in which
  every citation was actually checked.

`/health` on the proxy reports what each token has left, which is the only way
to tell the two windows apart from outside.

## 5. Where it stands

- 77 filings promoted, 20 carrying a citation their court confirmed fabricated
- 35 validated; **905 lookups outstanding** to clear the refusals in the rest
- over the 9 documents checked end to end: 101 citations, 30 flagged, and both
  confirmed fabrications present were caught

**Two of two is not a rate.** It is the size of what has been measured cleanly.
Clearing the 905 is what makes a real figure possible, and at 500 a day that is
two days with nothing else competing.

## 6. What to be careful about

**The court's list is a floor, not a labelling.** An order says enough to
justify a sanction — one says "more than three dozen (forty-two to be exact)"
and names a handful. A flag with no court counterpart is not a false positive
by default. One such flag, `Perkins v. Fed. Fruit & Produce Co., 945 F.3d
1242`, was checked by hand and is invented.

**A not-found verdict on a recent reporter is weak evidence in both
directions.** `United States v. Begay, 497 F. Supp. 3d 1025` is real and
CourtListener returns nothing for it. Its coverage of volumes from 2019 onward
is incomplete, and that is the range fabricated citations cluster in. Westlaw
citations resolve nowhere at all.

**A label is a citation together with the name written beside it.**
`539 F. App'x 937` is condemned in one filing as *United States v. Baker* and
cited soundly in another as *Williams v. Morahan*, the case actually printed
there.

**The archive's flag rate does not separate guilty filings from innocent
ones** — 3.7% against 2.5% on court orders, which is inside chance. It produces
specific confirmed citations, not a detector.

`exploration/AUDIT.md` on `experiment/reference-dataset` has the full record,
including the errors worth not repeating.

## 7. Standing constraints

Nothing is committed or pushed to `origin`; work goes to `woody-fork`. No
dataset is pushed anywhere without asking.
