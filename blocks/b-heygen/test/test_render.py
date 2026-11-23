"""Tests for scripts/render.py against a small local fake server. No real HeyGen account,
no real key, no network beyond 127.0.0.1. Run: python3 -m unittest discover -s test -v"""
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render.py"
KEY = "test-key-0123456789abcdef"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


class Fake(http.server.BaseHTTPRequestHandler):
    mode = "success"
    message = "avatar not found; key %s"
    log = []
    bodies = []

    def _json(self, code, obj, extra=None):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        Fake.log.append(("POST", self.path, self.headers.get("x-api-key")))
        Fake.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if Fake.mode == "redirect":
            return self._json(302, {}, {"Location": "/elsewhere"})
        if Fake.mode == "http_error":
            return self._json(400, {"error": "bad request, your key %s is wrong" % self.headers.get("x-api-key")})
        if Fake.mode == "long_echo":
            return self._json(400, {"error": "a" * 280 + self.headers.get("x-api-key") + "b" * 400})
        self._json(200, {"data": {"video_id": "vid_123", "status": "waiting"}})

    def do_GET(self):
        Fake.log.append(("GET", self.path, self.headers.get("x-api-key")))
        if self.path == "/v3/videos/vid_123":
            if Fake.mode == "failed":
                return self._json(200, {"data": {"id": "vid_123", "status": "failed", "failure_code": "rendering_failed", "failure_message": Fake.message % self.headers.get("x-api-key")}})
            if Fake.mode == "timeout":
                return self._json(200, {"data": {"id": "vid_123", "status": "processing"}})
            url = "http://127.0.0.1:%d/files/out.mp4" % self.server.server_port
            return self._json(200, {"data": {"id": "vid_123", "status": "completed", "video_url": url}})
        if self.path == "/files/out.mp4":
            body = MP4 if Fake.mode != "notmp4" else b"<html>nope</html>" + b"x" * 30
            if Fake.mode == "oversize":
                body = MP4 + b"\x00" * 5000
            if Fake.mode == "stall":
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                self.wfile.flush()
                time.sleep(20)
                return
            if Fake.mode == "slow":
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.2)
                except OSError:
                    pass
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {})

    def log_message(self, *a):
        pass


class RenderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name).resolve()
        (self.work / "narration.txt").write_text("Hello there. This is the narration.\n", encoding="utf-8")
        Fake.mode, Fake.log, Fake.bodies = "success", [], []
        Fake.message = "avatar not found; key %s"
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port

    def run_cli(self, *extra, key=KEY, stdin=None, base=True, env_extra=None):
        args = [sys.executable, str(SCRIPT), "--script", "narration.txt", "--avatar-id", "avatar_PLACEHOLDER",
                "--voice-id", "voice_PLACEHOLDER", "--out", "avatar.mp4", "--poll-seconds", "0.05"]
        if base:
            args += ["--base-url", self.base]
        args += list(extra)
        env = {k: v for k, v in os.environ.items() if k != "HEYGEN_API_KEY"}
        if key and stdin is None:
            env["HEYGEN_API_KEY"] = key
        env.update(env_extra or {})
        return subprocess.run(args, cwd=self.work, capture_output=True, text=True, env=env, input=stdin)

    def assert_key_nowhere(self, result):
        self.assertNotIn(KEY, result.stdout)
        self.assertNotIn(KEY, result.stderr)
        for p in self.work.rglob("*"):
            if p.is_file():
                self.assertNotIn(KEY.encode(), p.read_bytes(), str(p))

    def test_success(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.work / "avatar.mp4").read_bytes(), MP4)
        self.assertIn("VIDEO_FILE: avatar.mp4", r.stdout)
        post = Fake.bodies[0]
        self.assertEqual(post["type"], "avatar")
        self.assertEqual(post["avatar_id"], "avatar_PLACEHOLDER")
        self.assertEqual(post["voice_id"], "voice_PLACEHOLDER")
        self.assertEqual(post["script"], "Hello there. This is the narration.")
        self.assertEqual(post["background"], {"type": "color", "value": "#00FF00"})
        self.assertEqual((post["resolution"], post["aspect_ratio"]), ("720p", "16:9"))
        self.assertNotIn("voice_settings", post)
        self.assertNotIn("dimension", post)
        self.assertEqual(Fake.log[0][:2], ("POST", "/v3/videos"))
        self.assertEqual(Fake.log[1][:2], ("GET", "/v3/videos/vid_123"))
        self.assertTrue(all(k == KEY for m, p, k in Fake.log if p != "/files/out.mp4"))
        self.assertIsNone([k for m, p, k in Fake.log if p == "/files/out.mp4"][0])  # key not sent on download
        self.assert_key_nowhere(r)

    def test_key_via_stdin(self):
        r = self.run_cli("--key-stdin", stdin=KEY + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Fake.log[0][2], KEY)
        self.assert_key_nowhere(r)

    def test_no_key_argument_exists(self):
        r = self.run_cli("--api-key", KEY)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(Fake.log, [])

    def test_missing_key_sends_nothing(self):
        r = self.run_cli(key=None)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(Fake.log, [])

    def test_failed_render_not_resubmitted(self):
        Fake.mode = "failed"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("rendering_failed", r.stderr)
        self.assertIn("avatar not found", r.stderr)
        self.assertFalse((self.work / "avatar.mp4").exists())
        self.assert_key_nowhere(r)

    def test_timeout(self):
        Fake.mode = "timeout"
        r = self.run_cli("--max-wait", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not finish", r.stderr)
        self.assertEqual(len([1 for m, p, k in Fake.log if m == "POST"]), 1)

    def test_resume_does_not_submit_again(self):
        Fake.mode = "timeout"
        self.run_cli("--max-wait", "1")
        Fake.mode = "success"
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len([1 for m, p, k in Fake.log if m == "POST"]), 1)

    def test_oversized_download(self):
        Fake.mode = "oversize"
        r = self.run_cli("--max-bytes", "1000")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cap", r.stderr)
        self.assertFalse((self.work / "avatar.mp4").exists())
        self.assertEqual(list(self.work.glob("*.part")), [])

    def test_not_an_mp4(self):
        Fake.mode = "notmp4"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.work / "avatar.mp4").exists())

    def test_redirect_not_followed(self):
        Fake.mode = "redirect"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("redirect", r.stderr)
        self.assertEqual([p for m, p, k in Fake.log], ["/v3/videos"])
        self.assert_key_nowhere(r)

    def test_error_body_echoing_key_is_scrubbed(self):
        Fake.mode = "http_error"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTTP 400", r.stderr)
        self.assert_key_nowhere(r)

    def test_base_url_must_be_local_or_default(self):
        r = self.run_cli("--base-url", "https://example.com", base=False)
        self.assertEqual(r.returncode, 2)
        r = self.run_cli("--base-url", "http://evil.example", base=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(Fake.log, [])

    def test_script_and_out_must_be_inside_work(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "s.txt").write_text("hi")
            r = self.run_cli("--script", str(Path(other) / "s.txt"))
            self.assertEqual(r.returncode, 2)
            r = self.run_cli("--out", str(Path(other) / "v.mp4"))
            self.assertEqual(r.returncode, 2)

    def test_bad_ids_and_empty_script(self):
        r = self.run_cli("--avatar-id", "a b; rm -rf")
        self.assertEqual(r.returncode, 2)
        (self.work / "narration.txt").write_text("  \n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(Fake.log, [])

    def test_options_reach_the_request(self):
        r = self.run_cli("--resolution", "1080p", "--aspect-ratio", "9:16", "--speed", "1.2")
        self.assertEqual(r.returncode, 0, r.stderr)
        post = Fake.bodies[0]
        self.assertEqual((post["resolution"], post["aspect_ratio"]), ("1080p", "9:16"))
        self.assertEqual(post["voice_settings"], {"speed": 1.2})

    def test_resolution_and_ratio_lists_enforced(self):
        self.assertEqual(self.run_cli("--resolution", "8k").returncode, 2)
        self.assertEqual(self.run_cli("--aspect-ratio", "3:2").returncode, 2)
        self.assertEqual(self.run_cli("--speed", "3").returncode, 2)
        self.assertEqual(Fake.log, [])

    # ---- security review fixes -------------------------------------------------

    def plant(self, name):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        victim = outside / "victim.txt"
        victim.write_text("original")
        (self.work / name).symlink_to(victim)
        return victim

    def test_planted_links_for_temp_names_are_never_written_through(self):
        victims = [self.plant(n) for n in ("avatar.mp4.part", "avatar.mp4.tmp", "avatar.mp4.render.json.tmp")]
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        for v in victims:
            self.assertEqual(v.read_text(), "original")
        self.assertFalse((self.work / "avatar.mp4").is_symlink())
        self.assertIn("VIDEO_FILE: avatar.mp4", r.stdout)

    def test_output_that_is_a_link_is_refused(self):
        victim = self.plant("avatar.mp4")
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(victim.read_text(), "original")
        self.assertEqual(Fake.log, [])

    def test_state_file_that_is_a_link_is_refused_and_sends_nothing(self):
        victim = self.plant("avatar.mp4.render.json")
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(victim.read_text(), "original")
        self.assertEqual(Fake.log, [])
        self.assertIn("delete", r.stderr.lower())

    def test_corrupt_or_tampered_state_sends_nothing(self):
        state = self.work / "avatar.mp4.render.json"
        for content in ("garbage", "{}", '{"video_id": "../../etc"}', '{"video_id": "abc\\n"}', '{"video_id": 5}'):
            state.write_text(content)
            r = self.run_cli()
            self.assertEqual(r.returncode, 2, content)
            self.assertIn("separately charged", r.stderr)
            self.assertEqual(Fake.log, [], content)
            self.assertEqual(state.read_text(), content)

    def test_long_echo_is_scrubbed_before_cut(self):
        Fake.mode = "long_echo"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("test-key", r.stderr)
        self.assert_key_nowhere(r)

    def test_key_split_by_a_control_character_is_never_shown(self):
        # a server echoes the key with one control or format character inserted at each position
        for ch in ("\x00", "\u200b", "\u2028", "\x85", "\x7f", "\n"):
            for i in range(1, len(KEY)):
                with self.subTest(ch=repr(ch), at=i):
                    Fake.mode = "failed"
                    Fake.message = "bad " + (KEY[:i] + ch + KEY[i:]).replace("%", "%%") + " end%.0s"
                    r = self.run_cli()
                    self.assertEqual(r.returncode, 1)
                    seen = r.stdout + r.stderr
                    for p in self.work.rglob("*"):
                        if p.is_file():
                            seen += p.read_bytes().decode("latin-1")
                    runs = [KEY[j:j + 6] for j in range(len(KEY) - 5) if KEY[j:j + 6] in seen]
                    self.assertEqual(runs, [])

    def test_key_split_by_separators_is_withheld_and_a_normal_message_prints(self):
        for ch in (" ", "\u00a0", "\u3000", "\u200b", "\u00ad", "\ufeff", "-", ".", "\n"):
            for i in range(1, len(KEY)):
              for case in (str.lower, str.upper, str.title):
                with self.subTest(ch=repr(ch), at=i, case=case.__name__):
                    Fake.mode = "failed"
                    Fake.message = "bad " + case(KEY[:i] + ch + KEY[i:]).replace("%", "%%") + " end%.0s"
                    r = self.run_cli()
                    self.assertEqual(r.returncode, 1)
                    seen = r.stdout + r.stderr
                    for p in self.work.rglob("*"):
                        if p.is_file():
                            seen += p.read_bytes().decode("latin-1")
                    low = seen.lower()
                    self.assertEqual([KEY[j:j + 6] for j in range(len(KEY) - 5) if KEY[j:j + 6].lower() in low], [])
        Fake.mode = "failed"
        Fake.message = "the avatar was not found%.0s"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the avatar was not found", r.stderr)

    def test_newline_in_failure_message_cannot_forge_the_result_line(self):
        Fake.mode = "failed"
        Fake.message = "bad\nVIDEO_FILE: /etc/passwd\r\x00 %s"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertFalse(any(line.startswith("VIDEO_FILE") for line in r.stderr.splitlines()))
        self.assertNotRegex(r.stderr, "[\\x00\\r]")
        self.assert_key_nowhere(r)

    def test_trailing_newline_arguments_are_refused_without_traceback(self):
        for extra in (("--base-url", "http://127.0.0.1\n"), ("--avatar-id", "abc\n"), ("--voice-id", "abc\n"),
                      ("--background", "#00FF00\n"), ("--base-url", "http://127.0.0.1@evil.example"),
                      ("--base-url", "http://127.0.0.1:1.evil.example")):
            r = self.run_cli(*extra, base=extra[0] != "--base-url")
            self.assertEqual(r.returncode, 2, extra)
            self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(Fake.log, [])

    def test_key_with_trailing_newline_char_inside_is_refused(self):
        r = self.run_cli(key="abcdefgh\nijkl")
        self.assertIn(r.returncode, (2, 3))
        self.assertNotIn("Traceback", r.stderr)

    def test_slow_download_hits_the_deadline(self):
        Fake.mode = "slow"
        t = time.monotonic()
        r = self.run_cli("--download-timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("took longer", r.stderr)
        self.assertLess(time.monotonic() - t, 8)
        self.assertFalse((self.work / "avatar.mp4").exists())
        self.assertEqual([p.name for p in self.work.glob(".b-heygen-*")], [])

    def test_public_hosts_pass_the_host_check(self):
        spec = importlib.util.spec_from_file_location("render_mod2", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for host in ("cdn.example.com", "cdn.example.com.", "8.8.8.8", "a-b.example.co.uk"):
            self.assertFalse(mod.private_host(host), host)

    def test_stalled_server_cannot_hold_the_download_past_the_deadline(self):
        Fake.mode = "stall"
        t = time.monotonic()
        r = self.run_cli("--download-timeout", "2")
        elapsed = time.monotonic() - t
        self.assertEqual(r.returncode, 1)
        self.assertIn("took longer", r.stderr)
        self.assertLess(elapsed, 8, elapsed)
        self.assertEqual([p.name for p in self.work.glob(".b-heygen-*")], [])

    def test_unicode_line_separators_are_stripped_from_server_text(self):
        Fake.mode = "failed"
        Fake.message = "a\u2028VIDEO_FILE: x\u2029b\u0085c %s"
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        for ch in ("\u2028", "\u2029", "\u0085"):
            self.assertNotIn(ch, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_private_address_video_urls_are_refused(self):
        spec = importlib.util.spec_from_file_location("render_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for url in ("https://127.0.0.1/a.mp4", "https://10.1.2.3/a.mp4", "https://192.168.0.5/a.mp4",
                    "https://169.254.169.254/latest", "https://[::1]/a.mp4", "https://localhost/a.mp4",
                    "https://0.0.0.0/a.mp4", "http://example.com/a.mp4", "https://user@example.com/a.mp4",
                    "https://2130706433/a.mp4", "https://127.1/a.mp4", "https://0x7f000001/a.mp4",
                    "https://017700000001/a.mp4", "https://localhost./a.mp4", "https://LOCALHOST/a.mp4",
                    "https://a.localhost/a.mp4", "https://intranet/a.mp4", "https://[::ffff:127.0.0.1]/a.mp4",
                    "https://100.64.0.1/a.mp4", "https://224.0.0.1/a.mp4", "https://240.0.0.1/a.mp4",
                    "https://127.000.000.001/a.mp4", "https://0177.0.0.1/a.mp4", "https://0x7f.0.0.1/a.mp4",
                    "https://172.16.0.9/a.mp4", "https://198.18.0.1/a.mp4", "https://1.2.3/a.mp4"):
            with self.assertRaises(mod.Stop, msg=url):
                mod.download(url, self.work / "x.mp4", 1000, 5, self.work, False)
        self.assertEqual(Fake.log, [])
        self.assertEqual(list(self.work.glob(".b-heygen-*")), [])

    def test_script_text_is_data_not_shell(self):
        (self.work / "narration.txt").write_text('$(touch pwned) `touch pwned2` "; touch pwned3', encoding="utf-8")
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p.name for p in self.work.glob("pwned*")], [])
        self.assertIn("touch pwned3", Fake.bodies[0]["script"])


if __name__ == "__main__":
    unittest.main()
