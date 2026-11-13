"""The refusal gate and the scorecard it protects.

The scorecard is FOLDED INTO the refusal gate: ``build_scorecard``
first validates the bundle, and when validation fails it returns a
REFUSED result carrying the reasons — and no scores at all. A
scorecard produced over a mismatched truth file, leaked speakers or
missing slices would look precise and mean nothing.

When validation passes, the scorecard reports per-slice and overall
WER/CER for both vendors, plus — per slice — a paired bootstrap CI
on the WER difference. The gate refuses any "Vendor X wins" claim
for a slice when the CI crosses 0 or the slice's n is below the
contract floor (min_slice_n_for_claim).
"""
from __future__ import annotations

from scoring import normalization_impact, paired_bootstrap_ci, per_utterance_errors
from validation import coverage_summary, validate_bundle


def build_scorecard(bundle: dict) -> dict:
    issues = validate_bundle(bundle)
    if issues:
        return {"status": "REFUSED", "reasons": issues,
                "scorecard": None}
    contract = bundle["contract"]
    vendors = contract["vendors"]
    per_vendor = {v: per_utterance_errors(bundle, v) for v in vendors}
    slices = {}
    claims = {}
    floor = contract["min_slice_n_for_claim"]
    for idx, sl in enumerate(contract["slices"]):
        sid = sl["slice_id"]
        entry = {"n": 0}
        diffs = []
        for v in vendors:
            rows = [r for r in per_vendor[v] if r["slice_id"] == sid]
            entry[v] = {
                "wer": round(sum(r["wer"] for r in rows) / len(rows), 6) if rows else 0.0,
                "cer": round(sum(r["cer"] for r in rows) / len(rows), 6) if rows else 0.0,
            }
            entry["n"] = len(rows)
        a, b = vendors
        by_id_b = {r["utterance_id"]: r for r in per_vendor[b]}
        diffs = [r["wer"] - by_id_b[r["utterance_id"]]["wer"]
                 for r in per_vendor[a] if r["slice_id"] == sid]
        # diff = WER(vendor A) - WER(vendor B) per utterance.
        ci = paired_bootstrap_ci(
            diffs, seed=contract["bootstrap_seed"] + idx,
            reps=contract["bootstrap_reps"])
        entry["wer_diff_a_minus_b"] = ci
        slices[sid] = entry
        if entry["n"] < floor:
            claims[sid] = {"winner": None,
                           "reason": f"slice n={entry['n']} below claim floor {floor}"}
        elif ci["ci_95"][0] <= 0 <= ci["ci_95"][1]:
            claims[sid] = {"winner": None,
                           "reason": "bootstrap CI for the WER difference crosses 0"}
        else:
            winner = a if ci["mean_diff"] < 0 else b
            claims[sid] = {"winner": winner,
                           "reason": "CI excludes 0 and slice n meets the floor"}
    overall = {}
    for v in vendors:
        rows = per_vendor[v]
        overall[v] = {
            "wer": round(sum(r["wer"] for r in rows) / len(rows), 6),
            "cer": round(sum(r["cer"] for r in rows) / len(rows), 6),
            "n": len(rows)}
    return {"status": "SCORED", "reasons": [],
            "scorecard": {"vendors": vendors, "overall": overall,
                          "slices": slices, "claims": claims}}


def build_report(bundle: dict) -> dict:
    gate = build_scorecard(bundle)
    vendors = bundle["contract"]["vendors"]
    return {
        "benchmark_id": bundle["contract"]["benchmark_id"],
        "customer": bundle["contract"]["customer"],
        "validation_issues": validate_bundle(bundle),
        "coverage": coverage_summary(bundle),
        "normalization_impact": {v: normalization_impact(bundle, v)
                                 for v in vendors},
        "gate_status": gate["status"],
        "refusal_reasons": gate["reasons"],
        "scorecard": gate["scorecard"],
    }
