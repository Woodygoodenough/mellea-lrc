"""Identity of a case cited by docket number. Recorded as a route, not yet run.

A docket citation -- `Reyes v. Pac. Bell, No. 1:25-cv-05745-RPK (E.D.N.Y. Oct.
31, 2024)` -- is a full citation: the docket number and the court together name
one case with no help from the text around them. It is a root in the citation
tree like any reporter citation, and it is checkable. It just cannot be checked
by the locator route, because it has no volume, reporter or page.

## The route, when it is built

1. Search RECAP by docket number scoped to the court: the client's ``search``
   with ``search_type="d"`` (dockets) or ``"r"`` (RECAP documents) and a query
   of the form ``docketNumber:"1:25-cv-05745" court_id:nyed``. The docket
   number is compared loosely -- filings drop the judge's initials, and a
   converter can drop a hyphen, as the extraction layer's docket reader notes.
2. A single docket returned is the candidate. Its ``case_name`` and
   ``date_filed`` go through the same rule guard and composite judgement as a
   reporter candidate, with two differences: the court is already known, since
   the query was scoped to it, and the date the filing states is usually a
   full day, so the comparison is at day precision.
3. Several dockets returned are separated by the filing's case name, as a
   crowded reporter page is.
4. Nothing returned is ``UNRESOLVED`` and goes to open search with the rest.
   RECAP holds a docket only when someone has paid to retrieve it, so absence
   here says less than absence from the opinion archive does.

The reporter route is the common case and is built first. This node records
that a docket root was seen and not checked, so a document's identity summary
counts it as deferred rather than silently omitting it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mellea_lrc.core.citations import DocketCitation
from mellea_lrc.validation.types import DocketIdentityNode, DocketIdentityOutcome, ValidationNodeStatus

if TYPE_CHECKING:
    from mellea_lrc.validation.record import CitationRecord


def run_docket_identity(record: CitationRecord) -> DocketIdentityNode:
    """Record that a docket root was seen and that its route is not built."""
    citation = record.citation
    if not isinstance(citation, DocketCitation):
        msg = "Docket identity requires a docket citation"
        raise TypeError(msg)
    return DocketIdentityNode(
        node_id=f"{record.citation_id}:docket_identity",
        status=ValidationNodeStatus.SKIPPED,
        outcome=DocketIdentityOutcome.NOT_IMPLEMENTED,
        docket_number=citation.docket_number,
        court_id=citation.court,
        status_message="Skipped docket identity because the RECAP route is not built yet.",
        outcome_message=(
            "A case cited by docket number is checkable through RECAP; the route is "
            "described in validation/identity/docket.py and not yet run."
        ),
    )
