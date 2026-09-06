"""The identity stage: which case does each authority in a filing name?

This runs once per **root** -- the citation that introduced an authority --
rather than once per citation. Extraction's citation tree already resolves
every `Id.`, short form and repeated full citation to the root that introduced
it, so checking the root checks the identity of everything that refers to it.
A filing citing one case ten times costs one lookup, and the nine return
visits are pinpoint claims for a later stage. If extraction attributed one of
them wrongly, that is found where the pinpoint fails, not here.

Per root the stage is a fixed sequence: look the locator up, then run the
rule guard on every record the archive returned. A record whose every
comparable field agrees with the filing confirms the identity without a
model, and any other records at the page are disclosed. When no record
agrees, a page holding one record gets the single-candidate judgement, which
reads the filing's context and judges every field at once, and a page holding
several gets one judgement over all of them together.

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

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import DocketCitation, FullCaseCitation
from mellea_lrc.courtlistener import CourtListenerClient
from mellea_lrc.validation.candidate_evaluation import run_locator_candidate_evaluation
from mellea_lrc.validation.citation_lookup import run_exact_locator_lookup
from mellea_lrc.validation.court_retrieval import run_docket_court_retrieval
from mellea_lrc.validation.identity.dates import exploration_of, run_date_reconciliation
from mellea_lrc.validation.identity.docket import run_docket_identity
from mellea_lrc.validation.identity.field_checks import (
    run_case_name_agreement,
    run_court_comparison,
    run_date_check,
)
from mellea_lrc.validation.identity.mellea_candidates import MAX_CANDIDATES, run_mellea_candidate_judgment
from mellea_lrc.validation.identity.mellea_judgment import (
    apply_readings,
    chosen_disagreements,
    field_disagreements,
    run_mellea_identity_judgment,
)
from mellea_lrc.validation.record import CitationRecord, DateExploration, Resolution
from mellea_lrc.validation.types import (
    AuthorityMergeNode,
    AuthorityMergeOutcome,
    CandidateEvaluationNode,
    DateReconciliationNode,
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
        CaseNameAgreementNode,
        CourtCheckNode,
        DateCheckNode,
        ExactLocatorLookupNode,
        FieldDisagreement,
    )

RULE = "validation.identity.stage"
_YEAR = re.compile(r"\b(\d{4})\b")


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

    def date_only_disagreements(self) -> tuple[CitationRecord, ...]:
        """The roots that are a wrong identity on the date and nothing else.

        Each carries its resolution, with the case the archive holds and the
        ``DateExploration`` of everything read about its dates. These are the
        records where the case is very likely real and the dates differ for a
        reason the reconciliation could not find in the archive.

        TODO(date-analysis): this is the entry point for the step that decides
        what each disagreement is. It is not written; nothing yet consumes
        this list.
        """
        found = []
        for record in self.records:
            node = self.resolution_of(record.citation_id) if record.is_root else None
            if node is None or node.outcome is not IdentityOutcome.WRONG_IDENTITY:
                continue
            if node.reason is IdentityReason.FIELD_DISAGREEMENT and [f.field for f in node.fields] == [
                "date"
            ]:
                found.append(record)
        return tuple(found)

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
    """Establish, refute, or leave unresolved the identity of one reporter root.

    Every record the archive returns at the locator gets the rule guard. Any
    record whose every comparable field agrees confirms the identity, and the
    others are disclosed. When none agrees, one record is judged on its own
    and several are judged together, by a model that sees them all.
    """
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
    clusters = (lookup.cluster,) if lookup.cluster is not None else lookup.candidate_clusters
    too_many = len(clusters) > MAX_CANDIDATES
    guarded = [
        _rule_guard(
            record,
            cluster=cluster,
            candidate_index=index,
            depends_on=(lookup.node_id,),
            client=client,
            fetch_court=not too_many,
        )
        for index, cluster in enumerate(clusters, start=1)
    ]
    agreeing = [guard for guard in guarded if guard.verdict is not None]
    if agreeing:
        return _conclude(agreeing[0].verdict, record, records_at_locator=len(clusters), agreeing=agreeing)
    if len(guarded) == 1:
        verdict = await _model_judge(
            record, guarded[0], document_text=document_text, citations=citations, session=session
        )
        return _conclude(verdict, record, records_at_locator=1, agreeing=())
    if too_many:
        return record.append(
            _resolution(
                record,
                IdentityOutcome.AMBIGUOUS_IDENTITY,
                reason=IdentityReason.CROWDED_PAGE,
                depends_on=(scope.node_id, *(node_id for guard in guarded for node_id in guard.node_ids)),
                message=(
                    f"{len(clusters)} records at the locator, none agreeing with the filing on every field, "
                    f"and more than the {MAX_CANDIDATES} a judgement is shown at once."
                ),
                records_at_locator=len(clusters),
            )
        )
    verdict = await _judge_candidates(
        record, guarded, document_text=document_text, citations=citations, session=session
    )
    return _conclude(verdict, record, records_at_locator=len(clusters), agreeing=())


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
    reconciled: DateReconciliationNode | None = None
    """The archive's other dates, read when the plain date comparison disagreed."""

    @property
    def node_ids(self) -> tuple[str, ...]:
        ids = (self.candidate.node_id, self.case_name.node_id, self.date.node_id, self.court.node_id)
        return (*ids, self.reconciled.node_id) if self.reconciled is not None else ids

    @property
    def compatible_years(self) -> tuple[str, ...]:
        """Years the archive holds for the record beside its filing date."""
        if self.reconciled is None:
            return ()
        return tuple(sorted({m for p in self.reconciled.dated_phrases for m in _YEAR.findall(p)}))


