"""Report a citation whose first page is wrong, without firing on short forms.

:mod:`~mellea_lrc.caselaw.cap_index` can say that a cited page falls inside a
case rather than starting it. That is not by itself a defect, and the reason is
a gap in how citations are parsed rather than anything about the archive.

A brief introduces a case in full and then returns to it by name::

    Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837, 842 (1984)
    ...
    Chevron, 467 U.S. 842-43

The second is a pin cite. Written *with* ``at`` -- ``467 U.S. at 842`` -- eyecite
types it as a ``ShortCaseCitation`` and nothing downstream mistakes it for a
locator. Written without, which is common, eyecite has no way to tell it from a
full citation and types it as one. The archive then correctly reports a
mid-case page, and a checker reading that as a defect accuses a brief of
miscitation for citing a case perfectly well.

Over the 109 mid-case citations in the annotated corpus, 15 have a case name
agreeing with the case that covers the page -- the only ones that could be
wrong-first-page defects at all, since a disagreeing name is a different
finding. **Eight of those 15 are short forms of this kind.** Suppressing them
is the whole job of this module.

Three tests, tried in order, each stronger than the one after it:

1. **The document cites the case correctly elsewhere.** If some other citation
   in the same document names the same volume, reporter and the page the case
   actually starts on, then this one is a later reference to it. This is the
   soundest test and it needs no judgement at all.
2. **The citation tree resolves it to a correctly-cited authority.** eyecite's
   own resolution, followed transitively, reaching a full citation at the real
   first page.
3. **The citation is not shaped like a full one.** A full citation names both
   parties and states a year; a short form names one party and no year. This is
   weaker than the first two and it is what carries the load on excerpts, where
   the case was introduced in text that is not present.

Tests 1 and 2 are what "join it to the citation tree" means, and on whole
filings they are the right mechanism. On the annotated corpus they fire only 5
times in 109, because it is excerpts and the case was usually introduced in
text that is not in the fragment. Test 3 carries the rest.

A fourth condition sits outside those three: **the case name has to agree**.
Where it does not, the citation names one case and the page belongs to
another, which is a wrong *name* rather than a wrong *page* -- a different
finding, and this check cannot tell which of the two is wrong. That is most of
the volume: 94 of the 109 have a disagreeing name, and every annotator label
on them is `case_name_mismatch`.

Together these take **109 mid-case citations down to 7 reported**, and the 7
are the ones a person reading the excerpts picks out.

It costs one known mistake, in the safe direction. ``Day v. AT&T Corp., 63
Cal. App.4th 325, 340 (1998)`` is a full citation with a wrong first page --
the case starts at 319 -- but the filing writes the name in emphasis markup as
``*Day v. AT&T Corp.*``, eyecite recovers only the defendant, and test 3 calls
it a short form. Missing a real defect is the direction this project prefers
to be wrong in; the other direction accuses a correct citation.

Of the 7 reported, 6 were checked back against the excerpt text by hand and
are plain first-page errors -- ``Brady v. United States, 397 U.S. 757`` where
the case starts at 742, ``Medtronic v. Lohr, 518 U.S. 480`` where it starts at
470. The seventh, ``G & S Holdings LLC v. Cont'l Cas. Co., 697 F.3d 534``, **is
unresolved, and the weight of evidence is now against the archive rather than
against the filing.** The archive gives that case a 30-page span, 514 to 544,
where the median in that volume is 10 and only 9 of its 112 cases reach 25;
its neighbours match ordinary usage exactly, *Naficy* at 504 and *S.C.
Johnson* at 544; and no case appears to be cited at 697 F.3d 514 anywhere. The
economical reading is that the archive's entry absorbed whatever occupied 514
to 533 and took its first page. Searching for either citation did not settle
it, so it stays a question -- but a caller should not report this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from mellea_lrc.caselaw.cap_index import PageOutcome, reporter_slug
from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.extraction.citation_tree import build_citation_tree
from mellea_lrc.validation.duplicate_clusters import name_covers, name_words

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mellea_lrc.caselaw.cap_index import CapCase, CapIndex
    from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument

__all__ = ["FirstPageFinding", "LaterReferenceEvidence", "check_first_pages"]


class LaterReferenceEvidence(str, Enum):
    """Why a mid-case page was taken to be a pin cite rather than a defect."""

    CITED_CORRECTLY_ELSEWHERE = "cited_correctly_elsewhere"
    """Another citation in the document names this case at the page it starts on."""

    RESOLVED_BY_THE_TREE = "resolved_by_the_tree"
    """Citation resolution reached a full citation at the page the case starts on."""

    NOT_SHAPED_LIKE_A_FULL_CITATION = "not_shaped_like_a_full_citation"
    """Only one party, or no year. A full citation carries both."""


@dataclass(frozen=True, slots=True)
class FirstPageFinding:
    """One citation whose page falls inside the case rather than starting it."""

    citation: ExtractedCitation
    case: CapCase
    """The case the archive says occupies the cited page."""
    later_reference: LaterReferenceEvidence | None
    """Set when this is a pin cite rather than a defect, saying how that was known."""
    name_agrees: bool = False
    """Whether the filing's case name is the name of the case covering the page."""

    @property
    def is_defect(self) -> bool:
        """Whether to report this as a wrong first page.

        Requires the name to agree. Where it does not, the citation names one
        case and the page belongs to another, which is a wrong *name* rather
        than a wrong *page* -- a different finding, reported by a different
        check, and this one has no way to tell which of the two is wrong. On
        the annotated corpus that distinction is most of the volume: of 109
        mid-case citations, 94 have a disagreeing name and every label on them
        is `case_name_mismatch`.
        """
        return self.later_reference is None and self.name_agrees

    @property
    def pages_early(self) -> int:
        """How far past the case's first page the citation lands."""
        return int(self.citation.citation.page or 0) - self.case.first_page


