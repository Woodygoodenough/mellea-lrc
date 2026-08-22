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

Knowing the page *range* of every case in a volume answers a question a lookup
service cannot. A lookup asks "is there a case at page 691?" and returns
nothing. This index asks "what covers page 691?" and finds that *United States
v. Smith* runs from 690 to 693 -- so the page is real, the case is real, and the
citation names a page inside the case rather than the page it starts on. That is
positive evidence about a specific defect, not an absence.

Measured against the citations the locator probe left unresolved, of the four
whose volume this index holds:

* ``489 U.S. 379`` is inside *City of Canton v. Harris*, which starts at 378.
* ``54 F.3d 691`` is inside *United States v. Smith*, which starts at 690.
* ``481 F. 2d 946`` is inside *Sherar v. Cullen*, which starts at 945 -- and the
  filing's own text names *Sherar v. Cullen*, so only the page is wrong.
* ``243 F.R.D. 604`` is covered by nothing in the volume, which the index
  reports as absent rather than as a defect, for the same reason a CourtListener
  miss is not one.

Two limits, both structural rather than incidental:

**The archive ends around 2020.** Volume 157 is the last A.D.3d, and
``587 U.S.`` is not there. A recent citation gets ``VOLUME_UNAVAILABLE``, which
is a statement about this index and never about the citation.

**A page range is the printed page, not the opinion's own numbering.** A case
spanning 690 to 693 covers four printed pages; the index says the cited page
falls within the case, and says nothing about whether the proposition is on it.
"""

from __future__ import annotations

import json
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

    Not evidence of fabrication. This index is one archive with a known end
    date, so its silence means what a CourtListener miss means: nothing.
    """

    VOLUME_UNAVAILABLE = "volume_unavailable"
    """The archive does not hold this volume, usually because it is too recent.

    A statement about the index, never about the citation.
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
    case: CapCase | None = None
    """The case that starts on or covers the page, when there is one."""

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

    The archive is not consistent about how it closes up spaces -- ``F.2d`` is
    ``f2d`` and ``F. Supp.`` is ``f-supp`` -- so both forms are tried against
    the set of names the archive actually publishes, along with the
    apostrophe-stripped forms needed for ``F. App'x``. Returns ``None`` when no
    variant is published, which is the answer for a vendor identifier like
    ``WL`` that is not a reporter at all.
    """
    known = set(known)
    words = reporter.replace(".", " ").replace("’", "'").strip().lower().split()
    joined, dashed = "".join(words), "-".join(words)
    for candidate in (joined, dashed, joined.replace("'", ""), dashed.replace("'", "")):
        if candidate in known:
            return candidate
    return None


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
        starting = next((case for case in cases if case.first_page == number), None)
        if starting is not None:
            return PageVerdict(slug, volume, page, PageOutcome.STARTS_A_CASE, starting)
        covering = next((case for case in cases if case.covers(number)), None)
        if covering is not None:
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
        return _parse(json.loads(path.read_text(encoding="utf-8")))

    def load_file(self, slug: str, volume: str, path: Path | str) -> None:
        """Register a volume index already on disk, for tests and offline runs."""
        self._volumes[(slug, volume)] = _parse(json.loads(Path(path).read_text(encoding="utf-8")))


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


def _parse(payload: list[dict]) -> list[CapCase]:
    cases = []
    for entry in payload:
        first, last = str(entry.get("first_page", "")), str(entry.get("last_page", ""))
        if not (first.isdigit() and last.isdigit()):
            continue
        court = entry.get("court") or {}
        cases.append(
            CapCase(
                name=entry.get("name_abbreviation") or entry.get("name") or "",
                first_page=int(first),
                last_page=int(last),
                decision_date=entry.get("decision_date") or "",
                court=court.get("name_abbreviation") or court.get("name") or "",
                citations=tuple(c["cite"] for c in entry.get("citations", []) if c.get("cite")),
            )
        )
    return cases
