"""Check citations against the published record we hold, without spending API budget.

Given a PDF, every full case citation in it is asked one question: does the
case named in the citation really begin on that page of that volume? The page
index built by `caselaw_index.py` answers it offline.

Each citation lands in one of these:

| verdict | meaning |
|---|---|
| `volume-not-held` | we do not have that volume; no opinion offered |
| `no-name-parsed` | a citation with no recoverable party names |
| `name-match` | a case with a matching name starts on that page |
| `pin-cite-ok` | the page falls inside the named case, so it is a pin cite |
| `NAME-MISMATCH` | a case starts there, under a different name |
| `PAGE-INSIDE-OTHER-CASE` | the page falls inside some other case |
| `PAGE-ABSENT` | no case occupies that page at all |

**The last three are suspicions, not findings.** Measured against 120 court
orders -- whose citations judges wrote and which are therefore almost all
genuine -- this flags 3.3% of the citations it judges. That is the false
positive rate, and it does not come from a tunable threshold. Courts name the
same case in several legitimate ways:

- *NAACP v. Button* is published as "National Ass'n for the Advancement of
  Colored People v. Button"
- sealed matters are published as "Under Seal v. United States" while briefs
  cite them as "In re Grand Jury Subpoena"
- consolidated litigation is published under party names while briefs cite the
  "In re ..." caption

All three are correct citations that this check calls mismatches. Resolving the
citation through CourtListener handles the variants properly and remains the
deciding test. Use this to rank suspects cheaply, not to declare fabrication.

One caution when using court orders as a control: an order about fabricated
citations quotes the fabrications, so a few control flags are real fakes rather
than errors, and the true false positive rate is a little below what it
measures.
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import subprocess
from contextlib import redirect_stdout

from eyecite import get_citations
from eyecite.models import FullCaseCitation

from scripts.miner.caselaw_index import normalise_reporter

INDEX_PATH = pathlib.Path("local/cap-index.json")

SUSPICIOUS = ("NAME-MISMATCH", "PAGE-INSIDE-OTHER-CASE", "PAGE-ABSENT")

# Words shared by too many captions to identify a case.
_GENERIC = {
    "in", "re", "ex", "rel", "vs", "the", "of", "and", "state", "states",
    "united", "commonwealth", "com", "people", "city", "county", "inc", "llc",
    "co", "corp", "ltd", "et", "al", "dept", "department", "board", "bd",
    "estate", "matter", "no", "america",
}


def name_tokens(text: str | None) -> set[str]:
    """The words in a caption that actually distinguish one case from another."""
    return {w for w in re.findall(r"[a-z]+", (text or "").lower())
            if w not in _GENERIC and len(w) > 2}


def pdf_text(path: str | pathlib.Path) -> str:
    """Layout-preserving text, via poppler's pdftotext."""
    try:
        done = subprocess.run(["pdftotext", "-q", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
        return done.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def check_text(text: str, index: dict) -> list[tuple[str, str]]:
    """Classify every full case citation in `text`. Returns (verdict, description)."""
    with redirect_stdout(io.StringIO()):     # eyecite narrates to stdout
        citations = get_citations(text)

    results = []
    for citation in citations:
        if not isinstance(citation, FullCaseCitation):
            continue
        groups = citation.groups
        if not all(groups.get(k) for k in ("volume", "reporter", "page")):
            continue
        if not groups["page"].isdigit():
            continue

        reporter = normalise_reporter(groups["reporter"])
        key = f"{reporter}|{groups['volume']}"
        described = f"{groups['volume']} {reporter} {groups['page']}"
        if key not in index:
            results.append(("volume-not-held", described))
            continue

        page = int(groups["page"])
        meta = citation.metadata
        claimed = (name_tokens(meta.plaintiff) | name_tokens(meta.defendant)
                   | name_tokens(meta.antecedent_guess))
        if not claimed:
            results.append(("no-name-parsed", described))
            continue

        starting = [e for e in index[key] if e[0] == page]
        containing = [e for e in index[key] if e[0] <= page <= e[1]]

        if starting:
            matched = any(claimed & name_tokens(e[2]) for e in starting)
            results.append(("name-match" if matched else "NAME-MISMATCH",
                            described + f" | published as: {starting[0][2]}"))
        elif containing:
            # A pin cite landing inside the case actually named is benign.
            if any(claimed & name_tokens(e[2]) for e in containing):
                results.append(("pin-cite-ok", described))
            else:
                results.append(("PAGE-INSIDE-OTHER-CASE",
                                described + f" | page sits in: {containing[0][2]}"))
        else:
            results.append(("PAGE-ABSENT", described))
    return results


def check_pdfs(paths, index: dict) -> tuple[collections.Counter, list]:
    tally: collections.Counter[str] = collections.Counter()
    flagged = []
    for path in paths:
        for verdict, described in check_text(pdf_text(path), index):
            tally[verdict] += 1
            if verdict in SUSPICIOUS:
                flagged.append([pathlib.Path(path).name, verdict, described])
    return tally, flagged


def report(tally: collections.Counter, label: str) -> None:
    judged = sum(tally[k] for k in
                 ("name-match", "pin-cite-ok", *SUSPICIOUS))
    print(f"\n== {label}")
    for verdict, count in tally.most_common():
        print(f"   {count:5d}  {verdict}")
    if judged:
        bad = sum(tally[k] for k in SUSPICIOUS)
        print(f"   -> flagged {bad}/{judged} = {100 * bad / judged:.1f}% of judged citations")


if __name__ == "__main__":
    import glob
    index = json.loads(INDEX_PATH.read_text())
    accused_tally, accused_flags = check_pdfs(sorted(glob.glob("local/accused/*.pdf")), index)
    report(accused_tally, "accused filings")
    control_tally, control_flags = check_pdfs(sorted(glob.glob("local/orders/*.pdf"))[:120], index)
    report(control_tally, "court orders (control -- judges' own citations)")
    pathlib.Path("local/miner-namecheck.json").write_text(
        json.dumps({"accused": accused_flags, "orders": control_flags}, indent=1))
