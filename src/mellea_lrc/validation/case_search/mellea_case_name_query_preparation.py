"""Mellea preparation of a CourtListener case-name search query."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from mellea.core import ValidationResult
from mellea.stdlib.requirements import req
from mellea.stdlib.sampling import MultiTurnStrategy
from pydantic import BaseModel, ConfigDict, ValidationError

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.llm import (
    InstructIvrSpec,
    llm_api_config_from_env,
    run_instruct_ivr,
    start_mellea_session_from_env,
)
from mellea_lrc.validation.types import (
    CitationValidation,
    MelleaCaseNameQueryPreparationNode,
    MelleaCaseNameQueryPreparationOutcome,
    MelleaCaseNameReextractionNode,
    MelleaCaseNameReextractionOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea import MelleaSession
    from mellea.core.base import Context

# A reasoning model spends this budget on reasoning before it emits anything,
# and how much it spends varies run to run: the same one-field verdict prompt
# used 43, 74, 120, 171 and 392 reasoning tokens on five consecutive calls.
# When the budget runs out first the response comes back with no content at all
# and the verdict is lost, which is a silent failure rather than a worse answer.
# These are therefore sized for the reasoning, not for the JSON.
MAX_TOKENS = 1024
MAX_REPAIR_TURNS = 2
INSTRUCTION = """
Prepare broad but faithful party-name search terms for a legal case search.

You receive the plaintiff and defendant names from one case citation. A downstream
program will add search syntax and a court filter. Your only task is to provide
one term for each party in the structured output fields ``query_plaintiff`` and
``query_defendant``.

Prefer the shortest distinctive term likely to retrieve the same party. You may:

- normalize whitespace or punctuation;
- expand an unambiguous legal abbreviation;
- remove generic organizational or governmental wording when the remaining term
  preserves the party's identifying core;
- simplify reordered forms of the same identifying core.

Example:

- plaintiff: "City of New York"
- defendant: "New York City"
- query_plaintiff: "New York"
- query_defendant: "New York"

Another example:

- plaintiff: "Methodist Hosp. of Sacramento"
- defendant: "Shalala"
- query_plaintiff: "Methodist Hospital of Sacramento"
- query_defendant: "Shalala"

Do not use outside knowledge to correct or replace a name. Do not invent missing
words, combine the two parties, omit either party, add alternative terms, or
include quotes, operators, field names, court identifiers, or search-query
syntax. Return exactly one non-empty term for each output field.

plaintiff:
{{plaintiff}}

