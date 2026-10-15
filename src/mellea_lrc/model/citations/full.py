"""Source fields and relationships shared by full citations."""

from __future__ import annotations

from typing import Self

from mellea_lrc.model.citations.citation import Citation
from mellea_lrc.model.citations.fields import CourtField, DateField
from mellea_lrc.model.citations.history import RelationshipUpdate
from mellea_lrc.model.citations.kind import FullCitationKind
from mellea_lrc.model.span import Span


class FullCitation(Citation):
    """A full reporter or docket occurrence with its contextual field history."""

    kind: FullCitationKind
    court: tuple[CourtField, ...] = ()
    date: tuple[DateField, ...] = ()
    colocation_id: tuple[RelationshipUpdate[str | None], ...] = ()

    @property
    def locator_span(self) -> Span:
        """The written identifier span; concrete full types supply it."""
        raise NotImplementedError

    @property
    def site_span(self) -> Span:
        return self.locator_span

    def with_court(self, source: str, span: Span) -> Self:
        """Append a grounded court and normalize its source quote."""
        reading = CourtField.from_source(source, span, node_id=self._decision_node_id())
        return self._with_log(court=(*self.court, reading))

    def with_inferred_court(self, court_id: str) -> Self:
        """Record a court inferred from the reporter, without a court quote."""
        reading = CourtField.inferred(court_id, node_id=self._decision_node_id())
        return self._with_log(court=(*self.court, reading))

    def with_date(self, source: str, span: Span) -> Self:
        """Append a grounded date and normalize its source quote."""
        reading = DateField.from_source(source, span, node_id=self._decision_node_id())
        return self._with_log(
            date=(*self.date, reading),
        )

    def with_colocation(self, group_id: str) -> Self:
        """Append a parsing-group assignment."""
        return self._with_log(
            colocation_id=(
                *self.colocation_id,
                RelationshipUpdate(value=group_id, node_id=self._decision_node_id()),
            ),
        )
