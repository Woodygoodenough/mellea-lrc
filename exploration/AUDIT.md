# State of the work, for an auditor

One document covering what exists, what it rests on, and what should be checked
first. Written for an agent with no prior context on this repository.

Every number names the file or command that produces it. Section 12 lists the
claims most likely to be wrong.

---

## 1. What the project is

`mellea-lrc` checks whether the citations in a legal filing hold up. It reads a
document, finds every citation, and asks whether the authority each one names
exists and matches how the filing cites it — case name, court, year, and the
proposition a pinpoint is offered for.

Three layers run in order, each consuming the last:

| layer | input | output |
|---|---|---|
| preprocessing | PDF or DOCX via Docling, or plain text | `PreprocessedDocument` |
| extraction | preprocessed text | `ExtractedDocument` |
| validation | extracted citations | `ValidatedDocument` |

Extraction is deterministic and offline. Only validation needs a CourtListener
key and a model endpoint. Every citation keeps a character span into the
preprocessed text, and each validation step is a node in a tree, so a verdict
traces back to the characters that produced it.

`ValidatedDocument` holding `citation_validation: list[ValidationNode]` replaced
an earlier nested chain of five document types (`PreprocessedDocument` →
`ExtractedDocument` → `InferredDocument` → `RetrievedDocument` →
`AssessedDocument`). That refactor is done and is not under review here.

## 2. Where things live

| path | what |
|---|---|
| `src/mellea_lrc/core/` | documents, spans, citations, `reporter_series.py` |
| `src/mellea_lrc/caselaw/` | offline checks against the printed reporters |
| `src/mellea_lrc/courtlistener/` | API client, one module per endpoint |
| `src/mellea_lrc/statutes/` | statute citation work; **imported by nothing** |
| `src/mellea_lrc/experimental/` | page crops, layout review, relaxed extractor |
| `evaluations/lephantomcite/` | the reference dataset harness |
| `evaluations/validation/`, `evaluations/extraction/` | scoring harnesses |
| `scripts/miner/` | the hallucination miner |
| `scripts/modal/courtlistener/` | the caching proxy deployed on Modal |
| `exploration/notes/` | 17 notes, one per direction investigated |
| `local/` | all data; **git-ignored, never distributed** |
| `tests/` | 59 test files |

Branch is `experiment/lephantomcite`. Two remotes: `origin`
(`gt-csse/mellea-lrc`, the primary repo) and `woody-fork`
(`Woodygoodenough/mellea-lrc`).

**Standing constraint: nothing is committed or pushed to `origin`.** All work
goes to `woody-fork`. No dataset is ever pushed anywhere.

## 3. The four data stores

Total 4.5 GB under `local/`, all git-ignored.

### 3.1 Our own annotated set — under 1 MB
`local/test_data/`, 27 documents, plus `local/annotations/` and two masked
variants (`test_data_locator_masked`, `test_data_full_span_masked`) used for
ablations. This is what the validation runs score against.

### 3.2 The reference dataset — lephantomcite
Harness in `evaluations/lephantomcite/`. The latest locator probe
(`local/locator-probe.json`) covers roughly 1,300 citation instances:

| label | count |
|---|---|
| resolved | 746 |
| short form | 331 |
| ambiguous | 120 |
| unresolved | 94 |
| refuted | 31 |
| out of scope | 12 |

**A caution that governs how this dataset may be used.** Its own README
documents one field, `hallucinations`, mapping *hallucinated text span → type*.
The keys are spans, not citations. For `content_misrepresentation` (131 spans)
and `misquote` (46 spans) — roughly half the eval spans — the labelled unit is
a passage, and the citation is only the pointer used to check it. A checker
whose unit is the citation cannot locate those defects at all. See
`exploration/notes/directions-measured-24aug.md` §1.

Two further traps in the same file: `optional` appears 22 times in eval and
never in train, and is in neither the README taxonomy nor its count table. And
the file carries both `list_hallucinations` and `list_hallucination_types`,
whose keys differ in 183 of 390 eval rows — only the first matches the
published counts. Any figure must name which field it used.

### 3.3 Caselaw Access Project — 4.2 GB
`local/cap/`, 2,770 published reporter volumes as JSON, one file per volume,
named `{reporter-slug}-{volume}.json`. This is Harvard's digitisation of the
printed reporters, fetched from `static.case.law` — no key, no rate limit.

This is not a dataset of citations to check. It is the answer key. It is also
the cache directory for `mellea_lrc.caselaw.CapIndex`, which fetches volumes on
demand and reads them back from here.

