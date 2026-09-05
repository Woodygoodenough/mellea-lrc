"""Typed document and node types for post-extraction validation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mellea_lrc.core.spans import Span
    from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster
    from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument


class ValidationNodeStatus(str, Enum):
    """Execution status of one validation operation."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


class LocatorLookupOutcome(str, Enum):
    """Typed outcomes of the exact locator lookup node."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED_CITATION = "unsupported_citation"
    INCOMPLETE_LOCATOR = "incomplete_locator"
    FAILED = "failed"


class FieldCheckOutcome(str, Enum):
    """Deterministic comparison outcome for one citation field."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"


class MelleaCaseNameCheckOutcome(str, Enum):
    """Outcomes of semantic comparison after an exact case-name mismatch."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MelleaCaseNameReextractionOutcome(str, Enum):
    """Results of Mellea re-extracting locally grounded case parties."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MelleaCaseNameQueryPreparationOutcome(str, Enum):
    """Results of preparing a CourtListener query from re-extracted parties."""

    PREPARED = "prepared"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class OpinionSearchOutcome(str, Enum):
    """Results of searching CourtListener's opinion corpus."""

    SEARCHED = "searched"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class RecapSearchOutcome(str, Enum):
    """Results of searching CourtListener's RECAP corpus."""

    SEARCHED = "searched"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class DocketCourtRetrievalOutcome(str, Enum):
    """Results of retrieving a CourtListener docket's court identifier."""

    FOUND = "found"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class CaseNameAgreement(str, Enum):
    """How the case name a filing wrote relates to the one a record holds."""

    EXACT = "exact"
    """Equal after whitespace and case folding."""
    CONTAINED = "contained"
    """Every distinctive word the filing wrote is in the record, side by side."""
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    """One side wrote no name, or no distinctive word survives normalisation."""

    @property
    def agrees(self) -> bool:
        """Whether the rule counts this as the same name."""
        return self in (CaseNameAgreement.EXACT, CaseNameAgreement.CONTAINED)


class IdentityScope(str, Enum):
    """Whether a citation's identity is checked, and if not, why not."""

    ROOT_CASE = "root_case"
    """A full case citation that introduces its authority. Checked by locator."""
    ROOT_DOCKET = "root_docket"
    """A docket citation that introduces its authority. Its route is not built yet."""
    NON_ROOT = "non_root"
    """Refers to an authority another citation introduced, and inherits its identity."""
    OUT_OF_SCOPE = "out_of_scope"
    """Names no case: a statute, a journal, or a span that could not be parsed."""


class DatePrecision(str, Enum):
    """How much of a date the filing stated, which is how much is compared."""

    YEAR = "year"
    DAY = "day"


class IdentityVerdict(str, Enum):
    """A model's answer to whether the filing and the record name one case."""

    SAME_CASE = "same_case"
    DIFFERENT_CASE = "different_case"
    UNDETERMINABLE = "undeterminable"
    FAILED = "failed"


class FieldAgreement(str, Enum):
    """A model's answer about one field, read from the filing's context."""

    AGREE = "agree"
    DISAGREE = "disagree"
    UNDETERMINABLE = "undeterminable"
    VARIANT = "variant"
    """The same case, named defectively: a misspelt or garbled party, a party
    dropped. Case name only. Counts as agreement for identity and as a defect."""


class IdentityOutcome(str, Enum):
    """What the identity stage concluded about one root citation.

    Four answers, and one reason under each that says why. `WRONG_IDENTITY` is
    the wide one: the locator names a different case, or names the right case
    and a field the filing states disagrees with it. Both are the filing citing
    something other than what it says, and the reason and the fields under the
    node keep them apart.
    """

    CONFIRMED_IDENTITY = "confirmed_identity"
    """The locator names one case and every field the filing states agrees with it."""
    WRONG_IDENTITY = "wrong_identity"
    """The locator names a different case, or the right case with a field the filing misstates."""
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    """Several distinct cases remain at the locator after merging duplicates and narrowing by name."""
    DEFER_TO_SEARCH = "defer_to_search"
    """Nothing the lookup route can decide: nothing at the locator, a docket citation, a judgement that could not decide."""


