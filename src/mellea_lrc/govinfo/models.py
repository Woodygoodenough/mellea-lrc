"""What the Government Publishing Office holds for a federal case.

govinfo's United States Courts Opinions collection is fed by the courts
themselves under the E-Government Act: each participating court deposits
the opinions it writes, publication or not. A *package* is one case, keyed
by court and docket number; each *granule* in it is one deposited opinion,
with the day it was issued and the clerk's docket text describing it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GovinfoOpinion:
    """One opinion the court deposited for a case."""

    package_id: str
    granule_id: str
    title: str | None
    date_issued: str | None
    docket_text: str | None = None
    """The clerk's description of the entry, when the granule summary was read."""
    pdf_link: str | None = None


@dataclass(frozen=True, slots=True)
class GovinfoCase:
    """One case the collection holds: the package and every opinion deposited in it."""

    package_id: str
    court_code: str | None
    case_number: str | None
    """The docket number as the court's own system writes it, `2:05-cv-04206`."""
    title: str | None
    case_type: str | None
    date_issued: str | None
    opinions: tuple[GovinfoOpinion, ...]


__all__ = ["GovinfoCase", "GovinfoOpinion"]
