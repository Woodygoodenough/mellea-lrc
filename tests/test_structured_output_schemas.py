"""Tests that every structured-output schema satisfies strict JSON-schema mode.

Mellea sets `"strict": True` on every `response_format` it sends, in both its
OpenAI and non-OpenAI branches, and exposes no way to turn that off. Strict mode
is an API-level contract rather than a model capability: the request is
validated before the model sees it, and it requires every key in `properties` to
appear in `required`. Optionality is expressed as a nullable type.

Pydantic drops a field from `required` as soon as it carries a default, so
`field: str | None = None` produces a schema the API refuses outright with
`invalid_json_schema`. The same schema sent with `strict: false` is accepted and
answered correctly, which is the evidence that the model's schema support is not
what fails here.

Keeping strict is the right trade for this project: it buys guaranteed
conformance to the schema, which is worth more than the convenience of a default.
So an absent value is a required key whose type admits null, and these tests pin
that shape for every model the pipeline hands to Mellea as `output_format`.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from mellea_lrc.experimental.grounded_adjudication.docket_adjudication import _DocketProposal
from mellea_lrc.experimental.grounded_adjudication.locator_adjudication import _Locator, _Locators
from mellea_lrc.validation.case_search.mellea_case_name_query_preparation import _QueryTermsProposal
from mellea_lrc.validation.field_checks.mellea_case_name_check import _SemanticVerdict
from mellea_lrc.validation.field_checks.mellea_case_name_reextraction import _PartyProposal
from mellea_lrc.validation.pinpoint_retrieval.mellea_citing_proposition_extraction import (
    _CitingPropositionProposal,
)
from mellea_lrc.validation.pinpoint_retrieval.mellea_pinpoint_check import _PinpointProposal

OUTPUT_FORMATS: tuple[type[BaseModel], ...] = (
    _CitingPropositionProposal,
    _DocketProposal,
    _Locator,
    _Locators,
    _PartyProposal,
    _PinpointProposal,
    _QueryTermsProposal,
    _SemanticVerdict,
)


def _definitions(schema: dict[str, object]) -> list[dict[str, object]]:
    """Return the root object schema and every nested `$defs` object schema."""
    defs = schema.get("$defs", {})
    assert isinstance(defs, dict)
    nested = [value for value in defs.values() if isinstance(value, dict)]
    return [schema, *nested]


@pytest.mark.parametrize("model", OUTPUT_FORMATS, ids=lambda model: model.__name__)
def test_every_property_is_required(model: type[BaseModel]) -> None:
    """Strict mode requires every declared property to appear in `required`."""
    for definition in _definitions(model.model_json_schema()):
        properties = definition.get("properties")
        if properties is None:
            continue
        assert set(definition.get("required", [])) == set(properties), (
            f"{model.__name__}: every property must be required; express an absent "
            f"value as a nullable type rather than a defaulted field"
        )


@pytest.mark.parametrize("model", OUTPUT_FORMATS, ids=lambda model: model.__name__)
def test_no_property_carries_a_default(model: type[BaseModel]) -> None:
    """A default is what drops a field out of `required`, so none may carry one."""
    for definition in _definitions(model.model_json_schema()):
        properties = definition.get("properties", {})
        assert isinstance(properties, dict)
        for name, spec in properties.items():
            assert isinstance(spec, dict)
            assert "default" not in spec, f"{model.__name__}.{name} carries a default"


@pytest.mark.parametrize("model", OUTPUT_FORMATS, ids=lambda model: model.__name__)
def test_additional_properties_are_forbidden(model: type[BaseModel]) -> None:
    """Strict mode also requires `additionalProperties: false` on every object."""
    for definition in _definitions(model.model_json_schema()):
        if definition.get("properties") is None:
            continue
        assert definition.get("additionalProperties") is False, (
            f"{model.__name__}: set `model_config = ConfigDict(extra='forbid')`"
        )


def test_a_nullable_field_still_accepts_null() -> None:
    """Making the field required must not stop the model reporting an absence."""
    proposal = _PinpointProposal(verdict="inconclusive", reasoning="no support found", evidence_quote=None)

    assert proposal.evidence_quote is None
