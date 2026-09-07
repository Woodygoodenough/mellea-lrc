"""The citing side: window, string cites, signals and quotations."""

from __future__ import annotations

from mellea_lrc.core.citations import FullCaseCitation, Reporter
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction.types import ExtractedCitation
from mellea_lrc.validation.pinpoint.citing import citing_window, read_signal, string_members

TEXT = (
    "The Court must accept as true all well-pleaded factual allegations. "
    "Dismissal is appropriate only where there is a lack of a cognizable legal theory. "
    "See Iqbal, 556 U.S. 662, 678; Twombly, 550 U.S. 544, 555; Navarro v. Block, 250 F.3d 729, 732 (9th Cir. 2001).\n\n"
    'A complaint must contain "enough facts to state a claim to relief that is plausible on its face." '
    'Twombly, 550 U.S. at 570 (holding that "labels and conclusions" do not suffice).'
)


def _citation(citation_id: str, text: str, locator: str) -> ExtractedCitation:
    start = TEXT.index(text)
    lstart = TEXT.index(locator, start)
    return ExtractedCitation(
        citation_id=citation_id,
        full_span=Span(start, start + len(text)),
        locator_span=Span(lstart, lstart + len(locator)),
        matched_text=locator,
        citation=FullCaseCitation(
            volume="1",
            reporter=Reporter(
                as_written="U.S.",
                short_name="U.S.",
                name="",
                cite_type="federal",
                is_scotus=True,
                editions=(),
            ),
            page="1",
        ),
    )


IQBAL = _citation("a", "Iqbal, 556 U.S. 662, 678", "556 U.S. 662")
TWOMBLY = _citation("b", "Twombly, 550 U.S. 544, 555", "550 U.S. 544")
NAVARRO = _citation("c", "Navarro v. Block, 250 F.3d 729, 732 (9th Cir. 2001)", "250 F.3d 729")
SHORT = _citation(
    "d", 'Twombly, 550 U.S. at 570 (holding that "labels and conclusions" do not suffice)', "550 U.S. at 570"
)
ALL = (IQBAL, TWOMBLY, NAVARRO, SHORT)


def test_string_members_are_found_in_both_directions() -> None:
    assert string_members(TWOMBLY, ALL, TEXT) == ("a", "c")
    assert string_members(IQBAL, ALL, TEXT) == ("b", "c")
    assert string_members(SHORT, ALL, TEXT) == ()


def test_the_signal_ahead_of_a_string_is_read_for_its_first_member_only_by_position() -> None:
    assert read_signal(TEXT, IQBAL.full_span.start) == "see"
    assert read_signal(TEXT, SHORT.full_span.start) is None
    sentence = "as the court held. See also Smith, 1 U.S. 1"
    assert read_signal(sentence, sentence.index("Smith")) == "see_also"
    assert read_signal("as the court held. Cf. Smith", len("as the court held. Cf. ")) == "cf"


def test_the_window_marks_the_target_and_stops_at_the_paragraph() -> None:
    window = citing_window(TWOMBLY, ALL, TEXT)
    assert (
        "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}Twombly, 550 U.S. 544, 555\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}"
        in window.marked
    )
    assert window.text.startswith("The Court must accept")
    assert "plausible on its face" not in window.text
    assert window.string_members == ("a", "c")


def test_quotations_in_the_sentence_and_the_parenthetical_are_lifted() -> None:
    window = citing_window(SHORT, ALL, TEXT)
    texts = [q.text for q in window.quotations]
    assert texts == [
        "enough facts to state a claim to relief that is plausible on its face.",
        "labels and conclusions",
    ]
    assert [q.in_parenthetical for q in window.quotations] == [False, True]
    for quotation in window.quotations:
        assert TEXT[quotation.span.start : quotation.span.end] == quotation.text


def test_single_quoted_quotations_are_lifted_without_breaking_on_apostrophes() -> None:
    text = (
        "The court held that 'baseless and speculative attacks on opposing counsel's conduct do not "
        "substitute for legal argument.' Sibley v. Choice, 304 F.R.D. 125, 129 (E.D.N.Y. 2015)."
    )
    start = text.index("Sibley")
    citation = ExtractedCitation(
        citation_id="s",
        full_span=Span(start, len(text) - 1),
        locator_span=Span(text.index("304"), text.index("304") + 12),
        matched_text="304 F.R.D. 125",
        citation=FullCaseCitation(
            volume="304",
            reporter=Reporter(as_written="F.R.D.", short_name="F.R.D.", name="", cite_type="federal"),
            page="125",
        ),
    )
    window = citing_window(citation, (citation,), text)
    assert [q.text for q in window.quotations] == [
        "baseless and speculative attacks on opposing counsel's conduct do not substitute for legal argument."
    ]


def _one(text: str, cited: str, locator: str, page: str) -> tuple[ExtractedCitation, str]:
    start = text.index(cited)
    citation = ExtractedCitation(
        citation_id="x",
        full_span=Span(start, start + len(cited)),
        locator_span=Span(text.index(locator), text.index(locator) + len(locator)),
        matched_text=locator,
        citation=FullCaseCitation(
            volume="1",
            reporter=Reporter(
                as_written="U.S.", short_name="U.S.", name="", cite_type="federal", is_scotus=True
            ),
            page=page,
        ),
    )
    return citation, text


def test_the_quoted_sentence_the_citation_follows_is_not_a_sentence_break() -> None:
    text = (
        "Earlier point. The Supreme Court has made clear that the test is not rigid, but 'at bottom an "
        "equitable one, taking account of all relevant circumstances.' See Pioneer Inv. Servs. Co. v. "
        "Brunswick Assocs., 507 U.S. 380, 395 (1993). The next sentence."
    )
    citation, text = _one(
        text, "Pioneer Inv. Servs. Co. v. Brunswick Assocs., 507 U.S. 380, 395 (1993)", "507 U.S. 380", "380"
    )
    window = citing_window(citation, (citation,), text)
    assert [q.text for q in window.quotations] == [
        "at bottom an equitable one, taking account of all relevant circumstances."
    ]


def test_a_quotation_after_the_citation_in_the_same_sentence_belongs_to_it() -> None:
    text = (
        "Earlier point. In Ahanchian v. Xenon Pictures, Inc., 624 F.3d 1253, 1261 (9th Cir. 2010), the "
        "Ninth Circuit stated that 'we disapprove the overly rigid application of the standard.' Later "
        "sentence with 'another quotation entirely' in it."
    )
    citation, text = _one(
        text,
        "Ahanchian v. Xenon Pictures, Inc., 624 F.3d 1253, 1261 (9th Cir. 2010)",
        "624 F.3d 1253",
        "1253",
    )
    window = citing_window(citation, (citation,), text)
    assert [q.text for q in window.quotations] == [
        "we disapprove the overly rigid application of the standard."
    ]
