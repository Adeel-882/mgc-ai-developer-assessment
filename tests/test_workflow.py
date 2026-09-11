import unittest
import pandas as pd
from fastapi.testclient import TestClient

from app import app
from lead_scoring import ROOT, FEATURES, prepare_features, score_lead
from train_model import canonical_leads


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.details = {"source": "Referral", "city": "ISB", "property_type": "Apartment",
                       "budget_pkr_lac": 180, "bedrooms": 2, "agent_experience_years": 5,
                       "is_overseas": 0, "referred_by_existing_client": 1}

    def test_deduplication_and_balance(self):
        raw = pd.read_csv(ROOT / "leads.csv")
        clean = canonical_leads(raw)
        self.assertEqual((len(raw), len(clean), int(clean.converted.sum())), (9160, 9000, 626))
        duplicates = raw[raw.duplicated("crm_record_hash", keep=False)].copy()
        duplicates.loc[duplicates.index[0], "converted"] = 1 - duplicates.iloc[0].converted
        with self.assertRaises(ValueError):
            canonical_leads(duplicates)

    def test_preprocessing_and_leakage_boundary(self):
        frame = prepare_features([self.details])
        self.assertEqual(frame.loc[0, "city"], "islamabad")
        self.assertEqual(list(frame.columns), FEATURES)
        first = score_lead(self.details)
        second = score_lead({**self.details, "converted": 1, "token_amount_received_pkr": 9999999,
                             "crm_record_hash": 123, "calls_made": 100, "has_financing_approved": 1})
        self.assertEqual(first, second)
        self.assertTrue(0 <= first <= 1)
        self.assertEqual(prepare_features([{"property_type": "Plot"}]).loc[0, "bedrooms"], 0)

    def test_missing_unseen_and_invalid_features(self):
        self.assertTrue(0 <= score_lead({"source": "Unseen new source"}) <= 1)
        for details in [{}, {"budget_pkr_lac": -1}, {"is_overseas": 3},
                        {"budget_pkr_lac": float("inf")}, {"bedrooms": 2.5}]:
            with self.assertRaises(ValueError):
                score_lead(details)

    def test_web_forms(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Document assistant", response.text)
        self.assertIn("Lead scoring", response.text)
        response = self.client.post("/ask", data={"question": "What's the transfer fee?"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("2.5%", response.text)
        response = self.client.post("/score", data=self.details)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Estimated conversion likelihood:", response.text)
        response = self.client.post("/ask", data={"question": "<script>alert(1)</script>"})
        self.assertNotIn("<script>alert(1)</script>", response.text)

    def test_json_endpoints(self):
        response = self.client.post("/api/score", json=self.details)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(0 <= response.json()["probability"] <= 1)
        self.assertEqual(self.client.post("/api/score", json={"budget_pkr_lac": -3}).status_code, 422)
        self.assertEqual(self.client.post("/api/score", json={}).status_code, 422)
        response = self.client.post("/api/ask", json={"question": "Who is the anchor tenant?"})
        self.assertIn("No anchor tenant has been confirmed", response.json()["answer"])

    def test_empty_document_form(self):
        for data in [{}, {"question": ""}, {"question": "   "}]:
            response = self.client.post("/ask", data=data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn("Please enter a question.", response.text)

    def test_optional_scoring_form_values(self):
        for data in [{"source": "Referral"}, {"source": "Referral", "area": "",
                                              "budget_pkr_lac": "", "bedrooms": ""}]:
            response = self.client.post("/score", data=data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Estimated conversion likelihood:", response.text)
        response = self.client.post("/score", data={})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter at least one intake feature.", response.text)


if __name__ == "__main__":
    unittest.main()
