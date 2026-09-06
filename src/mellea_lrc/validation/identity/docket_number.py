"""Read a court out of a docket number's format, a second witness to the docket's court.

The archive names a record's court in one place, the docket's ``court_id``,
and that field is sometimes wrong: `Beery v. Hitachi`, 157 F.R.D. 477, is
filed under `cand` with the docket number `No. CV 93-4868 DT (Ex)`, which is
the Central District of California's format down to the magistrate's
lowercase `x`. The number was printed by the court that decided the case and
copied into the archive with the opinion, so its format is evidence about the
court that does not come from the field being checked.

What a format can say, and only this, is read here:

- its **level**: a bare `13-2316` is a court of appeals number or a
  bankruptcy court's, which print the same form; `18-CV-4418`,
  `5:03-misc-00007` and `Civil Action 05-1452 (RBW)` are district-court
  numbers; `20-10234-bk` is a bankruptcy number
- a **court**, where a convention is distinctive enough to name one: the
  First Circuit's `P` suffix (`15-1987P`), the Second Circuit's `-cv` and
  `-cr` (`18-2321-cv`), the Federal Circuit's four-digit year (`2019-1234`),
  the five-digit sequences of the Fifth, Ninth and Eleventh Circuits
  (`93-50859`), the Central District of California's lowercase-`x`
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

_DASHES = re.compile(r"[\u2010-\u2015\u2212]")
_PREFIX = re.compile(
    r"^\s*(?:(?:case|docket|civil action|criminal action|civ\.?|cr\.?)\s*)*(?:nos?\.?|numbers?|#)?\s*",
    re.IGNORECASE,
)
_TRIAL_WORDS = re.compile(r"\b(?:civil action|criminal action|civil|criminal)\b", re.IGNORECASE)
_TRIAL_PREFIX = re.compile(
    r"^(?:cause\s*(?:no\.?)?\s*:?\s*)?(?:civ\.?|cv|cr|crim\.?)\s*(?:a\.?\s*)?(?:no\.?)?\s*:?\s*\d",
    re.IGNORECASE,
)
"""`Civ. A. No. 89-S-501`, `10 Civ. 07497 (VM)`, `CV11-232-PHX-JAT`: a district court's type word before its number."""
_CIV_AFTER_YEAR = re.compile(r"^\d{2}\s+civ\.?\s*\d", re.IGNORECASE)
_STATE_APPELLATE = re.compile(r"-(?:PR|SA)$|\bCA-C[VR]\b")
"""Arizona's `CV 86-0148-PR` and `1 CA-CV 93-0218`: appellate numbers that carry `CV` too."""
_DOCKET_WORD = re.compile(r"\bdockets?\s+(\d{2}-\d{4})\b", re.IGNORECASE)
"""`606, Docket 84-7925`: the Second Circuit's older form, the reporter's own number before the docket's."""
_APPELLATE_NUMBER = re.compile(r"^\d{2}-\d{3,5}$")
_FIRST_CIRCUIT = re.compile(r"^\d{2}-\d{4}P$")
_SECOND_CIRCUIT = re.compile(r"^\d{2}-\d{4}-(?:cv|cr)$", re.IGNORECASE)
_FEDERAL_CIRCUIT = re.compile(r"^(?:19|20)\d{2}-\d{4}$")
_FIVE_DIGIT_CIRCUITS = frozenset({"ca5", "ca9", "ca11"})
_DISTRICT_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{1,2}:)?\d{2}-(?:cv|cr|mc|md|misc|civ|crim)-\d{1,6}\b", re.IGNORECASE
)
_BANKRUPTCY_TOKEN = re.compile(r"(?<![A-Za-z])(?:bk|bankr|adv|ap)(?![A-Za-z])", re.IGNORECASE)
_JUDGE_SUFFIX_NUMBER = re.compile(r"^\d{2}-\d{4}-([A-Z]{3,4})$")
_CACD_MAGISTRATE = re.compile(r"\(([A-Z]{1,4}x)\)")
_TXSD_DIVISION = re.compile(r"(?<![A-Za-z0-9])([BCGHLMV])-\d{2}-\d{1,5}\b")
_PAREN_INITIALS = re.compile(r"\(([A-Z]{2,4})\)")
_SUFFIX_INITIALS = re.compile(r"(?<=\d)-([A-Z]{3,4})(?![A-Za-z0-9])")
_CACD_INITIALS = re.compile(r"\d\s+([A-Z]{2,4})\s+\([A-Z]{1,4}x\)")

APPELLATE_OR_BANKRUPTCY = frozenset({"appellate", "bankruptcy"})
"""A bare `16-10303` is a court of appeals number and a bankruptcy court number alike."""


@dataclass(frozen=True, slots=True)
class DocketNumberReading:
    """What one docket number's format says, and the fragment that says it."""

    number: str
    levels: frozenset[str]
    """The levels the form fits -- `appellate`, `trial`, `bankruptcy` -- empty when it says nothing."""
    courts: frozenset[str]
    """courts-db identifiers a convention pins the number to; empty when no convention applies."""
    evidence: str
    judge_initials: str | None


