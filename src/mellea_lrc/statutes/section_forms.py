"""Resolve what a cited section string names before asking whether it exists.

:meth:`~mellea_lrc.statutes.us_code.UsCodeIndex.lookup` answers a plain
question: is this exact section in the Code? A citation as written in a filing
does not always name one section, and taking the string at face value produces
confident wrong answers. Across the 601 U.S.C. citations in this project's two
corpora, the plain lookup reports 15 sections as absent. Fourteen of them are
real law, misread in two ways:

* **A section range.** ``28 U.S.C. §§ 2201-2202`` means sections 2201 through
  2202, and ``28 U.S.C. §§ 2201-02`` means the same thing with the second
  number abbreviated in the ordinary Bluebook way. eyecite's section pattern
  swallows the hyphen, so the section reads as ``2201-2202`` -- which is not a
  section, and reporting it as absent would accuse a correct citation. Ten of
  the fifteen are this.
* **A digit that came out of the scan as a letter, or a hyphen that did not
  survive.** In one typewritten filing every ``1`` was rendered ``l``, so
  ``18 U.S.C. § 201`` reads as ``20l``. Another filing writes ``2000e5`` in a
  list two words after writing ``2000e-5`` correctly. Four of the fifteen are
  this, and one more (``42 U.S.C. § 200d`` for ``2000d``) is a dropped digit of
  the same character.

Both are settled by evidence rather than by guessing. A hyphenated section is
treated as a range only when it is absent as written **and** both endpoints
exist -- so ``42 U.S.C. § 2000e-2`` and ``15 U.S.C. § 78u-4``, which are real
hyphenated sections, never reach the range branch at all. Damaged digits cannot
be repaired from the Code, so they are reported as unresolved, which is the
honest answer: this checker cannot tell a scanning artifact from a fabrication,
and the two must not be reported alike.

What is left after both is one citation: ``42 U.S.C. §§ 2000, et seq.``, which
a filing wrote for Title VII. Title VII is 2000e et seq.; bare 2000 is not a
section. That is imprecise rather than invented, and it is the only citation in
601 that this layer cannot account for.

:func:`listed_sections` answers a different question about the same string: a
plural citation names several sections and eyecite's pattern stops at the first,
so the rest are absent from the count rather than reported wrongly. Reading them
adds 33 sections across the two corpora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mellea_lrc.statutes.us_code import ProvisionStatus, UsCodeIndex

# A hyphenated section, split at its last hyphen. `2000e-2` and `2201-2202`
# both match; which one is a range is decided by the Code, not by the shape.
_HYPHENATED = re.compile(r"^(?P<start>.+)-(?P<end>[0-9]+[a-zA-Z]?)$")

# A section that mixes digits and letters. Real ones are common (`1681g`,
# `2000e-5`, `668dd`, `1915A`), which is why an absent one cannot be called
# fabricated -- every way a scan damages a section number lands in this shape:
# a `1` read as `l` gives `20l` for 201, and a lost hyphen gives `2000e5` for
# `2000e-5`, which one filing writes in a list two words after writing
# `2000e-5` correctly. A section of digits alone carries no such ambiguity, so
# an absent one is reported as absent.
_MIXED_ALPHANUMERIC = re.compile(r"^(?=.*\d)(?=.*[a-zA-Z])[0-9A-Za-z\-.:]+$")

# A range's endpoints have to be numbers to be enumerated at all.
_NUMERIC = re.compile(r"^\d+$")

# The plural section symbol, or the plural word, inside a citation's own text.
# It is what licenses reading a list after the citation: `§ 1331, 1332` is a
# writing error, `§§ 1331, 1332` is two sections.
_PLURAL_MARKER = re.compile(r"§\s*§|\bSect(?:ion)?s\b|\bSs\b", re.IGNORECASE)

# One more section in a list, separated by a comma and optionally the word
# "and": `, 1332`, `, and 1446`, `, 1446(b)`. The leading group swallows the
# *previous* section's subsections, without which a list like
# `§§ 1225(b)(1)(B)(ii), 1226(c), 1231(a)(2)(A)` stops after its second entry.
# Matched at a position rather than searched for, so reading stops at the first
# thing that is not another section -- which is what keeps
# `§§ 1331, 1332, and the rules thereunder` from swallowing the prose.
_NEXT_LISTED = re.compile(
    r"(?:\([0-9A-Za-z]+\))*\s*,\s*(?:and\s+)?"
    r"(?P<section>\d[0-9A-Za-z]*(?:[\-.:]\d+[a-zA-Z]{,2})*)",
    re.IGNORECASE,
)

# `2201-2202` and `2201-02` are the same range. Above this many sections the
# citation is a span the filing is pointing at wholesale rather than a list
# worth enumerating, and the endpoints are what get checked.
MAX_ENUMERATED_RANGE = 32


class SectionForm(str, Enum):
    """What a cited section string turned out to name."""

    SECTION = "section"
    """One section, found in the Code."""

    RANGE = "range"
    """A span of sections, both endpoints found in the Code."""

    ABSENT = "absent"
    """One section, and the Code has no such section."""

    UNRESOLVED = "unresolved"
    """Absent as written, and shaped like scanning damage rather than a claim.

    Never report this as a fabricated statute. See the module docstring.
    """


@dataclass(frozen=True, slots=True)
class SectionVerdict:
    """What one cited section resolved to, and whether the law is in force."""

    title: str
    written: str
    form: SectionForm
    sections: tuple[str, ...] = ()
    """The section or sections the citation names, empty if none was found."""
    not_in_force: tuple[tuple[str, ProvisionStatus], ...] = ()
    """Named sections the Code marks repealed, omitted, renumbered or transferred."""

    @property
    def is_defect(self) -> bool:
        """Whether this is something to report against the filing.

        An unresolved section is deliberately not a defect. It is a limit of
        this checker rather than a finding about the citation.
        """
        return self.form is SectionForm.ABSENT or bool(self.not_in_force)


def resolve_section(index: UsCodeIndex, title: str, section: str) -> SectionVerdict:
    """Decide what a cited section names, then report on the law it names."""
    written = section.strip()
    direct = index.lookup(title, written)
    if direct.exists:
        return _verdict(index, title, written, SectionForm.SECTION, (direct.section,))

    span = _as_range(index, title, written)
    if span is not None:
        return _verdict(index, title, written, SectionForm.RANGE, span)

    form = SectionForm.UNRESOLVED if _MIXED_ALPHANUMERIC.match(written) else SectionForm.ABSENT
    return SectionVerdict(title=str(title), written=written, form=form)


def _verdict(
    index: UsCodeIndex,
    title: str,
    written: str,
    form: SectionForm,
    sections: tuple[str, ...],
) -> SectionVerdict:
    not_in_force = tuple(
        (section, result.status)
        for section in sections
        for result in (index.lookup(title, section),)
        if result.exists and result.status is not None
    )
    return SectionVerdict(
        title=str(title),
        written=written,
        form=form,
        sections=sections,
        not_in_force=not_in_force,
    )


def _as_range(index: UsCodeIndex, title: str, section: str) -> tuple[str, ...] | None:
    """Read a hyphenated section as a span, but only if the Code agrees it is one.

    Returns the sections the span covers, or ``None`` if this is not a range.
    Requiring both endpoints to exist is what keeps a real hyphenated section
    out of here: `2000e-2` is found by the direct lookup and never gets this
    far, and a hyphenated string whose endpoints are not both real sections is
    absent rather than silently reinterpreted.
    """
    match = _HYPHENATED.match(section)
    if match is None:
        return None
    start, end = match.group("start"), _expand_abbreviated(match.group("start"), match.group("end"))
    if end is None or not index.lookup(title, start).exists or not index.lookup(title, end).exists:
        return None
    return _enumerate(start, end)


def _expand_abbreviated(start: str, end: str) -> str | None:
    """Write out a Bluebook-abbreviated second number: 2201-02 means 2201-2202.

    The abbreviation drops the leading digits the two numbers share, so they
    are restored from the start. An end that is already at least as long as the
    start is not abbreviated and is returned unchanged.
    """
    if not _NUMERIC.match(start) or not _NUMERIC.match(end):
        return end if _NUMERIC.match(end) else None
    if len(end) >= len(start):
        return end
    expanded = start[: len(start) - len(end)] + end
    return expanded if int(expanded) > int(start) else None


def _enumerate(start: str, end: str) -> tuple[str, ...]:
    """Every section a range covers, or just its endpoints if it is a long one.

    A range is written to cover the sections between its endpoints, and the
    ones in between are worth checking too -- `25 U.S.C. §§ 1301-1304` names
    four. A span like `29 U.S.C. §§ 2601-2654` is a filing pointing at a whole
    act, where enumerating every number would assert that each one exists and
    the Code frequently leaves gaps. Beyond `MAX_ENUMERATED_RANGE` only the
    endpoints are reported.
    """
    if not (_NUMERIC.match(start) and _NUMERIC.match(end)):
        return (start, end)
    first, last = int(start), int(end)
    if last - first + 1 > MAX_ENUMERATED_RANGE:
        return (start, end)
    return tuple(str(number) for number in range(first, last + 1))


def listed_sections(text: str, *, citation_start: int, citation_end: int) -> tuple[str, ...]:
    """The further sections a plural citation lists after the one it captured.

    `28 U.S.C. §§ 1331, 1332, 1441, and 1446` names four sections. eyecite's
    pattern ends at the first, so the other three are never extracted and never
    checked -- they are not reported wrongly, they are absent from the count
    entirely. Across the two corpora that is 24 distinct sections named only
    inside such a list, which puts the statute total at 625 rather than 601 and
    the share actually found at 96%.

    Reading a list is licensed by the plural marker inside the citation's own
    text, so a single `§` followed by a comma is left alone. Reading stops at
    the first thing that is not another section number, which is what keeps
    `§§ 1331, 1332, and the rules thereunder` from swallowing prose.
    """
    if not _PLURAL_MARKER.search(text[citation_start:citation_end]):
        return ()
    found: list[str] = []
    position = citation_end
    while match := _NEXT_LISTED.match(text, position):
        found.append(match.group("section"))
        position = match.end()
    return tuple(found)
