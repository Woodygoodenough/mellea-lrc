"""The immutable workflow hierarchy and durable checkpoint events."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class SubstageDefinition:
    """An atomic execution, commit, and recovery boundary."""

    name: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class StageDefinition:
    """An ordered group of substages with a meaningful task boundary."""

    name: str
    substages: tuple[SubstageDefinition, ...]
    optional: bool = False

    @property
    def required_substages(self) -> tuple[str, ...]:
        return tuple(substage.name for substage in self.substages if not substage.optional)


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """An ordered collection of semantic stages."""

    name: str
    stages: tuple[StageDefinition, ...]

    @property
    def required_stages(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages if not stage.optional)


def _stage(
    workflow: str,
    name: str,
    substages: tuple[str, ...],
    *,
    optional_substages: tuple[str, ...] = (),
    optional: bool = False,
) -> StageDefinition:
    path = f"{workflow}.{name}"
    return StageDefinition(
        name=path,
        substages=tuple(
            SubstageDefinition(f"{path}.{substage}", substage in optional_substages) for substage in substages
        ),
        optional=optional,
    )


WORKFLOW_CATALOG: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        "grow_roots",
        (
            _stage(
                "grow_roots",
                "discover_root_locators",
                ("find_full_reporter_locators", "find_docket_locators", "hunt_docket_locators"),
                optional_substages=("hunt_docket_locators",),
            ),
            _stage(
                "grow_roots",
                "read_root_fields",
                (
                    "resolve_docket_entries",
                    "resolve_colocations",
                    "resolve_case_names",
                    "resolve_courts",
                    "resolve_dates",
                    "resolve_pin_cites",
                ),
            ),
            _stage(
                "grow_roots",
                "form_root_groups",
                ("form_roots", "reassign_docket_roots_llm"),
                optional_substages=("reassign_docket_roots_llm",),
            ),
        ),
    ),
)

STAGE_CATALOG = MappingProxyType(
    {stage.name: stage for workflow in WORKFLOW_CATALOG for stage in workflow.stages}
)
SUBSTAGE_CATALOG = MappingProxyType(
    {substage.name: substage for stage in STAGE_CATALOG.values() for substage in stage.substages}
)
_SUBSTAGE_STAGES = MappingProxyType(
    {substage.name: stage.name for stage in STAGE_CATALOG.values() for substage in stage.substages}
)


def get_workflow(name: str) -> WorkflowDefinition:
    """Look up one workflow without importing execution implementations."""
    for workflow in WORKFLOW_CATALOG:
        if workflow.name == name:
            return workflow
    raise KeyError(f"Unknown workflow: {name}")


def get_stage_definition(name: str) -> StageDefinition:
    try:
        return STAGE_CATALOG[name]
    except KeyError as exc:
        raise KeyError(f"Unknown stage: {name}") from exc


def get_substage_definition(name: str) -> SubstageDefinition:
    try:
        return SUBSTAGE_CATALOG[name]
    except KeyError as exc:
        raise KeyError(f"Unknown substage: {name}") from exc


def stage_for_substage(name: str) -> str | None:
    """Return catalog membership; ad hoc development substages have no group."""
    return _SUBSTAGE_STAGES.get(name)


class CheckpointRun(BaseModel):
    """One append-only event; a stage marker has no citation decision node."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    kind: Literal["substage", "stage"]
    name: str = Field(min_length=1)
