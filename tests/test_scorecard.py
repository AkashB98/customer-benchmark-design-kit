import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import clean_bundle, defective_bundle, floor_bundle  # noqa: E402
from scorecard import build_report, build_scorecard  # noqa: E402
from scoring import normalization_impact  # noqa: E402


class TestRefusalGate(unittest.TestCase):
    def test_defective_refused_no_scores(self):
        gate = build_scorecard(defective_bundle())
        self.assertEqual(gate["status"], "REFUSED")
        self.assertIsNone(gate["scorecard"])
        self.assertEqual(len(gate["reasons"]), 6)

    def test_clean_scored(self):
        gate = build_scorecard(clean_bundle())
        self.assertEqual(gate["status"], "SCORED")
        self.assertEqual(gate["reasons"], [])


class TestScorecardNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = build_scorecard(clean_bundle())["scorecard"]

    def test_overall_pinned(self):
        self.assertEqual(self.sc["overall"]["VendorAlpha"]["wer"], 0.086265)
        self.assertEqual(self.sc["overall"]["VendorAlpha"]["cer"], 0.086082)
        self.assertEqual(self.sc["overall"]["VendorBeta"]["wer"], 0.167994)
        self.assertEqual(self.sc["overall"]["VendorBeta"]["cer"], 0.160452)

    def test_alpha_wins_clear_slices(self):
        for sid in ("us_general/support", "us_general/sales",
                    "indian/support", "indian/sales"):
            self.assertEqual(self.sc["claims"][sid]["winner"], "VendorAlpha", sid)

    def test_british_slices_no_claim_ci_crosses_zero(self):
        for sid in ("british/support", "british/sales"):
            claim = self.sc["claims"][sid]
            self.assertIsNone(claim["winner"], sid)
            self.assertIn("crosses 0", claim["reason"])
            ci = self.sc["slices"][sid]["wer_diff_a_minus_b"]["ci_95"]
            self.assertLessEqual(ci[0], 0)
            self.assertGreaterEqual(ci[1], 0)

    def test_bootstrap_pinned_slice(self):
        entry = self.sc["slices"]["us_general/support"]["wer_diff_a_minus_b"]
        self.assertEqual(entry["mean_diff"], -0.090555)
        self.assertEqual(entry["ci_95"], [-0.154192, -0.031717])
        self.assertEqual(entry["n"], 20)
        self.assertEqual(entry["reps"], 1000)

    def test_floor_refuses_claim(self):
        gate = build_scorecard(floor_bundle())
        self.assertEqual(gate["status"], "SCORED")  # bundle itself is valid
        claim = gate["scorecard"]["claims"]["us_general/support"]
        self.assertIsNone(claim["winner"])
        self.assertIn("below claim floor", claim["reason"])


class TestNormalizationImpact(unittest.TestCase):
    def test_defective_inflation_several_points(self):
        bundle = defective_bundle()
        for vendor, raw, norm in (("VendorAlpha", 0.247325, 0.081051),
                                  ("VendorBeta", 0.321046, 0.165389)):
            impact = normalization_impact(bundle, vendor)
            self.assertEqual(impact["wer_raw_no_normalization"], raw)
            self.assertEqual(impact["wer_after_contract_normalization"], norm)
            self.assertGreater(raw - norm, 0.10)

    def test_report_folds_gate(self):
        report = build_report(defective_bundle())
        self.assertEqual(report["gate_status"], "REFUSED")
        self.assertIsNone(report["scorecard"])
        self.assertEqual(len(report["refusal_reasons"]), 6)


if __name__ == "__main__":
    unittest.main()
