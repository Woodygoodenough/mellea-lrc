# Checking statute citations

> **Scope.** This is domain learning, not a component. Nothing in the citation
> pipeline imports any of it, and nothing should until the questions in
> section 0 are answered. The project is case citations; statutes are being
> read about, not built on.

## 0. What has to be understood before any of this is wired in

None of these is answered yet, and each one changes what a statute checker
would even be:

- **How a provision is represented.** A section is not a stable object. It is
  amended, renumbered, transferred between titles, and split. Two citations to
  "the same" provision years apart may not name the same text.
- **Which jurisdictions, in what order.** Federal first is obvious. After that
  the ordering question is real: the corpora cite New York, California and
  Indiana, each with its own code structure, its own abbreviations, and its
  own publication arrangements.
- **What counts as a defect.** A repealed section cited for history is correct
  practice. A transferred section cited under its old title is arguably
  correct at the date the brief was written. Neither is a fabrication.

Until those are settled, wiring statute handling into the extractor would
entangle the citation results with a question nobody has answered.

Written 22 August 2026. The project checks case citations and ignores statutes
entirely. This is a measurement of what that leaves out and what checking it
would involve.

## 1. How much is being skipped

| corpus | case citations | statute citations | statutes as a share |
|---|---:|---:|---:|
| 26 test filings | 583 | 114 | 16% |
| 109 sampled filings | 1,429 | 590 | 29% |

Between a sixth and a third of every citation in a filing is a statute, and
none of them is looked at. A report that says a filing's citations were checked
is, at present, describing three quarters of them.

## 2. Nine tenths of them are federal, and parse cleanly

Across both corpora, 704 statute citations:

| | count | share |
|---|---:|---:|
| federal, code named by the parse (`U.S.C.`, `C.F.R.`, `Stat.`, `Pub. L.`) | 642 | 91% |
| state or other | 62 | 9% |

eyecite gives a federal citation full structure. `28 U.S.C. § 636(b)(1)(A)`
becomes title 28, section 636, subsection (b)(1)(A) — enough to address a
specific provision without any further parsing.

Both federal sources are free and complete:

- The **United States Code** is published as bulk XML by the Office of the Law
  Revision Counsel, with each section carrying its own amendment history.
- The **Code of Federal Regulations** has a public API through eCFR, including
  historical versions by date.

So a checker covering 91% of statute citations needs no commercial licence and
no per-jurisdiction work.

## 3. The state problem is real, and smaller than expected

The remaining 9% is where the parse stops being enough. Every New York
citation in these corpora reduces to reporter `N.Y.`, and the code itself
survives only in the raw text:

| as written | what the parse yields |
|---|---|
| `N.Y. C.P.L.R. § 308` ×14 | `N.Y.` § 308 |
| `N.Y. Executive Law § 292` ×3 | `N.Y.` § 292 |
| `N.Y. Exec. Law § 296` ×3 | `N.Y.` § 296 |
| `N.Y. Judiciary Law § 750` ×2 | `N.Y.` § 750 |
| `N.Y. Civil Rights Law § 41` ×2 | `N.Y.` § 41 |

Five different bodies of law, one reporter value. New York has around ninety
consolidated laws, each with its own section numbering, so `N.Y. § 308` does
not identify a provision — CPLR § 308 is service of process, and a Judiciary
Law § 308 would be something else entirely. The abbreviations are not
consistent either: `Executive Law` and `Exec. Law` appear in the same corpus.

This is 29 citations out of 704, so it is a real gap and not the main one. The
sensible order is federal first.

## 4. What can be checked that has no equivalent for cases

Three of these are specific to statutes and none is a matter of judgement.

**Does the provision exist?** A cited section is either in the code or it is
not. This is the same kind of positive claim as a reporter series that does not
exist, and it is settled by lookup rather than by search.

**Is it still in force?** Statutes are repealed and amended in a way that
opinions are not. A citation to a repealed section is a defect that has no
analogue in case citation — the nearest equivalent, an overruled case, needs a
citator and a judgement, while a repeal is recorded as a fact in the code
itself.

**Does the version match the date?** A brief filed in 2026 citing a section as
it read before a 2019 amendment may be quoting text that is no longer law. The
Code's amendment notes make this checkable. Nothing similar exists for cases,
whose text does not change.

The fourth question — does the provision say what the filing claims — is the
same semantic problem as for cases, with the same boundary as
`pinpoint-design.md` sets out.

## 5. Why this is not simply more of the same work

Two differences worth planning around.

**The unit is the subsection, not the page.** Case citations point at a page
and the whole page is retrieved. A statute citation points at
`§ 636(b)(1)(A)`, which is a specific clause inside a section that may run for
pages. Retrieving the section and checking the whole of it against a
proposition would be the statutory equivalent of ignoring the pin cite.

**A statute is quoted more often than a case is.** A brief paraphrases what a
case held; it reproduces what a statute says, because the words are the law.
That makes the deterministic quotation check — already built, in
`quotation/verbatim.py` — more valuable here than it is for cases, and it
suggests statutes may be the better place to demonstrate it.

## 6. The patterns had to be relaxed before any of this could run

Measured after section 5 was written, and it changed the order of the work.
eyecite generates law patterns the same way it generates reporter patterns, and
they are brittle in the same three places. The failure is silent: a statute
that does not match produces a bare section symbol typed as unknown and no law
citation at all, so a checker never sees it.