def check_first_pages(
    document: ExtractedDocument,
    index: CapIndex,
    *,
    known_reporters: Iterable[str],
) -> tuple[FirstPageFinding, ...]:
    """Find citations naming a page inside a case, and say which are pin cites.

    Every mid-case citation is returned, including the suppressed ones, so a
    caller can count what was set aside rather than only what survived.
    """
    known = set(known_reporters)
    correctly_cited = _pages_this_document_cites(document, known)
    roots = _authority_roots(document)

    findings: list[FirstPageFinding] = []
    for item in document.citations:
        citation = item.citation
        if not isinstance(citation, FullCaseCitation):
            continue
        slug = _slug_of(citation, known)
        if slug is None or not (citation.volume and citation.page):
            continue
        verdict = index.page(slug, citation.volume, citation.page)
        if verdict.outcome is not PageOutcome.INSIDE_A_CASE or verdict.case is None:
            continue
        findings.append(
            FirstPageFinding(
                citation=item,
                case=verdict.case,
                later_reference=_later_reference(item, verdict.case, slug, correctly_cited, roots, known),
                name_agrees=_names_the_same_case(verdict.case, citation),
            )
        )
    return tuple(findings)


def _later_reference(
    item: ExtractedCitation,
    case: CapCase,
    slug: str,
    correctly_cited: set[tuple[str, str]],
    roots: dict[str, ExtractedCitation],
    known: set[str],
) -> LaterReferenceEvidence | None:
    """Decide whether this mid-case page is a pin cite, and on what evidence."""
    citation = item.citation
    assert isinstance(citation, FullCaseCitation)
    real_first = (slug, str(case.first_page))
    if real_first in correctly_cited:
        return LaterReferenceEvidence.CITED_CORRECTLY_ELSEWHERE

    root = roots.get(item.citation_id)
    if root is not None and root.citation_id != item.citation_id:
        root_citation = root.citation
        if (
            isinstance(root_citation, FullCaseCitation)
            and _slug_of(root_citation, known) == slug
            and root_citation.page == str(case.first_page)
        ):
            return LaterReferenceEvidence.RESOLVED_BY_THE_TREE

    if not (citation.plaintiff and citation.defendant and citation.year):
        return LaterReferenceEvidence.NOT_SHAPED_LIKE_A_FULL_CITATION
    return None


def _names_the_same_case(case: CapCase, citation: FullCaseCitation) -> bool:
    """Whether the filing's case name is the covering case's, on both sides of the `v.`.

    Stricter than the comparison used to pick a case off a crowded page, and it
    has to be. `United States v. Lo` reduces to the words `united` and `states`
    -- a two-letter surname carries none -- and those two appear in every
    `United States v. ...` on the page, so the looser rule matched it against
    *United States v. Zamoran-Coronel* and reported a wrong first page for a
    citation to a different case entirely.

    Requiring each party to contribute a matched word removes that, because a
    government party alone can no longer carry a match. It costs the citations
    whose second party survives normalisation to nothing, which are declined
    rather than reported -- the direction this project prefers to be wrong in.
    """
    recorded = name_words(case.name)
    return name_covers(recorded, name_words(citation.plaintiff)) and name_covers(
        recorded, name_words(citation.defendant)
    )


def _pages_this_document_cites(document: ExtractedDocument, known: set[str]) -> set[tuple[str, str]]:
    """Every reporter and page the document states, for the correctly-cited test."""
    pages: set[tuple[str, str]] = set()
    for item in document.citations:
        citation = item.citation
        if not isinstance(citation, FullCaseCitation) or not citation.page:
            continue
        slug = _slug_of(citation, known)
        if slug is not None:
            pages.add((slug, citation.page))
    return pages


def _authority_roots(document: ExtractedDocument) -> dict[str, ExtractedCitation]:
    """Map each citation to the full citation that introduced its authority."""
    tree = build_citation_tree(document)
    return {
        occurrence.citation_id: authority.root
        for authority in tree.authorities
        for occurrence in authority.occurrences
    }


def _slug_of(citation: FullCaseCitation, known: set[str]) -> str | None:
    """The archive's directory name for this citation's reporter and volume."""
    if not citation.reporter or not citation.volume or not citation.volume.isdigit():
        return None
    return reporter_slug(citation.reporter, known)
