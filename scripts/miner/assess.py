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
OCR_DIR = pathlib.Path("local/accused-ocr")
"""Text recovered from filings that were scanned rather than filed digitally.

A scan carries its citations as pixels, so it reads as a filing citing nothing
-- which is otherwise the signature of the wrong docket entry. Running OCR over
the six in this corpus recovered 66 citations that were being counted as absent.
"""
ORDERS_DIR = pathlib.Path("local/orders")
CAP_DIR = pathlib.Path("local/cap")

_COURT_DOCUMENT = re.compile(r"(?i)\b(memorandum opinion|opinion|order|signed by|show cause)\b")
_PARTY_FILING = re.compile(
    r"(?i)\b(motion|memorandum in (opposition|support)|response|reply|brief"
    r"|petition|complaint|declaration)\b"
)
# A description opening with one of these is the court speaking whatever else it
# goes on to mention. `MEMORANDUM OPINION re 35 Special Motion to Dismiss` names
# a motion, and reading that as a party filing lets an opinion into the corpus.
_COURT_OPENING = re.compile(r"(?i)^\s*(memorandum opinion|opinion and order|opinion|order)\b")
# The filing that answers a show-cause order is not the filing that provoked it.
# It is counsel's explanation, filed after the accusation and usually citing
# nothing at all -- which is why every one of these arrived with no citations.
_ANSWERS_THE_ORDER = re.compile(
    # A docket description interleaves cross-references -- "RESPONSE to re 187
    # to the Court's Order to Show Cause" -- so the two halves cannot be
    # required to sit next to each other.
    r"(?:response|reply|answer)\b.{0,60}?\border\s+to\s+show\s+cause"
    r"|(?:response|reply)\s+to\s+show\s+cause"
    r"|in\s+response\s+to\s+(?:the\s+)?court'?s?\s+order"
    r"|motion\s+for\s+leave\s+to\s+correct",
    re.IGNORECASE,
)


def is_court_document(description: str) -> bool:
    """Whether a docket description names something the court wrote.

    A description routinely carries both, so what it *opens* with decides. An
    order or opinion names the motion it rules on, and matching "motion"
    anywhere in the text let those into the corpus as party filings.
    """
    text = description or ""
    if _COURT_OPENING.search(text):
        return True
    if _PARTY_FILING.search(text):
        return False
    return bool(_COURT_DOCUMENT.search(text))


def answers_the_order(description: str) -> bool:
    """Whether this filing is the reply to the accusation rather than its cause.

    A show-cause order names two things in one sentence: the filing that
    contained the fabricated citations, and the response it demands. The
    resolver has no way to tell them apart from the sentence alone, and it
    picked the response often enough to be the largest single source of wrong
    pairings -- every one of them arriving with no citations in it at all,
    because an apology cites nothing.
    """
    return bool(_ANSWERS_THE_ORDER.search(description or ""))


# A born-digital filing runs to thousands of characters a page. A scan with no
# text layer yields only the header stamp RECAP adds, which is under a hundred.
# The distinction matters because a scan reads as a filing with no citations in
# it, which is otherwise the signature of the wrong docket entry.
SCANNED_CHARS_PER_PAGE = 200


def page_count(path: pathlib.Path) -> int:
    """Pages in a PDF, or 0 if it cannot be read."""
    try:
        done = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return 0
    for line in done.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


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
    # Entries reached through the widened reader are recorded separately, in the
    # shape that lookup returns rather than the shape resolution produced.
    candidates = pathlib.Path("local/miner-candidates.json")
    if candidates.exists():
        for stem, found in json.loads(candidates.read_text()).items():
            if "error" in found or stem in entries:
                continue
            entries[stem] = {
                "docket_id": found["docket"],
                "entry": found["entry"],
                "desc": found.get("desc", ""),
                "case_name": "",
                "court": "",
                "available": found.get("available", False),
            }
    parsed = json.loads(pathlib.Path("local/miner-parsed.json").read_text())
    orders_by_docket = collections.defaultdict(list)
    for order in parsed:
        orders_by_docket[order["docket_id"]].append(order)
    # An order that named no entry has its candidates recorded by the widened
    # reader instead, so the pairing for those filings lives there. Without it
    # every widened filing reads as corroborated by nothing.
    widened = pathlib.Path("local/miner-widened.json")
    if widened.exists():
        for order in json.loads(widened.read_text()):
            orders_by_docket[order["docket_id"]].append({
                "docket_id": order["docket_id"],
                "document_id": order["document_id"],
                "accused_entries": order.get("accused_entries") or [],
            })

    quoted = collections.defaultdict(set)
    for pair in json.loads(pathlib.Path("local/miner-fakes.json").read_text()):
        quoted[f"{pair['docket']}_{pair['entry']}"].add(_normalise(pair["citation"]))

    slugs = known_slugs(CAP_DIR)
    index = CapIndex(cache_dir=CAP_DIR, allow_fetch=False)

    rows = []
    for path in sorted(ACCUSED_DIR.glob("*.pdf")):
        stem = path.stem
        entry = entries.get(stem, {})
        recognised = OCR_DIR / f"{stem}.txt"
        text = pdf_text(path)
        if recognised.exists() and len(recognised.read_text()) > len(text):
            text = recognised.read_text()
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

        pages = page_count(path)
        rows.append({
            "entry": stem,
            "pages": pages,
            "chars": len(text),
            "scanned": bool(pages and len(text) / pages < SCANNED_CHARS_PER_PAGE),
            "case": entry.get("case_name", ""),
            "court": entry.get("court", ""),
            "court_document": is_court_document(entry.get("desc", "")),
            "answers_the_order": answers_the_order(entry.get("desc", "")),
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
    party = [r for r in rows
             if not r["court_document"] and not r["answers_the_order"]]

    print(f"downloaded entries              : {len(rows)}")
    print(f"  court documents (excluded)    : {sum(1 for r in rows if r['court_document'])}")
    print(f"  answers to the order (excluded): {sum(1 for r in rows if r['answers_the_order'] and not r['court_document'])}")
    print(f"  offending filings             : {len(party)}")
    print(f"    sharing citations with order: {sum(1 for r in party if r['shared_with_order'])}")
    empty = [r for r in party if not r["citations"]]
    print(f"    with no citations at all    : {len(empty)}"
          f"  ({sum(1 for r in empty if r['scanned'])} of them scans with no text layer)")

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
