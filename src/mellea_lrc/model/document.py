"""Native documents, citation histories, and recoverable checkpoint boundaries."""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from mellea_lrc.model.citations import FullCitationVariant, latest
from mellea_lrc.model.citations.history import WITHDRAWN_ROOT_ID
from mellea_lrc.model.citations.tags import CitationTag, CitationTagKind
from mellea_lrc.model.colocation import Colocation
from mellea_lrc.model.execution import CheckpointRun, get_stage_definition, stage_for_substage
from mellea_lrc.model.preprocessed_document import PreprocessedDocument
from mellea_lrc.model.span import is_within


class Document(PreprocessedDocument):
    """Source text plus cumulative citation-local history and completed boundaries."""

    citations: tuple[FullCitationVariant, ...] = ()
    runs: tuple[CheckpointRun, ...] = ()

    @property
    def substage_runs(self) -> tuple[str, ...]:
        """Atomic commits in event order; persisted only in ``runs``."""
        return tuple(run.name for run in self.runs if run.kind == "substage")

    @property
    def stage_runs(self) -> tuple[str, ...]:
        """Completed group boundaries in event order."""
        return tuple(run.name for run in self.runs if run.kind == "stage")

    def _ensure_substage_open(self, substage: str) -> None:
        if substage in self.substage_runs:
            raise ValueError(f"Substage already completed: {substage}")
        if stage_for_substage(substage) in self.stage_runs:
            raise ValueError(f"Cannot change a completed stage: {stage_for_substage(substage)}")

    def _pending_substages(self) -> set[str]:
        completed = set(self.substage_runs)
        return {
            node.substage
            for citation in self.citations
            for node in citation.nodes
            if node.substage not in completed
        }

    @classmethod
    def from_preprocessed(cls, source: PreprocessedDocument) -> Self:
        return cls.model_validate(source.model_dump(mode="python"))

    @property
    def full_locators(self) -> tuple[FullCitationVariant, ...]:
        """Every full locator occurrence, including repeated roots."""
        return self.citations

    @property
    def roots(self) -> tuple[FullCitationVariant, ...]:
        return tuple(citation for citation in self.full_locators if latest(citation.root_id) == citation.id)

    @property
    def leaves(self) -> tuple[FullCitationVariant, ...]:
        """Attached occurrences, including repeated full citations."""
        return tuple(
            citation
            for citation in self.citations
            if latest(citation.root_id) not in {None, WITHDRAWN_ROOT_ID, citation.id}
        )

    def add_citation(self, citation: FullCitationVariant) -> Self:
        if any(existing.id == citation.id for existing in self.citations):
            raise ValueError(f"Citation already exists: {citation.id}")
        self._ensure_substage_open(citation.nodes[0].substage)
        creation_span = citation._through_node_count(1).site_span
        tags = tuple(
            CitationTag(
                node_id=citation.nodes[0].id,
                kind=CitationTagKind.TABLE_OF_AUTHORITIES,
                component_index=index,
            )
            for index, component in enumerate(self.index_spans)
            if is_within(creation_span, (component,))
        )
        if tags:
            if citation.tags and citation.tags != tags:
                raise ValueError("Citation component tags differ from its source components")
            if not citation.tags:
                citation = type(citation).model_validate({**citation.model_dump(mode="python"), "tags": tags})
        return self._with_citation(citation)

    def replace_citation(self, citation: FullCitationVariant) -> Self:
        original = next((item for item in self.citations if item.id == citation.id), None)
        if original is None:
            raise KeyError(f"Unknown citation: {citation.id}")
        if type(original) is not type(citation):
            raise ValueError("Citation type cannot change")
        if citation.nodes[: len(original.nodes)] != original.nodes:
            raise ValueError("Citation nodes must be append-only")
        appended_nodes = citation.nodes[len(original.nodes) :]
        for node in appended_nodes:
            self._ensure_substage_open(node.substage)
        new_nodes = {node.id for node in appended_nodes}
        for name in type(citation).model_fields:
            if name in {"id", "kind", "nodes"}:
                continue
            prior = getattr(original, name)
            current = getattr(citation, name)
            if isinstance(prior, tuple) or isinstance(current, tuple):
                # Nullable histories begin as None and become tuples on their
                # first reading. Validate their entries as an append-only log.
                prior_entries = prior if prior is not None else ()
                current_entries = current if current is not None else ()
                if current_entries[: len(prior_entries)] != prior_entries:
                    raise ValueError(f"Citation {name} must be append-only")
                added = current_entries[len(prior_entries) :]
            else:
                if prior is not None and current != prior:
                    raise ValueError(f"Citation {name} must be append-only")
                added = (current,) if prior is None and current is not None else ()
            if any(update.node_id not in new_nodes for update in added):
                raise ValueError("New citation records need a new decision node")
        return self._with_citation(citation)

    def _with_citation(self, citation: FullCitationVariant) -> Self:
        remaining = (item for item in self.citations if item.id != citation.id)
        ordered = tuple(sorted((*remaining, citation), key=lambda item: (item.site_span.start, item.id)))
        return type(self).model_validate({**self.model_dump(mode="python"), "citations": ordered})

    def complete_substage(self, substage: str) -> Self:
        """Commit one atomic run, including runs with no citation changes."""
        self._ensure_substage_open(substage)
        if self._pending_substages() - {substage}:
            raise ValueError("Complete the pending substage before starting another substage run")
        return type(self).model_validate(
            {
                **self.model_dump(mode="python"),
                "runs": (*self.runs, CheckpointRun(kind="substage", name=substage)),
            }
        )

    def complete_stage(self, stage: str) -> Self:
        """Commit a semantic group after its required atomic runs have completed."""
        get_stage_definition(stage)
        if stage in self.stage_runs:
            raise ValueError(f"Stage already completed: {stage}")
        if self._pending_substages():
            raise ValueError("Complete the pending substage before completing a stage")
        return type(self).model_validate(
            {
                **self.model_dump(mode="python"),
                "runs": (*self.runs, CheckpointRun(kind="stage", name=stage)),
            }
        )

    def get_substage(self, substage: str) -> Self:
        """Recover exactly the document returned by a completed substage run."""
        return self._get_checkpoint("substage", substage)

    def get_stage(self, stage: str) -> Self:
        """Recover exactly the document at the semantic group's completion event."""
        get_stage_definition(stage)
        return self._get_checkpoint("stage", stage)

    def _get_checkpoint(self, kind: str, name: str) -> Self:
        try:
            cutoff = next(
                index + 1 for index, run in enumerate(self.runs) if run.kind == kind and run.name == name
            )
        except StopIteration as exc:
            raise KeyError(f"{kind.capitalize()} has not run: {name}") from exc
        runs = self.runs[:cutoff]
        included = {run.name for run in runs if run.kind == "substage"}
        citations: list[FullCitationVariant] = []
        for citation in self.citations:
            count = 0
            for node in citation.nodes:
                if node.substage not in included:
                    break
                count += 1
            if count:
                citations.append(citation._through_node_count(count))
        citations.sort(key=lambda item: (item.site_span.start, item.id))
        return type(self).model_validate(
            {
                **self.model_dump(mode="python"),
                "citations": tuple(citations),
                "runs": runs,
            }
        )

    @model_validator(mode="after")
    def _validate_runs(self) -> Self:
        """Validate durable group markers and prevent reopening a committed group."""
        substages: set[str] = set()
        stages: set[str] = set()
        latest_substage: str | None = None
        for run_index, run in enumerate(self.runs):
            if run.kind == "substage":
                # Workflow.stage.substage identifiers belong to the catalog. Reject
                # obsolete names and typos instead of treating them as ad hoc
                # history and silently replaying a renamed operation.
                if run.name.count(".") >= 2 and stage_for_substage(run.name) is None:
                    raise ValueError(f"Unknown substage: {run.name}")
                if run.name in substages:
                    raise ValueError("Substage runs must be unique")
                if stage_for_substage(run.name) in stages:
                    raise ValueError("Cannot run a substage after its completed stage")
                substages.add(run.name)
                latest_substage = run.name
                continue
            if run.name in stages:
                raise ValueError("Stage runs must be unique")
            try:
                definition = get_stage_definition(run.name)
            except KeyError as exc:
                raise ValueError(str(exc)) from exc
            missing = set(definition.required_substages) - substages
            if missing:
                raise ValueError(f"Stage has unfinished required substages: {', '.join(sorted(missing))}")
            if latest_substage is None or stage_for_substage(latest_substage) != run.name:
                raise ValueError("Stage must complete immediately after its own final substage")
            members = {member.name: index for index, member in enumerate(definition.substages)}
            positions = [
                members[previous.name]
                for previous in self.runs[:run_index]
                if previous.kind == "substage" and previous.name in members
            ]
            if positions != sorted(positions):
                raise ValueError("Stage substages must complete in catalog order")
            stages.add(run.name)
        if any(stage_for_substage(substage) in stages for substage in self._pending_substages()):
            raise ValueError("Completed stage cannot contain pending substage changes")
        return self

    @model_validator(mode="after")
    def _validate_component_tags(self) -> Self:
        for citation in self.citations:
            creation_span = citation._through_node_count(1).site_span
            expected = tuple(
                CitationTag(
                    node_id=citation.nodes[0].id,
                    kind=CitationTagKind.TABLE_OF_AUTHORITIES,
                    component_index=index,
                )
                for index, component in enumerate(self.index_spans)
                if is_within(creation_span, (component,))
            )
            if citation.tags != expected:
                raise ValueError("Citation component tags must match its creation span and source components")
        return self

    @property
    def colocations(self) -> tuple[Colocation, ...]:
        """Derive parsing groups from citation assignment histories."""
        groups: dict[str, list[str]] = {}
        for citation in self.citations:
            group_id = latest(citation.colocation_id)
            if group_id is not None:
                groups.setdefault(group_id, []).append(citation.id)
        return tuple(Colocation(id=key, citation_ids=tuple(ids)) for key, ids in groups.items())

    @model_validator(mode="after")
    def _validate_citations(self) -> Self:
        by_id = {citation.id: citation for citation in self.citations}
        if len(by_id) != len(self.citations):
            raise ValueError("Duplicate citation ID")
        if tuple(sorted(self.citations, key=lambda item: (item.site_span.start, item.id))) != self.citations:
            raise ValueError("Citations must be ordered by site span and ID")
        completed = {name: index for index, name in enumerate(self.substage_runs)}
        pending = len(completed)
        for citation in self.citations:
            previous = -1
            for node in citation.nodes:
                position = completed.get(node.substage, pending)
                if position < previous:
                    raise ValueError("Citation nodes cannot move backward through substage runs")
                previous = position
            citation.validate_source(self.text)
            for update in citation.root_id:
                if update.value in {None, WITHDRAWN_ROOT_ID}:
                    continue
                root = by_id.get(update.value)
                if root is None:
                    raise ValueError("Citation points to an unknown root")
                nodes = {node.id: node.substage for node in citation.nodes}
                if completed.get(root.nodes[0].substage, pending) > completed.get(
                    nodes[update.node_id], pending
                ):
                    raise ValueError("Citation root cannot be created after its assignment")
        if len(self._pending_substages()) > 1:
            raise ValueError("Only one substage can have uncommitted citation nodes")
        # Pending changes may span several citations. Enforce a valid graph at
        # every committed boundary, including historical boundaries after load.
        for cutoff in range(len(completed)):
            roots: dict[str, str | None] = {}
            groups: dict[str, int] = {}
            for citation in self.citations:
                positions = {node.id: completed.get(node.substage, pending) for node in citation.nodes}
                roots[citation.id] = next(
                    (item.value for item in reversed(citation.root_id) if positions[item.node_id] <= cutoff),
                    None,
                )
                group = next(
                    (
                        item.value
                        for item in reversed(citation.colocation_id)
                        if positions[item.node_id] <= cutoff
                    ),
                    None,
                )
                if group is not None:
                    groups[group] = groups.get(group, 0) + 1
            if any(
                root not in {None, WITHDRAWN_ROOT_ID} and roots.get(root) != root for root in roots.values()
            ):
                raise ValueError("Citation attachment must point to a self-root at every completed substage")
            if any(size < 2 for size in groups.values()):
                raise ValueError("A colocation group needs at least two citations")
        return self
