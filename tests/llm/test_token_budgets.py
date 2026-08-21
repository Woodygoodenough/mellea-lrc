"""Live check that each node's token budget survives the model's reasoning.

A reasoning model spends the completion budget on reasoning before it emits
anything. When the budget runs out first the response carries no content at all
-- `finish_reason` is `length` and the verdict is simply lost. That is a silent
failure, not a worse answer, and it is invisible offline because the schema and
the prompt are both fine.

How much reasoning a call uses varies run to run. The same one-field verdict
prompt used 43, 74, 120, 171 and 392 reasoning tokens on five consecutive calls,
so a budget that fits the median still drops answers. These evaluations sample
each node's real budget several times and fail if any call comes back empty.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest
from dotenv import load_dotenv

from mellea_lrc.validation.case_search.mellea_case_name_query_preparation import (
    MAX_TOKENS as QUERY_PREPARATION_MAX_TOKENS,
)
from mellea_lrc.validation.field_checks.mellea_case_name_check import (
    MAX_TOKENS as CASE_NAME_MAX_TOKENS,
)
from mellea_lrc.validation.field_checks.mellea_case_name_reextraction import (
    REEXTRACTION_MAX_TOKENS,
)
from mellea_lrc.validation.pinpoint_retrieval.mellea_citing_proposition_extraction import (
    MAX_TOKENS as PROPOSITION_MAX_TOKENS,
)
from mellea_lrc.validation.pinpoint_retrieval.mellea_pinpoint_check import (
    MAX_TOKENS as PINPOINT_MAX_TOKENS,
)

load_dotenv(".env")

SAMPLES = 4
VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"verdict": {"type": "string", "enum": ["match", "mismatch"]}},
    "required": ["verdict"],
}


def _completion(prompt: str, max_tokens: int) -> tuple[str | None, str | None, int]:
    """Return the content, finish reason, and reasoning tokens for one call."""
    body = {
        "model": os.environ["MELLEA_LRC_LLM_MODEL"],
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "V", "schema": VERDICT_SCHEMA, "strict": True},
        },
    }
    request = urllib.request.Request(  # noqa: S310 - configured API base
        os.environ["MELLEA_LRC_LLM_API_BASE"].rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['MELLEA_LRC_LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        payload = json.load(response)
    choice = payload["choices"][0]
    details = (payload.get("usage") or {}).get("completion_tokens_details") or {}
    return choice["message"]["content"], choice.get("finish_reason"), details.get("reasoning_tokens", 0)


@pytest.mark.llm_evaluation
@pytest.mark.parametrize(
    ("label", "budget"),
    [
        ("case name check", CASE_NAME_MAX_TOKENS),
        ("query preparation", QUERY_PREPARATION_MAX_TOKENS),
        ("case name reextraction", REEXTRACTION_MAX_TOKENS),
        ("citing proposition", PROPOSITION_MAX_TOKENS),
        ("pinpoint check", PINPOINT_MAX_TOKENS),
    ],
)
def test_a_nodes_budget_leaves_room_for_the_models_reasoning(label: str, budget: int) -> None:
    """Every sampled call must return content, not run out of budget reasoning."""
    prompt = (
        "Are 'Rubin v. Smith' and 'In re Rubin' the same case? Consider the "
        "bankruptcy caption convention carefully, then answer in the schema."
    )

    for attempt in range(SAMPLES):
        content, finish, reasoning = _completion(prompt, budget)
        assert content, (
            f"{label} (budget {budget}) returned no content on attempt {attempt + 1}: "
            f"finish_reason={finish}, reasoning_tokens={reasoning}. "
            f"The budget is spent on reasoning before any answer is emitted."
        )
        assert finish == "stop"


@pytest.mark.llm_evaluation
def test_an_undersized_budget_loses_the_answer_silently() -> None:
    """Documents the failure this guards against, so it is not mistaken for a refusal.

    The call succeeds, costs tokens, and returns nothing. Nothing in the schema
    or the prompt is wrong, which is why the node recorded a failure with no
    useful reason before the budgets were raised.
    """
    content, finish, _ = _completion("Are these the same case? Answer in the schema.", 8)

    assert content is None
    assert finish == "length"
