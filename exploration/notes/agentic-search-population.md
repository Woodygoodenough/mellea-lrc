# What a search loop would have to work on

Three free moves settle almost every ambiguous locator, and nine citations in
659 are left over. This note is the count behind that, and behind section 1 of
`agentic-search-handoff.md`. Written 1 September 2026.

Two buckets are in question. A locator is **unresolved** when CourtListener
holds no case at the cited volume, reporter and page; it is **ambiguous** when
CourtListener returns more than one record there and something has to decide
which one the filing meant.

## 1. Where the numbers come from

Two measurements over the same corpus, the 390-excerpt LePhantomCite evaluation
split.

`evaluations/agentic_search/search_population.py` reads a locator probe's saved
output and counts what the probe concluded. It sends no requests. The probe is
`evaluations/lephantomcite/locator_probe.py` on
`experiment/general-explorations`, run on 31 August 2026 over 1,334 case
citations; its output is a run artifact rather than a tracked file.

`evaluations/agentic_search/ambiguous_candidates.py` extracts every full case
citation itself, looks each distinct locator up once, and measures what
separates the ambiguous ones. Its 659 locators are the 1,334 citations
deduplicated to distinct volume-reporter-page triples. **Every one of its 659
lookups was served from the proxy's cache, so the run spent no request
allowance**, and it stops on its own if uncached responses exceed a budget.

Two limits apply to every label count below.

**The corpus is defect-injected.** A label distribution over LePhantomCite
describes how the benchmark was generated as much as it describes filings.
Section 7.1 of `caselaw-archive.md` works through a case where that distinction
changed the reading of a result. Section 5.2 below is a place where the labels
are demonstrably wrong.

**The probe stores each citation's locator span, not the citation as written.**
A court parenthetical survives only where eyecite's span happened to include it,
so the probe cannot measure how many citations carry a court.

## 2. The unresolved bucket is 97% sound citations

| locator outcome | count | share |
|---|---:|---:|
| resolved | 746 | 55.9% |
| short form, whose page is a pin cite | 331 | 24.8% |
| ambiguous | 120 | 9.0% |
| unresolved | 94 | 7.0% |
| refuted, an impossible reporter series | 31 | 2.3% |
| out of scope | 12 | 0.9% |

Of the 94 unresolved, **91 are labelled `sound` and 3 are labelled
`case_name_mismatch`**. The citation is correct and CourtListener does not hold
the record.

Resolving that bucket by search would confirm 91 citations that nothing was
wrong with, and could reach at most 3 defects. It is a coverage improvement, not
a detection one.

## 3. Most of the bucket is unreachable by search anyway

| what the unresolved locator is | count | share |
|---|---:|---:|
| a Westlaw or LEXIS record | 70 | 74.5% |
| a statute, regulation or agency document | 9 | 9.6% |
| a printed reporter a name search could reach | **15** | **16.0%** |

Section 11 of `open-ended-search.md` established that CourtListener's search
endpoint returns nothing for a vendor number even where its citation-lookup
endpoint holds the cluster, because the two endpoints are backed by different
corpora. The 70 are closed to search for that reason and not for want of a
better query. The 9 name Oklahoma Statutes, FERC orders, the Massachusetts Code
of Regulations and an Office of Legal Counsel opinion, which `reporters-db` maps
to case reporters; section 5 of `open-ended-search.md` identifies each.

**Fifteen citations remain.** A loop that reformulates against a miss is a loop
built for fifteen citations in 1,334, of which the labels say at most three
carry a defect.

Section 9 of `open-ended-search.md` estimated 25 reaching the search, 19 of them
Westlaw and 3 LEXIS. That count and this one measure different things — it
counted citations passing the preconditions, this counts citations a search
could act on — and this one is the tighter bound.

## 4. Three free moves settle 85 of the 94 ambiguous locators

Measured directly against the archive, over 659 distinct locators:

| what the lookup returned | count |
|---|---:|
| one record, so nothing has to choose | 486 |
| no record, which is the search route's population | 79 |
| **more than one record** | **94** |

Each move below runs on records already in hand and costs no request.

| move | locators it settles | left |
|---|---:|---:|
| merging records that are one decision held more than once | 84 | 10 |
| picking the records carrying the case name the filing wrote | 1 | **9** |
| comparing the court and year the filing states | **0** | 9 |

**Merging does nearly all of it.** 74 of the 94 are a single decision the archive
holds several times, and 84 come within `CANDIDATE_SELECTION_LIMIT` once merged.
`validation/duplicate_clusters.py` merges on the decision date.

**The court comparison never fires here, and that is structural.** 0 of the 508
records returned by the citation-lookup endpoint carry a court identifier; the
payload has no court field, which is why `validation/court_retrieval` fetches
the docket to get one, a request per candidate. All 508 carry a decision date.

**The year separates none of the remaining 9**, because each is a page of
decisions from one court in one year. `search/narrowing.py` was written for this
move and, on this route, contributes nothing. Section 6 says what follows.

## 5. The nine that are left are all crowded pages

Each of the nine returns between 7 and 32 records, and the case name the filing
wrote matches none of them. These are tables of decisions: the reporter prints
unpublished dispositions many to a page, alphabetically.

