"""Deterministic synthetic STT benchmark bundles.

SYNTHETIC DATA ONLY. The customer (Acme Support Co), both vendors
(VendorAlpha, VendorBeta), every speaker and every transcript are
fictional and fabricated by a seeded generator. No audio exists —
this kit designs and validates a benchmark from declared text files.

Two bundle flavours:
- clean: declarations match the contract, every slice filled, no
  speaker leakage. Validation passes; a scorecard is produced.
- defective (the default seeded bundle): three planted defects —
  (1) the truth file DECLARES a normalization profile that differs
  from the contract (digits/lowercase/no-punctuation instead of
  number words), and its text really is in that form, so a raw
  comparison would inflate WER by several points;
  (2) two eval speakers also appear in the vendor tuning set
  (speaker-overlap leakage);
  (3) one slice is missing entirely and one is under-filled
  (slice coverage gaps).
"""
from __future__ import annotations

import json
import random

SEED = 42

ACCENTS = [("us_general", "US"), ("british", "GB"), ("indian", "IN")]
SLICE_DEFS = [
    ("us_general/support", "us_general", "support", "inbound"),
    ("us_general/sales", "us_general", "sales", "outbound"),
    ("british/support", "british", "support", "inbound"),
    ("british/sales", "british", "sales", "outbound"),
    ("indian/support", "indian", "support", "inbound"),
    ("indian/sales", "indian", "sales", "outbound"),
]
MIN_SAMPLES = 20
SPEAKERS_PER_SLICE = 5

_NUMBER_WORDS = ["twelve", "twenty four", "forty two", "sixty seven",
                 "eighty nine", "one hundred", "thirty five",
                 "fifty eight"]
# Reverse map used ONLY to fabricate the defective digits-form truth.
_WORD_TO_DIGIT = {"twelve": "12", "twenty four": "24", "forty two": "42",
                  "sixty seven": "67", "eighty nine": "89",
                  "one hundred": "100", "thirty five": "35",
                  "fifty eight": "58"}

_SUPPORT = [
    "My order number is {num} and the delivery never arrived.",
    "I need help resetting the password for account {num}.",
    "The invoice for {num} dollars was charged twice this month.",
    "Please cancel ticket number {num} and refund the fee.",
    "Our office line has been down for {num} hours today.",
]
_SALES = [
    "I am calling about the renewal quote for {num} seats.",
    "Can you send pricing for {num} licences before Friday.",
    "We want to upgrade the plan that costs {num} dollars a month.",
    "The discount code saved us {num} dollars on the order.",
    "Please book a demo for a team of {num} people next week.",
]
_FILLER = ["please", "thanks", "actually", "today", "again"]
_SUBS = {"refund": "charge", "cancel": "pause", "help": "assist",
         "send": "mail", "book": "hold", "upgrade": "change",
         "resetting": "changing", "arrived": "shipped",
         "charged": "billed", "saved": "earned"}


def _speakers(accent_code: str, domain: str) -> list:
    # Speakers are unique to ONE slice (accent x domain): a speaker
    # shared across slices would blur the per-slice readouts, and the
    # contract validator forbids it.
    tag = "SUP" if domain == "support" else "SAL"
    return [f"SPK-{accent_code}-{tag}-{i:02d}"
            for i in range(1, SPEAKERS_PER_SLICE + 1)]


def build_contract() -> dict:
    slices = []
    for slice_id, accent, domain, call_type in SLICE_DEFS:
        code = dict(ACCENTS)[accent]
        slices.append({"slice_id": slice_id, "accent": accent,
                       "domain": domain, "call_type": call_type,
                       "min_samples": MIN_SAMPLES,
                       "speakers": _speakers(code, domain)})
    tuning = [f"SPK-TUNE-{i:02d}" for i in range(1, 9)]
    return {
        "benchmark_id": "acme-stt-benchmark-v1",
        "customer": "Acme Support Co (fictional)",
        "vendors": ["VendorAlpha", "VendorBeta"],
        "audio": {"language": "en", "sample_rate_hz": 16000},
        "normalization": {"lowercase": True, "strip_punctuation": True,
                          "number_format": "words"},
        "slices": slices,
        "tuning_speakers": tuning,
        "min_slice_n_for_claim": 15,
        "bootstrap_reps": 1000,
        "bootstrap_seed": 1234,
    }


