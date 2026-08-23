"""An offline reporter index built from the Caselaw Access Project's static files.

The pipeline asks CourtListener whether a case sits at a volume and page. When
the answer is no, nothing more can be said: the free record is incomplete, so an
absence is not evidence the citation was invented. That is the right rule and it
leaves a large bucket of citations with no verdict at all.

The Caselaw Access Project publishes Harvard's digitisation of the printed
reporters as plain static files at ``static.case.law`` -- no API key, no rate
limit, no account. Each volume carries a ``CasesMetadata.json`` listing every
case in it with its name, its court, its decision date, its **first and last
page**, and its official and parallel citations. That last pair is what this
module is for.

Knowing the page *range* of every case in a volume lets a different question be
asked. A lookup asks "is there a case at page 691?"; this index asks "what
covers page 691?", and a page that falls inside a case rather than starting one
is positive evidence that the locator is wrong.

Swept over the 3,138 case citations in the 1,300 annotated excerpts, the index
could answer for 2,622 of them (84%), and **109 name a page inside a case rather
than the page it begins on**. Against the human annotations, 66 of those 109
(61%) carry a defect label, against a corpus base rate of 10% -- and every one
of the 66 is labelled `case_name_mismatch`, none `wrong_pincite` or `misquote`.

**Two things stop that from being a precision figure, and both matter.**

*The corpus is defect-injected, and the check may be detecting the injector.*
A `case_name_mismatch` there appears to have been made by pairing a case name
with a wrong page number, and a wrong page number lands mid-case at whatever
rate mid-case pages occur -- which is what this detects. Of the 160 labelled
occurrences that could be joined, 66 sit inside a case, 47 fall in a gap, and 39
start a case. A borrowed real citation would always start a case, so the
injection is perturbing digits rather than borrowing. This therefore measures
the index against that generator, not against organic citation error.

*A short form written without "at" is indistinguishable from a wrong first
page.* `*Chevron*, 467 U.S. 842-43` and `Kimbrough, 552 U.S. 101-02` are pin
cites into cases the brief introduced earlier; eyecite reads them as full
citations because no `at` separates the page. The index then correctly reports
a mid-case page, and it is not a defect. Roughly half the 15 findings whose
case name *agrees* with the covering case are this. **Anything built on this
outcome has to establish that the citation is not a short form of a case
already introduced, which is a document-level question the index cannot see.**

**What survives is real, and it is unlabelled.** The other half of those 15 are
genuine first-page errors in real briefs that no annotator marked:
`Brady v. United States, 397 U.S. 757` (the case starts at 742),
`Medtronic v. Lohr, 518 U.S. 480` (470), `City of Canton v. Harris, 489 U.S.
379` (378), `Sherar v. Cullen, 481 F. 2d 946` (945). The name agrees, both
parties are present, and the page is simply wrong.

**And a lookup service does not simply miss these.** For 17 of 24 cross-checked
on another corpus, CourtListener resolved the citation -- to exactly the case
the archive says covers the page. `491 F.2d 56` came back as *United States v.
Melton*, whose own citation is `491 F.2d 45`. It normalises a mid-case page to
its covering case and reports the citation sound, so these are invisible to it
rather than unanswered by it.

Two limits, both structural rather than incidental:

**The archive ends around 2020.** Volume 157 is the last A.D.3d, and
``587 U.S.`` is not there. A recent citation gets ``VOLUME_UNAVAILABLE``, which
is a statement about this index and never about the citation.

**A page range is the printed page, not the opinion's own numbering.** A case
spanning 690 to 693 covers four printed pages; the index says the cited page
falls within the case, and says nothing about whether the proposition is on it.

**What may be concluded, and what may not.** The one claim this index supports
is narrow: *no case begins at this volume and page*. That is safe where a case
demonstrably covers the page, because a case the archive is missing leaves a
**gap** rather than being absorbed by its neighbour -- ``last_page`` is
recorded per case, not derived from where the next one starts, and 0.9% of
adjacent pairs do leave a gap, which is how that is known. A page in a gap
returns ``NO_CASE_COVERS_IT`` and concludes nothing.

It does not support "the correct first page is N". The covering case need not
be the one the filing meant, and in the corpus it never is: in all 27 findings
the name the filing wrote disagrees with the case covering the page.

**Coverage is 57% of the corpus** and the rest divides cleanly. A third of all
citations name a reporter the archive does not publish, which is mostly Westlaw
and LEXIS -- not reporters at all -- plus `F.4th`, which began after the archive
stopped. Eleven per cent name a volume outside what is published, most of it
after the last volume but 35 citations *before the first*: the archive holds
only `S. Ct.` volumes 134 to 140 and `L. Ed. 2d` 176 to 181.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "BASE_URL",
    "CapIndex",
    "PageOutcome",
    "PageVerdict",
    "reporter_slug",
    "volume_metadata_url",
]

BASE_URL = "https://static.case.law"

# The host refuses the default urllib User-Agent with a 403 while serving the
# same URL to a browser-shaped one. This is its bot rule rather than an access
# control -- the files are published for bulk use -- so the client identifies
# itself honestly instead of pretending to be a browser.
USER_AGENT = "mellea-lrc/0.1 (legal citation research; +https://github.com/gt-csse/mellea-lrc)"

FETCH_TIMEOUT_SECONDS = 120


class PageOutcome(str, Enum):
    """What the index can say about one volume-and-page."""

    STARTS_A_CASE = "starts_a_case"
    """A case begins on exactly this page. The locator is well formed."""

    INSIDE_A_CASE = "inside_a_case"
    """A case covers this page but begins on an earlier one.

    Positive evidence that the locator names the wrong first page -- most often
    a pin cite written where the first page belongs. The case that covers it is
    reported, so the claim can be checked against the right case rather than
    abandoned.
    """

    NO_CASE_COVERS_IT = "no_case_covers_it"
    """Nothing in the volume covers this page.

    Not evidence of fabrication, as a matter of logic: a gap can be a case the
    archive is missing, and this index is one archive with a known end date.

    Empirically it is not silent, and the gap between those two facts should be
    treated with care. On the annotated corpus 46% of the citations landing in
    a gap carry a defect label, against a base rate of 10% -- nearly as
    predictive as sitting inside a case. That is a reason to look, and not a
    licence to report: the same injection artefact described in the module
    docstring explains it just as well.
    """

    VOLUME_UNAVAILABLE = "volume_unavailable"
    """The archive does not hold this volume, usually because it is too recent.

    A statement about the index, never about the citation.
    """

    AMBIGUOUS_PAGE = "ambiguous_page"
    """More than one case is recorded as occupying this page.

    Cases share a page routinely -- one ends partway down and the next begins
    -- and the archive records that by letting spans touch. What this outcome
    marks is the other thing: spans that genuinely overlap, so the archive
    does not agree with itself about which case the page belongs to. About 1.5%
    of adjacent pairs are like that.

    Nothing may be concluded. Saying a page sits inside a case means nothing if
    a second case claims it, and this is the shape a volume takes when its
    recorded pages are wrong in bulk -- so it also catches the scanned-page
    problem that :func:`_printed_first_page` corrects, independently of that
    correction.
    """


@dataclass(frozen=True, slots=True)
class CapCase:
    """One case as the archive records it."""

    name: str
    first_page: int
    last_page: int
    decision_date: str
    court: str
    citations: tuple[str, ...]

    def covers(self, page: int) -> bool:
        """Whether this case occupies the given printed page."""
        return self.first_page <= page <= self.last_page


@dataclass(frozen=True, slots=True)
class PageVerdict:
    """What the archive says about one cited volume and page."""

    reporter: str
    volume: str
    page: str
    outcome: PageOutcome
    cases: tuple[CapCase, ...] = ()
    """Every case the archive puts at this page.

    More than one when several begin on the same page, which is ordinary: a
    reporter starts a new case partway down the page the last one ended on, and
    a one-page disposition can sit between two longer opinions. `963 F.2d 1258`
    begins both `United States v. Fine`, which occupies that page alone, and
    `Ferdik v. Bonzelet`, which runs to 1264.

    Picking one of those arbitrarily is how a correct citation gets contradicted:
    a filing citing Ferdik was told the page belongs to Fine. A caller comparing
    case names has to be satisfied by **any** of them.
    """

    @property
    def case(self) -> CapCase | None:
        """The first case at this page, for callers that need only one."""
        return self.cases[0] if self.cases else None

    @property
    def contradicts_locator(self) -> bool:
        """Whether this is positive evidence that the cited page is wrong.

        True only for a page that sits inside a case rather than starting one.
        An absent page and an unavailable volume both say nothing, and must not
        be reported as defects.
        """
        return self.outcome is PageOutcome.INSIDE_A_CASE


def reporter_slug(reporter: str, known: Iterable[str]) -> str | None:
    """Map a citation's reporter to the archive's directory name.

    The rule the archive follows is that a period *inside* an abbreviation
    closes up while a space *between* abbreviations becomes a dash. So ``F.2d``
    is ``f2d`` and ``A.D.3d`` is ``ad3d``, while ``F. Supp.`` is ``f-supp`` and
    ``N.C. App.`` is ``nc-app``. Splitting on whitespace before removing
    periods gets all four; treating every period as a space gets ``n-c-app``
    and finds nothing.

    The all-joined and all-dashed forms are still tried afterwards, because one
    rule derived from a sample is not a guarantee about 401 directory names --
    and it is not: three reporters in this project's corpora need
    :data:`SLUG_ALIASES`, which is checked first. Returns ``None`` when no
    variant is published, which is the answer for a vendor identifier like
    ``WL`` that is not a reporter at all, and for a reporter that began after
    the archive stopped, like ``F.4th``.
    """
    known = set(known)
    alias = SLUG_ALIASES.get(reporter.replace("’", "'").strip())
    if alias is not None and alias in known:
        return alias
    cleaned = reporter.replace("’", "'").replace("'", "").strip().lower()
    tokens = [token.replace(".", "") for token in cleaned.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    flattened = cleaned.replace(".", " ").split()
    for candidate in ("-".join(tokens), "".join(tokens), "".join(flattened), "-".join(flattened)):
        if candidate in known:
            return candidate
    return None


# Reporters the rule above does not reach, because the archive's own naming is
# not consistent. `N.Y.2d` becomes `ny-2d` with a dash the rule cannot predict,
# `N.C.App.` written closed up gives `ncapp` where the archive has `nc-app`,
# and `Fed. Appx.` is filed under the modern `f-appx`. Each verified against
# the published directory listing rather than guessed.
SLUG_ALIASES = {
    "N.Y.2d": "ny-2d",
    "N.Y. 2d": "ny-2d",
    "N.C.App.": "nc-app",
    "Fed. Appx.": "f-appx",
    "Fed. App'x": "f-appx",
    "Fed.Appx.": "f-appx",
    "Fed.App.": "f-appx",
}


def volume_metadata_url(slug: str, volume: str) -> str:
    """The archive's URL for one volume's case index."""
    return f"{BASE_URL}/{slug}/{volume}/CasesMetadata.json"


@dataclass
class CapIndex:
    """Volume indexes read from a local directory, fetched on demand.

    ``cache_dir`` holds one JSON file per volume, so a run that has fetched a
    volume once never fetches it again and an offline run works entirely from
    what is already there. Set ``allow_fetch=False`` to guarantee that no
    network call is made.
    """

    cache_dir: Path
    allow_fetch: bool = True
    _volumes: dict[tuple[str, str], list[CapCase] | None] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._volumes = {}

    def page(self, slug: str, volume: str, page: str) -> PageVerdict:
        """Say what the archive holds at one volume and page."""
        cases = self._volume(slug, volume)
        if cases is None:
            return PageVerdict(slug, volume, page, PageOutcome.VOLUME_UNAVAILABLE)
        if not page.isdigit():
            # A star page or a paragraph number is not a printed page, so the
            # range comparison below would be meaningless rather than wrong.
            return PageVerdict(slug, volume, page, PageOutcome.NO_CASE_COVERS_IT)
        number = int(page)
        starting = tuple(case for case in cases if case.first_page == number)
        if starting:
            return PageVerdict(slug, volume, page, PageOutcome.STARTS_A_CASE, starting)
        covering = tuple(case for case in cases if case.covers(number))
        if len(covering) > 1:
            return PageVerdict(slug, volume, page, PageOutcome.AMBIGUOUS_PAGE)
        if covering:
            return PageVerdict(slug, volume, page, PageOutcome.INSIDE_A_CASE, covering)
        return PageVerdict(slug, volume, page, PageOutcome.NO_CASE_COVERS_IT)

    def _volume(self, slug: str, volume: str) -> list[CapCase] | None:
        key = (slug, volume)
        if key not in self._volumes:
            self._volumes[key] = self._load(slug, volume)
        return self._volumes[key]

    def _load(self, slug: str, volume: str) -> list[CapCase] | None:
        path = self.cache_dir / f"{slug}-{volume}.json"
        if not path.exists():
            if not self.allow_fetch:
                return None
            payload = _fetch(volume_metadata_url(slug, volume))
            if payload is None:
                return None
            path.write_bytes(payload)
        return _parse(json.loads(path.read_text(encoding="utf-8")), volume)

    def load_file(self, slug: str, volume: str, path: Path | str) -> None:
        """Register a volume index already on disk, for tests and offline runs."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self._volumes[(slug, volume)] = _parse(payload, volume)


