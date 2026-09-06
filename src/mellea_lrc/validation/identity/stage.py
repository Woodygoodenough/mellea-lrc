"""The identity stage: which case does each authority in a filing name?

This runs once per **root** -- the citation that introduced an authority --
rather than once per citation. Extraction's citation tree already resolves
every `Id.`, short form and repeated full citation to the root that introduced
it, so checking the root checks the identity of everything that refers to it.
A filing citing one case ten times costs one lookup, and the nine return
visits are pinpoint claims for a later stage. If extraction attributed one of
them wrongly, that is found where the pinpoint fails, not here.

Per root the stage is a fixed sequence: look the locator up, merge the records
that are one decision held twice, narrow a crowded page by the case name the
filing wrote, and then, for each remaining candidate, run the rule guard. When
every rule agrees or has nothing to compare, the identity is established
without a model. When any rule disagrees, one composite model call reads the
filing's context and judges every field at once.

What the stage writes back:

- a trace on every record, root or not, of what was decided and on what
- a resolution on each established root: which cluster, under what name
- corrections to the filing's reading where the model read the filing
  differently from the extractor, each attributed to the model
- a re-attribution where two roots at one text position -- a parallel citation
  -- resolved to the same cluster, so the later one becomes a non-root and
  everything that referred to it follows

Every root ends in one of four outcomes: `CONFIRMED_IDENTITY`,
`WRONG_IDENTITY` with a reason and the fields under it, `AMBIGUOUS_IDENTITY`,
or `DEFER_TO_SEARCH` for what the lookup route cannot decide -- nothing at the
locator, a docket number (``docket.py`` describes that route), or a judgement
that could not decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import DocketCitation, FullCaseCitation
from mellea_lrc.courtlistener import CourtListenerClient
from mellea_lrc.validation.candidate_evaluation import run_locator_candidate_evaluation
from mellea_lrc.validation.candidate_selection import CANDIDATE_SELECTION_LIMIT
from mellea_lrc.validation.citation_lookup import run_exact_locator_lookup
from mellea_lrc.validation.court_retrieval import run_docket_court_retrieval
from mellea_lrc.validation.duplicate_clusters import matching_case_names, merge_duplicates
from mellea_lrc.validation.identity.docket import run_docket_identity
from mellea_lrc.validation.identity.field_checks import (
    run_case_name_agreement,
    run_court_comparison,
    run_date_check,
)
from mellea_lrc.validation.identity.mellea_judgment import (
    apply_readings,
    field_disagreements,
    run_mellea_identity_judgment,
)
from mellea_lrc.validation.record import CitationRecord, Resolution
from mellea_lrc.validation.types import (
    AuthorityMergeNode,
    AuthorityMergeOutcome,
    CandidateSelectionNode,
    CandidateSelectionOutcome,
    FieldCheckOutcome,
    IdentityOutcome,
    IdentityReason,
    IdentityResolutionNode,
    IdentityScope,
    IdentityScopeNode,
    IdentityVerdict,
    LocatorLookupOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea import MelleaSession

    from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument
    from mellea_lrc.validation.types import (
        CandidateEvaluationNode,
        CaseNameAgreementNode,
        CourtCheckNode,
        DateCheckNode,
        ExactLocatorLookupNode,
        FieldDisagreement,
    )

RULE = "validation.identity.stage"


@dataclass(frozen=True, slots=True)
class IdentifiedDocument:
    """Every citation's record after the identity stage, in extraction order."""

    source: ExtractedDocument
    records: tuple[CitationRecord, ...]

    def __post_init__(self) -> None:
        source_ids = tuple(item.citation_id for item in self.source.citations)
        record_ids = tuple(item.citation_id for item in self.records)
        if record_ids != source_ids:
            msg = "Records must match the extracted citations in order"
            raise ValueError(msg)

    def record(self, citation_id: str) -> CitationRecord:
        """One citation's record."""
        for record in self.records:
            if record.citation_id == citation_id:
                return record
        msg = f"Unknown citation id: {citation_id!r}"
        raise KeyError(msg)

    @property
    def roots(self) -> tuple[CitationRecord, ...]:
        """The records that introduce an authority, after any merge."""
        return tuple(record for record in self.records if record.is_root)

    def resolution_of(self, citation_id: str) -> IdentityResolutionNode | None:
        """The identity conclusion a citation inherits, through its root."""
        record = self.record(citation_id)
        if record.authority_id is None:
            return None
        root = self.record(record.authority_id)
        for node in root.trace.nodes:
            if isinstance(node, IdentityResolutionNode):
                return node
        return None


