"""Identity of a case cited by docket number.

A docket citation -- `Reyes v. Pac. Bell, No. 1:25-cv-05745-RPK (E.D.N.Y. Oct.
31, 2024)` -- is a full citation: the docket number and the court together
name one case with no help from the text around them. It cannot be checked by
the locator route, which needs a volume, a reporter and a page; it is checked
by :mod:`mellea_lrc.validation.docket_lookup`, which asks two archives the
same key and needs no model.

What comes back is a caption and every decision each archive holds for the
case, dated. The caption is compared with the parties the filing wrote by the
same rule as a reporter record's; a day the filing states is read against the
decisions, and a day on which neither archive holds anything the court wrote
is disclosed on the node. Nothing under the key in any archive defers the
root to search, as before, since absence from an archive is not falsity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mellea_lrc.core.citations import DocketCitation
from mellea_lrc.validation.docket_lookup import lookup_docket
from mellea_lrc.validation.identity.case_name import compare_case_names
from mellea_lrc.validation.identity.field_checks import iso_date
from mellea_lrc.validation.types import (
    CaseNameAgreement,
    DocketArchiveAnswer,
    DocketDecisionRecord,
    DocketIdentityNode,
    DocketIdentityOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.govinfo import GovinfoServiceClient
    from mellea_lrc.validation.record import CitationRecord


def run_docket_identity(
    record: CitationRecord,
    *,
    client: CourtListenerServiceClient | None = None,
    govinfo: GovinfoServiceClient | None = None,
) -> DocketIdentityNode:
    """Ask both archives for the case under the filing's court and docket number."""
    citation = record.citation
    if not isinstance(citation, DocketCitation):
        msg = "Docket identity requires a docket citation"
        raise TypeError(msg)
    node_id = f"{record.citation_id}:docket_identity"
    number = citation.docket_number or ""
    if not citation.court or not number.strip():
        return DocketIdentityNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=DocketIdentityOutcome.NO_COURT,
            docket_number=citation.docket_number,
            court_id=citation.court,
            status_message="Skipped docket identity because the key is incomplete.",
            outcome_message="A docket number without a court is not a key: every district has one like it.",
        )
    if client is None and govinfo is None:
        return DocketIdentityNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=DocketIdentityOutcome.UNAVAILABLE,
            docket_number=citation.docket_number,
            court_id=citation.court,
            status_message="Skipped docket identity because no archive client was given.",
            outcome_message="No archive was asked.",
        )
    found = lookup_docket(citation.court, number, courtlistener=client, govinfo=govinfo)
    answers = tuple(
        DocketArchiveAnswer(
            archive=answer.archive,
            status=answer.status,
            identifier=answer.identifier,
            docket_number=answer.docket_number,
            caption=answer.caption,
            date_filed=answer.date_filed,
            decisions=len(answer.decisions),
            error=answer.error,
            candidates=answer.candidates,
        )
        for answer in found.answers
    )
    decisions = tuple(
        DocketDecisionRecord(d.archive, d.identifier, d.date, d.description) for d in found.decisions
    )
    statuses = {answer.status for answer in found.answers}
    date_stated = iso_date(citation.date)
    if not found.found:
        if statuses <= {"unavailable"}:
            outcome, status = DocketIdentityOutcome.UNAVAILABLE, ValidationNodeStatus.FAILED
            message = "No archive answered: " + "; ".join(f"{a.archive}: {a.error}" for a in found.answers)
        elif "several" in statuses:
            outcome, status = DocketIdentityOutcome.SEVERAL, ValidationNodeStatus.SUCCEEDED
            message = "An archive holds several cases under the key: " + "; ".join(
                f"{a.archive}: {', '.join(a.candidates)}" for a in found.answers if a.status == "several"
            )
        else:
            outcome, status = DocketIdentityOutcome.NOT_FOUND, ValidationNodeStatus.SUCCEEDED
            message = "No archive holds a case under the key" + (
                " ("
                + "; ".join(
                    f"{a.archive}: {a.status}" + (f", {a.error}" if a.error else "") for a in found.answers
                )
                + ")."
            )
        return DocketIdentityNode(
            node_id=node_id,
            status=status,
            outcome=outcome,
            docket_number=citation.docket_number,
            court_id=citation.court,
            status_message="Docket identity completed.",
            outcome_message=message,
            answers=answers,
            decisions=decisions,
            date_stated=date_stated,
        )
    comparison = compare_case_names(
        plaintiff=citation.plaintiff, defendant=citation.defendant, recorded=found.caption
    )
    on_date = len(found.decisions_on(date_stated)) if date_stated and found.decisions else None
    held = ", ".join(f"{a.archive} ({a.identifier}, {len(a.decisions)} decisions)" for a in found.found)
    return DocketIdentityNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=DocketIdentityOutcome.FOUND,
        docket_number=citation.docket_number,
        court_id=citation.court,
        status_message="Docket identity completed.",
        outcome_message=f"The key names {found.caption!r} in {held}. Case name: {comparison.reason}",
        caption=found.caption,
        answers=answers,
        decisions=decisions,
        name_agreement=comparison.agreement,
        date_stated=date_stated,
        decisions_on_date=on_date,
    )


__all__ = ["run_docket_identity"]
