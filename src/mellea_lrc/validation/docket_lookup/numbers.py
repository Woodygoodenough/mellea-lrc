"""Docket numbers as filings write them and as courts record them.

A filing writes `No. 05-4206`; the court's system holds `2:05-cv-04206`. The
office prefix, the case-type token and the zero padding are the clerk's, not
the case's. What names the case is the year and the sequence, so those are
what two numbers are compared on, and what a query is built from.
"""

from __future__ import annotations

import re

_CORE = re.compile(
    r"(?:(\d):)?(\d{2})(?:[-\s]*(cv|cr|bk|md|mc|misc|civ|crim|ap)\.?[-\s]*|-\s?)(\d{2,6})", re.IGNORECASE
)
_DIGITS = re.compile(r"\d+")


def docket_core(number: str | None) -> tuple[str, str] | None:
    """The year and sequence of a docket number, zeros stripped from the sequence: `('05', '4206')`."""
    if not number:
        return None
    match = _CORE.search(number)
    if match:
        return match.group(2), match.group(4).lstrip("0") or "0"
    groups = _DIGITS.findall(number)
    if len(groups) >= 2:
        return groups[-2][-2:], groups[-1].lstrip("0") or "0"
    return None


def docket_number_matches(written: str | None, recorded: str | None) -> bool:
    """Whether two docket numbers name the same case, allowing for how each was written."""
    left, right = docket_core(written), docket_core(recorded)
    return left is not None and right is not None and left == right


__all__ = ["docket_core", "docket_number_matches"]
