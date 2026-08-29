# The AI-hallucination miner

A record of what the miner is, what it has produced, and which of its numbers
can be relied on. Written to be audited: every figure below names the file or
command that produces it, and section 8 lists the claims that should be
distrusted first.

Nothing in this note is wired into the validation pipeline.

## 1. What the miner is for

The project needs filings whose citations a court found to be fabricated —
real documents, with a judicial finding attached saying which citations were
invented. That pairing is what makes them usable as ground truth.

The obvious source is a published tracker of AI-fabrication cases. This does
not use one. It builds the corpus from CourtListener's own search instead, so
the corpus is reproducible from a public API and the search is itself the
method. A tracker is then useful for measuring recall, not as the source.

## 2. The pipeline and what each stage yields

| stage | code | output | count |
|---|---|---|---|
| search for orders discussing fabricated citations | `scripts/miner/discover.py` | `local/miner-all.json` | 1,044 hits |
| keep those that are court orders | `scripts/miner/discover.py` | `local/miner-orders.json` | 476 |
| download and read the order text | `scripts/miner/harvest.py` | `local/orders/*.pdf`, `local/miner-parsed.json` | 448 parsed |
| find which entry the order accuses | `scripts/miner/resolve.py` | `accused_entries` field | 79 orders name one |
| rank candidates when no entry is named | `scripts/miner/rank_candidates.py` | `local/miner-widened.json` | 113 |
| look the accused entry up on its docket | ad hoc | `local/miner-accused.json` | 120 entries |
| download the accused filing | ad hoc | `local/accused/*.pdf` | 47 available, 44 on disk |

Coverage of the 47 downloadable filings: 58 distinct cases across 32 courts.

### Why only 47 of 120

RECAP holds only what somebody has already paid PACER for and contributed.
Roughly a third of accused filings were never bought. This is a ceiling on the
method, not a defect in it, and no amount of budget moves it.

## 3. Finding which filing an order accuses

The order that complains is not the filing that contains the fabrications. It
is a different entry on the same docket, and locating it is the part that makes
this a method rather than a search.

`resolve.py` requires a docket reference (`Dkt`, `ECF`, `Doc`, `Docket`) and
accusation language to appear **in the same sentence**. Four traps were found
by reading real orders, and each is guarded against:

1. **The page header.** Every RECAP PDF is stamped `Case 2:25-cv-00689
   Document 47 Filed…` at the top of each page. `Document N` therefore appears
   in 147 of 200 orders and refers to nothing. It is stripped before matching,
   and `Document` is not accepted as a reference form.
2. **Citations to other cases.** Numbers inside a citation to a different case
   look like entry numbers. Guarded.
3. **`document_number` is often null** on the `recap-documents` endpoint. The
   correct source for an entry is `/docket-entries/?docket__id=X&entry_number=N`,
   which returns one entry with nested `recap_documents` carrying
   `is_available` and `filepath_local`.
4. **High entry numbers are not implausible.** An early filter discarded
   entries above 200 as unrealistic. Entry 532 was real, on a criminal docket.
   The filter is removed.

## 4. Verifying the miner picked the right filing

Of the 47 downloaded filings, 24 share at least one citation with the order
that accuses them, and 17 share three or more. Shared citations are evidence
the pairing is correct.

The remainder are not necessarily wrong. Some accused filings contain no
citations at all, which usually means the wrong entry was picked; others are
ambiguous.

## 5. Identifying the specific fabricated citations

Two extraction rules were tried. Both are on record because the first is
attractive and wrong.

**Proximity to accusation language — rejected.** Take citations appearing
within 600 characters of phrases like "does not exist" or "fictitious". This
yields 89 pairs across 13 cases and is dominated by false positives, because
judges discussing hallucination cite the *real* sanctions case law in the same
paragraph. `678 F. Supp. 3d 443` is *Mata v. Avianca*, a genuine case that
appears in five of the flagged cases for exactly this reason.

**Quotation — currently used.** Judges quote fabricated citations because they
are repeating what the lawyer wrote. Taking citations inside quotation marks,
excluding those introduced by `see also`, `citing`, `quoting`, and requiring
the citation to also appear in the accused filing, gives 45 pairs across 6
cases and 31 distinct citations, none repeated between cases. Output:
`local/miner-fakes.json`.

Judges also quote *real* citations they are discussing, so this is a candidate
list, not a finding. Section 6 measures how impure it is.

