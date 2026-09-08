"""Putting a search query into one form, so two ways of writing it cost one request.

The proxy caches a search on the request it received, and the route's
case-name queries are written by a model, so `caseName:(Turner AND Murphy)`
and `caseName:( Murphy  AND Turner )` are two requests against an allowance of
fifty an hour for one question. Sending both in one form folds them together.

Only what cannot change an answer is touched.

* **Whitespace outside quotation marks** is collapsed. Inside them it is the
  phrase, and `"206 A.D.3d 558"` is not `"206 A.D.3d  558"` to an index that
  matches the words in order.
* **Terms joined by one operator inside one group** are ordered, because `a
  AND b` asks what `b AND a` asks. A group mixing operators is left alone,
  since precedence makes the order carry meaning, and so is a group holding
  another group.

Everything else is passed through as written. A normaliser that guesses is
worse than none: it would answer a question nobody asked and charge the same
allowance for it.
"""

from __future__ import annotations

import re

_QUOTED = re.compile(r'"[^"]*"')
_GROUP = re.compile(r"(\w+:)\(([^()]*)\)")
_SPACE = re.compile(r"\s+")
_OPERATOR = re.compile(r"\s+(AND|OR)\s+")


def normalize_query(query: str) -> str:
    """One form of a query, for two ways of writing it to be served from one cache entry."""
    if not query:
        return query
    spaced = _outside_quotes(query, lambda text: _SPACE.sub(" ", text)).strip()
    return _GROUP.sub(_ordered_group, spaced)


def _ordered_group(match: re.Match[str]) -> str:
    field, inside = match.group(1), match.group(2).strip()
    operators = set(_OPERATOR.findall(inside))
    if len(operators) != 1:
        return f"{field}({inside})"
    operator = operators.pop()
    terms = [term.strip() for term in _OPERATOR.split(inside) if term.strip() not in ("AND", "OR", "")]
    if len(terms) < 2:
        return f"{field}({inside})"
    return f"{field}({f' {operator} '.join(sorted(terms, key=str.casefold))})"


def _outside_quotes(text: str, change) -> str:
    """Apply a change to every part of the text that is not inside quotation marks."""
    pieces: list[str] = []
    at = 0
    for quoted in _QUOTED.finditer(text):
        pieces.append(change(text[at : quoted.start()]))
        pieces.append(quoted.group(0))
        at = quoted.end()
    pieces.append(change(text[at:]))
    return "".join(pieces)


__all__ = ["normalize_query"]
