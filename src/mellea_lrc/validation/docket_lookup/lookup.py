"""A docket is a lookup, and two archives answer different halves of it.

A docket number with a court is a key: asked of CourtListener's docket index
scoped to the court, or of the Government Publishing Office by court code and
case number, one case comes back, or none. Neither returns a field of
candidates to judge between, so neither needs a model, and both are
deterministic.

The two archives are fed oppositely, which is the reason to ask both.
CourtListener holds what was published and what somebody bought from PACER:
its docket sheet is complete but the documents on it usually are not. The
Publishing Office is fed by the court itself under the E-Government Act, so
it holds the opinions the court wrote, publication and purchase aside, and
holds no docket sheet at all. An unreported decision is exactly what one
holds and the other does not.

A docket number without a court is not a key -- every district has a
`05-4206` -- and is refused rather than guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.validation.docket_lookup.numbers import docket_core, docket_number_matches

if TYPE_CHECKING:
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.govinfo import GovinfoServiceClient

try:
    from mellea_lrc.govinfo import GovinfoError
except ImportError:  # pragma: no cover
    GovinfoError = RuntimeError  # type: ignore[assignment,misc]


@dataclass(frozen=True, slots=True)
class DocketDecision:
    """One thing a court wrote in the case, as one archive holds it."""

    archive: str
    """`courtlistener` or `govinfo`."""
    identifier: str
    """The granule id, or the docket entry id."""
    date: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class ArchiveAnswer:
    """What one archive said to the key."""

    archive: str
    status: str
    """`found`, `not_found`, `several`, `unavailable`."""
    identifier: str | None = None
    """The docket id, or the package id."""
    docket_number: str | None = None
    """The number as the archive writes it."""
    caption: str | None = None
    date_filed: str | None = None
    decisions: tuple[DocketDecision, ...] = ()
    error: str | None = None
    candidates: tuple[str, ...] = ()
    """When several cases answered, their captions."""


@dataclass(frozen=True, slots=True)
class DocketRecord:
    """The answer to one key, from every archive asked."""

    court_id: str | None
    docket_number: str
    answers: tuple[ArchiveAnswer, ...] = field(default_factory=tuple)

    @property
    def found(self) -> tuple[ArchiveAnswer, ...]:
        return tuple(answer for answer in self.answers if answer.status == "found")

    @property
    def caption(self) -> str | None:
        """The case's caption, the Publishing Office's first since the court wrote it."""
        for archive in ("govinfo", "courtlistener"):
            for answer in self.found:
                if answer.archive == archive and answer.caption:
                    return answer.caption
        return None

    @property
    def decisions(self) -> tuple[DocketDecision, ...]:
        return tuple(decision for answer in self.found for decision in answer.decisions)

    def decisions_on(self, day: str) -> tuple[DocketDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.date == day)


def lookup_docket(
    court_id: str | None,
    docket_number: str,
    *,
    courtlistener: CourtListenerServiceClient | None = None,
    govinfo: GovinfoServiceClient | None = None,
) -> DocketRecord:
    """Ask every archive given for the case under this court and docket number."""
    if not court_id:
        return DocketRecord(court_id, docket_number, ())
    answers: list[ArchiveAnswer] = []
    if govinfo is not None:
        answers.append(_ask_govinfo(govinfo, court_id, docket_number))
    if courtlistener is not None:
        answers.append(_ask_courtlistener(courtlistener, court_id, docket_number))
    return DocketRecord(court_id, docket_number, tuple(answers))


def _ask_govinfo(govinfo: GovinfoServiceClient, court_id: str, docket_number: str) -> ArchiveAnswer:
    try:
        cases = govinfo.find_case(court_id, docket_number)
    except GovinfoError as exc:
        return ArchiveAnswer("govinfo", "unavailable", error=getattr(exc, "message", str(exc)))
    matching = [case for case in cases if docket_number_matches(docket_number, case.case_number)]
    if not matching:
        return ArchiveAnswer("govinfo", "not_found", candidates=tuple(c.title or c.package_id for c in cases))
    if len(matching) > 1:
        return ArchiveAnswer(
            "govinfo", "several", candidates=tuple(c.title or c.package_id for c in matching)
        )
    case = matching[0]
    return ArchiveAnswer(
        "govinfo",
        "found",
        identifier=case.package_id,
        docket_number=case.case_number,
        caption=case.title,
        date_filed=case.date_issued,
        decisions=tuple(
            DocketDecision(
                "govinfo", opinion.granule_id, opinion.date_issued, opinion.docket_text or opinion.title
            )
            for opinion in case.opinions
        ),
    )


def _ask_courtlistener(
    client: CourtListenerServiceClient, court_id: str, docket_number: str
) -> ArchiveAnswer:
    core = docket_core(docket_number)
    query = f"docketNumber:({core[0]}-{core[1]})" if core else f'docketNumber:"{docket_number.strip()}"'
    try:
        result = client.search(query, "d", court=court_id)
    except CourtListenerError as exc:
        return ArchiveAnswer("courtlistener", "unavailable", error=exc.message)
    rows = [
        row for row in _rows(result) if docket_number_matches(docket_number, _text(row.get("docketNumber")))
    ]
    if not rows:
        return ArchiveAnswer(
            "courtlistener",
            "not_found",
            candidates=tuple(_text(r.get("caseName")) or "" for r in _rows(result)),
        )
    if len(rows) > 1:
        return ArchiveAnswer(
            "courtlistener", "several", candidates=tuple(_text(r.get("caseName")) or "" for r in rows)
        )
    row = rows[0]
    return ArchiveAnswer(
        "courtlistener",
        "found",
        identifier=_text(row.get("docket_id")) or _text(row.get("id")),
        docket_number=_text(row.get("docketNumber")),
        caption=_text(row.get("caseName")),
        date_filed=_text(row.get("dateFiled")),
    )


def _rows(result: object) -> list[Mapping[str, object]]:
    rows = getattr(result, "results", None) or ()
    return [row for row in rows if isinstance(row, Mapping)]


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["ArchiveAnswer", "DocketDecision", "DocketRecord", "lookup_docket"]
