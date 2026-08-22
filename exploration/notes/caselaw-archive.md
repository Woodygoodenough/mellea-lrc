# A bulk archive beats a search agent

Written 22 August 2026. This started as an attempt to design a web search for
citations CourtListener cannot settle, restricted to trustworthy domains. It
ended somewhere better, and the reason is worth writing down because it applies
beyond this one case.

## 1. The domain-first rule, and how far it got

Trust is not a property of a hostname alone. A court's own site is
authoritative for **its own** decisions and says nothing about anyone else's:
the Ninth Circuit publishing Ninth Circuit opinions is the record itself, and
its silence about a New York case means nothing. So the tiers in
`experimental/web_refutation/domains.py` are scoped by jurisdiction, not just
ranked:

| tier | who | example |
|---|---|---|
| 1, the court | the deciding court publishing its own decision | `supremecourt.gov`, `ca9.uscourts.gov`, `nycourts.gov` |
| 2, government | another arm of government republishing official text | `govinfo.gov`, `loc.gov` |
| 3, archive | an established archive transcribing official text, selling nothing | `law.cornell.edu`, `case.law`, `courtlistener.com` |
| 4, commercial | a commercial legal publisher | `justia.com`, `casetext.com` |
| untrusted | everything else | not evidence in either direction |

Only tiers 1 and 2, and only for the right jurisdiction, may support a
refutation. Commercial sites are deliberately excluded: several now carry
generated summaries beside transcribed text, and a result page does not say
which one it is.

## 2. It works, and it is not reproducible

Tested on three citations from the corpus whose case name disagrees with the
CourtListener record, searching `nycourts.gov` only:

- `183 A.D.3d 649` — the official bound-volume index gives `Goodine, Matter of,
  v Evans`. The filing wrote `Cornhill LLC v. Sowers`. Refuted, and it agrees
  with CourtListener exactly.
- `139 A.D.3d 695` — the official index puts `Cadle Co. v Ayala` at
  **47 A.D.3d 919**, a different volume from the filing's.
- `131 A.D.3d 1185` and `85 A.D.3d 1510` — the correct index came back both
  times and the answer was not in the snippet.

The mechanism is sound. Its reliability is not, for a specific reason:
**`nycourts.gov` returns 403 to every program.** The whole site is behind bot
protection, PDFs and HTML alike. The official reports are therefore reachable
only through a search engine's index of them, and the evidence is whatever the
snippet happened to include.

A verification result that depends on a search snippet cannot be reproduced
next year, by anyone else, or by us. That is the same standard the project
already applies to its CourtListener cache, and this fails it.

## 3. What was there instead

`static.case.law` — the Caselaw Access Project, Harvard's digitisation of the
printed reporters, published as plain static files. No API key, no allowance,
no account, 401 reporters. Each volume carries a `CasesMetadata.json` listing
every case in it with its name, court, decision date, official and parallel
citations, and **first and last page**.

The page range is the part a lookup service cannot offer. CourtListener answers
"is there a case at page 691?" — and for a page inside a case it answers no,
confirmed directly: `489 U.S. 379` returns 404 even though *City of Canton v.
Harris* occupies pages 378 to 400. The archive answers a different question,
"what covers page 691?", and that turns a silence into a finding.

Of the four unresolved locators whose volume the archive holds:

| citation | what the archive says |
|---|---|
| `489 U.S. 379` | inside *City of Canton v. Harris*, which starts at 378 |
| `54 F.3d 691` | inside *United States v. Smith*, which starts at 690 |
| `481 F. 2d 946` | inside *Sherar v. Cullen*, which starts at 945 |
| `243 F.R.D. 604` | covered by nothing — reported as absent, not as a defect |

The third is the one to read twice. The filing's own text names *Sherar v.
Cullen*, and the archive puts *Sherar v. Cullen* at 481 F.2d 945. Nothing was
invented; a page is off by one. That citation had no verdict at all before.

This is a new outcome and it deserves its own name: **the citation names a real
case at a page inside it rather than the page it begins on.** It is positive
evidence about a specific defect, and it is the commonest way a pin cite gets
written where a first page belongs.

Implemented in `caselaw/cap_index.py`.

## 4. What it does not cover

**The archive ends around 2020.** Volume 157 is the last A.D.3d and `587 U.S.`
is not there. A recent volume reports `VOLUME_UNAVAILABLE`, which is a
statement about the index and never about the citation.

**It cannot touch the largest part of the unresolved bucket.** Of the 64
distinct unresolved locators, 58 name a Westlaw or LEXIS record or an agency
document rather than a reporter, and `reporter_slug` returns `None` for those
because they are not reporters. See `open-ended-search.md` section 5. Six had a
reporter the archive covers, and two of those six were past its cutoff.

**A page range is a printed page.** Falling inside a case says the locator is
wrong; it says nothing about whether the proposition is on that page.

**The host refuses urllib's default User-Agent** with a 403 while serving the
same file to a browser. The client sends an honest descriptive User-Agent
rather than impersonating one — the files are published for bulk use, and the
rule is aimed at scrapers rather than at readers.

## 5. The general point

The web search and the bulk archive were reached by the same reasoning — prefer
the publisher closest to the source — and it produced two very different
answers. Searching an authoritative site through a third-party index inherits
that index's caprice. Downloading what the same institutions publish in bulk
does not.

So the ordering is not "official domains first, then the rest of the web". It
is:

1. **A bulk corpus that can be held locally.** Reproducible, free of any
   allowance, and it can answer questions its publisher's own search cannot —
   the page range being exactly that.
2. **An API against a known corpus**, which is CourtListener today. Its
   boundary is knowable, so its silence has a defined meaning.
3. **A domain-restricted search**, only where neither of the above reaches, and
   only to refute.
4. **The open web**, which is not evidence.

Two bulk corpora are now in the project on this basis — the United States Code
in `statutes/us_code.py` and the reporters here — and both answer questions
that were previously either unanswerable or rate-limited.

## 6. Next

1. Run the archive over every locator in both corpora, not just the unresolved
   ones, and count how many citations name a page inside a case rather than its
   start. That is a defect class nobody has measured.
2. Use it as the case-name reference for the annotation in
   `case-name-extraction.md`. It gives a name for every page of every volume it
   holds, offline, which is exactly what that annotation needs — with the same
   caution recorded there: it is a reference to check the annotation against,
   never the value written into it.
3. Check the parallel citations against the duplicate-merging problem in
   `candidate-cardinality.md`. A record giving both `139 A.D.3d 695` and
   `32 N.Y.S.3d 201` settles a parallel-citation clash directly.