class IdentityReason(str, Enum):
    """Why an identity outcome is what it is."""

    DIFFERENT_CASE_AT_LOCATOR = "different_case_at_locator"
    FIELD_DISAGREEMENT = "field_disagreement"
    CROWDED_PAGE = "crowded_page"
    NOT_FOUND = "not_found"
    LOOKUP_FAILED = "lookup_failed"
    UNDETERMINABLE = "undeterminable"
    DOCKET = "docket"


@dataclass(frozen=True, slots=True)
class FieldDisagreement:
    """One field the filing states that does not agree with the resolved record."""

    field: str
    filing_value: str | None
    record_value: str | None
    agreement: FieldAgreement
    """``disagree`` or ``variant``, as the judgement or the rule answered."""


class AuthorityMergeOutcome(str, Enum):
    """What became of a root that shares its text position with another root."""

    MERGED_INTO = "merged_into"
    """Both locators resolved to one cluster, so this root now refers to the other."""
    KEPT = "kept"
    """The locators resolved to different clusters, or one did not resolve."""


class DocketIdentityOutcome(str, Enum):
    """Results of identifying a case by docket number and court."""

    NOT_IMPLEMENTED = "not_implemented"


class ReporterPageRetrievalOutcome(str, Enum):
    """Results of retrieving a reporter page from citation-aware opinion HTML."""

    FOUND = "found"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MelleaPinpointCheckOutcome(str, Enum):
    """Semantic support findings from one retrieved reporter page."""

    SUPPORTS = "supports"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MelleaCitingPropositionExtractionOutcome(str, Enum):
    """Results of identifying the proposition attributed to one citation."""

    IDENTIFIED = "identified"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class EvidenceQuoteMatchMethod(str, Enum):
    """How a model-proposed quote was grounded in retrieved page text."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"


class CandidateSelectionOutcome(str, Enum):
    """Results of applying the bounded candidate-validation guard."""

    ALL_SELECTED = "all_selected"
    DEFERRED_OVER_LIMIT = "deferred_over_limit"
    NARROWED_BY_CASE_NAME = "narrowed_by_case_name"
    """Too many candidates to evaluate, but the filing's own case name picks out
    a few of them.

    A page of unpublished decisions holds many unrelated cases, so the volume
    and page cannot choose between them and the case name can. Reaching this
    outcome means the name matched; failing to match is not recorded here,
    because it does not distinguish a filing naming a case that is not on the
    page from an archive holding only part of the page.
    """


class CandidateEvaluationOutcome(str, Enum):
    """Readiness of one independently evaluable retrieved candidate."""

    READY = "ready"


class CandidateEvaluationSource(str, Enum):
    """Retrieval route that produced a candidate evaluation node."""

    LOCATOR_LOOKUP = "locator_lookup"
    OPINION_SEARCH = "opinion_search"
    RECAP_SEARCH = "recap_search"


class AggregatedFieldOutcome(str, Enum):
    """Field-level outcome projected into a candidate assessment."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class LocatorCandidateAssessmentOutcome(str, Enum):
    """Overall conclusion for one uniquely located opinion candidate."""

    MATCH = "match"
    MISMATCH = "mismatch"
    PARTIAL_MATCH = "partial_match"


class LocatorCitationSummaryOutcome(str, Enum):
    """Completion state of the unique-locator citation summary."""

    COMPLETE = "complete"


class SearchCandidateAssessmentOutcome(str, Enum):
    """Limited conclusion for one candidate returned by a search."""

    POSSIBLE_MATCH = "possible_match"
    MISMATCH = "mismatch"


CandidateAssessmentOutcome: TypeAlias = LocatorCandidateAssessmentOutcome | SearchCandidateAssessmentOutcome


class CandidateProvenance(str, Enum):
    """CourtListener corpus that produced a summarized candidate."""

    OPINION = "opinion"
    RECAP = "recap"


class CitationSummaryAssessmentOutcome(str, Enum):
    """Strongest candidate conclusion exposed at citation scope."""

    MATCH = "match"
    POSSIBLE_MATCH = "possible_match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"


class SearchCitationSummaryOutcome(str, Enum):
    """Completion state of a search-derived citation summary."""

    COMPLETE = "complete"


MIN_AMBIGUOUS_CANDIDATE_COUNT = 2


