"""Check a filed quotation against the page it is attributed to, deterministically.

A brief that quotes an opinion makes a checkable claim: these characters appear
there. Nothing about it needs a model. What it needs is the citation conventions
that make a faithful quotation differ from the source on purpose --

- `. . .` and `[. . .]` mark omitted intervening text;
- `[W]here` marks a changed first letter;
- `[the plaintiff]` marks a substituted word;
- `[sic]`, `[emphasis added]` and `(citation omitted)` are the quoter's notes,
  not the court's words;
- typographic quotes, dashes and spacing vary between renderings.

Applying those rules is what separates this from a string comparison, and it is
also what a system that skips them gets wrong: an honest Bluebook quotation
fails a naive `in` test, so a checker without the rules reports defects that are
not there.

The outcome vocabulary keeps a contradiction apart from an absence, as
elsewhere in validation. A quotation whose surrounding words are on the page
but whose quoted words differ is `altered` -- a positive finding. A quotation
that does not appear on the page at all is `not_on_page`, which may only mean
the pinpoint is wrong, and asserts nothing on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from mellea_lrc.core.spans import Span

# A quoted fragment shorter than this is too common to locate reliably: "the
# court" appears on most pages, and matching it would ground a quotation that
# was never there.
MIN_FRAGMENT_WORDS = 4
# Above this, the page window is the passage being quoted and any difference is
# an alteration. Below it, the passage is simply not here.
MIN_ALIGNMENT_SCORE = 0.75
# A window this close is the same words, differing only where normalization
# cannot reach.
VERBATIM_SCORE = 0.995

_WORD = re.compile(r"[^\W_]+", flags=re.UNICODE)
_ELLIPSIS = re.compile(r"\[\s*\.\s*\.\s*\.\s*\]|\.\s*\.\s*\.|…")
# `[sic]`, `[emphasis added]`, `(internal citations omitted)` and friends: an
# editorial note rather than words claimed to be on the page.
_EDITORIAL = re.compile(
    r"[\[(]\s*(?:sic|emphases?\s+(?:added|omitted|in\s+original)|"
    r"(?:internal\s+)?(?:citations?|quotations?|quotation\s+marks?|footnotes?)"
    r"(?:\s+and\s+\w+)*\s+omitted|alterations?\s+in\s+original|cleaned\s+up)"
    r"\s*[\])]",
    flags=re.IGNORECASE,
)
# `[W]here` and `[the plaintiff]`: a deliberate substitution whose contents are
# the quoter's, so the brackets are dropped and the contents kept.
_BRACKETED = re.compile(r"\[([^\[\]]{0,40})\]")
_PUNCTUATION_EQUIVALENTS = str.maketrans(
    {
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": '"',
        "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "-",
        "\N{MINUS SIGN}": "-",
    }
)
_QUOTED = re.compile(
    r"[“\"]"  # opening double quote, curly or straight
    r"(?P<quoted>[^“”\"]{8,1200}?)"
    r"[”\"]"  # closing double quote
)


class QuotationOutcome(str, Enum):
    """What the cited page established about one quoted passage."""

    VERBATIM = "verbatim"
    ALTERED = "altered"
    NOT_ON_PAGE = "not_on_page"
    UNCHECKABLE = "uncheckable"


@dataclass(frozen=True, slots=True)
class QuotationFinding:
    """One quoted passage, checked against the page it was attributed to."""

    quoted_text: str
    quoted_span: Span
    outcome: QuotationOutcome
    score: float
    page_span: Span | None = None
    page_text: str | None = None
    differences: tuple[tuple[str, str], ...] = ()

    @property
    def is_defect(self) -> bool:
        """Whether this finding asserts a defect rather than reporting an absence."""
        return self.outcome is QuotationOutcome.ALTERED


def find_quotations(citing_text: str) -> tuple[tuple[str, Span], ...]:
    """Return each double-quoted passage in the citing text with its span."""
    return tuple(
        (match["quoted"], Span(match.start("quoted"), match.end("quoted")))
        for match in _QUOTED.finditer(citing_text)
    )


def check_quotation(page_text: str, quoted_text: str, quoted_span: Span) -> QuotationFinding:
    """Check one quoted passage against the page, applying the citation conventions."""
    fragments = [fragment for fragment in (_clean(part) for part in _ELLIPSIS.split(quoted_text)) if fragment]
    long_enough = [fragment for fragment in fragments if len(_words(fragment)) >= MIN_FRAGMENT_WORDS]
    if not long_enough:
        return QuotationFinding(
            quoted_text=quoted_text,
            quoted_span=quoted_span,
            outcome=QuotationOutcome.UNCHECKABLE,
            score=0.0,
        )

    aligned = [_align(page_text, fragment) for fragment in long_enough]
    best = max(aligned, key=lambda item: item[0])
    score = min(item[0] for item in aligned)

    if score < MIN_ALIGNMENT_SCORE:
        return QuotationFinding(
            quoted_text=quoted_text,
            quoted_span=quoted_span,
            outcome=QuotationOutcome.NOT_ON_PAGE,
            score=score,
        )

    differences = tuple(
        difference for item in aligned for difference in item[2] if difference[0] != difference[1]
    )
    outcome = QuotationOutcome.VERBATIM if score >= VERBATIM_SCORE else QuotationOutcome.ALTERED
    window = best[1]
    return QuotationFinding(
        quoted_text=quoted_text,
        quoted_span=quoted_span,
        outcome=outcome,
        score=score,
        page_span=window,
        page_text=page_text[window.start : window.end] if window is not None else None,
        differences=differences,
    )


def check_quotations(page_text: str, citing_text: str) -> tuple[QuotationFinding, ...]:
    """Check every quoted passage in the citing text against the cited page."""
    return tuple(check_quotation(page_text, quoted, span) for quoted, span in find_quotations(citing_text))


def _align(page_text: str, fragment: str) -> tuple[float, Span | None, tuple[tuple[str, str], ...]]:
    """Find the page window best matching one fragment, and the words that differ."""
    page_words = _word_spans(page_text)
    fragment_words = _words(fragment)
    if not page_words or not fragment_words:
        return (0.0, None, ())

    normalized_page = [_normalize(word) for word, _, _ in page_words]
    normalized_fragment = [_normalize(word) for word in fragment_words]
    width = len(normalized_fragment)

    best_score = 0.0
    best_index = 0
    for start in range(max(1, len(normalized_page) - width + 1)):
        window = normalized_page[start : start + width]
        score = SequenceMatcher(None, normalized_fragment, window).ratio()
        if score > best_score:
            best_score, best_index = score, start
            if score == 1.0:
                break

    window_words = page_words[best_index : best_index + width]
    if not window_words:
        return (best_score, None, ())
    span = Span(window_words[0][1], window_words[-1][2])
    differences = tuple(
        (fragment_word, page_word)
        for fragment_word, page_word in zip(
            normalized_fragment,
            [_normalize(word) for word, _, _ in window_words],
            strict=False,
        )
    )
    return (best_score, span, differences)


def _clean(value: str) -> str:
    without_notes = _EDITORIAL.sub(" ", value)
    return _BRACKETED.sub(lambda match: match.group(1), without_notes).strip()


def _words(value: str) -> list[str]:
    return _WORD.findall(value)


def _word_spans(value: str) -> list[tuple[str, int, int]]:
    return [(match.group(), match.start(), match.end()) for match in _WORD.finditer(value)]


def _normalize(word: str) -> str:
    return word.translate(_PUNCTUATION_EQUIVALENTS).casefold()
