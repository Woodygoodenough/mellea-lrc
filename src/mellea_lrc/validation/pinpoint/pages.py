"""The cited page, cut from the archive's opinion text along the reporter's own pagination.

CourtListener's ``html_with_citations`` marks where each reporter's pages
turn: ``<span class="star-pagination" citation-index="1" label="570">``,
where the index counts the cluster's parallel citations from one. So a pin
cite ``550 U.S. 544, 570`` is the text between the marker labelled ``570``
for the U.S. Reports and the next U.S. Reports marker -- and the same opinion
paginated by S. Ct. turns at different places, which is why a page is only
ever cut for the reporter the filing wrote.

A cluster holds several opinions: the court's, a concurrence, a dissent. Each
is read and paginated on its own, and which one the page came from travels
with the text, because words on the cited page in a dissent are a different
fact from the same words in the opinion of the court.

What is cut is the page, or the run of pages a range names, with the tail of
the page before and the head of the page after beside it: a sentence that a
filing pins to 678 often begins on 677, and a reader deciding whether the
page carries something must be able to see the turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from mellea_lrc.core.spans import Span

if TYPE_CHECKING:
    from mellea_lrc.courtlistener.opinion_models import (
        CourtListenerOpinion,
        CourtListenerOpinionClusterCitation,
    )

MAX_RANGE_PAGES = 4
"""How many pages a range such as `588-90` is allowed to span before only its first page is cut."""
NEIGHBOUR_CHARS = 700
"""How much of the page before and the page after is shown beside the cited page."""
HEAD_CHARS_PER_PAGE = 600
"""The least text per page the unmarked head of an opinion must hold to count as those pages."""

_DASH = re.compile(r"[-\N{EN DASH}\N{EM DASH}\N{MINUS SIGN}]")
_PAGE = re.compile(r"^(?P<first>\d+)(?:\s*[-\N{EN DASH}\N{EM DASH}]\s*(?P<last>\d+))?$")
_FOOTNOTE = re.compile(r"^(?P<page>\d+)\s*(?:n|nn)\.?\s*\d+", re.IGNORECASE)

OPINION_ORDER = {
    "015unamimous": 0,  # CourtListener's canonical value carries this typo.
    "020lead": 1,
    "025plurality": 2,
    "010combined": 3,
    "030concurrence": 4,
    "035concurrenceinpart": 5,
    "040dissent": 6,
    "050addendum": 7,
    "060remittitur": 8,
    "070rehearing": 9,
    "080onthemerits": 10,
    "090onmotiontostrike": 11,
}


@dataclass(frozen=True, slots=True)
class PinPages:
    """The reporter pages a pin cite names, or the reason it names none this stage can cut."""

    labels: tuple[str, ...]
    """`("570",)` for `570`; `("180", "181")` for `180-81`; empty when the form is not a page."""
    form: str
    """`page`, `range`, `footnote`, `star`, `paragraph`, `section`, `other`."""


def pin_pages(pin_cite: str | None) -> PinPages:
    """Read which reporter pages a pin cite names.

    A star page (`*3`) counts an electronic report, a paragraph (`¶ 26`) an
    opinion's or an indictment's numbering, a section (`§ 12`) a statute:
    none is a reporter page, and each is named for what it is rather than
    read as one. A footnote pin (`657 n.1`) names its page and says the
    material is in a footnote there.
    """
    if pin_cite is None or not pin_cite.strip():
        return PinPages((), "other")
    text = " ".join(pin_cite.split()).strip(" ,")
    text = re.sub(r"^(?:at\s+)", "", text, flags=re.IGNORECASE)
    if text.startswith("*"):
        return PinPages((), "star")
    if "¶" in text or text.lower().startswith("para"):
        return PinPages((), "paragraph")
    if "§" in text:
        return PinPages((), "section")
    if match := _FOOTNOTE.match(text):
        return PinPages((match.group("page"),), "footnote")
    if match := _PAGE.match(text):
        first = match.group("first")
        last = match.group("last")
        if last is None:
            return PinPages((first,), "page")
        return PinPages(_expand_range(first, last), "range")
    return PinPages((), "other")


def _expand_range(first: str, last: str) -> tuple[str, ...]:
    """`588-90` is 588 to 590; `1072-73` is 1072 to 1073; `912-913` is itself."""
    if len(last) < len(first):
        last = first[: len(first) - len(last)] + last
    start, end = int(first), int(last)
    if end < start:
        return (first,)
    if end - start + 1 > MAX_RANGE_PAGES:
        end = start + MAX_RANGE_PAGES - 1
    return tuple(str(page) for page in range(start, end + 1))


@dataclass(frozen=True, slots=True)
class PageMarker:
    """One place an opinion's text turns a reporter page."""

    citation_index: str
    label: str
    offset: int