@dataclass(frozen=True, slots=True)
class ExactLocatorLookupNode:
    """One exact reporter-locator lookup against CourtListener.

    Only ``FOUND`` continues into the currently implemented branch. Other
    outcomes are explicit terminal nodes, not implicit fallback behavior.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: LocatorLookupOutcome
    locator: str | None
    cluster: CourtListenerOpinionCluster | None = None
    candidate_clusters: tuple[CourtListenerOpinionCluster, ...] = ()
    candidate_count: int = 0
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.node_id:
            msg = "Validation node_id must not be empty"
            raise ValueError(msg)
        if self.outcome is LocatorLookupOutcome.FOUND:
            if self.status is not ValidationNodeStatus.SUCCEEDED or self.cluster is None:
                msg = "A found locator node requires a succeeded status and one cluster"
                raise ValueError(msg)
            if self.candidate_count != 1:
                msg = "A found locator node requires candidate_count=1"
                raise ValueError(msg)
        elif self.outcome is LocatorLookupOutcome.AMBIGUOUS:
            if (
                self.status is not ValidationNodeStatus.SUCCEEDED
                or self.cluster is not None
                or self.candidate_count < MIN_AMBIGUOUS_CANDIDATE_COUNT
                or len(self.candidate_clusters) != self.candidate_count
            ):
                msg = "An ambiguous locator node requires its complete candidate clusters"
                raise ValueError(msg)
        elif self.cluster is not None or self.candidate_clusters:
            msg = "Only a found or ambiguous locator node may carry candidate clusters"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ExactCaseNameCheckNode:
    """Exact normalized case-name comparison after a found locator lookup."""

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    extracted_case_name: str | None
    retrieved_case_name: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaCaseNameCheckNode:
    """Mellea semantic comparison of otherwise unmatched case names."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaCaseNameCheckOutcome
    extracted_case_name: str
    retrieved_case_name: str
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaCaseNameReextractionNode:
    """Plaintiff and defendant re-extracted from citation-local text by Mellea."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaCaseNameReextractionOutcome
    plaintiff: str | None
    defendant: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaCaseNameQueryPreparationNode:
    """Mellea-prepared terms and deterministic query for candidate retrieval."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaCaseNameQueryPreparationOutcome
    query: str | None
    query_plaintiff: str | None
    query_defendant: str | None
    court_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None
    year: str | None = None
    """The year the citation states, when it states one, and the query used it.

    Recorded because it changes what a miss means. A search narrowed to a range
    of years that finds nothing has not established that the case is absent,
    only that it is absent from those years, and a reader of the result has to
    be able to tell the two apart.
    """


@dataclass(frozen=True, slots=True)
class OpinionSearchNode:
    """One CourtListener opinion-corpus search from prepared case-name terms."""

    node_id: str
    status: ValidationNodeStatus
    outcome: OpinionSearchOutcome
    query: str | None
    result_count: int | None
    results: tuple[Mapping[str, object], ...]
    next_cursor: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RecapSearchNode:
    """One CourtListener RECAP-corpus search from prepared case-name terms."""

    node_id: str
    status: ValidationNodeStatus
    outcome: RecapSearchOutcome
    query: str | None
    result_count: int | None
    results: tuple[Mapping[str, object], ...]
    next_cursor: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateSelectionNode:
    """Bounded decision on whether one retrieval result set may be evaluated."""

    node_id: str
    status: ValidationNodeStatus
    outcome: CandidateSelectionOutcome
    total_candidate_count: int
    selected_candidate_count: int
    selection_limit: int
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    selected_indices: tuple[int, ...] | None = None
    """Which candidates were chosen, when the choice is not simply the first few.

    ``None`` means the leading ``selected_candidate_count`` records, which is
    what a count-based decision produces. A selection made by matching the
    filing's case name picks particular records out of the middle of a long
    list, and those positions have to travel with the decision.
    """
    distinct_case_count: int | None = None
    """How many separate cases the returned records amount to, when known.

    A citation lookup often returns the same decision more than once, so
    `total_candidate_count` counts records rather than cases. The limit is
    applied to this figure where it is available, and both are kept so the
    difference between them is visible in the record rather than inferred.
    """


