"""WER and CER scoring — word level and character level only.

WER — word error rate — is the edit distance between reference and
hypothesis word sequences divided by the number of reference words.
CER — character error rate — is the same ratio at character level.
No other variants live here on purpose: no diarization error rate,
no speaker attribution, no audio handling at all.
"""
from __future__ import annotations

import random

from normalize import normalize_text, words


def edit_distance(a: list, b: list) -> int:
    """Levenshtein distance between two sequences (words or chars)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[len(b)]


def wer(ref_norm: str, hyp_norm: str) -> float:
    rw, hw = words(ref_norm), words(hyp_norm)
    if not rw:
        return 0.0 if not hw else 1.0
    return edit_distance(rw, hw) / len(rw)


def cer(ref_norm: str, hyp_norm: str) -> float:
    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0
    return edit_distance(list(ref_norm), list(hyp_norm)) / len(ref_norm)


def per_utterance_errors(bundle: dict, vendor: str) -> list:
    """Per-utterance WER/CER for one vendor, both sides normalized
    under the contract profile. Returns rows in truth-file order."""
    profile = bundle["contract"]["normalization"]
    hyps = {h["utterance_id"]: h["text"] for h in bundle["hypotheses"][vendor]}
    out = []
    for row in bundle["truth"]:
        ref_n = normalize_text(row["reference"], profile)
        hyp_n = normalize_text(hyps[row["utterance_id"]], profile)
        out.append({"utterance_id": row["utterance_id"],
                    "slice_id": row["slice_id"],
                    "speaker_id": row["speaker_id"],
                    "wer": round(wer(ref_n, hyp_n), 6),
                    "cer": round(cer(ref_n, hyp_n), 6)})
    return out


def normalization_impact(bundle: dict, vendor: str) -> dict:
    """WER computed RAW (no normalization at all) vs WER computed
    after applying the contract profile to both sides. On a bundle
    whose truth file was produced under a mismatched profile this
    gap is the inflation the mismatch would have caused."""
    hyps = {h["utterance_id"]: h["text"] for h in bundle["hypotheses"][vendor]}
    profile = bundle["contract"]["normalization"]
    raw_err = raw_n = norm_err = norm_n = 0
    for row in bundle["truth"]:
        hyp = hyps[row["utterance_id"]]
        rw = words(row["reference"])
        raw_err += edit_distance(rw, words(hyp))
        raw_n += len(rw)
        ref_n = normalize_text(row["reference"], profile)
        hyp_n = normalize_text(hyp, profile)
        norm_err += edit_distance(words(ref_n), words(hyp_n))
        norm_n += len(words(ref_n))
    return {"vendor": vendor,
            "wer_raw_no_normalization": round(raw_err / raw_n, 6) if raw_n else 0.0,
            "wer_after_contract_normalization": round(norm_err / norm_n, 6) if norm_n else 0.0}


def paired_bootstrap_ci(diffs: list, seed: int = 1234, reps: int = 1000,
                        alpha: float = 0.05) -> dict:
    """Paired bootstrap CI — confidence interval — for a mean
    per-utterance difference. Paired means each resample draws whole
    utterances, so the two vendors are always compared on the same
    utterances they both transcribed. Seeded, stdlib only."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean_diff": 0.0, "ci_95": [0.0, 0.0], "reps": reps}
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        total = 0.0
        for _ in range(n):
            total += diffs[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo_idx = int((alpha / 2) * reps)
    hi_idx = min(reps - 1, int((1 - alpha / 2) * reps) - 1)
    return {"n": n, "mean_diff": round(sum(diffs) / n, 6),
            "ci_95": [round(means[lo_idx], 6), round(means[hi_idx], 6)],
            "reps": reps}
