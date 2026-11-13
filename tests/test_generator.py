import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import build_contract, generate_bundle  # noqa: E402


class TestGenerator(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(generate_bundle(), generate_bundle())
        self.assertEqual(generate_bundle(defective=False),
                         generate_bundle(defective=False))

    def test_counts(self):
        self.assertEqual(len(generate_bundle(defective=False)["truth"]), 120)
        self.assertEqual(len(generate_bundle(defective=True)["truth"]), 85)

    def test_different_seed_differs(self):
        self.assertNotEqual(generate_bundle(seed=7, defective=False),
                            generate_bundle(seed=42, defective=False))

    def test_speakers_unique_to_one_slice(self):
        contract = build_contract()
        owner = {}
        for sl in contract["slices"]:
            for spk in sl["speakers"]:
                self.assertNotIn(spk, owner)
                owner[spk] = sl["slice_id"]
        self.assertEqual(len(owner), 30)

    def test_hypotheses_cover_truth(self):
        for defective in (True, False):
            bundle = generate_bundle(defective=defective)
            truth_ids = {r["utterance_id"] for r in bundle["truth"]}
            for vendor in bundle["contract"]["vendors"]:
                self.assertEqual(
                    {h["utterance_id"] for h in bundle["hypotheses"][vendor]},
                    truth_ids)

    def test_defective_truth_is_digits_form(self):
        bundle = generate_bundle(defective=True)
        self.assertTrue(any(tok.isdigit()
                            for r in bundle["truth"]
                            for tok in r["reference"].split()))
        clean = generate_bundle(defective=False)
        self.assertFalse(any(tok.strip(".,").isdigit()
                             for r in clean["truth"]
                             for tok in r["reference"].split()))


if __name__ == "__main__":
    unittest.main()