@dataclass(frozen=True, slots=True)
class PaginatedOpinion:
    """One opinion's plain text with every reporter page turn located in it."""

    opinion_id: str
    opinion_type: str
    text: str
    markers: tuple[PageMarker, ...]

    def labels(self, citation_index: str) -> tuple[str, ...]:
        return tuple(marker.label for marker in self.markers if marker.citation_index == citation_index)

    def page_span(self, citation_index: str, label: str, *, first_page: str | None = None) -> Span | None:
        """Where the page with this label lies in the text, to the next turn of the same reporter.

        An opinion's opening pages often carry no marker at all -- `814 F.2d
        565` is marked only at 568 -- so a label between the case's first
        page and the first marker is the head of the text, cut as one run.
        """
        for position, marker in enumerate(self.markers):
            if marker.citation_index != citation_index or marker.label != label:
                continue
            end = next(
                (m.offset for m in self.markers[position + 1 :] if m.citation_index == citation_index),
                len(self.text),
            )
            return Span(marker.offset, end)
        first = next((m for m in self.markers if m.citation_index == citation_index), None)
        if first is not None and first_page is not None and label.isdigit() and first.label.isdigit():
            pages = int(first.label) - int(first_page)
            # The head must be long enough to be those pages. A title and an
            # epigraph before a marker for the sixth page are not five pages
            # of text; the archive's pagination simply starts late.
            if (
                int(first_page) <= int(label) < int(first.label)
                and first.offset >= HEAD_CHARS_PER_PAGE * pages
            ):
                return Span(0, first.offset)
        return None

    def head_labels(self, citation_index: str, first_page: str | None) -> tuple[str, ...]:
        """The unmarked pages the head of the text spans: from the first page to the first marker."""
        first = next((m for m in self.markers if m.citation_index == citation_index), None)
        if first is None or first_page is None or not first_page.isdigit() or not first.label.isdigit():
            return ()
        pages = int(first.label) - int(first_page)
        if first.offset < HEAD_CHARS_PER_PAGE * pages:
            return ()
        return tuple(str(page) for page in range(int(first_page), int(first.label)))

    def label_at(self, offset: int, citation_index: str) -> str | None:
        """The page an offset falls on, for the given reporter; None before its first marker."""
        label: str | None = None
        for marker in self.markers:
            if marker.citation_index != citation_index:
                continue
            if marker.offset > offset:
                break
            label = marker.label
        return label


def paginate(opinion: CourtListenerOpinion) -> PaginatedOpinion:
    """Read an opinion's citation-aware HTML into text with its page turns located."""
    parser = _Parser()
    parser.feed(opinion.html_with_citations)
    parser.close()
    text, markers = parser.result()
    return PaginatedOpinion(opinion.opinion_id, opinion.opinion_type, text, markers)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._length = 0
        self._markers: list[tuple[str, str, int]] = []
        self._in_marker = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        index = attributes.get("citation-index")
        label = attributes.get("label")
        if index is not None and label is not None:
            # The marker's own text, `*544`, is the reporter's page number
            # and not the opinion's words; the page begins after it.
            self._markers.append((index, label, self._length))
            self._in_marker = True
        elif tag in ("p", "div", "br", "blockquote", "li", "h1", "h2", "h3"):
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._in_marker and tag == "span":
            self._in_marker = False
            return
        if tag in ("p", "div", "blockquote", "li", "h1", "h2", "h3"):
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_marker:
            return
        self._append(data)

    def _append(self, data: str) -> None:
        self._parts.append(data)
        self._length += len(data)

    def result(self) -> tuple[str, tuple[PageMarker, ...]]:
        raw = "".join(self._parts)
        # Collapse runs of whitespace while keeping every marker on the
        # character it preceded, so offsets stay true after the collapse.
        out: list[str] = []
        mapping: list[int] = []
        pending_space = False
        for position, character in enumerate(raw):
            if character.isspace():
                pending_space = True
                continue
            if pending_space and out:
                out.append(" ")
                mapping.append(position)
            pending_space = False
            out.append(character)
            mapping.append(position)
        text = "".join(out)
        # A marker's offset maps to the first kept character at or after it.
        import bisect

        markers = []
        for index, label, offset in self._markers:
            position = min(bisect.bisect_left(mapping, offset), len(text))
            while position < len(text) and text[position] == " ":
                position += 1
            markers.append(PageMarker(index, label, position))
        return text, tuple(markers)