### 3.4 Miner exploration — 340 MB
`local/orders/` (452 order PDFs), `local/accused/` (44 accused filing PDFs),
and the derived JSON described in section 8.

### 3.5 Not on disk
An R2 read-through cache behind a Modal proxy holds CourtListener responses.
Cache key is `sha256("METHOD|endpoint|urlencoded-params|urlencoded-data")` with
params sorted. Do not change that function; every stored object depends on it.

## 4. CourtListener access and its limits

Four API tokens: three in the main pool, one reserved, reached with the header
`x-cl-pool: reserved`. Each allows 125 requests a day, so about **500 a day
total**.

**Each token's allowance resets 24 hours after that token's own first use**, so
the windows drift apart and refill at different times rather than together. A
`launchd` job (`scripts/courtlistener/com.mellea-lrc.cache-fill.plist`) runs
four times daily at 05:10, 11:10, 17:10 and 23:10 to meet them.

Four endpoint facts that shape everything:

- `lookup_citation` and `get_opinion` are cached and warmed.
- `get_docket` is cached but **not** fully warmed — see section 5.
- `search` is not reliably cacheable, because the query is model-generated.
- RECAP PDFs are **free**: `https://storage.courtlistener.com/{filepath}` needs
  no token and counts against no allowance.

Two operational traps, both hit and fixed:

- **Pagination `next` URLs point at `courtlistener.com` directly**, bypassing
  the proxy. They must be rewritten to the proxy base or the request silently
  misses the cache and the allowance.
- **Probing whether allowance remains requires a guaranteed-uncached request.**
  A cached request returns 200 and tells you nothing. This mistake was made more
  than once.

Jobs now try the main pool and fall back to reserved before giving up, so
allowance is not stranded in one pool while a job blocks on the other. Moving
tokens between pools would not raise the ceiling; four tokens is 500 a day
however they are grouped.

## 5. Warming state

| corpus | endpoint | state |
|---|---|---|
| opinions for the reference dataset | `get_opinion` | **1,068 of 1,068 — complete** |
| citation lookups | `lookup_citation` | complete |
| dockets for the reference dataset | `get_docket` | **at least 291 of 633** |

The docket figure is a floor, not a measurement. The warming walk stops when
allowance runs out, and the last run confirmed 291 cached before stopping
(`local/docket-warm.log`). Nothing is known about the remaining 342.

Opinion warming was completed only after four defects were fixed, each hidden
by the previous one: it was given leftover allowance rather than main-pool
priority; a throttled token idled the whole pool because the burst branch slept
before rotating; long refusals were misclassified as bursts and retried
forever; and the schedule met the token windows only by luck.

## 6. The validation pipeline

Not under active change. `evaluations/validation/` and `evaluations/extraction/`
hold the scoring harnesses. `local/` carries console and progress logs from
runs across 8B and 30B models, with and without repair, and ablations.

`src/mellea_lrc/llm/ivr.py` holds the instruct–validate–repair loop.

## 7. What has been built this cycle

### 7.1 The reporter-series rule — merged
`src/mellea_lrc/core/reporter_series.py`. `find_impossible_series(text)` reports
a citation naming a series a real reporter family never published — `531
N.E.4th 224`, where the North Eastern Reporter stops at `N.E.3d`.

It exists because **eyecite does not report these at all.** Its patterns come
from the same reporter database, so a citation naming a series outside it
matches nothing and is returned as no citation rather than a bad one. Every
later stage therefore never sees it.

Design constraints worth checking: it only reports an impossible series *of a
family that exists*; `_normalise` strips whitespace, periods and case; and
variations inherit the canonical family's series set.

This rule replaced `names_no_real_reporter` in
`evaluations/lephantomcite/locator_probe.py`, which was deleted. `"fr"` was
added to `NON_CASE_SOURCES` so the Federal Register stops being refuted.

### 7.2 The offline caselaw checks — pre-existing, now used by the miner
`src/mellea_lrc/caselaw/` holds three modules that matter:

- `cap_index.py` — page outcomes for a cited volume and page. Its five outcomes
  are deliberately not two: `STARTS_A_CASE`, `INSIDE_A_CASE`,
  `NO_CASE_COVERS_IT`, `VOLUME_UNAVAILABLE`, `AMBIGUOUS_PAGE`.
- `case_name_check.py` — a name comparison with **three** verdicts, so that an
  abbreviation is not read as a disagreement.
- `first_page_check.py` — reports a wrong first page without firing on short
  forms written without `at`.

