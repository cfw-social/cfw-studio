"""Tests for scripts/voiceover.py against a small local fake server. No network, no account, no real key."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "voiceover.py"
KEY = "sk_fake_key_1234567890abcdef"
MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 300


class Handler(BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        Handler.seen.append({"path": self.path, "key": self.headers.get("xi-api-key"), "body": json.loads(body or b"{}")})
        m = Handler.mode
        if m == "ok":
            return self.send(200, MP3, "audio/mpeg")
        if m in ("401", "402", "429", "404", "422"):
            detail = {"status": "x", "message": "bad thing for " + KEY + "\nAUDIO_FILE: evil.mp3"}
            if m == "422":
                detail = [{"msg": "text too odd"}]
            return self.send(int(m), json.dumps({"detail": detail}).encode(), "application/json")
        if m == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if m == "big":
            return self.send(200, b"ID3" + b"\x00" * 50000, "audio/mpeg")
        if m == "html":
            return self.send(200, b"<html>" + b"x" * 400, "text/html")
        if m == "slow":
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.write(b"ID3" + b"\x00" * 100)
            self.wfile.flush()
            time.sleep(5)
            return

    def send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.wd = Path(self._tmp.name)
        (self.wd / "script.txt").write_text("Hello there. This is the narration.", encoding="utf-8")
        Handler.mode, Handler.seen = "ok", []

    def tearDown(self):
        self._tmp.cleanup()

    def run_vo(self, *extra, key=KEY, stdin=None, base=None, voice="voiceId12345", out="work/vo.mp3"):
        env = {k: v for k, v in os.environ.items() if k != "ELEVENLABS_API_KEY"}
        if key and stdin is None:
            env["ELEVENLABS_API_KEY"] = key
        args = [sys.executable, "-I", str(SCRIPT), "--text-file", "script.txt", "--voice-id", voice, "--out", out,
                "--base-url", base or "http://127.0.0.1:%d" % self.port, *extra]
        return subprocess.run(args, cwd=self.wd, env=env, input=stdin, text=True, capture_output=True, timeout=60)

    def last(self, r):
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len([l for l in lines if l.startswith(("AUDIO_FILE:", "AUDIO_FAILED:"))]), 1, r.stdout)
        self.assertTrue(lines[-1].startswith(("AUDIO_FILE:", "AUDIO_FAILED:")))
        return lines[-1]

    def assertClean(self, r):
        self.assertNotIn(KEY, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class Calls(Base):
    def test_success_request_shape_and_file(self):
        r = self.run_vo("--stability", "0.4", "--speed", "1.1", "--use-speaker-boost")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.last(r), "AUDIO_FILE: work/vo.mp3")
        self.assertEqual((self.wd / "work/vo.mp3").read_bytes(), MP3)
        seen = Handler.seen[0]
        self.assertEqual(seen["path"], "/v1/text-to-speech/voiceId12345?output_format=mp3_44100_128")
        self.assertEqual(seen["key"], KEY)
        self.assertEqual(seen["body"]["model_id"], "eleven_multilingual_v2")
        self.assertEqual(seen["body"]["voice_settings"], {"stability": 0.4, "speed": 1.1, "use_speaker_boost": True})
        self.assertEqual(len(Handler.seen), 1, "the call is made once")
        self.assertClean(r)
        self.assertEqual([p.name for p in (self.wd / "work").iterdir()], ["vo.mp3"], "no temp file is left")

    def test_key_on_stdin(self):
        r = self.run_vo("--key-stdin", key=None, stdin=KEY + "\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(Handler.seen[0]["key"], KEY)

    def test_provider_errors_are_one_clean_failed_line_without_the_key(self):
        expect = {"401": "key was refused", "402": "credits", "429": "rate limiting", "404": "voice id", "422": "rejected"}
        for mode, words in expect.items():
            Handler.mode = mode
            r = self.run_vo()
            self.assertEqual(r.returncode, 1, mode)
            line = self.last(r)
            self.assertTrue(line.startswith("AUDIO_FAILED:"), line)
            self.assertIn(words, line)
            self.assertClean(r)
            self.assertFalse((self.wd / "work/vo.mp3").exists(), mode)
        Handler.mode = "401"
        r = self.run_vo()
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, "a forged line in a server message must not become a line")
        self.assertNotIn("AUDIO_FILE", self.last(r).split("AUDIO_FAILED:")[0])
        self.assertIn("withheld", r.stdout)

    def test_redirect_is_not_followed(self):
        Handler.mode = "redirect"
        r = self.run_vo()
        self.assertEqual(r.returncode, 1)
        self.assertIn("redirect", self.last(r))
        self.assertEqual(len(Handler.seen), 1)

    def test_oversized_body_and_non_mp3_are_refused(self):
        Handler.mode = "big"
        r = self.run_vo("--max-bytes", "2048")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cap", self.last(r))
        Handler.mode = "html"
        r = self.run_vo()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not an MP3", self.last(r))
        self.assertFalse((self.wd / "work/vo.mp3").exists())

    def test_slow_body_hits_the_deadline(self):
        Handler.mode = "slow"
        t = time.monotonic()
        r = self.run_vo("--timeout", "1")
        self.assertLess(time.monotonic() - t, 4)
        self.assertEqual(r.returncode, 1)
        self.assertIn("timed out", self.last(r))
        self.assertFalse((self.wd / "work/vo.mp3").exists())

    def test_planted_symlink_target_is_refused(self):
        (self.wd / "work").mkdir()
        victim = self.wd / "victim.txt"
        victim.write_text("keep")
        os.symlink(victim, self.wd / "work/vo.mp3")
        r = self.run_vo()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(victim.read_text(), "keep")
        self.assertEqual(Handler.seen, [], "nothing is sent when the output is refused")

    def test_output_folder_that_is_a_link_out_is_refused(self):
        with tempfile.TemporaryDirectory() as other:
            os.symlink(other, self.wd / "work")
            r = self.run_vo()
            self.assertEqual(r.returncode, 2)
            self.assertEqual(os.listdir(other), [])


class Scrub(unittest.TestCase):
    def test_a_control_character_inside_an_echoed_key_never_prints_the_key(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("voiceover_mod", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._KEY = KEY
        for ch in ("\x00", "\n", "\x1b", "\u2028", "\x85", "\x7f"):
            for pos in range(len(KEY) + 1):
                echoed = "bad key " + KEY[:pos] + ch + KEY[pos:] + " rejected"
                out = m.scrub(echoed)
                self.assertNotIn(KEY, out)
                self.assertNotIn(KEY, m._CONTROL.sub("", out))
                self.assertNotIn("\n", out)
        self.assertEqual(m.scrub("fine text"), "fine text")

    def test_the_key_is_withheld_whatever_separator_a_server_inserts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("voiceover_mod2", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._KEY = KEY
        seps = [" ", "\u00a0", "\u200b", "\u00ad", "\u3000", "\ufeff", "\t", "\u200d", "-", "_", ".", "\x00", "\u2060"]
        for sep in seps:
            for pos in range(len(KEY) + 1):
                out = m.scrub("rejected: " + KEY[:pos] + sep + KEY[pos:])
                self.assertEqual(out, m.WITHHELD, (sep, pos))
            self.assertEqual(m.scrub(sep.join(KEY)), m.WITHHELD, sep)
        self.assertEqual(m.scrub("plain " + KEY), m.WITHHELD)
        self.assertEqual(m.scrub(KEY.upper()), m.WITHHELD)
        self.assertEqual(m.scrub("HTTP 401 for voice abc"), "HTTP 401 for voice abc")


class Refusals(Base):
    def test_no_key_sends_nothing(self):
        r = self.run_vo(key=None)
        self.assertEqual(r.returncode, 3)
        self.assertTrue(self.last(r).startswith("AUDIO_FAILED:"))
        self.assertEqual(Handler.seen, [])

    def test_bad_inputs_are_exit_2_and_send_nothing(self):
        (self.wd / "long.txt").write_text("a" * 10001)
        outside = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        outside.write("hi there")
        outside.close()
        cases = [
            dict(voice="../etc/passwd"), dict(voice="short"), dict(voice="voice id with spaces"),
            dict(extra=["--output-format", "pcm_44100"]), dict(extra=["--model-id", "BAD MODEL"]),
            dict(extra=["--stability", "2"]), dict(extra=["--speed", "9"]), dict(out="work/vo.wav"), dict(out="../vo.mp3"),
            dict(base="https://evil.example.com"), dict(base="http://127.0.0.1:%d@evil.example.com" % self.port),
            dict(base="http://evil@127.0.0.1:%d" % self.port), dict(base="http://localhost@evil.example.com:80"),
            dict(base="http://127.0.0.1:%d/x" % self.port), dict(base="http://127.0.0.1"), dict(base="http://10.0.0.1:80"),
            dict(base="https://api.elevenlabs.io.evil.example.com"),
        ]
        for c in cases:
            r = self.run_vo(*c.get("extra", []), voice=c.get("voice", "voiceId12345"), out=c.get("out", "work/vo.mp3"), base=c.get("base"))
            self.assertEqual(r.returncode, 2, "%s -> %s" % (c, r.stdout))
            self.assertTrue(self.last(r).startswith("AUDIO_FAILED:"))
            self.assertClean(r)
        args = [sys.executable, "-I", str(SCRIPT), "--text-file", "long.txt", "--voice-id", "voiceId12345", "--out", "vo.mp3",
                "--base-url", "http://127.0.0.1:%d" % self.port]
        env = dict(os.environ, ELEVENLABS_API_KEY=KEY)
        self.assertEqual(subprocess.run(args, cwd=self.wd, env=env, capture_output=True, text=True).returncode, 2)
        args[args.index("long.txt")] = outside.name
        self.assertEqual(subprocess.run(args, cwd=self.wd, env=env, capture_output=True, text=True).returncode, 2)
        os.unlink(outside.name)
        self.assertEqual(Handler.seen, [])

    def test_the_key_is_not_an_argument_and_no_key_option_exists(self):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--key", KEY], cwd=self.wd, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        text = SCRIPT.read_text()
        self.assertNotIn('"--key"', text)
        self.assertNotIn("api_key", text.lower().replace("elevenlabs_api_key", ""))
if __name__ == "__main__":
    unittest.main()
