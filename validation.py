"""Truth-file validation BEFORE scoring.

Runs after the contract checks and before any error rate is
computed. It never raises on bad data — it returns issue strings so
the refusal gate (and the CLI check exit codes) can act on them.
Issue codes: NORMALIZATION_MISMATCH, CONFIG_MISMATCH,
SPEAKER_LEAKAGE, SLICE_MISSING, SLICE_UNDERFILLED, plus plain
data-quality issues (missing fields, duplicate utterance ids,
undeclared slices/speakers, references with digit tokens where the
contract profile says number words).
"""
from __future__ import annotations

from contract import check_config_declarations, validate_contract


def validate_bundle(bundle: dict) -> list:
    issues = []
    contract = bundle.get("contract", {})
    issues.extend(validate_contract(contract))
    manifest = bundle.get("manifest", {})
    if not manifest:
        issues.append("bundle: missing manifest (declarations are required)")
    else:
        issues.extend(check_config_declarations(contract, manifest))

    truth = bundle.get("truth", [])
    seen_ids = set()
    declared_slices = {s["slice_id"]: s for s in contract.get("slices", [])}
    declared_speakers = {spk for s in contract.get("slices", [])
                          for spk in s.get("speakers", [])}
    counts = {sid: 0 for sid in declared_slices}
    eval_speakers = set()
    digit_rows = 0
    for row in truth:
        for key in ("utterance_id", "slice_id", "speaker_id", "reference"):
            if key not in row:
                issues.append(f"truth: row missing '{key}': {row.get('utterance_id', '?')}")
        uid = row.get("utterance_id")
        if uid in seen_ids:
            issues.append(f"truth: duplicate utterance_id '{uid}'")
        seen_ids.add(uid)
        sid = row.get("slice_id")
        if sid not in declared_slices:
            issues.append(f"truth: undeclared slice_id '{sid}'")
        else:
            counts[sid] += 1
        spk = row.get("speaker_id")
        if spk not in declared_speakers:
            issues.append(f"truth: speaker '{spk}' not declared in any slice")
        eval_speakers.add(spk)
        ref = row.get("reference", "")
        if any(tok.strip(".,") .isdigit() for tok in ref.split()):
            digit_rows += 1
    # Slice coverage: declared vs actual.
    for sid, sl in declared_slices.items():
        if counts[sid] == 0:
            issues.append(f"SLICE_MISSING: slice '{sid}' declared "
                          f"(min_samples={sl['min_samples']}) has 0 truth rows")
        elif counts[sid] < sl["min_samples"]:
            issues.append(f"SLICE_UNDERFILLED: slice '{sid}' has {counts[sid]} "
                          f"truth rows, contract requires {sl['min_samples']}")
    # Speaker-overlap leakage: tuning set vs eval set.
    tuning = set(manifest.get("tuning_speakers",
                              contract.get("tuning_speakers", [])))
    for spk in sorted(eval_speakers & tuning):
        issues.append(f"SPEAKER_LEAKAGE: speaker '{spk}' appears in both "
                      f"the vendor tuning set and the eval set")
    # Stream-level corroboration of the normalization declaration:
    # digit tokens in references while the contract says words.
    if contract.get("normalization", {}).get("number_format") == "words" and digit_rows:
        issues.append(f"NORMALIZATION_MISMATCH: {digit_rows} truth references "
                      f"contain digit tokens but the contract normalization "
                      f"profile declares number_format='words'")
    # Hypotheses must cover exactly the truth ids, per vendor.
    truth_ids = {r.get("utterance_id") for r in truth}
    for vendor, hyps in bundle.get("hypotheses", {}).items():
        hyp_ids = [h.get("utterance_id") for h in hyps]
        if set(hyp_ids) != truth_ids or len(hyp_ids) != len(set(hyp_ids)):
            issues.append(f"hypotheses: {vendor} ids do not match the truth "
                          f"file exactly (missing/extra/duplicate)")
    return issues


def coverage_summary(bundle: dict) -> dict:
    counts = {}
    for row in bundle.get("truth", []):
        counts[row["slice_id"]] = counts.get(row["slice_id"], 0) + 1
    out = {}
    for sl in bundle["contract"]["slices"]:
        actual = counts.get(sl["slice_id"], 0)
        out[sl["slice_id"]] = {"declared_min": sl["min_samples"],
                               "actual": actual,
                               "ok": actual >= sl["min_samples"]}
    return out
