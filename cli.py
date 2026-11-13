"""CLI: generate | validate | score | report | check | demo | serve.

SYNTHETIC DATA ONLY - Acme Support Co, VendorAlpha and VendorBeta
are fictional and every bundle handled here is fabricated sample
data.

Exit codes:
  check : 0 = pass (bundle validates, scorecard produced),
          1 = REFUSED (validation failed - EXPECTED on the seeded
          defective bundle, by design: it plants a normalization
          mismatch, speaker leakage and slice coverage gaps, and
          the refusal gate exists to catch exactly those),
          2 = usage / IO / data-quality error
  others: 0 = success, 1 = scorecard refused (score only),
          2 = usage / IO error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generator import generate_bundle, load_bundle, write_bundle  # noqa: E402
from scorecard import build_report, build_scorecard  # noqa: E402
from validation import validate_bundle  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def _load_or_error(path: str) -> Optional[Dict]:
    try:
        return load_bundle(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _write_out(args, text: str, summary: str) -> int:
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    bundle = generate_bundle(seed=args.seed, defective=not args.clean)
    if args.out:
        try:
            write_bundle(bundle, args.out)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        kind = "clean" if args.clean else "defective (planted defects)"
        print(f"generated {kind} synthetic bundle "
              f"({len(bundle['truth'])} truth rows, seed={args.seed}) -> {args.out}")
        return EXIT_OK
    from generator import bundle_to_json
    print(bundle_to_json(bundle), end="")
    return EXIT_OK


def cmd_validate(args) -> int:
    bundle = _load_or_error(args.input)
    if bundle is None:
        return EXIT_ERROR
    issues = validate_bundle(bundle)
    payload = {"valid": not issues, "issues": issues}
    return _write_out(args, canonical(payload) + "\n", f"validate -> {args.out}")


def cmd_score(args) -> int:
    bundle = _load_or_error(args.input)
    if bundle is None:
        return EXIT_ERROR
    gate = build_scorecard(bundle)
    code = _write_out(args, canonical(gate) + "\n", f"score -> {args.out}")
    if code != EXIT_OK:
        return code
    return EXIT_OK if gate["status"] == "SCORED" else EXIT_FAIL


def cmd_report(args) -> int:
    bundle = _load_or_error(args.input)
    if bundle is None:
        return EXIT_ERROR
    return _write_out(args, canonical(build_report(bundle)) + "\n",
                      f"report -> {args.out}")


def cmd_check(args) -> int:
    bundle = _load_or_error(args.input)
    if bundle is None:
        return EXIT_ERROR
    issues = validate_bundle(bundle)
    if not issues:
        print("check PASS: bundle validates - scorecard produced")
        return EXIT_OK
    for issue in issues:
        print(f"validation: {issue}")
    print(f"check FAIL (refusal gate): {len(issues)} validation issue(s) - "
          f"no scorecard will be produced for this bundle")
    return EXIT_FAIL


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _State:
    def __init__(self):
        self.bundle: Dict = generate_bundle(defective=False)


_STATE = _State()


def get_state() -> _State:
    return _STATE


def reset_state(bundle: Optional[Dict] = None) -> None:
    _STATE.bundle = bundle if bundle is not None else generate_bundle(defective=False)


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: Any) -> None:
        body = (canonical(payload) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw) if raw.strip() else {}
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object")
        return body

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/report":
            return self._send_json(200, build_report(_STATE.bundle))
        return self._send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        try:
            body = self._body()
            bundle = body.get("bundle", _STATE.bundle)
            if self.path == "/validate":
                issues = validate_bundle(bundle)
                return self._send_json(200, {"valid": not issues, "issues": issues})
            if self.path == "/score":
                return self._send_json(200, build_scorecard(bundle))
            if self.path == "/report":
                return self._send_json(200, build_report(bundle))
            return self._send_json(404, {"error": "unknown endpoint"})
        except (ValueError, TypeError, KeyError) as exc:
            return self._send_json(400, {"error": f"bad request: {exc}"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    if args.input:
        bundle = _load_or_error(args.input)
        if bundle is None:
            return EXIT_ERROR
        reset_state(bundle)
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  "
          f"(POST /validate, /score, /report; GET /report, /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="customer-benchmark-design-kit",
        description="Customer STT benchmark design kit: contract, "
                    "truth-file validation, refusal gate, WER/CER "
                    "scorecard (synthetic Acme sample data).")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a synthetic benchmark bundle")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--clean", action="store_true",
                   help="generate the clean bundle (default: defective, planted defects)")
    g.add_argument("--out", default=None)
    g.set_defaults(func=cmd_generate)

    for name, fn, helptext in (
            ("validate", cmd_validate, "contract + truth-file validation"),
            ("score", cmd_score, "refusal gate + scorecard (exit 1 when refused)"),
            ("report", cmd_report, "validation + coverage + normalization impact + scorecard")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--input", required=True)
        s.add_argument("--out", default=None)
        s.set_defaults(func=fn)

    c = sub.add_parser("check", help="CI gate: exit 0 pass / 1 refused / 2 error")
    c.add_argument("--input", required=True)
    c.set_defaults(func=cmd_check)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="localhost JSON API")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--input", default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
