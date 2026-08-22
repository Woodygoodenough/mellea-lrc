# Extracting the case name, and why the test set cannot measure it

Written 22 August 2026. Everything downstream of the locator depends on knowing
which case a filing named — the fallback search is built from it, and separating
thirty-one cases printed on one Federal Reporter page is impossible without it.
This note measures how often the current extraction gets it, and finds that the
measurement cannot be completed with the test set as it stands.

## 1. What eyecite gives and where it stops

eyecite fills `plaintiff` and `defendant` on a full case citation by reading
backwards from the locator. It works on the ordinary form and stops in four
places, all of which occur in these filings:

- **A table of authorities.** `| Gucci America , 768 F.3d 122 (2 nd Cir. 2014)`
  — the row is a table cell, the party separator is gone, and eyecite returns
  no party at all.
- **A prior-history chain.** `2019 WL ... (D.N.M. Mar. 7, 2019), aff'd, 950 F.3d
  754 (10th Cir. 2020)` — the second locator's name sits before the first
  citation, and eyecite attaches nothing to it.
- **A one-party form.** `In re Marcus, 491 F.2d 56` gives defendant `Marcus`
  and no plaintiff, which is correct as parsing and wrong as a case name.
- **A neighbouring citation.** `806 F.3d 1288` came back as `United States v.
  Hoffman` in a passage about credibility attacks, where the name belongs to a
  different citation nearby. This is the worst of the four, because it is a
  confident wrong name rather than a missing one.

## 2. Measuring it against CourtListener, and what that cannot settle

For every full case citation in the 26 test filings whose locator resolves to
exactly one CourtListener record, the extracted parties were compared with that
record's case name. Both were reduced to word sets with corporate and
procedural words removed, and "agreement" means they share at least one word.

| | count |
|---|---:|
| checkable (locator resolved to one record, record has a name) | 352 |
| the two names share a word | 319 |
| share no word, eyecite gave both parties | 20 |
| share no word, eyecite gave one party | 7 |
| eyecite gave no party | 6 |

The 13 in the last two rows are extraction failures of the kinds in section 1.

**The 20 in the middle row cannot be classified at all**, and that is the
finding. A citation where eyecite produced a full, confident case name that
shares no word with the record at that locator is either:

- a **genuine defect** — the filing named a case that is not at the locator it
  cited, which is exactly what this project exists to detect. `Cornhill LLC v.
  Sowers, 183 A.D.3d 649` sits at a record named `Matter of Goodine v. Evans`;
  `Cadle Co. v. Ayala, 139 A.D.3d 695` sits at `Ramirez v. City of New York`.
- or an **extraction failure** — eyecite borrowed the name from a neighbouring
  citation, as in the `806 F.3d 1288` case above.

Both produce identical evidence: a well-formed name that does not match the
record. Telling them apart requires knowing **what the filing actually wrote**,
independently of what eyecite read. Nothing in the test set records that.

## 3. What the test set annotates

`derived/extraction.jsonl`, 596 rows across 26 filings:

| kind | rows | fields annotated |
|---|---:|---|
| `locator` | 585 | volume, reporter, page |
| `docket` | 11 | docket number, court, court span |

That is the whole schema. **No case name, no pin cite, no year, and no court
for the 585 locator rows.** The set measures whether the pipeline finds the
volume-reporter-page string and nothing else about the citation.

So the 9% figure in section 2 is not an error rate for eyecite. It is a mixture
of an error rate and a defect rate, and the set cannot separate them.

## 4. What annotating the case name would give

One field, and it settles four separate things:

1. **An extraction score for case names**, which does not exist today.
2. **The split in section 2.** With the written name annotated, a mismatch
   against the record is a defect; a mismatch against the annotation is an
   extraction failure. The same 20 citations become two measured populations.
3. **A denominator for the fallback search.** Section 2 of
   `open-ended-search.md` records that the search refuses to run without both
   parties. How often that refusal is the extraction's fault is currently
   unknown.
4. **Disambiguation among table-page candidates.** `candidate-cardinality.md`
   section 4 needs the written case name to separate 31 cases sharing a page,
   and there is no way to evaluate that step without knowing the right answer.

## 5. The same argument for court, pin cite and date

Each is used by the pipeline and none is annotated.

- **Court** is a hard filter on the fallback search, so a court eyecite misreads
  silently removes the citation from the search. Annotated, the cost is
  measurable.
- **Pin cite** is what the pinpoint check is applied to. `pinpoint-design.md`
  counts 339 pinpoint claims across the corpus and 63 that are star pagination,
  but whether the pin cite was *read correctly* has never been measured.
- **Date** is stated by the citation and is the most obvious unused filter. It
  is also the field a fabricated citation is most likely to get wrong, since a
  model picks a plausible reporter series and a plausible year independently.

Annotating all four turns the set from one that scores string-finding into one
that scores citation understanding. No competitor's set does this: the published
ones either score a yes-or-no fabrication verdict, or score locator extraction
in the way this one already does.

## 6. What re-extraction should be given that it is not given now

`field_checks/mellea_case_name_reextraction.py` sees 320 characters before the
locator and 160 after, and nothing else. Two things it could have:

**The retrieved record.** When re-extraction runs after an *ambiguous* lookup
rather than a miss, the candidate case names are already in hand. Showing them
turns an open extraction into a choice among known options, which is a far
easier problem and one a programmatic guard can check exactly. The danger is
obvious and has to be guarded: a model shown `Matter of Goodine v. Evans` may
copy it out instead of reading the filing, which would erase precisely the
defect the project looks for. The existing grounding guard already forbids that
— a party must occur verbatim in the text before the locator — so the record
can be shown as a *list of options to reject*, never as text to copy.

**More than 320 characters, when the structure calls for it.** A table of
authorities row and a prior-history chain both put the name outside that
window. The window is a fixed constant standing in for "the local context",
and page structure is already available from the preprocessing.

## 7. Order of work

1. Annotate the case name as written, for all 585 locator rows. This is the one
   that unblocks the others, and section 2 says 33 citations need reading
   regardless.
2. Re-run the section 2 comparison against the annotation, producing a real
   case-name extraction score and a real case-name defect count.
3. Annotate court, pin cite, and date.
4. Only then decide whether re-extraction needs the retrieved record, because
   the annotation will say how much room there is to improve.
