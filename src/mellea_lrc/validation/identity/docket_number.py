"""Read a court out of a docket number's format, a second witness to the docket's court.

The archive names a record's court in one place, the docket's ``court_id``,
and that field is sometimes wrong: `Beery v. Hitachi`, 157 F.R.D. 477, is
filed under `cand` with the docket number `No. CV 93-4868 DT (Ex)`, which is
the Central District of California's format down to the magistrate's
lowercase `x`. The number was printed by the court that decided the case and
copied into the archive with the opinion, so its format is evidence about the
court that does not come from the field being checked.

What a format can say, and only this, is read here:

- its **level**: a bare `13-2316` is a court of appeals number; `18-CV-4418`,
  `5:03-misc-00007` and `Civil Action 05-1452 (RBW)` are trial-court numbers;
  `20-10234-bk` is a bankruptcy number
- a **court**, where a convention is distinctive enough to name one: the
  First Circuit's `P` suffix (`15-1987P`), the Federal Circuit's four-digit
  year (`2019-1234`), the Central District of California's lowercase-`x`
  magistrate token (`DT (Ex)`), the Southern District of Texas's division
  letter (`L-07-132` for Laredo)
- the **judge's initials**, where the number carries them -- `(ALC)`,
  `-JWL` -- which are kept as evidence and not resolved to a court here

Everything else is silence. A state docket number, an index number, a number
with no convention this module knows, reads as nothing, and the node says so.
The reading is compared with the docket's court: a court the convention pins
must be that court; a level must be the court's level in courts-db. A
disagreement does not by itself decide which side is wrong. It is recorded so
that the two witnesses can be measured against each other over a corpus
before either is trusted over the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from mellea_lrc.validation.types import (
    DocketCourtRetrievalNode,
    DocketNumberCourtNode,
    FieldCheckOutcome,
    ValidationNodeStatus,
)

_PREFIX = re.compile(
    r"^\s*(?:(?:case|docket|civil action|criminal action|civ\.?|cr\.?)\s*)*(?:nos?\.?|numbers?|#)?\s*",
    re.IGNORECASE,
)
_APPELLATE_NUMBER = re.compile(r"^(?:\d{2}|\d{4})-\d{3,5}[A-Z]?$")
_FIRST_CIRCUIT = re.compile(r"^\d{2}-\d{4}P$")
_FEDERAL_CIRCUIT = re.compile(r"^(?:19|20)\d{2}-\d{4}$")
_TRIAL_TOKEN = re.compile(
    r"(?<![A-Za-z])(?:cv|civ|civil|cr|crim|criminal|misc|mc|md|cvp|civil action)(?![A-Za-z])", re.IGNORECASE
)
_BANKRUPTCY_TOKEN = re.compile(r"(?<![A-Za-z])(?:bk|bankr|adv|ap)(?![A-Za-z])", re.IGNORECASE)
_DIVISION_PREFIX = re.compile(r"^\d{1,2}:\d{2}-")
_CACD_MAGISTRATE = re.compile(r"\(([A-Z]{1,4}x)\)")
_TXSD_DIVISION = re.compile(r"(?<![A-Za-z0-9])([BCGHLMV])-\d{2}-\d{1,5}\b")
_PAREN_INITIALS = re.compile(r"\(([A-Z]{2,4})\)")
_SUFFIX_INITIALS = re.compile(r"(?<=\d)(-[A-Z]{2,4})(?![A-Za-z0-9])")
_CACD_INITIALS = re.compile(r"\d\s+([A-Z]{2,4})\s+\([A-Z]{1,4}x\)")


@dataclass(frozen=True, slots=True)
class DocketNumberReading:
    """What one docket number's format says, and the fragment that says it."""

    number: str
    level: str | None
    """`appellate`, `trial` or `bankruptcy`, in courts-db's words; None when the format says nothing."""
    courts: frozenset[str]
    """courts-db identifiers a convention pins the number to; empty when no convention applies."""
    evidence: str
    judge_initials: str | None


def read_docket_number(number: str | None) -> DocketNumberReading | None:
    """Read the level, the court and the judge's initials a docket number's format carries."""
    if number is None or not number.strip():
        return None
    text = " ".join(number.split())
    body = _PREFIX.sub("", text)
    initials = _initials(body)
    trial_token = _TRIAL_TOKEN.search(text)
    if match := _CACD_MAGISTRATE.search(body):
        return DocketNumberReading(text, "trial", frozenset({"cacd"}), match.group(0), initials)
    if match := _TXSD_DIVISION.search(body):
        return DocketNumberReading(text, "trial", frozenset({"txsd"}), match.group(0), initials)
    tokens = [token.strip() for token in re.split(r",|\band\b|;|/", body) if token.strip()]
    if tokens and all(_APPELLATE_NUMBER.match(token) or re.fullmatch(r"\d{3,5}", token) for token in tokens):
        first = tokens[0]
        if _FIRST_CIRCUIT.match(first):
            return DocketNumberReading(text, "appellate", frozenset({"ca1"}), first, None)
        if _FEDERAL_CIRCUIT.match(first):
            return DocketNumberReading(text, "appellate", frozenset({"cafc"}), first, None)
        return DocketNumberReading(text, "appellate", frozenset(), first, None)
    if match := _BANKRUPTCY_TOKEN.search(body):
        return DocketNumberReading(text, "bankruptcy", frozenset(), match.group(0), initials)
    if match := trial_token or _DIVISION_PREFIX.search(body):
        return DocketNumberReading(text, "trial", frozenset(), match.group(0), initials)
    if match := _SUFFIX_INITIALS.search(body):
        # `08-2027-JWL`: a judge's initials hang off district-court numbers.
        return DocketNumberReading(text, "trial", frozenset(), match.group(1), initials)
    return DocketNumberReading(text, None, frozenset(), "", initials)


