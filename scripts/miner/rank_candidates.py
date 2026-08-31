"""Rank candidate docket entries for an order that names no docket number.

`resolve.accused_entries` handles the order that names its target in the same
sentence as the accusation: "the Court found that Petitioner's habeas
petition (Dkt. 1) ... contained citation errors". A meaningful share of real
orders do not do that. They identify the offending filing some other way --

    attorney Jason Castro had filed a motion littered with fabricated cases
    and sham quotes

-- which names an attorney and a kind of document, not an entry. There is no
number in the sentence for `resolve.py` to find, and there never will be, no
matter how the sentence-splitting is tuned.

This module is the fallback for that case. It does not try to parse a docket
number out of the order at all -- if one were extractable that way, resolve.py
would have found it. Instead it fetches the docket's own entries and scores
each one against what the order's language *does* give you, in the order the
task set out (strongest first):

1. **Document kind.** The order describes the filing ("a motion...", "his
   response brief...", "a surreply"). An entry's own docket description
   either uses that word or it doesn't.
2. **Timing.** An entry filed on or after the order can't be what the order
   is complaining about. This is a hard filter, not a score -- entries in the
   future are dropped, not merely penalized. (Nothing similarly excludes "too
   early": entry 1 is normally the complaint that opened the case, and a
   pro se litigant's very first filing has been fabricated citations before
   now.)
3. **Attorney.** A name the order attaches to the filing ("attorney Jason
   Castro"), matched against the entry's own docket text -- PACER dockets
   routinely tag entries with the filer's name.
4. **Recency.** Among entries that tie on the above, the one closest to the
   order (by entry number, which increases with time on a docket) is the
   likelier candidate: most sanctions and show-cause orders follow shortly
   after the filing they are about.

The result is a ranked list with the evidence for each entry, not a decision.
Nothing here is confirmed by fetching and reading the candidate the way
`resolve.py`'s docstring describes for its own candidates -- that step still
belongs to whoever adjudicates the output of this module.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.miner.resolve import _ATTRIBUTION, _split_sentences

# Some courts' PDF generators write real Unicode hyphens (U+2010/U+2011)
# rather than the ASCII hyphen-minus every pattern in this module is written
# against -- enough to turn "non-existent" into a string none of them
# recognizes. `resolve._ATTRIBUTION` accepts every dash variant in its own
# pattern, which is affordable for one phrase; this module matches many, so it
# normalizes once up front instead of giving each a hyphen character class.
_HYPHENS = str.maketrans({"‐": "-", "‑": "-"})


def _normalize(text: str) -> str:
    return " ".join(text.split()).translate(_HYPHENS)


# Kinds of filing a court names when describing what it is complaining about.
# Ordered most-specific first so "motion for sanctions" is credited as itself
# and not double-counted as a second, bare "motion" match.
DOCUMENT_KIND_TERMS: tuple[str, ...] = (
    "amended complaint",
    "counterclaim",
    "cross-claim",
    "cross claim",
    "habeas petition",
    "motion for summary judgment",
    "motion to dismiss",
    "motion for sanctions",
    "motion for preliminary injunction",
    "memorandum of law",
    "memorandum in support",
    "memorandum in opposition",
    "opening brief",
    "response brief",
    "reply brief",
    "opposition brief",
    "sur-reply",
    "surreply",
    "traverse",
    "declaration",
    "affidavit",
    "objection",
    "opposition",
    "response",
    "reply",
    "petition",
    "complaint",
    "counter-complaint",
    "answer",
    "application",
    "notice",
    "brief",
    "memorandum",
    "motion",
)

# Cue words that introduce the name of the attorney the order is describing.
# Matches only the singular ("attorney", not "attorneys") -- Rule 11
# boilerplate's collective phrasing ("attorneys and pro se parties") never
# names anyone, so requiring the singular already excludes most of it. The
# negative lookaround excludes what is left: generic non-name uses of the
# singular itself -- "attorney fees", "attorney's fees", "attorney general",
# "attorney-client privilege", "attorney work product", "an attorney or
# unrepresented party", "a practicing attorney".
_ATTORNEY_CUE = re.compile(
    r"(?<!practicing )\b(?:attorney|counsel|esq\.?)\b"
    r"(?!'s\s+fees?\b|\s+fees?\b|\s+general\b|[-\s]client[-\s]privilege\b|[-\s]work[-\s]product\b"
    r"|\s*\[?(?:or|and)\b)",
    re.IGNORECASE,
)
# A run of two or three capitalized words -- what a proper name looks like in
# flattened PDF text.
_NAME_RUN = re.compile(r"\b[A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){1,2}\b")
# Capitalized runs that are legal boilerplate, not a person's name. A run is
# discarded only when every one of its words is on this list, so "Jason
# Castro" survives even though neither word is a coincidence, while "The
# Court", "Rule 11", and "Federal Rules" do not.
_NAME_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "in",
        "on",
        "at",
        "court",
        "courts",
        "rule",
        "rules",
        "civil",
        "procedure",
        "federal",
        "circuit",
        "district",
        "states",
        "united",
        "supreme",
        "appeals",
        "order",
        "orders",
        "plaintiff",
        "plaintiffs",
        "defendant",
        "defendants",
        "judge",
        "magistrate",
        "clerk",
        "case",
        "cases",
        "counsel",
        "attorney",
        "attorneys",
        "esq",
        "artificial",
        "intelligence",
        "ai",
        "generative",
        "sanctions",
        "sanction",
        "motion",
        "motions",
        "brief",
        "response",
        "reply",
        "opposition",
        "citation",
        "citations",
        "fed",
        "civ",
        "proc",
        "no",
        "nos",
        "amended",
        "complaint",
        "id",
        "see",
        "conclusion",
        "background",
        "analysis",
        "discussion",
        "introduction",
        "standing",
    }
)
# A window of characters to search around a cue word for the name it
# introduces -- wide enough for "Plaintiff's counsel, Maria Elena Lopez,"
# without reaching into an unrelated sentence.
_NAME_WINDOW = 80

# A name immediately followed by a quoted short form defining it as an alias
# -- `Jason Castro ("Castro")` -- a convention legal writing uses to name
# whoever it is about to keep discussing, whether or not it also ever calls
# them "attorney" or "counsel" outright.
_ALIAS_NAME = re.compile(r"\b([A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){1,2})\s*\([\"“][^\"”]{1,40}[\"”]\)")

# Sentences that discuss the misconduct but not in words `resolve._ATTRIBUTION`
# recognizes -- a court warning about "AI hallmarks" or "wholly inapplicable
# citations" without using resolve.py's exact vocabulary. Used only as a
# fallback when no sentence matches `_ATTRIBUTION`, since it is looser: it
# would, for instance, match a passing mention of "sanctions" that names no
# defect at all.
_MISCONDUCT_FALLBACK = re.compile(
    r"(hallmarks? of (?:reckless )?(?:artificial intelligence|ai)"
    r"|ai[- ]hallucinat\w*|ai[- ]generated|generative artificial intelligence"
    r"|wholly (?:inapplicable|inapposite|unsupported)"
    r"|irrelevant legal authority|frivolous filing)",
    re.IGNORECASE,
)


def _is_name(run: str) -> bool:
    words = run.split()
    return not all(word.strip(".'-").lower() in _NAME_STOPWORDS for word in words)


def extract_attorney_names(text: str) -> tuple[str, ...]:
    """Proper names the order attaches to a person it holds responsible.

    Two independent patterns, both scanning the whole document rather than
    just the accusing sentence -- an order often names someone in a
    background paragraph well before, or after, the sentence that actually
    describes the defective filing:

    - a name introduced by "attorney", "counsel", or "Esq.", e.g. "attorney
      Jason Castro"; and
    - a name immediately aliased in quotes, e.g. 'Jason Castro ("Castro")',
      a convention legal writing uses for whoever it is about to keep
      discussing, whether or not it ever also calls them "attorney" or
      "counsel" outright.

    The second pattern does not distinguish an attorney from a party, so it
    is weaker evidence on its own; `rank_candidates` treats every name this
    returns the same way, on the premise that a name matching an entry's own
    docket text is meaningful regardless of which pattern found it.
    """
    flat = _normalize(text)
    found: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            found.append(name)

    for cue in _ATTORNEY_CUE.finditer(flat):
        after = flat[cue.end() : cue.end() + _NAME_WINDOW]
        before = flat[max(0, cue.start() - _NAME_WINDOW) : cue.start()]
        # Do not cross a sentence boundary in either direction -- without
        # this, a case citation two sentences away from an unrelated mention
        # of "counsel" is close enough, by raw character count, to be
        # mistaken for the name it introduces.
        after = after.split(". ", 1)[0]
        before = before.rsplit(". ", 1)[-1]
        name = None
        after_match = _NAME_RUN.search(after)
        if after_match and _is_name(after_match.group(0)):
            name = after_match.group(0)
        else:
            before_matches = list(_NAME_RUN.finditer(before))
            for candidate in reversed(before_matches):
                if _is_name(candidate.group(0)):
                    name = candidate.group(0)
                    break
        if name:
            _add(name)

    for alias in _ALIAS_NAME.finditer(flat):
        name = alias.group(1)
        if _is_name(name):
            _add(name)

    return tuple(found)


def _accusing_text(order_text: str) -> str:
    """The part of the order worth mining for a document-kind signal.

    Prefers sentences `resolve._ATTRIBUTION` recognizes -- the same
    vocabulary `resolve.accused_entries` trusts -- and falls back to a looser
    misconduct vocabulary, and finally to the whole order, only when *neither*
    finds a single sentence to work with.

    Deliberately not entered a level further whenever the sentences found
    happen not to name a document kind: a generic AI-use notice ("AI may
    generate results that appear correct but rely on non-existent cases")
    matches `_ATTRIBUTION` just as reliably as a genuine finding does, and
    such boilerplate is exactly the case where falling through to the whole
    order would start crediting every kind of filing procedurally mentioned
    anywhere in it. A real order whose finding and whose description of the
    filing fall in different sentences -- neither of which resolve.py's or
    this module's vocabulary happens to span -- is a genuine miss this
    function accepts rather than trading for that noise.
    """
    flat = _normalize(order_text)
    sentences = _split_sentences(flat)
    strong = [s for s in sentences if _ATTRIBUTION.search(s)]
    if strong:
        return " ".join(strong)
    loose = [s for s in sentences if _MISCONDUCT_FALLBACK.search(s)]
    if loose:
        return " ".join(loose)
    return flat


def extract_document_kinds(order_text: str) -> tuple[str, ...]:
    """Kinds of filing the order's own language names, most specific first."""
    text = _accusing_text(order_text).lower()
    found: list[str] = []
    consumed: list[tuple[int, int]] = []
    for term in DOCUMENT_KIND_TERMS:
        # `s?` so "motions", "briefs", "declarations" match their singular
        # entry -- an order describes what was filed in whichever number is
        # grammatical, and a docket description is not guaranteed to agree.
        for match in re.finditer(rf"\b{re.escape(term)}s?\b", text):
            span = match.span()
            if any(span[0] < end and span[1] > start for start, end in consumed):
                continue
            found.append(term)
            consumed.append(span)
    return tuple(found)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One docket entry, ranked, with the evidence behind its rank."""

    entry_number: int
    description: str
    kind_matches: tuple[str, ...]
    attorney_matches: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def score(self) -> tuple[int, int, int]:
        """Sort key: kind match strength, then attorney match, then recency.

        Recency is `entry_number` itself -- among entries tied on the first
        two, the one with the higher (later, closer to the order) entry
        number ranks first.
        """
        kind_weight = sum(len(term.split()) for term in self.kind_matches)
        return (kind_weight, len(self.attorney_matches), self.entry_number)


def _entry_number(entry: Mapping[str, Any]) -> int | None:
    for key in ("document_number", "entry_number"):
        value = entry.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _entry_description(entry: Mapping[str, Any]) -> str:
    for key in ("description", "short_description"):
        value = entry.get(key)
        if value:
            return str(value)
    return ""


def rank_candidates(
    order_text: str,
    entries: Iterable[Mapping[str, Any]],
    *,
    order_entry: int | None = None,
) -> tuple[Candidate, ...]:
    """Rank a docket's entries as candidates for what an order accuses.

    `entries` is whatever `fetch_docket_entries` (or the `recap-documents/`
    endpoint it wraps) returns -- each a mapping with at least an entry
    number (`document_number` or `entry_number`) and a description
    (`description` or `short_description`).

    `order_entry` is the order's own entry number, used two ways: entries at
    or after it are dropped (they can't be what an earlier order is
    complaining about), and it anchors the recency tiebreak. Pass `None` when
    it is not known; every entry is then a candidate, without a filed-before
    cutoff.

    An empty result means either that the order's language carries no
    document-kind or attorney signal to match against (call
    `extract_document_kinds` / `extract_attorney_names` to see which), or
    that no entry on this docket survived the timing filter.
    """
    kinds = extract_document_kinds(order_text)
    attorneys = extract_attorney_names(order_text)
    attorney_keys = tuple((name, name.split()[-1]) for name in attorneys)

    candidates: list[Candidate] = []
    for entry in entries:
        number = _entry_number(entry)
        if number is None:
            continue
        if order_entry is not None and number >= order_entry:
            continue
        description = _entry_description(entry)
        lowered = description.lower()

        kind_matches = tuple(term for term in kinds if term in lowered)

        attorney_matches: list[str] = []
        for full_name, last_name in attorney_keys:
            if full_name.lower() in lowered or (last_name and last_name.lower() in lowered):
                attorney_matches.append(full_name)

        if not kind_matches and not attorney_matches:
            continue

        evidence: list[str] = []
        if kind_matches:
            evidence.append(f"description matches document kind(s): {', '.join(kind_matches)}")
        if attorney_matches:
            evidence.append(f"description names attorney: {', '.join(attorney_matches)}")
        if order_entry is not None:
            evidence.append(f"filed before the order (entry {number} < {order_entry})")

        candidates.append(
            Candidate(
                entry_number=number,
                description=description,
                kind_matches=kind_matches,
                attorney_matches=tuple(attorney_matches),
                evidence=tuple(evidence),
            )
        )

    return tuple(sorted(candidates, key=lambda c: c.score, reverse=True))


# --- Fetching real docket entries ------------------------------------------
#
# Separate from ranking on purpose: `rank_candidates` takes plain data so it
# can be tested and reused without a network call, and every network call
# this module makes goes through one function that is easy to count.

REQUEST_INTERVAL_SECONDS = 2.0


def fetch_docket_entries(base: str, docket_id: int, *, pages: int = 5) -> list[dict[str, Any]]:
    """Enumerate a docket's RECAP documents through the CourtListener proxy.

    One request per page of results; paced the same way `discover.py` and
    `harvest.py` pace theirs, since this hits the same shared, rate-limited
    proxy.
    """
    results: list[dict[str, Any]] = []
    url: str | None = (
        f"{base.rstrip('/')}/recap-documents/"
        f"?{urllib.parse.urlencode({'docket_entry__docket__id': str(docket_id)})}"
    )
    for _ in range(pages):
        if not url:
            break
        with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as response:
            payload = json.load(response)
        results.extend(payload.get("results", []))
        url = payload.get("next")
        if url:
            time.sleep(REQUEST_INTERVAL_SECONDS)
    return results


def propose_candidates(
    base: str,
    docket_id: int,
    order_text: str,
    *,
    order_entry: int | None = None,
) -> tuple[Candidate, ...]:
    """Fetch a docket's entries and rank them as candidates in one call."""
    entries = fetch_docket_entries(base, docket_id)
    return rank_candidates(order_text, entries, order_entry=order_entry)


def format_candidates(candidates: Sequence[Candidate]) -> str:
    """A human-readable rendering of a ranked candidate list, for reports."""
    if not candidates:
        return "(no candidates)"
    lines = []
    for rank, candidate in enumerate(candidates, start=1):
        lines.append(f"{rank}. entry {candidate.entry_number}: {candidate.description!r}")
        for item in candidate.evidence:
            lines.append(f"   - {item}")
    return "\n".join(lines)
