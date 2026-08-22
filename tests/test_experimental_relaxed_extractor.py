"""Tests for the experimental layout-tolerant eyecite extractor."""

from mellea_lrc.core.citations import FullCaseCitation, FullLawCitation, UnknownCitation
from mellea_lrc.experimental import extract_relaxed_citations
from mellea_lrc.extraction import ExtractedDocument, extract_from_plain_text


def _locators(document: ExtractedDocument | str) -> set[str]:
    if isinstance(document, str):
        document = extract_relaxed_citations(document)
    return {
        f"{c.citation.volume} {c.citation.reporter} {c.citation.page}"
        for c in document.citations
        if isinstance(c.citation, FullCaseCitation)
    }


def test_recovers_a_space_lost_between_reporter_and_page() -> None:
    """PDF table extraction drops the space; the baseline extractor sees nothing."""
    text = "Doe v. Colgate Univ. , 2016 WL1448829, at *2 (N.D.N.Y. Apr. 12, 2016)"
    assert _locators(extract_from_plain_text(text)) == set()
    assert "2016 WL 1448829" in _locators(extract_relaxed_citations(text))


def test_recovers_a_volume_split_from_its_reporter_by_a_page_break() -> None:
    text = "See also White v. McBride , 937\n\nS.W.2d  796,  800  (Tenn.  1996)"
    assert _locators(extract_from_plain_text(text)) == set()
    assert "937 S.W.2d 796" in _locators(extract_relaxed_citations(text))


def test_recovers_doubled_whitespace_without_rewriting_the_text() -> None:
    text = "Cracker Barrel Old  Country  Store,  Inc.  v.  Epperson ,  284  S.W.3d  303,  312"
    assert "284 S.W.3d 303" in _locators(extract_relaxed_citations(text))


def test_leaves_well_formed_citations_unchanged() -> None:
    text = "Norton v. Shelby County, 118 U.S. 425, 442 (1886)"
    assert _locators(extract_relaxed_citations(text)) == _locators(extract_from_plain_text(text))


def test_reporter_groups_are_not_left_with_absorbed_whitespace() -> None:
    """Relaxed separators let alternation branches ending in \\s* keep a space."""
    text = "United States v. Rucker , 188 Fed. Appx. 772, 778 (10th Cir. 2006)"
    reporters = {
        c.citation.reporter
        for c in extract_relaxed_citations(text).citations
        if isinstance(c.citation, FullCaseCitation)
    }
    assert reporters
    assert all(r == r.strip() for r in reporters if r)


def test_returns_a_plain_extracted_document_with_usable_spans() -> None:
    """No text is rewritten, so spans index directly into document.text."""
    text = "Doe v. Colgate Univ. , 2016 WL1448829, at *2 (N.D.N.Y. Apr. 12, 2016)"
    document = extract_relaxed_citations(text)
    assert isinstance(document, ExtractedDocument)
    citation = next(c for c in document.citations if isinstance(c.citation, FullCaseCitation))
    assert document.text[citation.locator_span.start : citation.locator_span.end] == "2016 WL1448829"
    assert document.text == extract_from_plain_text(text).text


def test_a_page_break_before_margin_line_numbers_no_longer_yields_a_wrong_page() -> None:
    """The reporter-to-page join stops at a block boundary.

    Relaxing that join to \\s* let PDF margin line numbers stand in for a page:
    this read as 214 F.3d 1 when the citation is 214 F.3d 1058. That is not a
    miss but a wrong page, which sends validation to a different case and
    reports a confident verdict about it -- the worst outcome available to an
    extractor, and worse than finding nothing.

    The volume-to-reporter join stays open, because a break there leaves the
    page adjacent to its own reporter. See the test above, which needs it.
    """
    text = "Advanced Textile , 214 F.3d\n\n1\n\n2\n\n3\n\n4"
    assert _locators(extract_relaxed_citations(text)) == set()


def _sections(text: str) -> set[str]:
    """Statute title and section, which the canonical form keeps in `volume` and `page`."""
    return {
        f"{c.citation.volume} U.S.C. § {c.citation.page}"
        for c in extract_relaxed_citations(text).citations
        if isinstance(c.citation, FullLawCitation)
    }


