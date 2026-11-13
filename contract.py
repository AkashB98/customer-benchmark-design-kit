"""Benchmark contract: the agreement, declared before any scoring.

A contract declares the slices to be measured, how many samples each
slice needs, which speakers belong to each slice, which speakers a
vendor was allowed to tune on, the two vendor configurations under
test, and the single normalization profile both sides must use.
Config checks run on these DECLARATIONS — the manifest a dataset
bundle carries about itself — not on streaming the audio or text.
"""
from __future__ import annotations

REQUIRED_PROFILE_KEYS = ("lowercase", "strip_punctuation", "number_format")


def validate_contract(contract: dict) -> list:
    """Return declaration-level issues with the contract itself."""
    issues = []
    if not isinstance(contract, dict):
        return ["contract: not an object"]
    for key in ("benchmark_id", "customer", "vendors", "normalization",
                "slices", "tuning_speakers", "min_slice_n_for_claim"):
        if key not in contract:
            issues.append(f"contract: missing field '{key}'")
    if issues:
        return issues
    vendors = contract["vendors"]
    if not isinstance(vendors, list) or len(vendors) != 2:
        issues.append("contract: exactly two vendors are required for a paired comparison")
    profile = contract["normalization"]
    for key in REQUIRED_PROFILE_KEYS:
        if key not in profile:
            issues.append(f"contract: normalization missing '{key}'")
    if profile.get("number_format") not in ("words", "digits"):
        issues.append("contract: normalization.number_format must be 'words' or 'digits'")
    if not isinstance(contract["min_slice_n_for_claim"], int) or contract["min_slice_n_for_claim"] < 1:
        issues.append("contract: min_slice_n_for_claim must be a positive int")
    seen = set()
    for sl in contract["slices"]:
        for key in ("slice_id", "accent", "domain", "call_type", "min_samples", "speakers"):
            if key not in sl:
                issues.append(f"contract: slice missing '{key}': {sl.get('slice_id', '?')}")
        sid = sl.get("slice_id")
        if sid in seen:
            issues.append(f"contract: duplicate slice_id '{sid}'")
        seen.add(sid)
        if isinstance(sl.get("min_samples"), int) and sl["min_samples"] < 1:
            issues.append(f"contract: slice '{sid}' min_samples must be >= 1")
        if not sl.get("speakers"):
            issues.append(f"contract: slice '{sid}' declares no speakers")
    # A speaker declared in two slices would blur the slice readouts.
    owner = {}
    for sl in contract["slices"]:
        for spk in sl.get("speakers", []):
            if spk in owner and owner[spk] != sl["slice_id"]:
                issues.append(f"contract: speaker '{spk}' declared in two slices")
            owner[spk] = sl["slice_id"]
    return issues


def check_config_declarations(contract: dict, manifest: dict) -> list:
    """Compare a bundle manifest's declarations against the contract.

    This is the config check: sample rate, language and the
    normalization each file CLAIMS to use, checked as declarations.
    """
    issues = []
    expected_sr = contract.get("audio", {}).get("sample_rate_hz")
    expected_lang = contract.get("audio", {}).get("language")
    if manifest.get("sample_rate_hz") != expected_sr:
        issues.append(
            f"CONFIG_MISMATCH: manifest sample_rate_hz={manifest.get('sample_rate_hz')} "
            f"!= contract {expected_sr}")
    if manifest.get("language") != expected_lang:
        issues.append(
            f"CONFIG_MISMATCH: manifest language={manifest.get('language')} "
            f"!= contract {expected_lang}")
    declared_norm = manifest.get("truth_normalization")
    want = contract["normalization"]
    if declared_norm != want:
        issues.append(
            f"NORMALIZATION_MISMATCH: truth file declares normalization "
            f"{declared_norm} but contract requires {want}")
    for vendor, prof in sorted(manifest.get("hypothesis_normalization", {}).items()):
        if prof != want:
            issues.append(
                f"NORMALIZATION_MISMATCH: hypothesis file for {vendor} declares "
                f"normalization {prof} but contract requires {want}")
    return issues