def read_docket_number(number: str | None) -> DocketNumberReading | None:
    """Read the levels, the courts and the judge's initials a docket number's format carries.

    Every rule here was checked against a docket the archive holds, and the
    ones that read a court are the distinctive conventions only. State
    appellate numbers -- Tennessee's `E2010-00991-SC-R11-CV`, Arizona's
    `1 CA-CV 93-0218` -- carry `CV` too, so a type token alone is not a
    trial-court marker; the form has to be a district court's.
    """
    if number is None or not number.strip():
        return None
    text = _DASHES.sub("-", " ".join(number.split()))
    body = _PREFIX.sub("", text)
    initials = _initials(body)
    trial = frozenset({"trial"})
    if match := _CACD_MAGISTRATE.search(body):
        return DocketNumberReading(text, trial, frozenset({"cacd"}), match.group(0), initials)
    if match := _TXSD_DIVISION.search(body):
        return DocketNumberReading(text, trial, frozenset({"txsd"}), match.group(0), initials)
    if match := _DISTRICT_NUMBER.search(body):
        return DocketNumberReading(text, trial, frozenset(), match.group(0), initials)
    if match := _TRIAL_WORDS.search(text):
        return DocketNumberReading(text, trial, frozenset(), match.group(0), initials)
    if not _STATE_APPELLATE.search(body) and (
        match := _TRIAL_PREFIX.match(text) or _CIV_AFTER_YEAR.match(body)
    ):
        return DocketNumberReading(text, trial, frozenset(), match.group(0).strip(), initials)
    if match := _BANKRUPTCY_TOKEN.search(body):
        return DocketNumberReading(text, frozenset({"bankruptcy"}), frozenset(), match.group(0), initials)
    tokens = [token.strip() for token in re.split(r",|\band\b|;|/", body) if token.strip()]
    first = tokens[0] if tokens else ""
    if _SECOND_CIRCUIT.match(first):
        return DocketNumberReading(text, frozenset({"appellate"}), frozenset({"ca2"}), first, None)
    if _FIRST_CIRCUIT.match(first):
        return DocketNumberReading(text, frozenset({"appellate"}), frozenset({"ca1"}), first, None)
    if _FEDERAL_CIRCUIT.match(first):
        return DocketNumberReading(text, frozenset({"appellate"}), frozenset({"cafc"}), first, None)
    if match := _JUDGE_SUFFIX_NUMBER.match(first):
        # `08-2027-JWL`: a judge's initials hang off a district court's number.
        return DocketNumberReading(text, trial, frozenset(), first, match.group(1))
    if tokens and all(_APPELLATE_NUMBER.match(token) or re.fullmatch(r"\d{3,5}", token) for token in tokens):
        if re.match(r"^\d{2}-\d{5}$", first):
            # Five-digit sequences are the Fifth, Ninth and Eleventh Circuits'
            # among the courts of appeals, and every bankruptcy court's.
            return DocketNumberReading(text, APPELLATE_OR_BANKRUPTCY, _FIVE_DIGIT_CIRCUITS, first, None)
        return DocketNumberReading(text, APPELLATE_OR_BANKRUPTCY, frozenset(), first, None)
    if match := _DOCKET_WORD.search(text):
        return DocketNumberReading(text, APPELLATE_OR_BANKRUPTCY, frozenset(), match.group(1), None)
    return DocketNumberReading(text, frozenset(), frozenset(), "", initials)


def _initials(body: str) -> str | None:
    for pattern in (_PAREN_INITIALS, _CACD_INITIALS, _SUFFIX_INITIALS):
        if match := pattern.search(body):
            return match.group(1)
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
    level = court_level(court)
    if not reading.levels or level is None:
        return _node(
            node_id,
            retrieval,
            reading,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.UNAVAILABLE,
            status_message="Docket number check completed.",
            outcome_message=(
                f"The number '{reading.number}' follows no convention this check reads."
                if not reading.levels
                else f"No level is known for {court}."
            ),
        )
    if level not in reading.levels:
        return _node(
            node_id,
            retrieval,
            reading,
            ValidationNodeStatus.SUCCEEDED,
            FieldCheckOutcome.MISMATCH,
            status_message="Docket number check completed.",
            outcome_message=(
                f"The number's '{reading.evidence}' is a {' or '.join(sorted(reading.levels))}-court form, "
                f"and {court} is a {level} court."
            ),
        )
    # A convention pins the court among the courts of its own level: five
    # digits name three circuits among the courts of appeals and say nothing
    # about which bankruptcy court.
    if reading.courts and level == court_level(next(iter(reading.courts))):
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
    return _node(
        node_id,
        retrieval,
        reading,
        ValidationNodeStatus.SUCCEEDED,
        FieldCheckOutcome.MATCH,
        status_message="Docket number check completed.",
        outcome_message=(
            f"The number's '{reading.evidence}' is a {' or '.join(sorted(reading.levels))}-court form, "
            f"and {court} is a {level} court."
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
        levels=tuple(sorted(reading.levels)) if reading else (),
        courts=tuple(sorted(reading.courts)) if reading else (),
        evidence=reading.evidence if reading else "",
        judge_initials=reading.judge_initials if reading else None,
        depends_on=(retrieval.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
    )


__all__ = ["DocketNumberReading", "court_level", "read_docket_number", "run_docket_number_check"]
