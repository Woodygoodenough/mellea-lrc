"""Docket numbers as filings write them and as courts record them.

A filing writes `No. 05-4206`; the court's system holds `2:05-cv-04206`. The
office prefix, the zero padding and the judge's initials are the clerk's, not
the case's. What names the case is the year, the kind of case and the
sequence, so those are what two numbers are compared on and what a query is
built from.

The kind is half of the identity, not decoration: a district assigns
`21-cv-01915` and `21-cr-01915` in the same year to different cases, and
document 016 of the bench cites `1:25-cv-05745-RPK` and `1:25-cr-00312-RPK`
side by side. Where only one side names the kind the two are compared on what
they both state, since a filing that omits `cv` has not said the case is
something else.

The kind table and this rule are the search route's, ported from
`validation/open_search/docket_date.py` so the two stages read a number the
same way.
"""

from __future__ import annotations

import re

MIN_GROUPS = 2
"""Digit groups a docket number must have: the year and the sequence."""

_TOKEN = re.compile(r"[A-Za-z]+|[0-9]+")
_KINDS = {"cv": "cv", "civ": "cv", "civa": "cv", "cr": "cr", "crim": "cr", "bk": "bk",
          "ap": "ap", "adv": "ap", "md": "md", "mdl": "md", "mc": "mc", "misc": "mc",
          "mj": "mj", "sw": "sw"}  # fmt: skip


def docket_parts(number: str | None) -> tuple[str, str | None, str] | None:
    """A docket number as the year, the kind of case, and the sequence.

    `2:05-cv-04206` and `No. 05-4206` are both `('05', 'cv'|None, '4206')`:
    the office prefix goes, the padding goes, `Civ.` and `cv` are one word,
    and `PAB-KAS` on the end is the judge rather than the case.
    """
    if not number:
        return None
    tokens = _TOKEN.findall(number)
    digits = [index for index, token in enumerate(tokens) if token.isdigit()]
    if len(digits) < MIN_GROUPS:
        return None
    year, sequence = tokens[digits[-2]], tokens[digits[-1]]
    kind = next(
        (_KINDS[token.lower()] for token in tokens[digits[-2] : digits[-1]] if token.lower() in _KINDS),
        None,
    )
    return year.lstrip("0") or "0", kind, sequence.lstrip("0") or "0"


def docket_core(number: str | None) -> tuple[str, str] | None:
    """The year and sequence, for building a query the archives match loosely.

    The year keeps the two digits a docket number is written with -- both
    archives answer `05-4206` and neither answers `5-4206` -- while the
    comparison strips them, since what is compared is the number itself.
    """
    parts = docket_parts(number)
    return (parts[0].zfill(2), parts[2]) if parts else None


def docket_number_matches(written: str | None, recorded: str | None) -> bool:
    """Whether two docket numbers name the same case, allowing for how each was written.

    Where both name a kind, they must agree: a civil case and a criminal case
    can share a number in the same district in the same year.
    """
    left, right = docket_parts(written), docket_parts(recorded)
    if left is None or right is None:
        return False
    if left[1] and right[1] and left[1] != right[1]:
        return False
    return (left[0], left[2]) == (right[0], right[2])


__all__ = ["docket_core", "docket_number_matches", "docket_parts"]
