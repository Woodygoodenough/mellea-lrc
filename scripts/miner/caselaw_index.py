"""Turn the local Caselaw Access Project volumes into a page index.

`local/cap/` holds published reporter volumes as JSON, one file per volume,
named `{reporter-slug}-{volume}.json`. Each case in a file carries its first
page, last page, and a short name. That is enough to answer the only question
the miner needs to ask offline: *is there really a case by that name starting
on that page?*

Two things about the data decide how this is built.

**The file, not the citation, is the authority for what we hold.** A volume we
have never downloaded still appears in the data, because cases cite across
reporters -- a F.3d opinion citing a Va. App. case puts "26 Va. App. 505" into
the text of `f3d-*.json`. An index built by scanning every citation string
therefore claims coverage it does not have, and every absent page then reads as
a fabrication. Only a volume with its own file is held.

**A file names its own reporter.** The filename slug and the reporter as
written in a citation do not agree (`f-supp-3d` against `F. Supp. 3d`), and the
slug is not a reliable key. Instead each file votes: among the citations whose
volume number matches the filename's, the most common reporter is what this
file is. That keys the index the same way a citation parsed out of a PDF will
be keyed, so lookups match.

Output is `local/cap-index.json`: `"{reporter}|{volume}" -> [[first, last, name], ...]`
with the reporter stripped of periods and spaces.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import pathlib
import re

CAP_DIR = pathlib.Path("local/cap")
OUT = pathlib.Path("local/cap-index.json")

_VOLUME_FILE = re.compile(r"(.+)-(\d+)\.json$")
_CITE = re.compile(r"\*?\[?(\d+)\s+(.+?)\s+(\d+)$")


def normalise_reporter(reporter: str) -> str:
    """Strip periods and spaces so `F. Supp. 3d` and `F.Supp.3d` share a key."""
    return re.sub(r"[.\s]", "", reporter)


def _reporter_of(cases: list[dict], volume: str) -> str | None:
    """Which reporter this file is, decided by its own cases rather than its name."""
    votes: collections.Counter[str] = collections.Counter()
    for case in cases:
        for citation in case.get("citations") or []:
            match = _CITE.match((citation.get("cite") or "").strip())
            if match and match.group(1) == volume:
                votes[normalise_reporter(match.group(2))] += 1
    return votes.most_common(1)[0][0] if votes else None


def build() -> dict[str, list]:
    index: dict[str, list] = {}
    for path in sorted(glob.glob(str(CAP_DIR / "*.json"))):
        name_match = _VOLUME_FILE.match(os.path.basename(path))
        if not name_match:
            continue
        volume = name_match.group(2)
        try:
            cases = json.load(open(path, errors="ignore"))
        except (json.JSONDecodeError, OSError):
            continue
        reporter = _reporter_of(cases, volume)
        if reporter is None:
            continue
        entries = []
        for case in cases:
            first, last = str(case.get("first_page", "")), str(case.get("last_page", ""))
            if not first.isdigit():
                continue
            entries.append([
                int(first),
                int(last) if last.isdigit() else int(first),
                case.get("name_abbreviation", ""),
            ])
        index[f"{reporter}|{volume}"] = entries
    return index


if __name__ == "__main__":
    index = build()
    OUT.write_text(json.dumps(index))
    print(f"volumes indexed: {len(index)}  cases: {sum(len(v) for v in index.values())}")
