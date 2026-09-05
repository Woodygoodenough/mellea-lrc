"""One model call over every field the rules could not settle, with evidence.

The rules compare a field the extractor produced with a field the archive
returned, and when they disagree the disagreement has three possible sources:
the filing is wrong, the extractor misread the filing, or the two are the same
thing written differently. Two strings cannot tell those apart. The filing's
own text can, so the model is shown it and asked to read each field again.

The model is a reader that must show its evidence. Each field it reads comes
with the string it read it from, and a deterministic requirement checks that
string against the window the field has to come from: the text before the
locator for the case name, the parenthetical after it for the court and the
date. The check is fuzzy, because the model writes `Suffolk` where the filing
wrote `Suffock` and is not to be punished for reading well; it needs one place
in the window the string could have come from. A court read from a stated
parenthetical must resolve to the identifier the model gave through courts-db,
and a court the model infers from the reporter is allowed only where the
reporter implies exactly one court.

What the model does not decide: whether the court or the date agrees. Those
follow from the reading and the record, at the precision the filing stated.
The model's one judgement is the case name -- the same case abbreviated, a
variant, or a different case -- and the verdict is held to the agreements by a
requirement of its own.

When the requirements are still unmet after the repair budget, the judgement
is recorded as failed, and the fields whose evidence passed on the last
attempt are kept and written onto the record. A good reading of the case name
is not lost because the court could not be grounded.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from mellea.core import ValidationResult
from mellea.stdlib.requirements import req
from mellea.stdlib.sampling import MultiTurnStrategy
from pydantic import BaseModel, ConfigDict, ValidationError

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.extraction.reading.courts import resolve_court
from mellea_lrc.llm import (
    InstructIvrSpec,
    llm_api_config_from_env,
    run_instruct_ivr,
    start_mellea_session_from_env,
)
from mellea_lrc.text import find_all
from mellea_lrc.validation.duplicate_clusters import name_words
from mellea_lrc.validation.identity.case_name import written_case_name
from mellea_lrc.validation.identity.field_checks import iso_date
from mellea_lrc.validation.identity.reporter_courts import describe, implied_courts
from mellea_lrc.validation.identity.windows import windows_for
from mellea_lrc.validation.types import (
    FieldAgreement,
    FieldCheckOutcome,
    FieldDisagreement,
    IdentityVerdict,
    MelleaIdentityJudgmentNode,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea import MelleaSession
    from mellea.core.base import Context

    from mellea_lrc.core.citations import Reporter
    from mellea_lrc.extraction.types import ExtractedCitation
    from mellea_lrc.validation.identity.windows import CitationWindows
    from mellea_lrc.validation.record import CitationRecord
    from mellea_lrc.validation.types import (
        CandidateEvaluationNode,
        CaseNameAgreementNode,
        CourtCheckNode,
        DateCheckNode,
    )

MAX_TOKENS = 1024
MAX_REPAIR_TURNS = 3
CONTEXT_CHARS = 400
"""Characters of the filing shown either side of the citation, for orientation."""

_DATE = re.compile(r"^\d{4}(-\d{2}-\d{2})?$")

INSTRUCTION = """
You are checking one legal citation in a court filing against the record an
archive holds at that citation's volume, reporter and page. Read the filing's
own words, report what it states for each field with the exact string you
read it from, and decide whether the filing and the record name the same case.

`context` shows the citation in its surroundings, marked between [[ and ]].
Do not rely on the extractor's reading of it; the extractor may have taken a
court or a date from a neighbouring citation, or cut a party name short.

Two windows bound what you may read:

- `name_window` is the text before the locator. The case name must come from
  here. Report it in `case_name_read` as the filing wrote it, plaintiff v.
  defendant, or null if the filing states no name there.
- `parenthetical_window` is the text after the locator. The court and the date
  must come from here.

