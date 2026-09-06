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
2. failing that, the header of the cluster's first opinion, where a court
   prints `Decided December 20, 1948` or `Filed September 28, 2021`

A dated event that states the filing's year -- decided, amended, filed,
reissued, modified -- makes the date ``compatible``, and the node carries the
phrase. Argued and submitted dates do not count: a case is argued before it is
decided, and a filing citing the argument year is wrong. Nothing found leaves
the ``mismatch`` standing, with everything that was read on the node, so a
reader can see the archive holds no date the filing's year could have come
from.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.validation.types import DateReconciliationNode, FieldCheckOutcome, ValidationNodeStatus

if TYPE_CHECKING:
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.validation.types import CandidateEvaluationNode, DateCheckNode

HEADER_CHARS = 3000
"""How far into an opinion's text the dated header is looked for."""

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
) -> DateReconciliationNode:
    """Read the archive's other dates for a record the plain comparison disagreed with."""
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
    if matched is None and cluster.sub_opinion_ids:
        opinion_id = cluster.sub_opinion_ids[0]
        try:
            opinion = client.get_opinion(opinion_id)
        except CourtListenerError as exc:
            return _node(
                node_id,
                date,
                ValidationNodeStatus.FAILED,
                FieldCheckOutcome.MISMATCH,
                other_dates=cluster.other_dates,
                opinion_id=opinion_id,
                dated_phrases=tuple(phrases),
                status_message="Date reconciliation failed while fetching the opinion.",
                outcome_message="The plain comparison stands; the opinion's header could not be read.",
                error=exc.message,
            )
        header = " ".join(_TAG.sub(" ", opinion.html_with_citations).split())[:HEADER_CHARS]
        phrases.extend(dated_events(header))
        matched = _states_year(phrases, year)
    if matched is not None:
        return _node(
            node_id,
            date,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.COMPATIBLE,
            other_dates=cluster.other_dates,
            opinion_id=opinion_id,
            dated_phrases=tuple(phrases),
            matched_phrase=matched,
            status_message="Date reconciliation completed.",
            outcome_message=f"The archive dates the record {date.retrieved_date}, and also holds '{matched}', which states the filing's year.",
        )
    return _node(
        node_id,
        date,
        ValidationNodeStatus.SUCCEEDED,
        FieldCheckOutcome.MISMATCH,
        other_dates=cluster.other_dates,
        opinion_id=opinion_id,
        dated_phrases=tuple(phrases),
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
    dated_phrases: tuple[str, ...] = (),
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
        dated_phrases=dated_phrases,
        matched_phrase=matched_phrase,
        depends_on=(date.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
        error=error,
    )
