"""Canonical citation representations shared across extraction and validation.

These are project-level citation classes. Eyecite citations are converted into
these canonical types before downstream validation and serialization.
"""

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, TypeAlias


class CitationKind(str, Enum):
    """Canonical citation type names used in annotation and serialization."""

    FULL_CASE = "FullCaseCitation"
    FULL_LAW = "FullLawCitation"
    FULL_JOURNAL = "FullJournalCitation"
    DOCKET = "DocketCitation"
    SHORT_CASE = "ShortCaseCitation"
    SUPRA = "SupraCitation"
    ID = "IdCitation"
    REFERENCE = "ReferenceCitation"
    UNKNOWN = "UnknownCitation"


# Full citations identify what they cite on their own; short citations
# generally need an antecedent before they can be validated. A docket citation
# belongs here on that test -- a docket number and its court name a case with
# no help from the text around them -- even though the reporter-keyed case
# search cannot look one up, which is a fact about that service and not about
# the citation.
FULL_CITATION_KINDS = frozenset(
    {
        CitationKind.FULL_CASE,
        CitationKind.FULL_LAW,
        CitationKind.FULL_JOURNAL,
        CitationKind.DOCKET,
    }
)


@dataclass(frozen=True, slots=True)
class FullCaseCitation:
    """Complete citation to a reported case."""

    kind: ClassVar[CitationKind] = CitationKind.FULL_CASE

    plaintiff: str | None = None
    defendant: str | None = None
    volume: str | None = None
    reporter: str | None = None
    page: str | None = None
    pin_cite: str | None = None
    extra: str | None = None
    year: str | None = None
    court: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class FullLawCitation:
    """Citation to a statute, regulation, or code section."""

    kind: ClassVar[CitationKind] = CitationKind.FULL_LAW

    volume: str | None = None
    reporter: str | None = None
    page: str | None = None
    pin_cite: str | None = None
    year: str | None = None
    publisher: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class FullJournalCitation:
    """Citation to a law review or journal article."""

    kind: ClassVar[CitationKind] = CitationKind.FULL_JOURNAL

    volume: str | None = None
    reporter: str | None = None
    page: str | None = None
    pin_cite: str | None = None
    year: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class DocketCitation:
    """A case identified by its docket number rather than by a reporter page.

    The court is not decoration here, it is half of the identifier: the same
    docket number exists in every district, and only the pair names a case. So
    both are on the citation, and a docket read without a court is not read at
    all.

    ``docket_number`` is kept as the filing wrote it, damage included --
    ``1:25cv-05745-RPK`` is a real citation in false-citation-bench, missing the
    hyphen its converter dropped. Normalizing it here would hide from a reader
    what the document actually says, which is the one thing a verification tool
    must not do.
    """

    kind: ClassVar[CitationKind] = CitationKind.DOCKET

    plaintiff: str | None = None
    defendant: str | None = None
    docket_number: str | None = None
    court: str | None = None
    """The courts-db identifier, e.g. ``nyed``."""
    court_name: str | None = None
    court_text: str | None = None
    """The court exactly as the filing wrote it, e.g. ``E.D.N.Y.``."""
    pin_cite: str | None = None
    year: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class ShortCaseCitation:
    """Subsequent reference using volume + reporter + pin cite."""

    kind: ClassVar[CitationKind] = CitationKind.SHORT_CASE

    volume: str | None = None
    reporter: str | None = None
    page: str | None = None
    pin_cite: str | None = None
    court: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class SupraCitation:
    """Reference using party name + supra."""

    kind: ClassVar[CitationKind] = CitationKind.SUPRA

    pin_cite: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class IdCitation:
    """Reference using Id. or Ibid."""

    kind: ClassVar[CitationKind] = CitationKind.ID

    pin_cite: str | None = None
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceCitation:
    """Bare party-name reference with no reporter information."""

    kind: ClassVar[CitationKind] = CitationKind.REFERENCE

    plaintiff: str | None = None
    defendant: str | None = None


@dataclass(frozen=True, slots=True)
class UnknownCitation:
    """Span that looks like a citation but cannot be parsed."""

    kind: ClassVar[CitationKind] = CitationKind.UNKNOWN


CanonicalCitation: TypeAlias = (
    FullCaseCitation
    | FullLawCitation
    | FullJournalCitation
    | DocketCitation
    | ShortCaseCitation
    | SupraCitation
    | IdCitation
    | ReferenceCitation
    | UnknownCitation
)


def citation_kind(citation: CanonicalCitation) -> CitationKind:
    """Return the canonical type name for a citation."""
    return citation.kind


def is_full_citation(citation: CanonicalCitation) -> bool:
    """Return True when the citation is a self-contained bibliographic cite."""
    return citation.kind in FULL_CITATION_KINDS