1. The section group admits digits, dots, dashes and colons and refuses a
   letter fixed to the digits. That rules out Title VII (`2000e-2`), the Fair
   Credit Reporting Act (`1681g`), the Rehabilitation Act (`794a`), the
   Securities Act (`77l`) and the National Wildlife Refuge System
   Administration Act (`668dd`).
2. Most law patterns join the reporter to the section symbol with a literal
   space and allow one after it.
3. Every reporter branch requires its closing period, so `42 U.S.C § 12132` and
   `29 U.S.C.A § 2612` match nothing. Both are written that way in the sampled
   filings.

Relaxing all three is in `statutes/exploratory_tokenizer.py`, which nothing
imports. It lived in `experimental/relaxed_eyecite_extractor.py` for part of a
day, which was a mistake: that is the case-citation extractor and it should
not change behaviour because of statute work. It now relaxes case patterns and
leaves law patterns exactly as eyecite generates them. Counting distinct
title-and-section pairs per document against what is written on the page:

| corpus | eyecite as published | relaxed |
|---|---:|---:|
| 26 test filings | 41/46 (89%) | 46/46 (100%) |
| 109 sampled filings | 218/247 (88%) | 246/247 (100%) |

The one remaining miss is layout damage — `78u-4` lost its hyphen — and that
same statute parses correctly elsewhere in the same document.

The relaxation is not applied to case patterns. A case reporter's closing
period is what separates it from the page in `410 U.S. 113`. The case
extraction benchmark is unchanged at 583/585 with no false positives.

Two side effects worth recording.

**`17 C.F.R. § 240.10b-5` is no longer truncated to `240`.** Rule 10b-5 is the
securities-fraud rule; part 240 is every rule under the Exchange Act. eyecite
returned the part, which would have sent a checker to the wrong provision.

**The letter suffix misreads a scanned digit.** In a typewritten filing in the
sampled corpus every digit 1 came out as a lowercase l, so `18 U.S.C. § 201`
reads as `20l` — a section that does not exist, where eyecite found nothing at
all. Four of the 53 letter-suffixed sections recovered across the 109 filings
are that damage, against 49 real ones. The widening is worth having, but it
constrains the existence check directly: **a letter-suffixed section that is
not in the code must not be reported as fabricated**, because the checker
cannot tell that case apart from a scanning artifact. It can be reported as
unresolved, which is honest and still useful.

## 7. What the existence check found across all 601 federal citations

The 18 U.S. Code titles the two corpora actually cite were downloaded (601
citations; titles 28 and 42 alone are 321 of them). Every U.S.C. citation was
resolved and checked offline:

| | count |
|---|---:|
| one section, found | 625 |
| a span, both endpoints found | 10 |
| no such section | 1 |
| unresolved, shaped like scanning damage | 5 |
| of all the above, cited under a title they have left | 5 |

The denominator is 641, not 601. A plural citation names several sections and
eyecite's pattern stops at the first, so `28 U.S.C. §§ 1331, 1332, 1441, and
1446` reached the checker as one citation instead of four. Reading the list
adds 40 sections, 33 of which appear nowhere else in their document. Of the 40,
39 are real; the one that is not is `42 U.S.C. § 2000e5`, written two words
after the same filing writes `2000e-5` correctly, so the hyphen was lost when
the page was read.

**No fabricated federal statute appears in 641 citations across 135 filings.**
That is the base rate, and it is a useful negative: the existence check is
cheap and offline, but on real filings it almost never fires. A paper claiming
statute checking as a contribution cannot lean on it.

The single absence is `42 U.S.C. §§ 2000, et seq.`, written for Title VII,
which is 2000e et seq. Bare 2000 is not a section. That is imprecise rather
than invented.

**The five in-force failures are the real finding.** `42 U.S.C. § 14135a` was
moved to title 34 in the 2017 reorganization and `25 U.S.C. § 477` was
reclassified in 2016; three filings cite them under the titles they have left.
This is the defect class with no case-citation equivalent — an overruled case
needs a citator and a judgement, while a transfer is recorded as a fact in the
Code — and it fires five times where the existence check fires zero.

Two things had to be built before these numbers meant anything, both in
`statutes/section_forms.py`:

- **A hyphenated section is often a span.** `28 U.S.C. §§ 2201-2202` covers two
  sections and `§§ 2201-02` is the same span abbreviated. eyecite hands the
  whole string over as one section. Ten of the fifteen apparent absences were
  this, and reporting them would have accused correct citations. A hyphenated
  string is read as a span only when it is absent as written *and* both
  endpoints are real sections, so `2000e-2` and `78u-4` never reach that
  branch.
- **An absence that mixes digits and letters is unresolved, not fabricated.**
  See the scanning damage in section 6. Every way a scan damages a section
  number lands in that shape — a `1` read as `l` gives `20l` for 201, a lost
  hyphen gives `2000e5` for `2000e-5` — and none can be told apart from an
  invented section. A section of digits alone carries no such ambiguity, so an
  absent one is still reported as absent.

## 8. Where to start

1. **Done.** Relax the law patterns, because 11% to 12% of statute citations
   never reached a checker at all. Section 6 has the measurement.
2. **Done.** Load the U.S. Code from the bulk XML and answer the existence and
   in-force questions offline. `statutes/us_code.py` and
   `statutes/section_forms.py`, measured in section 7.
3. Decide whether the in-force result is worth building on. Five findings in
   601 citations is a real defect class that nothing else in this project can
   see, but it is thin on its own. Widening the corpus is the way to know
   whether five is the rate or the sample.
4. Leave state statutes until federal is done, and expect the first work there
   to be recovering the code name from the raw text rather than checking
   anything.