For the court, report `court_read` as a courts-db identifier and say how you
know. If the parenthetical names the court, `court_basis` is `stated` and
`court_evidence` is the exact string that names it, such as `9th Cir.` or
`E.D.N.Y.` or `Fla. Dist. Ct. App.`. If the parenthetical names no court but
the reporter implies one -- `U.S.`, `S. Ct.` and `L. Ed.` are the Supreme
Court, `scotus` -- `court_basis` is `implied_by_reporter` and
`court_evidence` is null. A regional or federal reporter such as `F.3d` or
`So. 3d` implies a family of courts and not one, so with no stated court the
answer is null and `court_basis` is `none`; whether the record's court is one
the reporter holds is then checked without you.

For the date, report `date_read` as `YYYY` when the filing states a year and
`YYYY-MM-DD` when it states a day, and `date_evidence` as the exact string you
read it from, such as `2007` or `Oct. 31, 2024`.

Then the one judgement that is yours: `case_name_agreement`. `agree` when the
filing's name and the record's name the same case, allowing the abbreviations
a citation uses by convention -- `Pac.` for Pacific, `Corp.` for Corporation,
first names and `et al.` dropped, `United States` written `U.S.`, sides
reversed on appeal, a record carrying more words than the filing wrote.
`variant` when it is evidently the same case written defectively: a misspelt
party, a party dropped or garbled, a caption that does not match. `disagree`
when a party on either side is a different party. `undeterminable` when the
filing or the record states no name.

`verdict` is `same_case`, `different_case` or `undeterminable`, and it must
follow from the agreements. The court and date agreements are computed from
your readings and the record, so read them carefully. Identity is the case,
not its fields: a court or date the filing misstates on an agreeing name is a
defect of the filing and the verdict is still `same_case`. `different_case`
needs the case name to disagree. `undeterminable` needs a field nobody can
compare.

`reason`: one or two sentences a lawyer could check against the windows and
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
    court_evidence: str | None
    court_basis: Literal["stated", "implied_by_reporter", "none"]
    date_read: str | None
    date_evidence: str | None
    verdict: Literal["same_case", "different_case", "undeterminable"]
    reason: str


@dataclass(frozen=True, slots=True)
class Grounding:
    """What the model may read from, and what the record holds, for the checks."""

    name_window: str
    parenthetical_window: str
    reporter: Reporter | None
    record_court_id: str | None
    record_date: str | None
    implied: frozenset[str] = frozenset()
    """The courts the reporter can hold; the compatibility check when no court is read."""


# --- the checks ----------------------------------------------------------------


def ground_case_name(judgment: IdentityJudgment, grounding: Grounding) -> str | None:
    """Why the case name is not in the name window, or None when it is or none was read."""
    if judgment.case_name_read is None:
        return None
    if find_all(judgment.case_name_read, grounding.name_window):
        return None
    return (
        f"case_name_read {judgment.case_name_read!r} is not in name_window, even allowing for spelling; "
        "read the name from name_window or answer null."
    )


def ground_court(judgment: IdentityJudgment, grounding: Grounding) -> str | None:
    """Why the court reading is not supported, or None when it is or none was read."""
    if judgment.court_read is None:
        return None
    if judgment.court_read not in _court_ids():
        return f"court_read {judgment.court_read!r} is not a courts-db identifier."
    spelled = grounding.reporter.as_written if grounding.reporter else "the reporter"
    if judgment.court_basis == "stated":
        if not judgment.court_evidence:
            return (
                "court_basis is stated, so court_evidence must be the string in "
                "parenthetical_window that names the court."
            )
        if not find_all(judgment.court_evidence, grounding.parenthetical_window):
            return f"court_evidence {judgment.court_evidence!r} is not in parenthetical_window."
        resolved = resolve_court(judgment.court_evidence)
        if resolved != judgment.court_read:
            named = (
                f"resolves to {resolved!r} ({_court_name(resolved)})"
                if resolved
                else "names no court courts-db knows"
            )
            return f"court_evidence {judgment.court_evidence!r} {named}, not {judgment.court_read!r}."
        return None
    if judgment.court_basis == "implied_by_reporter":
        implied = _implied_court(grounding.reporter)
        if implied is None:
            return (
                f"{spelled} holds more than one court ({describe(grounding.implied) or 'unknown'}), so it "
                "implies none; cite the parenthetical or answer null, and the reporter's courts are "
                "checked for conflict without a reading."
            )
        if implied != judgment.court_read:
            return f"{spelled} implies {implied!r}, not {judgment.court_read!r}."
        return None
    return (
        "court_read is set but court_basis is none; say whether the parenthetical states it "
        "or the reporter implies it."
    )


