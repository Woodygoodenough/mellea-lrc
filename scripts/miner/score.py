"""Score a promoted filing against what the court said about it.

The established corpus is scored against a published benchmark's annotations.
A mined filing has no benchmark entry, but it has something a benchmark cannot
give: a judge stated, in an order on the same docket, which of its citations
were fabricated. So the question here is not whether the pipeline agrees with
an annotator, it is whether the pipeline flags what a court flagged.

Two cautions on reading the numbers.

**The court's list is a floor, not a complete labelling.** An order says enough
to justify the sanction. It quotes some of the invented citations and describes
the rest -- "more than three dozen" -- so a citation the order does not name is
not thereby sound, and recall against this list overstates nothing but cannot
be read as recall against the truth.

**A label is a citation together with the name written beside it, not the
citation alone.** The order names citations on a docket, and the same volume
and page can appear in another filing cited correctly. `539 F. App'x 937` is
condemned in one filing, where it is written *United States v. Baker*, and
cited soundly in another as *Williams v. Morahan* -- which is the case actually
printed there. Matching on the locator alone scores that sound citation as a
miss, and the pipeline is marked wrong for agreeing with the reporter.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

CORPUS = pathlib.Path("local/mined-corpus")
SERIALIZED = pathlib.Path("local/mined-serialized")
MANIFEST = CORPUS / "manifest.json"

# Anything the pipeline did not conclude was sound.
FLAGGED = {"mismatch", "not_found", "refuted", "unresolved", "ambiguous"}
"""Every verdict that is not "this citation is sound".

`possible_match` is deliberately absent: it is the pipeline declining to
decide, and counting it as a catch would score indecision as detection.
"""


def locator_key(citation: str) -> str:
    """A citation reduced to what identifies it: volume, reporter, page."""
    return re.sub(r"[^a-z0-9]", "", (citation or "").lower())


def _validated(document: str) -> dict[str, str]:
    """Each citation the pipeline validated in one document, and its verdict."""
    path = SERIALIZED / f"{document}.json"
    if not path.exists():
        return {}
    run = json.loads(path.read_text())
    verdicts: dict[str, tuple[str, str | None]] = {}
    for citation in run.get("citations", []):
        aggregation = citation.get("aggregation") or {}
        outcome = aggregation.get("overall_outcome") or "unknown"
        # A citation that resolved to nothing carries no candidates, and those
        # are precisely the fabricated ones -- reading only the candidate list
        # makes the pipeline's clearest finding invisible. The locator it
        # looked up is on the lookup node.
        name = next((c.get("extracted_case_name") for c in aggregation.get("candidates") or []
                     if c.get("extracted_case_name")), None)
        for node in citation.get("nodes", []):
            locator = node.get("locator")
            if locator:
                verdicts.setdefault(locator_key(locator), (outcome, name))
        for candidate in aggregation.get("candidates") or []:
            written = candidate.get("extracted_citation")
            if written:
                verdicts[locator_key(written)] = (outcome, name)
    return verdicts


def _same_case(written: str | None, cited: str | None) -> bool:
    """Whether two names refer to the same case, tolerantly.

    Both come from imperfect extraction, so this asks only whether they share a
    distinctive word rather than whether they agree as captions.
    """
    if not written or not cited:
        return True                      # nothing to separate them on
    stop = {"the", "of", "and", "state", "united", "states", "commonwealth",
            "city", "county", "inc", "corp", "co", "llc"}
    def words(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in stop and len(w) > 3}
    a, b = words(written), words(cited)
    return not (a and b) or bool(a & b)


def refused(document: str) -> int:
    """Citations in one run whose lookup was refused rather than answered.

    A refused citation is not a verdict. Counting one as "the pipeline did not
    flag it" reads a rate limit as a judgement, so a document holding any is
    reported separately rather than mixed into the measurement.
    """
    path = SERIALIZED / f"{document}.json"
    if not path.exists():
        return 0
    run = json.loads(path.read_text())
    return sum(1 for citation in run.get("citations", [])
               for node in citation.get("nodes", [])
               if node.get("status") == "failed")


def score() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text())
    rows = []
    for entry in manifest:
        if "error" in entry:
            continue
        verdicts = _validated(entry["document"])
        if not verdicts:
            continue
        # A docket-level label only applies here if this document wrote the
        # same case name beside the citation.
        present, caught = set(), set()
        for named in entry.get("court_named_citations", []):
            key = locator_key(named["citation"])
            if key not in verdicts:
                continue
            outcome, cited_as = verdicts[key]
            if not _same_case(named.get("written"), cited_as):
                continue
            present.add(key)
            if outcome in FLAGGED:
                caught.add(key)
        named = {locator_key(c["citation"]) for c in entry.get("court_named_citations", [])}
        rows.append({
            "document": entry["document"],
            "refused": refused(entry["document"]),
            "case": entry.get("case", ""),
            "citations_validated": len(verdicts),
            "flagged_by_pipeline": sum(1 for v, _ in verdicts.values() if v in FLAGGED),
            "court_named": len(named),
            "court_named_in_this_document": len(present),
            "court_named_and_caught": len(caught),
            "missed": sorted(present - caught),
        })
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    rows = score()
    complete = [row for row in rows if not row["refused"]]
    partial = [row for row in rows if row["refused"]]
    total = collections.Counter()
    for row in complete:
        for key in ("citations_validated", "flagged_by_pipeline",
                    "court_named_in_this_document", "court_named_and_caught"):
            total[key] += row[key]
        if args.verbose:
            print(f"  {row['document']:<18} {row['citations_validated']:>3} cites"
                  f"  {row['flagged_by_pipeline']:>3} flagged"
                  f"  {row['court_named_and_caught']}/{row['court_named_in_this_document']} court-named caught")
    print(f"\ndocuments fully checked       : {len(complete)}"
          f"   (excluded, holding refusals: {len(partial)})")
    print(f"citations validated           : {total['citations_validated']}")
    print(f"flagged by the pipeline       : {total['flagged_by_pipeline']}")
    print(f"court-named, present here     : {total['court_named_in_this_document']}")
    print(f"  of those, pipeline caught   : {total['court_named_and_caught']}")
