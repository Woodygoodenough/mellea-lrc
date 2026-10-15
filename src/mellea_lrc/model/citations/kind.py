"""Kinds of full case citations."""

from enum import Enum


class FullCitationKind(str, Enum):
    REPORTER = "reporter"
    DOCKET = "docket"
