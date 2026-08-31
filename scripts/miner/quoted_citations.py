"""Take the fabricated citations from the orders, which quote them.

The pipeline in `discover.py` and `resolve.py` works towards the filing that
contains the fabrications, and two thirds of those cannot be obtained: RECAP
holds only what somebody already bought from PACER. But a court explaining that
counsel cited invented authority **quotes the citation**, so for the citation
itself the filing is not needed at all. Reading the orders directly gives 254
candidates across 101 cases where the filings route gave 31 across 6, and it is
subject to no availability ceiling.

Two things decide whether a quoted citation is usable.

**It has to be the lawyer's citation, not the judge's.** Orders about
fabrication cite the real sanctions case law in the same paragraphs -- *Mata v.
Avianca* above all -- so a citation introduced by `see also`, `citing` or
`quoting` is the court's own and is skipped. Quotation marks are the signal
that the court is repeating what counsel wrote.

**The case name has to be read correctly, and that is the fragile part.** Two
attempts failed in opposite directions:

* A pattern over the quotation captured sentence text. `527 U.S. 526` was
  reported as fabricated because the pattern took "Kolstad v. Am. D" from
  mid-sentence; it is *Kolstad v. American Dental Ass'n*, cited correctly.
* Rejecting any candidate containing an ordinary word then discarded real
  names. `of`, `the` and `in` are everywhere in captions -- *Miller v. Indiana
  Dep't of Corr.*, *Church of the Lukumi Babalu Aye*, *In re Marcus* -- and
  removing them left a bare surname, too thin to act on.

What works is taking eyecite's parsed parties, rejecting only words that never
appear in a caption, capping the length, and recovering a one-party caption
from the quotation, because eyecite returns `Marcus` for *In re Marcus* and
nothing further.

Output is `local/miner-quoted-all.json`. Judging the citations is a separate
step: the archive answers about a fifth of them offline, and the rest need the
lookup service.
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

ORDERS_DIR = pathlib.Path("local/orders")
OUT = pathlib.Path("local/miner-quoted-all.json")

# A citation the court is relying on rather than condemning.
SUPPORTING = re.compile(r"(see\s+also|see,\s|see\s+e\.?g|citing|quoting|accord|cf\.|compare)\s*$", re.I)
QUOTATION = re.compile(r"[“\"]([^”\"]{10,400})[”\"]")
ALLEGES_FABRICATION = re.compile(
    r"(does\s+not\s+exist|do\s+not\s+exist|non-?existent|fictitious|fabricat\w+|"
    r"hallucinat\w+|could\s+not\s+(?:be\s+)?locate|unable\s+to\s+locate|"
    r"no\s+such\s+case|bogus|made[-\s]up)", re.I)
# Words a sentence uses and a caption never does. `of`, `the` and `in` are
# deliberately absent -- see the module docstring.
SENTENCE_ONLY = re.compile(
    r"\b(cited|recognized|runs|filed|see|court|motion|response|argues|holds|found|"
    r"alleges|claims|supported|squarely|qualifies|confirms|reach|enforce|right)\b", re.I)
ONE_PARTY_PREFIX = re.compile(r"\b(In re|Matter of|Ex parte|Estate of)\s+", re.I)
LONGEST_CAPTION_WORDS = 9


def pdf_text(path: str | pathlib.Path) -> str:
    try:
        done = subprocess.run(["pdftotext", "-q", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
        return done.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def clean_party(name: str | None) -> str | None:
    """One party of a caption, or None if the parse ran into the surrounding prose.

    A party name is read backwards from the citation, so it collects whatever
    precedes it across a line break -- a page stamp, or the tail of a sentence.
    """
    if not name:
        return None
    name = re.split(r"\n\s*\n", name)[-1].replace("\n", " ").strip(" ,;“”\"")
    if not name or SENTENCE_ONLY.search(name):
        return None
    return None if len(name.split()) > LONGEST_CAPTION_WORDS else name


def written_name(citation: FullCaseCitation, quotation: str) -> str | None:
    """The case name as the brief wrote it, as far as it can be recovered."""
    meta = citation.metadata
    plaintiff, defendant = clean_party(meta.plaintiff), clean_party(meta.defendant)
    if plaintiff and defendant:
        return f"{plaintiff} v. {defendant}"
    name = defendant or plaintiff or clean_party(meta.antecedent_guess)
    if not name:
        return None
    # A one-party caption reaches us as the party alone; the prefix is in the text.
    prefix = re.search(ONE_PARTY_PREFIX.pattern + re.escape(name.split(",")[0][:40]),
                       quotation, re.I)
    return prefix.group(0).strip() if prefix else name


def full_citations(text: str) -> list[FullCaseCitation]:
    with redirect_stdout(io.StringIO()):     # eyecite narrates to stdout
        found = get_citations(text)
    return [c for c in found if isinstance(c, FullCaseCitation)
            and all(c.groups.get(k) for k in ("volume", "reporter", "page"))]


def harvest() -> list[dict]:
    parsed = {f"{o['docket_id']}_{o['document_id']}": o
              for o in json.loads(pathlib.Path("local/miner-parsed.json").read_text())}
    rows = []
    for path in sorted(ORDERS_DIR.glob("*.pdf")):
        order = parsed.get(path.stem, {})
        text = pdf_text(path)
        if not ALLEGES_FABRICATION.search(text):
            continue
        for match in QUOTATION.finditer(text):
            quotation = match.group(1)
            if SUPPORTING.search(text[max(0, match.start() - 40):match.start()].strip()):
                continue
            for citation in full_citations(quotation):
                groups = citation.groups
                rows.append({
                    "order": path.stem,
                    "case": order.get("case_name", ""),
                    "court": order.get("court_id", ""),
                    "citation": f"{groups['volume']} {groups['reporter']} {groups['page']}",
                    "written": written_name(citation, quotation),
                    "quoted_as": quotation.replace("\n", " ")[:200],
                })
    return rows


if __name__ == "__main__":
    rows = harvest()
    OUT.write_text(json.dumps(rows, indent=1))
    distinct = {r["citation"] for r in rows}
    named = {r["citation"] for r in rows if r["written"]}
    westlaw = sum(1 for c in distinct if re.match(r"^\d+\s+WL\s", c))
    print(f"orders alleging fabrication : {len({r['order'] for r in rows})}")
    print(f"quoted candidates           : {len(rows)}  ({len(distinct)} distinct)")
    print(f"  with a usable case name   : {len(named)}")
    print(f"  Westlaw, uncheckable      : {westlaw}")
    print(f"cases                       : {len({r['case'] or r['order'] for r in rows})}")
