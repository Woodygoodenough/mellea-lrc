"""Existence and in-force lookup against the bulk United States Code XML.

The Office of the Law Revision Counsel (OLRC) publishes each "release point"
of the Code as USLM XML at uscode.house.gov, one zip per title plus a combined
zip of all 54. A release point is not a single title's currency: the site
republishes every title against the same cutoff public law even when a given
title has not changed, so the zip for an untouched title is still current as
of that release point. The download URL shape is::

    https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{law}/xml_usc{title:02d}@{congress}-{law}.zip

``{congress}-{law}`` is the release-point identifier shown on the site (for
example ``119-102not101``); :func:`title_zip_url` builds this URL, and
:data:`DEFAULT_RELEASE_POINT` records the point this module was built and
measured against. The full all-titles archive was not used: at roughly a
gigabyte of XML for 54 titles, downloading only the titles a caller actually
needs (this project's filings cite title 28 and title 42 almost exclusively)
keeps a `uv run pytest` fixture-backed test suite fast and offline, while
still leaving :meth:`UsCodeIndex.load_xml` able to load as many titles as a
caller wants.

Every USLM ``<section>`` carries an ``identifier`` like ``/us/usc/t28/s636``
and, when the section is not current law, a ``status`` attribute --
``repealed``, ``omitted``, ``renumbered``, or ``transferred`` -- covering the
same ground as the visible ``[Repealed.]`` heading text but without needing to
parse prose. A missing ``status`` attribute means the section is in force.
That single attribute is what this module reads; it does not parse section
text, notes, or history.

Three identifier shapes need handling, all of them from real title 28 and
title 42 data, not hypothetical:

* A single identifier, the common case: ``/us/usc/t28/s636``.
* A space-separated list on one ``<section>``, for a joint repeal:
  ``/us/usc/t28/s570 /us/usc/t28/s571`` repeals both 570 and 571 with one
  entry, and each identifier in the list is registered individually.
* A ``"..."`` range on one ``<section>``, for a block repeal:
  ``/us/usc/t28/s211...216`` covers every section OLRC would have numbered
  between 211 and 216, most of which never got their own ``<section>``
  element once the block was collapsed. Membership is decided by
  :func:`_natural_key`, a natural sort (numeric run, then letter run,
  compared numerically within each run) rather than string comparison,
  because plain string order would put ``"...15a"`` after ``"...9"`` and
  ``"e-10"`` before ``"e-9"``.

OLRC's own export corrupts one more thing worth naming: some identifiers use
an en dash (U+2013) where a citation would use a plain hyphen, e.g. title 42
section 2000e-2 is indexed as ``/us/usc/t42/s2000e`` + U+2013 + ``2`` for what
every court filing writes as ``42 U.S.C. § 2000e-2``.
:func:`_normalize_section` folds dash variants to a plain hyphen on both the
indexed and the queried side so that mismatch is invisible to callers.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from collections.abc import Iterable

# The release point this module was built and measured against. OLRC does not
# expose a "latest" alias -- the download page resolves one via client-side
# JavaScript -- so a caller who wants a newer release must find its identifier
# on https://uscode.house.gov/download/download.shtml and pass it explicitly.
DEFAULT_RELEASE_POINT = "119-102not101"

_USLM_NS = "http://xml.house.gov/schemas/uslm/1.0"
_SECTION_TAG = f"{{{_USLM_NS}}}section"

# Every dash variant OLRC's export has been observed to use in an identifier,
# folded to a plain hyphen so a citation's ASCII hyphen still matches:
# hyphen, non-breaking hyphen, figure dash, en dash, em dash, minus sign.
_DASH_CODEPOINTS = "‐‑‒–—−"
_DASH_TRANSLATION = str.maketrans(dict.fromkeys(_DASH_CODEPOINTS, "-"))

# A USLM section identifier, e.g. "/us/usc/t28/s636" or "/us/usc/t42/s2000e-2".
_IDENTIFIER_RE = re.compile(r"^/us/usc/t(?P<title>\d+[A-Za-z]?)/s(?P<section>[^/\s]+)$")

# Splits a section identifier into alternating digit and non-digit runs, e.g.
# "2000e-16a" -> ["2000", "e-", "16", "a"], so _natural_key can compare the
# digit runs numerically instead of lexicographically.
_CHUNK_RE = re.compile(r"\d+|\D+")


def title_zip_url(title: int, *, release_point: str = DEFAULT_RELEASE_POINT) -> str:
    """Build the OLRC download URL for one title's USLM XML at a release point."""
    congress, _, law = release_point.partition("-")
    return (
        f"https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{law}"
        f"/xml_usc{title:02d}@{release_point}.zip"
    )


class ProvisionStatus(str, Enum):
    """The USLM ``status`` values OLRC has been observed to put on a section.

    Absence of a ``status`` attribute -- not a member here -- means in force;
    see :attr:`UscLookupResult.in_force`.
    """

    REPEALED = "repealed"
    OMITTED = "omitted"
    RENUMBERED = "renumbered"
    TRANSFERRED = "transferred"


