"""Tests for the identity stage: roots, the rule guard, the judgement, and the merge."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from mellea_lrc.core.citations import (
    CitationDate,
    DocketCitation,
    FullCaseCitation,
    FullLawCitation,
    IdCitation,
    Reporter,
)
from mellea_lrc.core.spans import Span
from mellea_lrc.courtlistener import (
    CourtListenerCitationLookup,
    CourtListenerClusterDetail,
    CourtListenerDocket,
    CourtListenerError,
    CourtListenerOpinion,
    CourtListenerOpinionCluster,
)
from mellea_lrc.extraction import ExtractedCitation, ExtractedDocument, ExtractionMetadata
from mellea_lrc.preprocessing import preprocess_plain_text_from_string
from mellea_lrc.serialization import deserialize_identified_document, serialize_identified_document
from mellea_lrc.validation.identity import identify_document
from mellea_lrc.validation.identity.mellea_candidates import (
    CandidateJudgment,
    CandidateVerdict,
    choice_supported,
)
from mellea_lrc.validation.identity.mellea_judgment import (
    Grounding,
    IdentityJudgment,
    court_agreement,
    date_agreement,
    readings_grounded,
    verdict_supported,
)
from mellea_lrc.validation.record import CitationRecord, Correction
from mellea_lrc.validation.types import (
    AuthorityMergeNode,
    AuthorityMergeOutcome,
    CandidateSelectionNode,
    CandidateSelectionOutcome,
    DateReconciliationNode,
    FieldAgreement,
    FieldCheckOutcome,
    IdentityOutcome,
    IdentityReason,
    IdentityResolutionNode,
    IdentityScope,
    IdentityScopeNode,
    MelleaCandidateJudgmentNode,
    MelleaIdentityJudgmentNode,
    ValidationNodeStatus,
)

US = Reporter(
    as_written="U.S.",
    short_name="U.S.",
    name="United States Supreme Court Reports",
    cite_type="federal",
    is_scotus=True,
)
SCT = Reporter(
    as_written="S. Ct.",
    short_name="S. Ct.",
    name="West's Supreme Court Reporter",
    cite_type="federal",
    is_scotus=True,
)
F3D = Reporter(as_written="F.3d", short_name="F.3d", name="Federal Reporter", cite_type="federal")

TWOMBLY = CourtListenerOpinionCluster(
    cluster_id="c-twombly",
    case_name="Bell Atlantic Corp. v. Twombly",
    date_filed="2007-05-21",
    docket_id="d1",
)
IQBAL = CourtListenerOpinionCluster(
    cluster_id="c-iqbal", case_name="Ashcroft v. Iqbal", date_filed="2009-05-18", docket_id="d2"
)


class Client:
    """A lookup table standing in for CourtListener."""

    def __init__(
        self,
        table: dict[tuple[str, str, str], tuple[CourtListenerOpinionCluster, ...]],
        *,
        courts: dict[str, str] | None = None,
        failing: set[tuple[str, str, str]] | None = None,
        details: dict[str, tuple[str, tuple[str, ...]]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.table = table
        self.courts = courts or {}
        self.failing = failing or set()
        self.details = details or {}
        """Per cluster id: its other_dates text and its sub-opinion ids."""
        self.headers = headers or {}
        """Per opinion id: the HTML whose header is read."""
        self.lookups: list[tuple[str, str, str]] = []
        self.dockets: list[str] = []
        self.clusters: list[str] = []
        self.opinions: list[str] = []

    def lookup_citation(self, volume: str, reporter: str, page: str) -> CourtListenerCitationLookup:
        key = (volume, reporter, page)
        self.lookups.append(key)
        if key in self.failing:
            raise CourtListenerError("boom", failure_type="test")
        clusters = self.table.get(key, ())
        status = 404 if not clusters else 200 if len(clusters) == 1 else 300
        return CourtListenerCitationLookup(citation=" ".join(key), status=status, clusters=clusters)

    def get_docket(self, docket_id: str) -> CourtListenerDocket:
        self.dockets.append(docket_id)
        return CourtListenerDocket(docket_id=docket_id, court_id=self.courts.get(docket_id))

    def search(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("the identity stage sends no search")

    def get_cluster(self, cluster_id: str) -> CourtListenerClusterDetail:
        self.clusters.append(cluster_id)
        other_dates, opinion_ids = self.details.get(cluster_id, ("", ()))
        return CourtListenerClusterDetail(
            cluster_id=cluster_id,
            date_filed=None,
            other_dates=other_dates,
            sub_opinion_ids=tuple(opinion_ids),
        )

    def get_opinion(self, opinion_id: str) -> CourtListenerOpinion:
        self.opinions.append(opinion_id)
        return CourtListenerOpinion(
            opinion_id=opinion_id,
            cluster_id=None,
            opinion_type="010combined",
            html_with_citations=self.headers.get(opinion_id, ""),
        )


def _cite(
    citation_id: str,
    citation: object,
    *,
    text: str,
    locator: str,
    authority_id: str | None,
    colocation_id: str | None = None,
    resolves_to: str | None = None,
) -> ExtractedCitation:
    start = text.index(locator)
    return ExtractedCitation(
        citation_id=citation_id,
        full_span=Span(start, start + len(locator)),
        locator_span=Span(start, start + len(locator)),
        matched_text=locator,
        citation=citation,
        resolves_to=resolves_to,
        authority_id=authority_id,
        colocation_id=colocation_id,
    )


def _document(text: str, *citations: ExtractedCitation) -> ExtractedDocument:
    preprocessed = preprocess_plain_text_from_string(text)
    return ExtractedDocument(
        source_metadata=preprocessed.source_metadata,
        text=text,
        preprocessing_metadata=preprocessed.preprocessing_metadata,
        citations=citations,
        extraction_metadata=ExtractionMetadata(),
    )


def _twombly(**overrides: object) -> FullCaseCitation:
    fields: dict[str, object] = {
        "plaintiff": "Bell Atl. Corp.",
        "defendant": "Twombly",
        "volume": "550",
        "reporter": US,
        "page": "544",
        "date": CitationDate(year="2007"),
        "court": "scotus",
    }
    fields.update(overrides)
    return FullCaseCitation(**fields)


def _run(document: ExtractedDocument, client: Client, session: object | None = None):
    return asyncio.run(identify_document(document, client=client, session=session))


def _resolution(record: CitationRecord) -> IdentityResolutionNode:
    nodes = [node for node in record.trace.nodes if isinstance(node, IdentityResolutionNode)]
    assert len(nodes) == 1
    return nodes[0]


def _fake_model(monkeypatch: pytest.MonkeyPatch, answer: dict[str, object]) -> list[object]:
    monkeypatch.setenv("MELLEA_LRC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_KEY", "test-key")
    calls: list[object] = []

    async def fake_instruct(_session: object, spec: object, **_kwargs: object) -> SimpleNamespace:
        calls.append(spec)
        return SimpleNamespace(success=True, result=SimpleNamespace(value=json.dumps(answer)))

    monkeypatch.setattr("mellea_lrc.validation.identity.mellea_judgment.run_instruct_ivr", fake_instruct)
    return calls


def _fake_candidates_model(monkeypatch: pytest.MonkeyPatch, answer: dict[str, object]) -> list[object]:
    monkeypatch.setenv("MELLEA_LRC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_KEY", "test-key")
    calls: list[object] = []

    async def fake_instruct(_session: object, spec: object, **_kwargs: object) -> SimpleNamespace:
        calls.append(spec)
        return SimpleNamespace(success=True, result=SimpleNamespace(value=json.dumps(answer)))

    monkeypatch.setattr("mellea_lrc.validation.identity.mellea_candidates.run_instruct_ivr", fake_instruct)
    return calls


def _no_reading() -> dict[str, object]:
    return {
        "case_name_read": None,
        "court_read": None,
        "court_evidence": None,
        "court_basis": "none",
        "date_read": None,
        "date_evidence": None,
    }


# --- scope ---------------------------------------------------------------------


def test_only_roots_are_looked_up_and_non_roots_inherit() -> None:
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2007). Id. at 570. 28 U.S.C. § 1331."
    root = _cite("c1", _twombly(), text=text, locator="550 U.S. 544", authority_id="c1")
    follow = _cite(
        "c2", IdCitation(pin_cite="at 570"), text=text, locator="Id.", authority_id="c1", resolves_to="c1"
    )
    statute = _cite(
        "c3",
        FullLawCitation(volume="28", reporter=Reporter(as_written="U.S.C."), page="1331"),
        text=text,
        locator="28 U.S.C. § 1331",
        authority_id=None,
    )
    client = Client({("550", "U.S.", "544"): (TWOMBLY,)}, courts={"d1": "scotus"})

    result = _run(_document(text, root, follow, statute), client)

    assert client.lookups == [("550", "U.S.", "544")]
    scopes = [
        next(n for n in r.trace.nodes if isinstance(n, IdentityScopeNode)).outcome for r in result.records
    ]
    assert scopes == [IdentityScope.ROOT_CASE, IdentityScope.NON_ROOT, IdentityScope.OUT_OF_SCOPE]
    assert _resolution(result.record("c1")).outcome is IdentityOutcome.CONFIRMED_IDENTITY
    assert result.resolution_of("c2") is _resolution(result.record("c1"))
    assert result.resolution_of("c3") is None
    assert result.record("c1").resolution is not None
    assert result.record("c1").resolution.cluster_id == "c-twombly"
    assert result.record("c1").resolution.court_id == "scotus"


def test_a_docket_root_is_deferred_and_says_so() -> None:
    text = "Reyes v. Pac. Bell, No. 1:25-cv-05745-RPK (E.D.N.Y. Oct. 31, 2024)."
    docket = DocketCitation(
        plaintiff="Reyes", defendant="Pac. Bell", docket_number="1:25-cv-05745-RPK", court="nyed"
    )
    root = _cite("c1", docket, text=text, locator="No. 1:25-cv-05745-RPK", authority_id="c1")
    client = Client({})

    result = _run(_document(text, root), client)

    assert client.lookups == []
    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.DEFER_TO_SEARCH
    assert [type(n).__name__ for n in result.record("c1").trace.nodes] == [
        "IdentityScopeNode",
        "DocketIdentityNode",
        "IdentityResolutionNode",
    ]


# --- the rule guard --------------------------------------------------------------


def test_the_rule_guard_establishes_identity_without_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_model(monkeypatch, {})
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2007)."
    root = _cite("c1", _twombly(), text=text, locator="550 U.S. 544", authority_id="c1")
    client = Client({("550", "U.S.", "544"): (TWOMBLY,)}, courts={"d1": "scotus"})

    result = _run(_document(text, root), client, session=object())

    assert calls == []
    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.CONFIRMED_IDENTITY
    assert resolution.decided_by == "rule"
    assert resolution.fields == ()
    assert resolution.reason is None


def test_an_absent_field_is_not_a_disagreement(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_model(monkeypatch, {})
    text = "Twombly, 550 U.S. 544."
    root = _cite("c1", _twombly(date=None, court=None), text=text, locator="550 U.S. 544", authority_id="c1")
    client = Client({("550", "U.S.", "544"): (TWOMBLY,)})

    result = _run(_document(text, root), client, session=object())

    assert calls == []
    assert _resolution(result.record("c1")).outcome is IdentityOutcome.CONFIRMED_IDENTITY


def test_a_year_the_archive_holds_beside_its_filing_date_is_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_model(monkeypatch, {})
    text = "Roe v. Acme Corp., 700 F.3d 1 (4th Cir. 2014)."
    citation = FullCaseCitation(
        plaintiff="Roe",
        defendant="Acme Corp.",
        volume="700",
        reporter=F3D,
        page="1",
        date=CitationDate(year="2014"),
    )
    root = _cite("c1", citation, text=text, locator="700 F.3d 1", authority_id="c1")
    amended = CourtListenerOpinionCluster(
        cluster_id="c-a", case_name="Roe v. Acme Corp.", date_filed="2013-12-27"
    )
    client = Client(
        {("700", "F.3d", "1"): (amended,)},
        details={"c-a": ("Argued and Submitted April 18, 2013., Amended Feb. 5, 2014.", ("o1",))},
    )

    result = _run(_document(text, root), client, session=object())

    assert calls == []
    assert client.clusters == ["c-a"] and client.opinions == []
    record = result.record("c1")
    reconciled = next(n for n in record.trace.nodes if isinstance(n, DateReconciliationNode))
    assert reconciled.outcome is FieldCheckOutcome.COMPATIBLE
    assert reconciled.matched_phrase == "Amended Feb. 5, 2014"
    assert _resolution(record).outcome is IdentityOutcome.CONFIRMED_IDENTITY


def test_the_opinion_header_is_read_when_the_cluster_holds_no_other_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_model(monkeypatch, {})
    text = "Roe v. Acme Corp., 300 U.S. 1 (1948)."
    citation = FullCaseCitation(
        plaintiff="Roe",
        defendant="Acme Corp.",
        volume="300",
        reporter=US,
        page="1",
        date=CitationDate(year="1948"),
        court="scotus",
    )
    root = _cite("c1", citation, text=text, locator="300 U.S. 1", authority_id="c1")
    later = CourtListenerOpinionCluster(
        cluster_id="c-b", case_name="Roe v. Acme Corp.", date_filed="1949-02-14", docket_id="d"
    )
    client = Client(
        {("300", "U.S.", "1"): (later,)},
        courts={"d": "scotus"},
        details={"c-b": ("Argued October 14-15, 1948.", ("o1", "o2"))},
        headers={
            "o1": "<p>Mr. Justice delivered the opinion of the Court.</p>",
            "o2": "<p>300 U.S. 1 (1948) ROE v. ACME CORP. Argued October 14-15, 1948. Decided December 20, 1948.</p>",
        },
    )

    result = _run(_document(text, root), client, session=object())

    assert calls == []
    # The lead opinion carries no header; the combined one after it does.
    assert client.opinions == ["o1", "o2"]
    record = result.record("c1")
    reconciled = next(n for n in record.trace.nodes if isinstance(n, DateReconciliationNode))
    assert reconciled.outcome is FieldCheckOutcome.COMPATIBLE
    assert reconciled.matched_phrase == "Decided December 20, 1948"
    assert reconciled.opinion_id == "o2" and reconciled.opinions_read == ("o1", "o2")
    assert _resolution(record).outcome is IdentityOutcome.CONFIRMED_IDENTITY
    # The opinion that answered leads the resolution, and its text stays on the record.
    assert record.resolution is not None and record.resolution.opinion_ids == ("o2", "o1")
    assert set(record.opinions) == {"o1", "o2"}
    assert "Decided December 20, 1948" in record.opinions["o2"].html_with_citations


def test_an_argument_date_does_not_make_a_year_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_model(
        monkeypatch,
        {
            "case_name_read": "Roe v. Acme Corp.",
            "case_name_agreement": "agree",
            "court_read": "scotus",
            "court_evidence": None,
            "court_basis": "implied_by_reporter",
            "date_read": "1875",
            "date_evidence": "1875",
            "verdict": "same_case",
            "reason": "Same case; the filing states the argument year.",
        },
    )
    text = "Roe v. Acme Corp., 90 U.S. 1 (1875)."
    citation = FullCaseCitation(
        plaintiff="Roe",
        defendant="Acme Corp.",
        volume="90",
        reporter=US,
        page="1",
        date=CitationDate(year="1875"),
        court="scotus",
    )
    root = _cite("c1", citation, text=text, locator="90 U.S. 1", authority_id="c1")
    old = CourtListenerOpinionCluster(
        cluster_id="c-o", case_name="Roe v. Acme Corp.", date_filed="1876-04-24", docket_id="d"
    )
    client = Client(
        {("90", "U.S.", "1"): (old,)},
        courts={"d": "scotus"},
        details={"c-o": ("Argued November 3, 1875.", ("o3",))},
        headers={"o3": "<p>Mr. Chief Justice delivered the opinion of the court.</p>"},
    )

    result = _run(_document(text, root), client, session=object())

    record = result.record("c1")
    reconciled = next(n for n in record.trace.nodes if isinstance(n, DateReconciliationNode))
    assert reconciled.outcome is FieldCheckOutcome.MISMATCH
    assert reconciled.dated_phrases == ()
    resolution = _resolution(record)
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert [(f.field, f.filing_value, f.record_value) for f in resolution.fields] == [
        ("date", "1875", "1876-04-24")
    ]


def test_not_found_is_unresolved_not_refuted() -> None:
    text = "Smith v. Jones, 999 F.3d 1 (9th Cir. 2020)."
    citation = FullCaseCitation(
        plaintiff="Smith",
        defendant="Jones",
        volume="999",
        reporter=F3D,
        page="1",
        date=CitationDate(year="2020"),
    )
    root = _cite("c1", citation, text=text, locator="999 F.3d 1", authority_id="c1")

    result = _run(_document(text, root), Client({}))

    assert _resolution(result.record("c1")).outcome is IdentityOutcome.DEFER_TO_SEARCH
    assert result.record("c1").resolution is None


def test_a_failed_lookup_is_unresolved_with_the_error_in_the_trace() -> None:
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2007)."
    root = _cite("c1", _twombly(), text=text, locator="550 U.S. 544", authority_id="c1")
    client = Client({}, failing={("550", "U.S.", "544")})

    result = _run(_document(text, root), client)

    assert _resolution(result.record("c1")).outcome is IdentityOutcome.DEFER_TO_SEARCH
    assert any(getattr(node, "error", None) == "boom" for node in result.record("c1").trace.nodes)


# --- the judgement ----------------------------------------------------------------


def test_a_rule_disagreement_sends_one_composite_call_and_records_its_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_model(
        monkeypatch,
        {
            "case_name_read": "Conley v. Gibson",
            "case_name_agreement": "disagree",
            "court_read": "fladistctapp",
            "court_evidence": "Fla. Dist. Ct. App.",
            "court_basis": "stated",
            "date_read": "2010",
            "date_evidence": "2010",
            "verdict": "different_case",
            "reason": "The page holds Galeana v. Galeana.",
        },
    )
    text = "See Conley v. Gibson, 44 So. 3d 587 (Fla. Dist. Ct. App. 2010)."
    so3d = Reporter(
        as_written="So. 3d", short_name="So. 3d", name="Southern Reporter", cite_type="state_regional"
    )
    citation = FullCaseCitation(
        plaintiff="Conley",
        defendant="Gibson",
        volume="44",
        reporter=so3d,
        page="587",
        date=CitationDate(year="2010"),
        court="fladistctapp",
    )
    root = _cite("c1", citation, text=text, locator="44 So. 3d 587", authority_id="c1")
    galeana = CourtListenerOpinionCluster(
        cluster_id="c-g", case_name="Galeana v. Galeana", date_filed="2010-08-11", docket_id="d9"
    )
    client = Client({("44", "So. 3d", "587"): (galeana,)}, courts={"d9": "fladistctapp"})

    result = _run(_document(text, root), client, session=object())

    assert len(calls) == 1
    spec = calls[0]
    assert "Conley v. Gibson, [[44 So. 3d 587]]" in spec.grounding_context["context"]
    assert "Galeana v. Galeana" in spec.user_variables["record"]
    assert "case name: mismatch" in spec.user_variables["rules"]
    assert [r.description for r in spec.requirements] == [
        "Return a valid identity-judgment object.",
        "Every reading must be grounded in its window.",
        "The verdict must follow from the agreements.",
    ]
    record = result.record("c1")
    judgment = next(n for n in record.trace.nodes if isinstance(n, MelleaIdentityJudgmentNode))
    assert judgment.model == "test-model"
    resolution = _resolution(record)
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert resolution.reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR
    assert resolution.record_case_name == "Galeana v. Galeana"
    assert resolution.decided_by == judgment.node_id
    assert [(f.field, f.filing_value, f.record_value) for f in resolution.fields] == [
        ("case_name", "Conley v. Gibson", "Galeana v. Galeana")
    ]
    assert record.resolution is None
    assert record.corrections == ()


def test_the_model_corrects_the_filing_reading_but_never_the_filing(monkeypatch: pytest.MonkeyPatch) -> None:
    # The extractor took the court from the next citation, and the filing states
    # the wrong year. The model fixes the first and reports the second.
    _fake_model(
        monkeypatch,
        {
            "case_name_read": "Bell Atl. Corp. v. Twombly",
            "case_name_agreement": "agree",
            "court_read": "scotus",
            "court_evidence": None,
            "court_basis": "implied_by_reporter",
            "date_read": "2009",
            "date_evidence": "2009",
            "verdict": "same_case",
            "reason": "Same case; the filing misdates it.",
        },
    )
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2009); Other v. Case, 1 F.3d 2 (9th Cir. 1993)."
    root = _cite(
        "c1",
        _twombly(court="ca9", date=CitationDate(year="2009")),
        text=text,
        locator="550 U.S. 544",
        authority_id="c1",
    )
    client = Client({("550", "U.S.", "544"): (TWOMBLY,)}, courts={"d1": "scotus"})

    result = _run(_document(text, root), client, session=object())

    record = result.record("c1")
    resolution = _resolution(record)
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert resolution.reason is IdentityReason.FIELD_DISAGREEMENT
    assert [(f.field, f.filing_value, f.record_value, f.agreement.value) for f in resolution.fields] == [
        ("date", "2009", "2007-05-21", "disagree")
    ]
    assert record.citation.court == "scotus"
    assert record.citation.date == CitationDate(year="2009")
    assert record.source.citation.court == "ca9"
    assert [(c.field, c.before, c.after, c.made_by) for c in record.corrections] == [
        ("court", "ca9", "scotus", "test-model")
    ]
    assert record.resolution is not None
    assert record.resolution.date_filed == "2007-05-21"


def test_a_misspelt_party_is_the_same_case_with_a_defect(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_model(
        monkeypatch,
        {
            "case_name_read": "Rufo v. Inmates of Suffock County Jail",
            "case_name_agreement": "misspelt",
            "court_read": "scotus",
            "court_evidence": None,
            "court_basis": "implied_by_reporter",
            "date_read": "1992",
            "date_evidence": "1992",
            "verdict": "same_case",
            "reason": "Suffock is a misspelling of Suffolk.",
        },
    )
    text = "Rufo v. Inmates of Suffock County Jail, 502 U.S. 367 (1992)."
    citation = FullCaseCitation(
        plaintiff="Rufo",
        defendant="Inmates of Suffock County Jail",
        volume="502",
        reporter=US,
        page="367",
        date=CitationDate(year="1992"),
        court="scotus",
    )
    root = _cite("c1", citation, text=text, locator="502 U.S. 367", authority_id="c1")
    rufo = CourtListenerOpinionCluster(
        cluster_id="c-rufo",
        case_name="Rufo v. Inmates of Suffolk County Jail",
        date_filed="1992-01-15",
        docket_id="d",
    )
    client = Client({("502", "U.S.", "367"): (rufo,)}, courts={"d": "scotus"})

    result = _run(_document(text, root), client, session=object())

    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert resolution.reason is IdentityReason.FIELD_DISAGREEMENT
    assert [(f.field, f.agreement.value) for f in resolution.fields] == [("case_name", "misspelt")]
    assert result.record("c1").resolution is not None
    assert result.record("c1").corrections == ()


def test_an_equivalent_caption_is_a_variant_and_not_a_defect(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_model(
        monkeypatch,
        {
            "case_name_read": "Roe ex rel. Roe v. Acme Corp.",
            "case_name_agreement": "variant",
            "court_read": None,
            "court_evidence": None,
            "court_basis": "none",
            "date_read": "2001",
            "date_evidence": "2001",
            "verdict": "same_case",
            "reason": "A relator caption for the same case.",
        },
    )
    text = "Roe ex rel. Roe v. Acme Corp., 300 F.3d 1 (4th Cir. 2001)."
    citation = FullCaseCitation(
        plaintiff="Roe ex rel. Roe",
        defendant="Acme Corp.",
        volume="300",
        reporter=F3D,
        page="1",
        date=CitationDate(year="2001"),
    )
    root = _cite("c1", citation, text=text, locator="300 F.3d 1", authority_id="c1")
    record = CourtListenerOpinionCluster(
        cluster_id="c-r", case_name="Doe v. Acme Corporation", date_filed="2001-05-05"
    )
    result = _run(_document(text, root), Client({("300", "F.3d", "1"): (record,)}), session=object())

    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.CONFIRMED_IDENTITY
    assert resolution.fields == ()
    judgment = next(n for n in result.record("c1").trace.nodes if isinstance(n, MelleaIdentityJudgmentNode))
    assert judgment.case_name_agreement is FieldAgreement.VARIANT


def test_a_failed_model_call_leaves_the_root_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELLEA_LRC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_KEY", "test-key")

    async def failing(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(success=False, result=None)

    monkeypatch.setattr("mellea_lrc.validation.identity.mellea_judgment.run_instruct_ivr", failing)
    text = "Wrong v. Name, 550 U.S. 544 (2007)."
    root = _cite(
        "c1",
        _twombly(plaintiff="Wrong", defendant="Name"),
        text=text,
        locator="550 U.S. 544",
        authority_id="c1",
    )
    client = Client({("550", "U.S.", "544"): (TWOMBLY,)}, courts={"d1": "scotus"})

    result = _run(_document(text, root), client, session=object())

    record = result.record("c1")
    judgment = next(n for n in record.trace.nodes if isinstance(n, MelleaIdentityJudgmentNode))
    assert judgment.status is ValidationNodeStatus.FAILED
    assert _resolution(record).outcome is IdentityOutcome.DEFER_TO_SEARCH


@pytest.mark.parametrize(
    ("answers", "verdict", "reason"),
    [
        (("agree", "agree", "agree"), "different_case", "Every field agrees"),
        (("agree", "agree", "agree"), "undeterminable", "Every field agrees"),
        (("agree", "undeterminable", "agree"), "different_case", "at least one field to disagree"),
        (("disagree", "agree", "agree"), "same_case", "rules out same_case"),
        (("agree", "disagree", "agree"), "undeterminable", "undeterminable field"),
        (("agree", "disagree", "agree"), "different_case", "same case"),
        (("undeterminable", "disagree", "agree"), "different_case", "no case name"),
        (("undeterminable", "disagree", "agree"), "undeterminable", None),
        (("variant", "agree", "agree"), "same_case", None),
        (("variant", "agree", "agree"), "different_case", "Every field agrees"),
        (("variant", "agree", "agree"), "undeterminable", "Every field agrees"),
        (("misspelt", "agree", "agree"), "same_case", None),
        (("misspelt", "agree", "agree"), "undeterminable", "undeterminable field"),
        (("misspelt", "disagree", "agree"), "different_case", "same case"),
        (("agree", "disagree", "agree"), "same_case", None),
        (("agree", "undeterminable", "agree"), "same_case", None),
        (("disagree", "agree", "agree"), "different_case", None),
        (("agree", "undeterminable", "agree"), "undeterminable", None),
    ],
)
def test_the_verdict_must_follow_from_the_field_answers(
    answers: tuple[str, str, str], verdict: str, reason: str | None
) -> None:
    court_read = {"agree": "scotus", "disagree": "ca9", "undeterminable": None}[answers[1]]
    date_read = {"agree": "2007", "disagree": "2009", "undeterminable": None}[answers[2]]
    judgment = IdentityJudgment(
        case_name_read=None,
        case_name_agreement=answers[0],
        court_read=court_read,
        court_evidence=None,
        court_basis="implied_by_reporter" if court_read else "none",
        date_read=date_read,
        date_evidence=date_read,
        verdict=verdict,
        reason="",
    )
    grounding = Grounding(
        name_window="",
        parenthetical_window="",
        reporter=US,
        record_court_id="scotus",
        record_date="2007-05-21",
    )
    problem = verdict_supported(judgment, grounding)
    if reason is None:
        assert problem is None
    else:
        assert problem is not None
        assert reason in problem


def _grounding(**overrides: object) -> Grounding:
    fields: dict[str, object] = {
        "name_window": "See Conley v. Gibson, ",
        "parenthetical_window": " (Fla. Dist. Ct. App. 2010).",
        "reporter": Reporter(as_written="So. 3d", short_name="So. 3d", cite_type="state_regional"),
        "record_court_id": "fladistctapp",
        "record_date": "2010-08-11",
    }
    fields.update(overrides)
    return Grounding(**fields)


def _judgment(**overrides: object) -> IdentityJudgment:
    fields: dict[str, object] = {
        "case_name_read": "Conley v. Gibson",
        "case_name_agreement": "agree",
        "court_read": "fladistctapp",
        "court_evidence": "Fla. Dist. Ct. App.",
        "court_basis": "stated",
        "date_read": "2010",
        "date_evidence": "2010",
        "verdict": "same_case",
        "reason": "",
    }
    fields.update(overrides)
    return IdentityJudgment(**fields)


def test_a_grounded_judgment_passes_every_check() -> None:
    assert readings_grounded(_judgment(), _grounding()) == {}


def test_the_case_name_must_come_from_the_name_window_allowing_for_spelling() -> None:
    assert "case_name" in readings_grounded(_judgment(case_name_read="Smith v. Gibson"), _grounding())
    # The model corrects a typo the filing made; that is reading well, not inventing.
    assert readings_grounded(_judgment(case_name_read="Conley v. Gibsom"), _grounding()) == {}
    # A name that is in the parenthetical window but not the name window is another citation's.
    assert "case_name" in readings_grounded(
        _judgment(case_name_read="Galeana v. Galeana"),
        _grounding(parenthetical_window=" (Galeana v. Galeana, 2010)."),
    )
    assert readings_grounded(_judgment(case_name_read=None), _grounding()) == {}


def test_a_stated_court_needs_evidence_in_the_parenthetical_that_resolves_to_it() -> None:
    assert "courts-db" in readings_grounded(_judgment(court_read="nowhere"), _grounding())["court"]
    assert "court_evidence" in readings_grounded(_judgment(court_evidence=None), _grounding())["court"]
    assert (
        "not in parenthetical_window"
        in readings_grounded(_judgment(court_evidence="9th Cir."), _grounding())["court"]
    )
    assert (
        "resolves to 'ca9'"
        in readings_grounded(
            _judgment(court_read="ca10", court_evidence="9th Cir."),
            _grounding(parenthetical_window=" (9th Cir. 2010)"),
        )["court"]
    )
    assert (
        readings_grounded(
            _judgment(court_read="ca9", court_evidence="9th Cir."),
            _grounding(parenthetical_window=" (9th Cir. 2010)"),
        )
        == {}
    )


def test_an_implied_court_is_allowed_only_where_the_reporter_implies_one() -> None:
    implied = _judgment(court_read="scotus", court_evidence=None, court_basis="implied_by_reporter")
    assert readings_grounded(implied, _grounding(reporter=US, record_court_id="scotus")) == {}
    assert "holds more than one court" in readings_grounded(implied, _grounding())["court"]
    wrong = _judgment(court_read="ca9", court_evidence=None, court_basis="implied_by_reporter")
    assert "implies 'scotus'" in readings_grounded(wrong, _grounding(reporter=US))["court"]
    unsaid = _judgment(court_read="fladistctapp", court_evidence=None, court_basis="none")
    assert "court_basis is none" in readings_grounded(unsaid, _grounding())["court"]


def test_a_date_needs_evidence_in_the_parenthetical_it_can_be_read_from() -> None:
    assert "YYYY" in readings_grounded(_judgment(date_read="Oct 2010"), _grounding())["date"]
    assert "date_evidence" in readings_grounded(_judgment(date_evidence=None), _grounding())["date"]
    assert (
        "not in parenthetical_window"
        in readings_grounded(_judgment(date_evidence="2011"), _grounding())["date"]
    )
    assert "states a year" in readings_grounded(_judgment(date_read="2011"), _grounding())["date"]
    day = _judgment(
        date_read="2024-10-31", date_evidence="Oct. 31, 2024", court_read=None, court_basis="none"
    )
    assert readings_grounded(day, _grounding(parenthetical_window=" (E.D.N.Y. Oct. 31, 2024)")) == {}
    off = _judgment(
        date_read="2024-10-30", date_evidence="Oct. 31, 2024", court_read=None, court_basis="none"
    )
    assert (
        "states a day"
        in readings_grounded(off, _grounding(parenthetical_window=" (E.D.N.Y. Oct. 31, 2024)"))["date"]
    )


def test_an_unstated_court_is_checked_for_conflict_with_the_reporter() -> None:
    nc_app = frozenset({"nc", "ncctapp"})
    assert court_agreement(None, "ncctapp", nc_app) is FieldAgreement.COMPATIBLE
    assert court_agreement(None, "txsd", nc_app) is FieldAgreement.DISAGREE
    assert court_agreement(None, "txsd", frozenset()) is FieldAgreement.UNDETERMINABLE
    compatible = _judgment(court_read=None, court_evidence=None, court_basis="none", verdict="same_case")
    grounding = _grounding(record_court_id="ncctapp", implied=nc_app)
    assert verdict_supported(compatible, grounding) is None
    conflicting = _grounding(record_court_id="txsd", implied=nc_app)
    assert "must be same_case" in (
        verdict_supported(
            _judgment(court_read=None, court_evidence=None, court_basis="none", verdict="different_case"),
            conflicting,
        )
        or ""
    )


def test_court_and_date_agreement_are_computed_from_the_reading() -> None:
    assert court_agreement("scotus", "scotus") is FieldAgreement.AGREE
    assert court_agreement("ca9", "scotus") is FieldAgreement.DISAGREE
    assert court_agreement(None, "scotus") is FieldAgreement.UNDETERMINABLE
    assert date_agreement("2007", "2007-05-21") is FieldAgreement.AGREE
    assert date_agreement("2007-05-22", "2007-05-21") is FieldAgreement.DISAGREE
    assert date_agreement("2008", "2007-05-21") is FieldAgreement.DISAGREE
    assert date_agreement("2007", None) is FieldAgreement.UNDETERMINABLE


def test_a_failed_judgment_keeps_the_readings_whose_evidence_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELLEA_LRC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("MELLEA_LRC_LLM_API_KEY", "test-key")
    answer = {
        "case_name_read": "Norton v. Shelby County",
        "case_name_agreement": "agree",
        "court_read": "ca9",
        "court_evidence": "9th Cir.",
        "court_basis": "stated",
        "date_read": "1886",
        "date_evidence": "1886",
        "verdict": "same_case",
        "reason": "The extractor took Under into the name.",
    }

    async def exhausted(_session: object, spec: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            success=False, result=None, sample_generations=[SimpleNamespace(value=json.dumps(answer))]
        )

    monkeypatch.setattr("mellea_lrc.validation.identity.mellea_judgment.run_instruct_ivr", exhausted)
    text = "Under Norton v. Shelby County, 118 U.S. 425 (1886), the rule is settled."
    root = _cite(
        "c1",
        _twombly(
            plaintiff="Under Nortan",
            defendant="Shelby County",
            volume="118",
            page="425",
            date=CitationDate(year="1886"),
        ),
        text=text,
        locator="118 U.S. 425",
        authority_id="c1",
    )
    norton = CourtListenerOpinionCluster(
        cluster_id="c-n", case_name="Norton v. Shelby County", date_filed="1886-05-10", docket_id="d"
    )
    client = Client({("118", "U.S.", "425"): (norton,)}, courts={"d": "scotus"})

    result = _run(_document(text, root), client, session=object())

    record = result.record("c1")
    judgment = next(n for n in record.trace.nodes if isinstance(n, MelleaIdentityJudgmentNode))
    assert judgment.status is ValidationNodeStatus.FAILED
    assert judgment.grounded == ("case_name", "date")
    assert judgment.case_name_read == "Norton v. Shelby County"
    assert judgment.court_read is None
    assert "9th Cir." in (judgment.error or "")
    assert [(c.field, c.after) for c in record.corrections] == [("plaintiff", "Norton")]
    assert _resolution(record).outcome is IdentityOutcome.DEFER_TO_SEARCH


# --- several records at the locator ---------------------------------------------

SO3D = Reporter(
    as_written="So. 3d", short_name="So. 3d", name="Southern Reporter", cite_type="state_regional"
)
F2D = Reporter(as_written="F.2d", short_name="F.2d", name="Federal Reporter", cite_type="federal")


def _page(*names: str, year: int = 2010) -> tuple[CourtListenerOpinionCluster, ...]:
    return tuple(
        CourtListenerOpinionCluster(cluster_id=f"c{i}", case_name=name, date_filed=f"{year}-0{i}-01")
        for i, name in enumerate(names, 1)
    )


def test_one_record_agreeing_by_rule_confirms_and_the_page_is_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    single = _fake_model(monkeypatch, {})
    several = _fake_candidates_model(monkeypatch, {})
    text = "Sprague v. Gen. Motors Corp., 688 F.2d 816 (2d Cir. 1982)."
    citation = FullCaseCitation(
        plaintiff="Sprague", defendant="Gen. Motors Corp.", volume="688", reporter=F2D, page="816"
    )
    root = _cite("c1", citation, text=text, locator="688 F.2d 816", authority_id="c1")
    page = _page(
        "Kulwiec, in re",
        "Langone v. Leach",
        "Malvasio v. Marshall",
        "Sprague v. General Motors Corp.",
        year=1982,
    )

    result = _run(_document(text, root), Client({("688", "F.2d", "816"): page}), session=object())

    assert single == [] and several == []
    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.CONFIRMED_IDENTITY
    assert resolution.decided_by == "rule"
    assert resolution.records_at_locator == 4
    assert resolution.cluster_id == "c4"
    assert "One of 4 records" in (resolution.outcome_message or "")


def test_a_decision_the_archive_holds_twice_confirms_with_both_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    several = _fake_candidates_model(monkeypatch, {})
    text = "Ashcroft v. Iqbal, 556 U.S. 662 (2009)."
    citation = FullCaseCitation(
        plaintiff="Ashcroft",
        defendant="Iqbal",
        volume="556",
        reporter=US,
        page="662",
        date=CitationDate(year="2009"),
    )
    root = _cite("c1", citation, text=text, locator="556 U.S. 662", authority_id="c1")
    twice = (
        CourtListenerOpinionCluster(cluster_id="c-a", case_name="Ashcroft v. Iqbal", date_filed="2009-05-18"),
        CourtListenerOpinionCluster(cluster_id="c-b", case_name="Ashcroft v. Iqbal", date_filed="2009-05-18"),
    )
    result = _run(_document(text, root), Client({("556", "U.S.", "662"): twice}), session=object())

    assert several == []
    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.CONFIRMED_IDENTITY
    assert resolution.agreeing_cluster_ids == ("c-a", "c-b")
    assert "one decision the archive holds more than once" in (resolution.outcome_message or "")


def test_a_page_with_more_records_than_a_judgement_is_shown_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    several = _fake_candidates_model(monkeypatch, {})
    text = "Conley v. Gibson, 44 So. 3d 587 (Fla. Dist. Ct. App. 2010)."
    citation = FullCaseCitation(
        plaintiff="Conley", defendant="Gibson", volume="44", reporter=SO3D, page="587"
    )
    root = _cite("c1", citation, text=text, locator="44 So. 3d 587", authority_id="c1")
    page = _page(
        "Galeana v. Galeana",
        "Galura v. State",
        "Gest v. State",
        "Gillins v. State",
        "Grady v. State",
        "Griner v. State",
        "Haynes v. State",
    )
    client = Client({("44", "So. 3d", "587"): page})

    result = _run(_document(text, root), client, session=object())

    assert several == []
    assert client.dockets == []  # no court fetched on a page this crowded
    resolution = _resolution(result.record("c1"))
    assert resolution.outcome is IdentityOutcome.AMBIGUOUS_IDENTITY
    assert resolution.reason is IdentityReason.CROWDED_PAGE
    assert resolution.records_at_locator == 7


def test_when_no_record_agrees_one_judgement_sees_them_all_and_may_refute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_candidates_model(
        monkeypatch,
        {
            **_no_reading(),
            "case_name_read": "Boss v. N.Y. Life Ins. Co.",
            "records": [
                {
                    "index": 1,
                    "case_name_agreement": "disagree",
                    "same_case": "no",
                    "reason": "Different parties.",
                },
                {
                    "index": 2,
                    "case_name_agreement": "disagree",
                    "same_case": "no",
                    "reason": "Different parties.",
                },
            ],
            "chosen_index": None,
            "verdict": "different_case",
            "reason": "Neither record is the filing's case.",
        },
    )
    text = "Boss v. N.Y. Life Ins. Co., 298 N.Y. 917."
    ny = Reporter(as_written="N.Y.", short_name="N.Y.", editions=("N.Y.",), cite_type="state")
    citation = FullCaseCitation(
        plaintiff="Boss", defendant="N.Y. Life Ins. Co.", volume="298", reporter=ny, page="917"
    )
    root = _cite("c1", citation, text=text, locator="298 N.Y. 917", authority_id="c1")
    page = (
        CourtListenerOpinionCluster(
            cluster_id="c1", case_name="Condur Affiliates, Inc. v. Ronnie, Inc.", date_filed="1949-03-03"
        ),
        CourtListenerOpinionCluster(
            cluster_id="c2", case_name="Marks v. Prov. Mut. Life Ins. Co.", date_filed="1949-03-03"
        ),
    )
    result = _run(_document(text, root), Client({("298", "N.Y.", "917"): page}), session=object())

    assert len(calls) == 1
    spec = calls[0]
    assert "record 1:" in spec.user_variables["records"] and "record 2:" in spec.user_variables["records"]
    assert spec.user_variables["count"] == "2"
    record = result.record("c1")
    judgment = next(n for n in record.trace.nodes if isinstance(n, MelleaCandidateJudgmentNode))
    assert [a.same_case for a in judgment.candidates] == ["no", "no"]
    resolution = _resolution(record)
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert resolution.reason is IdentityReason.DIFFERENT_CASE_AT_LOCATOR
    assert "2 records" in (resolution.outcome_message or "")
    assert record.resolution is None


def test_the_judgement_may_choose_one_record_and_its_fields_are_then_compared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_candidates_model(
        monkeypatch,
        {
            **_no_reading(),
            "case_name_read": "Lacey v. Maricopa County",
            "date_read": "2012",
            "date_evidence": "2012",
            "records": [
                {
                    "index": 1,
                    "case_name_agreement": "disagree",
                    "same_case": "no",
                    "reason": "Different case.",
                },
                {
                    "index": 2,
                    "case_name_agreement": "variant",
                    "same_case": "yes",
                    "reason": "Same case under the sheriff's caption.",
                },
            ],
            "chosen_index": 2,
            "verdict": "same_case",
            "reason": "Record 2 is the en banc decision.",
        },
    )
    text = "Lacey v. Maricopa County, 693 F.3d 896 (9th Cir. 2012)."
    citation = FullCaseCitation(
        plaintiff="Lacey",
        defendant="Maricopa County",
        volume="693",
        reporter=F3D,
        page="896",
        date=CitationDate(year="2012"),
    )
    root = _cite("c1", citation, text=text, locator="693 F.3d 896", authority_id="c1")
    page = (
        CourtListenerOpinionCluster(cluster_id="c1", case_name="Smith v. Jones", date_filed="2012-08-29"),
        CourtListenerOpinionCluster(
            cluster_id="c2", case_name="Michael Lacey v. Joseph Arpaio", date_filed="2011-06-09"
        ),
    )
    result = _run(_document(text, root), Client({("693", "F.3d", "896"): page}), session=object())

    record = result.record("c1")
    resolution = _resolution(record)
    assert resolution.outcome is IdentityOutcome.WRONG_IDENTITY
    assert resolution.reason is IdentityReason.FIELD_DISAGREEMENT
    assert [(f.field, f.agreement.value) for f in resolution.fields] == [("date", "disagree")]
    assert resolution.cluster_id == "c2"
    assert record.resolution is not None and record.resolution.cluster_id == "c2"


@pytest.mark.parametrize(
    ("records", "chosen", "verdict", "reason"),
    [
        ([("agree", "yes"), ("disagree", "no")], 1, "same_case", None),
        ([("agree", "yes"), ("disagree", "no")], 2, "same_case", "must be a record whose"),
        ([("misspelt", "yes"), ("disagree", "no")], 1, "same_case", None),
        ([("agree", "yes"), ("disagree", "no")], 1, "different_case", "chosen record means"),
        ([("agree", "yes"), ("disagree", "no")], None, "same_case", "needs a chosen_index"),
        ([("disagree", "no"), ("disagree", "no")], None, "different_case", None),
        ([("disagree", "no"), ("undeterminable", "undeterminable")], None, "different_case", "every record"),
        ([("disagree", "no"), ("disagree", "no")], None, "undeterminable", "must be different_case"),
        ([("disagree", "no"), ("undeterminable", "undeterminable")], None, "undeterminable", None),
        ([("disagree", "no")], None, "different_case", "every index"),
    ],
)
def test_the_choice_must_follow_from_the_per_record_answers(
    records: list[tuple[str, str]], chosen: int | None, verdict: str, reason: str | None
) -> None:
    judgment = CandidateJudgment(
        **_no_reading(),
        records=[
            CandidateVerdict(index=i, case_name_agreement=name, same_case=same, reason="")
            for i, (name, same) in enumerate(records, 1)
        ],
        chosen_index=chosen,
        verdict=verdict,
        reason="",
    )
    problem = choice_supported(judgment, count=2)
    if reason is None:
        assert problem is None
    else:
        assert problem is not None and reason in problem


# --- parallel citations ---------------------------------------------------------


def test_parallel_citations_that_resolve_to_one_cluster_become_one_authority() -> None:
    text = "Ashcroft v. Iqbal, 556 U.S. 662, 129 S. Ct. 1937 (2009). Iqbal, 129 S. Ct. at 1949."
    first = _cite(
        "c1",
        FullCaseCitation(plaintiff="Ashcroft", defendant="Iqbal", volume="556", reporter=US, page="662"),
        text=text,
        locator="556 U.S. 662",
        authority_id="c1",
        colocation_id="c1",
    )
    second = _cite(
        "c2",
        FullCaseCitation(plaintiff="Ashcroft", defendant="Iqbal", volume="129", reporter=SCT, page="1937"),
        text=text,
        locator="129 S. Ct. 1937",
        authority_id="c2",
        colocation_id="c1",
    )
    follower = _cite(
        "c3",
        FullCaseCitation(volume="129", reporter=SCT, page="1949"),
        text=text,
        locator="129 S. Ct. at 1949",
        authority_id="c2",
        resolves_to="c2",
    )
    client = Client({("556", "U.S.", "662"): (IQBAL,), ("129", "S. Ct.", "1937"): (IQBAL,)})

    result = _run(_document(text, first, second, follower), client)

    assert [r.citation_id for r in result.roots] == ["c1"]
    merged = result.record("c2")
    assert merged.authority_id == "c1"
    merge = next(n for n in merged.trace.nodes if isinstance(n, AuthorityMergeNode))
    assert merge.outcome is AuthorityMergeOutcome.MERGED_INTO
    assert merge.target_citation_id == "c1"
    assert [(c.field, c.before, c.after) for c in merged.corrections] == [("authority_id", "c2", "c1")]
    assert merged.corrections[0].node_id == merge.node_id
    assert result.record("c3").authority_id == "c1"
    assert result.resolution_of("c3") is _resolution(result.record("c1"))


def test_parallel_citations_that_resolve_differently_stay_two_authorities() -> None:
    text = "Ashcroft v. Iqbal, 556 U.S. 662, 129 S. Ct. 1937 (2009)."
    first = _cite(
        "c1",
        FullCaseCitation(plaintiff="Ashcroft", defendant="Iqbal", volume="556", reporter=US, page="662"),
        text=text,
        locator="556 U.S. 662",
        authority_id="c1",
        colocation_id="c1",
    )
    second = _cite(
        "c2",
        FullCaseCitation(plaintiff="Ashcroft", defendant="Iqbal", volume="129", reporter=SCT, page="1937"),
        text=text,
        locator="129 S. Ct. 1937",
        authority_id="c2",
        colocation_id="c1",
    )
    other = CourtListenerOpinionCluster(
        cluster_id="c-other", case_name="Ashcroft v. Iqbal", date_filed="2009-05-18"
    )
    client = Client({("556", "U.S.", "662"): (IQBAL,), ("129", "S. Ct.", "1937"): (other,)})

    result = _run(_document(text, first, second), client)

    assert [r.citation_id for r in result.roots] == ["c1", "c2"]
    merge = next(n for n in result.record("c2").trace.nodes if isinstance(n, AuthorityMergeNode))
    assert merge.outcome is AuthorityMergeOutcome.KEPT


# --- the record and the artifact ------------------------------------------------


def test_a_correction_must_name_a_node_in_the_trace() -> None:
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2007)."
    record = CitationRecord.from_extracted(
        _cite("c1", _twombly(), text=text, locator="550 U.S. 544", authority_id="c1")
    )
    with pytest.raises(ValueError, match="not in the trace"):
        record.correct_field("court", "ca9", made_by="test", reason="", node_id="c1:nowhere")
    with pytest.raises(ValueError, match="must name the trace node"):
        Correction(field="court", before="a", after="b", made_by="test", reason="", node_id="")
    with pytest.raises(ValueError, match="must change the value"):
        Correction(field="court", before="a", after="a", made_by="test", reason="", node_id="n")
    assert record.citation == record.source.citation


def test_the_identified_document_round_trips_through_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_model(
        monkeypatch,
        {
            "case_name_read": "Bell Atl. Corp. v. Twombly",
            "case_name_agreement": "agree",
            "court_read": "scotus",
            "court_evidence": None,
            "court_basis": "implied_by_reporter",
            "date_read": "2009",
            "date_evidence": "2009",
            "verdict": "same_case",
            "reason": "Same case; the filing misdates it.",
        },
    )
    text = "Bell Atl. Corp. v. Twombly, 550 U.S. 544 (2009). Id. at 570. Ashcroft v. Iqbal, 556 U.S. 662, 129 S. Ct. 1937 (2009)."
    citations = (
        _cite(
            "c1",
            _twombly(court="ca9", date=CitationDate(year="2009")),
            text=text,
            locator="550 U.S. 544",
            authority_id="c1",
        ),
        _cite(
            "c2", IdCitation(pin_cite="at 570"), text=text, locator="Id.", authority_id="c1", resolves_to="c1"
        ),
        _cite(
            "c3",
            FullCaseCitation(plaintiff="Ashcroft", defendant="Iqbal", volume="556", reporter=US, page="662"),
            text=text,
            locator="556 U.S. 662",
            authority_id="c3",
            colocation_id="c3",
        ),
        _cite(
            "c4",
            FullCaseCitation(
                plaintiff="Ashcroft", defendant="Iqbal", volume="129", reporter=SCT, page="1937"
            ),
            text=text,
            locator="129 S. Ct. 1937",
            authority_id="c4",
            colocation_id="c3",
        ),
    )
    client = Client(
        {
            ("550", "U.S.", "544"): (TWOMBLY,),
            ("556", "U.S.", "662"): (IQBAL,),
            ("129", "S. Ct.", "1937"): (IQBAL,),
        },
        courts={"d1": "scotus"},
    )
    result = _run(_document(text, *citations), client, session=object())

    payload = json.loads(json.dumps(serialize_identified_document(result)))
    restored = deserialize_identified_document(payload)

    assert serialize_identified_document(restored) == payload
    assert restored.record("c1").citation.court == "scotus"
    assert restored.record("c1").source.citation.court == "ca9"
    assert restored.record("c1").corrections == result.record("c1").corrections
    assert restored.record("c4").authority_id == "c3"
    assert [type(n).__name__ for n in restored.record("c1").trace.nodes] == [
        type(n).__name__ for n in result.record("c1").trace.nodes
    ]
    assert restored.record("c1").resolution == result.record("c1").resolution