@dataclass(frozen=True, slots=True)
class CandidateEvaluationNode:
    """One selected retrieved candidate made ready for field-check subtrees."""

    node_id: str
    status: ValidationNodeStatus
    outcome: CandidateEvaluationOutcome
    source: CandidateEvaluationSource
    candidate_index: int
    cluster_id: str | None
    case_name: str | None
    date_filed: str | None
    court_id: str | None
    docket_id: str | None
    record: CourtListenerOpinionCluster | Mapping[str, object]
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None

    @property
    def year(self) -> str | None:
        """Return the filed-year prefix when the opinion result provides one."""
        return self.date_filed[:4] if self.date_filed else None


@dataclass(frozen=True, slots=True)
class MelleaReextractedCaseNameCheckNode:
    """Semantic comparison using re-extracted plaintiff and defendant evidence."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaCaseNameCheckOutcome
    reextracted_case_name: str | None
    retrieved_case_name: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DocketCourtRetrievalNode:
    """Court identifier retrieved from the docket linked to a found citation."""

    node_id: str
    status: ValidationNodeStatus
    outcome: DocketCourtRetrievalOutcome
    docket_id: str | None
    court_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CourtCheckNode:
    """Exact comparison of Eyecite and CourtListener court identifiers."""

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    extracted_court_id: str | None
    retrieved_court_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class ReporterPageEvidence:
    """One reporter page recovered from a CourtListener sub-opinion."""

    opinion_id: str
    opinion_type: str
    text: str


@dataclass(frozen=True, slots=True)
class ReporterPageRetrievalNode:
    """Serialization-ready reporter-page evidence for one opinion candidate."""

    node_id: str
    status: ValidationNodeStatus
    outcome: ReporterPageRetrievalOutcome
    cluster_id: str | None
    reporter_citation: str | None
    pin_cite: str | None
    citation_index: int | None
    evidence: ReporterPageEvidence | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaCitingPropositionExtractionNode:
    """Grounded citing proposition and its offsets in the source document."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaCitingPropositionExtractionOutcome
    context_span: Span
    reasoning: str | None
    proposition: str | None
    proposition_span: Span | None
    proposition_match_method: EvidenceQuoteMatchMethod | None
    proposition_match_score: float | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaPinpointCheckNode:
    """Semantic judgment with evidence offsets into its retrieval dependency's page text."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaPinpointCheckOutcome
    reasoning: str | None
    evidence_quote: str | None
    evidence_span: Span | None
    evidence_match_method: EvidenceQuoteMatchMethod | None
    evidence_match_score: float | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LocatorCandidateAssessmentNode:
    """Table-ready conclusion for the one candidate from a found locator."""

    node_id: str
    status: ValidationNodeStatus
    outcome: LocatorCandidateAssessmentOutcome
    candidate_index: int
    extracted_citation: str | None
    extracted_case_name: str | None
    retrieved_case_name: str | None
    case_name_outcome: AggregatedFieldOutcome
    case_name_evidence: str
    extracted_year: str | None
    retrieved_year: str | None
    year_outcome: AggregatedFieldOutcome
    extracted_court_id: str | None
    retrieved_court_id: str | None
    court_outcome: AggregatedFieldOutcome
    docket_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class CitationSummaryPinpoint:
    """Frontend-ready projection of one candidate's pinpoint comparison."""

    node_id: str
    status: ValidationNodeStatus
    outcome: MelleaPinpointCheckOutcome
    reporter_citation: str | None
    pin_cite: str | None
    opinion_id: str | None
    opinion_type: str | None
    reporter_page_text: str | None
    citing_context_span: Span
    citation_span: Span
    proposition: str | None
    proposition_span: Span | None
    reasoning: str | None
    evidence_quote: str | None
    evidence_span: Span | None
    evidence_match_method: EvidenceQuoteMatchMethod | None
    evidence_match_score: float | None
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CitationSummaryCandidate:
    """Frontend-ready, provenance-tagged candidate exposed by a citation summary."""

    provenance: CandidateProvenance
    candidate_index: int
    assessment_node_id: str
    outcome: CandidateAssessmentOutcome
    extracted_citation: str | None
    extracted_case_name: str | None
    retrieved_case_name: str | None
    case_name_outcome: AggregatedFieldOutcome
    case_name_evidence: str
    extracted_year: str | None
    retrieved_year: str | None
    year_outcome: AggregatedFieldOutcome
    extracted_court_id: str | None
    retrieved_court_id: str | None
    court_outcome: AggregatedFieldOutcome
    docket_id: str | None
    opinion_url: str | None = None
    docket_url: str | None = None
    pinpoint: CitationSummaryPinpoint | None = None


