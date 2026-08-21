"""Tests for scoring a validation sweep against LePhantomCite labels."""

from __future__ import annotations

import json
from pathlib import Path

from evaluations.lephantomcite.evaluate import node_outcomes, score_run


def _write_run(tmp_path: Path, citations: list[dict[str, object]], labels: dict[str, list[str]]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    payload = {
        "excerpt_id": "a.pdf:0",
        "filename": "a.pdf",
        "labels": labels,
        "validated": {
            "source": {
                "citations": [
                    {"citation_id": item["citation_id"], "matched_text": item["matched_text"]}
                    for item in citations
                ]
            },
            "citations": [
                {
                    "citation_id": item["citation_id"],
                    "nodes": [{"node_type": node, "outcome": outcome} for node, outcome in item["nodes"]],
                }
                for item in citations
            ],
        },
    }
    (run_dir / "a.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def test_a_reported_defect_on_a_labelled_citation_is_a_true_positive(tmp_path: Path) -> None:
    """The pinpoint check's absence answers the wrong-pincite label."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "550 U.S. 544",
                "nodes": [("MelleaPinpointCheckNode", "absent_from_page")],
            }
        ],
        {"550 U.S. 544, 570 (2007)": ["wrong_pincite"]},
    )

    score = score_run(run_dir)["by_type"]["wrong_pincite"]

    assert score["true_positive"] == 1
    assert score["false_positive"] == 0
    assert score["coverage"] == 1.0


def test_an_abstention_is_not_counted_as_either_verdict(tmp_path: Path) -> None:
    """`inconclusive` must leave the matrix untouched and reduce coverage."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "550 U.S. 544",
                "nodes": [("MelleaPinpointCheckNode", "inconclusive")],
            }
        ],
        {"550 U.S. 544, 570 (2007)": ["wrong_pincite"]},
    )

    score = score_run(run_dir)["by_type"]["wrong_pincite"]

    assert score["true_positive"] == 0
    assert score["false_negative"] == 0
    assert score["covered"] == 0
    assert score["abstained_defective"] == 1
    assert score["abstained_outcomes"] == {"MelleaPinpointCheckNode:inconclusive": 1}


def test_a_clean_finding_on_a_sound_citation_is_a_true_negative(tmp_path: Path) -> None:
    """A check that ran and found nothing wrong is a finding, not an abstention."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "550 U.S. 544",
                "nodes": [("QuotationCheckNode", "verbatim")],
            }
        ],
        {},
    )

    score = score_run(run_dir)["by_type"]["misquote"]

    assert score["true_negative"] == 1
    assert score["coverage"] == 1.0


def test_a_defect_reported_on_a_sound_citation_is_a_false_positive(tmp_path: Path) -> None:
    """The number the safety claim rests on has to be countable."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "550 U.S. 544",
                "nodes": [("QuotationCheckNode", "altered")],
            }
        ],
        {},
    )

    score = score_run(run_dir)["by_type"]["misquote"]

    assert score["false_positive"] == 1
    assert score["precision"] == 0.0


def test_each_type_is_scored_against_its_own_node(tmp_path: Path) -> None:
    """A quotation finding must not answer a case-name label, or the reverse."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "550 U.S. 544",
                "nodes": [("QuotationCheckNode", "altered")],
            }
        ],
        {"550 U.S. 544, 570 (2007)": ["case_name_mismatch"]},
    )

    by_type = score_run(run_dir)["by_type"]

    assert by_type["misquote"]["false_positive"] == 1
    assert by_type["case_name_mismatch"]["true_positive"] == 0
    assert by_type["case_name_mismatch"]["abstained_defective"] == 1


def test_labels_match_a_citation_by_its_locator(tmp_path: Path) -> None:
    """The benchmark keys labels on its own citation string, not on the locator."""
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "556 U.S. 662",
                "nodes": [("LocatorCandidateAssessmentNode", "mismatch")],
            }
        ],
        {"Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009)": ["case_name_mismatch"]},
    )

    score = score_run(run_dir)["by_type"]["case_name_mismatch"]

    assert score["true_positive"] == 1


def test_the_scorer_reads_a_real_run_artifact() -> None:
    """Pinned to a file the runner actually wrote, not to an assumed shape.

    The first version of the scorer looked for `citation.citation_id` while the
    serializer writes `citation_id` at the top level, so it read every node list
    as empty and would have scored a whole sweep as total abstention without
    failing anything.
    """
    artifact = json.loads((Path(__file__).parent / "real_run_artifact.json").read_text(encoding="utf-8"))

    outcomes = node_outcomes(artifact["validated"])

    assert outcomes, "no citations were read out of a real artifact"
    assert any(pairs for pairs in outcomes.values()), "every node list came back empty"
    node_types = {node for pairs in outcomes.values() for node, _ in pairs}
    assert "ExactLocatorLookupNode" in node_types


def test_a_not_found_locator_is_never_scored_as_a_detection(tmp_path: Path) -> None:
    """Absence from an incomplete archive establishes nothing.

    Counting `not_found` as a fabrication finding is the binary framing this
    project rejects, and it manufactured seven false positives out of ordinary
    abstentions on the first scored sweep.
    """
    run_dir = _write_run(
        tmp_path,
        [
            {
                "citation_id": "c1",
                "matched_text": "512 U.S. 7000",
                "nodes": [("ExactLocatorLookupNode", "not_found")],
            }
        ],
        {},
    )

    score = score_run(run_dir)["by_type"]["non_existent_citation"]

    assert score["false_positive"] == 0
    assert score["covered"] == 0
    assert score["abstained_sound"] == 1