def test_a_statute_section_may_carry_a_letter_on_its_digits() -> None:
    """eyecite's section pattern allows digits, dots, dashes and colons only.

    A section written `2000e-2` or `1681g` therefore matches nothing at all --
    not a degraded parse but no citation, so the checker never sees it. Those
    two are Title VII and the Fair Credit Reporting Act, and between them with
    the Securities Acts and the Rehabilitation Act they account for 10 of the
    85 statute citations written in the 26 test filings and 116 of the 529 in
    the 109 sampled ones.
    """
    text = "brought under 42 U.S.C. § 2000e-2(a)(1), 15 U.S.C. § 1681g, 29 U.S.C. § 794a, and 15 U.S.C. § 77l"

    assert _sections(text) == {
        "42 U.S.C. § 2000e-2",
        "15 U.S.C. § 1681g",
        "29 U.S.C. § 794a",
        "15 U.S.C. § 77l",
    }
    # What the baseline leaves behind names the failure: four bare section
    # symbols typed as unknown, and not one law citation among them.
    baseline = [c.citation for c in extract_from_plain_text(text).citations]
    assert not any(isinstance(c, FullLawCitation) for c in baseline)
    assert all(isinstance(c, UnknownCitation) for c in baseline)


def test_the_ordinary_section_forms_still_parse_the_same_way() -> None:
    """Widening the digits must not change what already worked."""
    text = "under 42 U.S.C. § 1983, 28 U.S.C. § 636(b)(1)(A), and 42 U.S.C. § 12112"
    relaxed = _sections(text)

    assert relaxed == {"42 U.S.C. § 1983", "28 U.S.C. § 636", "42 U.S.C. § 12112"}
    assert relaxed == {
        f"{c.citation.volume} U.S.C. § {c.citation.page}"
        for c in extract_from_plain_text(text).citations
        if isinstance(c.citation, FullLawCitation)
    }


def test_a_section_does_not_absorb_the_word_that_follows_it() -> None:
    """The letter is optional and fixed to the digits, so prose stays outside.

    `1983 and` and `1983. Next` both have to end the section at `1983`; a
    pattern that let the letter float would take the `a` of `and`.
    """
    assert _sections("42 U.S.C. § 1983 and the rule") == {"42 U.S.C. § 1983"}
    assert _sections("42 U.S.C. § 1983. Next sentence") == {"42 U.S.C. § 1983"}


def test_a_statute_reporter_may_be_written_without_its_closing_period() -> None:
    """`42 U.S.C § 12132` and `29 U.S.C.A § 2612` are both written that way.

    eyecite requires the closing period on every reporter branch, so each of
    these matches nothing. A statute has a section symbol where a case has its
    page, so no boundary depends on that period.
    """
    assert _sections("on the basis of that disability. 42 U.S.C § 12132.") == {"42 U.S.C. § 12132"}
    assert _sections("leave pursuant to 29 U.S.C.A § 2612 (a)(1) for") == {"29 U.S.C. § 2612"}


def test_the_case_reporter_closing_period_is_still_required() -> None:
    """It is what separates the reporter from the page in `410 U.S. 113`.

    Making it optional for case citations would let the reporter run into the
    number after it, so the relaxation above is scoped to law patterns.
    """
    assert _locators("Roe v. Wade , 410 U.S 113 (1973)") == set()


def test_a_rule_number_is_no_longer_truncated_to_its_part() -> None:
    """eyecite reads `17 C.F.R. § 240.10b-5` as section 240, which is the whole part.

    Rule 10b-5 is the securities-fraud rule; part 240 is every rule under the
    Exchange Act. Checking the truncated form would check the wrong thing.
    """
    document = extract_relaxed_citations("SEC Rule 10b-5 (17 C.F.R. § 240.10b-5), and Section 21D")
    sections = {c.citation.page for c in document.citations if isinstance(c.citation, FullLawCitation)}

    assert sections == {"240.10b-5"}
    assert {c.citation.page for c in extract_from_plain_text("17 C.F.R. § 240.10b-5").citations} == {"240"}


def test_the_letter_suffix_misreads_a_scanned_digit_as_a_letter() -> None:
    """A cost of the widening, recorded rather than hidden.

    In a typewritten filing scanned into the sampled corpus, every digit 1 came
    out as a lowercase l: `18 U.S.C. S 20l(b)(l)` is section 201. eyecite finds
    nothing there; the widened pattern finds section `20l`, which is a section
    that does not exist. Four of the 53 letter-suffixed sections it recovers
    across the 109 sampled filings are this kind of damage, against 49 real
    ones -- so the widening is worth having, but a statute existence check must
    not report a letter-suffixed unknown section as fabricated. It cannot tell
    that case apart from this one.
    """
    assert _sections("violation of 18 U.S.C. S 20l(b)(l), is: fifteen years") == {"18 U.S.C. § 20l"}
    assert extract_from_plain_text("violation of 18 U.S.C. S 20l(b)(l), is").citations == ()
