"""One model call over every record at a locator, when the rules matched none.

A locator that returns several records is the ambiguous branch. The rules run
on each record first, and a record whose every comparable field agrees with
the filing confirms the identity without a model. This module is for the rest:
no record agreed, and the question is whether any of them is nonetheless the
filing's case -- written under a different caption, abbreviated past what the
rules allow, or held with a field the filing misstates -- or whether none is.

That is one question over the whole set, not one per record. Shown all of
them at once, the model can say that two records are one decision held twice,
that a third is a different case, and that the filing's case is the second;
shown one at a time it could only say "not this one" three times and never
that the page as a whole answers the question. So the filing's reading -- one
case name, court and date, each with its evidence -- is read once and grounded
in the same windows as the single-candidate judgement, and the model answers
per record, then chooses one or none.

The choice is held to the answers. A chosen record must be one whose name the
model called the same case, a variant of it or a misspelling; a verdict that the filing's
case is not at the page needs every record judged not the filing's case; and
anything short of both is undeterminable, which defers to search.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

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
from mellea_lrc.validation.identity.case_name import written_case_name
from mellea_lrc.validation.identity.field_checks import iso_date
from mellea_lrc.validation.identity.mellea_judgment import (
    GROUNDING_CHECKS,
    MAX_REPAIR_TURNS,
    Grounding,
    IdentityJudgment,
    context_window,
    court_label,
    describe_fields,
    last_output,
    readings_grounded,
)
from mellea_lrc.validation.identity.reporter_courts import implied_courts
from mellea_lrc.validation.identity.windows import windows_for
from mellea_lrc.validation.types import (
    CandidateAnswer,
    FieldAgreement,
    IdentityVerdict,
    MelleaCandidateJudgmentNode,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea import MelleaSession
    from mellea.core.base import Context

    from mellea_lrc.extraction.types import ExtractedCitation
    from mellea_lrc.validation.identity.windows import CitationWindows
    from mellea_lrc.validation.record import CitationRecord
    from mellea_lrc.validation.types import (
        CandidateEvaluationNode,
        CaseNameAgreementNode,
        CourtCheckNode,
        DateCheckNode,
    )

MAX_TOKENS = 2048
MAX_CANDIDATES = 6
"""How many records the model is shown at once. A page with more is ambiguous
unless the rules matched one of them."""

INSTRUCTION = """
You are checking one legal citation in a court filing against the records an
archive holds at that citation's volume, reporter and page. The archive holds
{{count}} records there, and none of them agreed with the filing on every
field by rule. Decide, for each record, whether it is the case the filing
cites, and then which record, if any, the filing's case is.

First read the filing's own words. `context` shows the citation in its
surroundings, marked between [[ and ]]. Two windows bound what you may read:
`name_window`, the text before the locator, is where the case name must come
from; `parenthetical_window`, the text after it, is where the court and date
must come from. Report `case_name_read` as the filing wrote it, or null;
`court_read` as a courts-db identifier with `court_basis` `stated` and
`court_evidence` the exact string that names it, or `implied_by_reporter` for
a Supreme Court reporter, or null with `court_basis` `none`; `date_read` as
`YYYY` or `YYYY-MM-DD` with `date_evidence` the exact string.

Then, for each record in `records`, answer `case_name_agreement`: `agree`
when the filing's name and the record's name the same case allowing the
abbreviations a citation uses by convention; `variant` when the two are
equivalent captions of one case -- a qui tam relator form against the
government's own name, a party under another role, a caption one side
truncated or malformed in transcription -- which is the same case correctly
cited; `misspelt` when the same party is spelled wrongly in the filing, which
is the same case and a defect; `disagree` when a party on either side is a
different party; `undeterminable` when one side states no name. Then
`same_case`: `yes`, `no`, or `undeterminable`, and a one-sentence `reason`
per record. Two records may be one decision the archive holds twice; say so,
and answer both the same way.

Then `chosen_index`: the index of the record that is the filing's case, or
null. `verdict`: `same_case` when you chose one, `different_case` when every
record is `no`, `undeterminable` otherwise. Identity is the case, not its
fields: a record whose name agrees and whose court or date the filing
misstates is still the filing's case. `reason`: one or two sentences a lawyer
could check.

Extractor's reading of the citation (may be wrong):
{{extracted}}

Records held at the locator:
{{records}}
""".strip()


class CandidateVerdict(BaseModel):
    """The model's answer about one record."""

    model_config = ConfigDict(extra="forbid")

    index: int
    case_name_agreement: Literal["agree", "disagree", "undeterminable", "variant", "misspelt"]
    same_case: Literal["yes", "no", "undeterminable"]
    reason: str


class CandidateJudgment(BaseModel):
    """The model's structured answer over every record."""

    model_config = ConfigDict(extra="forbid")

    case_name_read: str | None
    court_read: str | None
    court_evidence: str | None
    court_basis: Literal["stated", "implied_by_reporter", "none"]
    date_read: str | None
    date_evidence: str | None
    records: list[CandidateVerdict]
    chosen_index: int | None
    verdict: Literal["same_case", "different_case", "undeterminable"]
    reason: str