def _fetch(url: str) -> bytes | None:
    """Fetch one volume index, or ``None`` if the archive does not hold it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


# A citation for this volume, e.g. "377 U.S. 408" in volume 377. The page is
# what the printed reporter numbered it, which is not always what `first_page`
# holds -- see _printed_first_page.
_CITE_PAGE = re.compile(r"^(?P<volume>\d+)\s+\S.*?\s(?P<page>\d+)$")


def _printed_first_page(entry: dict, volume: str, recorded: int) -> int:
    """The page the reporter printed this case on, not the page of the scan.

    In a few volumes ``first_page`` holds the physical page of the scanned
    book rather than the printed page number. Volume 377 of the United States
    Reports is one: *Missouri Pacific Railroad v. Elmore & Stahl* carries
    ``first_page`` 266 while its own citation is ``377 U.S. 134``, a constant
    offset of 132 running through the whole volume.

    Left uncorrected this is not a missed answer but a confident wrong one --
    ``377 U.S. 408`` was reported as sitting inside *United States v. Aluminum
    Co. of America*, which is a different case entirely. Anchoring on the page
    in the case's own citation for this volume fixes it; the span length from
    ``first_page`` to ``last_page`` is kept, since only the origin is wrong.

    Found across 686 volumes in four of them, and correcting it removed four
    false findings and created none.
    """
    for citation in entry.get("citations", ()):
        match = _CITE_PAGE.match(str(citation.get("cite", "")).strip())
        if match and match.group("volume") == volume:
            return int(match.group("page"))
    return recorded


def _parse(payload: list[dict], volume: str) -> list[CapCase]:
    cases = []
    for entry in payload:
        first, last = str(entry.get("first_page", "")), str(entry.get("last_page", ""))
        if not first.isdigit():
            continue
        if not last.isdigit():
            # A malformed last page occurs -- `Sher v. Johnson` carries
            # `1366-1376` -- and dropping the case for it is worse than not
            # knowing where it ends. The case disappears, its first page reads
            # as belonging to whatever ran up to it, and a correct citation is
            # contradicted. Treated as a single page instead, which understates
            # the span and never invents one.
            last = first
        court = entry.get("court") or {}
        printed = _printed_first_page(entry, volume, int(first))
        cases.append(
            CapCase(
                name=entry.get("name_abbreviation") or entry.get("name") or "",
                first_page=printed,
                last_page=printed + (int(last) - int(first)),
                decision_date=entry.get("decision_date") or "",
                court=court.get("name_abbreviation") or court.get("name") or "",
                citations=tuple(c["cite"] for c in entry.get("citations", []) if c.get("cite")),
            )
        )
    return cases
