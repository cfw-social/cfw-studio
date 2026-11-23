"""Tests for scripts/transcribe.py. They use a small fake tool: no speech model, no network
beyond a local fake server, no paid account. Run: python3 -m unittest discover -s test -v"""
import hashlib
import http.server
import importlib.util
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "transcribe.py"

FAKE_TOOL = '''#!{py}
import json, sys
a = sys.argv[1:]
if "-m" not in a or "-f" not in a or "-ojf" not in a:
    sys.exit(9)
import os
if os.environ.get("FAKE_ARGS"):
    json.dump(a, open(os.environ["FAKE_ARGS"], "w"))
if {fail}:
    sys.stderr.write("boom\\n"); sys.exit(4)
prefix = a[a.index("-of") + 1]
def tok(t, f, to):
    return {{"text": t, "offsets": {{"from": f, "to": to}}}}
seg = {{"tokens": [tok("[_BEG_]", 0, 0), tok(" Hello", 200, 600), tok(" wor", 700, 800),
        tok("ld", 800, 1000), tok(".", 1000, 1100), tok(" [MUSIC]", 1200, 1300), tok(" again", 1500, 1900)]}}
json.dump({{"transcription": [seg]}}, open(prefix + ".json", "w"))
'''


def make_wav(path, seconds=3.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        n = int(16000 * seconds)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20.0))) for i in range(n)))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        make_wav(self.work / "in.wav")
        (self.work / "model.bin").write_bytes(b"fake model bytes")
        self.tool = self.make_tool("fake-whisper", fail=False)

    def make_tool(self, name, fail):
        p = self.work / name
        p.write_text(FAKE_TOOL.format(py=sys.executable, fail="True" if fail else "False"))
        p.chmod(0o755)
        return p

    def run_cli(self, *extra, env_path=None, env_extra=None):
        args = [sys.executable, str(SCRIPT)] + list(extra)
        env = dict(os.environ)
        if env_path is not None:
            env["PATH"] = env_path
        env.update(env_extra or {})
        return subprocess.run(args, cwd=self.work, capture_output=True, text=True, env=env)

    def common(self, *more):
        return ["in.wav", "--out", "words.json", "--tool", "whisper-cpp", "--tool-version", "9.9.9-fake",
                "--tool-bin", str(self.tool), "--model", "model.bin", *more]


