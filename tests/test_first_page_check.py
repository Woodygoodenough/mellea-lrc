"""Tests for reporting a wrong first page without firing on short forms.

The archive slice is real: `Chevron U.S.A. Inc. v. NRDC` occupies pages 837 to
866 of volume 467 of the United States Reports.
"""

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mellea_lrc.caselaw import CapIndex, LaterReferenceEvidence, check_first_pages
from mellea_lrc.experimental.relaxed_eyecite_extractor import extract_relaxed_citations

_FIXTURES = Path(__file__).parent / "fixtures" / "cap"
_KNOWN = {"us", "f2d", "f3d"}


def _findings(text: str, tmp_path: Path):
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("us", "467", _FIXTURES / "us-467-slice.json")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        document = extract_relaxed_citations(text)
    return check_first_pages(document, index, known_reporters=_KNOWN)


def test_a_short_form_written_without_at_is_not_a_defect(tmp_path: Path) -> None:
    """`Chevron, 467 U.S. 842-43` is a pin cite into a case introduced earlier.

    Written `467 U.S. at 842` eyecite types it as a short form and nothing
    mistakes it for a locator. Written without the `at`, which is common, it
    parses as a full citation, the archive correctly reports a mid-case page,
    and a checker reading that as a defect accuses a brief of miscitation for
    citing a case perfectly well.
    """
    (finding,) = _findings("As held in *Chevron*, 467 U.S. 842-43, the agency may.", tmp_path)

    assert finding.case.name.startswith("Chevron")
    assert not finding.is_defect
    assert finding.later_reference is LaterReferenceEvidence.NOT_SHAPED_LIKE_A_FULL_CITATION


def test_the_document_citing_the_case_correctly_settles_it(tmp_path: Path) -> None:
    """The strongest evidence, and it needs no judgement at all.

    If some other citation in the same document names the case at the page it
    actually starts on, this one is a later reference to it.
    """
    text = (
        "Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837, 842 (1984) sets the rule. "
        "Applying Chevron U.S.A. Inc. v. NRDC, 467 U.S. 842 (1984), the agency prevails."
    )

    findings = _findings(text, tmp_path)

    assert findings
    assert all(not f.is_defect for f in findings)
    assert LaterReferenceEvidence.CITED_CORRECTLY_ELSEWHERE in {f.later_reference for f in findings}


def test_a_full_citation_with_a_wrong_first_page_is_reported(tmp_path: Path) -> None:
    """Both parties, a year, a name that agrees, and the page is simply wrong.

    This is the shape of the seven real errors the annotated corpus contains
    and no annotator marked, among them `Brady v. United States, 397 U.S. 757`
    where the case starts at 742.
    """
    (finding,) = _findings("See Hishon v. King & Spalding, 467 U.S. 72 (1984).", tmp_path)

    assert finding.is_defect
    assert finding.name_agrees
    assert finding.pages_early == 3
    assert finding.case.first_page == 69


def test_a_disagreeing_name_is_not_reported_as_a_wrong_page(tmp_path: Path) -> None:
    """The citation names one case and the page belongs to another.

    That is a wrong *name*, reported by a different check, and this one cannot
    tell which of the two is wrong. On the annotated corpus it is most of the
    volume: 94 of 109 mid-case citations have a disagreeing name, and every
    label on them is a name mismatch.
    """
    (finding,) = _findings("See Smith v. Jones, 467 U.S. 72 (1984).", tmp_path)

    assert not finding.name_agrees
    assert not finding.is_defect


def test_a_government_party_alone_does_not_establish_the_name(tmp_path: Path) -> None:
    """`United States v. Lo` reduces to `united` and `states`.

    A two-letter surname carries no distinctive word, and those two appear in
    every `United States v. ...` on a page of them -- which is how a looser
    rule matched one against a different case entirely and reported a wrong
    first page for it. Each party has to contribute.
    """
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("us", "467", _FIXTURES / "us-467-slice.json")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        document = extract_relaxed_citations("See United States v. Lo, 467 U.S. 842 (1984).")

    for finding in check_first_pages(document, index, known_reporters=_KNOWN):
        assert not finding.name_agrees
        assert not finding.is_defect


def test_a_page_that_starts_a_case_produces_no_finding(tmp_path: Path) -> None:
    assert _findings("Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837 (1984).", tmp_path) == ()
