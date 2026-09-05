"""The courts a reporter can hold, so an unstated court can be checked for conflict.

A filing that writes `61 N.C. App. 134 (1983)` names no court, and nothing
should guess one. But the reporter is not silent: the North Carolina Appellate
Reports hold the decisions of North Carolina's appellate courts and no others.
If the archive's record at that page comes from a Texas district court, the
citation and the record conflict, and that is worth knowing without a model.

reporters-db records this as `mlz_jurisdiction`, a list of every jurisdiction
a reporter has ever held, in a notation courts-db does not share --
`us:nc;court.appeals`, `us:c4:nc.ed;district.court`, `us;supreme.court`. This
module maps that notation onto courts-db identifiers, and the result is a
**family**: the set of courts a record at this reporter may come from. The
list is historical and generous, so the family is a superset; a court outside
it is a conflict, a court inside it is compatible, and neither is a reading of
what the filing wrote.

The mapping is by construction where courts-db's identifiers are regular --
`us:c4:nc.ed;district.court` is `nced`, `us:c9:ca.cd;bankruptcy.court` is
`cacb`, `us:c9;court.appeals` is `ca9` -- and by courts-db's own fields where
they are not: a state's `supreme.court` is the court of last resort in that
state, its `court.appeals` the intermediate appellate court.
"""

from __future__ import annotations

import re
from functools import cache, lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mellea_lrc.core.citations import Reporter

_STATES = {
    "al": "Alabama", "ak": "Alaska", "as": "American Samoa", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware", "dc": "Washington D.C.",
    "fl": "Florida", "ga": "Georgia", "gu": "Guam", "hi": "Hawaii", "id": "Idaho", "il": "Illinois",
    "in": "Indiana", "ia": "Iowa", "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "me": "Maine",
    "md": "Maryland", "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada", "nh": "New Hampshire",
    "nj": "New Jersey", "nm": "New Mexico", "ny": "New York", "nc": "North Carolina", "nd": "North Dakota",
    "mp": "Northern Mariana Islands", "oh": "Ohio", "ok": "Oklahoma", "or": "Oregon", "pa": "Pennsylvania",
    "pr": "Puerto Rico", "ri": "Rhode Island", "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee",
    "tx": "Texas", "ut": "Utah", "vt": "Vermont", "vi": "Virgin Islands", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
}  # fmt: skip

_CIRCUIT = re.compile(r"^us:c(\d+)$")
_DISTRICT = re.compile(r"^us:c\d+:([a-z]{2})[.:]([a-z]*d)$")
_STATE = re.compile(r"^us:([a-z]{2})(?:[.:].*)?$")

_STATE_APPELLATE = {
    "supreme.court",
    "supreme.judicial.court",
    "court.appeals",
    "appeals.court",
    "court.appeal",
    "district.court.appeal",
    "court.criminal.appeals",
    "court.civil.appeals",
    "court.special.appeals",
}


def implied_courts(reporter: Reporter | None) -> frozenset[str]:
    """Every courts-db identifier a record in this reporter may come from. Empty when unknown."""
    if reporter is None or not reporter.editions:
        return frozenset()
    return _family(reporter.canonical) | (frozenset({"scotus"}) if reporter.is_scotus else frozenset())


def describe(family: frozenset[str], *, limit: int = 6) -> str:
    """The family for a message: `ca1, ca2, ... (13 courts)` or the whole list when short."""
    ordered = sorted(family)
    if len(ordered) <= limit:
        return ", ".join(ordered)
    return ", ".join(ordered[:limit]) + f", ... ({len(ordered)} courts)"


@cache
def _family(edition: str) -> frozenset[str]:
    """The family for one edition name, such as `F.3d`, which reporters-db files under `F.`."""
    found: set[str] = set()
    for entry in _entries_by_edition().get(edition, ()):
        for jurisdiction in entry.get("mlz_jurisdiction") or ():
            found |= _courts_for(jurisdiction)
    return frozenset(found)


