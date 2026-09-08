"""A docket number with a court is a key; two archives answer it."""

from mellea_lrc.validation.docket_lookup.lookup import (
    ArchiveAnswer,
    DocketDecision,
    DocketRecord,
    lookup_docket,
)
from mellea_lrc.validation.docket_lookup.numbers import docket_core, docket_number_matches

__all__ = [
    "ArchiveAnswer",
    "DocketDecision",
    "DocketRecord",
    "docket_core",
    "docket_number_matches",
    "lookup_docket",
]