def ground_date(judgment: IdentityJudgment, grounding: Grounding) -> str | None:
    """Why the date reading is not supported, or None when it is or none was read."""
    if judgment.date_read is None:
        return None
    if not _DATE.match(judgment.date_read):
        return "date_read must be YYYY or YYYY-MM-DD."
    if not judgment.date_evidence:
        return "date_evidence must be the string in parenthetical_window the date was read from."
    if not find_all(judgment.date_evidence, grounding.parenthetical_window):
        return f"date_evidence {judgment.date_evidence!r} is not in parenthetical_window."
    if judgment.date_read[:4] not in judgment.date_evidence:
        return (
            f"date_read {judgment.date_read!r} states a year that date_evidence "
            f"{judgment.date_evidence!r} does not."
        )
    if len(judgment.date_read) > 4 and str(int(judgment.date_read[8:10])) not in judgment.date_evidence:
        return (
            f"date_read {judgment.date_read!r} states a day that date_evidence "
            f"{judgment.date_evidence!r} does not."
        )
    return None


GROUNDING_CHECKS = {"case_name": ground_case_name, "court": ground_court, "date": ground_date}


def readings_grounded(judgment: IdentityJudgment, grounding: Grounding) -> dict[str, str]:
    """Each field whose reading fails its check, with why. Empty when all pass."""
    return {
        name: reason for name, check in GROUNDING_CHECKS.items() if (reason := check(judgment, grounding))
    }


def court_agreement(
    court_read: str | None, record_court_id: str | None, implied: frozenset[str] = frozenset()
) -> FieldAgreement:
    """Computed, not asked: the same identifier or not.

    With no court read, the reporter's courts stand in: a record from one of
    them is compatible, from any other a disagreement. With neither, undeterminable.
    """
    if record_court_id is None:
        return FieldAgreement.UNDETERMINABLE
    if court_read is None:
        if not implied:
            return FieldAgreement.UNDETERMINABLE
        return FieldAgreement.COMPATIBLE if record_court_id in implied else FieldAgreement.DISAGREE
    return FieldAgreement.AGREE if court_read == record_court_id else FieldAgreement.DISAGREE


def date_agreement(date_read: str | None, record_date: str | None) -> FieldAgreement:
    """Computed at the precision the filing stated: the year, or the day."""
    if date_read is None or record_date is None:
        return FieldAgreement.UNDETERMINABLE
    same = date_read == record_date if len(date_read) > 4 else date_read == record_date[:4]
    return FieldAgreement.AGREE if same else FieldAgreement.DISAGREE


def verdict_supported(judgment: IdentityJudgment, grounding: Grounding) -> str | None:
    """Why the verdict does not follow from the agreements, or None when it does."""
    name = judgment.case_name_agreement
    court = court_agreement(judgment.court_read, grounding.record_court_id, grounding.implied).value
    answers = (
        name,
        "agree" if court == "compatible" else court,
        date_agreement(judgment.date_read, grounding.record_date).value,
    )
    if all(answer == "agree" for answer in answers) and judgment.verdict != "same_case":
        return "Every field agrees, so the verdict must be same_case."
    if judgment.verdict == "different_case" and "disagree" not in answers:
        return "A different_case verdict needs at least one field to disagree."
    if judgment.verdict == "different_case" and name in ("agree", "variant"):
        return (
            "The case name agrees, so this is the same case; a disagreeing court or date "
            "is a defect of the filing, and the verdict must be same_case."
        )
    if judgment.verdict == "different_case" and name == "undeterminable":
        return (
            "With no case name to compare, a disagreeing court or date cannot show a different "
            "case; the verdict must be undeterminable."
        )
    if judgment.verdict == "same_case" and name == "disagree":
        return "A disagreeing case name rules out same_case."
    if judgment.verdict == "undeterminable" and "undeterminable" not in answers:
        return "An undeterminable verdict needs at least one undeterminable field."
    return None


