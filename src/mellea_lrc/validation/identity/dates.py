"""Reconcile a date the filing states with every date the archive holds for a record.

A lookup record carries one date, ``date_filed``, and it is the date of the
opinion the archive holds. A reporter citation states the year of the print.
For an opinion amended, reheard or reissued into the following year the two
differ by design: the archive dates the original, the reporter carries the
amended one, and the filing that copies the reporter is right.

This is a known way the archive disagrees with a correct citation, so it is
checked explicitly and the evidence is kept, rather than any difference under
a year being waved through. When the plain comparison disagrees, two more
things are read, each a request:

1. the cluster itself, whose ``other_dates`` is free text of every date beside
   the filing date -- `Argued and Submitted April 18, 2013., Amended Feb. 5,
   2014.`
2. failing that, the headers of the cluster's opinions, read in turn, where a
   court prints `Decided December 20, 1948` or `Filed September 28, 2021`

A dated event that states the filing's year -- decided, amended, filed,
reissued, modified -- makes the date ``compatible``, and the node carries the
phrase. Everything read is also written onto the record's resolution as a
:class:`~mellea_lrc.validation.record.DateExploration`, matched or not.

TODO(date-analysis): a record whose only disagreeing field is the date, after
this reconciliation, is where the next step begins. It should read the
exploration on the resolution and say what the disagreement is; see
``IdentifiedDocument.date_only_disagreements``. Nothing in this module makes
that judgement. Argued and submitted dates do not count: a case is argued before it is
decided, and a filing citing the argument year is wrong. Nothing found leaves
the ``mismatch`` standing, with everything that was read on the node, so a
reader can see the archive holds no date the filing's year could have come
from.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.validation.record import DateExploration
from mellea_lrc.validation.types import DateReconciliationNode, FieldCheckOutcome, ValidationNodeStatus

if TYPE_CHECKING:
    from mellea_lrc.courtlistener import CourtListenerOpinion
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.validation.types import CandidateEvaluationNode, DateCheckNode

HEADER_CHARS = 3000
"""How far into an opinion's text the dated header is looked for."""
MAX_OPINIONS = 4
"""How many of a cluster's opinions are read for a header, each a request."""

