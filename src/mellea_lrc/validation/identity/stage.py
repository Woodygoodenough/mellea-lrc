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

Two routes are recorded and not run: a root cited by docket number
(``docket.py`` describes the route), and a root the archive holds nothing for,
which is open search's population.
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
    from mellea_lrc.extraction.types import ExtractedDocument
    from mellea_lrc.validation.types import ExactLocatorLookupNode

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
            await identify_root(record, document_text=document.text, client=service, session=session)
        elif scope is IdentityScope.ROOT_DOCKET:
            docket = record.append(run_docket_identity(record))
            record.append(
                _resolution(
                    record,
                    IdentityOutcome.DEFERRED,
                    cluster_id=None,
                    decided_by="rule",
                    defects=(),
                    depends_on=(docket.node_id,),
                    message="Identity by docket number is deferred until the RECAP route is built.",
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
                IdentityOutcome.UNRESOLVED,
                cluster_id=None,
                decided_by="rule",
                defects=(),
                depends_on=(scope.node_id, lookup.node_id),
                message="The archive holds nothing at the locator. Open search's population.",
            )
        )
    if lookup.outcome not in (LocatorLookupOutcome.FOUND, LocatorLookupOutcome.AMBIGUOUS):
        return record.append(
            _resolution(
                record,
                IdentityOutcome.UNRESOLVED,
                cluster_id=None,
                decided_by="rule",
                defects=(),
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
                IdentityOutcome.AMBIGUOUS,
                cluster_id=None,
                decided_by="rule",
                defects=(),
                depends_on=(scope.node_id, selection.node_id if selection else lookup.node_id),
                message="The page holds more cases than the stage will look at, and nothing separated them.",
            )
        )
    verdicts: list[
        tuple[IdentityOutcome, CourtListenerOpinionCluster, str, tuple[str, ...], tuple[str, ...]]
    ] = []
    parent = selection.node_id if selection is not None else lookup.node_id
    for index, cluster in enumerate(candidates, start=1):
        verdict = await _judge_candidate(
            record,
            cluster=cluster,
            candidate_index=index,
            depends_on=(parent,),
            document_text=document_text,
            client=client,
            session=session,
        )
        verdicts.append(verdict)
        if verdict[0] is IdentityOutcome.ESTABLISHED:
            break
    return _conclude(record, verdicts, page_holds_one_case=len(candidates) == 1 and selection is None)


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


async def _judge_candidate(
    record: CitationRecord,
    *,
    cluster: CourtListenerOpinionCluster,
    candidate_index: int,
    depends_on: tuple[str, ...],
    document_text: str,
    client: CourtListenerServiceClient,
    session: MelleaSession | None,
) -> tuple[IdentityOutcome, CourtListenerOpinionCluster, str, tuple[str, ...], tuple[str, ...]]:
    """Run the rule guard and, if it disagrees, the composite judgement, on one candidate."""
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
    node_ids = (candidate.node_id, case_name.node_id, date.node_id, court.node_id)
    if rules_agree:
        return IdentityOutcome.ESTABLISHED, cluster, "rule", (), node_ids
    judgment = record.append(
        await run_mellea_identity_judgment(
            record,
            document_text=document_text,
            candidate=candidate,
            case_name=case_name,
            court=court,
            date=date,
            session=session,
        )
    )
    apply_readings(record, judgment)
    defects = field_disagreements(judgment, case_name=case_name, court=court, date=date)
    node_ids = (*node_ids, judgment.node_id)
    if judgment.outcome is IdentityVerdict.SAME_CASE:
        outcome = IdentityOutcome.ESTABLISHED_WITH_DEFECTS if defects else IdentityOutcome.ESTABLISHED
    elif judgment.outcome is IdentityVerdict.DIFFERENT_CASE:
        outcome = IdentityOutcome.REFUTED
    else:
        outcome = IdentityOutcome.UNRESOLVED
    return outcome, cluster, judgment.node_id, defects, node_ids


def _conclude(
    record: CitationRecord,
    verdicts: Sequence[
        tuple[IdentityOutcome, CourtListenerOpinionCluster, str, tuple[str, ...], tuple[str, ...]]
    ],
    *,
    page_holds_one_case: bool,
) -> IdentityResolutionNode:
    """Pick the strongest candidate verdict and write the resolution it implies."""
    order = (
        IdentityOutcome.ESTABLISHED,
        IdentityOutcome.ESTABLISHED_WITH_DEFECTS,
        IdentityOutcome.UNRESOLVED,
        IdentityOutcome.REFUTED,
    )
    best = min(verdicts, key=lambda verdict: order.index(verdict[0]))
    outcome, cluster, decided_by, defects, node_ids = best
    if outcome is IdentityOutcome.REFUTED and not page_holds_one_case:
        # On a crowded page the archive may hold only part of the page, so a
        # candidate that is not the filing's case does not show the filing's
        # case is absent. That is the standing rule for absence.
        outcome = IdentityOutcome.UNRESOLVED
    scope = _scope_node(record)
    messages = {
        IdentityOutcome.ESTABLISHED: "The locator names one case and every field the filing states agrees with it.",
        IdentityOutcome.ESTABLISHED_WITH_DEFECTS: (
            f"The same case, but the filing's {', '.join(defects)} disagree{'s' if len(defects) == 1 else ''} with the record."
        ),
        IdentityOutcome.REFUTED: "The case at the locator is not the one the filing describes.",
        IdentityOutcome.UNRESOLVED: "Nothing at the locator could be shown to be the filing's case.",
    }
    node = _resolution(
        record,
        outcome,
        cluster_id=cluster.cluster_id
        if outcome in (IdentityOutcome.ESTABLISHED, IdentityOutcome.ESTABLISHED_WITH_DEFECTS)
        else None,
        decided_by=decided_by,
        defects=defects,
        depends_on=(scope.node_id, *node_ids),
        message=messages[outcome],
    )
    record.append(node)
    if node.cluster_id is not None:
        record.resolve(
            Resolution(
                cluster_id=cluster.cluster_id,
                case_name=cluster.case_name,
                date_filed=cluster.date_filed,
                court_id=_retrieved_court(record, node_ids),
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
    cluster_id: str | None,
    decided_by: str,
    defects: tuple[str, ...],
    depends_on: tuple[str, ...],
    message: str,
) -> IdentityResolutionNode:
    return IdentityResolutionNode(
        node_id=f"{record.citation_id}:identity_resolution",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        cluster_id=cluster_id,
        decided_by=decided_by,
        defects=defects,
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