def choice_supported(judgment: CandidateJudgment, *, count: int) -> str | None:
    """Why the choice does not follow from the per-record answers, or None when it does."""
    indices = [record.index for record in judgment.records]
    if sorted(indices) != list(range(1, count + 1)):
        return f"records must answer for every index 1..{count} exactly once; got {indices}."
    by_index = {record.index: record for record in judgment.records}
    if judgment.chosen_index is not None:
        chosen = by_index[judgment.chosen_index]
        if chosen.case_name_agreement not in ("agree", "variant", "misspelt") or chosen.same_case != "yes":
            return (
                f"chosen_index {judgment.chosen_index} must be a record whose case_name_agreement is agree, "
                "variant or misspelt and whose same_case is yes."
            )
        if judgment.verdict != "same_case":
            return "A chosen record means the verdict is same_case."
        return None
    if judgment.verdict == "same_case":
        return "same_case needs a chosen_index."
    if judgment.verdict == "different_case" and any(record.same_case != "no" for record in judgment.records):
        return "different_case needs every record's same_case to be no."
    if judgment.verdict == "undeterminable" and all(record.same_case == "no" for record in judgment.records):
        return "Every record is no, so the verdict must be different_case."
    return None


async def run_mellea_candidate_judgment(
    record: CitationRecord,
    *,
    document_text: str,
    citations: Sequence[ExtractedCitation],
    candidates: Sequence[CandidateEvaluationNode],
    checks: Sequence[tuple[CaseNameAgreementNode, CourtCheckNode, DateCheckNode]],
    compatible_years: Sequence[tuple[str, ...]] = (),
    session: MelleaSession | None = None,
) -> MelleaCandidateJudgmentNode:
    """Ask the model, over every record at the locator, which is the filing's case."""
    node_id = f"{record.citation_id}:mellea_candidate_judgment"
    depends_on = tuple(node.node_id for group in checks for node in group)
    windows = windows_for(record.source, citations, len(document_text))
    citation = record.citation
    reporter = citation.reporter if isinstance(citation, FullCaseCitation) else None
    grounding = Grounding(
        name_window=document_text[windows.name.start : windows.name.end],
        parenthetical_window=document_text[windows.parenthetical.start : windows.parenthetical.end],
        reporter=reporter,
        record_court_id=None,
        record_date=None,
        implied=implied_courts(reporter),
    )
    extracted = describe_fields(
        case_name=written_case_name(citation.plaintiff, citation.defendant)
        if isinstance(citation, FullCaseCitation)
        else None,
        court=court_label(citation.court) if isinstance(citation, FullCaseCitation) else None,
        date=iso_date(citation.date) if isinstance(citation, FullCaseCitation) else None,
        locator=record.source.matched_text,
    )
    records = "\n\n".join(
        f"record {index}:\n"
        + describe_fields(
            case_name=candidate.case_name,
            court=court_label(court.retrieved_court_id),
            date=candidate.date_filed,
            locator=record.source.matched_text,
        )
        + f"\n- rules: case name {name.outcome.value}, court {court.outcome.value}, date {date.outcome.value}"
        + (f"\n- other years the archive holds for this record: {', '.join(years)}" if years else "")
        for index, (candidate, (name, court, date), years) in enumerate(
            zip(candidates, checks, _padded(compatible_years, len(candidates)), strict=True), start=1
        )
    )
    count = len(candidates)
    model_name: str | None = None
    try:
        config = llm_api_config_from_env(os.environ)
        model_name = config.model
        spec = InstructIvrSpec(
            description=INSTRUCTION,
            grounding_context={
                "context": context_window(record, document_text),
                "name_window": grounding.name_window,
                "parenthetical_window": grounding.parenthetical_window,
            },
            user_variables={"extracted": extracted, "records": records, "count": str(count)},
            output_format=CandidateJudgment,
            requirements=[
                req("Return a valid candidate-judgment object.", validation_fn=_valid_schema),
                req("Every reading must be grounded in its window.", validation_fn=_grounded(grounding)),
                req("The choice must follow from the per-record answers.", validation_fn=_consistent(count)),
            ],
        )
        result = await run_instruct_ivr(
            session or start_mellea_session_from_env(),
            spec,
            strategy=MultiTurnStrategy(loop_budget=MAX_REPAIR_TURNS),
            model_options=config.mellea_call_options(max_tokens=MAX_TOKENS),
        )
        last = last_output(result)
        judgment = _parse(last) if last is not None else None
    except Exception as exc:
        return _failed(node_id, depends_on, model_name, windows, f"{type(exc).__name__}: {exc}")
    if judgment is None:
        return _failed(node_id, depends_on, model_name, windows, "No output")
    failures = readings_grounded(_as_identity(judgment), grounding)
    grounded = tuple(name for name in GROUNDING_CHECKS if name not in failures)
    kept = judgment.model_copy(
        update={
            **({} if "case_name" in grounded else {"case_name_read": None}),
            **(
                {}
                if "court" in grounded
                else {"court_read": None, "court_evidence": None, "court_basis": "none"}
            ),
            **({} if "date" in grounded else {"date_read": None, "date_evidence": None}),
        }
    )
    answers = tuple(
        CandidateAnswer(
            candidate_index=answer.index,
            cluster_id=candidates[answer.index - 1].cluster_id if 1 <= answer.index <= count else None,
            case_name=candidates[answer.index - 1].case_name if 1 <= answer.index <= count else None,
            case_name_agreement=FieldAgreement(answer.case_name_agreement),
            same_case=answer.same_case,
            reason=answer.reason,
        )
        for answer in sorted(judgment.records, key=lambda item: item.index)
    )
    if not result.success:
        problems = [f"{name}: {reason}" for name, reason in failures.items()]
        if (unsupported := choice_supported(judgment, count=count)) is not None:
            problems.append(f"choice: {unsupported}")
        return MelleaCandidateJudgmentNode(
            node_id=node_id,
            status=ValidationNodeStatus.FAILED,
            outcome=IdentityVerdict.FAILED,
            case_name_read=kept.case_name_read,
            court_read=kept.court_read,
            court_evidence=kept.court_evidence,
            court_basis=kept.court_basis if kept.court_read else None,
            date_read=kept.date_read,
            date_evidence=kept.date_evidence,
            candidates=answers,
            chosen_index=None,
            reason=judgment.reason,
            grounded=grounded,
            name_window=windows.name,
            parenthetical_window=windows.parenthetical,
            depends_on=depends_on,
            model=model_name,
            status_message="Mellea candidate judgement exhausted its repair attempts.",
            outcome_message=f"No verdict; kept the grounded readings ({', '.join(grounded) or 'none'}).",
            error="; ".join(problems) or "requirements unmet",
        )
    return MelleaCandidateJudgmentNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=IdentityVerdict(judgment.verdict),
        case_name_read=judgment.case_name_read,
        court_read=judgment.court_read,
        court_evidence=judgment.court_evidence,
        court_basis=judgment.court_basis if judgment.court_read else None,
        date_read=judgment.date_read,
        date_evidence=judgment.date_evidence,
        candidates=answers,
        chosen_index=judgment.chosen_index,
        reason=judgment.reason,
        grounded=grounded,
        name_window=windows.name,
        parenthetical_window=windows.parenthetical,
        depends_on=depends_on,
        model=model_name,
        status_message="Mellea candidate judgement completed.",
        outcome_message=judgment.reason,
    )