@dataclass(frozen=True, slots=True)
class UscLookupResult:
    """Answer to one (title, section) existence-and-force query."""

    title: str
    section: str
    exists: bool
    in_force: bool
    status: ProvisionStatus | None


def _normalize_section(section: str) -> str:
    """Fold dash variants so an indexed identifier matches an ASCII-hyphen citation."""
    return section.strip().translate(_DASH_TRANSLATION)


def _natural_key(section: str) -> tuple[tuple[int, int | str], ...]:
    """Order a section identifier by its digit runs numerically, not lexicographically.

    Plain string comparison would place "15a" before "9" and "e-10" before
    "e-9", which breaks range-containment lookups (see module docstring). Each
    chunk is tagged 0-for-digits/1-for-letters so two chunks of different kinds
    never get compared against each other by ``int < str``.
    """
    return tuple((0, int(chunk)) if chunk.isdigit() else (1, chunk) for chunk in _CHUNK_RE.findall(section))


@dataclass(frozen=True, slots=True)
class _RangeEntry:
    """One "..." block-repeal identifier, kept as a containment range."""

    start_key: tuple[tuple[int, int | str], ...]
    end_key: tuple[tuple[int, int | str], ...]
    status: ProvisionStatus | None

    def contains(self, key: tuple[tuple[int, int | str], ...]) -> bool:
        return self.start_key <= key <= self.end_key


class UsCodeIndex:
    """An in-memory existence/status index built from one or more USLM titles.

    Nothing here fetches data over the network -- call :meth:`load_xml` with
    paths to files already on disk (a bare ``.xml`` file, or the ``.zip`` OLRC
    distributes containing exactly one). That keeps the test suite offline and
    fast: it loads a few hand-written sections from ``tests/fixtures/us_code``
    rather than the full multi-megabyte title downloads this module was
    measured against.
    """

    def __init__(self) -> None:
        self._sections: dict[str, dict[str, ProvisionStatus | None]] = {}
        self._ranges: dict[str, list[_RangeEntry]] = {}

    @classmethod
    def from_paths(cls, paths: Iterable[Path | str]) -> UsCodeIndex:
        """Build an index by loading each of the given USLM XML or zip files."""
        index = cls()
        for path in paths:
            index.load_xml(path)
        return index

    def load_xml(self, path: Path | str) -> None:
        """Load one title's sections from a USLM ``.xml`` file or its ``.zip``."""
        path = Path(path)
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = [name for name in archive.namelist() if name.endswith(".xml")]
                if len(members) != 1:
                    msg = f"expected exactly one .xml member in {path}, found {members}"
                    raise ValueError(msg)
                with archive.open(members[0]) as fileobj:
                    root = ET.parse(fileobj).getroot()
        else:
            root = ET.parse(path).getroot()
        self._index_root(root)

    def _index_root(self, root: ET.Element) -> None:
        for section in root.iter(_SECTION_TAG):
            identifier = section.get("identifier")
            if not identifier:
                continue
            status_attr = section.get("status")
            status = ProvisionStatus(status_attr) if status_attr else None
            # A joint repeal puts several identifiers on one <section>,
            # space-separated; the common case is a list of exactly one.
            for single_id in identifier.split():
                self._index_identifier(single_id, status)

    def _index_identifier(self, identifier: str, status: ProvisionStatus | None) -> None:
        match = _IDENTIFIER_RE.match(identifier)
        if match is None:
            return
        title = match.group("title")
        section_id = match.group("section")
        if "..." in section_id:
            start, _, end = section_id.partition("...")
            self._ranges.setdefault(title, []).append(
                _RangeEntry(
                    start_key=_natural_key(_normalize_section(start)),
                    end_key=_natural_key(_normalize_section(end)),
                    status=status,
                )
            )
        else:
            normalized = _normalize_section(section_id)
            self._sections.setdefault(title, {})[normalized] = status

    def lookup(self, title: int | str, section: str) -> UscLookupResult:
        """Answer whether ``title`` section ``section`` exists and is in force.

        A section counts as existing if OLRC has (or ever had) a ``<section>``
        element for it, whatever its current status -- a repealed section
        still exists, it is simply not in force. A title this index was never
        loaded for reports every section as not existing, since that is
        indistinguishable from a title with no matching section from the data
        this index has.
        """
        title_key = str(title)
        section_key = _normalize_section(section)
        by_section = self._sections.get(title_key, {})
        if section_key in by_section:
            status = by_section[section_key]
            return UscLookupResult(
                title=title_key,
                section=section_key,
                exists=True,
                in_force=status is None,
                status=status,
            )
        query_key = _natural_key(section_key)
        for entry in self._ranges.get(title_key, ()):
            if entry.contains(query_key):
                return UscLookupResult(
                    title=title_key,
                    section=section_key,
                    exists=True,
                    in_force=entry.status is None,
                    status=entry.status,
                )
        return UscLookupResult(
            title=title_key,
            section=section_key,
            exists=False,
            in_force=False,
            status=None,
        )