async def identify_document(
    document: ExtractedDocument,
    *,
    client: CourtListenerServiceClient | None = None,
    session: MelleaSession | None = None,
) -> IdentifiedDocument:
    """Run the identity stage over every root in a document."""
    service = client if client is not None else CourtListenerClient()
    records = tuple(CitationRecord.from_extracted(item) for item in document.citations)
    for record in records:
        record.append(scope_node(record))
    for record in records:
        scope = _scope(record)
        if scope is IdentityScope.ROOT_CASE:
            await identify_root(
                record,
                document_text=document.text,
                citations=document.citations,
                client=service,
                session=session,
            )
        elif scope is IdentityScope.ROOT_DOCKET:
            docket = record.append(run_docket_identity(record))
            record.append(
                _resolution(
                    record,
                    IdentityOutcome.DEFER_TO_SEARCH,
                    reason=IdentityReason.DOCKET,
                    depends_on=(docket.node_id,),
                    message="A docket number is identified by the RECAP search route, which is not built.",
                )
            )
    merge_colocated_roots(records)
    return IdentifiedDocument(source=document, records=records)


def scope_node(record: CitationRecord) -> IdentityScopeNode:
    """Decide from the citation tree whether this citation's identity is checked."""
    citation = record.citation
    node_id = f"{record.citation_id}:identity_scope"
    if record.authority_id is None:
        return IdentityScopeNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=IdentityScope.OUT_OF_SCOPE,
            authority_id=None,
            colocation_id=record.source.colocation_id,
            status_message="Skipped identity because the citation belongs to no case authority.",
            outcome_message="Not a case citation, or a reference that reached no case authority.",
        )
    if not record.is_root:
        return IdentityScopeNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=IdentityScope.NON_ROOT,
            authority_id=record.authority_id,
            colocation_id=record.source.colocation_id,
            status_message="Skipped identity because another citation introduced this authority.",
            outcome_message=f"Inherits the identity of {record.authority_id}.",
        )
    if isinstance(citation, DocketCitation):
        outcome, message = IdentityScope.ROOT_DOCKET, "Introduces an authority by docket number."
    elif isinstance(citation, FullCaseCitation):
        outcome, message = IdentityScope.ROOT_CASE, "Introduces an authority by reporter locator."
    else:
        return IdentityScopeNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=IdentityScope.OUT_OF_SCOPE,
            authority_id=record.authority_id,
            colocation_id=record.source.colocation_id,
            status_message="Skipped identity because the root is not a case citation.",
            outcome_message=f"A {citation.kind.value} cannot introduce a case authority.",
        )
    return IdentityScopeNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        authority_id=record.authority_id,
        colocation_id=record.source.colocation_id,
        status_message="Identity scope decided.",
        outcome_message=message,
    )


