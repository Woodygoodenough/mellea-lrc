"""Tests for `scripts.miner.rank_candidates`.

`resolve.accused_entries` only finds an offending filing when the order names
its docket number in the same sentence as the accusation. These tests cover
the fallback for when it does not: ranking a docket's own entries against
whatever the order's language does give -- a kind of document and, often, an
attorney's name.

Two of the fixtures below are not invented. `CASTRO_SENTENCE` is the exact
sentence quoted in this project's own notes on the gap `resolve.py` leaves,
taken from a real order (CourtListener docket 72097131, "The Doc App, Inc. v.
Leafwell, Inc."). `LEAFWELL_ENTRIES` is the real docket 71998716's entries as
they appear in this project's `complaints.json` harvest -- a genuine negative
case, since that harvest never captured the actual accused motions (entries
26, 27, and 30 on that docket), only four unrelated ones.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from scripts.miner.rank_candidates import (
    Candidate,
    extract_attorney_names,
    extract_document_kinds,
    format_candidates,
    rank_candidates,
)

# A real sentence from CourtListener docket 72097131 -- an order that
# recounts, as background, a filing sanctioned in a different case. It names
# an attorney and a kind of document but, on its own docket, no entry number.
CASTRO_SENTENCE = (
    "Seeking emergency injunctive relief, attorney Jason Castro had filed a motion "
    "littered with fabricated cases and sham quotes—the apparent hallmarks of "
    "reckless AI use."
)

# docket 71998716's real accusing text (from its order, entry 51), which
# names the attorney and the kind of document across two sentences rather
# than one -- ordinary legal prose that `resolve.py`'s sentence-scoped
# matching does not have to solve, because this module never looks for a
# docket number in the text at all.
LEAFWELL_ORDER_TEXT = (
    'At issue are three motions filed by Jason Castro ("Castro"): (1) Motion to '
    "Dismiss for Failure to State a Claim (Doc. #26); (2) Motion to Dismiss for "
    "Lack of Subject-Matter Jurisdiction (Doc. #27); and (3) Motion to Strike "
    "(Doc. #30). Across these motions, the Court finds Castro: (1) overstated the "
    "breadth of four cases; (2) discussed a non-existent count; (3) completely "
    "misrepresented five cited authorities."
)

# docket 71998716's entries as `complaints.json` actually captured them --
# whatever matched a discovery phrase, not the full docket. None of these
# four is the accused motion.
LEAFWELL_ENTRIES = [
    {"document_number": 51, "description": "Order on Motion for Sanctions"},
    {"document_number": 62, "description": "Response in Opposition to Motion"},
    {"document_number": 1, "description": "Complaint"},
    {"document_number": 22, "description": "Amended Complaint"},
]


# --- extract_document_kinds -------------------------------------------------


def test_extract_document_kinds_finds_the_named_kind() -> None:
    text = "Petitioner's traverse contained citations to nonexistent cases."
    assert "traverse" in extract_document_kinds(text)


def test_extract_document_kinds_prefers_the_longer_phrase() -> None:
    text = "The Court finds that the motion to dismiss cited fabricated cases."
    kinds = extract_document_kinds(text)
    assert "motion to dismiss" in kinds
    # The bare "motion" inside "motion to dismiss" is not double-counted.
    assert kinds.count("motion") == 0


def test_extract_document_kinds_on_the_real_castro_sentence() -> None:
    assert "motion" in extract_document_kinds(CASTRO_SENTENCE)


def test_extract_document_kinds_ignores_unrelated_boilerplate() -> None:
    # A standing order's generic AI-use warning names no document at all.
    text = (
        "Litigants are reminded that AI systems are not factually or legally "
        "trustworthy sources and must be verified before citing them to the Court."
    )
    assert extract_document_kinds(text) == ()


def test_extract_document_kinds_falls_back_to_the_whole_order() -> None:
    # No sentence matches resolve._ATTRIBUTION or the misconduct fallback, so
    # the whole text is searched -- lower confidence, but not nothing.
    text = "The parties shall confer regarding the pending motion for sanctions."
    assert "motion for sanctions" in extract_document_kinds(text)


def test_extract_document_kinds_normalizes_a_real_unicode_hyphen() -> None:
    # A real order (CourtListener docket 71995508, D. Minn.) writes the word
    # "non-existent" with U+2010 HYPHEN rather than an ASCII hyphen-minus --
    # invisible on screen, but enough to make this module's own vocabulary miss
    # the word entirely without normalizing. resolve._ATTRIBUTION accepts every
    # dash variant directly; this module normalizes because it matches many
    # more phrases than that one pattern does.
    text = "Randolph’s motions contain citations to non‐existent cases."
    assert "motion" in extract_document_kinds(text)


# --- extract_attorney_names -------------------------------------------------


def test_extract_attorney_names_after_the_cue_word() -> None:
    assert extract_attorney_names(CASTRO_SENTENCE) == ("Jason Castro",)


def test_extract_attorney_names_handles_counsel_before_the_name() -> None:
    text = "Plaintiff's counsel, Maria Elena Lopez, filed the brief in question."
    names = extract_attorney_names(text)
    assert "Maria Elena Lopez" in names


def test_extract_attorney_names_filters_boilerplate_capitalized_runs() -> None:
    text = (
        "The Court reminds counsel that Federal Rules of Civil Procedure and "
        "the United States Code govern this dispute."
    )
    assert extract_attorney_names(text) == ()


def test_extract_attorney_names_deduplicates() -> None:
    text = "Attorney Jason Castro signed the motion. Attorney Jason Castro later disclaimed it."
    assert extract_attorney_names(text) == ("Jason Castro",)


def test_extract_attorney_names_empty_when_no_cue_word() -> None:
    text = "Plaintiff Michael Platt appears pro se and cited fictitious caselaw."
    assert extract_attorney_names(text) == ()


# --- rank_candidates ---------------------------------------------------------


def test_rank_candidates_prefers_kind_and_attorney_match() -> None:
    entries = [
        {"document_number": 1, "description": "Complaint"},
        {
            "document_number": 5,
            "description": "MOTION to Dismiss for Failure to State a Claim by Jason Castro (Castro, Jason)",
        },
        {"document_number": 8, "description": "Response in Opposition to Motion"},
    ]
    ranked = rank_candidates(CASTRO_SENTENCE, entries, order_entry=10)
    assert ranked
    assert ranked[0].entry_number == 5
    assert "motion" in ranked[0].kind_matches
    assert "Jason Castro" in ranked[0].attorney_matches


def test_rank_candidates_drops_entries_at_or_after_the_order() -> None:
    entries = [
        {"document_number": 10, "description": "Order to Show Cause"},
        {"document_number": 11, "description": "Motion by Jason Castro (Castro, Jason)"},
    ]
    # entry 11 was filed after the order (entry 10) and cannot be its target.
    ranked = rank_candidates(CASTRO_SENTENCE, entries, order_entry=10)
    assert all(candidate.entry_number < 10 for candidate in ranked)
    assert 11 not in {candidate.entry_number for candidate in ranked}


def test_rank_candidates_recency_breaks_ties() -> None:
    entries = [
        {"document_number": 2, "description": "Motion for Sanctions"},
        {"document_number": 6, "description": "Motion for Sanctions"},
    ]
    ranked = rank_candidates(CASTRO_SENTENCE, entries, order_entry=10)
    assert [c.entry_number for c in ranked] == [6, 2]


def test_rank_candidates_excludes_entries_with_no_matching_signal() -> None:
    entries = [{"document_number": 3, "description": "Notice of Appearance"}]
    ranked = rank_candidates(CASTRO_SENTENCE, entries, order_entry=10)
    assert ranked == ()


def test_rank_candidates_without_order_entry_keeps_every_matching_entry() -> None:
    entries = [
        {"document_number": 40, "description": "Motion by Jason Castro (Castro, Jason)"},
    ]
    ranked = rank_candidates(CASTRO_SENTENCE, entries, order_entry=None)
    assert len(ranked) == 1
    assert not any("filed before the order" in item for item in ranked[0].evidence)


def test_rank_candidates_on_the_real_leafwell_harvest_finds_nothing() -> None:
    # The genuine negative case: complaints.json's partial harvest of docket
    # 71998716 never captured the actually-accused motions (entries 26, 27,
    # 30) -- only four entries that match neither the "motion" kind nor the
    # "Jason Castro" attorney signal this order's own text carries.
    ranked = rank_candidates(LEAFWELL_ORDER_TEXT, LEAFWELL_ENTRIES, order_entry=51)
    assert ranked == ()
    assert "motion" in extract_document_kinds(LEAFWELL_ORDER_TEXT)
    assert "Jason Castro" in extract_attorney_names(LEAFWELL_ORDER_TEXT)


def test_rank_candidates_would_find_the_real_leafwell_motion_if_enumerated() -> None:
    # Same order text, but with one of the real accused entries (26, "Motion
    # to Dismiss for Failure to State a Claim") added the way a full docket
    # enumeration -- not the partial complaints.json harvest -- would supply
    # it, with the filer tag PACER dockets commonly carry.
    entries = [
        *LEAFWELL_ENTRIES,
        {
            "document_number": 26,
            "description": "MOTION to Dismiss for Failure to State a Claim (Castro, Jason)",
        },
    ]
    ranked = rank_candidates(LEAFWELL_ORDER_TEXT, entries, order_entry=51)
    assert ranked
    assert ranked[0].entry_number == 26


# --- format_candidates --------------------------------------------------------


def test_format_candidates_reports_no_candidates() -> None:
    assert format_candidates(()) == "(no candidates)"


def test_format_candidates_lists_evidence_per_entry() -> None:
    candidate = Candidate(
        entry_number=5,
        description="Motion for Sanctions",
        kind_matches=("motion",),
        attorney_matches=("Jason Castro",),
        evidence=("description matches document kind(s): motion",),
    )
    rendered = format_candidates([candidate])
    assert "entry 5" in rendered
    assert "description matches document kind(s): motion" in rendered