def _rule_guard(
    record: CitationRecord,
    *,
    cluster: CourtListenerOpinionCluster,
    candidate_index: int,
    depends_on: tuple[str, ...],
    client: CourtListenerServiceClient,
    fetch_court: bool = True,
) -> _Guarded:
    """Run the three rule comparisons on one candidate. No model is consulted.

    ``fetch_court`` is off on a page with more records than a judgement would
    be shown, since each court costs a request; the comparison then rests on
    the reporter's family alone.
    """
    candidate = record.append(
        run_locator_candidate_evaluation(
            record.trace, cluster=cluster, candidate_index=candidate_index, depends_on=depends_on
        )
    )
    case_name = record.append(run_case_name_agreement(record.citation, candidate=candidate))
    date = record.append(run_date_check(record.citation, candidate=candidate))
    if date.outcome is FieldCheckOutcome.MISMATCH and fetch_court:
        # The archive's one date is the original opinion's; a reporter cites
        # the amended print. Read the archive's other dates before believing
        # the disagreement. Two requests, on the few records that disagree.
        reconciled = record.append(
            run_date_reconciliation(candidate, date, client=client, fetched=record.opinions)
        )
        date_agrees = reconciled.outcome is FieldCheckOutcome.COMPATIBLE
    else:
        reconciled = None
        date_agrees = date.outcome is not FieldCheckOutcome.MISMATCH
    if fetch_court:
        court_retrieval = record.append(
            run_docket_court_retrieval(record.trace, candidate=candidate, client=client)
        )
        court = record.append(run_court_comparison(record.citation, evidence=court_retrieval))
    else:
        court = record.append(run_court_comparison(record.citation, evidence=candidate))
    rules_agree = (
        (case_name.outcome.agrees or case_name.outcome.value == "unavailable")
        and court.outcome is not FieldCheckOutcome.MISMATCH
        and date_agrees
    )
    guarded = _Guarded(cluster, candidate, case_name, date, court, None, reconciled)
    if not rules_agree:
        return guarded
    verdict = Verdict(IdentityOutcome.CONFIRMED_IDENTITY, None, cluster, "rule", (), guarded.node_ids)
    return _Guarded(cluster, candidate, case_name, date, court, verdict, reconciled)


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


async def _judge_candidates(
    record: CitationRecord,
    guarded: Sequence[_Guarded],
    *,
    document_text: str,
    citations: Sequence[ExtractedCitation],
    session: MelleaSession | None,
) -> Verdict:
    """Ask the model, over every record at the locator, which is the filing's case."""
    judgment = record.append(
        await run_mellea_candidate_judgment(
            record,
            document_text=document_text,
            citations=citations,
            candidates=[guard.candidate for guard in guarded],
            checks=[(guard.case_name, guard.court, guard.date) for guard in guarded],
            compatible_years=[guard.compatible_years for guard in guarded],
            session=session,
        )
    )
    apply_readings(record, judgment)
    node_ids = (*(node_id for guard in guarded for node_id in guard.node_ids), judgment.node_id)
    if judgment.outcome is IdentityVerdict.SAME_CASE and judgment.chosen_index is not None:
        chosen = guarded[judgment.chosen_index - 1]
        answer = judgment.candidates[judgment.chosen_index - 1]
        fields = chosen_disagreements(
            judgment,
            answer,
            chosen.case_name,
            chosen.court,
            chosen.date,
            compatible_years=chosen.compatible_years,
        )
        if fields:
            return Verdict(
                IdentityOutcome.WRONG_IDENTITY,
                IdentityReason.FIELD_DISAGREEMENT,
                chosen.cluster,
                judgment.node_id,
                fields,
                node_ids,
            )
        return Verdict(
            IdentityOutcome.CONFIRMED_IDENTITY, None, chosen.cluster, judgment.node_id, (), node_ids
        )
    if judgment.outcome is IdentityVerdict.DIFFERENT_CASE:
        return Verdict(
            IdentityOutcome.WRONG_IDENTITY,
            IdentityReason.DIFFERENT_CASE_AT_LOCATOR,
            guarded[0].cluster,
            judgment.node_id,
            (),
            node_ids,
        )
    return Verdict(
        IdentityOutcome.DEFER_TO_SEARCH,
        IdentityReason.UNDETERMINABLE,
        guarded[0].cluster,
        judgment.node_id,
        (),
        node_ids,
    )