async def identify_root(
    record: CitationRecord,
    *,
    document_text: str,
    citations: Sequence[ExtractedCitation],
    client: CourtListenerServiceClient,
    session: MelleaSession | None,
) -> IdentityResolutionNode:
    """Establish, refute, or leave unresolved the identity of one reporter root."""
    scope = _scope_node(record)
    lookup = record.append(run_exact_locator_lookup(record.trace, client=client))
    if lookup.outcome is LocatorLookupOutcome.NOT_FOUND:
        return record.append(
            _resolution(
                record,
                IdentityOutcome.DEFER_TO_SEARCH,
                reason=IdentityReason.NOT_FOUND,
                depends_on=(scope.node_id, lookup.node_id),
                message="The archive holds nothing at the locator.",
            )
        )
    if lookup.outcome not in (LocatorLookupOutcome.FOUND, LocatorLookupOutcome.AMBIGUOUS):
        return record.append(
            _resolution(
                record,
                IdentityOutcome.DEFER_TO_SEARCH,
                reason=IdentityReason.LOOKUP_FAILED,
                depends_on=(scope.node_id, lookup.node_id),
                message=lookup.outcome_message or "The locator could not be looked up.",
            )
        )
    candidates, selection = _select_candidates(record, lookup)
    if selection is not None:
        record.append(selection)
    if not candidates:
        return record.append(
            _resolution(
                record,
                IdentityOutcome.AMBIGUOUS_IDENTITY,
                reason=IdentityReason.CROWDED_PAGE,
                depends_on=(scope.node_id, selection.node_id if selection else lookup.node_id),
                message=(
                    f"{selection.distinct_case_count if selection else '?'} distinct cases remain at the locator "
                    "after merging duplicates, and the case name the filing wrote separates none."
                ),
            )
        )
    parent = selection.node_id if selection is not None else lookup.node_id
    # The rule guard runs on every candidate before any model is consulted: on
    # a page of several cases the filing's case is usually one the rules can
    # settle, and a model call on the wrong candidate first is a call wasted.
    guarded = [
        _rule_guard(record, cluster=cluster, candidate_index=index, depends_on=(parent,), client=client)
        for index, cluster in enumerate(candidates, start=1)
    ]
    verdicts: list[Verdict] = [guard.verdict for guard in guarded if guard.verdict is not None]
    if not verdicts:
        for guard in guarded:
            verdict = await _model_judge(
                record, guard, document_text=document_text, citations=citations, session=session
            )
            verdicts.append(verdict)
            if verdict.resolved:
                break
    # A refutation needs every case the archive holds at the page to have been
    # examined. A found page and a page whose distinct cases all fit within the
    # limit qualify; a page narrowed by the filing's name left others unread.
    every_case_examined = selection is None or selection.outcome is CandidateSelectionOutcome.ALL_SELECTED
    return _conclude(record, verdicts, every_case_examined=every_case_examined)


def merge_colocated_roots(records: Sequence[CitationRecord]) -> None:
    """Fold parallel citations that resolved to one cluster into one authority.

    Extraction leaves co-located citations as separate roots on purpose: where
    they sit is a candidate for identity, not a finding. The lookup settles it.
    When two roots at one position resolved to the same cluster, the later one
    is re-attributed to the earlier, and so is every citation that referred to
    the later one.
    """
    seen: dict[str, CitationRecord] = {}
    for record in records:
        colocation_id = record.source.colocation_id
        if colocation_id is None or not record.is_root or record.resolution is None:
            continue
        earlier = seen.get(colocation_id)
        if earlier is None:
            seen[colocation_id] = record
            continue
        node_id = f"{record.citation_id}:authority_merge"
        depends_on = (record.resolution.node_id,)
        if earlier.resolution is None or earlier.resolution.cluster_id != record.resolution.cluster_id:
            record.append(
                AuthorityMergeNode(
                    node_id=node_id,
                    status=ValidationNodeStatus.SUCCEEDED,
                    outcome=AuthorityMergeOutcome.KEPT,
                    colocation_id=colocation_id,
                    target_citation_id=earlier.citation_id,
                    cluster_id=record.resolution.cluster_id,
                    depends_on=depends_on,
                    status_message="Authority merge decided.",
                    outcome_message="Shares a position with an earlier root but resolved to a different cluster.",
                )
            )
            continue
        merge = record.append(
            AuthorityMergeNode(
                node_id=node_id,
                status=ValidationNodeStatus.SUCCEEDED,
                outcome=AuthorityMergeOutcome.MERGED_INTO,
                colocation_id=colocation_id,
                target_citation_id=earlier.citation_id,
                cluster_id=record.resolution.cluster_id,
                depends_on=depends_on,
                status_message="Authority merge decided.",
                outcome_message=(
                    f"Resolved to the same cluster as {earlier.citation_id} at the same position: "
                    "one authority cited in parallel."
                ),
            )
        )
        reason = merge.outcome_message or ""
        former_root = record.citation_id
        record.reattribute(earlier.citation_id, made_by=RULE, reason=reason, node_id=merge.node_id)
        for follower in records:
            if follower.authority_id == former_root and follower is not record:
                follower.reattribute(
                    earlier.citation_id,
                    made_by=RULE,
                    reason=f"Followed {former_root}, which merged into {earlier.citation_id}.",
                    node_id=_scope_node(follower).node_id,
                )