## 6. Checking citations against the published record, offline

`local/cap/` holds 4.2 GB of Caselaw Access Project data — 2,770 published
reporter volumes. `scripts/miner/caselaw_index.py` reduces these to a page
index of 847,728 cases, each with first page, last page, and name.
`scripts/miner/name_check.py` then asks of any citation: does a case by that
name really begin on that page?

Run both with `PYTHONPATH=. uv run python scripts/miner/name_check.py`.

Verdicts and current measurements over all citations in the accused filings,
with 120 court orders as a control:

| verdict | accused filings | orders (control) |
|---|---|---|
| `volume-not-held` | 549 | 2,458 |
| `name-match` | 340 | 940 |
| `no-name-parsed` | 60 | 63 |
| `pin-cite-ok` | 2 | 2 |
| `PAGE-INSIDE-OTHER-CASE` | 14 | 7 |
| `NAME-MISMATCH` | 10 | 19 |
| `PAGE-ABSENT` | 4 | 6 |
| **flagged / judged** | **28/370 = 7.6%** | **32/974 = 3.3%** |

### Why the control matters

Judges do not fabricate citations, so nearly everything flagged in an order is
a mistake by this check. 3.3% is therefore the false positive floor. Against
7.6% in the accused filings, roughly half of what is flagged there is wrong.

### Why the floor cannot be tuned away

Courts publish the same case under different captions:

- *NAACP v. Button* is published as "National Ass'n for the Advancement of
  Colored People v. Button"
- sealed matters are published as "Under Seal v. United States" while briefs
  cite "In re Grand Jury Subpoena"
- consolidated litigation is published under party names while briefs cite the
  "In re …" caption

All three are correct citations that this check calls mismatches. Resolving
through CourtListener handles the variants and remains the deciding test.

### Two traps in this check

**Coverage must come from files, not citations.** A volume never downloaded
still appears in the data, because opinions cite across reporters. An index
built by scanning citation strings claims coverage it does not have, and every
absent page then reads as a fabrication. An earlier version made this mistake
and reported 10 confirmed fakes when only 2 were supportable. Only a volume
with its own file is held.

**The control is contaminated.** Orders about fabricated citations quote the
fabrications, so a few control flags are real fakes rather than errors. The
true false positive rate is somewhat below 3.3%. `491 F.2d 56` appears in both
lists for this reason.

## 7. What is actually confirmed

Two citations are confirmed fabricated using only offline data, in volumes
that are held and densely covered:

| citation | claimed as | actually at that page |
|---|---|---|
| `491 F.2d 56` | In re Marcus | *United States v. Melton*, pp. 45–58 |
| `597 F.3d 381` | quoted for tortious interference | *Michigan Bell Telephone v. Covad*, pp. 370–392 |

Both point at a page that exists but holds a different case. That is the
signature worth pursuing: a believable volume and page under a name that is not
there.

Of the 31 candidate citations from section 5, the offline check finds 2 fake,
7 real, and cannot judge 22 because their volumes are not held.

## 8. Claims to distrust first

An auditor should attack these in order.

1. **The 7.6% figure is not a fabrication rate.** It is a flag rate against a
   3.3% error floor, on 370 judged citations. The excess is roughly 4%, and the
   sample is small.
2. **`597 F.3d 381` is weaker than `491 F.2d 56`.** Its volume file holds 116
   cases with a largest page gap of 110, so absence is less conclusive. The
   F.2d volume holds 302 cases with a largest gap of 22.
3. **The quotation extractor's error rate is measured on 9 citations** — the
   7 real and 2 fake that could be judged. Nothing about the other 22 is known.
4. **Whether each accused filing is the right filing** is established by shared
   citations for only 24 of 47.
5. **Nothing here has been checked against a published tracker,** so recall is
   unmeasured. The corpus may be badly incomplete in ways the search cannot see.

## 9. Reproducing it

The data under `local/` is git-ignored and not distributed: 4.2 GB of case law,
319 MB of order PDFs, 21 MB of accused filings. An auditor needs the case-law
volumes to rerun section 6, and CourtListener API budget to rerun sections 2
and 3.

Budget is four API tokens, three in the main pool and one reserved, at 125
requests each per day, so about 500 a day. Each token's daily allowance resets
24 hours after that token's own first use, so the windows drift apart rather
than refilling together.