def _initials(body: str) -> str | None:
    for pattern in (_PAREN_INITIALS, _CACD_INITIALS):
        if match := pattern.search(body):
            return match.group(1)
    if match := _SUFFIX_INITIALS.search(body):
        return match.group(1).lstrip("-")
    return None


@lru_cache(maxsize=1)
def _levels() -> dict[str, str]:
    from courts_db import courts

    # courts-db types 39 federal district courts `appellate` -- `ilsd`, `ksd`,
    # `dcd` among them -- so for the federal system the level is read from
    # the court's name, which is regular, and `type` is trusted elsewhere.
    levels: dict[str, str] = {}
    for court in courts:
        court_id = str(court["id"])
        kind = str(court.get("type") or "")
        if court.get("system") == "federal":
            name = str(court.get("name") or "")
            if "Bankruptcy" in name:
                kind = "bankruptcy"
            elif "District Court" in name:
                kind = "trial"
            elif "Court of Appeals" in name or "Circuit" in name:
                kind = "appellate"
        if kind in ("appellate", "trial", "bankruptcy"):
            levels[court_id] = kind
        elif kind == "trial & iac":
            levels[court_id] = "trial"
    return levels


def court_level(court_id: str | None) -> str | None:
    """A court's level -- `appellate`, `trial`, `bankruptcy` -- or None when nothing says."""
    return _levels().get(court_id) if court_id else None


def run_docket_number_check(retrieval: DocketCourtRetrievalNode) -> DocketNumberCourtNode:
    """Compare what the docket number's format says with the docket's court field."""
    node_id = f"{retrieval.node_id}:docket_number_check"
    reading = read_docket_number(retrieval.docket_number)
    court = retrieval.court_id
    if reading is None or court is None:
        return _node(
            node_id,
            retrieval,
            reading,
            ValidationNodeStatus.SKIPPED,
            FieldCheckOutcome.UNAVAILABLE,
            status_message="Skipped the docket number check because the docket carries no number or no court.",
            outcome_message="Nothing to compare.",
        )
    if reading.courts:
        agree = court in reading.courts
        return _node(
            node_id,
            retrieval,
            reading,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.MATCH if agree else FieldCheckOutcome.MISMATCH,
            status_message="Docket number check completed.",
            outcome_message=(
                f"The number's '{reading.evidence}' is {_name(reading.courts)}'s convention, "
                + ("which is the docket's court." if agree else f"and the docket says {court}.")
            ),
        )
    level = court_level(court)
    if reading.level is None or level is None:
        return _node(
            node_id,
            retrieval,
            reading,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.UNAVAILABLE,
            status_message="Docket number check completed.",
            outcome_message=(
                f"The number '{reading.number}' follows no convention this check reads."
                if reading.level is None
                else f"courts-db gives no level for {court}."
            ),
        )
    agree = reading.level == level
    return _node(
        node_id,
        retrieval,
        reading,
        ValidationNodeStatus.SUCCEEDED,
        FieldCheckOutcome.MATCH if agree else FieldCheckOutcome.MISMATCH,
        status_message="Docket number check completed.",
        outcome_message=(
            f"The number's '{reading.evidence}' is a {reading.level}-court form, and {court} is a {level} court."
        ),
    )


def _name(courts: frozenset[str]) -> str:
    return ", ".join(sorted(courts))


def _node(
    node_id: str,
    retrieval: DocketCourtRetrievalNode,
    reading: DocketNumberReading | None,
    status: ValidationNodeStatus,
    outcome: FieldCheckOutcome,
    *,
    status_message: str,
    outcome_message: str,
) -> DocketNumberCourtNode:
    return DocketNumberCourtNode(
        node_id=node_id,
        status=status,
        outcome=outcome,
        docket_number=retrieval.docket_number,
        retrieved_court_id=retrieval.court_id,
        level=reading.level if reading else None,
        courts=tuple(sorted(reading.courts)) if reading else (),
        evidence=reading.evidence if reading else "",
        judge_initials=reading.judge_initials if reading else None,
        depends_on=(retrieval.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
    )


__all__ = ["DocketNumberReading", "court_level", "read_docket_number", "run_docket_number_check"]
