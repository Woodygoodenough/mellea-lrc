"""The citing side: the passage around one citation, and what the filing puts in quotation marks.

A pin cite is a claim about a page, and the words the claim rests on sit in
the filing near the citation -- in a parenthetical, in the sentence, in a
sentence before it, or shared with the other members of a string cite. This
module cuts a window of the filing around the target, marks the target in it
so a reader knows which citation is under examination, finds the other
citations that share its string, reads the signal word ahead of it, and lifts
every quotation the filing writes near it.

Everything here is a span of the filing. What the model later says about the
citing side must land inside this window, so the filing's own words bound
what may be attributed to it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.spans import Span

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea_lrc.extraction.types import ExtractedCitation

BEFORE_CHARS = 1200
"""How far back from the citation the window may reach."""
AFTER_CHARS = 500
"""How far past the citation's end the window may reach, for a parenthetical or the rest of a string."""
MIN_QUOTE_WORDS = 2

TARGET_OPEN = "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}"
TARGET_CLOSE = "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}"

_SIGNALS = (
    ("see generally", "see_generally"),
    ("see also", "see_also"),
    ("but see", "but_see"),
    ("but cf.", "but_see"),
    ("compare", "compare"),
    ("contra", "contra"),
    ("accord", "accord"),
    ("e.g.", "eg"),
    ("cf.", "cf"),
    ("see", "see"),
    ("citing", "citing"),
    ("quoting", "quoting"),
)
_SIGNAL_WINDOW = 60
_DOUBLE_QUOTE = re.compile(
    r"[\"\N{LEFT DOUBLE QUOTATION MARK}](.+?)[\"\N{RIGHT DOUBLE QUOTATION MARK}]", re.DOTALL
)
_SINGLE_QUOTE = re.compile(
    r"(?<![A-Za-z0-9])['\N{LEFT SINGLE QUOTATION MARK}](?=[\[A-Za-z])(.+?)['\N{RIGHT SINGLE QUOTATION MARK}](?![A-Za-z0-9])",
    re.DOTALL,
)
"""A quotation in single marks, told from an apostrophe by what stands on either side of the mark."""
_STRING_JOIN = re.compile(
    r"\s*;\s*(?:(?:see also|see|accord|e\.g\.|cf\.|and|citing)\s*,?\s*)?$", re.IGNORECASE
)
_PARAGRAPH = re.compile(r"\n\s*\n")


@dataclass(frozen=True, slots=True)
class Quotation:
    """Words the filing puts in quotation marks near the target."""

    text: str
    span: Span
    """Where the quoted words are, in document coordinates, marks excluded."""
    in_parenthetical: bool
    """Inside the target's own parenthetical, which ties them to the target alone."""


@dataclass(frozen=True, slots=True)
class CitingWindow:
    """The filing around one citation, with the target marked and its neighbours known."""

    span: Span
    """The window, in document coordinates."""
    text: str
    """The window's text as the filing wrote it."""
    marked: str
    """The same text with the target enclosed in `«` and `»`, for showing to a reader."""
    target: Span
    signal: str | None
    """`see`, `see_also`, `cf`, `but_see`, `accord`, `eg`, `see_generally`, `compare`, `contra`, `citing`, `quoting`; None when bare."""
    string_members: tuple[str, ...]
    """Ids of the other citations joined to the target by semicolons into one string cite."""
    quotations: tuple[Quotation, ...]

    def offset(self, document_offset: int) -> int:
        return document_offset - self.span.start


def citing_window(
    target: ExtractedCitation, citations: Sequence[ExtractedCitation], text: str
) -> CitingWindow:
    """Cut the filing around the target and read its string, its signal and its quotations."""
    start = max(0, target.full_span.start - BEFORE_CHARS)
    end = min(len(text), target.full_span.end + AFTER_CHARS)
    # Do not start mid-sentence when a paragraph break is in reach, and do
    # not run past the paragraph the citation sits in.
    if breaks := list(_PARAGRAPH.finditer(text, start, target.full_span.start)):
        start = breaks[-1].end()
    if (after := _PARAGRAPH.search(text, target.full_span.end, end)) is not None:
        end = after.start()
    span = Span(start, end)
    window = text[start:end]
    marked = (
        window[: target.full_span.start - start]
        + TARGET_OPEN
        + window[target.full_span.start - start : target.full_span.end - start]
        + TARGET_CLOSE
        + window[target.full_span.end - start :]
    )
    return CitingWindow(
        span=span,
        text=window,
        marked=marked,
        target=target.full_span,
        signal=read_signal(text, target.full_span.start),
        string_members=string_members(target, citations, text),
        quotations=quotations_near(target, citations, text, span),
    )


def read_signal(text: str, citation_start: int) -> str | None:
    """The signal word immediately ahead of the citation, if any."""
    ahead = text[max(0, citation_start - _SIGNAL_WINDOW) : citation_start].lower()
    ahead = re.sub(r"[\s,]+$", "", ahead)
    # Only the last few words count: `See Smith, 1 U.S. 1; Jones, ...` is
    # `see` for both, `Smith held X. Jones, ...` is bare.
    tail = " ".join(ahead.split()[-3:])
    for word, name in _SIGNALS:
        if tail.endswith((word, word + ",")):
            return name
    return None


