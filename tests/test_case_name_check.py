"""Tests for comparing a written case name with the printed reporter's.

Every pair here is real: a case name a filing wrote, against the name the
Caselaw Access Project records at that citation.
"""

import pytest

from pathlib import Path

from mellea_lrc.caselaw import CapIndex, NameVerdict, check_case_name, compare_case_name


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


def test_a_name_matching_any_case_on_the_page_agrees(tmp_path: Path) -> None:
    """Several cases begin on one page, and the filing may mean any of them.

    A citation to `Ferdik v. Bonzelet, 963 F.2d 1258` was reported as naming a
    different case, because `United States v. Fine` also starts on that page
    and was compared first. Agreement with one of them is agreement.
    """
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("f2d", "963", Path(__file__).parent / "fixtures" / "cap" / "f2d-963-slice.json")

    finding = check_case_name(
        index,
        written_name="Ferdik v. Bonzelet",
        volume="963",
        reporter="F.2d",
        page="1258",
        known_reporters={"f2d"},
    )

    assert finding is not None
    assert finding.verdict is NameVerdict.AGREES
    assert finding.case.name == "Ferdik v. Bonzelet"


@pytest.mark.parametrize(
    ("written", "recorded"),
    [
        ("Miliken v. Meyer", "Milliken v. Meyer"),
        ("Matthews v. Eldridge", "Mathews v. Eldridge"),
        ("Coleman v. Maldnado", "Coleman v. Maldonado"),
        ("Bonner v. City of Pritchard", "Bonner v. City of Prichard"),
    ],
)
def test_a_one_letter_slip_is_not_a_different_case(written: str, recorded: str) -> None:
    """These are misspellings of famous case names, not citations to other cases.

    Reporting them buries the findings that matter under noise nobody will read
    past. One edit and no more: two is enough to turn one surname into another.
    """
    assert compare_case_name(written, recorded) is NameVerdict.AGREES


@pytest.mark.parametrize(
    ("written", "recorded"),
    [
        ("Danjaq, S.A. v. Pathe Commc'ns Corp.", "Danjaq, S.A. v. Pathe Communications Corp."),
        ("E. Shore Mkts., Inc. v. J.D. Assocs.", "Eastern Shore Markets, Inc. v. J.D. Associates"),
        ("AT&T Techs. v. Commc'ns Workers", "AT&T Technologies, Inc. v. Communications Workers"),
        ("Brunette Machine Works, Limited v. Kockum", "Brunette Machine Works, Ltd. v. Kockum"),
    ],
)
def test_a_contraction_is_never_a_disagreement(written: str, recorded: str) -> None:
    """`Commc'ns`, `Mkts.` and `Techs.` drop letters from the middle of a word.

    A prefix test cannot reach those, because the vowels are the first thing to
    go. Keeping the first letter and the letter order is how legal abbreviation
    actually works.
    """
    assert compare_case_name(written, recorded) is not NameVerdict.DISAGREES


def test_an_apostrophe_does_not_split_a_word_in_two() -> None:
    """`P'ship` is one word. Split, it becomes `P` and `ship`.

    `ship` is then four letters with no period, so it reads as spelled out and
    absent from `Partnership`, and the check reported a wrong case name for
    *Pioneer Investment Services Co. v. Brunswick Associates Ltd. Partnership*.
    Legal abbreviation is full of these -- `Ass'n`, `Int'l`, `Commc'ns`.
    """
    assert (
        compare_case_name(
            "Pioneer Inv. Servs. Co. v. Brunswick Assocs. Ltd. P'ship",
            "Pioneer Investment Services Co. v. Brunswick Associates Ltd. Partnership",
        )
        is NameVerdict.AGREES
    )


def test_the_whole_caption_is_compared_as_well_as_the_short_name(tmp_path: Path) -> None:
    """The archive's short name drops a relator; a filing may write one.

    `United States ex rel. Newsham v. Lockheed Missiles` is recorded short as
    `United States v. Lockheed Missiles & Space Co.`, which does not contain
    `Newsham` -- so comparing against the short name alone reads a correct
    citation as naming a different case. The full caption does contain it.
    """
    from mellea_lrc.caselaw.case_name_check import _best_verdict
    from mellea_lrc.caselaw.cap_index import CapCase

    case = CapCase(
        name="United States v. Lockheed Missiles & Space Co.",
        first_page=963,
        last_page=975,
        decision_date="1999-09-09",
        court="9th Cir.",
        citations=("190 F.3d 963",),
        full_name="UNITED STATES of America, ex rel. Margaret A. NEWSHAM v. LOCKHEED MISSILES & SPACE CO.",
    )

    assert _best_verdict("United States ex rel. Newsham v. Lockheed Missiles", case) is NameVerdict.AGREES
    assert _best_verdict("Cadle Co. v. Ayala", case) is NameVerdict.DISAGREES
