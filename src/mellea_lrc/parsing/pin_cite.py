"""Pinpoint syntax used to normalize quoted pages and paragraphs."""

import re

from mellea_lrc.matching.literal_to_regex import fuzzy_literal

# PDF text extraction may insert horizontal space on either side of a range
# separator. Share this bounded relaxation with the reader so the exact quote
# it captures is also a quote this normalizer can interpret.
PIN_RANGE_JOIN = r"[^\S\r\n]*[-–][^\S\r\n]*"
_HSPACE = r"[^\S\r\n]"
AT_JOIN = fuzzy_literal("at ", whitespace=True, newline=True)
AT_PREFIX = re.compile(AT_JOIN, re.I)
PIN_PART = re.compile(
    rf"(?P<label>\*|¶{{1,2}})?{_HSPACE}*(?P<first>\d+)"
    rf"(?:{PIN_RANGE_JOIN}(?P<last>\d+))?"
    rf"(?:{_HSPACE}+(?:(?:&|and){_HSPACE}*)?(?:n{{1,2}}\.|fn\.?)"
    rf"{_HSPACE}*(?P<footnote>\d+(?:{PIN_RANGE_JOIN}\d+)?))?\Z",
    re.I,
)