def string_members(
    target: ExtractedCitation, citations: Sequence[ExtractedCitation], text: str
) -> tuple[str, ...]:
    """The other citations semicolon-joined to the target, walking outward in both directions."""
    ordered = sorted(
        (c for c in citations if c.citation_id != target.citation_id), key=lambda c: c.full_span.start
    )
    members: list[str] = []
    # Leftwards: a member ends just before `; ` that leads into the current one.
    current = target.full_span.start
    changed = True
    while changed:
        changed = False
        for other in reversed(ordered):
            if other.full_span.end <= current and _joined(text[other.full_span.end : current]):
                members.insert(0, other.citation_id)
                current = other.full_span.start
                changed = True
                break
    current = target.full_span.end
    changed = True
    while changed:
        changed = False
        for other in ordered:
            if other.full_span.start >= current and _joined(text[current : other.full_span.start]):
                members.append(other.citation_id)
                current = other.full_span.end
                changed = True
                break
    return tuple(members)


def _joined(between: str) -> bool:
    """Whether the text between two citations is a string-cite join: a semicolon, maybe a signal."""
    if len(between) > 40:
        return False
    return bool(_STRING_JOIN.match(between))


_BOUNDARY = re.compile(
    r"[.!?][\"\N{RIGHT DOUBLE QUOTATION MARK}'\N{RIGHT SINGLE QUOTATION MARK}]?\s+(?=[A-Z\"\N{LEFT DOUBLE QUOTATION MARK}])"
)
_SIGNAL_ONLY = re.compile(
    r"^[\s,;]*(?:(?:see also|see generally|but see|see|accord|cf\.|e\.g\.|compare|contra|citing|quoting|in|and)[\s,]*)*$",
    re.IGNORECASE,
)


def quotations_near(
    target: ExtractedCitation, citations: Sequence[ExtractedCitation], text: str, window: Span
) -> tuple[Quotation, ...]:
    """Every quotation in the sentence the target belongs to and in the target's parenthetical.

    The sentence runs from the last sentence boundary before the target that
    is not the end of the quotation the citation follows -- `'... omission.'
    See Pioneer` breaks no sentence -- to the first boundary after the
    target, and stops at any other citation that is not a string member.
    """
    members = set(string_members(target, citations, text))
    sentence_start = window.start
    sentence_end = min(window.end, target.full_span.end + 600)
    for other in citations:
        if other.citation_id in members or other.citation_id == target.citation_id:
            continue
        if window.start <= other.full_span.end <= target.full_span.start:
            sentence_start = max(sentence_start, other.full_span.end)
        if target.full_span.end <= other.full_span.start < sentence_end:
            sentence_end = other.full_span.start
    region = text[sentence_start : target.full_span.start]
    last_real = None
    for match in _BOUNDARY.finditer(region):
        # A boundary is real only when a sentence of its own follows it
        # before the citation; a period inside the closing quotation mark
        # followed by `See` is the quoted sentence's, not a break.
        if _SIGNAL_ONLY.match(region[match.end() :]):
            continue
        last_real = match.end()
    if last_real is not None:
        sentence_start += last_real
    after_target = text[target.full_span.end : sentence_end]
    if match := _BOUNDARY.search(after_target):
        sentence_end = target.full_span.end + match.end()
    found: list[Quotation] = []
    paren = _parenthetical_span(target, text)
    taken: list[Span] = []
    for pattern in (_DOUBLE_QUOTE, _SINGLE_QUOTE):
        for match in pattern.finditer(text, sentence_start, sentence_end):
            inner = match.group(1)
            if len(inner.split()) < MIN_QUOTE_WORDS or len(inner) > 1500:
                continue
            span = Span(match.start(1), match.end(1))
            if any(t.start <= span.start < t.end or span.start <= t.start < span.end for t in taken):
                continue
            taken.append(span)
            in_paren = paren is not None and paren.start <= span.start and span.end <= paren.end
            found.append(Quotation(inner, span, in_paren))
    found.sort(key=lambda q: q.span.start)
    return tuple(found)


def _parenthetical_span(target: ExtractedCitation, text: str) -> Span | None:
    """The parenthetical the target's span ends with, when it ends with one."""
    end = target.full_span.end
    if end == 0 or text[end - 1] != ")":
        return None
    depth = 0
    for position in range(end - 1, target.full_span.start - 1, -1):
        if text[position] == ")":
            depth += 1
        elif text[position] == "(":
            depth -= 1
            if depth == 0:
                return Span(position, end)
    return None


__all__ = [
    "AFTER_CHARS",
    "BEFORE_CHARS",
    "TARGET_CLOSE",
    "TARGET_OPEN",
    "CitingWindow",
    "Quotation",
    "citing_window",
    "quotations_near",
    "read_signal",
    "string_members",
]
