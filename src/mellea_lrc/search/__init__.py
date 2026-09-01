"""The search stage as a loop, and the moves it is allowed to make.

Section 1 of `exploration/notes/agentic-search-handoff.md` says what the loop
is for and `agentic-search-population.md` carries the counts behind it.
"""

from mellea_lrc.search.narrowing import (
    YEAR_TOLERANCE,
    CandidateFacts,
    CitationFacts,
    NarrowedCandidate,
    Narrowing,
    NarrowingOutcome,
    narrow,
)

__all__ = [
    "YEAR_TOLERANCE",
    "CandidateFacts",
    "CitationFacts",
    "NarrowedCandidate",
    "Narrowing",
    "NarrowingOutcome",
    "narrow",
]
