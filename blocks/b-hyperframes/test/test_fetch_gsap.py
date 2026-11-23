"""Tests for scripts/fetch_gsap.py against a local stand-in registry. No internet needed."""
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_gsap.py"
LIB = b"/* stand-in library, not GSAP */\nwindow.gsap = {};\n"


def make_tarball(content):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("package/dist/gsap.min.js")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def integrity(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


class Registry:
    """Serves /gsap/3.14.2 and /tarball. Behaviour is switched per test."""

    def __init__(self):
        self.tarball = make_tarball(LIB)
        self.published = integrity(self.tarball)
        self.redirect = False
        self.tarball_host = None
        self.hits = []
        reg = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                reg.hits.append(self.path)
                if self.path == "/gsap/3.14.2":
                    base = reg.tarball_host or f"http://127.0.0.1:{reg.port}"
                    body = json.dumps({"version": "3.14.2", "dist": {
                        "integrity": reg.published, "tarball": base + "/tarball",
                        "shasum": hashlib.sha1(reg.tarball).hexdigest()}}).encode()
                    self.send_response(200)
                elif self.path == "/tarball":
                    if reg.redirect:
                        self.send_response(302)
                        self.send_header("Location", "http://127.0.0.1:1/x")
                        self.end_headers()
                        return
                    body = reg.tarball
                    self.send_response(200)
                else:
                    body = b"{}"
                    self.send_response(404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class FetchGsap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(os.path.realpath(self.tmp.name))
        self.reg = Registry()
        self.addCleanup(self.reg.stop)
        self.pins = self.work / "pins.json"
        self.write_pins()

    def tearDown(self):
        self.tmp.cleanup()

    def write_pins(self, **over):
        pin = {"version": "3.14.2", "tarball_integrity": self.reg.published,
               "file": "package/dist/gsap.min.js", "file_sha256": hashlib.sha256(LIB).hexdigest()}
        pin.update(over)
        self.pins.write_text(json.dumps({"gsap": pin}))

    def fetch(self, *extra, outdir="vendor"):
        cmd = [sys.executable, str(SCRIPT), "--outdir", outdir, "--work", str(self.work),
               "--registry", self.reg.url, "--pins", str(self.pins), *extra]
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work)
        return done.returncode, done.stdout, done.stderr

    def test_verified_fetch_writes_file_and_record(self):
        code, out, err = self.fetch()
        self.assertEqual(code, 0, err)
        target = self.work / "vendor" / "gsap.min.js"
        self.assertEqual(Path(out.strip()), target)
        self.assertEqual(target.read_bytes(), LIB)
        record = json.loads((self.work / "vendor" / "gsap.min.js.json").read_text())
        self.assertEqual(record["version"], "3.14.2")
        self.assertEqual(record["tarball_integrity"], self.reg.published)
        self.assertEqual(record["file_sha256"], hashlib.sha256(LIB).hexdigest())

    def test_second_run_uses_the_verified_file_without_the_network(self):
        self.assertEqual(self.fetch()[0], 0)
        hits = len(self.reg.hits)
        code, out, err = self.fetch()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.reg.hits), hits)
        self.assertEqual(self.fetch("--force")[0], 0)
        self.assertGreater(len(self.reg.hits), hits)

    def test_tampered_tarball_is_refused(self):
        self.reg.tarball = make_tarball(LIB + b"// extra\n")
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("integrity mismatch", err)
        self.assertFalse((self.work / "vendor" / "gsap.min.js").exists())

    def test_registry_value_that_differs_from_the_pin_is_refused(self):
        self.write_pins(tarball_integrity=integrity(b"something else"))
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("differs from the pinned", err)

    def test_library_file_checksum_must_match_the_pin(self):
        self.write_pins(file_sha256="0" * 64)
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("does not match the pinned", err)
        self.assertFalse((self.work / "vendor" / "gsap.min.js").exists())

    def test_missing_integrity_in_registry_answer_is_refused(self):
        self.reg.published = "sha1-nothing"
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("sha512", err)

    def test_redirects_are_not_followed(self):
        self.reg.redirect = True
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("download failed", err)

    def test_tarball_on_another_host_is_refused(self):
        self.reg.tarball_host = "http://127.0.0.1:9"
        code, out, err = self.fetch()
        self.assertEqual(code, 1)
        self.assertIn("not on the registry host", err)

    def test_usage_errors(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--outdir", "v", "--work", str(self.work),
                               "--registry", "https://evil.example"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        code, out, err = self.fetch(outdir="../escape")
        self.assertEqual(code, 2)
        done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)

    def test_pins_without_checksums_are_a_usage_error(self):
        base = {"version": "3.14.2", "file": "package/dist/gsap.min.js",
                "tarball_integrity": self.reg.published, "file_sha256": hashlib.sha256(LIB).hexdigest()}
        for missing in ("tarball_integrity", "file_sha256", "file", "version"):
            with self.subTest(missing):
                pin = {k: v for k, v in base.items() if k != missing}
                self.pins.write_text(json.dumps({"gsap": pin}))
                code, out, err = self.fetch()
                self.assertEqual(code, 2, err)
                self.assertFalse((self.work / "vendor" / "gsap.min.js").exists())
        self.pins.write_text(json.dumps({}))
        self.assertEqual(self.fetch()[0], 2)

    def test_symlinked_vendor_folder_is_refused(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, outside, True)
        os.symlink(outside, self.work / "vendor")
        code, out, err = self.fetch()
        self.assertEqual(code, 2, err)
        self.assertEqual(list(outside.iterdir()), [])
        os.unlink(self.work / "vendor")
        (self.work / "vendor").mkdir()
        os.symlink(outside / "elsewhere.js", self.work / "vendor" / "gsap.min.js")
        self.assertEqual(self.fetch()[0], 2)
        self.assertFalse((outside / "elsewhere.js").exists())

    def test_unexpected_error_prints_one_line_and_no_traceback(self):
        code = "import sys; sys.path.insert(0, %r); import hfcommon\ndef m():\n    raise RuntimeError('secret detail')\nhfcommon.run_main(m)" % str(SCRIPT.parent)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("Traceback", done.stderr)
        self.assertNotIn("secret detail", done.stderr)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1)

    def test_shipped_pins_are_well_formed(self):
        pins = json.loads((SCRIPT.parent.parent / "pins.json").read_text())
        self.assertEqual(pins["gsap"]["version"], "3.14.2")
        self.assertRegex(pins["gsap"]["file_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(pins["gsap"]["tarball_integrity"].startswith("sha512-"))


if __name__ == "__main__":
    unittest.main()
