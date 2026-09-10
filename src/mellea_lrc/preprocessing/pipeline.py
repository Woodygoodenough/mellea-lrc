"""One way in: a document, the rules to read it under, and the text they give.

    from mellea_lrc.preprocessing import Rule, preprocess

    document = preprocess(Path("filing.pdf"))
    document = preprocess(Path("filing.pdf"), [Rule.MARGIN_LINE_NUMBERS])
    document = preprocess("See Brown v. Board of Education, 347 U.S. 483 (1954).")

The argument's type says what it is -- **a `Path` is a location, a `str` is
content** -- which is the same distinction `mellea_lrc.extraction.extract`
makes, for the same reason: a filename that arrives as a string would otherwise
be read as a document about itself.

`rules` is the whole of the configuration. Leave it out and every rule runs;
pass a list and exactly those run; pass an empty list and the converter's own
reading comes through untouched. Which format the source is, which rules that
format can carry, when each rule is applied -- none of that is the caller's
business, and the result records which rules ran so that two renderings can be
told apart.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mellea_lrc.preprocessing.docling import is_docling_supported_format, preprocess_with_docling
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text, preprocess_plain_text_from_string
from mellea_lrc.preprocessing.types import DEFAULT_RULES, PreprocessedDocument, Rule


def preprocess(
    source: Path | str,
    rules: Sequence[Rule] | None = None,
) -> PreprocessedDocument:
    """Read a document, or wrap text already in hand, under the given rules.

    A `Path` is opened and converted by the backend its suffix calls for; a
    `str` is the document's text. `rules` defaults to every rule.
    """
    applied = DEFAULT_RULES if rules is None else tuple(rules)
    if isinstance(source, str):
        return preprocess_plain_text_from_string(source, rules=applied)
    if source.suffix.lower() == ".txt":
        return preprocess_plain_text(source, rules=applied)
    if not is_docling_supported_format(source):
        msg = f"Unsupported document format: {source.suffix or '<none>'}"
        raise ValueError(msg)
    return preprocess_with_docling(source, rules=applied)
