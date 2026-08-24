# A real case, correctly named, with an invented citation

23 August 2026. The clearest single finding the reporter archive has produced,
and it is a defect class the project had not named.

## 1. What the filing wrote

From a 2024 memorandum in opposition in the Southern District of New York
(`008__sai-malena-jimenez-fogarty…`), three times in the body and once in the
table of authorities:

> *Wells Fargo Bank, N.A. v. Enitan* (155 A.D.3d 781, 2d Dept. 2017)

Attached to it: that a process server's affidavit establishes a presumption of
proper service, and that a defendant's conclusory denial does not overcome it.

## 2. Everything about it is right except the citation

| part | verdict |
|---|---|
| the case name | **real, and exactly right** |
| the court | **right** — Second Department |
| the proposition | **right** — that is what the case holds |
| the citation | **invented** |

*Wells Fargo Bank, N.A. v Enitan* is **200 A.D.3d 736**, decided in 2021. The
filing gives 155 A.D.3d 781 and dates it 2017.

## 3. What sits at the page it cited

Nothing starts there. The archive puts page 781 inside *People v. Pagan*, which
begins at 155 A.D.3d 779 — an unrelated criminal appeal about whether an order
modifying probation conditions can be appealed.

## 4. How it was established, and why that matters

Three independent sources, none of which is the citation-lookup service that
the rest of this project leans on:

1. **The offline reporter archive** — page 781 starts no case and falls inside
   *Pagan* (155 A.D.3d 779–782), and no party named Enitan appears in any of
   the 157 A.D.3d volumes it publishes.
2. **The New York courts' own site**, searched under the domain-first rule in
   `open-ended-search.md`: *People v Pagan* is confirmed at 155 A.D.3d 779.
3. **The same source**, confirming *Wells Fargo Bank, N.A. v Enitan* at
   200 A.D.3d 736.

This is the case that rule was written for. The archive alone left a caveat —
it stops around volume 157, so a later *Enitan* could not be excluded from its
silence — and the second and third sources close exactly that gap. **An
authoritative publisher giving the case a different citation is a refutation;
finding nothing would not have been.**

## 5. Why this class is worse than an invented case

An invented case name is caught by anyone who looks for it. This is not:

- **The proposition checks out.** A reader who verifies what the brief says
  about service of process finds it correct, because the case really does hold
  that. The check that would catch a misrepresented holding passes.
- **The name checks out.** Searching the name finds a real case, decided by the
  court the filing names, on the subject the filing is arguing.
- **Only the numbers are wrong**, and numbers are what nobody reads.

A verifier built around "does this case exist" and "does it say what is
claimed" answers yes to both and reports the citation sound. What fails is the
narrower question of whether the case is *at the page given*, which is what the
page-range check asks and what a lookup service cannot answer, because it looks
up a page and finds nothing rather than looking at what occupies it.

## 6. It is not rare

Five of the twenty confirmed different-case findings over the 26 test filings
have this shape rather than a fabricated name:

| as written | where the case actually is |
|---|---|
| *Wells Fargo Bank v. Enitan*, 155 A.D.3d 781 | 200 A.D.3d 736 |
| *Cadle Co. v. Ayala*, 139 A.D.3d 695 | 47 A.D.3d 919 |
| *JPMorgan Chase Bank v. Szajna*, 104 A.D.3d 715 | 72 A.D.3d 902 |
| *Schum v. Bailey*, 578 F.2d 411 | 578 F.2d 493 (and the 3d Circuit, not the 2d) |
| *Calderon-Cardona v. BNY Mellon*, 821 F.3d 161 | 770 F.3d 993 |

A sixth is a variant worth keeping separate: *22nd Ave. Station v. City of
Minneapolis* at 429 F. Supp. 2d 144 is correctly named and correctly placed
except that the first page lost its leading digit — it is 1144.

## 7. What follows

**A defect taxonomy needs this as its own category.** "Fabricated citation"
covers an invented case; this is a real case with an invented locator, and the
two are caught by different checks and mean different things about how the
brief was written.

**And it argues for checking the locator even when everything else passes.**
The natural order — does the case exist, does it say what is claimed — never
reaches the question this fails.
