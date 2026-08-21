"""Read the LePhantomCite eval split into citation-keyed records.

LePhantomCite labels a *text segment*: `list_hallucinations` maps a run of
characters to a hallucination type, and its evaluator counts a prediction
correct when either string contains the other. That unit is not comparable to
this project's, which reports a verdict per citation identifier.

`list_hallucination_types` carries the same labels keyed by the citation they
belong to, so it is the field these records are built from. A citation absent
from it is a citation the benchmark considers sound.

Two label kinds are kept apart, because they ask different questions of a
verification system:

- **identity** (`non_existent_citation`, `case_name_mismatch`) is decidable
  from a locator lookup alone.
- **semantic** (`wrong_pincite`, `misquote`, `content_misrepresentation`)
  requires the cited page.

The dataset is not redistributed here. Download it first:

    hf download ai-law-society-lab/Legal_Phantom_Citation --repo-type dataset \
      --local-dir <dir>
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

# A reporter is one or more whitespace-separated tokens that each contain a
# letter, which is what separates a series number (`2d`, `App'x`) from the page
# that follows it. Matching the reporter as a lazy character class instead stops
# at the first token boundary and reads `798 F. Supp. 2d 1215` as page 2.
_LOCATOR = re.compile(
    r"(?P<volume>\d+)\s+(?P<reporter>(?:[A-Za-z0-9.'’]*[A-Za-z][A-Za-z0-9.'’]*\s+)+)(?P<page>\d+)"
)
_NON_ALNUM = re.compile(r"[^a-z0-9]")
# `556 U.S. at 662` puts a pin introducer between the reporter and the page.
_PIN_INTRODUCER = "at"

# `list_hallucinations` also carries "optional" spans, which the benchmark's own
# evaluator excludes from the precision denominator. They are not labels.
OPTIONAL_LABEL = "optional"


class HallucinationType(str, Enum):
    """The five injected defect types, spelled as the released data spells them."""

    NON_EXISTENT_CITATION = "non_existent_citation"
    CASE_NAME_MISMATCH = "case_name_mismatch"
    WRONG_PINCITE = "wrong_pincite"
    MISQUOTE = "misquote"
    CONTENT_MISREPRESENTATION = "content_misrepresentation"


IDENTITY_TYPES = frozenset({HallucinationType.NON_EXISTENT_CITATION, HallucinationType.CASE_NAME_MISMATCH})
SEMANTIC_TYPES = frozenset(
    {
        HallucinationType.WRONG_PINCITE,
        HallucinationType.MISQUOTE,
        HallucinationType.CONTENT_MISREPRESENTATION,
    }
)


@dataclass(frozen=True, slots=True)
class LabelledCitation:
    """One citation in one excerpt, with the defect types the benchmark assigns it."""

    cited_text: str
    locator_key: str | None
    types: frozenset[HallucinationType]

    @property
    def is_defective(self) -> bool:
        """Whether the benchmark labels this citation defective at all."""
        return bool(self.types)

    @property
    def is_identity_defect(self) -> bool:
        """Whether every assigned defect is decidable from a locator lookup."""
        return bool(self.types) and self.types <= IDENTITY_TYPES

    @property
    def is_semantic_defect(self) -> bool:
        """Whether any assigned defect requires the cited page to decide."""
        return bool(self.types & SEMANTIC_TYPES)


@dataclass(frozen=True, slots=True)
class Excerpt:
    """One benchmark row: a brief segment and the citations it states."""

    excerpt_id: str
    filename: str
    text: str
    citations: tuple[LabelledCitation, ...]

    @property
    def defective(self) -> tuple[LabelledCitation, ...]:
        """Return only the citations the benchmark labels defective."""
        return tuple(item for item in self.citations if item.is_defective)


def locator_key(cited_text: str) -> str | None:
    """Reduce a citation string to `volume|reporter|page`, or None if it states none.

    Punctuation, spacing and case are removed from the reporter so that
    `F.Supp.2d` and `F. Supp. 2d` reduce alike. A short form contributes its
    pin page, which is what the benchmark's own citation strings carry.
    """
    match = _LOCATOR.search(cited_text)
    if match is None:
        return None
    tokens = match["reporter"].split()
    if tokens and tokens[-1].lower() == _PIN_INTRODUCER:
        tokens = tokens[:-1]
    reporter = _NON_ALNUM.sub("", "".join(tokens).lower())
    if not reporter:
        return None
    return f"{match['volume']}|{reporter}|{match['page']}"


def load_excerpts(path: Path) -> tuple[Excerpt, ...]:
    """Read an eval or aux_train JSONL file into excerpts."""
    with path.open(encoding="utf-8") as handle:
        return tuple(_excerpt(index, json.loads(line)) for index, line in enumerate(handle))


def iter_labelled_citations(excerpts: Sequence[Excerpt]) -> Iterator[tuple[Excerpt, LabelledCitation]]:
    """Yield every citation of every excerpt, paired with the excerpt it came from."""
    for excerpt in excerpts:
        for citation in excerpt.citations:
            yield excerpt, citation


def _excerpt(index: int, row: Mapping[str, object]) -> Excerpt:
    filename = str(row["filename"])
    stated = row.get("citations_in_segment", [])
    if not isinstance(stated, list):
        msg = f"{filename}: citations_in_segment must be a list"
        raise ValueError(msg)
    labels = _labels(row.get("list_hallucination_types") or {})
    citations = tuple(
        LabelledCitation(
            cited_text=str(cited),
            locator_key=locator_key(str(cited)),
            types=labels.get(str(cited), frozenset()),
        )
        for cited in stated
    )
    return Excerpt(
        excerpt_id=f"{filename}:{index}",
        filename=filename,
        text=str(row["text"]),
        citations=citations,
    )


def _labels(raw: object) -> dict[str, frozenset[HallucinationType]]:
    if not isinstance(raw, dict):
        msg = "list_hallucination_types must be a mapping"
        raise ValueError(msg)
    labels: dict[str, frozenset[HallucinationType]] = {}
    for cited, types in raw.items():
        values = types if isinstance(types, list) else [types]
        parsed = {
            HallucinationType(value) for value in values if isinstance(value, str) and value != OPTIONAL_LABEL
        }
        if parsed:
            labels[str(cited)] = frozenset(parsed)
    return labels
