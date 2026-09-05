"""One model call over every field the rules could not settle.

The rules compare a field the extractor produced with a field the archive
returned, and when they disagree the disagreement has three possible sources:
the filing is wrong, the extractor misread the filing, or the two are the same
thing written differently. Two strings cannot tell those apart. The filing's
context can, so the model is shown it, along with the record, and asked three
things per field: what the filing actually says, whether that agrees with the
record, and -- once for the whole citation -- whether the two name one case.

What comes back is held to itself. A deterministic requirement checks that the
verdict is one the field answers support, and that every value the model read
from the filing is actually in the filing; a response that fails either is
repaired in a further turn rather than recorded. What the model reads that the
extractor did not is written onto the record as a correction, attributed to the
model, so a corrected court is distinguishable from a parsed one.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
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
from mellea_lrc.validation.duplicate_clusters import name_words
from mellea_lrc.validation.identity.case_name import written_case_name
from mellea_lrc.validation.identity.field_checks import iso_date
from mellea_lrc.validation.types import (
    FieldAgreement,
    FieldCheckOutcome,
    IdentityVerdict,
    MelleaIdentityJudgmentNode,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea import MelleaSession
    from mellea.core.base import Context

    from mellea_lrc.validation.record import CitationRecord
    from mellea_lrc.validation.types import (
        CandidateEvaluationNode,
        CaseNameAgreementNode,
        CourtCheckNode,
        DateCheckNode,
    )

MAX_TOKENS = 768
MAX_REPAIR_TURNS = 3
CONTEXT_CHARS = 400
"""Characters of the filing shown either side of the citation."""

_DATE = re.compile(r"^\d{4}(-\d{2}-\d{2})?$")

INSTRUCTION = """
You are checking one legal citation in a court filing against the record an
archive holds at that citation's volume, reporter and page. Decide, field by
field, what the filing itself states and whether that agrees with the record,
then decide whether the filing and the record name the same case.

Read the filing's own words in `context`. The citation under review is marked
between [[ and ]]. Do not rely on the extractor's reading of it; the extractor
may have taken a court or a date from a neighbouring citation, or cut a party
name short. What you report in each `*_read` field is what the filing states,
copied from the context, or null when the filing states nothing for it.

Domain knowledge to apply:
- A case name in a filing is abbreviated by convention: `Pac.` for Pacific,
  `Corp.` for Corporation, first names and `et al.` dropped, `United States`
  written `U.S.`, sides sometimes reversed on appeal. None of that makes it a
  different case. A different party on either side does.
- The court is stated in the parenthetical before the year, such as
  `(9th Cir. 2003)` or `(E.D.N.Y. Oct. 31, 2024)`. When the parenthetical
  names no court, the reporter implies one: `U.S.` and `S. Ct.` are the Supreme
  Court (id `scotus`); `F.`, `F.2d`, `F.3d`, `F.4th` and `F. App'x` are the
  courts of appeals (ids `ca1` .. `ca11`, `cadc`, `cafc`); `F. Supp.` and
  `F.R.D.` are district courts (ids like `nysd`, `cand`); a state's official
  reporter is that state's highest court unless the parenthetical says
  otherwise. Report the court as a courts-db identifier, such as `ca9`, `nyed`,
  `cal`, `calctapp`, or null when you cannot name one.
- The date in the parenthetical is the decision date. A filing usually states
  the year alone; report `YYYY`, or `YYYY-MM-DD` when the filing states a day.
  The record's date is the date the decision was filed. A one-year difference
  can be a rehearing or an amended opinion of the same case; a difference of
  several years is not.
- The record is what the archive holds at exactly this volume and page. If the
  filing describes a different case from the one on that page, the verdict is
  `different_case`, however plausible the filing's case name sounds on its own.
- Identity is the case, not its fields. When the filing's case name agrees with
  the record's, the filing is citing that case, and a court or date that
  disagrees is a defect in the filing rather than evidence of a different case:
  report the field as `disagree` and the verdict as `same_case`.
  `different_case` is for a page whose record names a different case.

