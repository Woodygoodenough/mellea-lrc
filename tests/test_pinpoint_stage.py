"""The pinpoint stage end to end, with a lookup table for the archive and a fake model."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from mellea_lrc.core.citations import FullCaseCitation, IdCitation, Reporter
from mellea_lrc.core.spans import Span
from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.courtlistener.citation_lookup_models import CourtListenerCitationLookup
from mellea_lrc.courtlistener.docket_models import CourtListenerDocket
from mellea_lrc.courtlistener.opinion_models import (
    CourtListenerClusterDetail,
    CourtListenerOpinion,
    CourtListenerOpinionCluster,
    CourtListenerOpinionClusterCitation,
)
from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument, ExtractionMetadata
from mellea_lrc.preprocessing import preprocess_plain_text_from_string
from mellea_lrc.serialization import deserialize_identified_document, serialize_identified_document
from mellea_lrc.validation.identity import identify_document
from mellea_lrc.validation.pinpoint import pinpoint_document, summarize
from mellea_lrc.validation.types import (
    PageRetrievalNode,
    PinpointOutcome,
    PinpointResolutionNode,
    PinpointScope,
    PinpointScopeNode,
    QuoteCheckNode,
    QuoteFindingOutcome,
)

US = Reporter(
    as_written="U.S.",
    short_name="U.S.",
    name="United States Supreme Court Reports",
    cite_type="federal",
    is_scotus=True,
)

PAGE_HTML = (
    "<p>Opening of the opinion, page five forty-four.</p>"
    '<span class="star-pagination" citation-index="1" label="545">*545</span>'
    "<p>Page five forty-five discusses the facts of the antitrust claim.</p>"
    '<span class="star-pagination" citation-index="1" label="570">*570</span>'
    "<p>To survive a motion to dismiss, a complaint must contain enough facts to state a claim to relief "
    "that is plausible on its face. Labels and conclusions will not do.</p>"
    '<span class="star-pagination" citation-index="1" label="571">*571</span>'
    "<p>Page five seventy-one turns to the parallel conduct allegations. " + "Filler sentence. " * 60 + "</p>"
    '<span class="star-pagination" citation-index="1" label="572">*572</span>'
    "<p>Page five seventy-two holds the distinctive closing words of the majority opinion.</p>"
)

TWOMBLY = CourtListenerOpinionCluster(
    cluster_id="c1",
    case_name="Bell Atlantic Corp. v. Twombly",
    date_filed="2007-05-21",
    docket_id="d1",
    citations=(CourtListenerOpinionClusterCitation("550", "U.S.", "544"),),
    sub_opinion_ids=("o1",),
)


class Client:
    def __init__(self, html: str = PAGE_HTML) -> None:
        self.html = html
        self.opinions_fetched: list[str] = []

    def lookup_citation(self, volume: str, reporter: str, page: str) -> CourtListenerCitationLookup:
        if (volume, reporter, page) == ("550", "U.S.", "544"):
            return CourtListenerCitationLookup(citation="550 U.S. 544", status=200, clusters=(TWOMBLY,))
        return CourtListenerCitationLookup(citation=f"{volume} {reporter} {page}", status=404, clusters=())

    def get_docket(self, docket_id: str) -> CourtListenerDocket:
        return CourtListenerDocket(docket_id=docket_id, court_id="scotus", docket_number="05-1126")

    def get_cluster(self, cluster_id: str) -> CourtListenerClusterDetail:
        return CourtListenerClusterDetail(cluster_id=cluster_id, other_dates="", sub_opinion_ids=("o1",))

    def get_opinion(self, opinion_id: str) -> CourtListenerOpinion:
        self.opinions_fetched.append(opinion_id)
        if opinion_id != "o1":
            raise CourtListenerError("no such opinion", failure_type="test")
        return CourtListenerOpinion(
            opinion_id="o1", cluster_id="c1", opinion_type="010combined", html_with_citations=self.html
        )

    def search(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("search is not part of these stages")


TEXT = (
    'A complaint must contain "enough facts to state a claim to relief that is plausible on its face." '
    "Bell Atlantic Corp. v. Twombly, 550 U.S. 544, 570 (2007). The Court added that mere labels will not do. "
    "Id. at 570. A quite different point about class certification is made there too. Id. at 545."
)


def _document(text: str = TEXT) -> ExtractedDocument:
    full = "Bell Atlantic Corp. v. Twombly, 550 U.S. 544, 570 (2007)"
    start = text.index(full)
    root = ExtractedCitation(
        citation_id="root",
        full_span=Span(start, start + len(full)),
        locator_span=Span(text.index("550 U.S. 544"), text.index("550 U.S. 544") + 12),
        matched_text="550 U.S. 544",
        citation=FullCaseCitation(
            plaintiff="Bell Atlantic Corp.",
            defendant="Twombly",
            volume="550",
            reporter=US,
            page="544",
            pin_cite="570",
            court="scotus",
            date=None,
        ),
        authority_id="root",
        pin_cite_span=Span(text.index(", 570") + 2, text.index(", 570") + 5),
    )
    ids = []
    for n, (needle, pin) in enumerate((("Id. at 570.", "570"), ("Id. at 545.", "545"))):
        s = text.index(needle)
        ids.append(
            ExtractedCitation(
                citation_id=f"id{n}",
                full_span=Span(s, s + len(needle) - 1),
                locator_span=Span(s, s + 3),
                matched_text="Id.",
                citation=IdCitation(pin_cite=pin),
                resolves_to="root",
                authority_id="root",
            )
        )
    preprocessed = preprocess_plain_text_from_string(text)
    return ExtractedDocument(
        source_metadata=preprocessed.source_metadata,
        text=text,
        preprocessing_metadata=preprocessed.preprocessing_metadata,
        citations=(root, *ids),
        extraction_metadata=ExtractionMetadata(),
    )


def _fake_reading(monkeypatch: pytest.MonkeyPatch, answers: list[dict[str, object]]) -> list[object]:
    monkeypatch.setenv("MELLEA_LRC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_KEY", "test-key")
    calls: list[object] = []

    async def fake_instruct(_session: object, spec: object, **_kwargs: object) -> SimpleNamespace:
        calls.append(spec)
        answer = answers[min(len(calls) - 1, len(answers) - 1)]
        return SimpleNamespace(success=True, result=SimpleNamespace(value=json.dumps(answer)))

    monkeypatch.setattr("mellea_lrc.validation.pinpoint.mellea_reading.run_instruct_ivr", fake_instruct)
    return calls


def _run(
    monkeypatch: pytest.MonkeyPatch,
    answers: list[dict[str, object]],
    text: str = TEXT,
    client: Client | None = None,
):
    client = client or Client()
    identified = asyncio.run(identify_document(_document(text), client=client))
    _fake_reading(monkeypatch, answers)
    asyncio.run(pinpoint_document(identified, client=client))
    return identified, client


def _resolutions(identified) -> dict[str, PinpointResolutionNode]:
    return {
        record.citation_id: next(n for n in record.trace.nodes if isinstance(n, PinpointResolutionNode))
        for record in identified.records
    }


SAME = {
    "attribution": "enough facts to state a claim to relief that is plausible on its face.",
    "attribution_scope": "own",
    "signal": "none",
    "passage": "a complaint must contain enough facts to state a claim to relief that is plausible on its face",
    "passage_location": "page",
    "relation": "same_content",
    "voice": "court",
    "page_subjects": "The page states the plausibility standard.",
    "reason": "Both say the same thing.",
}
NONE = {
    "attribution": "A quite different point about class certification is made there too.",
    "attribution_scope": "own",
    "signal": "none",
    "passage": None,
    "passage_location": None,
    "relation": "none",
    "voice": None,
    "page_subjects": "The page discusses the facts of the antitrust claim.",
    "reason": "Nothing on the page concerns class certification.",
}


def test_the_whole_tree_is_checked_and_a_quotation_on_the_page_is_found_by_the_program(monkeypatch) -> None:
    identified, client = _run(monkeypatch, [SAME, SAME, NONE])
    resolutions = _resolutions(identified)
    assert resolutions["root"].outcome is PinpointOutcome.QUOTE_ON_PAGE
    assert resolutions["root"].false_pin_cite is False
    assert resolutions["root"].passage_label == "570"
    assert resolutions["root"].passage_span is not None
    # The Id. citations inherit the authority through the tree and are checked on their own pages.
    assert resolutions["id0"].outcome is PinpointOutcome.PASSAGE_ON_PAGE
    assert resolutions["id1"].outcome is PinpointOutcome.PASSAGE_ABSENT
    assert resolutions["id1"].false_pin_cite is True
    # One opinion, fetched once for the three citations.
    assert client.opinions_fetched.count("o1") == 1
    quotes = next(n for n in identified.record("root").trace.nodes if isinstance(n, QuoteCheckNode))
    assert quotes.quotes[0].outcome is QuoteFindingOutcome.ON_PAGE
    assert quotes.quotes[0].label == "570"


def test_a_quotation_found_nowhere_in_the_case_is_a_false_pin_cite_before_any_reading(monkeypatch) -> None:
    text = TEXT.replace(
        "enough facts to state a claim to relief that is plausible on its face.",
        "words that appear nowhere in the opinion of the court at all.",
    )
    identified, _ = _run(monkeypatch, [SAME, SAME, NONE], text)
    root = _resolutions(identified)["root"]
    assert root.outcome is PinpointOutcome.QUOTE_ABSENT
    assert root.false_pin_cite is True


def test_a_quotation_on_another_page_is_a_wrong_page(monkeypatch) -> None:
    text = TEXT.replace(
        "enough facts to state a claim to relief that is plausible on its face.",
        "the distinctive closing words of the majority opinion.",
    )
    identified, _ = _run(monkeypatch, [SAME, SAME, NONE], text)
    root = _resolutions(identified)["root"]
    assert root.outcome is PinpointOutcome.QUOTE_ELSEWHERE
    assert "page 572" in (root.outcome_message or "")


def test_a_citation_with_no_pin_cite_is_not_retrieved() -> None:
    text = "Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007) says something."
    full = "Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007)"
    root = ExtractedCitation(
        citation_id="root",
        full_span=Span(0, len(full)),
        locator_span=Span(text.index("550 U.S. 544"), text.index("550 U.S. 544") + 12),
        matched_text="550 U.S. 544",
        citation=FullCaseCitation(
            plaintiff="Bell Atlantic Corp.",
            defendant="Twombly",
            volume="550",
            reporter=US,
            page="544",
            court="scotus",
        ),
        authority_id="root",
    )
    preprocessed = preprocess_plain_text_from_string(text)
    document = ExtractedDocument(
        source_metadata=preprocessed.source_metadata,
        text=text,
        preprocessing_metadata=preprocessed.preprocessing_metadata,
        citations=(root,),
        extraction_metadata=ExtractionMetadata(),
    )
    client = Client()
    identified = asyncio.run(identify_document(document, client=client))
    asyncio.run(pinpoint_document(identified, client=client))
    scope = next(n for n in identified.records[0].trace.nodes if isinstance(n, PinpointScopeNode))
    assert scope.outcome is PinpointScope.NO_PIN_CITE
    assert _resolutions(identified)["root"].outcome is PinpointOutcome.NOT_RETRIEVED


def test_the_artifact_round_trips_with_the_pinpoint_nodes(monkeypatch) -> None:
    identified, _ = _run(monkeypatch, [SAME, SAME, NONE])
    payload = json.loads(json.dumps(serialize_identified_document(identified)))
    recovered = deserialize_identified_document(payload)
    assert [type(n).__name__ for n in recovered.records[0].trace.nodes] == [
        type(n).__name__ for n in identified.records[0].trace.nodes
    ]
    page = next(n for n in recovered.records[0].trace.nodes if isinstance(n, PageRetrievalNode))
    assert page.labels == ("570",)
    assert summarize(recovered).outcomes["quote_on_page"] == 1


def test_a_misquotation_of_content_the_page_carries_is_altered_not_false(monkeypatch) -> None:
    text = TEXT.replace(
        "enough facts to state a claim to relief that is plausible on its face.",
        "enough facts to state a plausible claim to relief on its face, whatever that means.",
    )
    same = {
        **SAME,
        "attribution": "enough facts to state a plausible claim to relief on its face, whatever that means.",
    }
    identified, _ = _run(monkeypatch, [same, SAME, NONE], text)
    root = _resolutions(identified)["root"]
    assert root.outcome is PinpointOutcome.QUOTE_ALTERED
    assert root.false_pin_cite is False
    assert root.misquoted is True
    assert root.passage is not None


def test_an_opinion_without_page_markers_stands_in_for_the_page(monkeypatch) -> None:
    unpaged = PAGE_HTML.replace(
        '<span class="star-pagination" citation-index="1" label="545">*545</span>', ""
    )
    unpaged = unpaged.replace('<span class="star-pagination" citation-index="1" label="570">*570</span>', "")
    unpaged = unpaged.replace('<span class="star-pagination" citation-index="1" label="571">*571</span>', "")
    unpaged = unpaged.replace('<span class="star-pagination" citation-index="1" label="572">*572</span>', "")
    identified, _ = _run(monkeypatch, [SAME, SAME, NONE], client=Client(unpaged))
    resolutions = _resolutions(identified)
    assert resolutions["root"].outcome is PinpointOutcome.QUOTE_IN_OPINION
    assert resolutions["root"].text_scope == "opinion"
    assert resolutions["id1"].outcome is PinpointOutcome.PASSAGE_ABSENT_FROM_OPINION
    assert resolutions["id1"].false_pin_cite is True
