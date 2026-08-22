"""Work out which filing on a docket the court was complaining about.

Discovery finds the document that *complains* -- a sanctions order, a show-cause
order, an opponent's response. The filing that actually contains the fabricated
citations is a different entry on the same docket, and finding it is the part
that makes this a method rather than a search.

Two things about real orders make this harder than it sounds, and both were
learned by reading one:

- **The order does not list the bad citations.** A typical sanctions order
  describes the conduct and points at docket entries. It says counsel "filed a
  declaration explaining the origin of the errant citations", not which cases
  were invented.
- **The order's own citations are real.** It quotes genuine authority on Rule
  11 sanctions -- `Oneto v. Watson`, `Wadsworth v. Walmart`, `White v. General
  Motors`. Treating every citation in the order as suspect would collect a set
  of real cases and label them fabricated, which is the worst outcome available.

What the order does carry is a reference to the offending entry, usually in its
opening sentence:

    this Court found that Petitioner's habeas petition (Dkt. 1) and traverse
    (Dkt. 10) contained citation errors

So the offending filing is identified by *which docket entries are named in a
sentence that attributes a citation defect to them*. Entries named for other
reasons -- the earlier order, counsel's declaration, a response brief -- are
mentioned in sentences that attribute nothing, and are left alone.

That yields a candidate, not a finding. The candidate is confirmed by fetching
it and checking that its citations really are defective, which is what the rest
of this project already does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `Dkt. 10`, `ECF No. 23`, `Doc. 5`, `Dkt. Nos. 1, 10`.
_REFERENCE = re.compile(
    r"\b(?:Dkt\.?|ECF|Doc\.?|Docket)\s*(?:Nos?\.?)?\s*#?\s*(\d+(?:\s*,\s*\d+)*)",
    re.IGNORECASE,
)
# Language a court uses when saying *this filing* was the defective one. The
# words that describe the misconduct in general -- sanctions, Rule 11 -- are
# deliberately absent: they appear throughout an order that names many entries.
_ATTRIBUTION = re.compile(
    r"(citation errors?|errant citations?|fabricated|nonexistent|non-existent"
    r"|hallucinat\w*|fictitious|do(?:es)? not exist|no such case|could not be located"
    r"|miscit\w*|inaccurate citations?)",
    re.IGNORECASE,
)
# A sentence is the unit of attribution: a reference in the same sentence as the
# accusation is the thing accused. Anything wider starts collecting the whole
# order, since a short order mentions its own docket throughout.
#
# Splitting legal prose on periods needs care, and the first version of this got
# it wrong in the one way that mattered: `Dkt.` ends with a period, so every
# reference was cut in half and no sentence ever contained one. The periods that
# belong to an abbreviation are hidden before the split and restored after.
_ABBREVIATIONS = (
    "Dkt.",
    "ECF",
    "Doc.",
    "Nos.",
    "No.",
    "Id.",
    "Ex.",
    "Fed.",
    "Civ.",
    "Proc.",
    "Cir.",
    "Supp.",
    "F.2d",
    "F.3d",
    "U.S.",
    "v.",
    "Inc.",
    "Corp.",
    "Co.",
    "Mr.",
    "Ms.",
    "Dr.",
    "Hon.",
    "Jr.",
    "Sr.",
    "Ct.",
    "R.",
    "P.",
    "at.",
)
_MARK = "\x00"
_SENTENCE = re.compile(r"[^.!?]*[.!?]")


def _split_sentences(flat: str) -> list[str]:
    """Split on sentence ends, without letting an abbreviation end one."""
    protected = flat
    for abbreviation in _ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", _MARK))
    return [sentence.replace(_MARK, ".") for sentence in _SENTENCE.findall(protected)]


@dataclass(frozen=True, slots=True)
class DocketReference:
    """One docket entry a document refers to, and the sentence naming it."""

    entry_number: int
    sentence: str
    accused: bool


def docket_references(text: str) -> tuple[DocketReference, ...]:
    """Every docket entry this document names, with whether it is being accused."""
    flat = " ".join(text.split())
    found: dict[int, DocketReference] = {}
    for sentence in _split_sentences(flat):
        accused = bool(_ATTRIBUTION.search(sentence))
        for match in _REFERENCE.finditer(sentence):
            for number in re.findall(r"\d+", match.group(1)):
                entry = int(number)
                previous = found.get(entry)
                # An entry accused anywhere stays accused.
                if previous is None or (accused and not previous.accused):
                    found[entry] = DocketReference(
                        entry_number=entry, sentence=sentence.strip(), accused=accused
                    )
    return tuple(sorted(found.values(), key=lambda item: item.entry_number))


def accused_entries(text: str, *, exclude: int | None = None) -> tuple[int, ...]:
    """The docket entries this document blames for defective citations.

    `exclude` drops the complaining document's own entry number, which an order
    routinely refers to and which is never the filing being complained about.
    """
    return tuple(
        reference.entry_number
        for reference in docket_references(text)
        if reference.accused and reference.entry_number != exclude
    )