@lru_cache(maxsize=1)
def _entries_by_edition() -> dict[str, tuple[dict, ...]]:
    from reporters_db import REPORTERS

    by_edition: dict[str, list[dict]] = {}
    for entries in REPORTERS.values():
        for entry in entries:
            for name in entry.get("editions", {}):
                by_edition.setdefault(name, []).append(entry)
    return {name: tuple(items) for name, items in by_edition.items()}


def _courts_for(jurisdiction: str) -> set[str]:
    head, _, kind = jurisdiction.partition(";")
    if head == "us" and kind == "supreme.court":
        return {"scotus"}
    if head == "us:c" and kind == "court.appeals.federal.circuit":
        return {"cafc"}
    if (circuit := _CIRCUIT.match(head)) and kind == "court.appeals":
        number = circuit.group(1)
        return {"cadc" if number == "0" else f"ca{number}"}
    if circuit and kind == "bankruptcy.appellate.panel":
        return {f"bap{circuit.group(1)}"}
    if (district := _DISTRICT.match(head)) and kind in ("district.court", "bankruptcy.court"):
        state, suffix = district.group(1), district.group(2)
        constructed = _known({f"{state}{suffix}" if kind == "district.court" else f"{state}{suffix[:-1]}b"})
        if constructed:
            return constructed
        # An identifier courts-db did not build regularly -- the Northern
        # Mariana Islands district is `nmid`, not `mpd` -- is found by place.
        return _federal_courts(_STATES.get(state, ""), bankruptcy=kind == "bankruptcy.court")
    if (
        (state := _STATE.match(head))
        and state.group(1) in _STATES
        and ":c" not in head[3:]
        and not head.endswith(".d")
    ):
        location = _STATES[state.group(1)]
        if kind in _STATE_APPELLATE:
            level = "colr" if "supreme" in kind else "iac"
            return _state_courts(location, level=level)
        return _state_courts(location, level=None)
    return set()


@lru_cache(maxsize=1)
def _federal_index() -> dict[tuple[str, bool], frozenset[str]]:
    """Federal trial and bankruptcy courts by (location, is_bankruptcy)."""
    from courts_db import courts

    by_key: dict[tuple[str, bool], set[str]] = {}
    for court in courts:
        if court.get("system") != "federal" or not court.get("location"):
            continue
        kind = court.get("type")
        if kind not in ("trial", "bankruptcy"):
            continue
        by_key.setdefault((str(court["location"]), kind == "bankruptcy"), set()).add(str(court["id"]))
    return {key: frozenset(value) for key, value in by_key.items()}


def _federal_courts(location: str, *, bankruptcy: bool) -> set[str]:
    return set(_federal_index().get((location, bankruptcy), frozenset())) if location else set()


@lru_cache(maxsize=1)
def _index() -> tuple[frozenset[str], dict[tuple[str, str | None], frozenset[str]]]:
    """Every courts-db id, and the state courts by (location, level)."""
    from courts_db import courts

    # courts-db's `level` is blank on many intermediate appellate courts, so
    # the split is: court of last resort by level, every other appellate
    # court by type, and the rest as trial.
    ids = frozenset(str(court["id"]) for court in courts)
    by_key: dict[tuple[str, str | None], set[str]] = {}
    for court in courts:
        if court.get("system") != "state":
            continue
        location = court.get("location")
        if not location:
            continue
        court_id = str(court["id"])
        name = str(court.get("name") or "")
        if court.get("level") == "colr" or (court.get("type") == "appellate" and "supreme" in name.lower()):
            by_key.setdefault((location, "colr"), set()).add(court_id)
        elif court.get("type") == "appellate":
            by_key.setdefault((location, "iac"), set()).add(court_id)
        else:
            by_key.setdefault((location, None), set()).add(court_id)
    return ids, {key: frozenset(value) for key, value in by_key.items()}


def _known(candidates: set[str]) -> set[str]:
    ids, _ = _index()
    return {candidate for candidate in candidates if candidate in ids}


def _state_courts(location: str, *, level: str | None) -> set[str]:
    _, by_key = _index()
    return set(by_key.get((location, level), frozenset()))


__all__ = ["describe", "implied_courts"]
