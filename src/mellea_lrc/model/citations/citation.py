"""Citation-local nodes and append-only field histories."""

from __future__ import annotations

import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mellea_lrc.model.citations.fields.base import CitationField
from mellea_lrc.model.citations.fields.case_name import CaseName, CaseNameField, CaseNameKind
from mellea_lrc.model.citations.fields.pin_cite import PinCiteField, PinCiteValue
from mellea_lrc.model.citations.history import WITHDRAWN_ROOT_ID, Node, RelationshipUpdate
from mellea_lrc.model.citations.tags import CitationTag, CitationTagKind
from mellea_lrc.model.span import Span


class Citation(BaseModel):
    """Field readings belong to the citation and reference the node that made them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    kind: str
    nodes: tuple[Node, ...]
    tags: tuple[CitationTag, ...] = ()
    case_name: tuple[CaseNameField, ...] = ()
    root_id: tuple[RelationshipUpdate[str | None], ...] = ()
    routes: tuple[RelationshipUpdate[str | None], ...] = ()
    pin_cite: Annotated[tuple[PinCiteField, ...], Field(min_length=1)] | None = None

    def is_toa(self) -> bool:
        """Whether this occurrence was created inside a table-of-authorities component."""
        return any(tag.kind is CitationTagKind.TABLE_OF_AUTHORITIES for tag in self.tags)

    def get_case_name(self) -> CaseName:
        """Read the current written name, including the explicit unstated outcome."""
        if not self.case_name:
            return CaseName(kind=CaseNameKind.NOT_STATED)
        return self.case_name[-1].get_normalized()

    def with_case_name(self, source: str, span: Span, *, normalized: CaseName | None = None) -> Self:
        """Append a grounded name, using a model reading when supplied."""
        reading = (
            CaseNameField.from_source(source, span, node_id=self._decision_node_id())
            if normalized is None
            else CaseNameField.from_model(source, span, normalized, node_id=self._decision_node_id())
        )
        return self._with_log(case_name=(*self.case_name, reading))

    @property
    def next_substage(self) -> str | None:
        """The currently queued substage, independent of any identity opinion."""
        return self.routes[-1].value if self.routes else None

    @property
    def site_span(self) -> Span:
        """The source site used to order citation occurrences."""
        raise NotImplementedError

    def record(self, substage: str) -> Self:
        """Record one decision; named field methods may share its node."""
        node = Node(id=f"{self.id}:node:{len(self.nodes)}", substage=substage)
        return type(self).model_validate({**self.model_dump(mode="python"), "nodes": (*self.nodes, node)})

    def _decision_node_id(self) -> str:
        if len(self.nodes) == 1:
            raise ValueError("Record a decision node before changing citation fields")
        return self.nodes[-1].id

    def _with_log(self, **logs: object) -> Self:
        """Validate the immutable citation after a named field method changes it."""
        return type(self).model_validate({**self.model_dump(mode="python"), **logs})

    def _through_node_count(self, count: int) -> Self:
        """Recover the citation and field readings through one node boundary."""
        if not 1 <= count <= len(self.nodes):
            raise ValueError("Citation cutoff must retain its creation node")
        nodes = self.nodes[:count]
        node_ids = {node.id for node in nodes}
        data = {**self.model_dump(mode="python"), "nodes": nodes}
        for name in type(self).model_fields:
            if name not in {"id", "kind", "nodes"}:
                value = getattr(self, name)
                if isinstance(value, tuple):
                    retained = tuple(update for update in value if update.node_id in node_ids)
                    data[name] = retained if retained else type(self).model_fields[name].get_default()
                else:
                    data[name] = value if value is not None and value.node_id in node_ids else None
        return type(self).model_validate(data)

    def with_root(self, root_id: str | None) -> Self:
        """Append a root attachment without erasing earlier assignments."""
        return self._with_log(
            root_id=(*self.root_id, RelationshipUpdate(value=root_id, node_id=self._decision_node_id())),
        )

    def with_pin_cite(self, source: str, span: Span) -> Self:
        """Append a grounded pinpoint using the shared typed normalization."""
        reading = PinCiteField.from_source(source, span, node_id=self._decision_node_id())
        return self._with_log(pin_cite=(*(self.pin_cite or ()), reading))

    def get_pin_cite(self) -> PinCiteValue | None:
        """Read the latest targets, or None when no pinpoint has been read.

        A quoted reading that cannot normalize raises through its field getter,
        rather than being confused with absence.
        """
        return None if self.pin_cite is None else self.pin_cite[-1].get_normalized()

    def with_route(self, next_substage: str | None) -> Self:
        """Append a routing decision; None clears an earlier route."""
        if (
            next_substage is not None
            and re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,2}", next_substage) is None
        ):
            raise ValueError("A route must name a lowercase substage ID")
        return self._with_log(
            routes=(*self.routes, RelationshipUpdate(value=next_substage, node_id=self._decision_node_id()))
        )

    def withdraw(self) -> Self:
        """Attach to the dummy head when no real root applies, retaining history."""
        return self.with_root(WITHDRAWN_ROOT_ID)

    def validate_source(self, source: str) -> None:
        """Check all stored quotes against the source, including after JSON loading."""
        for name in type(self).model_fields:
            if name in {"id", "kind", "nodes"}:
                continue
            value = getattr(self, name)
            entries = value if isinstance(value, tuple) else (value,) if value is not None else ()
            for entry in entries:
                if isinstance(entry, CitationField):
                    entry.validate_source(source)

    @model_validator(mode="after")
    def _validate_history(self) -> Self:
        if not self.nodes:
            raise ValueError("Citation must have a creation node")
        positions = {node.id: index for index, node in enumerate(self.nodes)}
        if len(positions) != len(self.nodes):
            raise ValueError("Duplicate citation node")
        for name in type(self).model_fields:
            if name in {"id", "kind", "nodes"}:
                continue
            previous = -1
            value = getattr(self, name)
            updates = value if isinstance(value, tuple) else (value,) if value is not None else ()
            for update in updates:
                position = positions.get(update.node_id)
                if position is None:
                    raise ValueError(f"{name} refers to a missing node")
                # A node may read several fields, but only once per field.
                if position < previous or (
                    position == previous and isinstance(update, (CitationField, RelationshipUpdate))
                ):
                    raise ValueError(f"{name} updates are out of order")
                previous = position
        if any(
            route.value is not None
            and re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,2}", route.value) is None
            for route in self.routes
        ):
            raise ValueError("A route must name a lowercase substage ID")
        return self
