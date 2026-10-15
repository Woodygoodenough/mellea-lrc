"""Full citation types and their source-grounded field histories."""

from typing import Annotated, TypeAlias

from pydantic import Field

from mellea_lrc.model.citations.citation import Citation
from mellea_lrc.model.citations.fields import (
    CaseName,
    CaseNameField,
    CaseNameKind,
    CitationDate,
    CitationField,
    Court,
    CourtField,
    DateField,
    DocketEntryField,
    DocketLocatorValue,
    FullDocketLocator,
    FullReporterLocator,
    PinCiteField,
    PinCiteKind,
    PinCiteTarget,
    PinCiteValue,
    ReporterLocatorValue,
)
from mellea_lrc.model.citations.full import FullCitation
from mellea_lrc.model.citations.full_docket import FullDocketCitation
from mellea_lrc.model.citations.full_reporter import FullReporterCitation
from mellea_lrc.model.citations.history import Node, RelationshipUpdate, latest
from mellea_lrc.model.citations.kind import FullCitationKind
from mellea_lrc.model.citations.tags import CitationTag, CitationTagKind

FullCitationVariant: TypeAlias = Annotated[
    FullReporterCitation | FullDocketCitation, Field(discriminator="kind")
]

__all__ = [
    "CaseName",
    "CaseNameField",
    "CaseNameKind",
    "Citation",
    "CitationDate",
    "CitationField",
    "CitationTag",
    "CitationTagKind",
    "Court",
    "CourtField",
    "DateField",
    "DocketEntryField",
    "DocketLocatorValue",
    "FullCitation",
    "FullCitationKind",
    "FullCitationVariant",
    "FullDocketCitation",
    "FullDocketLocator",
    "FullReporterCitation",
    "FullReporterLocator",
    "Node",
    "PinCiteField",
    "PinCiteKind",
    "PinCiteTarget",
    "PinCiteValue",
    "RelationshipUpdate",
    "ReporterLocatorValue",
    "latest",
]