def _select_candidates(
    record: CitationRecord, lookup: ExactLocatorLookupNode
) -> tuple[tuple[CourtListenerOpinionCluster, ...], CandidateSelectionNode | None]:
    """One record per distinct case at the locator, narrowed by name when crowded."""
    if lookup.outcome is LocatorLookupOutcome.FOUND:
        assert lookup.cluster is not None
        return (lookup.cluster,), None
    clusters = lookup.candidate_clusters
    groups = merge_duplicates(clusters)
    firsts = tuple(clusters.index(group[0]) for group in groups)
    node_id = f"{record.citation_id}:locator_candidate_selection"
    if len(groups) <= CANDIDATE_SELECTION_LIMIT:
        selection = CandidateSelectionNode(
            node_id=node_id,
            status=ValidationNodeStatus.SUCCEEDED,
            outcome=CandidateSelectionOutcome.ALL_SELECTED,
            total_candidate_count=len(clusters),
            selected_candidate_count=len(groups),
            selection_limit=CANDIDATE_SELECTION_LIMIT,
            selected_indices=firsts,
            distinct_case_count=len(groups),
            depends_on=(lookup.node_id,),
            status_message="Candidate selection completed.",
            outcome_message=(
                f"{len(clusters)} records at the locator are {len(groups)} distinct cases after merging, "
                f"within the limit of {CANDIDATE_SELECTION_LIMIT}."
            ),
        )
        return tuple(clusters[i] for i in firsts), selection
    citation = record.citation
    plaintiff = citation.plaintiff if isinstance(citation, FullCaseCitation) else None
    defendant = citation.defendant if isinstance(citation, FullCaseCitation) else None
    matches = matching_case_names(
        tuple(clusters[i] for i in firsts), plaintiff=plaintiff, defendant=defendant
    )
    kept = tuple(firsts[i] for i in matches)
    if kept and len(kept) <= CANDIDATE_SELECTION_LIMIT:
        selection = CandidateSelectionNode(
            node_id=node_id,
            status=ValidationNodeStatus.SUCCEEDED,
            outcome=CandidateSelectionOutcome.NARROWED_BY_CASE_NAME,
            total_candidate_count=len(clusters),
            selected_candidate_count=len(kept),
            selection_limit=CANDIDATE_SELECTION_LIMIT,
            selected_indices=kept,
            distinct_case_count=len(groups),
            depends_on=(lookup.node_id,),
            status_message="Candidate selection completed.",
            outcome_message=(
                f"{len(groups)} distinct cases at the locator exceed the limit of "
                f"{CANDIDATE_SELECTION_LIMIT}, and the case name the filing wrote matches {len(kept)}."
            ),
        )
        return tuple(clusters[i] for i in kept), selection
    selection = CandidateSelectionNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=CandidateSelectionOutcome.DEFERRED_OVER_LIMIT,
        total_candidate_count=len(clusters),
        selected_candidate_count=0,
        selection_limit=CANDIDATE_SELECTION_LIMIT,
        selected_indices=(),
        distinct_case_count=len(groups),
        depends_on=(lookup.node_id,),
        status_message="Candidate selection completed.",
        outcome_message=(
            f"{len(groups)} distinct cases at the locator exceed the limit of "
            f"{CANDIDATE_SELECTION_LIMIT}, and the case name the filing wrote matches none of them."
        ),
    )
    return (), selection