@dataclass(frozen=True, slots=True)
class LocatorCitationSummaryNode:
    """Terminal list of every fully evaluated candidate from one locator route."""

    node_id: str
    status: ValidationNodeStatus
    outcome: LocatorCitationSummaryOutcome
    overall_outcome: CitationSummaryAssessmentOutcome | None
    pinpoint_requires_review: bool | None
    candidates: tuple[CitationSummaryCandidate, ...]
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class OpinionSearchCandidateAssessmentNode:
    """Serialization-ready conclusion for one opinion-search candidate."""

    node_id: str
    status: ValidationNodeStatus
    outcome: SearchCandidateAssessmentOutcome
    candidate_index: int
    extracted_citation: str | None
    extracted_case_name: str | None
    retrieved_case_name: str | None
    case_name_outcome: AggregatedFieldOutcome
    case_name_evidence: str
    extracted_year: str | None
    retrieved_year: str | None
    year_outcome: AggregatedFieldOutcome
    extracted_court_id: str | None
    retrieved_court_id: str | None
    court_outcome: AggregatedFieldOutcome
    docket_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class RecapSearchCandidateAssessmentNode:
    """Serialization-ready conclusion for one RECAP-search candidate."""

    node_id: str
    status: ValidationNodeStatus
    outcome: SearchCandidateAssessmentOutcome
    candidate_index: int
    extracted_citation: str | None
    extracted_case_name: str | None
    retrieved_case_name: str | None
    case_name_outcome: AggregatedFieldOutcome
    case_name_evidence: str
    extracted_year: str | None
    retrieved_year: str | None
    year_outcome: AggregatedFieldOutcome
    extracted_court_id: str | None
    retrieved_court_id: str | None
    court_outcome: AggregatedFieldOutcome
    docket_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class SearchCitationSummaryNode:
    """Terminal list of assessed candidates from both search corpora."""

    node_id: str
    status: ValidationNodeStatus
    outcome: SearchCitationSummaryOutcome
    overall_outcome: CitationSummaryAssessmentOutcome | None
    candidates: tuple[CitationSummaryCandidate, ...]
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class YearCheckNode:
    """Deterministic decision-year comparison after a found locator lookup."""

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    extracted_year: str | None
    retrieved_year: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityScopeNode:
    """Whether this citation's identity is checked, decided from the citation tree."""

    node_id: str
    status: ValidationNodeStatus
    outcome: IdentityScope
    authority_id: str | None
    colocation_id: str | None
    depends_on: tuple[str, ...] = ()
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class DateCheckNode:
    """Comparison of the date a filing states with a record's, at the precision stated."""

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    precision: DatePrecision | None
    extracted_date: str | None
    retrieved_date: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class CaseNameAgreementNode:
    """Rule-based comparison of the written and recorded case names."""

    node_id: str
    status: ValidationNodeStatus
    outcome: CaseNameAgreement
    written_case_name: str | None
    recorded_case_name: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaIdentityJudgmentNode:
    """One composite model judgement over every field the rules disagreed on.

    The model reads the filing's context, not the two strings, and states for
    each field what the filing says and whether it agrees with the record. The
    verdict is about identity -- the same case or not -- and a deterministic
    requirement holds it to the field answers, so a verdict the answers do not
    support is repaired rather than recorded.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: IdentityVerdict
    case_name_read: str | None
    case_name_agreement: FieldAgreement | None
    court_read: str | None
    court_agreement: FieldAgreement | None
    date_read: str | None
    date_agreement: FieldAgreement | None
    reason: str | None
    depends_on: tuple[str, ...]
    model: str | None = None
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityResolutionNode:
    """The stage's conclusion for one root, and how it was reached."""

    node_id: str
    status: ValidationNodeStatus
    outcome: IdentityOutcome
    reason: IdentityReason | None
    """Why. ``None`` only on a confirmed identity."""
    cluster_id: str | None
    """The record the conclusion is about: the resolved case, or the different case at the locator."""
    record_case_name: str | None
    decided_by: str | None
    """``rule`` when no model was consulted, else the judgement node's identifier."""
    fields: tuple[FieldDisagreement, ...]
    """Each field the filing states that disagrees with the record, with both values."""
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None

    @property
    def resolved(self) -> bool:
        """Whether the locator identified the filing's case, defects or not."""
        return self.outcome is IdentityOutcome.CONFIRMED_IDENTITY or (
            self.outcome is IdentityOutcome.WRONG_IDENTITY
            and self.reason is IdentityReason.FIELD_DISAGREEMENT
        )