Agreement values: `agree` when the filing's field and the record's field name
the same thing; `disagree` when they name different things; `undeterminable`
when the filing or the record does not state the field. The case name has one
more: `variant`, for a name that is evidently the same case written
defectively -- a misspelt party (`Suffock` for `Suffolk`), a party dropped or
garbled, a caption that does not match the record's. `variant` is not
`disagree`: the case is the same and the defect is reported. A record that
carries more words than the filing wrote, or the filing's conventional
abbreviations spelt out, is `agree`, not `variant`.

Verdict values: `same_case`, `different_case`, `undeterminable`. The verdict
must follow from the field answers: if every field agrees, the verdict is
`same_case`; `different_case` needs the case name to disagree or be
undeterminable, and some field to disagree; a disagreeing case name rules out
`same_case`; `undeterminable` needs at least one field to be undeterminable.

`reason`: one or two sentences a lawyer could check against the context and
the record.

Extractor's reading of the citation (may be wrong):
{{extracted}}

Record held at the locator:
{{record}}

Rule-based comparison so far:
{{rules}}
""".strip()


class IdentityJudgment(BaseModel):
    """The model's structured answer."""

    model_config = ConfigDict(extra="forbid")

    case_name_read: str | None
    case_name_agreement: Literal["agree", "disagree", "undeterminable", "variant"]
    court_read: str | None
    court_agreement: Literal["agree", "disagree", "undeterminable"]
    date_read: str | None
    date_agreement: Literal["agree", "disagree", "undeterminable"]
    verdict: Literal["same_case", "different_case", "undeterminable"]
    reason: str


def verdict_supported(judgment: IdentityJudgment) -> str | None:
    """Why the verdict does not follow from the field answers, or None when it does."""
    answers = (judgment.case_name_agreement, judgment.court_agreement, judgment.date_agreement)
    if all(answer == "agree" for answer in answers) and judgment.verdict != "same_case":
        return "Every field agrees, so the verdict must be same_case."
    if judgment.verdict == "different_case" and "disagree" not in answers:
        return "A different_case verdict needs at least one field to disagree."
    if judgment.verdict == "different_case" and judgment.case_name_agreement in ("agree", "variant"):
        return (
            "The case name agrees, so this is the same case; a disagreeing court or date "
            "is a defect of the filing, and the verdict must be same_case."
        )
    if judgment.verdict == "same_case" and judgment.case_name_agreement == "disagree":
        return "A disagreeing case name rules out same_case."
    if judgment.verdict == "undeterminable" and "undeterminable" not in answers:
        return "An undeterminable verdict needs at least one undeterminable field."
    return None


def readings_grounded(judgment: IdentityJudgment, *, context: str) -> str | None:
    """Why a value the model read is not in the filing, or None when all are."""
    if judgment.case_name_read is not None:
        missing = [word for word in name_words(judgment.case_name_read) if word not in name_words(context)]
        if missing:
            return f"case_name_read contains {', '.join(sorted(missing))}, which the context does not."
    if judgment.court_read is not None and judgment.court_read not in _court_ids():
        return f"court_read {judgment.court_read!r} is not a courts-db identifier."
    if judgment.date_read is not None and not _DATE.match(judgment.date_read):
        return "date_read must be YYYY or YYYY-MM-DD."
    if judgment.date_read is not None and judgment.date_read[:4] not in context:
        return f"date_read {judgment.date_read!r} names a year the context does not."
    return None


