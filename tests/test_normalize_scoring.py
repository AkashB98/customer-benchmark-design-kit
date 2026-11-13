import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize import normalize_text  # noqa: E402
from scoring import cer, edit_distance, paired_bootstrap_ci, wer  # noqa: E402

PROFILE = {"lowercase": True, "strip_punctuation": True,
           "number_format": "words"}


class TestNormalize(unittest.TestCase):
    def test_case_and_punctuation(self):
        self.assertEqual(normalize_text("Hello, World!", PROFILE),
                         "hello world")

    def test_digits_become_words(self):
        self.assertEqual(normalize_text("Order 42 costs 100 dollars.", PROFILE),
                         "order forty two costs one hundred dollars")

    def test_word_numbers_unchanged(self):
        self.assertEqual(normalize_text("forty two", PROFILE), "forty two")


class TestScoring(unittest.TestCase):
    def test_wer_identical(self):
        self.assertEqual(wer("the cat sat", "the cat sat"), 0.0)

    def test_wer_substitution(self):
        self.assertEqual(wer("the cat sat", "the dog sat"), 1 / 3)

    def test_wer_deletion_and_insertion(self):
        self.assertEqual(wer("a b c d", "a c d"), 0.25)
        self.assertEqual(wer("a b", "a x b"), 0.5)

    def test_wer_empty_reference(self):
        self.assertEqual(wer("", ""), 0.0)
        self.assertEqual(wer("", "x"), 1.0)

    def test_cer_hand_computed(self):
        self.assertEqual(cer("abc", "abd"), 1 / 3)
        self.assertEqual(cer("abc", "abc"), 0.0)

    def test_edit_distance(self):
        self.assertEqual(edit_distance(list("kitten"), list("sitting")), 3)
        self.assertEqual(edit_distance([], [1, 2]), 2)


class TestBootstrap(unittest.TestCase):
    def test_constant_diffs_ci_is_point(self):
        out = paired_bootstrap_ci([0.2] * 20, seed=1, reps=200)
        self.assertEqual(out["mean_diff"], 0.2)
        self.assertEqual(out["ci_95"], [0.2, 0.2])

    def test_deterministic(self):
        diffs = [0.1, -0.05, 0.2, 0.0, 0.15] * 4
        self.assertEqual(paired_bootstrap_ci(diffs, seed=99, reps=200),
                         paired_bootstrap_ci(diffs, seed=99, reps=200))

    def test_empty(self):
        out = paired_bootstrap_ci([], reps=10)
        self.assertEqual(out["n"], 0)


if __name__ == "__main__":
    unittest.main()
