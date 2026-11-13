"""Shared bundle builders for the test suite (not a test module)."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_bundle  # noqa: E402


def clean_bundle():
    return generate_bundle(defective=False)


def defective_bundle():
    return generate_bundle(defective=True)


def floor_bundle():
    """A bundle that VALIDATES but whose us_general/support slice has
    n=10 — below the claim floor of 15 — so the claim gate (not the
    validation gate) must refuse a winner for that slice. Achieved by
    lowering every slice's declared min_samples to 5 and trimming."""
    bundle = copy.deepcopy(clean_bundle())
    for sl in bundle["contract"]["slices"]:
        sl["min_samples"] = 5
    sid = "us_general/support"
    keep = [r for r in bundle["truth"] if r["slice_id"] != sid]
    trimmed = [r for r in bundle["truth"] if r["slice_id"] == sid][:10]
    bundle["truth"] = keep + trimmed
    ids = {r["utterance_id"] for r in bundle["truth"]}
    for vendor in bundle["hypotheses"]:
        bundle["hypotheses"][vendor] = [
            h for h in bundle["hypotheses"][vendor]
            if h["utterance_id"] in ids]
    return bundle