def _to_digits_form(text: str) -> str:
    out = text
    for words_form, digit_form in sorted(_WORD_TO_DIGIT.items(),
                                         key=lambda kv: -len(kv[0])):
        out = out.replace(words_form, digit_form)
        out = out.replace(words_form.capitalize(), digit_form)
    return out.rstrip(".").lower()


def _corrupt(normalized_ref: str, rng: random.Random, rate: float) -> str:
    """Fabricate one vendor hypothesis from the normalized reference:
    seeded substitutions, deletions and insertions at ``rate``."""
    out = []
    for w in normalized_ref.split():
        r = rng.random()
        if r < rate * 0.55:
            out.append(_SUBS.get(w, "um"))
        elif r < rate * 0.85:
            continue  # deletion
        else:
            out.append(w)
            if rng.random() < rate * 0.3:
                out.append(rng.choice(_FILLER))
    return " ".join(out)


# Per-vendor, per-accent word-error propensity. VendorAlpha is the
# stronger system overall; VendorBeta is closer on british speech.
_RATES = {
    "VendorAlpha": {"us_general": 0.06, "british": 0.10, "indian": 0.11},
    "VendorBeta": {"us_general": 0.13, "british": 0.12, "indian": 0.19},
}


def generate_bundle(seed: int = SEED, defective: bool = True) -> dict:
    rng = random.Random(seed)
    contract = build_contract()
    truth = []
    raw_refs = {}   # utterance_id -> (raw reference, accent)
    for slice_id, accent, domain, _ct in SLICE_DEFS:
        templates = _SUPPORT if domain == "support" else _SALES
        speakers = _speakers(dict(ACCENTS)[accent], domain)
        n = MIN_SAMPLES
        if defective and slice_id == "indian/sales":
            n = 0  # planted: missing slice
        elif defective and slice_id == "british/sales":
            n = 5  # planted: under-filled slice
        for i in range(n):
            uid = f"UTT-{slice_id.replace('/', '-').upper()}-{i + 1:03d}"
            template = templates[i % len(templates)]
            raw = template.format(num=_NUMBER_WORDS[i % len(_NUMBER_WORDS)])
            truth.append({"utterance_id": uid, "slice_id": slice_id,
                          "speaker_id": speakers[i % len(speakers)],
                          "reference": raw})
            raw_refs[uid] = (raw, accent)
    if defective:
        # Planted normalization mismatch: truth text rewritten into
        # digits / lowercase / no-punctuation form, and the manifest
        # honestly declares that (wrong) profile.
        for row in truth:
            row["reference"] = _to_digits_form(row["reference"])
    hypotheses = {}
    for vendor in contract["vendors"]:
        vrng = random.Random(seed + (1 if vendor == "VendorAlpha" else 2))
        hyps = []
        for row in truth:
            raw, accent = raw_refs[row["utterance_id"]]
            from normalize import normalize_text
            ref_n = normalize_text(raw, contract["normalization"])
            text = _corrupt(ref_n, vrng, _RATES[vendor][accent])
            hyps.append({"utterance_id": row["utterance_id"], "text": text})
        hypotheses[vendor] = hyps
    tuning_speakers = list(contract["tuning_speakers"])
    if defective:
        # Planted leakage: two eval speakers were also used to tune.
        leaked = [truth[0]["speaker_id"],
                  next(r["speaker_id"] for r in truth
                       if r["slice_id"] == "british/support")]
        tuning_speakers = tuning_speakers + leaked
    contract["tuning_speakers"] = tuning_speakers
    truth_norm_decl = ({"lowercase": True, "strip_punctuation": True,
                        "number_format": "digits"} if defective
                       else dict(contract["normalization"]))
    manifest = {
        "sample_rate_hz": 16000, "language": "en",
        "truth_normalization": truth_norm_decl,
        "hypothesis_normalization": {
            v: dict(contract["normalization"]) for v in contract["vendors"]},
        "tuning_speakers": list(tuning_speakers),
    }
    return {"contract": contract, "manifest": manifest,
            "truth": truth, "hypotheses": hypotheses}


def bundle_to_json(bundle: dict) -> str:
    return json.dumps(bundle, sort_keys=True, indent=1) + "\n"


def load_bundle(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "contract" not in data or "truth" not in data:
        raise ValueError("not a benchmark bundle (need contract + truth)")
    return data


def write_bundle(bundle: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(bundle_to_json(bundle))
