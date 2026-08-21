"""Group a document's citations by the authority they all refer to.

A filing does not cite an authority once. It cites it in full, then returns to
it as `Id. at 570`, `550 U.S. at 563`, or by party name -- and each of those
return visits usually names a **different page** and attaches a **different
proposition** to it. Validating only the full citations therefore checks one
claim per authority and skips every other claim made about it, which is the
larger part of what a brief actually asserts.

The tree makes that structure explicit. Every citation resolves, transitively,
to the full citation that introduced its authority; the authority is identified
once and that work is shared; and each occurrence keeps its own pin cite, so it
is its own checkable claim about its own page rather than an alias of the first
one.

Two properties are what make this worth having rather than merely tidy:

- **Identity is resolved once per authority, not once per occurrence.** Ten
  references to one case cost one lookup.
- **Pinpoint claims multiply.** An authority cited at pages 563, 570 and 578 is
  three distinct claims about three distinct pages, each verifiable on its own
  and each capable of being wrong on its own.

Resolution here is eyecite's, followed transitively: `Id.` may point at a short
form that points at the full citation. Nothing is invented -- a citation eyecite
could not attribute is reported as unattributed rather than guessed at, because
attaching a claim to the wrong authority would check it against the wrong page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument

# A chain longer than this is a resolution loop or a pathology, not a brief.
MAX_RESOLUTION_DEPTH = 24


@dataclass(frozen=True, slots=True)
class CitationOccurrence:
    """One place a document refers to an authority, with the page it names."""

    citation: ExtractedCitation
    depth: int
    pin_cite: str | None

    @property
    def citation_id(self) -> str:
        """The extracted citation's identifier."""
        return self.citation.citation_id

    @property
    def is_root(self) -> bool:
        """Whether this occurrence is the full citation that introduced the authority."""
        return self.depth == 0


@dataclass(frozen=True, slots=True)
class Authority:
    """One cited authority and every place the document refers to it."""

    root: ExtractedCitation
    occurrences: tuple[CitationOccurrence, ...]

    @property
    def authority_id(self) -> str:
        """The identifier of the full citation that introduced this authority."""
        return self.root.citation_id

    @property
    def pin_cites(self) -> tuple[str, ...]:
        """Every distinct pin cite claimed for this authority, in order of appearance.

        This is the count that matters for verification: it is how many separate
        claims about separate pages the document makes about one case.
        """
        seen: dict[str, None] = {}
        for occurrence in self.occurrences:
            if occurrence.pin_cite:
                seen.setdefault(occurrence.pin_cite, None)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class CitationTree:
    """Every authority a document cites, and what could not be attributed to one."""

    authorities: tuple[Authority, ...]
    unattributed: tuple[ExtractedCitation, ...]

    @property
    def occurrence_count(self) -> int:
        """How many citation occurrences were attributed to an authority."""
        return sum(len(authority.occurrences) for authority in self.authorities)

    @property
    def pinpoint_claim_count(self) -> int:
        """How many distinct page-level claims the document makes.

        Larger than the number of authorities whenever a brief returns to a case
        for a second proposition, which is most of the time.
        """
        return sum(len(authority.pin_cites) for authority in self.authorities)


def build_citation_tree(document: ExtractedDocument) -> CitationTree:
    """Group a document's citations under the authorities they refer to."""
    by_id = {item.citation_id: item for item in document.citations}
    roots: dict[str, list[CitationOccurrence]] = {}
    unattributed: list[ExtractedCitation] = []

    for item in document.citations:
        root_id, depth = _resolve_root(item, by_id)
        root = by_id.get(root_id) if root_id else None
        if root is None or not isinstance(root.citation, FullCaseCitation):
            unattributed.append(item)
            continue
        roots.setdefault(root_id or "", []).append(
            CitationOccurrence(citation=item, depth=depth, pin_cite=_pin_cite(item))
        )

    authorities = tuple(
        Authority(root=by_id[root_id], occurrences=tuple(occurrences))
        for root_id, occurrences in roots.items()
    )
    return CitationTree(authorities=authorities, unattributed=tuple(unattributed))


def _resolve_root(
    item: ExtractedCitation,
    by_id: Mapping[str, ExtractedCitation],
) -> tuple[str | None, int]:
    """Follow `resolves_to` to the citation that introduced the authority.

    `Id.` often points at a short form rather than at the full citation, so the
    chain is walked rather than read once. A cycle or an implausible chain
    yields no root, which sends the citation to `unattributed` -- guessing would
    attach a page claim to the wrong case.
    """
    current = item
    seen = {current.citation_id}
    for depth in range(MAX_RESOLUTION_DEPTH):
        target = current.resolves_to
        if target is None:
            return (current.citation_id, depth)
        if target in seen:
            return (None, depth)
        following = by_id.get(target)
        if following is None:
            return (None, depth)
        seen.add(target)
        current = following
    return (None, MAX_RESOLUTION_DEPTH)


def _pin_cite(item: ExtractedCitation) -> str | None:
    pin = getattr(item.citation, "pin_cite", None)
    return str(pin) if pin else None


def summarize(trees: Sequence[CitationTree]) -> dict[str, int]:
    """Count what a set of documents' trees contain, for reporting."""
    return {
        "authorities": sum(len(tree.authorities) for tree in trees),
        "occurrences": sum(tree.occurrence_count for tree in trees),
        "pinpoint_claims": sum(tree.pinpoint_claim_count for tree in trees),
        "unattributed": sum(len(tree.unattributed) for tree in trees),
    }
