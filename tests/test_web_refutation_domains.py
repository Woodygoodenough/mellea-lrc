"""Tests for which websites may be evidence about a citation, and for what."""

import pytest

from mellea_lrc.experimental.web_refutation import TrustTier, authority_for, may_refute, rank, tier_of


@pytest.mark.parametrize(
    ("url", "tier"),
    [
        ("https://www.supremecourt.gov/opinions/23pdf/22-1.pdf", TrustTier.COURT),
        ("https://www.ca9.uscourts.gov/opinions/", TrustTier.COURT),
        ("https://www.nycourts.gov/reporter/3dseries/2020/2020_03123.htm", TrustTier.COURT),
        ("https://www.govinfo.gov/app/details/USCOURTS-ca9-19-55376", TrustTier.GOVERNMENT),
        ("https://www.law.cornell.edu/supremecourt/text/384/436", TrustTier.ARCHIVE),
        ("https://case.law/caselaw/", TrustTier.ARCHIVE),
        ("https://law.justia.com/cases/federal/appellate-courts/", TrustTier.COMMERCIAL),
        ("https://somefirm.example.com/blog/top-10-cases", TrustTier.UNTRUSTED),
    ],
)
def test_a_host_earns_the_tier_of_whoever_publishes_it(url: str, tier: TrustTier) -> None:
    assert tier_of(url)[1] is tier


def test_a_court_is_authoritative_only_about_its_own_decisions() -> None:
    """The Ninth Circuit's silence about a New York case is not evidence.

    Trust is not a property of the hostname. A court's own site is the record
    for what it decided and says nothing about anybody else's docket, so the
    jurisdiction is checked rather than assumed.
    """
    federal = authority_for("https://www.ca9.uscourts.gov/opinions/x.pdf", court_id="ca9")
    new_york = authority_for("https://www.ca9.uscourts.gov/opinions/x.pdf", court_id="nyappdiv")

    assert federal.publishes_this_court
    assert may_refute(federal)
    assert not new_york.publishes_this_court
    assert not may_refute(new_york)


def test_a_citation_with_no_court_cannot_be_refuted_by_a_courts_own_site() -> None:
    """A citation written without a parenthetical carries no court.

    That is common, and it means the jurisdiction cannot be checked at all --
    so no court's site counts as publishing it, and the honest answer is that
    this route has nothing to say.
    """
    anywhere = authority_for("https://www.supremecourt.gov/opinions/x.pdf", court_id=None)

    assert not anywhere.publishes_this_court
    assert not may_refute(anywhere)


def test_a_commercial_publisher_may_not_refute() -> None:
    """Several now carry generated summaries beside transcribed text.

    A result page does not say which one it is, and a refutation has to be
    something a publisher can be held to.
    """
    justia = authority_for("https://law.justia.com/cases/x.html", court_id="scotus")

    assert justia.is_trusted
    assert not may_refute(justia)


def test_an_untrusted_host_is_dropped_rather_than_ranked_last() -> None:
    """Keeping it in the list invites reading it when nothing better appears.

    That is exactly the situation the tiers exist to prevent, so the ranking
    removes it instead of ordering it.
    """
    ranked = rank(
        [
            "https://blog.example.com/case-summaries",
            "https://law.justia.com/cases/x.html",
            "https://www.supremecourt.gov/opinions/x.pdf",
        ],
        court_id="scotus",
    )

    assert [host for _, a in ranked for host in (a.host,)] == ["supremecourt.gov", "law.justia.com"]