class Output(Base):
    def test_word_format_and_order(self):
        r = self.run_cli(*self.common())
        self.assertEqual(r.returncode, 0, r.stderr)
        words = json.loads((self.work / "words.json").read_text())
        self.assertEqual([w["text"] for w in words], ["Hello", "world.", "again"])
        for w in words:
            self.assertEqual(sorted(w), ["end", "start", "text"])
            self.assertIsInstance(w["start"], float)
            self.assertLessEqual(w["start"], w["end"])
        self.assertEqual(words[0]["start"], 0.2)
        starts = [w["start"] for w in words]
        self.assertEqual(starts, sorted(starts))
        for a, b in zip(words, words[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-9)
        self.assertLessEqual(words[-1]["end"], 3.0)

    def test_meta_records_tool_version_and_model_checksum(self):
        self.run_cli(*self.common())
        meta = json.loads((self.work / "words.meta.json").read_text())
        self.assertEqual(meta["tool"], "whisper-cpp")
        self.assertEqual(meta["tool_version"], "9.9.9-fake")
        self.assertEqual(meta["model_sha256"], hashlib.sha256(b"fake model bytes").hexdigest())
        self.assertFalse(meta["model_downloaded"])
        self.assertEqual(meta["input"], "in.wav")
        self.assertNotIn(str(self.work), meta["input"])
        self.assertEqual(meta["tool_bin_as_given"], str(self.tool))
        self.assertEqual(meta["tool_sha256"], hashlib.sha256(self.tool.read_bytes()).hexdigest())
        self.assertIsNone(meta["ffmpeg_version"])  # a 16 kHz mono WAV needs no ffmpeg

    def test_no_temp_files_left(self):
        self.run_cli(*self.common())
        left = sorted(p.name for p in self.work.iterdir() if p.name.startswith(".b-audio") or p.name.endswith(".tmp"))
        self.assertEqual(left, [])

    def test_tool_failure_exits_1(self):
        self.tool = self.make_tool("bad-whisper", fail=True)
        r = self.run_cli(*self.common())
        self.assertEqual(r.returncode, 1)
        self.assertIn("boom", r.stderr)
        self.assertFalse((self.work / "words.json").exists())


class Hint(Base):
    def test_hint_reaches_the_tool_as_one_argument_and_meta_records_it(self):
        text = 'Acme "Widget" $(touch pwned); `x`\nsecond line'
        (self.work / "hint.txt").write_text(text, encoding="utf-8")
        r = self.run_cli(*self.common("--hint-file", "hint.txt"), env_extra={"FAKE_ARGS": str(self.work / "args.json")})
        self.assertEqual(r.returncode, 0, r.stderr)
        args = json.loads((self.work / "args.json").read_text())
        self.assertEqual(args[args.index("--prompt") + 1], text)
        self.assertEqual(args.count(text), 1)
        self.assertEqual([p.name for p in self.work.glob("pwned*")], [])
        meta = json.loads((self.work / "words.meta.json").read_text())
        self.assertTrue(meta["hint_used"])
        self.assertEqual(meta["hint_chars"], len(text))
        self.assertEqual(meta["hint_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertNotIn("second line", json.dumps(meta))

    def test_no_hint_means_no_prompt_option(self):
        r = self.run_cli(*self.common(), env_extra={"FAKE_ARGS": str(self.work / "args.json")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("--prompt", json.loads((self.work / "args.json").read_text()))
        meta = json.loads((self.work / "words.meta.json").read_text())
        self.assertFalse(meta["hint_used"])
        self.assertIsNone(meta["hint_sha256"])

    def test_hint_outside_work_refused(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "h.txt").write_text("hello")
            self.assertEqual(self.run_cli(*self.common("--hint-file", str(Path(other) / "h.txt"))).returncode, 2)
            (self.work / "link.txt").symlink_to(Path(other) / "h.txt")
            self.assertEqual(self.run_cli(*self.common("--hint-file", "link.txt")).returncode, 2)

    def test_hint_too_long_or_bad_refused(self):
        for content in ("a" * 2001, "bad\x00char", "bell\x07", "  \n"):
            (self.work / "hint.txt").write_text(content)
            r = self.run_cli(*self.common("--hint-file", "hint.txt"))
            self.assertEqual(r.returncode, 2, repr(content))
            self.assertFalse((self.work / "words.json").exists())
        (self.work / "hint.txt").write_text("a" * 2000)
        self.assertEqual(self.run_cli(*self.common("--hint-file", "hint.txt")).returncode, 0)
        (self.work / "hint.txt").write_bytes(b"\xff\xfe bad utf8")
        self.assertEqual(self.run_cli(*self.common("--hint-file", "hint.txt")).returncode, 2)


class Refusals(Base):
    def test_missing_tool_names_what_to_install(self):
        r = self.run_cli("in.wav", "--out", "w.json", "--tool", "whisper-cpp", "--tool-version", "1",
                         "--model", "model.bin", env_path=str(self.work / "empty"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("whisper-cli", r.stderr)
        self.assertIn("whisper.cpp", r.stderr)

    def test_unknown_tool_is_usage_error(self):
        r = self.run_cli("in.wav", "--out", "w.json", "--tool", "other", "--tool-version", "1", "--model", "m.bin")
        self.assertEqual(r.returncode, 2)

    def test_model_outside_allowed_places(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "m.bin").write_bytes(b"x")
            args = self.common()
            args[args.index("--model") + 1] = str(Path(other) / "m.bin")
            r = self.run_cli(*args)
            self.assertEqual(r.returncode, 2)
            self.assertIn("outside", r.stderr)
            r = self.run_cli(*args, "--allow-model-dir", other)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_model_symlink_escape_refused(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "m.bin").write_bytes(b"x")
            (self.work / "link.bin").symlink_to(Path(other) / "m.bin")
            args = self.common()
            args[args.index("--model") + 1] = "link.bin"
            self.assertEqual(self.run_cli(*args).returncode, 2)

    def test_input_and_out_must_be_inside_work(self):
        with tempfile.TemporaryDirectory() as other:
            make_wav(Path(other) / "x.wav", 1)
            args = self.common()
            args[0] = str(Path(other) / "x.wav")
            self.assertEqual(self.run_cli(*args).returncode, 2)
            args = self.common()
            args[args.index("--out") + 1] = str(Path(other) / "w.json")
            self.assertEqual(self.run_cli(*args).returncode, 2)

    def test_missing_model_without_allow_flag_makes_no_download(self):
        args = self.common()
        args[args.index("--model") + 1] = "absent.bin"
        r = self.run_cli(*args, "--model-name", "base.en")
        self.assertEqual(r.returncode, 3)
        self.assertIn("--allow-download", r.stderr)
        self.assertFalse((self.work / "absent.bin").exists())

    def test_checksum_mismatch(self):
        r = self.run_cli(*self.common("--model-sha256", "0" * 64))
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.work / "words.json").exists())

    def test_non_wav_without_ffmpeg_exits_3(self):
        (self.work / "clip.mp4").write_bytes(b"not really video")
        args = self.common()
        args[0] = "clip.mp4"
        r = self.run_cli(*args, env_path=str(self.work / "empty"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("ffmpeg", r.stderr)

    def plant(self, name):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        victim = outside / "victim.txt"
        victim.write_text("original")
        (self.work / name).symlink_to(victim)
        return victim

    def test_planted_temp_links_are_not_written_through(self):
        victims = [self.plant(n) for n in ("words.json.tmp", "words.meta.json.tmp", "words.json.part")]
        r = self.run_cli(*self.common())
        self.assertEqual(r.returncode, 0, r.stderr)
        for v in victims:
            self.assertEqual(v.read_text(), "original")
        self.assertFalse((self.work / "words.json").is_symlink())
        self.assertFalse((self.work / "words.meta.json").is_symlink())

    def test_output_and_meta_that_are_links_are_refused(self):
        for name in ("words.json", "words.meta.json"):
            victim = self.plant(name)
            r = self.run_cli(*self.common())
            self.assertEqual(r.returncode, 2, name)
            self.assertEqual(victim.read_text(), "original")
            (self.work / name).unlink()

    def test_trailing_newline_arguments_refused_without_traceback(self):
        for extra in (("--language", "en\n"), ("--base-url", "http://127.0.0.1\n"), ("--model-sha256", "a" * 64 + "\n")):
            r = self.run_cli(*self.common(*extra))
            self.assertEqual(r.returncode, 2, extra)
            self.assertNotIn("Traceback", r.stderr)

    def test_lookalike_base_urls_refused(self):
        for url in ("http://127.0.0.1:1.evil.example", "http://127.0.0.1@evil.example",
                    "http://localhost.evil.example", "http://127.0.0.1.evil.example", "http://127.0.0.1/x?y=1"):
            r = self.run_cli(*self.common("--base-url", url))
            self.assertEqual(r.returncode, 2, url)

    def test_redirect_host_check_is_exact(self):
        spec = importlib.util.spec_from_file_location("transcribe_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = "http://127.0.0.1:5000"
        self.assertTrue(mod.host_allowed("http://127.0.0.1:5000/a", base))
        for bad in ("http://127.0.0.1:5000.evil.example/a", "http://127.0.0.1:5001/a",
                    "http://127.0.0.1:5000@evil.example/a", "https://127.0.0.1:5000/a"):
            self.assertFalse(mod.host_allowed(bad, base), bad)
        self.assertTrue(mod.host_allowed("https://cdn-lfs.hf.co/x", None))
        self.assertFalse(mod.host_allowed("https://hf.co.evil.example/x", None))
        self.assertFalse(mod.host_allowed("https://user@huggingface.co/x", None))
        self.assertFalse(mod.host_allowed("http://huggingface.co/x", None))

    def test_ffmpeg_gets_protocol_whitelist_and_version_is_recorded(self):
        bindir = self.work / "bin"
        bindir.mkdir()
        fake = bindir / "ffmpeg"
        fake.write_text("#!%s\nimport os, shutil, sys\nif '-version' in sys.argv:\n    print('ffmpeg version 0.0-fake'); sys.exit(0)\n"
                        "open(os.environ['FAKE_LOG'], 'w').write(' '.join(sys.argv[1:]))\nshutil.copy(os.environ['FAKE_WAV'], sys.argv[-1])\n"
                        % sys.executable)
        fake.chmod(0o755)
        (self.work / "clip.mp4").write_bytes(b"not really video")
        args = self.common()
        args[0] = "clip.mp4"
        r = self.run_cli(*args, env_path=str(bindir), env_extra={"FAKE_LOG": str(self.work / "ffargs.txt"),
                                                                 "FAKE_WAV": str(self.work / "in.wav")})
        self.assertEqual(r.returncode, 0, r.stderr)
        ffargs = (self.work / "ffargs.txt").read_text()
        self.assertIn("-protocol_whitelist file -i", ffargs)
        meta = json.loads((self.work / "words.meta.json").read_text())
        self.assertEqual(meta["ffmpeg_version"], "ffmpeg version 0.0-fake")

    def test_base_url_must_be_local(self):
        args = self.common("--base-url", "https://example.com")
        self.assertEqual(self.run_cli(*args).returncode, 2)


class Handler(http.server.BaseHTTPRequestHandler):
    body = b"downloaded model"
    hits = []

    slow = False
    stall = False

    def do_GET(self):
        Handler.hits.append(self.path)
        if Handler.stall:
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.flush()
            time.sleep(20)
            return
        if Handler.slow:
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
        self.send_header("Content-Length", str(len(Handler.body)))
        self.end_headers()
        self.wfile.write(Handler.body)

    def log_message(self, *a):
        pass


class Download(Base):
    def setUp(self):
        super().setUp()
        Handler.hits = []
        Handler.body = b"downloaded model"
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port

    def args(self):
        a = self.common()
        a[a.index("--model") + 1] = "models/new.bin"
        return a

    GOOD = hashlib.sha256(b"downloaded model").hexdigest()

    def dl(self, *more, sha=None):
        return self.run_cli(*self.args(), "--allow-download", "--model-name", "base.en", "--base-url", self.base,
                            "--model-sha256", sha or self.GOOD, *more)

    def test_download_only_with_flag(self):
        r = self.run_cli(*self.args(), "--model-name", "base.en", "--base-url", self.base)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(Handler.hits, [])

    def test_download_allowed(self):
        r = self.dl()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Handler.hits, ["/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"])
        meta = json.loads((self.work / "words.meta.json").read_text())
        self.assertTrue(meta["model_downloaded"])
        self.assertEqual(meta["model_sha256"], hashlib.sha256(b"downloaded model").hexdigest())

    def test_download_size_cap(self):
        r = self.dl("--max-model-bytes", "5")
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.work / "models" / "new.bin").exists())
        self.assertEqual(list((self.work / "models").glob("*.part")), [])

    def test_bad_model_name(self):
        for name in ("../x", "base.en\n"):
            r = self.run_cli(*self.args(), "--allow-download", "--model-name", name, "--base-url", self.base,
                             "--model-sha256", self.GOOD)
            self.assertEqual(r.returncode, 2, name)
            self.assertNotIn("Traceback", r.stderr)

    def test_download_needs_a_checksum(self):
        r = self.run_cli(*self.args(), "--allow-download", "--model-name", "base.en", "--base-url", self.base)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--model-sha256", r.stderr)
        self.assertEqual(Handler.hits, [])

    def test_checksum_mismatch_leaves_no_model_and_rerun_does_not_use_it(self):
        r = self.dl(sha="0" * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn("deleted", r.stderr)
        self.assertFalse((self.work / "models" / "new.bin").exists())
        self.assertEqual(list((self.work / "models").iterdir()), [])
        r = self.run_cli(*self.args())  # rerun without download flag and checksum
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.work / "words.json").exists())

    def test_download_outside_work_is_refused_even_in_an_allowed_dir(self):
        with tempfile.TemporaryDirectory() as other:
            a = self.args()
            a[a.index("--model") + 1] = str(Path(other) / "new.bin")
            r = self.run_cli(*a, "--allow-model-dir", other, "--allow-download", "--model-name", "base.en",
                             "--base-url", self.base, "--model-sha256", self.GOOD)
            self.assertEqual(r.returncode, 2)
            self.assertIn("work folder", r.stderr)
            self.assertEqual(list(Path(other).iterdir()), [])
            self.assertEqual(Handler.hits, [])

    def test_planted_model_part_link_is_not_written_through(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        victim = outside / "victim.txt"
        victim.write_text("original")
        (self.work / "models").mkdir()
        (self.work / "models" / "new.bin.part").symlink_to(victim)
        r = self.dl()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(victim.read_text(), "original")

    def test_stalled_server_cannot_hold_the_download_past_the_deadline(self):
        Handler.stall = True
        self.addCleanup(setattr, Handler, "stall", False)
        t = time.monotonic()
        r = self.dl("--download-timeout", "2")
        elapsed = time.monotonic() - t
        self.assertEqual(r.returncode, 1)
        self.assertIn("took longer", r.stderr)
        self.assertLess(elapsed, 8, elapsed)
        self.assertEqual(list((self.work / "models").iterdir()), [])

    def test_slow_download_hits_the_deadline(self):
        Handler.slow = True
        self.addCleanup(setattr, Handler, "slow", False)
        t = time.monotonic()
        r = self.dl("--download-timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("took longer", r.stderr)
        self.assertLess(time.monotonic() - t, 8)
        self.assertFalse((self.work / "models" / "new.bin").exists())
        self.assertEqual(list((self.work / "models").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
