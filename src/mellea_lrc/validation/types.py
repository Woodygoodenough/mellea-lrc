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
    COMPATIBLE = "compatible"
    """The filing states no value, and what it implies does not conflict with the record.

    A citation to `61 N.C. App. 134` names no court, but the reporter holds
    North Carolina's appellate courts and no others; a record from one of them
    is compatible, a record from a Texas district court is a mismatch. Counts
    as agreement, and is kept apart from a match because nothing was read.
    """


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
    """The same case under an equivalent caption: a relator form, a party under
    another role, a caption one side truncated. Case name only. Counts as
    agreement and is disclosed; it is not a defect of the filing."""
    MISSPELT = "misspelt"
    """The same case with a party the filing spells wrongly. Case name only.
    Counts as agreement for identity and as a defect of the filing."""
    COMPATIBLE = "compatible"
    """The filing states no value, and what the reporter implies does not
    conflict with the record. Court only. Counts as agreement."""


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
    """``disagree`` or ``misspelt``, as the judgement or the rule answered."""


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


class PinpointScope(str, Enum):
    """Whether a citation's pin cite can be checked against a reporter page at all."""

    IN_SCOPE = "in_scope"
    NO_PIN_CITE = "no_pin_cite"
    NO_AUTHORITY = "no_authority"
    """The citation is attributed to no authority, or the authority is not a case."""
    IDENTITY_NOT_ESTABLISHED = "identity_not_established"
    """The authority's identity was refuted, deferred or left ambiguous, so there is no page to cut."""
    PIN_FORM = "pin_form"
    """A star page, paragraph, section or other pin that names no reporter page."""


class PageRetrievalOutcome(str, Enum):
    """Whether the cited reporter page could be cut from the archive's opinions."""

    FOUND = "found"
    WHOLE_OPINION = "whole_opinion"
    """The opinions carry no page markers at all, so the whole opinion stands in for the page."""
    NO_REPORTER = "no_reporter"
    """The cluster does not list the filing's reporter among its citations."""
    NO_PAGE = "no_page"
    """The opinions carry no marker for the cited page in the filing's reporter."""
    NO_TEXT = "no_text"
    FAILED = "failed"


class QuoteFindingOutcome(str, Enum):
    """Where words the filing quotes were found."""

    ON_PAGE = "on_page"
    ADJACENT = "adjacent"
    """On the page before or after the cited one, within the neighbour text shown."""
    ELSEWHERE = "elsewhere"
    """In the opinion, on another page, which is named."""
    FOUND_UNPAGED = "found_unpaged"
    """In an opinion whose text carries no page markers, so the page cannot be told."""
    ABSENT = "absent"
    """Nowhere in any of the cluster's opinions."""


class PinpointRelation(str, Enum):
    """What the model read on the page against the filing's attribution. Factual, not evaluative."""

    SAME_CONTENT = "same_content"
    """A passage on the page states the same content as the filing's words."""
    RELATED_SUBJECT = "related_subject"
    """A passage on the page is about the same subject and says something different."""
    NONE = "none"
    """Nothing on the page concerns the subject of the filing's words."""


class PinpointOutcome(str, Enum):
    """What the stage concludes about one pin cite.

    Nothing here says a page *supports* a proposition. The stage reports what
    is on the page beside what the filing wrote, and calls a pin cite false
    only on a fact: quoted words that are not there, or a page that carries
    nothing on the subject.
    """

    QUOTE_ON_PAGE = "quote_on_page"
    QUOTE_ELSEWHERE = "quote_elsewhere"
    """The filing's quoted words are in the opinion, on a page other than the cited one."""
    QUOTE_ABSENT = "quote_absent"
    """The filing's quoted words are in none of the cluster's opinions."""
    QUOTE_ALTERED = "quote_altered"
    """The quoted words are not the opinion's as written, but the cited page carries the same content:
    a misquotation, disclosed side by side, not a wrong page."""
    QUOTE_IN_OPINION = "quote_in_opinion"
    """The quoted words are in the opinion; its text carries no page markers, so the page cannot be checked."""
    PASSAGE_ON_PAGE = "passage_on_page"
    """The page carries a passage on the filing's subject; both are shown side by side."""
    PASSAGE_ADJACENT = "passage_adjacent"
    """The passage is on the page before or after; a turn away, not a different page."""
    PASSAGE_ABSENT = "passage_absent"
    """Nothing on the cited page or beside it concerns the filing's subject."""
    PASSAGE_IN_OPINION = "passage_in_opinion"
    """The opinion carries a passage on the subject; its text carries no page markers."""
    PASSAGE_ABSENT_FROM_OPINION = "passage_absent_from_opinion"
    """Nothing in the whole opinion concerns the filing's subject."""
    NOT_TESTABLE = "not_testable"
    """The citation makes no page-level claim of its own: `see generally`, a `citing` parenthetical, a bare string share."""
    UNDETERMINED = "undetermined"
    """The reading did not pass its guards, or the evidence points both ways."""
    NOT_RETRIEVED = "not_retrieved"


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
    docket_number: str | None = None
    """The docket's number as printed, kept so its format can be read against the court."""


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
    implied_court_ids: tuple[str, ...] = ()
    """The courts the reporter can hold, when the filing states none and they were consulted."""