defendant:
{{defendant}}
""".strip()


class _QueryTermsProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_plaintiff: str
    query_defendant: str


async def run_mellea_case_name_query_preparation(
    validation: CitationValidation,
    *,
    reextraction: MelleaCaseNameReextractionNode,
    session: MelleaSession | None = None,
) -> MelleaCaseNameQueryPreparationNode:
    """Prepare query terms, then construct one CourtListener query locally."""
    court_id = _court_id(validation)
    if (
        reextraction.outcome is not MelleaCaseNameReextractionOutcome.COMPLETE
        or reextraction.plaintiff is None
        or reextraction.defendant is None
        or court_id is None
    ):
        return _node(
            validation,
            reextraction,
            ValidationNodeStatus.SKIPPED,
            MelleaCaseNameQueryPreparationOutcome.UNAVAILABLE,
            court_id=court_id,
            status_message="Skipped case-name query preparation because required search evidence is missing.",
            outcome_message="Search query is unavailable without both re-extracted parties and a court identifier.",
        )
    try:
        resolved_session = session or start_mellea_session_from_env()
        spec = InstructIvrSpec(
            description=INSTRUCTION,
            user_variables={
                "plaintiff": reextraction.plaintiff,
                "defendant": reextraction.defendant,
            },
            output_format=_QueryTermsProposal,
            requirements=[req("Return valid case-name query terms.", validation_fn=_valid_schema)],
        )
        result = await run_instruct_ivr(
            resolved_session,
            spec,
            strategy=MultiTurnStrategy(loop_budget=MAX_REPAIR_TURNS),
            model_options=llm_api_config_from_env(os.environ).mellea_call_options(max_tokens=MAX_TOKENS),
        )
        if not result.success:
            return _node(
                validation,
                reextraction,
                ValidationNodeStatus.FAILED,
                MelleaCaseNameQueryPreparationOutcome.FAILED,
                court_id=court_id,
                status_message="Case-name query preparation exhausted its repair attempts.",
                outcome_message="No CourtListener case-name query is available.",
                error="Case-name query preparation exhausted its repair budget",
            )
        terms = _proposal(result.result.value)
        year = _year(validation)
        query = _query(terms, court_id, year)
    except Exception as exc:
        return _node(
            validation,
            reextraction,
            ValidationNodeStatus.FAILED,
            MelleaCaseNameQueryPreparationOutcome.FAILED,
            court_id=court_id,
            status_message="Case-name query preparation failed during execution.",
            outcome_message="No CourtListener case-name query is available.",
            error=f"{type(exc).__name__}: {exc}",
        )
    return _node(
        validation,
        reextraction,
        ValidationNodeStatus.SUCCEEDED,
        MelleaCaseNameQueryPreparationOutcome.PREPARED,
        court_id=court_id,
        query=query,
        query_plaintiff=terms.query_plaintiff,
        query_defendant=terms.query_defendant,
        year=year,
        status_message="Case-name query preparation completed.",
        outcome_message=(
            "Prepared one CourtListener case-name query from both re-extracted parties"
            + (f", narrowed to {year} give or take {YEAR_WINDOW} year." if year else ".")
        ),
    )


def _node(
    validation: CitationValidation,
    reextraction: MelleaCaseNameReextractionNode,
    status: ValidationNodeStatus,
    outcome: MelleaCaseNameQueryPreparationOutcome,
    *,
    court_id: str | None,
    query: str | None = None,
    query_plaintiff: str | None = None,
    query_defendant: str | None = None,
    year: str | None = None,
    status_message: str | None = None,
    outcome_message: str | None = None,
    error: str | None = None,
) -> MelleaCaseNameQueryPreparationNode:
    return MelleaCaseNameQueryPreparationNode(
        node_id=f"{validation.citation_id}:mellea_case_name_query_preparation",
        status=status,
        outcome=outcome,
        query=query,
        query_plaintiff=query_plaintiff,
        query_defendant=query_defendant,
        court_id=court_id,
        year=year,
        depends_on=(reextraction.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
        error=error,
    )


def _court_id(validation: CitationValidation) -> str | None:
    citation = validation.citation.citation
    return citation.court if isinstance(citation, FullCaseCitation) else None


def _year(validation: CitationValidation) -> str | None:
    citation = validation.citation.citation
    return citation.year if isinstance(citation, FullCaseCitation) else None


def _proposal(value: object) -> _QueryTermsProposal:
    try:
        proposal = _QueryTermsProposal.model_validate_json(value)
    except ValidationError as exc:
        msg = f"Invalid case-name query preparation output: {exc}"
        raise ValueError(msg) from exc
    if not proposal.query_plaintiff.strip() or not proposal.query_defendant.strip():
        msg = "Case-name query terms must not be blank"
        raise ValueError(msg)
    return proposal


def _valid_schema(ctx: Context) -> ValidationResult:
    try:
        _proposal(ctx.last_output().value)
    except ValueError as exc:
        return ValidationResult(result=False, reason=str(exc))
    return ValidationResult(result=True)


# A citation's parenthetical states the year the case was decided, and every
# citation that reaches this step states one -- 25 of 25 in the last
# measurement, and 30 of 30 under a looser reading of the party requirement. So
# the year is a filter the search was giving away for nothing.
#
# The window is a year either side rather than the year itself. A decision
# handed down in December is reported in the following year's volume, an
# amended opinion carries a later date than the one the filing read, and this
# project would rather search too wide than miss the case it is looking for.
YEAR_WINDOW = 1


def _query(terms: _QueryTermsProposal, court_id: str, year: str | None) -> str:
    """Construct CourtListener query syntax outside the Mellea response."""
    query = (
        f"caseName:({_term(terms.query_plaintiff)} AND {_term(terms.query_defendant)}) "
        f"AND court_id:{court_id}"
    )
    span = _year_span(year)
    return f"{query} AND {span}" if span else query


def _year_span(year: str | None) -> str | None:
    """A date range around the year the citation states, or None if it states none."""
    if not year or not year.isdigit():
        return None
    stated = int(year)
    return f"dateFiled:[{stated - YEAR_WINDOW}-01-01 TO {stated + YEAR_WINDOW}-12-31]"


def _term(value: str) -> str:
    """Return one quoted query term with CourtListener-special characters escaped."""
    escaped = value.strip().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