async def run_mellea_identity_judgment(
    record: CitationRecord,
    *,
    document_text: str,
    candidate: CandidateEvaluationNode,
    case_name: CaseNameAgreementNode,
    court: CourtCheckNode,
    date: DateCheckNode,
    session: MelleaSession | None = None,
) -> MelleaIdentityJudgmentNode:
    """Ask the model to read the filing and judge the fields the rules could not."""
    node_id = f"{candidate.node_id}:mellea_identity_judgment"
    depends_on = (case_name.node_id, court.node_id, date.node_id)
    context = _context(record, document_text)
    citation = record.citation
    extracted = _describe(
        case_name=written_case_name(citation.plaintiff, citation.defendant)
        if isinstance(citation, FullCaseCitation)
        else None,
        court=citation.court if isinstance(citation, FullCaseCitation) else None,
        date=iso_date(citation.date) if isinstance(citation, FullCaseCitation) else None,
        locator=record.source.matched_text,
    )
    record_text = _describe(
        case_name=candidate.case_name,
        court=_court_label(court.retrieved_court_id),
        date=candidate.date_filed,
        locator=record.source.matched_text,
    )
    rules = "\n".join(
        (
            f"- case name: {case_name.outcome.value} ({case_name.outcome_message})",
            f"- court: {court.outcome.value} ({court.outcome_message})",
            f"- date: {date.outcome.value} ({date.outcome_message})",
        )
    )
    model_name: str | None = None
    try:
        config = llm_api_config_from_env(os.environ)
        model_name = config.model
        spec = InstructIvrSpec(
            description=INSTRUCTION,
            grounding_context={"context": context},
            user_variables={"extracted": extracted, "record": record_text, "rules": rules},
            output_format=IdentityJudgment,
            requirements=[
                req("Return a valid identity-judgment object.", validation_fn=_valid_schema),
                req("The verdict must follow from the field answers.", validation_fn=_consistent),
                req(
                    "Every value read from the filing must appear in the context.",
                    validation_fn=_grounded(context),
                ),
            ],
        )
        result = await run_instruct_ivr(
            session or start_mellea_session_from_env(),
            spec,
            strategy=MultiTurnStrategy(loop_budget=MAX_REPAIR_TURNS),
            model_options=config.mellea_call_options(max_tokens=MAX_TOKENS),
        )
        if not result.success:
            return _failed(
                node_id,
                depends_on,
                model_name,
                "Identity judgement exhausted its repair budget",
                status_message="Mellea identity judgement exhausted its repair attempts.",
            )
        judgment = _parse(result.result.value)
    except Exception as exc:
        return _failed(
            node_id,
            depends_on,
            model_name,
            f"{type(exc).__name__}: {exc}",
            status_message="Mellea identity judgement failed during execution.",
        )
    return MelleaIdentityJudgmentNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=IdentityVerdict(judgment.verdict),
        case_name_read=judgment.case_name_read,
        case_name_agreement=FieldAgreement(judgment.case_name_agreement),
        court_read=judgment.court_read,
        court_agreement=FieldAgreement(judgment.court_agreement),
        date_read=judgment.date_read,
        date_agreement=FieldAgreement(judgment.date_agreement),
        reason=judgment.reason,
        depends_on=depends_on,
        model=model_name,
        status_message="Mellea identity judgement completed.",
        outcome_message=judgment.reason,
    )


def apply_readings(record: CitationRecord, judgment: MelleaIdentityJudgmentNode) -> None:
    """Write what the model read from the filing onto the record, where it differs.

    Only the filing's reading changes. The archive's values never reach the
    citation, so a filing that states the wrong year keeps it, and the
    disagreement stays visible as a defect.
    """
    citation = record.citation
    if not isinstance(citation, FullCaseCitation) or judgment.status is not ValidationNodeStatus.SUCCEEDED:
        return
    made_by = judgment.model or "mellea"
    if judgment.case_name_read is not None:
        plaintiff, defendant = _split_case_name(judgment.case_name_read)
        if name_words(judgment.case_name_read) != name_words(
            written_case_name(citation.plaintiff, citation.defendant)
        ):
            for name, value in (("plaintiff", plaintiff), ("defendant", defendant)):
                if getattr(record.citation, name) != value:
                    record.correct_field(
                        name, value, made_by=made_by, reason=judgment.reason or "", node_id=judgment.node_id
                    )
    if judgment.court_read is not None and judgment.court_read != citation.court:
        record.correct_field(
            "court",
            judgment.court_read,
            made_by=made_by,
            reason=judgment.reason or "",
            node_id=judgment.node_id,
        )


def _context(record: CitationRecord, document_text: str) -> str:
    span = record.source.full_span
    start = max(0, span.start - CONTEXT_CHARS)
    end = min(len(document_text), span.end + CONTEXT_CHARS)
    return (
        document_text[start : span.start]
        + "[["
        + document_text[span.start : span.end]
        + "]]"
        + document_text[span.end : end]
    )


