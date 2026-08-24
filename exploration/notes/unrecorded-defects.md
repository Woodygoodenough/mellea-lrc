# Seventeen defects nobody recorded

23 August 2026. Both reporter checks run over the 910 `aux_train` excerpts —
the larger and far less examined half of the annotated set — and every flag
the annotations did not already cover was read one at a time.

**Seventeen are real defects that no annotator marked.** Nine of them sit in
excerpts carrying no annotation whatsoever.

## 1. Why these are the filings' own errors, not unlabelled injections

This is the check that had to be done first, because the corpus has defects
deliberately inserted and finding "new" ones could just mean finding those.

The two look nothing alike. **The injector swaps the whole reporter for an
unrelated one and prints a court that contradicts it** — `Haig v. Agee, 978
P.2d 1011 (Or. Ct. App. 1999)` puts a United States Supreme Court case in a
Pacific reporter attributed to an Oregon court. **Every one of the seventeen is
a single-digit or single-series slip with a court and year that stay
consistent** — `553 U.S. 194` for `533 U.S. 194`, `739 F.2d 131` for `739 F.3d
131`. Different generator, and the second is what a person or a drafting tool
does.

## 2. The strongest: the filing contradicts itself

For these the evidence needs nothing outside the document plus the archive.

| as written | what the archive has | what gives it away |
|---|---|---|
| *United States v. Shipsey*, **363 F.3d 92**, 971 | Shipsey at 363 F.3d **962**–974 | the filing's own pin cite is 971, impossible for a case starting at 92 — and it later writes "363 F.3d at 972" |
| *United States v. Beros*, **833 F.2d 445**, 460 | Beros at 833 F.2d **455**–468 | page 445 is inside *Diggs v. Owens*, which ends at 446, so pin 460 lies past the end of the case cited |
| *Bilski v. Kappos*, **561 U.S. 393**, 604 | Bilski at 561 U.S. **593**–660 | pin 604 is outside the covering case and inside Bilski's span |
| *Anderson v. Liberty Lobby*, **447 U.S. 242** | Anderson at **477** U.S. 242 | the filing prints the parallel cites `106 S. Ct. 2505` and `91 L. Ed. 2d 202`, which are 477 U.S. 242's |
| *Anderson v. Creighton*, **482 U.S. 635** | Anderson at **483** U.S. 635 | same — its own parallel citations identify the right volume |

A pin cite that cannot exist inside the case its own citation names is a
self-contained contradiction, and no external source is needed to see it.

## 3. Wrong series, right everything else

| as written | what the archive has |
|---|---|
| *Fox v. Elk Run Coal*, 739 **F.2d** 131 (4th Cir. 1-3-2014) | 739 **F.3d** 131, 4th Cir., decided 2014-01-03 — the exact date printed |
| *Lobato v. N.M. Env't Dep't*, 733 **F.2d** 1283 (10th Cir. 2013) | 733 **F.3d** 1283, 10th Cir., 2013-11-05 |
| *McDonald v. Superior Court*, 180 Cal.App.**2d** 297, 303-04 (1986) | 180 Cal. App. **3d** 297–304, 1986 — and the pin fits that span |

`F.2d` ended in 1993, so a 2014 date on an `F.2d` citation is impossible on its
face. That is the reporter-year check recorded as not working in
`reporter-year-check.md` — it fails there because the reporter database's dates
are unreliable, but the failure is in the reference data, not the idea.

## 4. Year or court contradicts the volume

*Saucier v. Katz* `553 U.S. 194` "(2001)" → 533 U.S. 194 · *DeShaney*
`89 U.S. 189` "(1989)" → 489 U.S. 189 · *Bd. of Trustees of SUNY v. Fox*
`494 U.S. 469` "(1989)" → 492 U.S. 469 · *Anderson v. Creighton* `438 U.S. 635`
"(1987)" → 483 U.S. 635 · *Hope v. Pelzer* `535 U.S. 730` "(2002)" → 536 U.S.
730 · *Almi Inc. v. Dick Corp.* `31 Pa. Commw. 218` → 31 Pa. Commw. 26 ·
*Ardesco Oil* `66 Pa. 374` → 66 Pa. 375.

Two of these share one excerpt that carries no annotation at all.

## 5. Right citation, wrong party

- **`415 F.3d 24`** — the filing writes *Heartland Regional Med. Ctr. v.
  **Sebelius*** (D.C. Cir. 2005). The case is *Heartland Regional Medical
  Center v. **Leavitt***. Sebelius did not become Secretary until 2009, so no
  2005 opinion can be captioned against her — and the filing's own case is
  *Allina Health Services v. Sebelius*, which is where the name came from.
- **`328 F.3d 1122`** — *Harris v. Rutsky & Co. Ins. Svcs. v. Bell &
  **Claimants**, Ltd.* The case is *Harris Rutsky & Co. Insurance Services v.
  Bell & **Clements** Ltd.* Volume, page, pin, court and year all correct; the
  party name is corrupted and an extra `v.` inserted.

The Sebelius one is the most interesting in the set, because the error is
internally datable: an official's tenure fixes the earliest date a caption
naming her can carry.

## 6. Where the checks are blind, which is the more useful half

44 annotated wrong-name citations were **not** flagged. Recall on what the name
check can reach is 68 of 76, or 89%. The misses divide sharply:

- **32 of 44 — the cited page falls in a gap.** The archive holds the volume
  and no case covers the page, so there is no recorded name to compare against
  and the check returns nothing by design. **This is the injector's own
  shape**: it pairs a real case name with an unrelated reporter and a page that
  lands nowhere.
- **8 — the name never arrived intact**, reaching the comparison empty or
  one-sided because emphasis markup swallowed a party. An extraction fault.
- **4 — the archive does not hold the volume.**

The gap outcome is *predictive* here — 39 of 69 gap citations carry a label,
57% against a 21% base rate — and reporting on it is still refused, because a
gap can be a case the archive is missing. That refusal is the same rule the
whole project runs on, and this is the clearest place it costs something real.

**Most of the 32 are reachable by a rule neither check has**: the reporter and
the court disagree. A `United States v.` case in `P.2d` attributed to an Oregon
court, a Virginia case with an `F.2d` parallel. That is a cheap check on the
citation's internal consistency and it does not touch an archive at all.

## 7. And a whole label class no archive check can ever reach

All **126** `non_existent_citation` labels in `aux_train` invent a *reporter
series* — `531 N.E.4th 224`, `423 F.5th 938`, `671 F. Supp. 4th 395`. eyecite
does not type them as citations at all, so nothing downstream sees them. They
need a "does this series exist" rule, which the project already has and which
is far cheaper than either of these checks. Worth stating plainly so nobody
tries to reach them from the archive.

## 8. What to do next

1. **Build the internal-consistency check**: reporter against court, reporter
   against year. Section 6 says it reaches most of what the archive cannot, and
   section 3 says it catches real errors too. It needs no external source.
2. **Three real weaknesses in the name comparison**, found here and not
   recorded before: a filing that writes given names (`Holly Wood v. Richard F.
   Allen` against the archive's surname-only caption), a split surname
   (`La Force` against `LaForce`), and a one-word caption (`In re Grand Jury
   Proceeding Impounded` against the archive's short name `Impounded`).
3. **The California citation order breaks extraction**: `Armstrong v. Brown
   (N.D. Cal. 2013) 939 F.Supp.2d 1012` puts the court and year before the
   reporter, and the case name comes out as `N.D. Cal. 2013`. Seven occurrences
   here, and it is a state convention rather than damage.
