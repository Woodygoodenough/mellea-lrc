# Further improvements

We do not tune for each individual failure. We first collect enough test data
to establish an obvious pattern; only then should we consider a targeted
correction or further prompt engineering.

## Known issues

### Mellea re-extraction corrects corrupted source text

For `16.txt`, the local text contains `Flota Mercante Grancolombiana, $.A.`.
Mellea returns `Flota Mercante Grancolombiana, S.A.`, correcting `$` to `S`.
The grounding rule deliberately rejects this lexical change and the repair
budget is exhausted. This is expected: re-extraction must copy local text,
not repair it.

Character-level correction should be considered explicitly before adding it.
It would change the contract from literal local extraction to source repair.

### Mellea re-extraction expands a legal abbreviation

For `19.txt`, the local citation is `Griffin v. Cnty. of Humboldt`. The
re-extraction prompt already says to copy party text as written and not expand
legal abbreviations, but both repair attempts returned `County of Humboldt`.
The grounding rule rejects that lexical change and the repair budget is
exhausted. This is a legitimate model failure, not a missing-context failure.

Further prompt engineering may be appropriate if this becomes a repeated
pattern across more test data.

### Court-mismatch false positives found auditing unannotated mismatches

While auditing every `mismatch` verdict across the full corpus against the
annotated dataset (not just the 77 known problem citations), 6 citations
showed a case name that matches but a court that doesn't. Two are confirmed
genuine wrong-court citations in the source briefs (verified against
external sources) and were added to the annotated dataset. Three are false
positives on our side, for three distinct reasons:

- `New York v. Shore Realty Corp., 759 F.2d 1032 (2nd Cir. 1985)` in `17.txt`:
  eyecite's own court-abbreviation parsing maps `"(2nd Cir. 1985)"` to court
  code `bap2` (Bankruptcy Appellate Panel, 2nd Cir.) instead of `ca2` (Court
  of Appeals, 2nd Cir.) - confirmed directly with `eyecite.get_citations()`,
  reproducible with or without the stray-space OCR variant ("2 nd Cir."), so
  it isn't our whitespace handling either. `F.2d` is a Court-of-Appeals-only
  reporter, so `bap2` is impossible on its face.

- `Doe v. Skyline Automobiles Inc.` in `3.txt`: the citation's extracted
  court field is garbled OCR junk (a table-of-authorities dot-leader
  string), meaning the citation span landed on a table-of-authorities entry
  rather than the real citing sentence in the body text. Not a real citation
  to evaluate at all.

- `Doe v. George Washington Univ., 369 F. Supp. 3d 49 (D.D.C. 2019)` in
  `3.txt`: our `DocketCourtRetrievalNode` retrieved `cadc` (D.C. Circuit, an
  appellate court) for an `F. Supp. 3d` citation - a reporter series that
  only ever publishes district-court opinions, so `cadc` is impossible here.
  Most likely our docket lookup grabbed a related-but-wrong docket, possibly
  a later appeal of the same underlying case sharing metadata.

A fourth case, `Beery v. Hitachi Home Elecs. (Am.), Inc., 157 F.R.D. 477
(C.D. Cal. 1993)` in `19.txt`, is unresolved: our pipeline retrieved `cand`
(N.D. Cal.) faithfully from CourtListener's own docket record, but the
docket number format (`CV 93-4868 DT (Ex)`, a standard C.D. Cal. convention)
and a 2025 opinion that cites it as `(C.D. Cal. 1993)` both suggest the
brief is actually correct and CourtListener's docket metadata is wrong.
Not confirmed either way - left out of the annotated dataset.

## Future improvements

### Complete parallel opinion-cluster exploration for RECAP candidates

Explore opinion clusters linked from a RECAP candidate's docket as a sibling of
docket-entry exploration. Do not make that low-yield path gate docket documents,
which can surface complementary unpublished material and actionable links.

Before unifying opinion and RECAP search, measure whether every opinion-search
cluster appears in the corresponding docket's `clusters`. Account explicitly
for duplicate PACER and case-law docket records, missing links, and search-index
coverage; the same case may currently resolve to different docket identifiers.

### Refine extracted pinpoint citations

Eyecite's rule-based extraction does not always place a numeric pinpoint in
`pin_cite`: for example, `Twombly, 550 U.S. 544, 570` may retain `570` in
`extra`. This prevents reporter-page retrieval even though the citation has a
usable pinpoint.

