"""Citation extraction from Layer 2 preprocessed legal text.

Three entrypoints, differing only in where the text comes from:

``extract``
    The front door. A :class:`str` is content, a :class:`~pathlib.Path` is a
    location, and it dispatches to one of the two below.

``extract_from_plain_text``
    Layer 2 text already in hand.

``extract_from_raw_document``
    A file on disk, preprocessed first by the backend its format calls for.

There is deliberately no entrypoint taking a ``PreprocessedDocument``. Nothing
serializes one, so it cannot cross a process boundary, and a caller holding one
is already inside the library.

All three take the same ``relaxation`` keyword, which is the one thing that
decides how much whitespace damage a citation may carry and still be found.
There is no separate relaxed extractor and no text repair anywhere behind them:
one code path, one parameter. See :class:`Relaxation` for the three levels and
what each one costs.

## How the layer is arranged

Four kinds of thing, and they were worth separating because they answer
different questions.

``eyecite_extractor``, ``pipeline``, ``types``
    The entrypoints and the vocabulary. `eyecite_extractor` is the one place
    that calls everything else, in the order the comments there give.

:mod:`~mellea_lrc.extraction.reading`
    What eyecite is made to read. Every correction to how the library parses
    text a PDF converter produced -- the reporter joins, pin cites, where the
    court-and-date scan stops, resolving a court, and reading a docket number
    as a locator.

:mod:`~mellea_lrc.extraction.structure`
    What the citations mean together once each is read: which occupy the same
    span, and which refer to the same authority. Neither looks at the text.

:mod:`~mellea_lrc.extraction.adjudication`
    What happens after the rules. Candidates the deterministic pass did not
    record, and the judgement that lets one into the record. Nothing above
    imports it, so a caller wanting only the deterministic reading never loads
    a reviewer.
"""

from mellea_lrc.extraction.eyecite_extractor import extract_from_plain_text
from mellea_lrc.extraction.pipeline import extract, extract_from_raw_document
from mellea_lrc.extraction.reading.relaxation import Relaxation
from mellea_lrc.extraction.types import (
    ExtractedCitation,
    ExtractedDocument,
    ExtractionBackend,
    ExtractionMetadata,
)

__all__ = [
    "ExtractedCitation",
    "ExtractedDocument",
    "ExtractionBackend",
    "ExtractionMetadata",
    "Relaxation",
    "extract",
    "extract_from_plain_text",
    "extract_from_raw_document",
]
