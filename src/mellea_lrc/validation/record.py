"""The one mutable object in validation: a citation as it is being corrected.

Extraction produces frozen citations, and everything downstream of it appends
frozen nodes to a trace. That is the right shape for evidence. It is the wrong
shape for the thing the evidence is *about*, which changes as validation
proceeds: a model re-reads the filing and finds that the extractor took the
court from the citation after this one, a lookup shows which of two co-located
locators introduced the authority, and by the end the citation the pipeline
holds is not the one extraction produced.

So the record is mutable, with three rules that keep it auditable.

**The original is never touched.** ``source`` is the extracted citation as it
arrived, and ``citation`` is the pipeline's current reading of what the filing
states. A reader comparing the two sees what validation changed.

**Every change is logged with the node that justified it.** A correction
carries the field, both values, who made it -- a rule by name, or a model and
which one -- and the identifier of the trace node holding the evidence. A
correction with no node is refused.

**What the filing states and what the archive holds are kept apart.**
``citation`` is only ever the filing's reading. The archive's answer -- which
cluster, under what name, decided when and where -- goes on ``resolution``. A
filing citing the right case under the wrong year keeps its wrong year on
``citation`` and gets the right one on ``resolution``, and the disagreement
between them is the finding. Overwriting the filing's field with the archive's
would erase the defect the pipeline exists to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mellea_lrc.validation.types import CitationValidation

if TYPE_CHECKING:
    from mellea_lrc.core.citations import CanonicalCitation
    from mellea_lrc.courtlistener import CourtListenerOpinion
    from mellea_lrc.extraction.types import ExtractedCitation
    from mellea_lrc.validation.types import ValidationNode


@dataclass(frozen=True, slots=True)
class Correction:
    """One change to the record, and the evidence it rests on."""

    field: str
    """Which field changed: a citation field such as ``court``, or ``authority_id``."""
    before: object
    after: object
    made_by: str
    """A rule, by module name, or a model, by the name the session reports."""
    reason: str
    node_id: str
    """The trace node holding the evidence. Refused when empty."""

    def __post_init__(self) -> None:
        if not self.node_id:
            msg = "A correction must name the trace node that justifies it"
            raise ValueError(msg)
        if self.before == self.after:
            msg = f"A correction to {self.field!r} must change the value"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DateExploration:
    """Everything read about a record's dates while resolving, kept for a later step.

    Written programmatically, whether or not the date reconciled: the date the
    filing stated and at what precision, the record's filing date, the
    cluster's free-text other dates, the dated phrases found in each opinion
    header read, and the phrase that matched when one did. A wrong identity
    whose only disagreeing field is the date is a strong sign the case is real
    and the dates differ for a reason -- an amendment the archive does not
    hold, a term-year convention, a rehearing -- and that reason has to be
    found from what was read, not from the verdict alone.

    TODO(date-analysis): the step that reads this history is not written. It
    would take the records ``IdentifiedDocument.date_only_disagreements``
    returns and decide, per record, what the disagreement is: the archive's
    coverage, a convention, or the filing's error. Nothing here decides that;
    this is the evidence it will need, kept in the shape it was found.
    """

    stated: str
    """The date the filing states, ``YYYY`` or ``YYYY-MM-DD``."""
    stated_precision: str
    """``year`` or ``day``."""
    record_date_filed: str | None
    other_dates: str | None
    """The cluster's free-text dates, verbatim, when fetched."""
    phrases_by_opinion: tuple[tuple[str, tuple[str, ...]], ...]
    """For each opinion header read, in order: its id and the dated events found in it."""
    matched_phrase: str | None
    matched_opinion_id: str | None
    """The opinion whose header stated the filing's year, or None when the cluster did or nothing did."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """What the archive holds at the identity the filing cited."""

    cluster_id: str | None
    case_name: str | None
    date_filed: str | None
    court_id: str | None
    node_id: str
    """The trace node that established this resolution."""
    opinion_ids: tuple[str, ...] = ()
    """The cluster's opinions already fetched while resolving, the one that
    answered first. A later stage that needs the opinion's text starts here
    rather than resolving the cluster's opinions again."""
    dates: DateExploration | None = None
    """What was read about the record's dates, when the plain comparison disagreed."""


@dataclass(slots=True)
class CitationRecord:
    """One citation's current state, its original, and the trace between them."""

    source: ExtractedCitation
    citation: CanonicalCitation
    authority_id: str | None
    resolution: Resolution | None = None
    corrections: tuple[Correction, ...] = ()
    trace: CitationValidation = field(init=False)
    opinions: dict[str, CourtListenerOpinion] = field(init=False, default_factory=dict)
    """Opinion text fetched while resolving, by opinion id. Not serialized:
    a stage starting from an artifact refetches by the ids on the resolution,
    which the proxy serves from cache."""

    def __post_init__(self) -> None:
        self.trace = CitationValidation(citation=self.source)

    @classmethod
    def from_extracted(cls, source: ExtractedCitation) -> CitationRecord:
        """Start a record from what extraction produced, unchanged."""
        return cls(source=source, citation=source.citation, authority_id=source.authority_id)

    @property
    def citation_id(self) -> str:
        """The identifier extraction assigned, which never changes."""
        return self.source.citation_id

    @property
    def is_root(self) -> bool:
        """Whether this citation introduces the authority it refers to."""
        return self.authority_id == self.citation_id

    def append(self, node: ValidationNode) -> ValidationNode:
        """Add one node to the trace, returning it so a caller can depend on it."""
        self.trace = self.trace.append(node)
        return node

    def correct_field(self, name: str, value: object, *, made_by: str, reason: str, node_id: str) -> None:
        """Change one field of the filing's reading, logging why."""
        before = getattr(self.citation, name)
        self._require_node(node_id)
        correction = Correction(
            field=name, before=before, after=value, made_by=made_by, reason=reason, node_id=node_id
        )
        self.citation = replace(self.citation, **{name: value})
        self.corrections = (*self.corrections, correction)

    def reattribute(self, authority_id: str, *, made_by: str, reason: str, node_id: str) -> None:
        """Point this citation at a different authority, logging why."""
        self._require_node(node_id)
        correction = Correction(
            field="authority_id",
            before=self.authority_id,
            after=authority_id,
            made_by=made_by,
            reason=reason,
            node_id=node_id,
        )
        self.authority_id = authority_id
        self.corrections = (*self.corrections, correction)

    def resolve(self, resolution: Resolution) -> None:
        """Record what the archive holds, once. A second resolution is a bug."""
        if self.resolution is not None:
            msg = f"Citation {self.citation_id!r} is already resolved"
            raise ValueError(msg)
        self._require_node(resolution.node_id)
        self.resolution = resolution

    def _require_node(self, node_id: str) -> None:
        if not any(node.node_id == node_id for node in self.trace.nodes):
            msg = f"Node {node_id!r} is not in the trace of citation {self.citation_id!r}"
            raise ValueError(msg)
