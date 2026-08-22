"""Deciding which websites may be evidence about a citation, and for what.

Not wired into the pipeline. It exists because the question came up and the
answer is worth keeping: see `exploration/notes/caselaw-archive.md` for why
this direction produced a bulk archive reader rather than a search agent.
"""

from mellea_lrc.experimental.web_refutation.domains import (
    Authority,
    DomainRule,
    TrustTier,
    WebEvidence,
    authority_for,
    may_refute,
    rank,
    tier_of,
)

__all__ = [
    "Authority",
    "DomainRule",
    "TrustTier",
    "WebEvidence",
    "authority_for",
    "may_refute",
    "rank",
    "tier_of",
]
