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
case at a page inside it rather than the page it begins on.** Section 7
measures it over the annotated corpus, and both of the guesses in this
paragraph's first draft turned out to need qualifying — read that section
before building on this one.

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

1. **Done, and section 7 has the result.** Run the archive over every citation
   in both corpora and count how many name a page inside a case.
2. **The first thing to build.** Join this outcome to the citation tree, so a
   short form of a case the brief already introduced stops being reported as a
   wrong first page. Section 7.1 says that is about half the findings whose
   case name agrees, and the tree already resolves exactly this.
3. Use it as the case-name reference for the annotation in
   `case-name-extraction.md`. It gives a name for every page of every volume it
   holds, offline, which is exactly what that annotation needs — with the same
   caution recorded there: it is a reference to check the annotation against,
   never the value written into it.
4. Check the parallel citations against the duplicate-merging problem in
   `candidate-cardinality.md`. A record giving both `139 A.D.3d 695` and
   `32 N.Y.S.3d 201` settles a parallel-citation clash directly.

## 7. What the annotated corpus says

Run over all 3,138 case citations in the 1,300 annotated LePhantomCite
excerpts. The archive could answer for **2,622, or 84%** — much better than the
57% on the unannotated filings, because those cite Westlaw heavily and these
cite reporters.

| outcome | count | share |
|---|---:|---:|
| starts a case | 2,403 | 76.6% |
| reporter not in the archive | 318 | 10.1% |
| volume not published | 198 | 6.3% |
| no case covers the page | 110 | 3.5% |
| **inside a case** | **109** | **3.5%** |
| page claimed by two cases | 0 | 0% |

**66 of the 109 carry a defect label, against a corpus base rate of 10%.** Every
one of the 66 is `case_name_mismatch` — not one `wrong_pincite`, `misquote` or
`content_misrepresentation`. That is roughly a twelve-fold lift on that label.

### 7.1 Two reasons that is not a precision figure

**The corpus is defect-injected, and this may be detecting the injector.** A
`case_name_mismatch` there looks to have been made by pairing a real case name
with a wrong page, and a wrong page lands mid-case at whatever rate mid-case
pages occur — which is exactly what this finds. Of the 160 labelled occurrences
that joined, 66 sit inside a case, 47 fall in a gap and 39 start one. If the
injector had borrowed another real citation, all 160 would start a case. It did
not; it perturbed digits. So this measures the index against that generator.

**A short form written without "at" reads as a wrong first page.**
`*Chevron*, 467 U.S. 842-43` and `Kimbrough, 552 U.S. 101-02` are pin cites into
cases the brief introduced earlier. eyecite reads them as full citations because
no `at` separates the page, so the index correctly reports a mid-case page and
it is not a defect. About half the 15 findings whose case name *agrees* with the
covering case are this shape, and they share a signal: eyecite recovers only one
party, because a short form names only one.

**So anything built on this outcome must first establish that the citation is
not a short form of a case already introduced in the document.** That is a
document-level question the index cannot see, and the citation tree already
computes exactly it — a short form resolves to the full citation that
introduced the case. Wiring the two together is the next step, and until it is
done this outcome is a lead rather than a finding.

### 7.2 What survives, and it is unlabelled

The other half of the name-agreeing findings are genuine first-page errors in
real briefs that no annotator marked, and eyecite recovered both parties for
each:

| as written | the case actually starts at |
|---|---|
| `Brady v. United States, 397 U.S. 757` | 742 |
| `Medtronic v. Lohr, 518 U.S. 480` | 470 |
| `Abbey v. United States, 99 Fed. Cl. 441` | 430 |
| `Day v. AT&T Corp., 63 Cal. App.4th 325` | 319 |
| `City of Canton v. Harris, 489 U.S. 379` | 378 |
| `Sherar v. Cullen, 481 F. 2d 946` | 945 |
| `Haines v. Kerner, 404 U.S. 520` | 519 |

These are not injected — they are what the source documents contain. They are
the real-world signal, and the annotations are silent on all of them.

### 7.3 Two other results

**`non_existent_citation` never reaches the index at all.** All 150 use an
invented reporter series (`F.6th`, `Mass. App. 4th`, `P.4th`), and eyecite has
no pattern for any of them, so nothing is extracted and there is nothing to look
up. The invented-reporter check is the right tool there and this is not.

**A pin-cite range check is much weaker.** Of 1,548 citations that start a case
and carry a numeric pin, 16 name a pin outside the case's pages; 6 are labelled
`wrong_pincite` and 8 of the other 10 are artefacts of the archive recording a
one-page span. Six of 121 joined `wrong_pincite` labels is not a usable check.

### 7.4 Coverage

Of the 516 citations the archive could not speak for, the shape is different
from the unannotated corpus. 318 name a reporter with no directory — 258 of
those are Westlaw or LEXIS, which are not reporters. **The 198 unavailable
volumes are mostly too _early_, not too late**: 108 `S. Ct.` and 36 `L. Ed. 2d`
citations fall before the archive's first published volume of those reporters,
which run only 134–140 and 176–181. Only 18 fall after a reporter's last
volume. So "the archive ends around 2020" is a minor limit here; the real one is
that its static files carry a narrow slice of the parallel Supreme Court
reporters.

## 8. The same check over real filings finds nothing

Run over the 135 filings that carry no injected defects — the 26 test filings
and the 109 sampled from other courts, 2,007 case citations between them.

| what the check concluded | count |
|---|---:|
| the case name disagrees, so this is a name question not a page one | 18 |
| a short form written without `at` | 9 |
| **a wrong first page** | **0** |

**Nothing is reported.** Set against the 7 found among the 3,138 citations in
the annotated excerpts, the rate of this defect in real filings is somewhere
under a tenth of a percent, and on this corpus it is zero.

That is worth stating plainly rather than burying. The check is sound, the 7 it
found are real and verified by hand, and it is a rare defect. Anyone planning
to build on it should size the effort against a defect that fires roughly twice
in a thousand citations, not against the 61% label agreement in section 7 —
which, as 7.1 says, is largely a property of how that corpus was built.

The 18 name disagreements are a different matter and are not this check's
business: the page belongs to one case and the filing names another, which is
the case-name defect, and the name check is what should report it.
