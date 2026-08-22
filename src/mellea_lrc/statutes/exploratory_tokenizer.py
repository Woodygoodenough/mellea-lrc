"""Statute-pattern relaxations, kept out of the citation pipeline on purpose.

**Nothing in this project imports this module, and nothing should yet.** The
case-citation work is the project; statute checking is a domain-learning
exercise that has not settled what a statute citation even is for our purposes
-- how a provision should be represented, which jurisdictions to take in what
order, what counts as the same provision across amendments. Wiring a
half-understood model of that into the extractor would entangle the citation
results with a question nobody has answered.

An earlier version of this code lived in
``experimental/relaxed_eyecite_extractor.py`` and changed how that extractor
handled law patterns. It is here instead. The case extractor relaxes case
patterns and nothing else.

What is recorded here is a measurement, not a component. eyecite generates law
patterns the same way it generates reporter patterns, and they are brittle in
the same three places. A statute that fails to match is not reported
imperfectly -- it produces a bare section symbol typed as unknown, and no law
citation at all.

1. The section group admits ``1983``, ``1-101`` and ``636(b)(1)(A)`` and
   refuses a letter fixed to the digits: ``2000e-2``, ``1681g``, ``794a``,
   ``77l``, ``668dd``. Those are Title VII, the Fair Credit Reporting Act, the
   Rehabilitation Act, the Securities Act and the National Wildlife Refuge
   System Administration Act. Two letters occur, so the allowance is two.
2. Most law patterns join the reporter to the section symbol with a literal
   space and allow one after it.
3. Every reporter branch requires its closing period, so ``42 U.S.C § 12132``
   and ``29 U.S.C.A § 2612`` match nothing. The prefilter has to admit the
   period-less spelling too, or the relaxation only fires in a document that
   happens to spell the reporter correctly somewhere else.

Relaxing all three took the parse rate from 89% to 100% on the 26 test filings
and from 88% to 100% on the 109 sampled ones, counted as distinct
title-and-section pairs against what is written on the page. It also stopped
``17 C.F.R. § 240.10b-5`` being cut down to part ``240``.

It has a measured cost. In one typewritten filing that was scanned, every digit
1 came out as a lowercase l, so ``18 U.S.C. § 201`` reads as ``20l`` -- a
section that does not exist, where the unrelaxed pattern found nothing at all.
Four of the 53 letter-ending sections recovered across the 109 filings are that
damage, against 49 real ones.

None of that is applied to case patterns, and now none of it is applied to
anything: building a tokenizer from here is an explicit act by a caller who
wants to reproduce the statute measurement.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from eyecite.models import TokenExtractor
from eyecite.tokenizers import EXTRACTORS

from mellea_lrc.experimental.relaxed_eyecite_extractor import (
    _REPORTER_GROUP,
    _TIGHT_PUNCTUATION,
    _joins,
    _RelaxedTokenizer,
)

if TYPE_CHECKING:
    from eyecite.tokenizers import Tokenizer

__all__ = ["exploratory_statute_tokenizer", "relax_law_pattern"]

# A law pattern is the one with a section group. Case patterns have a page.
IS_LAW_PATTERN = "(?P<section>"

_SECTION_DIGITS = r"(?:\d+(?:[\-.:]\d+){,3})"
_SECTION_DIGITS_WITH_LETTER = r"(?:\d+[a-zA-Z]{,2}(?:[\-.:]\d+[a-zA-Z]{,2}){,3})"
_SECTION_SYMBOL_JOIN = (") §§? ?", r")\s*§§?\s*")

# The closing period of one reporter branch, as it reads after the punctuation
# relaxation has already put `\s*` on either side of it.
_FINAL_PERIOD = re.compile(r"\\s\*\\\.(?:\\s\*)*$")
_FINAL_PERIOD_OPTIONAL = r"(?:\s*\.)?\s*"


def relax_law_pattern(regex: str) -> str:
    """Widen one generated law pattern in the three places it is brittle."""
    if IS_LAW_PATTERN not in regex:
        return regex
    regex = regex.replace(*_SECTION_SYMBOL_JOIN)
    regex = regex.replace(_SECTION_DIGITS, _SECTION_DIGITS_WITH_LETTER)
    return _REPORTER_GROUP.sub(_relax_law_reporter, regex)


def _relax_law_reporter(match: re.Match[str]) -> str:
    """Relax the punctuation, then let each branch end without its closing period.

    Law patterns only. A case reporter's closing period is what separates it
    from the page in `410 U.S. 113`, so making it optional there would let the
    reporter run into the number after it. A statute has a section symbol in
    that position, so nothing is riding on the period.
    """
    body = _TIGHT_PUNCTUATION.sub(lambda found: rf"\s*{found.group()}\s*", match.group(1))
    # A plain replacement string would be read as a template, and the `\s` in
    # it is not a valid template escape.
    branches = (_FINAL_PERIOD.sub(lambda _: _FINAL_PERIOD_OPTIONAL, branch) for branch in body.split("|"))
    return f"(?P<reporter>{'|'.join(branches)})"


def _prefilter_strings(extractor: TokenExtractor) -> list[str]:
    """The literals the prefilter admits one law extractor on.

    The prefilter decides whether a pattern runs at all, so relaxing a law
    reporter's closing period accomplishes nothing unless the period-less
    spelling is admitted here too.
    """
    if IS_LAW_PATTERN not in extractor.regex:
        return extractor.strings
    without_period = [text.removesuffix(".") for text in extractor.strings if text.endswith(".")]
    return list(dict.fromkeys([*extractor.strings, *without_period]))


def exploratory_statute_tokenizer(*, cross_blank_lines: bool = False) -> Tokenizer:
    """Build a tokenizer that also widens the statute patterns.

    For reproducing the statute measurement in
    `exploration/notes/statute-validation.md` and for nothing else. The
    citation pipeline uses
    :func:`~mellea_lrc.experimental.relaxed_eyecite_extractor.relaxed_tokenizer`,
    which leaves law patterns exactly as eyecite generates them.
    """
    case_joins = _joins(cross_blank_lines=cross_blank_lines)
    return _RelaxedTokenizer(
        extractors=[
            TokenExtractor(
                regex=relax_law_pattern(_relax_case_and_law(extractor.regex, case_joins)),
                constructor=extractor.constructor,
                extra=extractor.extra,
                flags=extractor.flags,
                strings=_prefilter_strings(extractor),
            )
            for extractor in EXTRACTORS
        ]
    )


def _relax_case_and_law(regex: str, joins: tuple[tuple[str, str], ...]) -> str:
    """Apply the case-pattern joins, which law patterns share."""
    for old, new in joins:
        regex = regex.replace(old, new)
    return regex