def _describe(*, case_name: str | None, court: str | None, date: str | None, locator: str) -> str:
    return "\n".join(
        (
            f"- locator: {locator}",
            f"- case name: {case_name or '(none)'}",
            f"- court: {court or '(none)'}",
            f"- date: {date or '(none)'}",
        )
    )


@lru_cache(maxsize=1)
def _court_ids() -> frozenset[str]:
    from courts_db import courts

    return frozenset(court["id"] for court in courts)


@lru_cache(maxsize=1)
def _court_names() -> dict[str, str]:
    from courts_db import courts

    return {court["id"]: court.get("name") or court["id"] for court in courts}


def _court_label(court_id: str | None) -> str | None:
    if court_id is None:
        return None
    name = _court_names().get(court_id)
    return f"{court_id} ({name})" if name and name != court_id else court_id


def _split_case_name(value: str) -> tuple[str | None, str | None]:
    parts = re.split(r"\s+vs?\.?\s+", value, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip() or None, parts[1].strip() or None
    return value.strip() or None, None


def _parse(value: object) -> IdentityJudgment:
    try:
        return IdentityJudgment.model_validate_json(value)
    except ValidationError as exc:
        msg = f"Invalid identity-judgment output: {exc}"
        raise ValueError(msg) from exc


def _valid_schema(ctx: Context) -> ValidationResult:
    try:
        _parse(ctx.last_output().value)
    except ValueError as exc:
        return ValidationResult(result=False, reason=str(exc))
    return ValidationResult(result=True)


def _consistent(ctx: Context) -> ValidationResult:
    try:
        judgment = _parse(ctx.last_output().value)
    except ValueError:
        return ValidationResult(result=True)  # the schema requirement reports this
    reason = verdict_supported(judgment)
    return ValidationResult(result=reason is None, reason=reason)


def _grounded(context: str):
    def validation_fn(ctx: Context) -> ValidationResult:
        try:
            judgment = _parse(ctx.last_output().value)
        except ValueError:
            return ValidationResult(result=True)
        reason = readings_grounded(judgment, context=context)
        return ValidationResult(result=reason is None, reason=reason)

    return validation_fn


def _failed(
    node_id: str,
    depends_on: tuple[str, ...],
    model: str | None,
    error: str,
    *,
    status_message: str,
) -> MelleaIdentityJudgmentNode:
    return MelleaIdentityJudgmentNode(
        node_id=node_id,
        status=ValidationNodeStatus.FAILED,
        outcome=IdentityVerdict.FAILED,
        case_name_read=None,
        case_name_agreement=None,
        court_read=None,
        court_agreement=None,
        date_read=None,
        date_agreement=None,
        reason=None,
        depends_on=depends_on,
        model=model,
        status_message=status_message,
        outcome_message="No identity verdict is available.",
        error=error,
    )


def field_disagreements(
    judgment: MelleaIdentityJudgmentNode | None,
    *,
    case_name: CaseNameAgreementNode,
    court: CourtCheckNode,
    date: DateCheckNode,
) -> tuple[str, ...]:
    """Which fields the filing states disagree with the record, by the best evidence.

    The model's answer stands where it ran; the rule's where it did not.
    """
    if judgment is not None and judgment.status is ValidationNodeStatus.SUCCEEDED:
        answers = {
            "case_name": judgment.case_name_agreement,
            "court": judgment.court_agreement,
            "date": judgment.date_agreement,
        }
        return tuple(
            name
            for name, answer in answers.items()
            if answer in (FieldAgreement.DISAGREE, FieldAgreement.VARIANT)
        )
    disagreements = []
    if not case_name.outcome.agrees and case_name.outcome.value == "mismatch":
        disagreements.append("case_name")
    if court.outcome is FieldCheckOutcome.MISMATCH:
        disagreements.append("court")
    if date.outcome is FieldCheckOutcome.MISMATCH:
        disagreements.append("date")
    return tuple(disagreements)