Two rules from these modules govern any use of them:

- **A page the archive does not cover is not evidence of fabrication.** The
  archive is one digitisation with an end date. Empirically 46% of citations
  landing in a gap carry a defect label against a 10% base rate, which is a
  reason to look and not a licence to report.
- **When several cases begin on the same page, any of them may be the one
  meant.** Picking one arbitrarily is how a correct citation gets contradicted.

## 8. The hallucination miner

### 8.1 What it is for
The project needs filings whose citations a court found fabricated — real
documents with a judicial finding saying which citations were invented.

It does not work from a published tracker. It builds the corpus from
CourtListener's own search, so the corpus is reproducible from a public API and
the search is the method. A tracker becomes a way to measure recall.

### 8.2 The pipeline

| stage | code | output | count |
|---|---|---|---|
| search for orders about fabricated citations | `scripts/miner/discover.py` | `local/miner-all.json` | 1,044 |
| keep court orders | `scripts/miner/discover.py` | `local/miner-orders.json` | 476 |
| download and read | `scripts/miner/harvest.py` | `local/orders/*.pdf`, `miner-parsed.json` | 448 parsed |
| find the accused entry | `scripts/miner/resolve.py` | `accused_entries` | 79 orders name one |
| rank candidates when none is named | `scripts/miner/rank_candidates.py` | `miner-widened.json` | 113 |
| look the entry up on its docket | ad hoc | `miner-accused.json` | 120 entries |
| download the accused filing | ad hoc | `local/accused/*.pdf` | 47 available, 44 on disk |

Coverage of the 47: 58 cases across 32 courts.

**Only 47 of 120 are obtainable.** RECAP holds only what somebody already paid
PACER for and contributed. About a third were never bought. This is a ceiling
on the method, and no budget moves it.

### 8.3 Locating the accused filing
The order that complains is not the filing that offends; it is a different
entry on the same docket. `resolve.py` requires a docket reference (`Dkt`,
`ECF`, `Doc`, `Docket`) and accusation language **in the same sentence**.

Four traps, each found by reading real orders and each now guarded:

1. **The page stamp.** Every RECAP PDF carries `Case 2:25-cv-00689 Document 47
   Filed…` on each page. `Document N` therefore appears in 147 of 200 orders
   and refers to nothing. It is stripped, and `Document` is not accepted as a
   reference form.
2. **Citations to other cases** contain numbers that look like entry numbers.
3. **`document_number` is often null** on `recap-documents`. The correct source
   is `/docket-entries/?docket__id=X&entry_number=N`, which returns one entry
   with nested `recap_documents` carrying `is_available` and `filepath_local`.
4. **High entry numbers are not implausible.** A filter discarding entries above
   200 was wrong; entry 532 was real on a criminal docket. Removed.

### 8.4 Confirming the pairing
Of the 47 downloaded filings, 24 share at least one citation with the order
accusing them, and 17 share three or more. The rest are not necessarily wrong —
9 contain no citations at all, which usually means the wrong entry was picked,
and 13 are ambiguous. **This is an open question, not a settled one.**

### 8.5 Identifying the fabricated citations
Two extraction rules were tried.

**Proximity to accusation language — rejected.** Citations within 600
characters of "does not exist", "fictitious" and similar. Yields 89 pairs
across 13 cases and is dominated by false positives, because judges discussing
hallucination cite the *real* sanctions case law in the same paragraph. `678 F.
Supp. 3d 443` is *Mata v. Avianca*, a genuine case, and it appears in five of
the flagged cases for exactly this reason.

**Quotation — currently used.** Judges quote fabricated citations because they
are repeating what the lawyer wrote. Citations inside quotation marks,
excluding those introduced by `see also` / `citing` / `quoting`, and required
to appear in the accused filing too. Yields 45 pairs across 6 cases, 31
distinct citations, none repeated between cases. Output `local/miner-fakes.json`.

Judges also quote *real* citations they are discussing, so this is a candidate
list, not a finding.

### 8.6 Checking against the printed record
`scripts/miner/archive_check.py`, built on `mellea_lrc.caselaw`. Run:

```
PYTHONPATH=src uv run python scripts/miner/archive_check.py
```

Two outcomes carry evidence — the page sits **inside** a different case, or a
case begins there under a name that **contradicts** what was written. Court
orders are the control, since judges write their own citations.

| | accused filings | orders (control) |
|---|---|---|
| judged citations | 377 | 990 |
| flagged | 17 | 22 |
| **rate** | **4.5%** | **2.2%** |

