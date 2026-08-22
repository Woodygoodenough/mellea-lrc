"""Eyecite extraction with layout-tolerant reporter matching.

eyecite generates every reporter regex with **literal single spaces** joining
volume, reporter, and page::

    (?P<volume>[1-9]\\d*) (?P<reporter>WL),? (?P<page>...)
                        ^                  ^

Any layout damage to those separators -- a space lost to table extraction, a
doubled space from justified text, a PDF page break landing mid-citation --
makes the citation vanish entirely rather than degrade. This module rebuilds
every extractor with those joins relaxed to ``\\s*``, which is reporter-agnostic:
it is not a fix for any particular reporter, but for how the regexes are
generated.

The result is a plain :class:`ExtractedDocument`, identical in shape to the
baseline extractor's output, so this can be swapped in without any downstream
change.

Not wired into the production pipeline.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING, cast

import ahocorasick
from eyecite import resolve_citations
from eyecite.models import CitationBase, Resource, TokenExtractor
from eyecite.tokenizers import EXTRACTORS, AhocorasickTokenizer

from mellea_lrc.core.spans import Span
from mellea_lrc.extraction.eyecite_extractor import (
    _assign_citation_ids,
    _build_antecedent_map,
    _get_citations_with_recovered_spans,
    _to_canonical,
)
from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument, ExtractionMetadata
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text_from_string

if TYPE_CHECKING:
    from eyecite.tokenizers import Tokenizer

    from mellea_lrc.preprocessing.types import PreprocessedDocument

# Reporter groups produced by eyecite's ``_relax_ws`` often end in ``\s*``
# themselves, so that variants like "U. S." still match. The original regex's
# literal trailing space forces such a group to give the space back on
# backtracking; replacing that space with ``\s*`` removes the pressure, and the
# group keeps it -- yielding reporter="U.S. " and a corrupted locator. The
# ``(?<!\s)`` assertion restores the pressure without requiring a space to be
# present, so the group still cannot end on whitespace. This works for the
# alternation-shaped groups too, where lifting the trailing ``\s*`` out by
# string surgery cannot reach every branch.
# The two joins are relaxed differently, and which one is right depends on what
# produced the text.
#
# Between volume and reporter, a break leaves reporter and page still adjacent
# on the far side, so the page that gets captured is the citation's own. Blank
# lines are always safe here, and needed: `937\n\nS.W.2d 796` is a real
# citation split by a page break.
#
# Between reporter and page, the page number is what lands beyond the break --
# which on pleading paper is where the margin line numbers are. Allowing a blank
# line there reads `214 F.3d\n\n1\n\n2\n\n3` as `214 F.3d 1` when the
# citation is `214 F.3d 1058`: not a miss but a *wrong page*, which sends
# validation to the wrong case and reports a confident verdict about it.
#
# That hazard is a property of the text, not of the tokenizer. Text produced by
# the structure-aware preprocessing has no margin left in it, and there the
# blank line between reporter and page means what it appears to mean. So the
# join is a parameter: bounded to a single newline by default, and opened up
# only for text whose margins have been removed. `PreprocessingMetadata.
# margin_line_numbers_dropped` records whether that ran, so the caller does not
# have to remember.
_ACROSS_BLOCKS = r"\s*"
_WITHIN_BLOCK = r"[^\S\r\n]*(?:\r?\n[^\S\r\n]*)?"


def _joins(*, cross_blank_lines: bool) -> tuple[tuple[str, str], ...]:
    """The two substitutions that relax a generated reporter pattern."""
    page_gap = _ACROSS_BLOCKS if cross_blank_lines else _WITHIN_BLOCK
    return (
        (r") (?P<reporter>", rf"){_ACROSS_BLOCKS}(?P<reporter>"),
        (r"),? (?P<page>", rf")(?<!\s),?{page_gap}(?P<page>"),
    )


def _relax(regex: str, joins: tuple[tuple[str, str], ...]) -> str:
    for old, new in joins:
        regex = regex.replace(old, new)
    return regex


class _RelaxedTokenizer(AhocorasickTokenizer):
    """Prefiltered tokenizer that honours its own extractor list.

    ``AhocorasickTokenizer`` builds its prefilter from the module-level
    ``EXTRACTORS``, so a tokenizer constructed with replacement extractors
    silently never runs them. Rebuilding the filters from ``self.extractors``
    keeps the prefilter -- without it every one of the ~6,800 extractors runs
    against every document, which is far too slow to be usable.
    """

    def __post_init__(self) -> None:
        self.unfiltered_extractors = {e for e in self.extractors if not e.strings}
        self.case_sensitive_filter = self._filter(case_sensitive=True)
        self.case_insensitive_filter = self._filter(case_sensitive=False)

    def _filter(self, *, case_sensitive: bool) -> ahocorasick.Automaton:
        pairs = [
            (s.replace(" ", "") if case_sensitive else s.replace(" ", "").lower(), e)
            for e in self.extractors
            if e.strings and bool(e.flags & re.I) is not case_sensitive
            for s in e.strings
        ]
        return self.make_ahocorasick_filter(pairs)


@lru_cache(maxsize=2)
def relaxed_tokenizer(*, cross_blank_lines: bool = False) -> Tokenizer:
    """Build a tokenizer whose reporter regexes tolerate separator whitespace.

    Set ``cross_blank_lines`` only for text whose page margins have been
    removed. On text that still holds them it reads a margin line number as the
    citation's page.
    """
    joins = _joins(cross_blank_lines=cross_blank_lines)
    return _RelaxedTokenizer(
        extractors=[
            TokenExtractor(
                regex=_relax(extractor.regex, joins),
                constructor=extractor.constructor,
                extra=extractor.extra,
                flags=extractor.flags,
                strings=extractor.strings,
            )
            for extractor in EXTRACTORS
        ]
    )


def _tokenizer_for(preprocessed: PreprocessedDocument) -> Tokenizer:
    """Pick the join width from how this document's text was produced.

    A document whose margins were removed records how many were removed, so
    ``None`` means the rule did not run and the wider join is not safe.
    """
    dropped = preprocessed.preprocessing_metadata.margin_line_numbers_dropped
    return relaxed_tokenizer(cross_blank_lines=dropped is not None)


def extract_relaxed(preprocessed: PreprocessedDocument) -> ExtractedDocument:
    """Extract canonical citations using layout-tolerant reporter matching.

    Returns an ordinary :class:`ExtractedDocument` whose spans index into
    ``preprocessed.text``.

    The baseline's whitespace-collapse step is kept even though a relaxed
    tokenizer no longer needs it to find doubled-space citations: keeping both
    backends on the same collapse-and-remap path means they stay directly
    comparable, and any normalization added there later applies to both.
    """
    text = preprocessed.text
    eyecite_citations = _get_citations_with_recovered_spans(text, tokenizer=_tokenizer_for(preprocessed))
    resolutions = cast(
        "dict[Resource, list[CitationBase]]",
        resolve_citations(eyecite_citations),
    )
    citation_ids = _assign_citation_ids(eyecite_citations)
    antecedent_map = _build_antecedent_map(resolutions, citation_ids)

    extracted: list[ExtractedCitation] = []
    for eyecite_citation, citation_id in citation_ids:
        span_start, span_end = eyecite_citation.full_span()
        locator_start, locator_end = eyecite_citation.span()
        extracted.append(
            ExtractedCitation(
                citation_id=citation_id,
                span=Span(start=span_start, end=span_end),
                locator_span=Span(start=locator_start, end=locator_end),
                matched_text=eyecite_citation.matched_text(),
                citation=_to_canonical(eyecite_citation),
                resolves_to=antecedent_map.get(citation_id),
            )
        )

    return ExtractedDocument(
        source_metadata=preprocessed.source_metadata,
        text=preprocessed.text,
        preprocessing_metadata=preprocessed.preprocessing_metadata,
        citations=tuple(extracted),
        extraction_metadata=ExtractionMetadata(),
    )


def extract_relaxed_citations(
    text: str,
    *,
    source_path: str | None = None,
    margins_removed: bool = False,
) -> ExtractedDocument:
    """Extract citations from raw Layer 2 text using the relaxed tokenizer.

    Plain text carries no record of how it was produced, so the wider
    reporter-to-page join has to be asserted by the caller. Set
    ``margins_removed`` only for text a structure-aware preprocessor produced;
    on text that still holds a page margin it reads a line number as the page.
    """
    document = preprocess_plain_text_from_string(text, source_path=source_path)
    if margins_removed:
        document = replace(
            document,
            preprocessing_metadata=replace(document.preprocessing_metadata, margin_line_numbers_dropped=0),
        )
    return extract_relaxed(document)