| citation | records | what the filing wrote | what the page holds |
|---|---:|---|---|
| 688 F.2d 816 | 25 | Sprague v. General Motors Corp. | Kulwiec, Langone, Leach, Malvasio, Marshall, Martin |
| 720 F.2d 679 | 27 | Charles v. Orange County | Hunter, Illsley, Jackman, Jones, Khan, Krause |
| 44 So. 3d 587 | 7 | Conley v. Gibson | Galeana, Galura, Gest, Gillins, Grady, Griner, Haynes |
| 986 F.2d 1418 | 27 | Waterhouse v. District of Columbia | Boulevard Bank, Carr, Cater, Cigna, Cooper, Fagan |
| 607 F.2d 1001 | 19 | All, Inc. v. Casa Marina Owner, LLC | Alford, Allen, Baltimore County, Behrens, Brackett |
| 554 F.2d 1071 | 32 | United States v. Dávila-González | 32 other `United States v.` entries |
| 998 So. 2d 614 | 20 | (no plaintiff) v. Ford Motor Co. | DeWitt, Diaz-Gonzalez, Dovil, Dubeck, Dumenigo |
| 788 F.2d 9 | 27 | (parties damaged) In re Slimick | Acker, Aguilar, Baez-Gomez, Berman, Bishop, Davis |
| 622 F.2d 589 | 9 | (no parties recovered) | West, Willey, Williams, Wilson, Wimmer, Young |

They divide in two.

**Six state a name the page does not carry.** For five of those six the name
sorts outside the alphabetical range the page covers — Sprague against a page
running K to M, Charles against H to K, Conley against G to H. For
`607 F.2d 1001` the name sorts *inside* the range: the page runs Alford, Allen,
Baltimore, and there is no `All, Inc.` between Alford and Allen.

**Three never had a name to compare.** `622 F.2d 589` yields no parties at all,
`998 So. 2d 614` an empty plaintiff, and `788 F.2d 9` a damaged one — eyecite
reads `(In re Slimick), 788 F.2d 9` and recovers `In Slimick)`. Those are
extraction failures, and the fix for them is in extraction rather than in
search.

### 5.1 A page-name comparison does not need a search

Section 6's conclusion turns on this. The first six of the nine are not waiting
on a query: the evidence needed to say something about them is already in the
lookup response. What is missing is not a request, it is a rule for what an
absence on a crowded page may be taken to mean.

`validation/duplicate_clusters.py` deliberately declines to say anything there,
and its reason is correct as far as it goes: nothing matching does not
distinguish a filing naming a case that is not on the page from an archive
holding only part of the page. A table of decisions is alphabetical, so the
records the archive does hold bound the page, and a name sorting outside those
bounds cannot be on it. That is a claim worth testing and this note does not
make it — see section 7.

### 5.2 Every one of the nine is labelled `sound`, and several are not

`Conley v. Gibson` is a 1957 Supreme Court case at 355 U.S. 41, written here as
a 2010 Florida District Court of Appeal case. `Charles v. Orange County` is a
Second Circuit case, written as Sixth Circuit 1983. `622 F.2d 589` is paired
with `132 L.Ed.2d 854 (1995)`, and volume 622 of F.2d is 1980.

The corpus labels all nine `sound`. That is the reverse of the concern in
section 7.1 of `caselaw-archive.md` — there the worry was that a check was
detecting the injector, and here the labels are missing defects the check finds.
Both have the same consequence: **a precision or recall figure against this
corpus does not measure what it appears to.** Nine citations read by hand is the
evidence for this paragraph, and it is not a rate.

## 6. What the loop is left with

**No move in this note needed a search.** Merging, the case-name match, and the
comparison in section 5.1 all run on records the lookup already returned. After
them the ambiguous route has nine citations left, and section 5 says six of
those are decidable from the same records and three are extraction failures.

So the ambiguous route does not justify a loop either. It justifies one more
free rule and a fix in extraction.

That leaves the loop's case resting on the **79 locators the lookup found
nothing for** — the search route — and on what a search returns when it runs.
Two things about that route are known and neither has been measured here:

- `validation/candidate_selection.py` applies the same limit to search results,
  and a search result set has no records to merge, so a query returning 111
  results is deferred whole. `caseName:("Pacific Bell")` returned exactly that
  in section 11 of `open-ended-search.md`.
- Search results **do** carry `court_id` and `dateFiled`, so
  `search/narrowing.py` has all three comparisons available there, where on the
  locator route it has one.

Measuring that costs request allowance, because a search is not cacheable.

## 7. What is unmeasured, and what it would cost

1. **Whether an alphabetical bound on a table page is sound.** Section 5.1.
   Free: it reads records already cached. It needs a rule for establishing that
   the archive holds enough of a page to bound it, and it asserts an absence,
   which is the thing this project is most careful about.
2. **Whether narrowing separates search results.** Section 6. Costs one search
   per citation, against a budget of roughly 500 requests a day.
3. **What the ambiguous bucket looks like in real filings.** Every count here is
   from a defect-injected corpus whose labels section 5.2 shows to be wrong on
   the citations that matter most. Section 8 of `caselaw-archive.md` found a
   check with 61% label agreement here fired zero times on 135 real filings.
4. **The three extraction failures in section 5.** `(In re Slimick), 788 F.2d 9`
   losing its parties to a parenthetical is a defect in extraction, not in
   search, and belongs to that track.

Items 1, 3 and 4 cost no requests.

## 8. A defect in the cherry-picked name comparison

`name_words` in `validation/duplicate_clusters.py` strips every character
outside `[a-z0-9 ]`, so `Dávila-González` becomes the words `vila`, `gonz` and
`lez` rather than one name. It does not change the outcome for `554 F.2d 1071`,
where no record carries that party under any spelling, but it will silently fail
to match any accented party name. The file is the primary track's work, brought
onto this branch unchanged, so the fix belongs with them.
