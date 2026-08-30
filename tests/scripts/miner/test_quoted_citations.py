"""Reading a case name out of a quotation, which failed twice in opposite ways.

Both failures produced wrong answers rather than errors, so they are pinned
here: one reported a correctly cited case as fabricated, the other discarded
fabrications a court had named in terms.
"""

from scripts.miner.quoted_citations import clean_party


class TestCleanParty:
    def test_ordinary_caption_words_are_kept(self) -> None:
        """`of`, `the` and `in` are everywhere in real captions.

        Rejecting them left a bare surname, which the caption test downstream
        then discarded -- losing `Lang v. City of Omaha` and `In re Marcus`,
        both fabrications a court had identified.
        """
        assert clean_party("City of Omaha") == "City of Omaha"
        assert clean_party("Indiana Dep't of Corr.") == "Indiana Dep't of Corr."
        assert clean_party("Church of the Lukumi Babalu Aye") == "Church of the Lukumi Babalu Aye"

    def test_sentence_text_is_rejected(self) -> None:
        """The parse runs backwards into prose, and that produced false positives."""
        assert clean_party("In that same response, Paul cited") is None
        assert clean_party("The 10th Circuit recognized in") is None
        assert clean_party("Defendants’ Motion runs afoul of") is None

    def test_a_run_on_parse_is_rejected_by_length(self) -> None:
        assert clean_party("qualifies as equitable relief under the terms of the plan at issue") is None

    def test_layout_bleed_is_dropped(self) -> None:
        """A page stamp precedes the name when the PDF is laid out in columns."""
        assert clean_party("Page 7 of 28\n\nLa Porte, Tex.") == "La Porte, Tex."

    def test_a_plain_party_survives(self) -> None:
        assert clean_party("Horizon Lines, Inc.") == "Horizon Lines, Inc."

    def test_nothing_in_gives_nothing_out(self) -> None:
        assert clean_party(None) is None
        assert clean_party("   ") is None
