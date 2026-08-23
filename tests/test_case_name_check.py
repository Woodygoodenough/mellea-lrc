"""Tests for comparing a written case name with the printed reporter's.

Every pair here is real: a case name a filing wrote, against the name the
Caselaw Access Project records at that citation.
"""

import pytest

from mellea_lrc.caselaw import NameVerdict, compare_case_name


@pytest.mark.parametrize(
    ("written", "recorded"),
    [
        ("Hoover v. Langston Equip. Assocs., Inc.", "Hoover v. Langston Equipment Associates, Inc."),
        ("Landis v. N. Am. Co.", "Landis v. North American Co."),
        ("Nationstar Mtge., LLC v. Kamil", "Nationstar Mortgage, LLC v. Kamil"),
        ("Doe v. George Washington Univ.", "Doe v. George Wash. Univ."),
        ("Austin v. Univ. of Oregon", "Austin v. Univ. of Or."),
        (
            "Precision Instrument Mfg. Co. v. Automotive",
            "Precision Instrument Manufacturing Co. v. Automotive",
        ),
    ],
)
def test_an_abbreviation_is_never_a_disagreement(written: str, recorded: str) -> None:
    """Citation abbreviates constantly, and in both directions.

    A filing writes `N. Am. Co.` where the reporter spells it out, and writes
    `George Washington Univ.` where the reporter abbreviates. A comparison with
    only two outcomes calls both of those a disagreement, and a checker built
    on it accuses a filing of miscitation for abbreviating a party name.
    """
    assert compare_case_name(written, recorded) is not NameVerdict.DISAGREES


@pytest.mark.parametrize(
    ("written", "recorded"),
    [
        ("Cadle Co. v. Ayala", "Ramirez v. City of New York"),
        ("Wells Fargo Bank, N.A. v. Enitan", "People v. Pagan"),
        ("Bank of Am., N.A. v. Gruff", "Bachvarov v. Lawrence Union Free School District"),
        ("United States v. Hoffman", "Villarreal v. R.J. Reynolds Tobacco Co."),
        ("Schum v. Bailey", "Laminators Safety Glass Ass'n v. Consumer Product Safety Comm'n"),
    ],
)
def test_a_spelled_out_word_that_is_absent_is_evidence(written: str, recorded: str) -> None:
    """`Cadle` and `Ayala` are not in `Ramirez v. City of New York`.

    No abbreviation rule reaches across that, so this is the citation naming a
    different case than the one printed at the page. Three independent sources
    agree on that particular one -- this archive, CourtListener, and the New
    York official reports.
    """
    assert compare_case_name(written, recorded) is NameVerdict.DISAGREES


def test_a_matching_name_agrees() -> None:
    assert compare_case_name("Brady v. United States", "Brady v. United States") is NameVerdict.AGREES


def test_one_party_matching_is_not_agreement() -> None:
    """Half a case name matches many cases.

    `United States v. ...` fills whole pages of unpublished decisions, so a
    filing naming only that party has not identified anything, and a match on
    it is not agreement.
    """
    assert compare_case_name("United States", "United States v. Melton") is NameVerdict.UNDECIDED


def test_a_one_party_name_can_still_disagree() -> None:
    """`In re Marcus` at a page the reporter gives to `United States v. Melton`.

    Only one party is named, so this can never reach agreement -- but `Marcus`
    is spelled out and absent, and no abbreviation rule reaches across that.
    Declining to look because a short form names one party would discard a real
    finding; this one is in the test filings.
    """
    assert compare_case_name("In re Marcus", "United States v. Melton") is NameVerdict.DISAGREES


def test_a_name_of_only_abbreviations_decides_nothing() -> None:
    """`CFTC` does not begin `Commodity Futures Trading Commission`.

    An acronym that fails to match is a limit of the comparison, not a finding
    about the filing, so the answer has to be that nothing was established.
    """
    assert (
        compare_case_name("CFTC v. Am. Metals", "Commodity Futures Trading Commission v. Metals")
        is NameVerdict.UNDECIDED
    )
    assert (
        compare_case_name("Karim-Panahi v. LAPD", "Karim-Panahi v. Los Angeles Police Department")
        is NameVerdict.UNDECIDED
    )


def test_an_empty_name_decides_nothing() -> None:
    assert compare_case_name(None, "Brady v. United States") is NameVerdict.UNDECIDED
    assert compare_case_name("Brady v. United States", None) is NameVerdict.UNDECIDED
