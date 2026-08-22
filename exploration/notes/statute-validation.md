# Checking statute citations

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

Relaxing all three, scoped to law patterns only, is in
`experimental/relaxed_eyecite_extractor.py`. Counting distinct
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

## 7. Where to start

1. **Done.** Relax the law patterns, because 11% to 12% of statute citations
   never reached a checker at all. Section 6 has the measurement.
2. **Done for titles 28 and 42.** Load the U.S. Code from the bulk XML and
   answer the existence question. `statutes/us_code.py` does this offline. On
   the 52 citations in those two titles across both corpora, all 52 exist and
   all 52 are in force, so the base rate for a fabricated federal statute in
   this data is zero out of 52 — an upper bound of roughly 6% by the rule of
   three, which is too loose to be worth reporting on its own. Downloading the
   remaining titles is the next step and is the cheapest way to tighten it.
3. Add the in-force check across all titles from the same data. It is the
   defect with no case equivalent and therefore the most distinctive thing
   available here.
4. Leave state statutes until federal is done, and expect the first work there
   to be recovering the code name from the raw text rather than checking
   anything.
