"""Project-owned Mellea instruct/validate/repair helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mellea.backends import ModelOption
from mellea.stdlib import functional as mfuncs
from mellea.stdlib.context import ChatContext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mellea import MelleaSession
    from mellea.core.requirement import Requirement
    from mellea.core.sampling import SamplingResult
    from mellea.stdlib.sampling import MultiTurnStrategy
    from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class InstructIvrSpec:
    """Complete project-level specification for one Mellea IVR instruction."""

    description: str
    prefix: str | None = None
    """A long text several calls share, sent as the system message ahead of the instruction.

    Measured against the configured model through OpenRouter, the provider served a repeated
    opening from its prompt cache only as a system message: the same opinion sent inside the
    instruction's message, or as a user message before it, was billed in full on every call, and
    as the system message it was billed at the cached rate from the second call on. It is also sent as written, where the instruction's texts pass through
    template substitution."""
    grounding_context: Mapping[str, str] = field(default_factory=dict)
    user_variables: Mapping[str, str] = field(default_factory=dict)
    requirements: Sequence[Requirement] = field(default_factory=tuple)
    output_format: type[BaseModel] | None = None


async def run_instruct_ivr(
    session: MelleaSession,
    spec: InstructIvrSpec,
    *,
    strategy: MultiTurnStrategy,
    model_options: dict[str, object],
) -> SamplingResult[str]:
    """Run one IVR instruction with a fresh Mellea chat context."""
    return await asyncio.to_thread(
        mfuncs.instruct,
        spec.description,
        context=ChatContext(),
        backend=session.backend,
        grounding_context=dict(spec.grounding_context),
        user_variables=dict(spec.user_variables),
        requirements=list(spec.requirements),
        strategy=strategy,
        return_sampling_results=True,
        format=spec.output_format,
        model_options=model_options
        if spec.prefix is None
        else {**model_options, ModelOption.SYSTEM_PROMPT: spec.prefix},
    )