@dataclass(frozen=True, slots=True)
class Verdict:
    """What one candidate came to: the outcome and its reason, and what it rests on."""

    outcome: IdentityOutcome
    reason: IdentityReason | None
    cluster: CourtListenerOpinionCluster
    decided_by: str
    fields: tuple[FieldDisagreement, ...]
    node_ids: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        """Whether this candidate is the filing's case, defects or not."""
        return (
            self.outcome is IdentityOutcome.CONFIRMED_IDENTITY
            or self.reason is IdentityReason.FIELD_DISAGREEMENT
        )


@dataclass(frozen=True, slots=True)
class _Guarded:
    """One candidate after the rule guard, with a verdict when the rules settled it."""

    cluster: CourtListenerOpinionCluster
    candidate: CandidateEvaluationNode
    case_name: CaseNameAgreementNode
    date: DateCheckNode
    court: CourtCheckNode
    verdict: Verdict | None

    @property
    def node_ids(self) -> tuple[str, ...]:
        return (self.candidate.node_id, self.case_name.node_id, self.date.node_id, self.court.node_id)


def _rule_guard(
    record: CitationRecord,
    *,
    cluster: CourtListenerOpinionCluster,
    candidate_index: int,
    depends_on: tuple[str, ...],
    client: CourtListenerServiceClient,
) -> _Guarded:
    """Run the three rule comparisons on one candidate. No model is consulted."""
    candidate = record.append(
        run_locator_candidate_evaluation(
            record.trace, cluster=cluster, candidate_index=candidate_index, depends_on=depends_on
        )
    )
    case_name = record.append(run_case_name_agreement(record.citation, candidate=candidate))
    date = record.append(run_date_check(record.citation, candidate=candidate))
    court_retrieval = record.append(
        run_docket_court_retrieval(record.trace, candidate=candidate, client=client)
    )
    court = record.append(run_court_comparison(record.citation, evidence=court_retrieval))
    rules_agree = (
        (case_name.outcome.agrees or case_name.outcome.value == "unavailable")
        and court.outcome is not FieldCheckOutcome.MISMATCH
        and date.outcome is not FieldCheckOutcome.MISMATCH
    )
    guarded = _Guarded(cluster, candidate, case_name, date, court, None)
    if not rules_agree:
        return guarded
    verdict = Verdict(IdentityOutcome.CONFIRMED_IDENTITY, None, cluster, "rule", (), guarded.node_ids)
    return _Guarded(cluster, candidate, case_name, date, court, verdict)


async def _model_judge(
    record: CitationRecord,
    guarded: _Guarded,
    *,
    document_text: str,
    citations: Sequence[ExtractedCitation],
    session: MelleaSession | None,
) -> Verdict:
    """Ask the model about one candidate the rules could not settle."""
    judgment = record.append(
        await run_mellea_identity_judgment(
            record,
            document_text=document_text,
            citations=citations,
            candidate=guarded.candidate,
            case_name=guarded.case_name,
            court=guarded.court,
            date=guarded.date,
            session=session,
        )
    )
    apply_readings(record, judgment)
    fields = field_disagreements(
        judgment, case_name=guarded.case_name, court=guarded.court, date=guarded.date
    )
    node_ids = (*guarded.node_ids, judgment.node_id)
    if judgment.outcome is IdentityVerdict.SAME_CASE:
        if fields:
            return Verdict(
                IdentityOutcome.WRONG_IDENTITY,
                IdentityReason.FIELD_DISAGREEMENT,
                guarded.cluster,
                judgment.node_id,
                fields,
                node_ids,
            )
        return Verdict(
            IdentityOutcome.CONFIRMED_IDENTITY, None, guarded.cluster, judgment.node_id, (), node_ids
        )
    if judgment.outcome is IdentityVerdict.DIFFERENT_CASE:
        return Verdict(
            IdentityOutcome.WRONG_IDENTITY,
            IdentityReason.DIFFERENT_CASE_AT_LOCATOR,
            guarded.cluster,
            judgment.node_id,
            fields,
            node_ids,
        )
    return Verdict(
        IdentityOutcome.DEFER_TO_SEARCH,
        IdentityReason.UNDETERMINABLE,
        guarded.cluster,
        judgment.node_id,
        fields,
        node_ids,
    )


