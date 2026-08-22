"""Find citations a filing contradicts itself about.

Most checks in this project ask an archive whether a citation is right. This one
asks only whether the filing agrees with itself, so it needs no network, no
model, and no archive that might simply be missing the case.

The pattern it looks for is one case name carrying two different citations in
the same reporter series. A brief citing *Liu v. Noem* as both
`708 F. Supp. 3d 386` and `780 F. Supp. 3d 386` -- same page, same court, same
year, volumes differing by a transposed digit -- has made an error in one of
them, and that is established by reading the filing alone.

**Parallel citations are not this.** A case is routinely reported in several
places at once: *International Shoe Co. v. Washington* is `326 U.S. 310`,
`66 S. Ct. 154` and `90 L. Ed. 95`, all correct and all the same decision.
Those differ by *series*, which is why a clash only counts when two citations
share one. Across the two corpora here, 62 case names carry several citations
and 60 of them are parallel citations of exactly this kind; treating them as
errors would bury the two real ones.

**What the finding is, and is not.** It says the two citations cannot both be
right. It does not say which is wrong, and it must not be read as saying the
case does not exist -- both volumes exist, and one of them holds this case. An
inconsistency is a positive observation about the document, which is why it can
be reported without consulting anything.

One reporter is deliberately excluded. A Westlaw citation identifies an
*opinion* rather than a case, so one case genuinely carries several across its
procedural history, and a brief citing `2023 WL 5721594` and `2024 WL 1555496`
for the same parties is usually citing two rulings rather than contradicting
itself.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation

if TYPE_CHECKING:
    from mellea_lrc.extraction.citation_tree import CitationTree

# Series where one case legitimately carries several citations, so a clash
# inside them says nothing.
_PER_OPINION_SERIES = frozenset({"wl", "lexis", "usdistlexis", "usapplexis"})
_NOT_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True, slots=True)
class InconsistentCitation:
    """One case name given two citations in the same reporter series."""

    plaintiff: str
    defendant: str
    reporter: str
    citations: tuple[tuple[str, str], ...]
    """Each (volume, page) the filing gave for this case in this series."""

    @property
    def description(self) -> str:
        """A one-line statement of what the filing said twice."""
        given = " and ".join(f"{volume} {self.reporter} {page}" for volume, page in self.citations)
        return f"{self.plaintiff} v. {self.defendant} is cited as {given}"


def inconsistent_citations(tree: CitationTree) -> tuple[InconsistentCitation, ...]:
    """Every case the filing cites twice, differently, within one reporter series."""
    # keyed by the normalized parties and series, holding the names as written
    grouped: dict[tuple[str, str, str], tuple[str, str, str, set[tuple[str, str]]]] = {}
    for authority in tree.authorities:
        citation = authority.root.citation
        if not isinstance(citation, FullCaseCitation):
            continue
        plaintiff, defendant, reporter = citation.plaintiff, citation.defendant, citation.reporter
        # Both party names are required. Without them two different cases can
        # share a name fragment and be reported as one contradiction.
        if not plaintiff or not defendant or not reporter:
            continue
        series = _normalize(reporter)
        if series in _PER_OPINION_SERIES:
            continue
        key = (_normalize(plaintiff), _normalize(defendant), series)
        entry = grouped.setdefault(key, (plaintiff, defendant, reporter, set()))
        entry[3].add((citation.volume or "", citation.page or ""))

    return tuple(
        InconsistentCitation(
            plaintiff=plaintiff,
            defendant=defendant,
            reporter=reporter,
            citations=tuple(sorted(pairs)),
        )
        for plaintiff, defendant, reporter, pairs in grouped.values()
        if len(pairs) > 1
    )


def _normalize(value: str) -> str:
    """Compare names and series without punctuation or spacing."""
    return _NOT_ALNUM.sub("", value.lower())
