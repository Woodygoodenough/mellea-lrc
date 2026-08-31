"""Tests for reading which docket entry an order blames for bad citations.

Every string here is quoted from a real order in the harvest, named in the
test that uses it, so a change that breaks one is a change against real court
prose rather than against an invented example.
"""

from scripts.miner.resolve import _ATTRIBUTION, accused_entries, docket_references


def test_an_ellipsis_inside_a_quotation_does_not_end_the_sentence() -> None:
    """Courts quote each other constantly, and a quotation drops text with `...`.

    This is from Hilts v. Bellevue Womans Center. The entry number and the
    finding that the case does not exist are one sentence, but the ellipsis
    split them into separate fragments, so the accusation reached no entry and
    a genuine finding read as no finding at all.
    """
    order = (
        'The case is cited for the proposition that the Fifth Circuit "allowed a private '
        'cause of action under the [Patient Self-Determination Act]." (Dkt. No. 75, at 14; '
        'see Dkt. No. 81, at 8 (Defendants explaining that "[u]pon thorough review ... no '
        'such case exists")).'
    )

    assert accused_entries(order) == (75, 81)


def test_a_unicode_hyphen_still_reads_as_an_accusation() -> None:
    """From Randolph v. Erick Berscheid Trucking, which uses U+2010, not a plain hyphen.

    A court PDF does not have to use ASCII. With the hyphen taken literally
    this sentence carried no accusation vocabulary at all, so the order read as
    saying nothing.
    """
    finding = "Randolph's motions contain citations to non‐existent cases"

    assert _ATTRIBUTION.search(finding) is not None
    assert _ATTRIBUTION.search(finding.replace("‐", "-")) is not None
    assert _ATTRIBUTION.search(finding.replace("‐", "")) is not None


def test_a_space_is_not_a_hyphen() -> None:
    """`non existent` is prose about existence, not the fixed phrase."""
    assert _ATTRIBUTION.search("the parties do non existent things") is None


def test_an_entry_named_without_an_accusation_is_reported_unaccused() -> None:
    """Not every entry an order mentions is an entry it complains about."""
    order = "Plaintiff responded to the motion. See Dkt. No. 12."

    (reference,) = docket_references(order)

    assert reference.entry_number == 12
    assert not reference.accused
    assert accused_entries(order) == ()


def test_an_accusation_naming_no_entry_resolves_to_nothing() -> None:
    """Also from Randolph: the order names the filings by party, not by number.

    Declining is correct here. Attaching the accusation to some other entry the
    order happens to mention would blame the wrong filing, and recovering this
    one needs the docket listing rather than the order's own text.
    """
    order = (
        "Because Randolph failed to obtain prior permission, his motions are unauthorized "
        "and are therefore denied. The Court notes that Randolph's motions contain "
        "citations to non‐existent cases as well as quotes that do not appear in the "
        "cited case. See Dkt. 33."
    )

    assert accused_entries(order, exclude=33) == ()
