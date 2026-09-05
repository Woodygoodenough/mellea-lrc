"""Find a short string in a window of text, allowing for the text's own damage.

A model that reads a filing writes `Suffolk` where the filing wrote `Suffock`,
`Pacific Bell` where a converter left `Pac ific Bell`, and a straight quote
where the page has a curly one. None of those is the model inventing text, and
a check that demands the model reproduce the page's errors punishes it for
reading well. So the question this module answers is not "is this string in
the text" but "is there a place in the text this string could have been read
from", and it answers with every such place, each with a score.

Three ways to match, tried in order, and the first that finds anything wins:

- **exact**: the string as written
- **normalised**: after folding case, accents, quote and dash variants, and
  runs of whitespace, so a converter's spacing and a typist's quotes are
  ignored
- **fuzzy**: a window of the same number of words, or one more or fewer, whose
  normalised text is close to the needle's by :class:`difflib.SequenceMatcher`
  ratio, which is what lets one wrong letter through

Every match carries the span it sits on in the original text, so a caller can
keep the evidence as an offset rather than a copy.

What this is not: it is not a search for a name across a document. It is for
a window a caller has already bounded -- the text between two citations, the
parenthetical after a locator -- where a match anywhere in it is what the
caller wants to know.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

DEFAULT_MIN_SCORE = 0.85
"""Below this ratio a window is not the needle. One wrong letter in a
three-word name scores about 0.95; two different words score below 0.8."""

_WORD = re.compile(r"\S+")
_EQUIVALENTS = str.maketrans(
    {
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": '"',
        "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "-",
        "\N{MINUS SIGN}": "-",
        "\N{NO-BREAK SPACE}": " ",
    }
)


class MatchMethod(str, Enum):
    """How a match was found, strictest first."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"


@dataclass(frozen=True, slots=True)
class Match:
    """One place in the text the needle could have been read from."""

    start: int
    end: int
    text: str
    """The text at the span, as the source wrote it."""
    score: float
    """1.0 for exact and normalised matches; the similarity ratio for fuzzy ones."""
    method: MatchMethod


def normalize(value: str) -> str:
    """Fold what a reader does not distinguish: case, accents, quote and dash variants, spacing."""
    folded = unicodedata.normalize("NFKD", value.translate(_EQUIVALENTS)).encode("ascii", "ignore").decode()
    return " ".join(folded.casefold().split())


def find_all(needle: str, window: str, *, min_score: float = DEFAULT_MIN_SCORE) -> tuple[Match, ...]:
    """Every place in ``window`` the needle could have been read from, best first.

    Empty when the needle is blank or nothing scores at or above ``min_score``.
    Overlapping fuzzy candidates are reduced to the best-scoring one.
    """
    needle = " ".join(needle.split())
    if not needle or not window:
        return ()
    exact = tuple(
        Match(start, start + len(needle), needle, 1.0, MatchMethod.EXACT)
        for start in _substring_starts(window, needle)
    )
    if exact:
        return exact
    normalized = _find_normalized(needle, window)
    if normalized:
        return normalized
    return _find_fuzzy(needle, window, min_score=min_score)


def find_word(word: str, window: str, *, min_score: float = 0.8) -> tuple[Match, ...]:
    """Every word in ``window`` that is this word, or this word with a letter wrong.

    Short words must match after normalisation; a wrong letter in a
    three-letter word is a different word. From five letters up the ratio
    applies, so `Suffock` finds `Suffolk`.
    """
    target = normalize(word)
    if not target:
        return ()
    found: list[Match] = []
    for match in _WORD.finditer(window):
        token = normalize(match.group(0).strip(".,;:()[]\"'"))
        if not token:
            continue
        if token == target:
            score, method = 1.0, MatchMethod.NORMALIZED if match.group(0) != word else MatchMethod.EXACT
        elif len(target) >= 5 and (score := SequenceMatcher(None, target, token).ratio()) >= min_score:
            method = MatchMethod.FUZZY
        else:
            continue
        found.append(Match(match.start(), match.end(), match.group(0), score, method))
    return tuple(sorted(found, key=lambda item: (-item.score, item.start)))


def contains(needle: str, window: str, *, min_score: float = DEFAULT_MIN_SCORE) -> bool:
    """Whether the needle could have been read from somewhere in the window."""
    return bool(find_all(needle, window, min_score=min_score))


def _find_normalized(needle: str, window: str) -> tuple[Match, ...]:
    target = normalize(needle)
    folded, offsets = _normalized_with_offsets(window)
    if not target:
        return ()
    return tuple(
        Match(
            offsets[start],
            offsets[start + len(target) - 1] + 1,
            window[offsets[start] : offsets[start + len(target) - 1] + 1],
            1.0,
            MatchMethod.NORMALIZED,
        )
        for start in _substring_starts(folded, target)
    )


def _find_fuzzy(needle: str, window: str, *, min_score: float) -> tuple[Match, ...]:
    target = normalize(needle)
    words = list(_WORD.finditer(window))
    width = len(target.split())
    if not target or not words:
        return ()
    candidates: list[Match] = []
    for size in sorted({width, max(1, width - 1), width + 1}):
        for index in range(len(words) - size + 1):
            first, last = words[index], words[index + size - 1]
            text = window[first.start() : last.end()]
            score = SequenceMatcher(None, target, normalize(text)).ratio()
            if score >= min_score:
                candidates.append(Match(first.start(), last.end(), text, score, MatchMethod.FUZZY))
    return _best_non_overlapping(candidates)


def _best_non_overlapping(candidates: list[Match]) -> tuple[Match, ...]:
    kept: list[Match] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.start)):
        if all(candidate.end <= other.start or candidate.start >= other.end for other in kept):
            kept.append(candidate)
    return tuple(sorted(kept, key=lambda item: (-item.score, item.start)))


def _normalized_with_offsets(value: str) -> tuple[str, list[int]]:
    """The normalised text and, for each of its characters, the source offset it came from."""
    out: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for index, char in enumerate(value):
        folded = (
            unicodedata.normalize("NFKD", char.translate(_EQUIVALENTS))
            .encode("ascii", "ignore")
            .decode()
            .casefold()
        )
        if not folded:
            continue
        if folded.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            offsets.append(index)
            pending_space = False
        for piece in folded:
            out.append(piece)
            offsets.append(index)
    return "".join(out), offsets


def _substring_starts(value: str, substring: str) -> list[int]:
    starts: list[int] = []
    position = value.find(substring)
    while position != -1:
        starts.append(position)
        position = value.find(substring, position + 1)
    return starts


__all__ = ["DEFAULT_MIN_SCORE", "Match", "MatchMethod", "contains", "find_all", "find_word", "normalize"]