**The 2.2% is the false positive floor, and 4.5% is not a fabrication rate.**
Roughly half of what is flagged in the accused filings is expected to be wrong.

The residual floor is caused by the source documents and the text extraction,
not by the rule:

- typos judges made — `Untied States`, and *Chevron* cited as `National
  Resources Defense Counsel` for `Natural Resources Defense Council`
- real-world abbreviations no prefix rule reaches — `MetLife` for
  `Metropolitan Life Insurance`
- layout bleed, now trimmed: party names are read backwards from the citation,
  so a page stamp or the previous line runs into them

### 8.7 What is actually confirmed
Two citations, using only offline data, in volumes that are held and densely
covered:

| citation | written as | printed at that page |
|---|---|---|
| `491 F.2d 56` | In re Marcus | *United States v. Melton*, pp. 45–58 |
| `597 F.3d 381` | quoted for tortious interference | *Michigan Bell Telephone v. Covad*, pp. 370–392 |

Both name a page that exists but holds a different case. That is the signature
worth pursuing.

## 9. Errors made and corrected, kept on the record

These are here because each is easy to repeat.

1. **A second reporter index was built that duplicated
   `mellea_lrc.caselaw`, worse.** Both are deleted. Before adding an offline
   check, look in `src/mellea_lrc/caselaw/` first.
2. **Coverage was counted from citation strings rather than downloaded files.**
   A volume never downloaded still appears in the data, because opinions cite
   across reporters. The index then claimed coverage it lacked and every absent
   page read as fabrication. This produced a reported 10 confirmed fakes when
   only 2 were supportable.
3. **The control is contaminated.** Orders about fabricated citations quote the
   fabrications, so a few control flags are real fakes rather than errors, and
   the true floor is a little below 2.2%. `491 F.2d 56` appears in both lists.
4. **A claim that the allowance was smaller than assumed was wrong.** Measured
   usage matches four tokens at 125 a day. The pool delivers its allowance; the
   workload simply exceeds it.
5. **`Document N` was nearly accepted as a docket reference form.** It is the
   page header.

## 10. Open decisions, unanswered

1. **How to spend remaining allowance** — finishing the docket cache (342 left)
   against fetching the 253 queued candidate filings from the widened reader.
   Together about 581 requests, a bit over one day at full allowance.
2. **What to do with the 9 accused filings containing no citations** (likely
   wrong entry picked) and the 13 with no shared citations (ambiguous).
3. **Whether findings attach to citations or to spans.** Half the reference
   dataset's labels are prose spans. This decides the shape of the output and
   wants settling before anything is merged.

## 11. Conventions in force

- Nothing is committed or pushed to `origin`. Code goes to `woody-fork` only.
- No dataset is pushed anywhere. `local/` is git-ignored in full.
- Commits are sole-authored, with no co-author trailer.
- Documentation describes the current state, not a history of changes. The
  exception is a recorded error whose repeat is likely, as in section 9.
- Nothing in `exploration/` is wired into the pipeline. Merging order is to be
  argued from measurements, starting the week of 31 August 2026.

## 12. What to attack first

In order of how likely each is to be wrong.

1. **4.5% is not a fabrication rate.** It is a flag rate above a 2.2% floor, on
   377 judged citations. The excess is about 2 points and the sample is small.
2. **`597 F.3d 381` is weaker than `491 F.2d 56`.** Its volume file holds 116
   cases with a largest page gap of 110, so absence is less conclusive. The F.2d
   volume holds 302 cases with a largest gap of 22.
3. **The quotation extractor's error rate rests on 9 citations** — the 7 real
   and 2 fake that could be judged. Nothing is known about the other 22.
4. **Only 24 of 47 pairings are corroborated** by shared citations.
5. **Recall is entirely unmeasured.** Nothing has been checked against a
   published tracker, so the corpus may be badly incomplete in ways the search
   cannot see.
6. **The docket cache figure of 291 is a floor from a truncated walk**, not a
   count of what the bucket holds.

## 13. Reproducing any of it

`local/` is not distributed. An auditor needs:

- the CAP volumes for section 8.6 — fetched by `mellea_lrc.caselaw.CapIndex`
  from `static.case.law`, needing no key
- CourtListener allowance for sections 5, 8.2 and 8.3
- `pdftotext` from poppler, used for all PDF text

Commands:

```
PYTHONPATH=src uv run python scripts/miner/archive_check.py
uv run --env-file .env python evaluations/lephantomcite/run_locator_probe.py
uv run pytest
```