# --- the call --------------------------------------------------------------------


async def run_mellea_identity_judgment(
    record: CitationRecord,
    *,
    document_text: str,
    citations: Sequence[ExtractedCitation],
    candidate: CandidateEvaluationNode,
    case_name: CaseNameAgreementNode,
    court: CourtCheckNode,
    date: DateCheckNode,
    session: MelleaSession | None = None,
) -> MelleaIdentityJudgmentNode:
    """Ask the model to read the filing, with evidence, and judge the case name."""
    node_id = f"{candidate.node_id}:mellea_identity_judgment"
    depends_on = (case_name.node_id, court.node_id, date.node_id)
    windows = windows_for(record.source, citations, len(document_text))
    citation = record.citation
    reporter = citation.reporter if isinstance(citation, FullCaseCitation) else None
    grounding = Grounding(
        name_window=document_text[windows.name.start : windows.name.end],
        parenthetical_window=document_text[windows.parenthetical.start : windows.parenthetical.end],
        reporter=reporter,
        record_court_id=court.retrieved_court_id,
        record_date=candidate.date_filed,
        implied=implied_courts(reporter),
    )
    extracted = _describe(
        case_name=written_case_name(citation.plaintiff, citation.defendant)
        if isinstance(citation, FullCaseCitation)
        else None,
        court=_court_label(citation.court) if isinstance(citation, FullCaseCitation) else None,
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
            grounding_context={
                "context": _context(record, document_text),
                "name_window": grounding.name_window,
                "parenthetical_window": grounding.parenthetical_window,
            },
            user_variables={"extracted": extracted, "record": record_text, "rules": rules},
            output_format=IdentityJudgment,
            requirements=[
                req("Return a valid identity-judgment object.", validation_fn=_valid_schema),
                req("Every reading must be grounded in its window.", validation_fn=_grounded(grounding)),
                req("The verdict must follow from the agreements.", validation_fn=_consistent(grounding)),
            ],
        )
        result = await run_instruct_ivr(
            session or start_mellea_session_from_env(),
            spec,
            strategy=MultiTurnStrategy(loop_budget=MAX_REPAIR_TURNS),
            model_options=config.mellea_call_options(max_tokens=MAX_TOKENS),
        )
        last = _last_output(result)
        judgment = _parse(last) if last is not None else None
    except Exception as exc:
        return _failed(
            node_id,
            depends_on,
            model_name,
            windows,
            f"{type(exc).__name__}: {exc}",
            status_message="Mellea identity judgement failed during execution.",
        )
    if judgment is None:
        return _failed(
            node_id, depends_on, model_name, windows, "No output", status_message="Mellea returned no output."
        )
    failures = readings_grounded(judgment, grounding)
    grounded = tuple(name for name in GROUNDING_CHECKS if name not in failures)
    kept = _keep_grounded(judgment, grounded)
    if not result.success:
        # The judgement failed, and the readings whose evidence passed are
        # still worth having: they are written onto the record like any other,
        # and the verdict is not.
        problems = [f"{name}: {reason}" for name, reason in failures.items()]
        if (unsupported := verdict_supported(judgment, grounding)) is not None:
            problems.append(f"verdict: {unsupported}")
        return MelleaIdentityJudgmentNode(
            node_id=node_id,
            status=ValidationNodeStatus.FAILED,
            outcome=IdentityVerdict.FAILED,
            case_name_read=kept.case_name_read,
            case_name_agreement=None,
            court_read=kept.court_read,
            court_evidence=kept.court_evidence,
            court_basis=kept.court_basis if kept.court_read else None,
            court_agreement=None,
            date_read=kept.date_read,
            date_evidence=kept.date_evidence,
            date_agreement=None,
            reason=judgment.reason,
            grounded=grounded,
            name_window=windows.name,
            parenthetical_window=windows.parenthetical,
            depends_on=depends_on,
            model=model_name,
            status_message="Mellea identity judgement exhausted its repair attempts.",
            outcome_message=f"No verdict; kept the grounded readings ({', '.join(grounded) or 'none'}).",
            error="; ".join(problems) or "requirements unmet",
        )
    return MelleaIdentityJudgmentNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=IdentityVerdict(judgment.verdict),
        case_name_read=judgment.case_name_read,
        case_name_agreement=FieldAgreement(judgment.case_name_agreement),
        court_read=judgment.court_read,
        court_evidence=judgment.court_evidence,
        court_basis=judgment.court_basis if judgment.court_read else None,
        court_agreement=court_agreement(judgment.court_read, grounding.record_court_id, grounding.implied),
        date_read=judgment.date_read,
        date_evidence=judgment.date_evidence,
        date_agreement=date_agreement(judgment.date_read, grounding.record_date),
        reason=judgment.reason,
        grounded=grounded,
        name_window=windows.name,
        parenthetical_window=windows.parenthetical,
        depends_on=depends_on,
        model=model_name,
        status_message="Mellea identity judgement completed.",
        outcome_message=judgment.reason,
    )