@dataclass(frozen=True, slots=True)
class DocketNumberCourtNode:
    """What the docket number's format says about the court, against the docket's court field.

    A second witness to the same fact as :class:`CourtCheckNode`'s record
    side. ``MATCH`` and ``MISMATCH`` are between the number and the field,
    not between the filing and the record; ``UNAVAILABLE`` is a number whose
    format this check cannot read.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    docket_number: str | None
    retrieved_court_id: str | None
    levels: tuple[str, ...]
    courts: tuple[str, ...]
    evidence: str
    judge_initials: str | None
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
class DateReconciliationNode:
    """A date the filing states, checked against every date the archive holds for the record.

    A lookup record carries one date, the filing date of the opinion the
    archive holds, and a reporter citation to an opinion amended into the next
    year states the year of the print. When the two disagree, the cluster's
    other dates and the opinion's own header are fetched and read for a dated
    event -- decided, amended, filed -- that states the filing's year. A match
    is ``compatible`` with the phrase as evidence; nothing found is a
    ``mismatch`` still, and says what was read.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: FieldCheckOutcome
    extracted_date: str | None
    retrieved_date: str | None
    other_dates: str | None
    """The cluster's free-text dates, as fetched."""
    opinion_id: str | None
    """The sub-opinion whose header stated the filing's year, when one did."""
    opinions_read: tuple[str, ...]
    """Every sub-opinion whose header was read, in order."""
    dated_phrases: tuple[str, ...]
    """Every dated event found, such as `Amended Feb. 5, 2014`."""
    phrases_by_opinion: tuple[tuple[str, tuple[str, ...]], ...]
    """For each opinion header read, its id and the dated events found in it."""
    matched_phrase: str | None
    """The phrase that states the filing's date, when one does."""
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


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

    The model is a reader that must show its evidence. For each field it
    states what the filing says and the string it read that from, and a
    deterministic requirement checks the string against the window the field
    has to come from. Court and date agreement are then computed from the
    reading; only the case-name agreement is the model's answer. The verdict is
    held to the agreements, so one they do not support is repaired rather than
    recorded. When repair is exhausted the judgement fails, and the fields
    whose evidence still passed are kept.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: IdentityVerdict
    case_name_read: str | None
    """What the filing states, read from the name window. Kept only when grounded there."""
    case_name_agreement: FieldAgreement | None
    """The model's answer: the one judgement rules cannot make."""
    court_read: str | None
    """A courts-db identifier, kept only when its evidence grounds it."""
    court_evidence: str | None
    """The string in the parenthetical window the court was read from."""
    court_basis: str | None
    """``stated`` when the parenthetical names it, ``implied_by_reporter`` when the reporter does."""
    court_agreement: FieldAgreement | None
    """Computed from ``court_read`` and the record, not asked of the model."""
    date_read: str | None
    """``YYYY`` or ``YYYY-MM-DD``, kept only when its evidence grounds it."""
    date_evidence: str | None
    date_agreement: FieldAgreement | None
    """Computed at the precision ``date_read`` states, not asked of the model."""
    reason: str | None
    grounded: tuple[str, ...]
    """The fields whose evidence passed. On a failed judgement, the readings kept."""
    name_window: Span | None
    parenthetical_window: Span | None
    depends_on: tuple[str, ...]
    model: str | None = None
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateAnswer:
    """The model's answer about one record at the locator, in the multi-candidate judgement."""

    candidate_index: int
    cluster_id: str | None
    case_name: str | None
    case_name_agreement: FieldAgreement
    same_case: str
    """``yes``, ``no`` or ``undeterminable``: whether this record is the filing's case."""
    reason: str


