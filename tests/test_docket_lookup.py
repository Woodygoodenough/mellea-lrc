"""A docket number with a court is a key, and two archives answer it."""

from __future__ import annotations

import json
from types import SimpleNamespace

from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.courtlistener.search_models import CourtListenerSearchResult
from mellea_lrc.govinfo import GovinfoCase, GovinfoClient, GovinfoConfig, GovinfoOpinion
from mellea_lrc.validation.docket_lookup import (
    docket_core,
    docket_number_matches,
    docket_parts,
    lookup_docket,
)


def test_the_year_and_sequence_name_the_case() -> None:
    assert docket_core("05-4206") == ("05", "4206")
    assert docket_core("2:05-cv-04206") == ("05", "4206")
    assert docket_core("No. 1:25-cv-05745-RPK") == ("25", "5745")
    assert docket_core("1:25cv-05745-RPK") == ("25", "5745")
    assert docket_core("13-02316") == ("13", "2316")
    assert docket_number_matches("05-4206", "2:05-cv-04206")
    assert docket_number_matches("1:19-CV-362", "1:19-cv-00362")
    assert not docket_number_matches("05-4206", "2:05-cv-04207")
    assert not docket_number_matches(None, "2:05-cv-04206")


def test_a_key_without_a_court_is_refused() -> None:
    record = lookup_docket(None, "05-4206", courtlistener=object(), govinfo=object())
    assert record.answers == ()
    assert record.caption is None


class Index:
    def __init__(self, rows=(), *, fail=False):
        self.rows = rows
        self.fail = fail
        self.calls = []

    def search(self, query, search_type, cursor=None, **kwargs):
        self.calls.append((query, search_type, kwargs.get("court")))
        if self.fail:
            raise CourtListenerError("CourtListener request failed with 429", failure_type="rate_limited")
        return CourtListenerSearchResult.from_payload(
            query=query,
            search_type=search_type,
            semantic=False,
            count=len(self.rows),
            results=list(self.rows),
            next_cursor=None,
            previous_cursor=None,
        )


class Office:
    def __init__(self, cases=()):
        self.cases = cases

    def find_case(self, court_code, docket_number):
        return self.cases


def test_both_archives_are_asked_and_the_courts_own_deposit_names_the_case_first() -> None:
    index = Index(
        (
            {
                "docket_id": 4271005,
                "docketNumber": "2:05-cv-04206",
                "caseName": "Turner v. Murphy Oil USA, Inc.",
                "dateFiled": "2005-09-09",
            },
        )
    )
    office = Office(
        (
            GovinfoCase(
                "USCOURTS-laed-2_05-cv-04206",
                "laed",
                "2:05-cv-04206",
                "Turner v. Murphy Oil USA, Inc.",
                "civil",
                "2011-01-03",
                (
                    GovinfoOpinion(
                        "USCOURTS-laed-2_05-cv-04206",
                        "USCOURTS-laed-2_05-cv-04206-0",
                        "Turner v. Murphy Oil USA, Inc.",
                        "2006-01-12",
                    ),
                ),
            ),
        )
    )
    record = lookup_docket("laed", "05-4206", courtlistener=index, govinfo=office)
    assert [a.archive for a in record.answers] == ["govinfo", "courtlistener"]
    assert all(a.status == "found" for a in record.answers)
    assert index.calls == [("docketNumber:(05-4206)", "d", "laed")]
    assert record.caption == "Turner v. Murphy Oil USA, Inc."
    assert record.decisions_on("2006-01-12")[0].identifier == "USCOURTS-laed-2_05-cv-04206-0"
    assert record.decisions_on("2006-07-13") == ()


def test_an_archive_that_does_not_answer_leaves_the_other_standing() -> None:
    record = lookup_docket("laed", "05-4206", courtlistener=Index(fail=True), govinfo=Office(()))
    assert [(a.archive, a.status) for a in record.answers] == [
        ("govinfo", "not_found"),
        ("courtlistener", "unavailable"),
    ]
    assert "429" in (record.answers[1].error or "")
    assert record.found == ()


def test_a_row_for_another_number_is_not_the_case() -> None:
    index = Index(
        (
            {
                "docket_id": 1,
                "docketNumber": "2:05-cv-04207",
                "caseName": "Other v. Case",
                "dateFiled": "2005-01-01",
            },
        )
    )
    record = lookup_docket("laed", "05-4206", courtlistener=index)
    assert record.answers[0].status == "not_found"
    assert record.answers[0].candidates == ("Other v. Case",)


class FakeSession:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url, params, json))
        body = self.answers[len(self.calls) - 1]
        return SimpleNamespace(status_code=200, json=lambda: body, text="")


def test_the_govinfo_client_finds_a_case_and_its_deposited_opinions() -> None:
    session = FakeSession(
        [
            {
                "count": 2,
                "results": [
                    {"packageId": "USCOURTS-laed-2_05-cv-04206", "title": "Turner"},
                    {"packageId": "USCOURTS-laed-2_05-cv-04206"},
                ],
            },
            {
                "title": "Turner v. Murphy Oil USA, Inc.",
                "caseNumber": "2:05-cv-04206",
                "courtCode": "laed",
                "caseType": "civil",
                "dateIssued": "2011-01-03",
            },
            {
                "count": 2,
                "granules": [
                    {"granuleId": "g-1", "title": "Turner", "dateIssued": "2006-01-30"},
                    {"granuleId": "g-0", "title": "Turner", "dateIssued": "2006-01-12"},
                ],
            },
        ]
    )
    client = GovinfoClient(GovinfoConfig(api_key="k", base_url="https://api.example.test/"), session=session)
    cases = client.find_case("laed", "No. 05-4206")
    assert session.calls[0][0] == "POST"
    assert session.calls[0][3]["query"] == "collection:USCOURTS AND casenumber:(05-4206) AND courtcode:(laed)"
    assert session.calls[0][2]["api_key"] == "k"
    assert len(cases) == 1
    assert cases[0].case_number == "2:05-cv-04206"
    assert [o.date_issued for o in cases[0].opinions] == ["2006-01-12", "2006-01-30"]
    assert client.requests == 3
    assert json.dumps(session.calls[0][3])


def test_a_civil_and_a_criminal_case_can_share_a_number() -> None:
    assert docket_parts("1:25-cv-05745-RPK") == ("25", "cv", "5745")
    assert docket_parts("No. 05-4206") == ("5", None, "4206")
    assert docket_core("No. 05-4206") == ("05", "4206")
    assert docket_parts("21-CV-01915-PAB-KAS") == ("21", "cv", "1915")
    assert not docket_number_matches("21-cv-01915", "21-cr-01915")
    assert not docket_number_matches("1:25-cv-05745", "1:25-cr-05745")
    # A filing that omits the kind has not said the case is something else.
    assert docket_number_matches("05-4206", "2:05-cv-04206")
    assert docket_number_matches("21-CV-01915", "21-CV-01915-PAB-KAS")