def apply_readings(record: CitationRecord, judgment: MelleaIdentityJudgmentNode) -> None:
    """Write what the model read from the filing onto the record, where it differs.

    Only grounded readings are on the node, whether the judgement succeeded or
    failed, so everything here rests on evidence in the filing. Only the
    filing's reading changes; the archive's values never reach the citation.
    """
    citation = record.citation
    if not isinstance(citation, FullCaseCitation):
        return
    made_by = judgment.model or "mellea"
    reason = judgment.reason or ""
    if judgment.case_name_read is not None:
        plaintiff, defendant = _split_case_name(judgment.case_name_read)
        if name_words(judgment.case_name_read) != name_words(
            written_case_name(citation.plaintiff, citation.defendant)
        ):
            for name, value in (("plaintiff", plaintiff), ("defendant", defendant)):
                if getattr(record.citation, name) != value:
                    record.correct_field(
                        name, value, made_by=made_by, reason=reason, node_id=judgment.node_id
                    )
    if judgment.court_read is not None and judgment.court_read != citation.court:
        evidence = (
            f"the parenthetical states {judgment.court_evidence!r}"
            if judgment.court_basis == "stated"
            else "the reporter implies it"
        )
        record.correct_field(
            "court",
            judgment.court_read,
            made_by=made_by,
            reason=f"{evidence}; {reason}",
            node_id=judgment.node_id,
        )


def field_disagreements(
    judgment: MelleaIdentityJudgmentNode | None,
    *,
    case_name: CaseNameAgreementNode,
    court: CourtCheckNode,
    date: DateCheckNode,
) -> tuple[FieldDisagreement, ...]:
    """Each field the filing states that disagrees with the record, by the best evidence.

    The judgement's answers stand where it succeeded; the rules' where it did
    not. Each carries the filing's value and the record's.
    """
    unstated = (
        f"none stated; the reporter holds {describe(frozenset(court.implied_court_ids))}"
        if court.extracted_court_id is None and court.implied_court_ids
        else court.extracted_court_id
    )
    values = {
        "case_name": (case_name.written_case_name, case_name.recorded_case_name),
        "court": (unstated, court.retrieved_court_id),
        "date": (date.extracted_date, date.retrieved_date),
    }
    if judgment is not None and judgment.status is ValidationNodeStatus.SUCCEEDED:
        answers = {
            "case_name": judgment.case_name_agreement,
            "court": judgment.court_agreement,
            "date": judgment.date_agreement,
        }
        if judgment.case_name_read is not None:
            values["case_name"] = (judgment.case_name_read, case_name.recorded_case_name)
        if judgment.court_read is not None:
            values["court"] = (judgment.court_read, court.retrieved_court_id)
        if judgment.date_read is not None:
            values["date"] = (judgment.date_read, date.retrieved_date)
    else:
        answers = {
            "case_name": FieldAgreement.DISAGREE if case_name.outcome.value == "mismatch" else None,
            "court": FieldAgreement.DISAGREE if court.outcome is FieldCheckOutcome.MISMATCH else None,
            "date": FieldAgreement.DISAGREE if date.outcome is FieldCheckOutcome.MISMATCH else None,
        }
    return tuple(
        FieldDisagreement(
            field=name, filing_value=values[name][0], record_value=values[name][1], agreement=answer
        )
        for name, answer in answers.items()
        if answer in (FieldAgreement.DISAGREE, FieldAgreement.VARIANT)
    )


