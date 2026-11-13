import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import clean_bundle, defective_bundle  # noqa: E402
from validation import coverage_summary, validate_bundle  # noqa: E402


def codes(issues):
    return [i.split(":")[0] for i in issues]


class TestValidation(unittest.TestCase):
    def test_clean_validates(self):
        self.assertEqual(validate_bundle(clean_bundle()), [])

    def test_defective_issue_codes(self):
        issues = validate_bundle(defective_bundle())
        self.assertEqual(codes(issues).count("NORMALIZATION_MISMATCH"), 2)
        self.assertEqual(codes(issues).count("SPEAKER_LEAKAGE"), 2)
        self.assertEqual(codes(issues).count("SLICE_MISSING"), 1)
        self.assertEqual(codes(issues).count("SLICE_UNDERFILLED"), 1)
        self.assertEqual(len(issues), 6)

    def test_leakage_names_the_speakers(self):
        issues = validate_bundle(defective_bundle())
        leaks = [i for i in issues if i.startswith("SPEAKER_LEAKAGE")]
        self.assertTrue(any("SPK-US-SUP-01" in i for i in leaks))
        self.assertTrue(any("SPK-GB-SUP-01" in i for i in leaks))

    def test_coverage_summary(self):
        cov = coverage_summary(defective_bundle())
        self.assertFalse(cov["indian/sales"]["ok"])
        self.assertEqual(cov["indian/sales"]["actual"], 0)
        self.assertEqual(cov["british/sales"]["actual"], 5)
        self.assertTrue(cov["us_general/support"]["ok"])

    def test_config_mismatch_sample_rate(self):
        bundle = clean_bundle()
        bundle["manifest"]["sample_rate_hz"] = 8000
        issues = validate_bundle(bundle)
        self.assertTrue(any(i.startswith("CONFIG_MISMATCH") for i in issues))

    def test_duplicate_utterance_id(self):
        bundle = clean_bundle()
        bundle["truth"].append(copy.deepcopy(bundle["truth"][0]))
        # keep hypotheses consistent in count is impossible with a dup
        # id; both the duplicate and the hyp-mismatch must surface.
        issues = validate_bundle(bundle)
        self.assertTrue(any("duplicate utterance_id" in i for i in issues))

    def test_missing_hypothesis_flagged(self):
        bundle = clean_bundle()
        bundle["hypotheses"]["VendorAlpha"] = \
            bundle["hypotheses"]["VendorAlpha"][:-1]
        issues = validate_bundle(bundle)
        self.assertTrue(any("VendorAlpha" in i and "hypotheses" in i
                            for i in issues))

    def test_contract_two_vendors_required(self):
        bundle = clean_bundle()
        bundle["contract"]["vendors"] = ["VendorAlpha"]
        issues = validate_bundle(bundle)
        self.assertTrue(any("exactly two vendors" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