def _conclude(
    record: CitationRecord,
    verdicts: Sequence[Verdict],
    *,
    every_case_examined: bool,
) -> IdentityResolutionNode:
    """Pick the strongest candidate verdict and write the resolution it implies."""

    def rank(verdict: Verdict) -> int:
        if verdict.outcome is IdentityOutcome.CONFIRMED_IDENTITY:
            return 0
        if verdict.reason is IdentityReason.FIELD_DISAGREEMENT:
            return 1
        if verdict.outcome is IdentityOutcome.DEFER_TO_SEARCH:
            return 2
        return 3

    best = min(verdicts, key=rank)
    outcome, reason = best.outcome, best.reason
    all_different = all(v.reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR for v in verdicts)
    if reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR and not (every_case_examined and all_different):
        # A page narrowed by the filing's name left cases unread, and a page
        # where one candidate could not be judged is not settled either; on
        # neither does a candidate that is not the filing's case show the
        # filing's case absent. That is the standing rule for absence.
        outcome, reason = IdentityOutcome.DEFER_TO_SEARCH, IdentityReason.UNDETERMINABLE
    scope = _scope_node(record)
    if outcome is IdentityOutcome.CONFIRMED_IDENTITY:
        message = "The locator names one case and every field the filing states agrees with it."
    elif reason is IdentityReason.FIELD_DISAGREEMENT:
        names = ", ".join(field.field for field in best.fields)
        message = f"The locator names the case, but the filing's {names} disagree{'s' if len(best.fields) == 1 else ''} with the record."
    elif reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR:
        names = [v.cluster.case_name or "unnamed" for v in verdicts]
        message = (
            f"The locator names a different case: {names[0]}."
            if len(names) == 1
            else f"The locator names {len(names)} cases, none the filing's: {'; '.join(names)}."
        )
    else:
        message = "Nothing at the locator could be shown to be the filing's case, or not to be."
    node = _resolution(
        record,
        outcome,
        reason=reason,
        cluster_id=best.cluster.cluster_id,
        record_case_name=best.cluster.case_name,
        decided_by=best.decided_by,
        fields=best.fields,
        depends_on=(scope.node_id, *best.node_ids),
        message=message,
    )
    record.append(node)
    if node.resolved:
        record.resolve(
            Resolution(
                cluster_id=best.cluster.cluster_id,
                case_name=best.cluster.case_name,
                date_filed=best.cluster.date_filed,
                court_id=_retrieved_court(record, best.node_ids),
                node_id=node.node_id,
            )
        )
    return node


def _retrieved_court(record: CitationRecord, node_ids: tuple[str, ...]) -> str | None:
    for node in record.trace.nodes:
        if node.node_id in node_ids and hasattr(node, "retrieved_court_id"):
            return node.retrieved_court_id
    return None


def _resolution(
    record: CitationRecord,
    outcome: IdentityOutcome,
    *,
    reason: IdentityReason | None,
    depends_on: tuple[str, ...],
    message: str,
    cluster_id: str | None = None,
    record_case_name: str | None = None,
    decided_by: str = "rule",
    fields: tuple[FieldDisagreement, ...] = (),
) -> IdentityResolutionNode:
    return IdentityResolutionNode(
        node_id=f"{record.citation_id}:identity_resolution",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        reason=reason,
        cluster_id=cluster_id,
        record_case_name=record_case_name,
        decided_by=decided_by,
        fields=fields,
        depends_on=depends_on,
        status_message="Identity resolution completed.",
        outcome_message=message,
    )


def _scope_node(record: CitationRecord) -> IdentityScopeNode:
    for node in record.trace.nodes:
        if isinstance(node, IdentityScopeNode):
            return node
    msg = f"Citation {record.citation_id!r} has no identity scope node"
    raise ValueError(msg)


def _scope(record: CitationRecord) -> IdentityScope:
    return _scope_node(record).outcome


__all__ = [
    "IdentifiedDocument",
    "identify_document",
    "identify_root",
    "merge_colocated_roots",
    "scope_node",
]
