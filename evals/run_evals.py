"""Golden evals for customer-benchmark-design-kit.

SYNTHETIC DATA ONLY (fictional Acme Support Co / VendorAlpha /
VendorBeta). Every eval is deterministic: run_evals.py writes
eval_report.json and the file must be byte-identical across runs.
No timestamps, ports, or temp paths enter the report — only names,
booleans, pinned counts and hashes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))

from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from generator import bundle_to_json, generate_bundle, load_bundle  # noqa: E402
from helpers import floor_bundle  # noqa: E402
from scorecard import build_report, build_scorecard  # noqa: E402
from scoring import cer, normalization_impact, wer  # noqa: E402
from validation import coverage_summary, validate_bundle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def main():
    print("== golden evals: customer-benchmark-design-kit ==")
    clean = generate_bundle(defective=False)
    bad = generate_bundle(defective=True)

    # E1: generator determinism (bytes pinned, both flavours)
    clean_md5 = hashlib.md5(bundle_to_json(clean).encode()).hexdigest()
    bad_md5 = hashlib.md5(bundle_to_json(bad).encode()).hexdigest()
    check("E1 generator determinism (seed=42 md5 pinned, clean + defective)",
          bundle_to_json(generate_bundle(defective=False)) == bundle_to_json(clean)
          and clean_md5 == "b9d1ea1b6c1aeb19d2d64c554472c794"
          and bad_md5 == "85e93c0d480c466e40271ba4687669be",
          f"clean_md5={clean_md5} defective_md5={bad_md5}")

    # E2: truth counts pinned
    check("E2 truth counts pinned (clean 120, defective 85)",
          len(clean["truth"]) == 120 and len(bad["truth"]) == 85)

    # E3: defective validation pinned — exactly 6 issues, by code
    issues = validate_bundle(bad)
    codes = sorted(i.split(":")[0] for i in issues)
    check("E3 defective validation pinned (6 issues: 2x NORMALIZATION_MISMATCH, "
          "2x SPEAKER_LEAKAGE, SLICE_MISSING, SLICE_UNDERFILLED)",
          codes == ["NORMALIZATION_MISMATCH", "NORMALIZATION_MISMATCH",
                    "SLICE_MISSING", "SLICE_UNDERFILLED",
                    "SPEAKER_LEAKAGE", "SPEAKER_LEAKAGE"]
          and validate_bundle(clean) == [],
          f"codes={codes}")

    # E4: leakage speakers named
    leaks = [i for i in issues if i.startswith("SPEAKER_LEAKAGE")]
    check("E4 leakage speakers pinned (SPK-US-SUP-01, SPK-GB-SUP-01)",
          any("SPK-US-SUP-01" in i for i in leaks)
          and any("SPK-GB-SUP-01" in i for i in leaks))

    # E5: coverage pinned
    cov = coverage_summary(bad)
    check("E5 coverage pinned (indian/sales 0/20 missing, british/sales 5/20)",
          cov["indian/sales"] == {"declared_min": 20, "actual": 0, "ok": False}
          and cov["british/sales"] == {"declared_min": 20, "actual": 5, "ok": False}
          and all(cov[s]["ok"] for s in cov if s not in
                  ("indian/sales", "british/sales")))

    # E6: normalization impact pinned — raw vs after contract profile
    ia = normalization_impact(bad, "VendorAlpha")
    ib = normalization_impact(bad, "VendorBeta")
    check("E6 normalization impact pinned (Alpha raw .247325 -> .081051; "
          "Beta raw .321046 -> .165389)",
          ia["wer_raw_no_normalization"] == 0.247325
          and ia["wer_after_contract_normalization"] == 0.081051
          and ib["wer_raw_no_normalization"] == 0.321046
          and ib["wer_after_contract_normalization"] == 0.165389,
          f"alpha_gap={round(ia['wer_raw_no_normalization'] - ia['wer_after_contract_normalization'], 6)}")

    # E7: refusal gate on the defective bundle
    gate = build_scorecard(bad)
    check("E7 refusal gate pinned (REFUSED, scorecard None, 6 reasons)",
          gate["status"] == "REFUSED" and gate["scorecard"] is None
          and len(gate["reasons"]) == 6)

    # E8: clean scorecard overall WER/CER pinned
    sc = build_scorecard(clean)["scorecard"]
    check("E8 clean scorecard pinned (Alpha WER .086265 CER .086082; "
          "Beta WER .167994 CER .160452)",
          sc["overall"]["VendorAlpha"] == {"wer": 0.086265, "cer": 0.086082, "n": 120}
          and sc["overall"]["VendorBeta"] == {"wer": 0.167994, "cer": 0.160452, "n": 120})

    # E9: claims pinned — Alpha wins 4 slices, british slices no claim
    winners = {sid: c["winner"] for sid, c in sc["claims"].items()}
    check("E9 claims pinned (VendorAlpha x4; british/support + british/sales None, CI crosses 0)",
          winners == {"us_general/support": "VendorAlpha",
                      "us_general/sales": "VendorAlpha",
                      "british/support": None, "british/sales": None,
                      "indian/support": "VendorAlpha",
                      "indian/sales": "VendorAlpha"},
          f"winners={winners}")

    # E10: paired bootstrap pinned for one slice
    entry = sc["slices"]["us_general/support"]["wer_diff_a_minus_b"]
    check("E10 bootstrap pinned (us_general/support mean -0.090555, CI [-0.154192, -0.031717], n=20, reps=1000)",
          entry == {"n": 20, "mean_diff": -0.090555,
                    "ci_95": [-0.154192, -0.031717], "reps": 1000},
          f"ci={entry['ci_95']}")

    # E11: WER / CER hand-computed
    check("E11 WER/CER hand-computed (sub 1/3, del 1/4, CER 1/3)",
          wer("the cat sat", "the dog sat") == 1 / 3
          and wer("a b c d", "a c d") == 0.25
          and cer("abc", "abd") == 1 / 3)

    # E12: CLI check exit codes 1 / 0 / 2
    import tempfile
    tmp = tempfile.mkdtemp(prefix="benchmark-evals-")
    bad_path = os.path.join(tmp, "defective.json")
    good_path = os.path.join(tmp, "clean.json")
    from generator import write_bundle
    write_bundle(bad, bad_path)
    write_bundle(clean, good_path)
    codes_out = (_run_cli(["check", "--input", bad_path]),
                 _run_cli(["check", "--input", good_path]),
                 _run_cli(["check", "--input", "/tmp/no-such-benchmark-xyz.json"]))
    check("E12 CLI check exit codes 1/0/2 (defective refusal is by design)",
          codes_out == (EXIT_FAIL, EXIT_OK, EXIT_ERROR), f"codes={codes_out}")

    # E13: serve round-trip matches local computation
    reset_state(clean)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/score", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            served_score = json.loads(resp.read())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/report",
                                    timeout=10) as resp:
            served_report = json.loads(resp.read())
        serve_ok = (served_score == build_scorecard(clean)
                    and served_report == build_report(clean))
    finally:
        server.shutdown()
        server.server_close()
        reset_state()
    check("E13 serve round-trip matches local scorecard + report", serve_ok)

    # E14: claim floor — a valid bundle with a slice at n=10 (< 15)
    # scores overall but may not claim a winner for that slice.
    gate_floor = build_scorecard(floor_bundle())
    claim = gate_floor["scorecard"]["claims"]["us_general/support"]
    check("E14 claim floor pinned (valid bundle, n=10 slice: winner None, floor reason)",
          gate_floor["status"] == "SCORED" and claim["winner"] is None
          and "below claim floor" in claim["reason"],
          f"reason={claim['reason']}")

    # E15: bundled fixtures pinned
    fx_clean = load_bundle(os.path.join(ROOT, "fixtures", "clean_bundle.json"))
    fx_bad = load_bundle(os.path.join(ROOT, "fixtures", "defective_bundle.json"))
    check("E15 fixtures pinned (clean validates + same scorecard; defective refused)",
          validate_bundle(fx_clean) == []
          and build_scorecard(fx_clean) == build_scorecard(clean)
          and build_scorecard(fx_bad)["status"] == "REFUSED")

    passed = sum(1 for r in RESULTS if r["passed"])
    total_n = len(RESULTS)
    summary_doc = {"passed": passed, "total": total_n,
                   "all_passed": passed == total_n, "evals": RESULTS}
    with open(os.path.join(HERE, "eval_report.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary_doc, sort_keys=True) + "\n")
    print(f"\n{passed}/{total_n} evals passed -> evals/eval_report.json")
    return 0 if passed == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
