"""Score a validation sweep against LePhantomCite's labels, abstentions apart.

    uv run python -m evaluations.lephantomcite.evaluate \
      --run-dir run-lephantomcite --output evaluation.json

Two rules govern the scoring, and they are the reason this does not simply
compute F1.

**An abstention is not a prediction.** The pipeline's outcome vocabulary
distinguishes a finding from an inability to reach one, and collapsing the
second into either label is the error the whole design avoids. Coverage is
therefore reported next to accuracy, and the confusion matrix is computed over
covered citations only. The uncovered ones are counted and named, never
silently folded in.

**A finding is typed.** Each defect type the benchmark injects is answered by a
different node, so a prediction is credited against the type it actually
speaks to rather than against a single "hallucinated" bit:

| benchmark type | the node that settles it | the finding |
|---|---|---|
| `non_existent_citation` | exact locator lookup | the reporter series does not exist |
| `case_name_mismatch` | locator candidate assessment | `mismatch` |
| `wrong_pincite` | pinpoint check | `absent_from_page` |
| `content_misrepresentation` | pinpoint check | `absent_from_page` |
| `misquote` | quotation check | `altered` |

`wrong_pincite` and `content_misrepresentation` share a node: both are the
claim that the cited page does not carry what it is cited for. They are scored
separately anyway, because the benchmark labels them separately and their
difficulty differs.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from evaluations.lephantomcite.dataset import HallucinationType

logger = logging.getLogger(__name__)

# Node outcomes that assert a defect. Everything else is either a clean finding
# or an abstention, and the two are kept apart below.
DEFECT_FINDINGS: dict[HallucinationType, tuple[tuple[str, str], ...]] = {
    HallucinationType.NON_EXISTENT_CITATION: (("ExactLocatorLookupNode", "not_found"),),
    HallucinationType.CASE_NAME_MISMATCH: (("LocatorCandidateAssessmentNode", "mismatch"),),
    HallucinationType.WRONG_PINCITE: (("MelleaPinpointCheckNode", "absent_from_page"),),
    HallucinationType.CONTENT_MISREPRESENTATION: (("MelleaPinpointCheckNode", "absent_from_page"),),
    HallucinationType.MISQUOTE: (("QuotationCheckNode", "altered"),),
}

# Outcomes that mean the check ran and found nothing wrong. Anything a node can
# report that is in neither table is an abstention.
CLEAN_FINDINGS: dict[HallucinationType, tuple[tuple[str, str], ...]] = {
    HallucinationType.NON_EXISTENT_CITATION: (("ExactLocatorLookupNode", "found"),),
    HallucinationType.CASE_NAME_MISMATCH: (
        ("LocatorCandidateAssessmentNode", "match"),
        ("LocatorCandidateAssessmentNode", "partial_match"),
    ),
    HallucinationType.WRONG_PINCITE: (("MelleaPinpointCheckNode", "supports"),),
    HallucinationType.CONTENT_MISREPRESENTATION: (("MelleaPinpointCheckNode", "supports"),),
    HallucinationType.MISQUOTE: (
        ("QuotationCheckNode", "verbatim"),
        ("QuotationCheckNode", "no_quotations"),
    ),
}


@dataclass
class TypeScore:
    """Counts for one defect type, with abstentions held out of the matrix."""

    true_positive: int = 0
    false_negative: int = 0
    false_positive: int = 0
    true_negative: int = 0
    abstained_defective: int = 0
    abstained_sound: int = 0
    abstained_outcomes: Counter[str] = field(default_factory=Counter)

    @property
    def covered(self) -> int:
        """Citations on which a finding was reached, either way."""
        return self.true_positive + self.false_negative + self.false_positive + self.true_negative

    @property
    def coverage(self) -> float:
        """Share of citations the checks could decide at all."""
        total = self.covered + self.abstained_defective + self.abstained_sound
        return self.covered / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        """Render the score, with every rate stated over its own denominator."""
        detected = self.true_positive + self.false_negative
        flagged = self.true_positive + self.false_positive
        return {
            "true_positive": self.true_positive,
            "false_negative": self.false_negative,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "covered": self.covered,
            "coverage": round(self.coverage, 4),
            "recall_on_covered": round(self.true_positive / detected, 4) if detected else None,
            "precision": round(self.true_positive / flagged, 4) if flagged else None,
            "abstained_defective": self.abstained_defective,
            "abstained_sound": self.abstained_sound,
            "abstained_outcomes": dict(self.abstained_outcomes.most_common()),
        }


def node_outcomes(validated: dict[str, object]) -> dict[str, list[tuple[str, str]]]:
    """Map each citation id to the (node type, outcome) pairs it produced.

    A serialized `CitationValidation` carries `citation_id` at its top level;
    the citation's own record lives under `source`. Reading it as a nested
    object silently yields nothing, which is why this is pinned by a test built
    from a real artifact rather than an assumed shape.
    """
    by_citation: dict[str, list[tuple[str, str]]] = {}
    for citation in validated.get("citations", []):
        citation_id = str(citation["citation_id"])
        by_citation[citation_id] = [
            (str(node["node_type"]), str(node["outcome"])) for node in citation.get("nodes", [])
        ]
    return by_citation


def score_run(run_dir: Path) -> dict[str, object]:
    """Score every excerpt written by a validation sweep."""
    scores = {kind: TypeScore() for kind in HallucinationType}
    excerpts = 0

    for path in sorted(run_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        excerpts += 1
        labels = {str(key): set(value) for key, value in payload.get("labels", {}).items()}
        outcomes = node_outcomes(payload["validated"])
        source = payload["validated"]["source"]
        for citation in source.get("citations", []):
            matched = str(citation.get("matched_text") or "")
            produced = outcomes.get(str(citation["citation_id"]), [])
            assigned = _labels_for(matched, labels)
            for kind in HallucinationType:
                _tally(scores[kind], kind, produced, defective=kind.value in assigned)

    return {
        "excerpts": excerpts,
        "by_type": {kind.value: scores[kind].as_dict() for kind in HallucinationType},
    }


def _labels_for(matched_text: str, labels: dict[str, set[str]]) -> set[str]:
    """Find the benchmark labels whose citation string names this citation.

    The benchmark keys labels on its own citation string, which carries the
    case name and parenthetical; extraction reports the locator. A label
    belongs to this citation when the locator appears in the labelled string.
    """
    if not matched_text:
        return set()
    assigned: set[str] = set()
    for cited, kinds in labels.items():
        if matched_text in cited or cited in matched_text:
            assigned |= kinds
    return assigned


def _tally(
    score: TypeScore,
    kind: HallucinationType,
    produced: list[tuple[str, str]],
    *,
    defective: bool,
) -> None:
    defect_pairs = set(DEFECT_FINDINGS[kind])
    clean_pairs = set(CLEAN_FINDINGS[kind])
    relevant_nodes = {node for node, _ in defect_pairs | clean_pairs}

    reported = [pair for pair in produced if pair in defect_pairs]
    cleared = [pair for pair in produced if pair in clean_pairs]

    if reported:
        if defective:
            score.true_positive += 1
        else:
            score.false_positive += 1
        return
    if cleared:
        if defective:
            score.false_negative += 1
        else:
            score.true_negative += 1
        return

    if defective:
        score.abstained_defective += 1
    else:
        score.abstained_sound += 1
    for node, outcome in produced:
        if node in relevant_nodes:
            score.abstained_outcomes[f"{node}:{outcome}"] += 1


def main() -> None:
    """Score a run directory and write the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = score_run(args.run_dir)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("scored %d excerpts into %s", result["excerpts"], args.output)


if __name__ == "__main__":
    main()
