# How many candidates a lookup returns, and what to do about it

Written 22 August 2026, corrected the same day after the numbers were checked
properly. When a locator lookup returns more than one record, something has to
decide which records are worth evaluating. The rule today is a constant, and it
is being applied to two different problems that need opposite treatment.

**Two claims in the first version of this note were wrong**, and both are
corrected below. The counts were taken from a partial dedup (68 locators rather
than 90), and the conclusion that name variation needs a model does not survive
contact with the data: the decision date settles 80% of it on its own, with no
false merges at all.

## 1. The rule today

`validation/candidate_selection.py`:

```python
CANDIDATE_SELECTION_LIMIT = 3
selected_count = total if total <= CANDIDATE_SELECTION_LIMIT else 0
```

It is not a top-3. **More than three candidates selects zero**, and the whole
branch below is marked deferred. The reasoning is defensible — picking three of
twenty-nine arbitrarily would be worse than declining — but section 4 measures
what it costs, and the answer is most of the right answers.

## 2. What the ambiguous results contain

94 records in the locator probe came back ambiguous, covering **90 distinct
locators**. Every one of them was read back from the cache at no request cost.

| records returned | locators |
|---:|---:|
| 2 | 76 |
| 3 | 2 |
| 4 to 32 | 12 |

## 3. The two-record case is one case recorded twice, and no model is needed

CourtListener holds the same decision more than once — a library import beside
a scraped copy, a panel opinion beside its rehearing, a record whose name field
is empty. **73 of the 76 two-record locators are one case.** Only 3 are two
genuinely different cases sharing a page.

The name variation is real and a string rule does not cover it:

| locator | one record | the other | why a name rule misses it |
|---|---|---|---|
| `828 F.2d 123` | Grasty v. Amalgamated Clothing **&** Text… | …Clothing **And** Textile… | truncated at different lengths |
| `343 F.3d 1143` | Giebeler v. **M & B** Associates | Giebeler v. Associates | dropped party words |
| `398 F.3d 868` | Johnson v. Karnes | Johnson **II** v. Karnes | appeal-stage marker |
| `332 F.3d 654` | Public Citizen, Inc. v. U.S. Dept HHS | Pub Ctzn Inc v. HHS | abbreviation throughout |
| `295 U.S. 602` | Rathbun v. **Unitted** States | Humphrey's v. United States | alternative caption, plus a typo |
| `70 F.3d 736` | Warrick v. General Electric Co. | In Re Warrick | bankruptcy caption |
| `244 F.3d 1152` | Local Joint Executive Board… | *(empty)* | one record has no name at all |

**But the name is not the field to merge on.** The decision date is:

- **61 of 76 pairs share `date_filed`, and reading all 61, every one is the same
  case. No false merges.**
- Ten pairs have an empty name on one side, and eight of those ten agree on
  date — so the date rule covers exactly the cases where a name rule has
  nothing to work with.
- Of the 15 pairs whose dates disagree, 12 are still one case, split because
  CourtListener recorded an opinion and its amendment or rehearing separately
  (`Ultramercial v. Hulu` at 2011-09-15 and 2011-03-18). Loose normalization
  catches all 12 — `Rhode Island`/`RI`, `Pub Ctzn`/`Public Citizen`.
- The 3 real collisions differ in **both** name and date, so nothing merges
  them by accident.

So the first version's conclusion — that this is where a model earns its place
— is wrong. A date comparison does 80% with no errors, and mechanical
normalization does the rest. `docket_id` is equal in 24 of 76 and never equal
for a non-duplicate, so it is a second no-model key with perfect precision and
low recall.

**One thing genuinely cannot be done here.** `court_id` is `None` on every
record, always. The cluster payload from the citation-lookup endpoint has no
court field at all, though `courtlistener/opinion_transport.py` declares one.
Recovering a court costs a second request per candidate, so any rule that wants
to compare courts is not free.

## 4. Deferring the high-cardinality ones loses the answers

For each of the 12 locators over the limit, the case name the filing wrote was
matched against the returned records. **Eleven of the twelve come out right:**

- **5 confirmations.** `515 U.S. 1159` matches `Johnson & Higgins v. Sempier`
  (the certiorari caption reverses the parties); `21 F.3d 1115` matches `Victor
  Reyes v. Pacific Bell`; and three more.
- **6 correct rejections**, every one of which the benchmark independently
  labels `case_name_mismatch`. `554 F.2d 1071`, `788 F.2d 9`, `998 So. 2d 614`
  and three others: the filing's name matches nothing on that page, which is
  the defect.
- **1 false rejection.** `132 L.Ed.2d 854` returns only 4 records for a page
  that carries many more, so the right entry is simply absent and the name
  matches nothing.

The one failure is the opposite of what the limit guards against: not too many
candidates, but too few — a sparsely covered page where absence reads as
mismatch. **That argues for gating on coverage rather than on cardinality.**

