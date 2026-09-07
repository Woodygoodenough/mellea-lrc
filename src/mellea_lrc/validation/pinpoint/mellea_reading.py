"""One reading of the citing passage against the cited page, every quote of it grounded.

The model is shown two texts: the filing around the target citation, with the
target marked, and the cited reporter page with the tail of the page before
and the head of the page after. It answers with quotations from each: the
words in the filing that state what the target is cited for, and the passage
on the page that carries the same content, if one does. Both are located
programmatically before anything is believed, and a reading whose quotes
cannot be found is rejected and asked for again.

The reading is factual. It says whether a passage on the page states the
same content as the filing's words, is on the same subject and says something
different, or that nothing on the page concerns the subject -- and whose
words the passage is. It does not say whether the page *supports* the filing;
that is an evaluation of legal sufficiency, and no field of the output asks
for one.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mellea.core import ValidationResult
from mellea.stdlib.requirements import req
from mellea.stdlib.sampling import MultiTurnStrategy
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mellea_lrc.core.spans import Span
from mellea_lrc.llm import (
    InstructIvrSpec,
    llm_api_config_from_env,
    run_instruct_ivr,
    start_mellea_session_from_env,
)
from mellea_lrc.text import fuzzy
from mellea_lrc.validation.types import (
    MelleaPinpointReadingNode,
    PinpointRelation,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea import MelleaSession
    from mellea.core.base import Context

    from mellea_lrc.validation.pinpoint.citing import CitingWindow
    from mellea_lrc.validation.pinpoint.pages import RetrievedPage

_log = logging.getLogger(__name__)

MAX_TOKENS = 8000
MAX_REPAIR_TURNS = 3
MIN_QUOTE_SCORE = 0.88

INSTRUCTION = """
You are comparing two texts. The first is a passage from a court filing in
which one citation is marked between « and ». The second is the page of the
cited case that the citation points at, shown with the end of the page before
it and the start of the page after it. Your task is to say, as a matter of
fact, what the filing attributes to the marked citation and what the cited
page carries on that subject. You are not asked whether the page supports the
filing, and you must not answer that question.

Read the filing first. Find the words that state what the marked citation is
cited for. Prefer, in this order: an explanatory parenthetical attached to the
marked citation; the clause or sentence the citation closes; the sentence
immediately before a bare citation. Copy those words exactly as `attribution`.
If the marked citation is one member of a string cite (several citations joined
by semicolons under one sentence) and has no parenthetical of its own, the
sentence is shared: copy it and set `attribution_scope` to "shared". If the
citation makes no page-level claim of its own -- it follows "see generally",
it sits inside a "citing" or "quoting" parenthetical of another citation, it is
in a table of authorities, or nothing near it states a proposition -- set
`attribution_scope` to "none" and copy whatever words are nearest as
`attribution` anyway.

Then read the page. If a passage on the page states the same content as the
attribution -- the same rule, fact or holding, in the court's words or the
filing's -- copy that passage exactly as `passage`, say where it is
(`passage_location`: "page", or "before" or "after" for the neighbouring
text), and set `relation` to "same_content". If the page discusses the same
subject but what it says differs from the attribution, copy the nearest
passage and set `relation` to "related_subject". If nothing on the page or
beside it concerns the subject at all, set `passage` to null and `relation` to
"none", and describe in `page_subjects` what the page does discuss, in one
sentence.

