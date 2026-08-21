"""Tests for measuring extraction coverage against LePhantomCite citation strings."""

from __future__ import annotations

from evaluations.lephantomcite.dataset import Excerpt, LabelledCitation
from evaluations.lephantomcite.extraction_coverage import identifiers, measure


def _excerpt(text: str, cited: list[str], excerpt_id: str = "a.pdf:0") -> Excerpt:
    return Excerpt(
        excerpt_id=excerpt_id,
        filename="a.pdf",
        text=text,
        citations=tuple(
            LabelledCitation(cited_text=item, locator_key=None, types=frozenset()) for item in cited
        ),
    )


def test_identifiers_are_comparable_across_spellings() -> None:
    """Two renderings of one reporter must reduce to one identifier."""
    spaced = identifiers("See Doe v. Roe, 798 F. Supp. 2d 1215 (D. Ariz. 2011).")
    tight = identifiers("See Doe v. Roe, 798 F.Supp.2d 1215 (D. Ariz. 2011).")

    assert spaced == tight == {"798|fsupp2d|1215"}


def test_short_forms_count_as_recoverable_citations() -> None:
    """The benchmark states short forms, so a system must find them to score."""
    found = identifiers("Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009). Later, 556 U.S. at 679.")

    assert "556|us|662" in found
    assert "556|us|679" in found


def test_measure_counts_recovery_against_the_stated_citations() -> None:
    """Recall is over the identifiers the benchmark says are in the excerpt."""
    report = measure(
        [
            _excerpt(
                "The rule comes from Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009).",
                ["556 U.S. 662, 678 (2009)"],
            )
        ]
    )

    assert report.gold_identifiers == 1
    assert report.recovered == 1
    assert report.recall == 1.0
    assert report.fully_recovered_excerpts == 1
    assert report.missed == ()


def test_a_gold_string_naming_no_real_citation_is_reported_as_missed() -> None:
    """One eval row states a truncated duplicate of a citation it also states.

    `25 F. App'x at 541` sits beside the correct `425 F. App'x at 541` in the
    released data. Extraction is right to find only the second, so the miss is
    counted and named rather than normalized away -- a coverage number that
    quietly drops rows it dislikes is not a coverage number.
    """
    report = measure(
        [
            _excerpt(
                "Nozzi v. Hous. Auth., 425 F. App'x 539 (9th Cir. 2011). See 425 F. App'x at 541.",
                ["425 F. App'x 539 (9th Cir. 2011)", "425 F. App'x at 541", "25 F. App'x at 541"],
            )
        ]
    )

    assert report.recovered == report.gold_identifiers - 1
    assert [identifier for _, identifier in report.missed] == ["25|fappx|541"]
