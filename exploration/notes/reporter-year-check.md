# A reporter-year check that does not work

Written 22 August 2026. Recorded because the idea is attractive, cheap to try,
and wrong, so the next person to think of it should be able to skip it.

## The idea

Every reporter series was published between known dates. *Federal Reporter,
Fourth Series* began in 2021; *Federal Reporter, Second Series* ended in 1993.
A citation naming a year outside its series' range is therefore impossible on
its face — `550 F.4th 100 (9th Cir. 1995)` cannot exist — and both halves are
already in hand: `reporters-db` ships the date ranges, and eyecite parses the
year out of the citation.

It is the kind of error a language model produces when inventing a citation,
because it picks a plausible reporter and a plausible year independently.

## What it found

Across the 26 test filings and the 109 sampled ones, 1,634 case citations carry
both a year and a reporter with a recorded range. 37 were flagged.

**All 37 are false.** They come from two causes in roughly four-to-one
proportion.

### The date ranges in reporters-db are wrong for some series

| series | reporters-db says | actually |
|---|---|---|
| `F. Supp.` | 1932–1988 | 1932–1998 |
| `F.R.D.` | 2001–present | 1940–present |

29 of the 37 flags are these two. `130 F.R.D. 455` is a 1990 volume and the
database claims the series began in 2001, so every correct F.R.D. citation
before 2001 is reported as impossible.

### eyecite attaches a year from the neighbouring citation

The other 8 use series whose ranges look right, and every one is a year taken
from a different citation nearby:

| flagged | year attached | what the surrounding text says |
|---|---|---|
| `540 F. Supp. 3d 638` | 2004 | `Greer's Ranch Cafe v. Guzman, 540 F. Supp. 3d 638, 645 (N.D. Tex. 2021)` |
| `686F.3d 122` | 1927 | `Albrecht v. United States, 271 U.S. 1, 8 (1927)` |
| `101 F. Supp. 3d 356` | 1975 | `Doe v. Commonwealth's Attorney, 403 F. Supp. 1199 (E.D. Va. 1975)` |

In the first the correct year is printed beside the citation and was passed
over. All 8 sit in text where the spacing is damaged — `686F.3d`,
`760F.2d618,62l`, `N.D. Tex.2021` — which is what breaks the year attachment.

## Why it cannot be repaired cheaply

Both causes have to be fixed for the check to say anything, and neither is
small. The date ranges would need auditing against another source, series by
series; there are several thousand of them and no reason to think the two found
here are the only wrong ones. The year attachment would need eyecite to be
right about which citation a parenthetical belongs to, in exactly the text
where it is least able to be.

Until then the check produces confident, wrong accusations about correct
citations, which is the worst failure available to this project.

## What the flags are actually good for

They are not a signal about the filing. They are a signal about **our own
reading of it**: all 8 of the second group sit in text this pipeline mangled.
A year that contradicts its reporter is a cheap indicator that the extraction
around that point went wrong, which is worth having as a diagnostic even though
it is worthless as a verdict.

That inverts the usual direction. Most checks here ask whether the document is
sound; this one, honestly labelled, asks whether we read it correctly.
