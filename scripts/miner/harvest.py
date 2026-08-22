"""Run discovery and resolution over a batch, and report what is actually reachable.

Prints one line per docket and a summary. The summary is the point: resolution
succeeding is not the same as the offending filing being obtainable, because
RECAP holds only what somebody has already bought and contributed.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from scripts.miner.resolve import accused_entries

BASE = os.environ["COURTLISTENER_BASE_URL"].rstrip("/")
OUT = pathlib.Path(sys.argv[1])
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 20
OUT.mkdir(parents=True, exist_ok=True)
PAUSE = 2.0


def api(path: str, params: dict[str, str]) -> dict:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as response:
        return json.load(response)


def pdf_text(filepath: str) -> str:
    import pypdfium2

    target = OUT / "pdf" / filepath.replace("/", "_")
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen("https://storage.courtlistener.com/" + filepath, timeout=300) as response:
            target.write_bytes(response.read())
    document = pypdfium2.PdfDocument(str(target))
    try:
        return "\n".join(document[i].get_textpage().get_text_range() for i in range(len(document)))
    finally:
        document.close()


complaints = json.loads((OUT / "complaints.json").read_text())
# An order is where a court makes the finding; a brief that merely uses the
# phrase is usually arguing, not adjudicating.
orders = [c for c in complaints if re.search(r"order", c["description"] or "", re.I)]
seen: set[int] = set()
rows = []
spent = 0

for complaint in orders:
    if len(rows) >= LIMIT:
        break
    if complaint["docket_id"] in seen or not complaint["is_available"]:
        continue
    seen.add(complaint["docket_id"])
    try:
        text = pdf_text(complaint["filepath"])
    except Exception as error:
        print(f"  {complaint['case_name'][:40]}: could not read the order ({error})", flush=True)
        continue

    accused = accused_entries(text, exclude=complaint["entry_number"])
    row = {
        "case": complaint["case_name"],
        "court": complaint["court_id"],
        "docket_id": complaint["docket_id"],
        "order_entry": complaint["entry_number"],
        "accused": list(accused),
        "reachable": [],
    }
    if accused:
        try:
            payload = api("recap-documents/", {"docket_entry__docket__id": str(complaint["docket_id"])})
            spent += 1
            wanted = {str(n) for n in accused}
            row["reachable"] = [
                {"entry": r.get("document_number"), "filepath": r.get("filepath_local")}
                for r in payload.get("results", [])
                if str(r.get("document_number")) in wanted and r.get("is_available")
            ]
            time.sleep(PAUSE)
        except Exception as error:
            row["error"] = str(error)
    rows.append(row)
    print(
        f"  {complaint['court_id']:6} {complaint['case_name'][:38]:40} "
        f"order#{complaint['entry_number']} accuses {list(accused) or '-'} "
        f"reachable {[r['entry'] for r in row['reachable']]}",
        flush=True,
    )

(OUT / "harvest.json").write_text(json.dumps(rows, indent=1))
with_accused = [r for r in rows if r["accused"]]
with_reachable = [r for r in rows if r["reachable"]]
print(f"\norders read                       : {len(rows)}")
print(f"  named an offending filing       : {len(with_accused)}")
print(f"  offending filing downloadable   : {len(with_reachable)}")
print(f"api requests spent                : {spent}")
print("HARVEST DONE", flush=True)