Say whose words the passage is (`voice`): the court's opinion; a dissent or
concurrence; a party's argument the court is reciting; a lower court's
reasoning the court is reviewing; another case the court is quoting; a
syllabus or headnote. Read the signal word ahead of the citation and copy it
as `signal` ("see", "see also", "cf.", "but see", "accord", "e.g.", "see
generally", "compare", or "none").

Rules for quoting: every `attribution` and `passage` is located by a program
in the text you were shown, so copy exactly -- do not paraphrase, shorten,
normalise, or bridge two places with an ellipsis. Keep each quotation
contiguous and under eighty words; quote the sentence that carries the
content, not the paragraph. If the passage runs across the page turn, quote
the part on the side you name.

Say what you found in `reason`, in two or three plain sentences that a reader
can check against the two texts. Do not evaluate whether the citation is
correct, adequate, or misleading.

The case cited: {{record}}
The pin cite: {{pin_cite}}
Quotations the filing writes near the citation, and where a program found them: {{quotes}}
""".strip()


class PinpointReading(BaseModel):
    """The model's answer, every quotation of which is located before it is believed."""

    model_config = ConfigDict(extra="forbid")

    attribution: str = Field(
        description="Words copied from the filing that state what the marked citation is cited for."
    )
    attribution_scope: Literal["own", "shared", "none"]
    signal: Literal[
        "none", "see", "see also", "cf.", "but see", "accord", "e.g.", "see generally", "compare", "contra"
    ]
    passage: str | None = Field(
        description="Words copied from the page (or its neighbours) on the same subject; null when none."
    )
    passage_location: Literal["page", "before", "after"] | None
    relation: Literal["same_content", "related_subject", "none"]
    voice: (
        Literal[
            "court",
            "dissent_or_concurrence",
            "party_argument",
            "lower_court",
            "quoted_authority",
            "syllabus_or_headnote",
        ]
        | None
    )
    page_subjects: str = Field(description="One sentence: what the cited page discusses.")
    reason: str


@dataclass(frozen=True, slots=True)
class Located:
    """Where the model's two quotations were found, or why each was not."""

    attribution: fuzzy.Match | None
    passage: fuzzy.Match | None
    problems: tuple[str, ...]
    passage_location: str | None = None
    """Where the passage was actually found, which may differ from where the model said."""


def locate(reading: PinpointReading, window: CitingWindow, page: RetrievedPage) -> Located:
    """Find the model's quotations in the texts it was shown."""
    problems: list[str] = []
    attribution = _best(reading.attribution, window.text)
    if attribution is None:
        problems.append("attribution: the words are not in the filing window as written")
    passage = None
    if reading.relation == "none":
        if reading.passage:
            problems.append("passage: a relation of none must come with no passage")
    else:
        if not reading.passage or reading.passage_location is None:
            problems.append("passage: a relation other than none must quote a passage and say where it is")
        else:
            source = {"page": page.text, "before": page.before, "after": page.after}[reading.passage_location]
            passage = _best(reading.passage, source)
            if passage is None:
                problems.append(
                    f"passage: the words are not in the {reading.passage_location} text as written"
                )
    return Located(attribution, passage, tuple(problems))


def _best(needle: str, haystack: str) -> fuzzy.Match | None:
    needle = needle.strip().strip("\"'\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}")
    if not needle or not haystack:
        return None
    matches = fuzzy.find_all(needle, haystack, min_score=MIN_QUOTE_SCORE)
    return matches[0] if matches else None


def _parse(value: object) -> PinpointReading:
    try:
        return PinpointReading.model_validate_json(value)
    except ValidationError as exc:
        msg = f"Invalid pinpoint reading: {exc}"
        raise ValueError(msg) from exc


def _last_output(result: object) -> object | None:
    generations = getattr(result, "sample_generations", None) or []
    if generations:
        return getattr(generations[-1], "value", None)
    chosen = getattr(result, "result", None)
    return getattr(chosen, "value", None) if chosen is not None else None


def _schema_requirement(ctx: Context) -> ValidationResult:
    try:
        _parse(ctx.last_output().value)
    except ValueError as exc:
        _log.info("pinpoint reading rejected: %s", str(exc)[:600])
        return ValidationResult(result=False, reason=str(exc))
    return ValidationResult(result=True)


def _located_requirement(window: CitingWindow, page: RetrievedPage):
    def validation_fn(ctx: Context) -> ValidationResult:
        try:
            reading = _parse(ctx.last_output().value)
        except ValueError:
            return ValidationResult(result=True)  # the schema requirement reports it
        located = locate(reading, window, page)
        if located.problems:
            return ValidationResult(
                result=False, reason="; ".join(located.problems) + ". Copy the words exactly as they appear."
            )
        return ValidationResult(result=True)

    return validation_fn


def describe_quotes(quotes) -> str:
    """The deterministic quote findings, for the model to know what was already searched."""
    if not quotes:
        return "none"
    lines = []
    for quote in quotes:
        where = {
            "on_page": f"found on the cited page (p. {quote.label})",
            "adjacent": f"found on the neighbouring page (p. {quote.label})",
            "elsewhere": f"found in the opinion on p. {quote.label}, not the cited page",
            "found_unpaged": "found in an opinion of the case whose text carries no page markers",
            "absent": "not found in any opinion of the case",
        }[quote.outcome.value]
        lines.append(f'- "{quote.text}" -- {where}')
    return "\n".join(lines)


async def run_mellea_pinpoint_reading(
    *,
    node_id: str,
    depends_on: tuple[str, ...],
    window: CitingWindow,
    page: RetrievedPage,
    record: str,
    pin_cite: str,
    quotes,
    session: MelleaSession | None = None,
) -> MelleaPinpointReadingNode:
    """Ask for one reading, ground it, and keep whatever quotations were located even if it failed."""
    model_name: str | None = None
    page_text = page.text
    if page.before:
        page_text = f"[end of the page before]\n{page.before}\n[*{page.labels[0]}]\n{page.text}"
    if page.after:
        page_text = f"{page_text}\n[next page]\n{page.after}"
    try:
        config = llm_api_config_from_env(os.environ)
        model_name = config.model
        spec = InstructIvrSpec(
            description=INSTRUCTION,
            grounding_context={"filing": window.marked, "cited_page": page_text},
            user_variables={"record": record, "pin_cite": pin_cite, "quotes": describe_quotes(quotes)},
            output_format=PinpointReading,
            requirements=[
                req("Return a valid pinpoint reading.", validation_fn=_schema_requirement),
                req(
                    "Every quotation must be located in the text it was copied from.",
                    validation_fn=_located_requirement(window, page),
                ),
            ],
        )
        result = await run_instruct_ivr(
            session or start_mellea_session_from_env(),
            spec,
            strategy=MultiTurnStrategy(loop_budget=MAX_REPAIR_TURNS),
            model_options=config.mellea_call_options(max_tokens=MAX_TOKENS),
        )
        last = _last_output(result)
        try:
            reading = _parse(last) if last is not None else None
        except ValueError as exc:
            tail = str(last)[-160:] if last is not None else ""
            return _failed(
                node_id,
                depends_on,
                model_name,
                window,
                f"{exc} | output {len(str(last or ''))} chars, ends: {tail!r}",
            )
    except Exception as exc:
        return _failed(node_id, depends_on, model_name, window, f"{type(exc).__name__}: {exc}")
    if reading is None:
        return _failed(node_id, depends_on, model_name, window, "No output")
    located = locate(reading, window, page)
    grounded = tuple(
        name
        for name, match in (("attribution", located.attribution), ("passage", located.passage))
        if match is not None
    )
    attribution_span = (
        Span(window.span.start + located.attribution.start, window.span.start + located.attribution.end)
        if located.attribution
        else None
    )
    passage_span = Span(located.passage.start, located.passage.end) if located.passage else None
    succeeded = result.success and not located.problems
    return MelleaPinpointReadingNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED if succeeded else ValidationNodeStatus.FAILED,
        outcome=PinpointRelation(reading.relation) if succeeded else None,
        model=model_name,
        window=window.span,
        attribution=located.attribution.text if located.attribution else reading.attribution,
        attribution_span=attribution_span,
        attribution_scope=reading.attribution_scope,
        signal=reading.signal,
        passage=located.passage.text if located.passage else reading.passage,
        passage_location=located.passage_location or reading.passage_location,
        passage_span=passage_span,
        voice=reading.voice,
        page_subjects=reading.page_subjects,
        reason=reading.reason,
        grounded=grounded,
        depends_on=depends_on,
        status_message="Pinpoint reading completed."
        if succeeded
        else "Pinpoint reading did not pass its guards.",
        outcome_message=reading.reason
        if succeeded
        else "; ".join(located.problems) or "The model's answer was rejected.",
        error=None if succeeded else ("; ".join(located.problems) or "rejected"),
    )


def _failed(
    node_id: str, depends_on: tuple[str, ...], model: str | None, window: CitingWindow, error: str
) -> MelleaPinpointReadingNode:
    return MelleaPinpointReadingNode(
        node_id=node_id,
        status=ValidationNodeStatus.FAILED,
        outcome=None,
        model=model,
        window=window.span,
        attribution=None,
        attribution_span=None,
        attribution_scope=None,
        signal=None,
        passage=None,
        passage_location=None,
        passage_span=None,
        voice=None,
        page_subjects=None,
        reason=None,
        grounded=(),
        depends_on=depends_on,
        status_message="Pinpoint reading failed during execution.",
        outcome_message="No reading was obtained.",
        error=error,
    )


__all__ = ["PinpointReading", "locate", "run_mellea_pinpoint_reading"]