# --- helpers ---------------------------------------------------------------------


def _keep_grounded(judgment: IdentityJudgment, grounded: tuple[str, ...]) -> IdentityJudgment:
    """The judgement with every ungrounded reading nulled."""
    fields: dict[str, object] = judgment.model_dump()
    if "case_name" not in grounded:
        fields["case_name_read"] = None
    if "court" not in grounded:
        fields.update(court_read=None, court_evidence=None, court_basis="none")
    if "date" not in grounded:
        fields.update(date_read=None, date_evidence=None)
    return IdentityJudgment(**fields)


def _implied_court(reporter: Reporter | None) -> str | None:
    """The one court a reporter implies, or None when it implies a family or nothing."""
    if reporter is not None and reporter.is_scotus:
        return "scotus"
    return None


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
def _courts() -> dict[str, tuple[str, str | None]]:
    from courts_db import courts

    return {
        str(court["id"]): (court.get("name") or str(court["id"]), court.get("citation_string") or None)
        for court in courts
    }


def _court_ids() -> frozenset[str]:
    return frozenset(_courts())


def _court_name(court_id: str | None) -> str:
    if court_id is None:
        return "none"
    name, _ = _courts().get(court_id, (court_id, None))
    return name


def _court_label(court_id: str | None) -> str | None:
    """`ca4 (Court of Appeals for the Fourth Circuit, cited as 4th Cir.)`, for the prompt."""
    if court_id is None:
        return None
    name, cited = _courts().get(court_id, (None, None))
    if name is None:
        return court_id
    return f"{court_id} ({name}, cited as {cited})" if cited else f"{court_id} ({name})"


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


def _last_output(result: object) -> object | None:
    generations = getattr(result, "sample_generations", None) or []
    if generations:
        return getattr(generations[-1], "value", None)
    chosen = getattr(result, "result", None)
    return getattr(chosen, "value", None) if chosen is not None else None


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
            return ValidationResult(result=True)  # the schema requirement reports this
        failures = readings_grounded(judgment, grounding)
        reason = "; ".join(f"{name}: {why}" for name, why in failures.items())
        return ValidationResult(result=not failures, reason=reason or None)

    return validation_fn


def _consistent(grounding: Grounding):
    def validation_fn(ctx: Context) -> ValidationResult:
        try:
            judgment = _parse(ctx.last_output().value)
        except ValueError:
            return ValidationResult(result=True)
        reason = verdict_supported(judgment, grounding)
        return ValidationResult(result=reason is None, reason=reason)

    return validation_fn


def _failed(
    node_id: str,
    depends_on: tuple[str, ...],
    model: str | None,
    windows: CitationWindows,
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
        court_evidence=None,
        court_basis=None,
        court_agreement=None,
        date_read=None,
        date_evidence=None,
        date_agreement=None,
        reason=None,
        grounded=(),
        name_window=windows.name,
        parenthetical_window=windows.parenthetical,
        depends_on=depends_on,
        model=model,
        status_message=status_message,
        outcome_message="No identity verdict is available.",
        error=error,
    )
