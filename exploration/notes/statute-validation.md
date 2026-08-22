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

## 6. Where to start

1. Load the U.S. Code from the bulk XML and answer the existence question for
   the 642 federal citations in the two corpora. No network, no model, and it
   establishes the base rate for how often a filing cites a section that is not
   there.
2. Add the in-force check from the same data, which is the defect with no case
   equivalent and therefore the most distinctive thing available here.
3. Leave state statutes until federal is done, and expect the first work there
   to be recovering the code name from the raw text rather than checking
   anything.