_EVENT = re.compile(
    r"\b(?:Decided|Filed|Amended|Reissued|Modified|Re-?filed|Opinion filed|As amended|"
    r"Rehearing denied|Certiorari denied|Entered)\b[^;\n]{0,60}?\b(\d{4})\b",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")


def dated_events(text: str) -> tuple[str, ...]:
    """Every dated event in the text, as written: `Amended Feb. 5, 2014`."""
    return tuple(" ".join(match.group(0).split()) for match in _EVENT.finditer(text))


def run_date_reconciliation(
    candidate: CandidateEvaluationNode,
    date: DateCheckNode,
    *,
    client: CourtListenerServiceClient,
    fetched: dict[str, CourtListenerOpinion] | None = None,
) -> DateReconciliationNode:
    """Read the archive's other dates for a record the plain comparison disagreed with.

    ``fetched`` collects every opinion read, by id, so the caller can keep the
    text for a later stage rather than fetch it twice.
    """
    node_id = f"{date.node_id}:date_reconciliation"
    year = (date.extracted_date or "")[:4]
    if date.outcome is not FieldCheckOutcome.MISMATCH or not year or candidate.cluster_id is None:
        return _node(
            node_id,
            date,
            ValidationNodeStatus.SKIPPED,
            FieldCheckOutcome.UNAVAILABLE,
            status_message="Skipped date reconciliation because the plain comparison did not disagree.",
            outcome_message="Nothing to reconcile.",
        )
    try:
        cluster = client.get_cluster(candidate.cluster_id)
    except CourtListenerError as exc:
        return _node(
            node_id,
            date,
            ValidationNodeStatus.FAILED,
            FieldCheckOutcome.MISMATCH,
            status_message="Date reconciliation failed while fetching the cluster.",
            outcome_message="The plain comparison stands; the cluster's other dates could not be read.",
            error=exc.message,
        )
    phrases = list(dated_events(cluster.other_dates))
    matched = _states_year(phrases, year)
    opinion_id: str | None = None
    opinions_read: list[str] = []
    by_opinion: list[tuple[str, tuple[str, ...]]] = []
    # The cluster lists its opinions in no useful order: the lead opinion,
    # which starts at the judge's name, may come before the combined one that
    # carries the court's header. Each is read until one states the year.
    for candidate_opinion in cluster.sub_opinion_ids[:MAX_OPINIONS] if matched is None else ():
        try:
            opinion = client.get_opinion(candidate_opinion)
        except CourtListenerError as exc:
            return _node(
                node_id,
                date,
                ValidationNodeStatus.FAILED,
                FieldCheckOutcome.MISMATCH,
                other_dates=cluster.other_dates,
                opinion_id=None,
                opinions_read=tuple(opinions_read),
                dated_phrases=tuple(phrases),
                status_message="Date reconciliation failed while fetching an opinion.",
                outcome_message="The plain comparison stands; an opinion's header could not be read.",
                error=exc.message,
            )
        opinions_read.append(candidate_opinion)
        if fetched is not None:
            fetched[candidate_opinion] = opinion
        header = " ".join(_TAG.sub(" ", opinion.html_with_citations).split())[:HEADER_CHARS]
        found = dated_events(header)
        phrases.extend(found)
        by_opinion.append((candidate_opinion, found))
        matched = _states_year(list(found), year)
        if matched is not None:
            opinion_id = candidate_opinion
            break
    if matched is not None:
        return _node(
            node_id,
            date,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.COMPATIBLE,
            other_dates=cluster.other_dates,
            opinion_id=opinion_id,
            opinions_read=tuple(opinions_read),
            dated_phrases=tuple(phrases),
            phrases_by_opinion=tuple(by_opinion),
            matched_phrase=matched,
            status_message="Date reconciliation completed.",
            outcome_message=(
                f"The archive dates the record {date.retrieved_date}, and also holds '{matched}', "
                "which states the filing's year."
            ),
        )
    return _node(
        node_id,
        date,
        ValidationNodeStatus.SUCCEEDED,
        FieldCheckOutcome.MISMATCH,
        other_dates=cluster.other_dates,
        opinion_id=None,
        opinions_read=tuple(opinions_read),
        dated_phrases=tuple(phrases),
        phrases_by_opinion=tuple(by_opinion),
        status_message="Date reconciliation completed.",
        outcome_message=(
            f"No dated event the archive holds for the record states {year}: "
            + (", ".join(f"'{p}'" for p in phrases) if phrases else "none was found")
            + "."
        ),
    )


def _states_year(phrases: list[str], year: str) -> str | None:
    for phrase in phrases:
        if re.search(rf"\b{year}\b", phrase):
            return phrase
    return None


def _node(
    node_id: str,
    date: DateCheckNode,
    status: ValidationNodeStatus,
    outcome: FieldCheckOutcome,
    *,
    other_dates: str | None = None,
    opinion_id: str | None = None,
    opinions_read: tuple[str, ...] = (),
    dated_phrases: tuple[str, ...] = (),
    phrases_by_opinion: tuple[tuple[str, tuple[str, ...]], ...] = (),
    matched_phrase: str | None = None,
    status_message: str,
    outcome_message: str,
    error: str | None = None,
) -> DateReconciliationNode:
    return DateReconciliationNode(
        node_id=node_id,
        status=status,
        outcome=outcome,
        extracted_date=date.extracted_date,
        retrieved_date=date.retrieved_date,
        other_dates=other_dates,
        opinion_id=opinion_id,
        opinions_read=opinions_read,
        dated_phrases=dated_phrases,
        phrases_by_opinion=phrases_by_opinion,
        matched_phrase=matched_phrase,
        depends_on=(date.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
        error=error,
    )


def exploration_of(node: DateReconciliationNode) -> DateExploration | None:
    """The date history a reconciliation node holds, in the shape the resolution keeps."""
    if node.status is ValidationNodeStatus.SKIPPED or node.extracted_date is None:
        return None
    return DateExploration(
        stated=node.extracted_date,
        stated_precision="day" if len(node.extracted_date) > 4 else "year",
        record_date_filed=node.retrieved_date,
        other_dates=node.other_dates,
        phrases_by_opinion=node.phrases_by_opinion,
        matched_phrase=node.matched_phrase,
        matched_opinion_id=node.opinion_id,
    )
