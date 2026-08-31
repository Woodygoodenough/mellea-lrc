"""Check the citations in a mined filing against the printed reporters.

This is the miner's use of :mod:`mellea_lrc.caselaw`, which already holds the
careful parts: page outcomes that distinguish "no case there" from "a different
case there" (:class:`~mellea_lrc.caselaw.PageOutcome`), and a name comparison
that does not treat an abbreviation as a disagreement
(:func:`~mellea_lrc.caselaw.compare_case_name`).

Nothing here decides that a citation was fabricated. Two outcomes carry
evidence and the rest do not:

* the page sits **inside** a different case than the one named, and
* a case does begin there under a name that **contradicts** what was written.

A page the archive does not cover is not evidence, because the archive is one
digitisation with an end date. A volume it does not hold says nothing at all.

Court orders serve as the control: judges write their own citations, so what
this flags in an order is very largely its own error rate.
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

from mellea_lrc.caselaw import CapIndex, NameVerdict, PageOutcome, compare_case_name, reporter_slug

CAP_DIR = pathlib.Path("local/cap")


REPORTERS = pathlib.Path("local/cap-reporters.json")
"""The archive's own list of the 401 reporters it publishes.

Fetched once from `static.case.law/ReportersMetadata.json`.
"""


def known_slugs(cap_dir: pathlib.Path = CAP_DIR) -> set[str]:
    """Every reporter slug the archive publishes, not merely those downloaded.

    Deriving this from the volume files on disk conflates two different
    answers. A reporter the archive publishes but whose volume is not yet
    downloaded should come back as `volume_unavailable` -- a statement about
    this machine, and fixable by fetching it, since the archive charges nothing
    and rate-limits nothing. A reporter it never carried should come back as
    itself. Reading the slugs off the filenames reported both as the latter,
    which is how 57% of the corpus was written off as unjudgeable when most of
    it was a download away.
    """
    if REPORTERS.exists():
        return {r["slug"] for r in json.loads(REPORTERS.read_text())}
    slugs = set()
    for path in cap_dir.glob("*-*.json"):
        match = re.match(r"(.+)-\d+\.json$", path.name)
        if match:
            slugs.add(match.group(1))
    return slugs


def pdf_text(path: str | pathlib.Path) -> str:
    """Layout-preserving text, via poppler's pdftotext."""
    try:
        done = subprocess.run(["pdftotext", "-q", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
        return done.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def _trim_bleed(name: str | None) -> str | None:
    """Drop text the layout bled into a party name.

    A party name is read backwards from the citation, so on a PDF laid out in
    columns or carrying a page stamp it collects whatever precedes it across a
    line break: ``Page 7 of 28\n\nLa Porte, Tex.``, or the tail of the previous
    sentence. Everything before the last blank line is not part of the name.
    """
    if not name:
        return name
    return re.split(r"\n\s*\n", name)[-1].replace("\n", " ").strip(" ,;“”\"")


def _written_name(citation: FullCaseCitation) -> str | None:
    """The case name as the filing wrote it, if it can be recovered."""
    meta = citation.metadata
    plaintiff = _trim_bleed(meta.plaintiff)
    defendant = _trim_bleed(meta.defendant)
    if plaintiff and defendant:
        return f"{plaintiff} v. {defendant}"
    return defendant or plaintiff or _trim_bleed(meta.antecedent_guess)


def check_text(text: str, index: CapIndex, slugs: set[str]) -> list[tuple[str, str]]:
    """Classify every full case citation in `text`."""
    with redirect_stdout(io.StringIO()):     # eyecite narrates to stdout
        citations = get_citations(text)

    results: list[tuple[str, str]] = []
    for citation in citations:
        if not isinstance(citation, FullCaseCitation):
            continue
        groups = citation.groups
        if not all(groups.get(k) for k in ("volume", "reporter", "page")):
            continue

        slug = reporter_slug(groups["reporter"], slugs)
        if slug is None:
            results.append(("reporter-not-held", groups["reporter"]))
            continue

        verdict = index.page(slug, groups["volume"], groups["page"])
        described = f"{groups['volume']} {slug} {groups['page']}"

        if verdict.outcome in (PageOutcome.VOLUME_UNAVAILABLE, PageOutcome.AMBIGUOUS_PAGE):
            results.append((verdict.outcome.value, described))
            continue
        if verdict.outcome is PageOutcome.NO_CASE_COVERS_IT:
            results.append(("page-not-covered", described))
            continue

        written = _written_name(citation)
        if not written:
            results.append(("no-name-parsed", described))
            continue

        # Any recorded case at the page may be the one meant, and either recorded
        # form of its name may be the one written, so satisfying any is enough.
        names = [n for c in verdict.cases for n in (c.name, c.full_name) if n]
        best = max((compare_case_name(written, n) for n in names),
                   key=lambda v: (v is NameVerdict.AGREES, v is NameVerdict.UNDECIDED))

        if verdict.outcome is PageOutcome.STARTS_A_CASE:
            if best is NameVerdict.DISAGREES:
                results.append(("NAME-CONTRADICTED", f"{described} | written: {written!r} | printed: {names[0]!r}"))
            else:
                results.append((f"starts-a-case/{best.value}", described))
        else:                                     # INSIDE_A_CASE
            if best is NameVerdict.AGREES:
                results.append(("pin-cite-ok", described))
            else:
                results.append(("PAGE-INSIDE-OTHER-CASE", f"{described} | page sits in: {names[0]}"))
    return results


SUSPICIOUS = ("NAME-CONTRADICTED", "PAGE-INSIDE-OTHER-CASE")


def run(paths, index: CapIndex, slugs: set[str], label: str) -> list:
    tally: collections.Counter[str] = collections.Counter()
    flagged = []
    for path in paths:
        for outcome, described in check_text(pdf_text(path), index, slugs):
            tally[outcome] += 1
            if outcome in SUSPICIOUS:
                flagged.append([pathlib.Path(path).name, outcome, described])

    judged = sum(count for name, count in tally.items()
                 if name.startswith("starts-a-case") or name in ("pin-cite-ok", *SUSPICIOUS))
    print(f"\n== {label}: {len(paths)} documents")
    for outcome, count in tally.most_common():
        print(f"   {count:5d}  {outcome}")
    if judged:
        bad = sum(tally[k] for k in SUSPICIOUS)
        print(f"   -> flagged {bad}/{judged} = {100 * bad / judged:.1f}% of judged citations")
    return flagged


if __name__ == "__main__":
    slugs = known_slugs()
    index = CapIndex(cache_dir=CAP_DIR, allow_fetch=False)
    accused = run(sorted(glob.glob("local/accused/*.pdf")), index, slugs, "accused filings")
    control = run(sorted(glob.glob("local/orders/*.pdf"))[:120], index, slugs,
                  "court orders (control -- judges' own citations)")
    pathlib.Path("local/miner-archive-check.json").write_text(
        json.dumps({"accused": accused, "orders": control}, indent=1))
