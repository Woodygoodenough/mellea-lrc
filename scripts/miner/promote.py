"""Turn a mined filing into the same shape as the established corpus.

The established corpus is a directory of `.txt` documents that
`evaluations/validation/run_mellea_lrc.py` reads and validates. A mined filing
is a PDF pulled from RECAP, so promoting one means running it through the same
preprocessing the pipeline uses on any PDF and writing the text out under a
name that keeps its provenance.

**What a mined case adds that the established corpus cannot.** The established
documents are scored against a published benchmark's labels. A mined filing
comes with something different and, for this purpose, better: a judge has said
in an order which of its citations were fabricated. That makes each promoted
document a small labelled test -- not "does the pipeline agree with an
annotator", but "does the pipeline flag what a court flagged".

The manifest records those labels alongside the provenance, so a promoted
document can be scored without going back to the orders.

Only filings that pass the gates in `assess.py` are promoted: a court document
or a reply to a show-cause order is not the filing that contained the
fabrications, and neither belongs in a corpus of offending filings.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

from mellea_lrc.preprocessing import preprocess

from scripts.miner.assess import answers_the_order, is_court_document

ACCUSED_DIR = pathlib.Path("local/accused")
CORPUS_DIR = pathlib.Path("local/mined-corpus")
MANIFEST = CORPUS_DIR / "manifest.json"


def _entries() -> dict[str, dict]:
    """Provenance for every downloaded entry, from both routes that produce them."""
    entries = {f"{e['docket_id']}_{e['entry']}": e
               for e in json.loads(pathlib.Path("local/miner-accused.json").read_text())}
    candidates = pathlib.Path("local/miner-candidates.json")
    if candidates.exists():
        for stem, found in json.loads(candidates.read_text()).items():
            if "error" in found or stem in entries:
                continue
            entries[stem] = {"docket_id": found["docket"], "entry": found["entry"],
                             "desc": found.get("desc", ""), "case_name": "", "court": ""}
    return entries


def _court_named_citations() -> dict[int, list[dict]]:
    """Citations a court quoted as fabricated, keyed by docket.

    Keyed by docket rather than by entry because the order names the citation,
    not which of the docket's filings it sits in. Matching it to a filing is
    the promoted document's job, not the manifest's.
    """
    named: dict[int, list[dict]] = collections.defaultdict(list)
    quoted = pathlib.Path("local/miner-quoted-all.json")
    if not quoted.exists():
        return named
    orders = {f"{o['docket_id']}_{o['document_id']}": o["docket_id"]
              for o in json.loads(pathlib.Path("local/miner-parsed.json").read_text())}
    for row in json.loads(quoted.read_text()):
        docket = orders.get(row["order"])
        if docket is not None:
            named[docket].append({"citation": row["citation"], "written": row["written"]})
    return named


def promotable() -> list[tuple[pathlib.Path, dict]]:
    """Every downloaded filing that is the offending filing rather than a reply or an order."""
    entries = _entries()
    out = []
    for path in sorted(ACCUSED_DIR.glob("*.pdf")):
        entry = entries.get(path.stem)
        if entry is None:
            continue
        description = entry.get("desc", "")
        if is_court_document(description) or answers_the_order(description):
            continue
        out.append((path, entry))
    return out


def promote(limit: int | None = None) -> list[dict]:
    """Preprocess each promotable filing into the corpus, recording its provenance."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    already = {row["document"] for row in manifest}
    named = _court_named_citations()

    # Preprocessing is the expensive half -- about twenty seconds of OCR per
    # filing -- so a document whose text is already written is never run again.
    # Recovering its manifest row from the text on disk costs nothing, and
    # without it an interrupted run repeats work it has already done.
    entries = _entries()
    for text_file in sorted(CORPUS_DIR.glob("*.txt")):
        if text_file.stem in already:
            continue
        entry = entries.get(text_file.stem)
        if entry is None:
            continue
        body = text_file.read_text(encoding="utf-8")
        manifest.append({
            "document": text_file.stem, "docket_id": entry["docket_id"], "entry": entry["entry"],
            "case": entry.get("case_name", ""), "court": entry.get("court", ""),
            "description": entry.get("desc", "")[:160], "characters": len(body),
            "court_named_citations": named.get(entry["docket_id"], []),
        })
        already.add(text_file.stem)
    MANIFEST.write_text(json.dumps(manifest, indent=1))

    promoted = 0
    for path, entry in promotable():
        if path.stem in already:
            continue
        if limit is not None and promoted >= limit:
            break
        text_path = CORPUS_DIR / f"{path.stem}.txt"
        try:
            document = preprocess(path)
        except Exception as failure:                      # a scan, or a PDF docling refuses
            manifest.append({"document": path.stem, "error": str(failure)[:120]})
            promoted += 1
            continue
        text_path.write_text(document.text, encoding="utf-8")
        manifest.append({
            "document": path.stem,
            "docket_id": entry["docket_id"],
            "entry": entry["entry"],
            "case": entry.get("case_name", ""),
            "court": entry.get("court", ""),
            "description": entry.get("desc", "")[:160],
            "characters": len(document.text),
            "court_named_citations": named.get(entry["docket_id"], []),
        })
        promoted += 1
        MANIFEST.write_text(json.dumps(manifest, indent=1))    # survive a kill
        print(f"  {path.stem:<18} {len(document.text):>7} chars"
              f"  {len(named.get(entry['docket_id'], [])):>3} court-named citations", flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Promote at most this many new filings; omit for all.")
    args = parser.parse_args()
    manifest = promote(limit=args.limit)
    failed = [r for r in manifest if "error" in r]
    print(f"\ncorpus holds {len(manifest) - len(failed)} documents"
          f"  ({len(failed)} could not be preprocessed)")
    print(f"  with at least one court-named citation: "
          f"{sum(1 for r in manifest if r.get('court_named_citations'))}")
