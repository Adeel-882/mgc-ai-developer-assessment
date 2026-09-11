from copy import deepcopy
from decimal import Decimal
import unittest

from document_assistant import answer_question, read_documents, PRICES, POLICY, BROCHURE

REQUIRED_QUESTIONS = [
    "What's the base price of a 2-bed in Block B?",
    "What's the total for a Margalla-facing corner unit on floor 15, 2-bed Block B?",
    "What's the transfer fee?",
    "What's the rental yield on a 1-bed?",
    "Who is the anchor tenant?",
]


class DocumentAssistantTests(unittest.TestCase):
    def test_base_price(self):
        response = answer_question(REQUIRED_QUESTIONS[0])
        self.assertEqual(response["base_price"], 22425000)
        self.assertIn("Standard", response["answer"])
        self.assertEqual(response["sources"][0]["file"], PRICES)

    def test_stacked_premiums(self):
        response = answer_question(REQUIRED_QUESTIONS[1])
        self.assertEqual(response["base_price"], 26855000)
        expected = Decimal("26855000") * (1 + Decimal("0.04") + Decimal("0.03") + Decimal("0.06"))
        self.assertEqual(Decimal(str(response["unit_price"])), expected)
        self.assertEqual(expected, Decimal("30346150"))
        for amount in ["1,074,200", "805,650", "1,611,300", "30,346,150"]:
            self.assertIn(amount, response["answer"])
        self.assertIn("other charges", response["answer"])

    def test_newer_transfer_fee(self):
        response = answer_question(REQUIRED_QUESTIONS[2])
        for text in ["2.5%", "2%", "May 2025", "April 2025", "newer"]:
            self.assertIn(text, response["answer"])
        self.assertEqual({s["file"] for s in response["sources"]}, {POLICY, PRICES})

    def test_rental_yield(self):
        response = answer_question(REQUIRED_QUESTIONS[3])
        self.assertIn("does not publish rental yield projections", response["answer"])
        self.assertIn("marketing manager", response["answer"])
        self.assertNotIn("%", response["answer"])
        self.assertEqual(response["sources"][0]["file"], POLICY)

    def test_current_transfer_fee_is_not_a_rental_question(self):
        response = answer_question("What is the current transfer fee?")
        self.assertIn("2.5%", response["answer"])
        self.assertNotIn("rental yield", response["answer"])

    def test_anchor_tenant(self):
        response = answer_question(REQUIRED_QUESTIONS[4])
        self.assertIn("no anchor tenant has been confirmed", response["answer"])
        self.assertEqual(response["sources"][0]["file"], BROCHURE)

    def test_unknown(self):
        response = answer_question("Who is the architect?")
        self.assertIn("do not provide", response["answer"])
        self.assertEqual(len(response["sources"]), 3)

    def test_ambiguous_chronology_is_not_guessed(self):
        documents = deepcopy(read_documents())
        documents[POLICY]["date"] = documents[PRICES]["date"]
        response = answer_question(REQUIRED_QUESTIONS[2], documents)
        self.assertIn("without a clear chronology", response["answer"])
        documents[POLICY]["date"] = None
        self.assertIn("without a clear chronology", answer_question(REQUIRED_QUESTIONS[2], documents)["answer"])

    def test_price_is_read_from_document(self):
        documents = deepcopy(read_documents())
        section = "Base Prices (Block B)"
        documents[PRICES]["sections"][section] = documents[PRICES]["sections"][section].replace("22,425,000", "23,000,000")
        self.assertEqual(answer_question(REQUIRED_QUESTIONS[0], documents)["base_price"], 23000000)

    def test_cross_document_orientation(self):
        response = answer_question("Total for 2-bed corner Block B on the 15th floor?")
        self.assertEqual(response["unit_price"], 30346150)
        self.assertIn(BROCHURE, {s["file"] for s in response["sources"]})

    def test_invalid_configurations(self):
        for question in ["Price of studio Block B?", "Price of 1-bed corner Block B?", "Price of 2-bed Block B floor 23?"]:
            self.assertNotIn("unit_price", answer_question(question))
        response = answer_question("Price of Margalla-facing 1-bed Block B?")
        self.assertIn("not available", response["answer"])

    def test_overseas_transfer_exception(self):
        response = answer_question("Can an overseas buyer transfer remotely and what is the transfer fee?")
        self.assertIn("2.5%", response["answer"])
        self.assertIn("exempt from the in-person requirement", response["answer"])


if __name__ == "__main__":
    unittest.main()
