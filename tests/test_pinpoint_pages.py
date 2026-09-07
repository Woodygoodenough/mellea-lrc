"""Cutting the cited page along the reporter's own pagination."""

from __future__ import annotations

from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinion, CourtListenerOpinionClusterCitation
from mellea_lrc.validation.pinpoint.pages import citation_index, cut_page, paginate, pin_pages

HTML = (
    "<p>Opening words of the opinion.</p>"
    '<span class="star-pagination" citation-index="1" label="544">*544</span>'
    '<span class="star-pagination" citation-index="2" label="1955">*1955</span>'
    "<p>Page five forty-four says the pleading standard is plausibility.</p>"
    '<span class="star-pagination" citation-index="2" label="1956">*1956</span>'
    "<p>Still on page five forty-four in the U.S. Reports.</p>"
    '<span class="star-pagination" citation-index="1" label="545">*545</span>'
    "<p>Page five forty-five begins the facts.</p>"
    '<span class="star-pagination" citation-index="1" label="546">*546</span>'
    "<p>Page five forty-six ends the opinion.</p>"
)


def _opinion() -> CourtListenerOpinion:
    return CourtListenerOpinion(
        opinion_id="1", cluster_id="9", opinion_type="010combined", html_with_citations=HTML
    )


def test_a_page_runs_from_its_marker_to_the_next_marker_of_the_same_reporter() -> None:
    paginated = paginate(_opinion())
    page = cut_page(paginated, "1", ("544",))
    assert page is not None
    assert page.text.startswith("Page five forty-four")
    assert "Still on page five forty-four" in page.text
    assert "Page five forty-five" not in page.text
    assert page.before.strip().endswith("Opening words of the opinion.")
    assert page.after.startswith("Page five forty-five")


def test_the_parallel_reporter_turns_its_pages_elsewhere() -> None:
    paginated = paginate(_opinion())
    page = cut_page(paginated, "2", ("1955",))
    assert page is not None
    assert "plausibility" in page.text
    assert "Still on page" not in page.text
    assert paginated.label_at(paginated.text.index("Still on page"), "2") == "1956"
    assert paginated.label_at(paginated.text.index("Still on page"), "1") == "544"


def test_a_range_is_cut_as_one_run_with_its_turns_marked() -> None:
    page = cut_page(paginate(_opinion()), "1", ("544", "545"))
    assert page is not None
    assert page.labels == ("544", "545")
    assert "[*545]" in page.text
    assert "Page five forty-six" not in page.text


def test_a_page_the_opinion_does_not_mark_is_none() -> None:
    assert cut_page(paginate(_opinion()), "1", ("999",)) is None


def test_pin_forms() -> None:
    assert pin_pages("570").labels == ("570",)
    assert pin_pages("180-81").labels == ("180", "181")
    assert pin_pages("588-90").labels == ("588", "589", "590")
    assert pin_pages("1072 -73").labels == ("1072", "1073")
    assert pin_pages("912-913").labels == ("912", "913")
    assert pin_pages("100-200").labels == ("100", "101", "102", "103")
    assert pin_pages("657 n.1") == ("657",) or pin_pages("657 n.1").form == "footnote"
    assert pin_pages("*3").form == "star"
    assert pin_pages("¶ 26").form == "paragraph"
    assert pin_pages("§ 1231(g)(1)").form == "section"
    assert pin_pages(None).labels == ()


def test_the_filing_reporter_is_found_among_the_cluster_citations() -> None:
    citations = (
        CourtListenerOpinionClusterCitation("550", "U.S.", "544"),
        CourtListenerOpinionClusterCitation("127", "S. Ct.", "1955"),
    )
    assert citation_index(citations, volume="550", reporter="U.S.") == "1"
    assert citation_index(citations, volume="127", reporter="S.Ct.") == "2"
    assert citation_index(citations, volume="1", reporter="F.3d") is None


def test_a_page_before_the_first_marker_is_the_unmarked_head() -> None:
    html = (
        "<p>Pages five sixty-five to five sixty-seven carry no marker. " + "Text of the head. " * 110 + "</p>"
        '<span class="star-pagination" citation-index="1" label="568">*568</span>'
        "<p>Page five sixty-eight is marked.</p>"
    )
    paginated = paginate(
        CourtListenerOpinion(
            opinion_id="k", cluster_id=None, opinion_type="010combined", html_with_citations=html
        )
    )
    page = cut_page(paginated, "1", ("567",), first_page="565")
    assert page is not None
    assert page.labels == ("565", "566", "567")
    assert page.text.startswith("Pages five sixty-five")
    assert "marked" not in page.text.replace("no marker", "")
    assert cut_page(paginated, "1", ("567",)) is None


def test_the_marker_index_is_read_from_the_numbers_not_the_citation_list() -> None:
    from mellea_lrc.validation.pinpoint.pages import marker_index_for

    html = (
        '<span class="star-pagination" citation-index="1" label="168">*168</span>a'
        '<span class="star-pagination" citation-index="2" label="1255">*1255</span>b'
        '<span class="star-pagination" citation-index="2" label="1261">*1261</span>c'
    )
    paginated = paginate(
        CourtListenerOpinion(
            opinion_id="a", cluster_id=None, opinion_type="010combined", html_with_citations=html
        )
    )
    assert marker_index_for((paginated,), "1253", ("1261",)) == "2"
    assert marker_index_for((paginated,), "166", ("168",)) == "1"
    assert marker_index_for((paginated,), "1253", ("1254",)) == "2"
    assert marker_index_for((paginated,), "900", ("905",)) is None


def test_a_page_too_short_to_be_a_page_is_not_retrieved() -> None:
    from mellea_lrc.validation.pinpoint.stage import MIN_PAGE_CHARS

    assert MIN_PAGE_CHARS == 100


def test_a_head_too_short_to_be_the_pages_before_the_first_marker_is_not_those_pages() -> None:
    html = (
        "<p>MEMORANDUM OPINION. Taxation without representation is tyranny.</p>"
        '<span class="star-pagination" citation-index="1" label="1092">*1092</span>'
        "<p>Page one thousand ninety-two.</p>"
    )
    paginated = paginate(
        CourtListenerOpinion(
            opinion_id="b", cluster_id=None, opinion_type="010combined", html_with_citations=html
        )
    )
    assert cut_page(paginated, "1", ("1091",), first_page="1087") is None