@dataclass(frozen=True, slots=True)
class MelleaCandidateJudgmentNode:
    """One model call over every record at a locator none of which the rules could match.

    The filing's reading is shared -- one case name, court and date, each with
    its evidence, grounded in the same windows as the single-candidate
    judgement -- and the model answers per record whether it is the filing's
    case, then chooses one or none. A requirement holds the choice to the
    per-record answers.
    """

    node_id: str
    status: ValidationNodeStatus
    outcome: IdentityVerdict
    case_name_read: str | None
    court_read: str | None
    court_evidence: str | None
    court_basis: str | None
    date_read: str | None
    date_evidence: str | None
    candidates: tuple[CandidateAnswer, ...]
    chosen_index: int | None
    reason: str | None
    grounded: tuple[str, ...]
    name_window: Span | None
    parenthetical_window: Span | None
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
    records_at_locator: int = 1
    """How many records the archive returned at the locator."""
    agreeing_cluster_ids: tuple[str, ...] = ()
    """Every record whose fields all agreed with the filing, when more than one did: the duplicates."""

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


@dataclass(frozen=True, slots=True)
class PinpointScopeNode:
    """Whether this citation's pin cite is checked, and against which authority."""

    node_id: str
    status: ValidationNodeStatus
    outcome: PinpointScope
    authority_id: str | None
    cluster_id: str | None
    pin_cite: str | None
    pin_form: str | None
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class PageRetrievalNode:
    """The cited page as cut from the archive, with its neighbours and its source opinion."""

    node_id: str
    status: ValidationNodeStatus
    outcome: PageRetrievalOutcome
    cluster_id: str | None
    reporter_citation: str | None
    citation_index: str | None
    labels: tuple[str, ...]
    opinion_id: str | None
    opinion_type: str | None
    page_text: str | None
    before: str | None
    after: str | None
    opinions_read: tuple[str, ...]
    """Every opinion in the cluster whose text was read, so quotes can be searched across all of them."""
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class QuoteFinding:
    """One quotation the filing writes near the citation, and where its words were found."""

    text: str
    filing_span: Span
    in_parenthetical: bool
    shared: bool
    """Written in a sentence a string cite shares, so absence from this member's opinion proves nothing."""
    outcome: QuoteFindingOutcome
    opinion_id: str | None
    label: str | None
    """The page the words were found on, in the filing's reporter."""
    page_span: Span | None
    """Where the words lie in the retrieved page text, when found on it."""
    score: float | None


@dataclass(frozen=True, slots=True)
class QuoteCheckNode:
    """Every quotation near the citation searched on the page, beside it, and through the opinions."""

    node_id: str
    status: ValidationNodeStatus
    outcome: QuoteFindingOutcome | None
    """The worst finding among the quotations the target owns; None when it quotes nothing."""
    quotes: tuple[QuoteFinding, ...]
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None


@dataclass(frozen=True, slots=True)
class MelleaPinpointReadingNode:
    """One reading of the citing passage against the cited page, every quote grounded."""

    node_id: str
    status: ValidationNodeStatus
    outcome: PinpointRelation | None
    model: str | None
    window: Span
    """The filing window shown to the model, in document coordinates."""
    attribution: str | None
    attribution_span: Span | None
    """Where the filing states what the citation is cited for, in document coordinates."""
    attribution_scope: str | None
    """`own`, `shared` or `none`."""
    signal: str | None
    passage: str | None
    passage_location: str | None
    """`page`, `before` or `after`."""
    passage_span: Span | None
    """Where the passage lies in the text of that location, as the retrieval node holds it."""
    voice: str | None
    page_subjects: str | None
    reason: str | None
    grounded: tuple[str, ...]
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PinpointResolutionNode:
    """What the stage concludes about one pin cite, with both sides located."""

    node_id: str
    status: ValidationNodeStatus
    outcome: PinpointOutcome
    false_pin_cite: bool
    """True only on a fact: quoted words not in the opinion or not on the page, or a page with nothing on the subject."""
    authority_id: str | None
    cluster_id: str | None
    pin_cite: str | None
    labels: tuple[str, ...]
    attribution_span: Span | None
    attribution: str | None
    passage_opinion_id: str | None
    passage_label: str | None
    passage_span: Span | None
    passage: str | None
    voice: str | None
    signal: str | None
    vocabulary_on_page: float | None
    """Share of the attribution's distinctive words found on the page, the guard against a missed passage."""
    decided_by: str
    depends_on: tuple[str, ...]
    status_message: str | None = None
    outcome_message: str | None = None
    misquoted: bool = False
    """The words the filing puts in quotation marks are not in the opinion as written."""
    text_scope: str = "page"
    """`page` when a reporter page was cut; `opinion` when the whole opinion stood in for it."""


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
    | DocketNumberCourtNode
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
    | DateReconciliationNode
    | CaseNameAgreementNode
    | MelleaIdentityJudgmentNode
    | MelleaCandidateJudgmentNode
    | IdentityResolutionNode
    | AuthorityMergeNode
    | DocketIdentityNode
    | PinpointScopeNode
    | PageRetrievalNode
    | QuoteCheckNode
    | MelleaPinpointReadingNode
    | PinpointResolutionNode
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