def _padded(years: Sequence[tuple[str, ...]], count: int) -> list[tuple[str, ...]]:
    return [*years, *([()] * (count - len(years)))][:count]


def _as_identity(judgment: CandidateJudgment) -> IdentityJudgment:
    """The shared readings in the single-candidate shape, for the grounding checks."""
    return IdentityJudgment(
        case_name_read=judgment.case_name_read,
        case_name_agreement="undeterminable",
        court_read=judgment.court_read,
        court_evidence=judgment.court_evidence,
        court_basis=judgment.court_basis,
        date_read=judgment.date_read,
        date_evidence=judgment.date_evidence,
        verdict="undeterminable",
        reason=judgment.reason,
    )


def _parse(value: object) -> CandidateJudgment:
    try:
        return CandidateJudgment.model_validate_json(value)
    except ValidationError as exc:
        msg = f"Invalid candidate-judgment output: {exc}"
        raise ValueError(msg) from exc


def _valid_schema(ctx: Context) -> ValidationResult:
    try:
        _parse(ctx.last_output().value)
    except ValueError as exc:
        return ValidationResult(result=False, reason=str(exc))
    return ValidationResult(result=True)


def _grounded(grounding: Grounding):
    def validation_fn(ctx: Context) -> ValidationResult:
        try:
            judgment = _parse(ctx.last_output().value)
        except ValueError:
            return ValidationResult(result=True)
        failures = readings_grounded(_as_identity(judgment), grounding)
        reason = "; ".join(f"{name}: {why}" for name, why in failures.items())
        return ValidationResult(result=not failures, reason=reason or None)

    return validation_fn


def _consistent(count: int):
    def validation_fn(ctx: Context) -> ValidationResult:
        try:
            judgment = _parse(ctx.last_output().value)
        except ValueError:
            return ValidationResult(result=True)
        reason = choice_supported(judgment, count=count)
        return ValidationResult(result=reason is None, reason=reason)

    return validation_fn


def _failed(
    node_id: str, depends_on: tuple[str, ...], model: str | None, windows: CitationWindows, error: str
) -> MelleaCandidateJudgmentNode:
    return MelleaCandidateJudgmentNode(
        node_id=node_id,
        status=ValidationNodeStatus.FAILED,
        outcome=IdentityVerdict.FAILED,
        case_name_read=None,
        court_read=None,
        court_evidence=None,
        court_basis=None,
        date_read=None,
        date_evidence=None,
        candidates=(),
        chosen_index=None,
        reason=None,
        grounded=(),
        name_window=windows.name,
        parenthetical_window=windows.parenthetical,
        depends_on=depends_on,
        model=model,
        status_message="Mellea candidate judgement failed during execution.",
        outcome_message="No identity verdict is available.",
        error=error,
    )
