"""End-to-end demo: generate -> validate (REFUSED) -> fix -> score
-> claim gate -> check -> serve.

SYNTHETIC DATA ONLY (fictional Acme Support Co / VendorAlpha /
VendorBeta). Runs fully offline; the serve round-trip is loopback
only on an ephemeral port. Every stage asserts.

The demo leads with the refusal, because that is the point of the
kit: the seeded bundle's truth file was produced under the wrong
normalization profile, two of its speakers leaked from the tuning
set, and two slices fail coverage — so no scorecard exists for it,
however nicely the numbers would have printed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from generator import generate_bundle, write_bundle  # noqa: E402
from scorecard import build_report, build_scorecard  # noqa: E402
from scoring import normalization_impact  # noqa: E402
from validation import validate_bundle  # noqa: E402


def _request(port: int, path: str, payload=None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def main() -> None:
    print("== 1. generate the seeded DEFECTIVE bundle (seed=42) ==")
    defective = generate_bundle()
    again = generate_bundle()
    assert defective == again, "generator must be deterministic"
    print(f"   {len(defective['truth'])} truth rows, deterministic")

    print("\n== 2. validation catches the planted defects ==")
    issues = validate_bundle(defective)
    for issue in issues:
        print(f"   - {issue}")
    assert any(i.startswith("NORMALIZATION_MISMATCH") for i in issues)
    assert any(i.startswith("SPEAKER_LEAKAGE") for i in issues)
    assert any(i.startswith("SLICE_MISSING") for i in issues)
    assert any(i.startswith("SLICE_UNDERFILLED") for i in issues)

    print("\n== 3. what the normalization mismatch would have cost ==")
    for vendor in defective["contract"]["vendors"]:
        impact = normalization_impact(defective, vendor)
        print(f"   {vendor}: WER raw (no normalization) "
              f"{impact['wer_raw_no_normalization']:.2%} vs after contract "
              f"normalization {impact['wer_after_contract_normalization']:.2%}")

    print("\n== 4. THE REFUSAL GATE: no scorecard for the defective bundle ==")
    gate = build_scorecard(defective)
    assert gate["status"] == "REFUSED" and gate["scorecard"] is None
    print(f"   status=REFUSED, {len(gate['reasons'])} reason(s), scorecard=None")

    print("\n== 5. the CLEAN bundle validates and scores ==")
    clean = generate_bundle(defective=False)
    assert validate_bundle(clean) == [], validate_bundle(clean)[:3]
    gate = build_scorecard(clean)
    assert gate["status"] == "SCORED"
    sc = gate["scorecard"]
    for v in sc["vendors"]:
        print(f"   {v}: overall WER {sc['overall'][v]['wer']:.2%}, "
              f"CER {sc['overall'][v]['cer']:.2%} (n={sc['overall'][v]['n']})")
    for sid, claim in sc["claims"].items():
        entry = sc["slices"][sid]
        ci = entry["wer_diff_a_minus_b"]["ci_95"]
        print(f"   {sid}: diff CI [{ci[0]:+.4f}, {ci[1]:+.4f}] "
              f"winner={claim['winner']} ({claim['reason']})")

    print("\n== 6. CLI check gate (1 on defective BY DESIGN, 0 on clean, 2 on missing) ==")
    tmp = tempfile.mkdtemp(prefix="benchmark-demo-")
    bad_path = os.path.join(tmp, "defective.json")
    good_path = os.path.join(tmp, "clean.json")
    write_bundle(defective, bad_path)
    write_bundle(clean, good_path)
    code_bad = cli_main(["check", "--input", bad_path])
    code_good = cli_main(["check", "--input", good_path])
    code_err = cli_main(["check", "--input", "/tmp/no-such-benchmark-xyz.json"])
    print(f"   defective={code_bad} clean={code_good} missing-file={code_err}")
    assert code_bad == EXIT_FAIL and code_good == EXIT_OK and code_err == 2

    print("\n== 7. live localhost serve round-trip ==")
    reset_state(clean)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = _request(port, "/health")
        assert status == 200 and health == {"status": "ok"}
        status, served_score = _request(port, "/score", payload={}, method="POST")
        assert status == 200 and served_score == build_scorecard(clean)
        status, served_report = _request(port, "/report")
        assert status == 200 and served_report == build_report(clean)
        print("   POST /score and GET /report match local computation")
    finally:
        server.shutdown()
        server.server_close()
        reset_state()

    print("\nDemo OK: generate, validation catches, normalization impact, "
          "refusal gate, scorecard + claims, check and serve verified.")


if __name__ == "__main__":
    main()