After collecting more examples, add a narrowly scoped LLM correction step for
an otherwise valid full case citation. It should recover a numeric pinpoint
from the extracted residual text without changing the reported locator,
parties, court, or year.

### Separate validation decisions from graph operations

Several current `run_*` functions both apply business rules and construct a
validation node. A larger structural refactor could separate pure decisions
from node-producing operations: deterministic field comparisons, candidate
selection, aggregation, locator-outcome classification, and Mellea grounding
would return domain results; operations would provide evidence, invoke external
services where needed, and record the result with node IDs and dependencies.

This should be done as one coordinated refactor across the validation package,
not incrementally. It would touch many call sites and node tests. Do not add a
generic `Operation` base class: the operations intentionally have distinct
inputs and synchronous/asynchronous behavior. The useful boundary is pure
decision logic versus graph operation versus execution progression.

### Preserve frozen upstream extra fields

CourtListener's citation-lookup and search responses expose materially
different endpoint-specific fields despite sharing a few comparable values.
Keep separate endpoint DTOs. At each transport boundary, retain unknown fields
in an immutable, recursively frozen `extra_data` mapping rather than dropping
them with `extra="ignore"`. Promote a field to the named DTO only when a
validation operation needs it; otherwise preserve it as provenance without
prematurely unifying the response shapes.

### Avoid repeated local party re-extraction across candidate branches

When several opinion candidates reach a case-name mismatch, each candidate
currently runs the same citation-local recovery subtree, including Mellea
re-extraction when needed. The local evidence is shared, so this duplicates
work and can produce inconsistent stochastic results.

A convenient improvement is a local re-extraction cache: once a candidate
selection has re-extracted the citation-local parties, later candidate branches
reuse that result without another LLM call. Scope the cache's lifetime to that
one candidate-selection subtree so independent validation runs remain
independent.

### Distinguish genuinely ambiguous evidence occurrences

Fuzzy evidence grounding currently returns the first highest-scoring source
window. If the same or a materially similar passage appears more than once,
the stored span may therefore identify the wrong occurrence.

Do not restore a simple best-versus-second-best score margin: overlapping
windows around one passage are not independent candidates and caused the
correct Iqbal evidence to be rejected. A future implementation should group
overlapping windows into occurrences, then require uniqueness across distinct
occurrences.

### Docket-derived court may disagree with independent sources (Beery)

For `19.txt`, `Beery v. Hitachi Home Elecs. (Am.), Inc., 157 F.R.D. 477
(C.D. Cal. 1993)`: our `DocketCourtRetrievalNode` retrieves `cand` (N.D.
Cal.) from CourtListener's own docket record for this citation, and the
project correctly reports exactly what that record says. But two
independent signals point the other way - the docket number format (`CV
93-4868 DT (Ex)`) is a standard C.D. Cal. convention, and a 2025 opinion
citing this case gives it as `(C.D. Cal. 1993)`. We could not resolve the
disagreement, and did not add it to the annotated dataset either way.

This deserves further exploration rather than being dismissed as noise:
if CourtListener's docket metadata is sometimes wrong independent of any
extraction or matching bug on our side, that's a real, currently-invisible
failure mode for the court check - we would report a confident `mismatch`
against a citation the source brief actually got right. Worth checking
whether this is a one-off data error or a more general pattern (e.g.
particular districts, particular eras of docket, or dockets attached to
cases that were later appealed) before deciding whether the court check
needs a corroborating cross-check against a second source.

### Pinpoint check grants support to compound propositions on partial grounding

For `26.txt`, the extracted proposition is "Constructive trust and unjust
enrichment are unavailable where an express contract governs." The retrieved
reporter page grounds the unjust-enrichment half at length but never mentions
constructive trust. The pinpoint check still returned `supports`, reasoning
from the grounded half to the whole compound claim.

Do not patch this one example directly - a targeted instruction fix would not
generalize, since compound propositions (two or more joined legal claims,
"X and Y", "X because Y", stacked holdings) are common and the failure mode is
structural: the check evaluates the compound claim as a single unit instead of
verifying each component claim has its own grounding. A systematic fix needs
either sharper instruction-level decomposition (require the check to identify
and separately verify each distinct claim before returning an aggregate
verdict) or a wired-in domain model of legal-claim structure that can split a
compound proposition before grounding is attempted. Collect more compound-
proposition examples before choosing between these.
