import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from generator import generate_bundle, write_bundle  # noqa: E402
from scorecard import build_scorecard  # noqa: E402


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="benchmark-cli-")
        cls.bad = os.path.join(cls.tmp, "defective.json")
        cls.good = os.path.join(cls.tmp, "clean.json")
        write_bundle(generate_bundle(defective=True), cls.bad)
        write_bundle(generate_bundle(defective=False), cls.good)

    def test_check_exit_codes(self):
        self.assertEqual(cli_main(["check", "--input", self.bad]), EXIT_FAIL)
        self.assertEqual(cli_main(["check", "--input", self.good]), EXIT_OK)
        self.assertEqual(cli_main(["check", "--input", "/tmp/no-such-benchmark-xyz.json"]),
                         EXIT_ERROR)

    def test_score_exit_codes(self):
        self.assertEqual(cli_main(["score", "--input", self.bad]), EXIT_FAIL)
        self.assertEqual(cli_main(["score", "--input", self.good]), EXIT_OK)

    def test_generate_and_validate_roundtrip(self):
        out = os.path.join(self.tmp, "gen.json")
        self.assertEqual(cli_main(["generate", "--clean", "--out", out]), EXIT_OK)
        self.assertEqual(cli_main(["validate", "--input", out]), EXIT_OK)
        self.assertEqual(cli_main(["report", "--input", out]), EXIT_OK)

    def test_serve_roundtrip(self):
        clean = generate_bundle(defective=False)
        reset_state(clean)
        server = make_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                        timeout=10) as resp:
                self.assertEqual(json.loads(resp.read()), {"status": "ok"})
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/score", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                served = json.loads(resp.read())
            self.assertEqual(served, build_scorecard(clean))
        finally:
            server.shutdown()
            server.server_close()
            reset_state()


if __name__ == "__main__":
    unittest.main()
