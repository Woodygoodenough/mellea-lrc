"""Detect citations to reporter series that were never published.

A reporter is published in numbered series: the North Eastern Reporter runs
`N.E.`, `N.E.2d`, `N.E.3d`, and stops there. `531 N.E.4th 224` names a series
that does not exist, so no case can be at that address and no lookup is needed
to say so. The volume and page are ordinary numbers and the court and year read
normally, which is what makes the citation survive an unaided reading.

This rule exists because **eyecite does not report these at all**. Its patterns
are built from the same reporter database used here, so a citation naming a
series outside it matches nothing and is returned as no citation rather than as
a bad one. Every later stage therefore never sees it: it is not extracted, not
looked up, and not counted among the citations a document contains. A checker
built only on extracted citations scores these as absent rather than as false,
which is the most expensive way to be wrong about a fabricated citation.

The rule reports only a series that is impossible **for a reporter family that
exists**. An entirely unknown name is a different question -- the database is
extensive but not complete, and an obscure or foreign reporter it lacks is not
evidence of fabrication. Requiring the family to be known keeps the verdict to
one that can be stated exactly: this family runs through `N.E.3d`, and the
citation names `N.E.4th`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from reporters_db import EDITIONS, VARIATIONS_ONLY

# A series suffix as written in a citation: `2d`, `3d`, `4th`. Reporters use
# `2d`/`3d` where ordinary English uses `2nd`/`3rd`, and fabricated citations
# are written both ways, so both are accepted.
_SERIES_SUFFIX = re.compile(r"^(?P<family>.*?)\s*(?P<series>\d+)\s*(?:d|st|nd|rd|th)$")

# The publisher a reporter is issued by, which the database appends to an
# edition name and a citation almost never carries.
_PUBLISHER_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")

# A citation whose reporter carries a series suffix. The volume and page are
# required: they are what make this an address rather than a mention of a
# reporter, and without them there is nothing to be wrong about.
#
# `at` is admitted so short forms (`531 N.E.4th at 242`) are caught too. A
# fabricated series is fabricated in either form.
_ADDRESS = re.compile(
    r"(?<!\d)(?P<volume>\d{1,4})\s+"
    r"(?P<reporter>[A-Z][A-Za-z.'’]*(?:\s+[A-Za-z.'’]+)*\s*\d+\s*(?:d|st|nd|rd|th))\s+"
    r"(?:at\s+)?(?P<page>\d{1,5})(?!\d)"
)


@dataclass(frozen=True, slots=True)
class ImpossibleSeries:
    """One citation naming a series its reporter family never reached."""

    text: str
    """The citation text as it appears, from volume through page."""

    start: int
    end: int

    volume: str
    reporter: str
    """The reporter as written, including the impossible series suffix."""

    family: str
    """The canonical reporter family the name resolves to."""

    series: int
    """The series the citation names."""

    highest_published_series: int
    """The highest series that family actually reached."""

    page: str

    @property
    def reason(self) -> str:
        """Why this address cannot exist, in terms a reader can check."""
        return (
            f"{self.reporter} names series {self.series} of {self.family}, "
            f"which was published only through series {self.highest_published_series}."
        )


def _normalise(name: str) -> str:
    """Key a reporter name so spacing, case, and periods cannot hide a match.

    `Mass. App.` and `Mass.App.` are the same reporter, and the database
    registers only the second as a variation, so comparing the strings as
    written misses it.

    Periods go too, and that one is load-bearing rather than tidy: a citation
    written `701 F. Supp 2d at 917` is an ordinary citation with a missing
    period, but keeping the period made `F. Supp` a family of its own holding
    only a first series, and every real `F. Supp. 2d` written that way was then
    reported as naming a series that does not exist. Dropping periods merges
    nine pairs across the database and every one of them is the same reporter
    written two ways -- `Vt.` and `VT`, `N.M.` and `NM` -- so the union is what
    was meant in each case.
    """
    return "".join(name.split()).replace(".", "").casefold()


@dataclass(frozen=True, slots=True)
class _Family:
    """What a reporter family is called and which series it published."""

    name: str
    series: frozenset[int]


def _split(name: str) -> tuple[str, int]:
    """A reporter name as its family and the series it names.

    A trailing publisher comes off first. The database names several editions
    `A.F.T.R.2d (RIA)` and `U.C.C. Rep. Serv. 2d (West)`, and the series suffix
    has to end the string to be read -- so the publisher hid it, those families
    were recorded as reaching only a first series, and every real second-series
    citation to them was reported as naming a series that does not exist.
    """
    match = _SERIES_SUFFIX.match(_PUBLISHER_SUFFIX.sub("", name).strip())
    if match is None:
        return name, 1
    return match.group("family"), int(match.group("series"))


@lru_cache(maxsize=1)
def _families() -> dict[str, _Family]:
    """Every reporter family, keyed by every spelling that reaches it.

    A variation carries no series of its own. `Fed.` is registered as another
    way of writing `F.`, and the Federal Reporter ran through `F.4th`, so
    `151 Fed 2nd 240` is an ordinary citation. Giving the variation its own
    entry left it holding a first series only and reported every real citation
    written that way as impossible, so a variation resolves to what it is a
    variation of and inherits that family's series.
    """
    published: dict[str, set[int]] = {}
    display: dict[str, str] = {}
    for edition in EDITIONS:
        family, series = _split(edition)
        key = _normalise(family)
        published.setdefault(key, set()).add(series)
        display.setdefault(key, family)

    families = {key: _Family(display[key], frozenset(series)) for key, series in published.items()}
    for variation, canonicals in VARIATIONS_ONLY.items():
        for canonical in canonicals:
            target = families.get(_normalise(_split(canonical)[0]))
            if target is not None:
                families.setdefault(_normalise(_split(variation)[0]), target)
    return families


def find_impossible_series(text: str) -> tuple[ImpossibleSeries, ...]:
    """Every citation in `text` naming a series its reporter never published."""
    found: list[ImpossibleSeries] = []
    families = _families()
    for match in _ADDRESS.finditer(text):
        reporter = " ".join(match.group("reporter").split())
        parts = _SERIES_SUFFIX.match(reporter)
        if parts is None:
            continue
        series = int(parts.group("series"))
        family = families.get(_normalise(parts.group("family")))
        # An unknown family is not evidence of anything: the database is
        # extensive but not exhaustive, and a reporter it lacks is a gap in the
        # database as readily as a fabrication.
        if family is None or series in family.series:
            continue
        found.append(
            ImpossibleSeries(
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                volume=match.group("volume"),
                reporter=reporter,
                family=family.name,
                series=series,
                highest_published_series=max(family.series),
                page=match.group("page"),
            )
        )
    return tuple(found)
