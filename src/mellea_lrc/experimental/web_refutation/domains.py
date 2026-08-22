"""Which websites may be treated as evidence about a case citation, and for what.

The project's central commitment is that not finding a case is never evidence
that the case was invented, because the free record is incomplete. Searching
the open web threatens that commitment from the other side: the web is not
incomplete, it is *contaminated*. Since 2023 it carries AI-written summaries of
cases, and a fabricated citation that a court has already sanctioned somebody
for will itself be quoted on dozens of pages discussing the sanction. A page
that mentions a citation is therefore not evidence the citation is real.

So the rule here is an asymmetry, and every function in this module exists to
enforce it:

* **The web may never confirm a citation.** No tier, no domain, no exception.
* **The web may refute one**, and only in one specific way: a source that
  authoritatively publishes a court's decisions gives that case name a
  *different* reporter citation than the filing did.

Refutation from an authoritative source is sound where confirmation from an
unknown source is not, because the failure modes are not symmetric. To wrongly
confirm, a page need only repeat what the filing said -- which is exactly what
a page about a fabricated-citation sanction does. To wrongly refute, an
authoritative publisher would have to misstate the citation of a decision it
published itself.

Trust is not a property of a domain alone. A court's website is authoritative
for **its own** decisions and says nothing about anybody else's: the Ninth
Circuit publishes Ninth Circuit opinions, and its silence about a New York
case means nothing at all. :func:`authority_for` is where that scoping lives,
and it is the part that carries actual domain knowledge rather than a list of
reputable-sounding hostnames.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from urllib.parse import urlsplit

__all__ = [
    "Authority",
    "DomainRule",
    "TrustTier",
    "WebEvidence",
    "authority_for",
    "may_refute",
    "tier_of",
]


class TrustTier(IntEnum):
    """How close a publisher is to the court whose decision is in question.

    Ordered so that a lower number is closer to the source. The ordering is
    used for ranking search results, never for deciding that a citation is
    real -- see the module docstring.
    """

    COURT = 1
    """The deciding court publishing its own decision. A slip opinion on the
    court's own site is the record itself, not a report of it."""

    GOVERNMENT = 2
    """Another arm of government republishing the official text -- the
    Government Publishing Office, the Library of Congress, a state's official
    reporter. One step from the court, with an accountable publisher."""

    ARCHIVE = 3
    """An established archive that transcribes official text and is not selling
    anything: Cornell's Legal Information Institute, the Caselaw Access
    Project, CourtListener itself."""

    COMMERCIAL = 4
    """A commercial legal publisher. Long-established and usually accurate, but
    several now carry generated summaries alongside the transcribed text, and a
    page cannot be assumed to be one rather than the other."""

    UNTRUSTED = 99
    """Everything else, including every blog, forum, news site and law-firm
    marketing page. Not evidence in either direction."""


@dataclass(frozen=True, slots=True)
class DomainRule:
    """One host pattern, the tier it earns, and what it is authoritative about."""

    pattern: re.Pattern[str]
    tier: TrustTier
    courts: re.Pattern[str] | None
    """CourtListener court identifiers this host authoritatively publishes.

    ``None`` means the host publishes across jurisdictions, which is true of a
    national archive and false of a single court.
    """
    note: str


def _host(pattern: str) -> re.Pattern[str]:
    """Match a host exactly or as a subdomain of it."""
    return re.compile(rf"(?:^|\.){re.escape(pattern)}$", re.IGNORECASE)


# CourtListener court identifiers, which are what the pipeline already carries
# on a citation. `scotus` is the Supreme Court; `ca1`..`ca11`, `cadc` and
# `cafc` are the courts of appeals; a district court is a state abbreviation
# plus a position, like `nysd` or `cand`; state appellate courts have their own
# identifiers such as `nyappdiv` and `calctapp`.
_FEDERAL_APPELLATE = re.compile(r"^(ca\d{1,2}|cadc|cafc)$")
_FEDERAL_ANY = re.compile(r"^(scotus|ca\d{1,2}|cadc|cafc|[a-z]{2}[ncsewmd]?d|.*bankr.*|uscfc|cit|tax)$")
_NEW_YORK = re.compile(r"^ny(app|sup|city|county|misc|ct)?")
_CALIFORNIA = re.compile(r"^cal")