@dataclass(frozen=True, slots=True)
class AuthorityMergeNode:
    """Decision on a root that shares a text position with an earlier root."""

    node_id: str
    status: ValidationNodeStatus
    outcome: AuthorityMergeOutcome
    colocation_id: str
    target_citation_id: str | None
    cluster_id: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class DocketIdentityNode:
    """Identity of a case cited by docket number. The route is recorded, not run."""

    node_id: str
    status: ValidationNodeStatus
    outcome: DocketIdentityOutcome
    docket_number: str | None
    court_id: str | None
    depends_on: tuple[str, ...] = ()
    status_message: str | None = None
    outcome_message: str | None = None


# Expand this union as operation-specific validation nodes are introduced.
ValidationNode: TypeAlias = (
    ExactLocatorLookupNode
    | ExactCaseNameCheckNode
    | MelleaCaseNameCheckNode
    | MelleaCaseNameReextractionNode
    | MelleaCaseNameQueryPreparationNode
    | OpinionSearchNode
    | RecapSearchNode
    | CandidateSelectionNode
    | CandidateEvaluationNode
    | MelleaReextractedCaseNameCheckNode
    | DocketCourtRetrievalNode
    | ReporterPageRetrievalNode
    | MelleaCitingPropositionExtractionNode
    | MelleaPinpointCheckNode
    | CourtCheckNode
    | LocatorCandidateAssessmentNode
    | LocatorCitationSummaryNode
    | OpinionSearchCandidateAssessmentNode
    | RecapSearchCandidateAssessmentNode
    | SearchCitationSummaryNode
    | YearCheckNode
    | IdentityScopeNode
    | DateCheckNode
    | CaseNameAgreementNode
    | MelleaIdentityJudgmentNode
    | IdentityResolutionNode
    | AuthorityMergeNode
    | DocketIdentityNode
)


@dataclass(frozen=True, slots=True)
class CitationValidation:
    """Ordered validation-node progression for one extracted citation."""

    citation: ExtractedCitation
    nodes: tuple[ValidationNode, ...] = ()

    @property
    def citation_id(self) -> str:
        """Return the stable identifier from extraction."""
        return self.citation.citation_id

    def append(self, node: ValidationNode) -> CitationValidation:
        """Return a new citation validation with one node appended."""
        if not node.node_id:
            msg = "Validation node_id must not be empty"
            raise ValueError(msg)
        known_ids = {item.node_id for item in self.nodes}
        if node.node_id in known_ids:
            msg = f"Duplicate validation node_id: {node.node_id!r}"
            raise ValueError(msg)
        if any(dependency not in known_ids for dependency in node.depends_on):
            msg = f"Validation node {node.node_id!r} has an unknown dependency"
            raise ValueError(msg)
        return replace(self, nodes=(*self.nodes, node))

    @property
    def aggregation(self) -> LocatorCitationSummaryNode | SearchCitationSummaryNode | None:
        """Return the route's terminal citation summary when one was produced."""
        summaries = tuple(
            node
            for node in self.nodes
            if isinstance(node, (LocatorCitationSummaryNode, SearchCitationSummaryNode))
        )
        return summaries[0] if len(summaries) == 1 else None


@dataclass(frozen=True, slots=True)
class ValidatedDocument:
    """Post-extraction validation state for every citation in one document."""

    source: ExtractedDocument
    citations: tuple[CitationValidation, ...]

    def __post_init__(self) -> None:
        source_ids = tuple(item.citation_id for item in self.source.citations)
        validation_ids = tuple(item.citation_id for item in self.citations)
        if validation_ids != source_ids:
            msg = "Citation validations must exactly match extracted citations in order"
            raise ValueError(msg)

    @property
    def text(self) -> str:
        """Return the immutable extracted-document text."""
        return self.source.text

    def citation_by_id(self, citation_id: str) -> CitationValidation:
        """Return one citation's validation progression."""
        for citation in self.citations:
            if citation.citation_id == citation_id:
                return citation
        msg = f"Unknown citation validation id: {citation_id!r}"
        raise KeyError(msg)