@dataclass(frozen=True, slots=True)
class RetrievedPage:
    """The cited page as cut from one opinion, with its neighbours."""

    opinion_id: str
    opinion_type: str
    citation_index: str
    labels: tuple[str, ...]
    text: str
    """The page, or the pages of a range joined with `[*label]` turns between them."""
    span: Span
    """Where `text` lies in the paginated opinion."""
    before: str
    """The tail of the page before, or empty at the opinion's start."""
    after: str
    """The head of the page after, or empty at the opinion's end."""


def cut_page(
    opinion: PaginatedOpinion, citation_index: str, labels: tuple[str, ...], *, first_page: str | None = None
) -> RetrievedPage | None:
    """Cut the page or run of pages from one paginated opinion; None when it does not hold the first."""
    spans = [opinion.page_span(citation_index, label, first_page=first_page) for label in labels]
    if not spans or spans[0] is None:
        return None
    start = spans[0].start
    end = spans[0].end
    held = [labels[0]]
    head = opinion.head_labels(citation_index, first_page)
    if labels[0] in head:
        # The unmarked head is one run; every page in it is held at once.
        held = list(head)
    for label, span in zip(labels[1:], spans[1:], strict=True):
        if label in held:
            continue
        if span is None or span.start != end:
            break
        end = span.end
        held.append(label)
    text = opinion.text[start:end]
    if len(held) > 1 and labels[0] not in head:
        # Mark the turns inside a range so a reader knows which page a passage is on.
        pieces: list[str] = []
        cursor = start
        for label in held[1:]:
            turn = opinion.page_span(citation_index, label)
            assert turn is not None
            pieces.append(opinion.text[cursor : turn.start])
            pieces.append(f" [*{label}] ")
            cursor = turn.start
        pieces.append(opinion.text[cursor:end])
        text = "".join(pieces)
    before = opinion.text[max(0, start - NEIGHBOUR_CHARS) : start]
    after = opinion.text[end : end + NEIGHBOUR_CHARS]
    return RetrievedPage(
        opinion_id=opinion.opinion_id,
        opinion_type=opinion.opinion_type,
        citation_index=citation_index,
        labels=tuple(held),
        text=text,
        span=Span(start, end),
        before=before,
        after=after,
    )


def citation_index(
    citations: tuple[CourtListenerOpinionClusterCitation, ...], *, volume: str | None, reporter: str | None
) -> str | None:
    """Which of the cluster's parallel citations the filing's reporter is, counted from one."""
    if volume is None or reporter is None:
        return None
    wanted = _reporter_key(reporter)
    exact = [
        str(position)
        for position, citation in enumerate(citations, start=1)
        if citation.volume == volume and _reporter_key(citation.reporter) == wanted
    ]
    if len(exact) == 1:
        return exact[0]
    same_volume = [
        str(position) for position, citation in enumerate(citations, start=1) if citation.volume == volume
    ]
    return same_volume[0] if len(same_volume) == 1 else None


def marker_index_for(
    opinions: tuple[PaginatedOpinion, ...], first_page: str | None, labels: tuple[str, ...]
) -> str | None:
    """The marker index whose page numbers are the cited reporter's, read from the numbers themselves.

    The cluster's citation list and the HTML's `citation-index` do not always
    count the same way, so the index is chosen by fit: its numeric labels run
    from just above the case's first page, and one of them is the cited page
    or the cited page lies in the unmarked head before them.
    """
    if first_page is None or not first_page.isdigit() or not labels or not labels[0].isdigit():
        return None
    wanted = int(labels[0])
    first = int(first_page)
    best: tuple[int, str] | None = None
    for opinion in opinions:
        by_index: dict[str, list[int]] = {}
        for marker in opinion.markers:
            if marker.label.isdigit():
                by_index.setdefault(marker.citation_index, []).append(int(marker.label))
        for index, numbers in by_index.items():
            low = min(numbers)
            if low <= first or low - first > 40:
                continue
            if wanted in numbers or first <= wanted < low:
                distance = low - first
                if best is None or distance < best[0]:
                    best = (distance, index)
    return best[1] if best else None


def _reporter_key(reporter: str) -> str:
    return "".join(character.lower() for character in reporter if character.isalnum())


def opinion_order(opinion_type: str) -> int:
    return OPINION_ORDER.get(opinion_type, 50)


__all__ = [
    "MAX_RANGE_PAGES",
    "NEIGHBOUR_CHARS",
    "PageMarker",
    "PaginatedOpinion",
    "PinPages",
    "RetrievedPage",
    "citation_index",
    "cut_page",
    "marker_index_for",
    "opinion_order",
    "paginate",
    "pin_pages",
]