## 5. The high-cardinality pages are two different things

They do not shrink when duplicates are collapsed, because they are not
duplicates. They split cleanly, and the decision date separates them:

| kind | example | records | distinct dates | span |
|---|---|---:|---:|---|
| Supreme Court orders list | `562 U.S. 1035` | 32 | 1 | 2010-11-08 |
| Supreme Court orders list | `493 U.S. 1023` | 29 | 1 | 1990-01-08 |
| reporter table of decisions | `554 F.2d 1071` | 32 | 20 | 1977-04-01 to 05-31 |
| reporter table of decisions | `21 F.3d 1115` | 28 | 11 | 1994-03-28 to 04-25 |

An orders list is one Monday's certiorari dispositions, so every record shares
a date. A table of unpublished decisions covers weeks, so the dates spread.
Six of the twelve are each kind, and **the date spread tells them apart without
reading anything**.

Neither is ambiguous by accident: one printed page really does name dozens of
unrelated cases. Only the case name the filing wrote can separate them, and the
current design never brings it to this step.

The rate is **12 of the 600 locators that returned any record, or 2.0%** — and
that is a floor, not an estimate. A table page that CourtListener covers thinly
lands in the two-record bucket and is invisible to this count. `132 L.Ed.2d
854` is exactly that case.

## 6. What should replace the constant

- **Merge on the date before counting.** Sixty-one of the 76 two-record results
  become single-candidate results with no model and no risk, and the limit
  stops binding on them at all.
- **For a page with many candidates, do the opposite of deferring.** Match the
  filing's own case name. Section 4 says that is right 11 times in 12, against
  0 in 12 today.
- **Gate on coverage, not cardinality.** The single failure was a page the
  archive holds thinly. Whether the returned set plausibly covers the page is
  the question worth asking; how many records came back is not.
- **Bound work, not evidence.** Deferring above a threshold discards records
  already paid for with a request. Rank them, evaluate the top few, and record
  plainly that the rest were not examined.

## 7. Still not measured

1. The opinion-search results, which this note has not touched. Search returns
   counts in the hundreds and the same all-or-nothing rule applies to them.
2. How often a thinly covered table page produces a false mismatch. One case is
   known; the rate is not.
3. Whether recovering `court_id` — one extra request per candidate — pays for
   itself anywhere.

## 8. Two things the lookup response carries that nothing reads

Checked against a live cluster payload rather than against our model of it.

**Parallel citations, on every cluster.** `Bell Atlantic Corp. v. Twombly`
comes back carrying eight: `550 U.S. 544`, `127 S. Ct. 1955`, `167 L. Ed. 2d
929`, `2007 U.S. LEXIS 5901` and four more. The field is parsed into
`CourtListenerOpinionCluster.citations` and read in exactly one place —
`pinpoint_retrieval/reporter_page.py`, to pick which citation index a star page
belongs to. Nothing reasons with it.

Three things it would settle:

- **Parallel-citation clashes.** `internal_consistency.py` restricts a clash to
  one reporter series precisely because a case is routinely reported in several
  at once, and 60 of the 62 multiply-cited names across the corpora are
  parallel citations of that kind. A cluster listing them all decides which is
  which directly, rather than by a rule about series.
- **Duplicate merging.** Two records for one page carrying the same parallel
  citation are the same case, whatever their names say. This is a third
  no-model key alongside the date and the docket identifier.
- **Whether a Westlaw citation names a real case.** The clusters for
  `21 F.3d 1115` carry `1994 WL 143951` and `1994 U.S. App. LEXIS 20024`. So
  CourtListener does hold vendor numbers — as parallel citations on a cluster,
  not as something the citation-lookup route resolves. `2016 WL 9137645`
  returns 404 there, from the cache. Since Westlaw and LEXIS are 53% of the
  unresolved bucket (`open-ended-search.md` section 5), a route that reaches
  them at all is worth knowing about. **Untested:** whether the search endpoint
  finds a cluster by its vendor citation. That needs request allowance and is
  the first thing to try when there is some.

**The court, which is not there at all.** `court` and `court_id` are `None` on
every record, and the reason is not a parsing gap: the payload has no court key
among its fifty-odd fields. It carries `docket`, `docket_id`, `judges` and
`panel`, so a court is one further request away. The fields stay declared on
the model, with a comment, because another route may populate them — but
nothing may depend on them, since a rule comparing courts across candidates
from a citation lookup silently never fires.

**One idea this killed.** `precedential_status` looked like a free way to
recognise a table-of-decisions page. It is not: `554 F.2d 1071` returns 32
clusters all marked `Published`, while `21 F.3d 1115` returns 28 all
`Unpublished`. Both are table pages. The date spread in section 5 remains the
signal that works.
