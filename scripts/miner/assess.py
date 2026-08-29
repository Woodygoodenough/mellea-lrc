"""Assess the mined corpus: which pairings hold, and which citations are contradicted.

Three questions, each answered over the filings already downloaded, and none of
them needing API allowance.

**Is the pairing right?** The order that complains and the filing that offends
are different entries. A filing sharing citations with the order accusing it is
corroborated; one sharing none may be the wrong entry.

**Is it even a party filing?** Six of the 44 downloaded entries are court
documents -- the resolver picked another order rather than the offending brief.
They must be excluded from every measurement, because an order about fabricated
citations quotes them and therefore looks exactly like a guilty filing. The
single most incriminating document in the corpus, at 5 contradicted citations
of 11 judged, was a memorandum opinion listing the 42 invented authorities it
was striking.

**Do the two independent signals agree?** A citation the judge quoted as
fabricated (`local/miner-fakes.json`) and which the printed record also
contradicts is confirmed twice over. The two methods are complementary: over
entry 353 of *Superb Motors*, quotation found *In re Marcus* and missed *In re
Amica*, while the archive found both.

Writes `local/miner-assessment.json`.
"""

from __future__ import annotations

import collections
import glob
import io
import json
import pathlib
import re
import subprocess
from contextlib import redirect_stdout

from eyecite import get_citations
from eyecite.models import FullCaseCitation

from mellea_lrc.caselaw import CapIndex

from scripts.miner.archive_check import SUSPICIOUS, check_text, known_slugs, pdf_text

ACCUSED_DIR = pathlib.Path("local/accused")
ORDERS_DIR = pathlib.Path("local/orders")
CAP_DIR = pathlib.Path("local/cap")

_COURT_DOCUMENT = re.compile(r"(?i)\b(memorandum opinion|opinion|order|signed by|show cause)\b")
_PARTY_FILING = re.compile(
    r"(?i)\b(motion|memorandum in (opposition|support)|response|reply|brief"
    r"|petition|complaint|declaration)\b"
)


def is_court_document(description: str) -> bool:
    """Whether a docket description names something the court wrote.

    Checked in this order because a description routinely carries both -- a
    `MEMORANDUM in Opposition ... Signed by` is a party filing. Naming a party
    document wins.
    """
    if _PARTY_FILING.search(description or ""):
        return False
    return bool(_COURT_DOCUMENT.search(description or ""))


def _normalise(citation: str) -> str:
    return re.sub(r"[^a-z0-9]", "", citation.lower())


def full_citations(text: str) -> set[str]:
    """Every full case citation in `text`, as `volume reporter page`."""
    with redirect_stdout(io.StringIO()):
        found = get_citations(text)
    out = set()
    for citation in found:
        if not isinstance(citation, FullCaseCitation):
            continue
        groups = citation.groups
        if all(groups.get(k) for k in ("volume", "reporter", "page")):
            out.add(_normalise(f"{groups['volume']}{groups['reporter']}{groups['page']}"))
    return out


def assess() -> dict:
    entries = {f"{e['docket_id']}_{e['entry']}": e
               for e in json.loads(pathlib.Path("local/miner-accused.json").read_text())}
    parsed = json.loads(pathlib.Path("local/miner-parsed.json").read_text())
    orders_by_docket = collections.defaultdict(list)
    for order in parsed:
        orders_by_docket[order["docket_id"]].append(order)

    quoted = collections.defaultdict(set)
    for pair in json.loads(pathlib.Path("local/miner-fakes.json").read_text()):
        quoted[f"{pair['docket']}_{pair['entry']}"].add(_normalise(pair["citation"]))

    slugs = known_slugs(CAP_DIR)
    index = CapIndex(cache_dir=CAP_DIR, allow_fetch=False)

    rows = []
    for path in sorted(ACCUSED_DIR.glob("*.pdf")):
        stem = path.stem
        entry = entries.get(stem, {})
        text = pdf_text(path)
        cites = full_citations(text)

        # citations of the order or orders that accuse this entry
        order_cites: set[str] = set()
        docket_id = entry.get("docket_id")
        for order in orders_by_docket.get(docket_id, []):
            if entry.get("entry") not in (order.get("accused_entries") or []):
                continue
            order_path = ORDERS_DIR / f"{order['docket_id']}_{order['document_id']}.pdf"
            if order_path.exists():
                order_cites |= full_citations(pdf_text(order_path))

        contradicted, judged = set(), set()
        for outcome, described in check_text(text, index, slugs):
            key = described.split("|")[0].strip()
            if outcome.startswith("starts-a-case") or outcome in ("pin-cite-ok", *SUSPICIOUS):
                judged.add(key)
            if outcome in SUSPICIOUS:
                contradicted.add(key)

        rows.append({
            "entry": stem,
            "case": entry.get("case_name", ""),
            "court": entry.get("court", ""),
            "court_document": is_court_document(entry.get("desc", "")),
            "citations": len(cites),
            "shared_with_order": len(cites & order_cites),
            "judged": len(judged),
            "contradicted": sorted(contradicted),
            "also_quoted_as_fake": sorted(
                c for c in contradicted if _normalise(c) in quoted.get(stem, set())),
        })
    return {"filings": rows}


def report(assessment: dict) -> None:
    rows = assessment["filings"]
    party = [r for r in rows if not r["court_document"]]

    print(f"downloaded entries              : {len(rows)}")
    print(f"  court documents (excluded)    : {len(rows) - len(party)}")
    print(f"  party filings                 : {len(party)}")
    print(f"    sharing citations with order: {sum(1 for r in party if r['shared_with_order'])}")
    print(f"    with no citations at all    : {sum(1 for r in party if not r['citations'])}")

    contradicted = sum(len(r["contradicted"]) for r in party)
    judged = sum(r["judged"] for r in party)
    print(f"\ncontradicted by the printed record: {contradicted} of {judged} judged"
          f" ({100 * contradicted / judged:.1f}%)" if judged else "")

    doubly = [(r, c) for r in party for c in r["also_quoted_as_fake"]]
    print(f"confirmed by court and archive    : {len(doubly)}")
    for row, citation in doubly:
        print(f"   {citation:22s} {row['case']} ({row['court']}) entry {row['entry']}")


if __name__ == "__main__":
    assessment = assess()
    pathlib.Path("local/miner-assessment.json").write_text(json.dumps(assessment, indent=1))
    report(assessment)