# Ordered most specific first; the first match wins.
DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        _host("supremecourt.gov"),
        TrustTier.COURT,
        re.compile(r"^scotus$"),
        "The Supreme Court's own slip opinions and bound volumes.",
    ),
    DomainRule(
        _host("uscourts.gov"),
        TrustTier.COURT,
        _FEDERAL_ANY,
        "A federal court's own site. Each subdomain is one court, and this rule "
        "is deliberately broader than that: the host is trusted, and whether "
        "the specific court matches is checked by authority_for.",
    ),
    DomainRule(
        _host("govinfo.gov"),
        TrustTier.GOVERNMENT,
        _FEDERAL_ANY,
        "The Government Publishing Office. Its United States Courts Opinions "
        "collection is deposited by the courts themselves.",
    ),
    DomainRule(_host("gpo.gov"), TrustTier.GOVERNMENT, _FEDERAL_ANY, "The GPO's older host."),
    DomainRule(
        _host("loc.gov"),
        TrustTier.GOVERNMENT,
        None,
        "The Library of Congress, which republishes official text across "
        "jurisdictions rather than deciding anything.",
    ),
    DomainRule(
        _host("nycourts.gov"),
        TrustTier.COURT,
        _NEW_YORK,
        "The New York Unified Court System, including the official reports. "
        "The corpora cite Appellate Division decisions heavily and those are "
        "exactly where the free federal record holds nothing.",
    ),
    DomainRule(
        _host("courts.ca.gov"),
        TrustTier.COURT,
        _CALIFORNIA,
        "The California courts' own published opinions.",
    ),
    DomainRule(
        re.compile(r"(?:^|\.)courts\.[a-z]{2}\.gov$", re.IGNORECASE),
        TrustTier.COURT,
        None,
        "A state judiciary on its own domain. The jurisdiction it covers is not "
        "derivable from the host alone, so it is left unscoped and can support "
        "a refutation only when the citation's court is confirmed separately.",
    ),
    DomainRule(
        re.compile(r"(?:^|\.)(courts|judicial|judiciary)\.state\.[a-z]{2}\.us$", re.IGNORECASE),
        TrustTier.COURT,
        None,
        "The older state-judiciary hosting convention.",
    ),
    DomainRule(
        _host("law.cornell.edu"),
        TrustTier.ARCHIVE,
        None,
        "Cornell's Legal Information Institute.",
    ),
    DomainRule(_host("case.law"), TrustTier.ARCHIVE, None, "The Caselaw Access Project."),
    DomainRule(
        _host("courtlistener.com"),
        TrustTier.ARCHIVE,
        None,
        "The archive this project already queries directly. A web result here "
        "adds nothing the API did not already give, and is listed so it is "
        "recognised rather than treated as an independent source.",
    ),
    DomainRule(_host("free.law"), TrustTier.ARCHIVE, None, "The Free Law Project."),
    DomainRule(_host("justia.com"), TrustTier.COMMERCIAL, None, "Justia."),
    DomainRule(_host("casetext.com"), TrustTier.COMMERCIAL, None, "Casetext."),
    DomainRule(_host("leagle.com"), TrustTier.COMMERCIAL, None, "Leagle."),
    DomainRule(_host("vlex.com"), TrustTier.COMMERCIAL, None, "vLex."),
    DomainRule(_host("anylaw.com"), TrustTier.COMMERCIAL, None, "AnyLaw."),
    DomainRule(_host("openjurist.org"), TrustTier.COMMERCIAL, None, "OpenJurist."),
    DomainRule(_host("findlaw.com"), TrustTier.COMMERCIAL, None, "FindLaw."),
)


@dataclass(frozen=True, slots=True)
class Authority:
    """What one URL is allowed to be evidence of, for one citation."""

    host: str
    tier: TrustTier
    publishes_this_court: bool
    """Whether this host authoritatively publishes the deciding court's decisions.

    ``False`` where the host is a court's own site and the citation belongs to
    a different court -- the Ninth Circuit's silence about a New York case is
    not evidence about that case.
    """
    note: str

    @property
    def is_trusted(self) -> bool:
        """Whether the host is on the list at all."""
        return self.tier is not TrustTier.UNTRUSTED


class WebEvidence(IntEnum):
    """What a web result may be used to conclude."""

    NOTHING = 0
    """The default, and the answer for every untrusted host, every absence of a
    result, and every page that merely mentions the citation."""

    REFUTES_LOCATOR = 1
    """An authoritative publisher gives this case name a different reporter
    citation than the filing did."""


def tier_of(url: str) -> tuple[str, TrustTier, str]:
    """Classify one URL's host. Returns the host, its tier, and the rule's note."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for rule in DOMAIN_RULES:
        if rule.pattern.search(host):
            return host, rule.tier, rule.note
    return host, TrustTier.UNTRUSTED, "Not an approved publisher of court decisions."


def authority_for(url: str, *, court_id: str | None) -> Authority:
    """Decide what one URL may be evidence of, for a citation from ``court_id``.

    ``court_id`` is a CourtListener court identifier as carried on the
    citation. Passing ``None`` -- which is common, since a citation written
    without a parenthetical has no court -- means the jurisdiction cannot be
    checked, so no host counts as publishing this court.
    """
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for rule in DOMAIN_RULES:
        if not rule.pattern.search(host):
            continue
        if rule.courts is None:
            # A cross-jurisdiction publisher. It republishes rather than
            # decides, so it is not scoped to one court.
            publishes = rule.tier <= TrustTier.ARCHIVE
        else:
            publishes = court_id is not None and bool(rule.courts.match(court_id))
        return Authority(host=host, tier=rule.tier, publishes_this_court=publishes, note=rule.note)
    return Authority(
        host=host,
        tier=TrustTier.UNTRUSTED,
        publishes_this_court=False,
        note="Not an approved publisher of court decisions.",
    )


def may_refute(authority: Authority) -> bool:
    """Whether a differing citation on this host is evidence against the filing.

    Requires both that the publisher is close enough to the court to be held to
    what it prints, and that it publishes this court at all. A commercial site
    is deliberately excluded: several now carry generated summaries beside the
    transcribed text, and a result page does not say which one it is.
    """
    return authority.tier <= TrustTier.GOVERNMENT and authority.publishes_this_court


def rank(urls: list[str], *, court_id: str | None) -> list[tuple[str, Authority]]:
    """Order candidate result URLs by how close their publisher is to the court.

    Untrusted hosts are dropped rather than ranked last. Keeping them in the
    list invites reading one when nothing better turns up, which is exactly the
    situation the tiers exist to prevent.
    """
    scored = [(url, authority_for(url, court_id=court_id)) for url in urls]
    kept = [(url, a) for url, a in scored if a.is_trusted]
    return sorted(kept, key=lambda pair: (pair[1].tier, not pair[1].publishes_this_court))
