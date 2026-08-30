"""What a docket description says about who wrote a filing and why.

These two tests carry most of the corpus's quality. A court document or a reply
to a show-cause order looks exactly like a guilty filing to everything
downstream -- an order about fabricated citations quotes them, and a reply is
filed by the same lawyer on the same docket in the same week.
"""

from scripts.miner.assess import answers_the_order, is_court_document


class TestIsCourtDocument:
    def test_an_opinion_naming_the_motion_it_rules_on_is_still_an_opinion(self) -> None:
        """Matching "motion" anywhere had let three opinions in as party filings."""
        assert is_court_document("MEMORANDUM OPINION re 35 Special Motion to Dismiss")

    def test_a_party_filing_the_judge_signed_is_still_a_party_filing(self) -> None:
        assert not is_court_document(
            "MEMORANDUM in Opposition to Motion to Vacate. Signed by Judge Smith."
        )

    def test_an_order_to_show_cause_is_the_court_speaking(self) -> None:
        assert is_court_document("ORDER TO SHOW CAUSE. Signed by Judge Ruiz on 11/3/2025.")

    def test_an_ordinary_motion_is_not(self) -> None:
        assert not is_court_document("First MOTION TO DISMISS FOR FAILURE TO STATE A CLAIM")

    def test_an_empty_description_says_nothing(self) -> None:
        assert not is_court_document("")


class TestAnswersTheOrder:
    def test_a_cross_reference_between_the_halves_does_not_hide_it(self) -> None:
        """Docket text interleaves references, so the phrase is not contiguous."""
        assert answers_the_order(
            "RESPONSE to re 187 to the Court's Order to Show Cause filed by Jefferson S."
        )

    def test_the_plain_form(self) -> None:
        assert answers_the_order("RESPONSE TO ORDER TO SHOW CAUSE filed by Gurpreet Kaur.")

    def test_a_declaration_answering_the_order(self) -> None:
        assert answers_the_order(
            "DECLARATION and Exhibit in response to Court's Order to Show Cause dated April 20"
        )

    def test_a_correction_is_filed_after_the_accusation_not_before(self) -> None:
        assert answers_the_order("MOTION for Leave to Correct Filing and Response to Show Cause")

    def test_the_offending_brief_itself_is_not_an_answer(self) -> None:
        assert not answers_the_order(
            "MEMORANDUM in Opposition to Plaintiffs' Motion to Vacate the Injunction"
        )

    def test_a_motion_that_merely_mentions_a_response_is_not_one(self) -> None:
        assert not answers_the_order(
            "First MOTION TO DISMISS FOR FAILURE TO STATE A CLAIM re 22 Response/Briefing Schedule"
        )
