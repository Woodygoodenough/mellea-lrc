"""Full citations identified by a docket number."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from mellea_lrc.model.citations.fields import DocketEntryField, FullDocketLocator
from mellea_lrc.model.citations.full import FullCitation
from mellea_lrc.model.citations.history import Node
from mellea_lrc.model.citations.kind import FullCitationKind
from mellea_lrc.model.span import Span


class FullDocketCitation(FullCitation):
    """A grounded full docket citation occurrence."""

    kind: Literal[FullCitationKind.DOCKET] = FullCitationKind.DOCKET
    locator: tuple[FullDocketLocator, ...]
    docket_entry: tuple[DocketEntryField, ...] = ()

    @property
    def locator_span(self) -> Span:
        return self.locator[-1].span

    @classmethod
    def from_locator(
        cls,
        *,
        citation_id: str,
        substage: str,
        source: str,
        span: Span,
        number_span: Span,
    ) -> Self:
        """Create the citation with only its grounded docket locator."""
        node = Node(id=f"{citation_id}:node:0", substage=substage)
        return cls(
            id=citation_id,
            nodes=(node,),
            locator=(FullDocketLocator.from_source(source, span, number_span, node_id=node.id),),
        )

    def with_docket_entry(self, source: str, span: Span) -> Self:
        """Quote an adjacent entry under the current decision node."""
        return self._with_log(
            docket_entry=(
                *self.docket_entry,
                DocketEntryField.from_source(source, span, node_id=self._decision_node_id()),
            ),
        )

    def with_docket_number(self, source: str, number_span: Span) -> Self:
        """Reread the number within this locator without moving its source site."""
        locator = self.locator[-1]
        reading = FullDocketLocator.from_source(
            source, locator.span, number_span, node_id=self._decision_node_id()
        )
        return self._with_log(locator=(*self.locator, reading))

    @model_validator(mode="after")
    def _validate_locator(self) -> Self:
        if not self.locator or self.locator[0].node_id != self.nodes[0].id:
            raise ValueError("Docket citation needs a source-spanned locator")
        return self
