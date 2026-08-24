"""Build the case-name annotation from the corpus text, so it can be rebuilt.

`derived/extraction.jsonl` records where each citation's volume, reporter and
page sit in the document and nothing else. That is enough to score whether a
citation was found and nothing about whether it was *understood*, and it is why
20 citations in this corpus could not be classified: a case name disagreeing
with the archive is either a real defect or a misreading, and without knowing
what the filing actually wrote there is no way to tell.

This produces `derived/case_names.jsonl`, one row per locator row, recording the
case name **as the filing wrote it**.

**The name is always text that occurs in the document.** It is copied out at a
recorded span, never supplied from an archive or a lookup -- that is the whole
point, since a name taken from an external source would agree with that source
by construction and could never evidence a defect. Every row is verified by
slicing the document at its span and comparing.

Three sources of a name, recorded per row so a reader can weigh them:

* ``extractor_parties`` -- eyecite named both parties and they appear together
  in the text before the locator.
* ``backward_scan`` -- eyecite named none or one, and an `X v. Y`, `In re X` or
  `Matter of X` was found by reading back from the locator.
* ``extractor_partial`` -- eyecite named one party, found in the text.

`needs_review` marks a row a person should look at before it is used as ground
truth. It is not a claim that the row is wrong; most of the flagged rows are
correct and merely sit somewhere the reader is known to struggle, such as a
table of authorities.

Run it with the corpus root::

    uv run python -m scripts.corpus.build_case_names data/false-citation-bench-v2
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.experimental.relaxed_eyecite_extractor import extract_relaxed_citations

# How far back a name may sit from the citation it belongs to. A table of
# authorities puts the name on the line above; body prose puts it immediately
# before. Beyond this the nearest `v.` usually belongs to a different citation.
LOOKBACK_CHARACTERS = 320

# `Smith v. Jones`, allowing the punctuation and spacing damage these documents
# carry. Party text stops at a citation, a semicolon or a sentence end.
_PARTY = r"[A-Z][A-Za-z0-9.,'’&\- ]{1,90}?"
_VERSUS = re.compile(rf"({_PARTY})\s+v[.s]?\.?\s+({_PARTY})\s*[,(]?\s*$", re.DOTALL)
_ONE_PARTY = re.compile(rf"((?:In\s+re|Matter\s+of|Ex\s+parte)\s+{_PARTY})\s*[,(]?\s*$", re.DOTALL | re.I)

# A row sitting in one of these wants a person's eye before it is trusted.
_TABLE_ROW = re.compile(r"\|")

# A docket number follows the case name and is not part of it: `Turner v.
# Murphy Oil USA, Inc., No. 05-4206`. The name ends before it.
_DOCKET_SUFFIX = re.compile(r",?\s*(?:Civ(?:il)?\.?\s*)?(?:Case\s+)?No[.s]?\s*[A-Z]{0,4}\.?\s*[\d:]+.*$")

# A word the prose puts immediately before a case name, which a backward scan
# then takes for part of it -- `Under Norton v. Shelby County`, `Accord Smith
# v. Jones`. `In re` and `Matter of` are part of a name and are not here.
_LEADING_PROSE = re.compile(
    r"^(?:Under|Accord|Compare|See|Citing|Quoting|But|And|In|Cf|E\.g|Contra)\b[.,]?\s+(?=[A-Z])",
    re.IGNORECASE,
)


def _trim(name: str, start: int) -> tuple[str, int]:
    """Drop what sits around a case name without belonging to it."""
    trimmed = _DOCKET_SUFFIX.sub("", name).rstrip(" ,")
    lead = _LEADING_PROSE.match(trimmed)
    if lead is not None:
        start += lead.end()
        trimmed = trimmed[lead.end() :]
    return trimmed, start


@dataclass(frozen=True, slots=True)
class Name:
    """One case name found in the document, with where it was found."""

    text: str
    start: int
    end: int
    evidence: str


def _grounded(text: str, name: str, before: int) -> tuple[int, int] | None:
    """Where this name occurs in the document, allowing damaged spacing.

    Returns the last occurrence ending at or before ``before``, because a name
    repeated through a filing belongs to the citation it immediately precedes.
    """
    pattern = r"\s+".join(re.escape(piece) for piece in name.split())
    found = None
    for match in re.finditer(pattern, text):
        if match.end() <= before:
            found = match
    return (found.start(), found.end()) if found else None


def _from_extractor(text: str, citation: FullCaseCitation, before: int) -> Name | None:
    """The name eyecite parsed, located in the document rather than trusted."""
    parties = [party for party in (citation.plaintiff, citation.defendant) if party and party.strip()]
    if not parties:
        return None
    joined = f"{citation.plaintiff} v. {citation.defendant}" if len(parties) == 2 else parties[0]
    where = _grounded(text, joined, before)
    if where is None:
        # eyecite normalises spacing, so the joined form may not occur even
        # though the parties do. Fall back to the longest party that does.
        for party in sorted(parties, key=len, reverse=True):
            where = _grounded(text, party, before)
            if where is not None:
                return Name(text[where[0] : where[1]], *where, "extractor_partial")
        return None
    evidence = "extractor_parties" if len(parties) == 2 else "extractor_partial"
    found = text[where[0] : where[1]]
    trimmed, start = _trim(found, where[0])
    return Name(trimmed, start, start + len(trimmed), evidence)


def _from_scan(text: str, before: int) -> Name | None:
    """Read back from the citation for a case name the extractor did not give."""
    window_start = max(0, before - LOOKBACK_CHARACTERS)
    window = text[window_start:before]
    for pattern in (_VERSUS, _ONE_PARTY):
        match = pattern.search(window)
        if match is None:
            continue
        start = window_start + match.start(1)
        end = window_start + match.end(match.lastindex or 1)
        found = text[start:end].strip()
        trimmed, start = _trim(found, start)
        return Name(trimmed, start, start + len(trimmed), "backward_scan")
    return None


def _same(left: Name | None, right: Name | None) -> bool:
    """Whether two readers named the same case, ignoring spacing damage."""
    if left is None or right is None:
        return True
    one, other = " ".join(left.text.split()), " ".join(right.text.split())
    return one == other or one in other or other in one


def _pick(from_extractor: Name | None, from_scan: Name | None) -> Name | None:
    """Which reader's answer to record.

    The extractor wins when it named both parties. When it named only one, a
    scan that found a full `X v. Y` containing that party is naming the same
    case more completely, and is preferred -- eyecite drops the plaintiff on
    captions it parses partially, and half a caption is worse than none for
    comparing against an archive.
    """
    if from_extractor is None:
        return from_scan
    if from_extractor.evidence == "extractor_partial" and from_scan is not None:
        one = " ".join(from_extractor.text.split())
        if one in " ".join(from_scan.text.split()):
            return from_scan
    return from_extractor


def build(corpus: Path) -> list[dict]:
    """One row per locator row in the extraction annotation."""
    rows = [
        json.loads(line)
        for line in (corpus / "derived" / "extraction.jsonl").read_text().splitlines()
        if line
    ]
    locators = [row for row in rows if row.get("kind") == "locator"]
    by_document: dict[str, list[dict]] = {}
    for row in locators:
        by_document.setdefault(row["document"], []).append(row)

    built: list[dict] = []
    for document, group in sorted(by_document.items()):
        text = (corpus / "documents_txt" / document).read_text(encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            extracted = extract_relaxed_citations(text)
        parsed = {
            (item.span.start, item.span.end): item.citation
            for item in extracted.citations
            if isinstance(item.citation, FullCaseCitation)
        }
        for row in sorted(group, key=lambda r: r["span"]["start"]):
            start = row["span"]["start"]
            citation = next(
                (c for (s, e), c in parsed.items() if s <= start < e or abs(s - start) < 2),
                None,
            )
            # Two readers, deliberately. The extractor's parties are precise
            # when eyecite parsed the citation cleanly; the backward scan is
            # the only reader that works when it did not. Where both answer
            # and answer differently, neither is trusted silently -- the row
            # is flagged, because a disagreement here is exactly the kind of
            # misreading that would otherwise be recorded as ground truth.
            from_extractor = _from_extractor(text, citation, start) if citation else None
            from_scan = _from_scan(text, start)
            name = _pick(from_extractor, from_scan)
            built.append(_row(row, name, text, from_extractor, from_scan))
    return built


def _row(
    row: dict,
    name: Name | None,
    text: str,
    from_extractor: Name | None = None,
    from_scan: Name | None = None,
) -> dict:
    """One output row, with the reasons a person might want to look at it."""
    reasons = []
    if not _same(from_extractor, from_scan):
        reasons.append("the two readers disagree")
    if name is None:
        reasons.append("no case name found")
    else:
        line_start = text.rfind("\n", 0, name.start) + 1
        line_end = text.find("\n", name.end)
        if _TABLE_ROW.search(text[line_start : line_end if line_end > 0 else len(text)]):
            reasons.append("table-of-authorities row")
        if name.evidence == "extractor_partial":
            reasons.append("only one party found")
        if row["span"]["start"] - name.end > LOOKBACK_CHARACTERS // 2:
            reasons.append("name is far from the citation")
    return {
        "id": row["id"],
        "document": row["document"],
        "span": row["span"],
        "matched_text": row["matched_text"],
        "case_name_written": name.text if name else None,
        "case_name_span": {"start": name.start, "end": name.end} if name else None,
        "evidence": name.evidence if name else None,
        "needs_review": bool(reasons),
        "review_reason": "; ".join(reasons) or None,
    }


def verify(rows: list[dict], corpus: Path) -> tuple[int, int]:
    """Check every recorded name really is the document's text at its span."""
    texts = {
        row["document"]: (corpus / "documents_txt" / row["document"]).read_text(encoding="utf-8")
        for row in rows
    }
    checked = wrong = 0
    for row in rows:
        if row["case_name_written"] is None:
            continue
        checked += 1
        span = row["case_name_span"]
        if texts[row["document"]][span["start"] : span["end"]] != row["case_name_written"]:
            wrong += 1
        elif span["end"] > row["span"]["start"]:
            wrong += 1
    return checked, wrong


def main() -> None:
    """Write `derived/case_names.jsonl` for one corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="corpus root, e.g. data/false-citation-bench-v2")
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

    rows = build(arguments.corpus)
    checked, wrong = verify(rows, arguments.corpus)
    if wrong:
        msg = f"{wrong} of {checked} recorded names do not slice out of their document"
        raise SystemExit(msg)

    destination = arguments.output or arguments.corpus / "derived" / "case_names.jsonl"
    destination.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    named = sum(1 for row in rows if row["case_name_written"])
    review = sum(1 for row in rows if row["needs_review"])
    disagree = sum(1 for row in rows if "readers disagree" in (row["review_reason"] or ""))
    print(f"wrote {len(rows)} rows to {destination}")
    print(f"  named: {named}  ({len(rows) - named} with no name found)")
    print(f"  verified against the document: {checked} of {checked}")
    print(f"  needing review: {review}  (of which {disagree} because the two readers disagree)")


if __name__ == "__main__":
    main()