def _conclude(
    verdict: Verdict,
    record: CitationRecord,
    *,
    records_at_locator: int,
    agreeing: Sequence[_Guarded],
) -> IdentityResolutionNode:
    """Write the resolution one verdict implies, disclosing what else sat at the page."""
    outcome, reason = verdict.outcome, verdict.reason
    scope = _scope_node(record)
    others = records_at_locator - 1
    if outcome is IdentityOutcome.CONFIRMED_IDENTITY:
        message = "The locator names one case and every field the filing states agrees with it."
        if len(agreeing) > 1:
            message = (
                f"{len(agreeing)} of {records_at_locator} records at the locator agree with the filing on every "
                "field; they are one decision the archive holds more than once."
            )
        elif others:
            message = (
                f"One of {records_at_locator} records at the locator agrees with the filing on every field."
                if verdict.decided_by == "rule"
                else f"The judgement chose one of {records_at_locator} records at the locator as the filing's case."
            )
    elif reason is IdentityReason.FIELD_DISAGREEMENT:
        names = ", ".join(field.field for field in verdict.fields)
        message = f"The locator names the case, but the filing's {names} disagree{'s' if len(verdict.fields) == 1 else ''} with the record."
    elif reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR:
        listed = _names_at_locator(record, verdict)
        message = (
            f"The locator names a different case: {listed[0]}."
            if len(listed) == 1
            else f"The locator names {len(listed)} records, none the filing's case: {'; '.join(listed)}."
        )
    else:
        message = "Nothing at the locator could be shown to be the filing's case, or not to be."
    node = _resolution(
        record,
        outcome,
        reason=reason,
        cluster_id=verdict.cluster.cluster_id,
        record_case_name=verdict.cluster.case_name,
        decided_by=verdict.decided_by,
        fields=verdict.fields,
        depends_on=(scope.node_id, *verdict.node_ids),
        message=message,
        records_at_locator=records_at_locator,
        agreeing_cluster_ids=tuple(g.cluster.cluster_id or "" for g in agreeing) if len(agreeing) > 1 else (),
    )
    record.append(node)
    if node.resolved:
        record.resolve(
            Resolution(
                cluster_id=verdict.cluster.cluster_id,
                case_name=verdict.cluster.case_name,
                date_filed=verdict.cluster.date_filed,
                court_id=_retrieved_court(record, verdict.node_ids),
                node_id=node.node_id,
                opinion_ids=_opinions_read(record, verdict.node_ids),
                dates=_dates_explored(record, verdict.node_ids),
            )
        )
    return node


def _dates_explored(record: CitationRecord, node_ids: tuple[str, ...]) -> DateExploration | None:
    """The date history the reconciliation wrote for this candidate, when it ran."""
    for node in record.trace.nodes:
        if isinstance(node, DateReconciliationNode) and node.node_id in node_ids:
            return exploration_of(node)
    return None


def _opinions_read(record: CitationRecord, node_ids: tuple[str, ...]) -> tuple[str, ...]:
    """The opinions the reconciliation fetched for this candidate, the one that answered first."""
    for node in record.trace.nodes:
        if isinstance(node, DateReconciliationNode) and node.node_id in node_ids:
            first = (node.opinion_id,) if node.opinion_id else ()
            return (*first, *(o for o in node.opinions_read if o != node.opinion_id))
    return ()


def _names_at_locator(record: CitationRecord, verdict: Verdict) -> list[str]:
    """The case names of every record the verdict rests on, in candidate order."""
    names = [
        node.case_name or "unnamed"
        for node in record.trace.nodes
        if isinstance(node, CandidateEvaluationNode) and node.node_id in verdict.node_ids
    ]
    return names or [verdict.cluster.case_name or "unnamed"]


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
    records_at_locator: int = 1,
    agreeing_cluster_ids: tuple[str, ...] = (),
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
        records_at_locator=records_at_locator,
        agreeing_cluster_ids=agreeing_cluster_ids,
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
