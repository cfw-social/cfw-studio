#!/usr/bin/env python3
"""Step 00 (generate the avatar video) through its own commands, against a small local fake server.

  python3 -I recipes/r-reels-pip-heygen/test/test_generate_step.py -v

No real account, no real key, no network beyond 127.0.0.1. The test takes the bash blocks of
steps/00-generate-avatar.md as they are written and changes one thing: it adds the block's test-only
--base-url option and a short poll time to the render command, so the call reaches the fake server.
Needs ffmpeg (a small video is generated and served as the "render").
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
BLOCKS = os.path.join(os.path.dirname(os.path.dirname(RECIPE)), "blocks")
STEP = os.path.join(RECIPE, "steps", "00-generate-avatar.md")
KEY = "test-key-0123456789abcdef"
FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
WORDS = ("Most people waste hours every week on slides. Here is the trick I use instead. Start with one clear idea, "
         "then say it out loud in plain words. Record it once, and let the tool do the rest. The result is a short reel "
         "that your audience actually finishes. Try it today, and tell me how it goes.")


class Fake(http.server.BaseHTTPRequestHandler):
    video = b""
    log = []
    bodies = []

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        Fake.log.append(("POST", self.path, self.headers.get("x-api-key")))
        Fake.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self._json(200, {"data": {"video_id": "vid_123", "status": "waiting"}})

    def do_GET(self):
        Fake.log.append(("GET", self.path, self.headers.get("x-api-key")))
        if self.path == "/v3/videos/vid_123":
            return self._json(200, {"data": {"id": "vid_123", "status": "completed",
                                             "video_url": "http://127.0.0.1:%d/files/out.mp4" % self.server.server_port}})
        if self.path == "/files/out.mp4":
            self.send_response(200)
            self.send_header("Content-Length", str(len(Fake.video)))
            self.end_headers()
            self.wfile.write(Fake.video)
            return
        self._json(404, {})

    def log_message(self, *a):
        pass


def blocks_of_step():
    with open(STEP, encoding="utf-8") as fh:
        text = fh.read()
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def make_video(path, seconds, audio=True):
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x0F172A:s=180x320:r=10:d=%s" % seconds]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=300:duration=%s" % seconds, "-c:a", "aac"]
    subprocess.run(args + ["-pix_fmt", "yuv420p", path], check=True)


@unittest.skipUnless(FFMPEG, "needs ffmpeg")
class GenerateStepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.mkdtemp(prefix="pip-hg-media-")
        make_video(os.path.join(cls.media, "ok.mp4"), 22)
        make_video(os.path.join(cls.media, "short.mp4"), 8)
        make_video(os.path.join(cls.media, "mute.mp4"), 22, audio=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media, ignore_errors=True)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pip-hg-")
        Fake.log, Fake.bodies = [], []
        self.serve("ok.mp4")
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_port
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(shutil.rmtree, self.root, True)

    def serve(self, name):
        with open(os.path.join(self.media, name), "rb") as fh:
            Fake.video = fh.read()

    def workdir(self, script=WORDS, avatar="avatar_PLACEHOLDER", voice="voice_PLACEHOLDER", brand=None):
        wd = tempfile.mkdtemp(dir=self.root)
        for sub in ("inputs/script", "inputs/avatar_id", "inputs/voice_id", "work", "saves"):
            os.makedirs(os.path.join(wd, sub))
        with open(os.path.join(wd, "brief.json"), "w") as fh:
            json.dump({"recipe": "r-reels-pip-heygen", "brand": brand if brand is not None else {"name": "Test", "palette": {"bg": "#112233"}}}, fh)
        for name, value in (("script", script), ("avatar_id", avatar), ("voice_id", voice)):
            if value is not None:
                with open(os.path.join(wd, "inputs", name, name + ".txt"), "w") as fh:
                    fh.write(value)
            else:
                os.rmdir(os.path.join(wd, "inputs", name))
        return wd

    def run_step(self, wd, key=KEY):
        code = "\n".join(blocks_of_step())
        code = code.replace('render.py" --script', 'render.py" --base-url "$HEYGEN_TEST_BASE" --poll-seconds 0.05 --script')
        self.assertIn("HEYGEN_TEST_BASE", code)
        env = {k: v for k, v in os.environ.items() if k not in ("HEYGEN_API_KEY", "BRAND_KEY")}
        env.update({"RECIPE_DIR": RECIPE, "HEYGEN_TEST_BASE": self.base})
        # the step reads the key with `read -rs` from standard input, as a person or a secret tool would give it
        return subprocess.run(["bash", "-c", code], cwd=wd, env=env, capture_output=True, text=True,
                              input=(key + "\n") if key else "")

    def assert_key_nowhere(self, wd, result):
        self.assertNotIn(KEY, result.stdout)
        self.assertNotIn(KEY, result.stderr)
        for dirpath, _, files in os.walk(wd):
            for f in files:
                with open(os.path.join(dirpath, f), "rb") as fh:
                    self.assertNotIn(KEY.encode(), fh.read(), os.path.join(dirpath, f))

    def test_a_good_run_saves_the_video_and_the_record(self):
        wd = self.workdir()
        r = self.run_step(wd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("avatar render OK", r.stdout)
        for name in ("saves/talking_head.mp4", "saves/avatar_render.json", "work/narration.txt"):
            self.assertTrue(os.path.getsize(os.path.join(wd, name)) > 0, name)
        with open(os.path.join(wd, "saves", "avatar_render.json")) as fh:
            self.assertEqual(json.load(fh)["video_id"], "vid_123")
        post = Fake.bodies[0]
        self.assertEqual((post["type"], post["avatar_id"], post["voice_id"]), ("avatar", "avatar_PLACEHOLDER", "voice_PLACEHOLDER"))
        self.assertEqual((post["aspect_ratio"], post["resolution"]), ("9:16", "720p"))
        self.assertEqual(post["background"], {"type": "color", "value": "#112233"})   # the brand's colour, not the block's green
        self.assertEqual(post["script"], WORDS)
        self.assertEqual(Fake.log[0][:2], ("POST", "/v3/videos"))
        self.assertEqual(len([e for e in Fake.log if e[0] == "POST"]), 1)
        self.assertTrue(all(k == KEY for m, p, k in Fake.log if p != "/files/out.mp4"))
        self.assertIsNone([k for m, p, k in Fake.log if p == "/files/out.mp4"][0])   # no key to the file host
        self.assert_key_nowhere(wd, r)

    def test_a_rerun_with_the_record_resumes_and_does_not_submit_again(self):
        first = self.workdir()
        self.assertEqual(self.run_step(first).returncode, 0)
        second = self.workdir()
        shutil.copy(os.path.join(first, "saves", "avatar_render.json"), os.path.join(second, "saves", "avatar_render.json"))
        r = self.run_step(second)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len([e for e in Fake.log if e[0] == "POST"]), 1, "a second render was submitted")
        self.assertTrue(os.path.isfile(os.path.join(second, "saves", "talking_head.mp4")))

    def test_no_key_sends_nothing(self):
        wd = self.workdir()
        r = self.run_step(wd, key=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("HeyGen is not connected", r.stderr + r.stdout)
        self.assertEqual(Fake.log, [])
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "talking_head.mp4")))

    def test_missing_or_bad_inputs_ask_and_send_nothing(self):
        cases = (({"script": ""}, "script"), ({"script": "too short to be a reel"}, "script"), ({"avatar": None}, "avatar_id"),
                 ({"voice": None}, "voice_id"), ({"avatar": "a;touch pwned"}, "avatar_id"), ({"voice": "-x"[:0] + "v" * 129}, "voice_id"),
                 ({"avatar": "$(touch pwned)"}, "avatar_id"))
        for kw, asked in cases:
            wd = self.workdir(brand={}, **kw)
            r = self.run_step(wd)
            self.assertEqual(r.returncode, 0, (kw, r.stdout + r.stderr))
            with open(os.path.join(wd, "needs_input.json")) as fh:
                self.assertEqual(json.load(fh)["inputId"], asked, kw)
            self.assertEqual(Fake.log, [], kw)
            self.assertFalse(os.path.exists(os.path.join(wd, "pwned")), kw)
            self.assertFalse(os.path.exists(os.path.join(wd, "saves", "talking_head.mp4")), kw)

    def test_brand_ids_are_used_when_the_inputs_are_absent(self):
        wd = self.workdir(avatar=None, voice=None, brand={"heygen": {"avatarId": "brand_av", "voiceId": "brand_vo"}})
        r = self.run_step(wd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((Fake.bodies[0]["avatar_id"], Fake.bodies[0]["voice_id"]), ("brand_av", "brand_vo"))
        self.assertEqual(Fake.bodies[0]["background"]["value"], "#0F172A")             # the default when the brand has none

    def test_a_render_of_the_wrong_length_or_without_audio_fails_but_keeps_the_record(self):
        for name, why in (("short.mp4", "20 to 60"), ("mute.mp4", "no picture or no audio")):
            self.serve(name)
            wd = self.workdir()
            r = self.run_step(wd)
            self.assertNotEqual(r.returncode, 0, name)                       # a failure, never an ask
            self.assertIn(why, r.stdout + r.stderr, name)
            self.assertFalse(os.path.exists(os.path.join(wd, "needs_input.json")), name)
            self.assertFalse(os.path.exists(os.path.join(wd, "saves", "talking_head.mp4")), name)
            with open(os.path.join(wd, "saves", "avatar_render.json")) as fh:    # saved BEFORE the check
                self.assertEqual(json.load(fh)["video_id"], "vid_123", name)
            before = len([e for e in Fake.log if e[0] == "POST"])
            self.serve("ok.mp4")                                             # the rerun resumes, and is not charged again
            again = self.workdir()
            shutil.copy(os.path.join(wd, "saves", "avatar_render.json"), os.path.join(again, "saves", "avatar_render.json"))
            self.assertEqual(self.run_step(again).returncode, 0)
            self.assertEqual(len([e for e in Fake.log if e[0] == "POST"]), before, name)

    def test_the_provider_block_is_the_one_in_this_repository(self):
        self.assertTrue(os.path.isfile(os.path.join(BLOCKS, "b-heygen", "scripts", "render.py")))
        with open(STEP, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("HEYGEN_API_KEY=" + KEY, text)
        self.assertNotRegex(text, r"--(api-)?key[ =]")        # the key is never a command-line option
        self.assertNotRegex(text, r"(?m)^\s*export\s+\w*KEY")  # and never exported
        self.assertNotRegex(text, r"(?i)cheap|cheaper|price|per minute|credits? cost")   # no cost or price claim
        self.assertIn("read -rs BRAND_KEY", text)
        self.assertIn("not exported", text)
        self.assertIn("never written to a file", text)


class InputsScriptTest(unittest.TestCase):
    def setUp(self):
        self.wd = tempfile.mkdtemp(prefix="pip-hg-in-")
        self.addCleanup(shutil.rmtree, self.wd, True)

    def run_script(self, *args):
        return subprocess.run([sys.executable, os.path.join(RECIPE, "scripts", "heygen_inputs.py")] + list(args),
                              cwd=self.wd, capture_output=True, text=True)

    def test_json_script_and_get(self):
        for sub in ("inputs/script", "inputs/avatar_id", "inputs/voice_id"):
            os.makedirs(os.path.join(self.wd, sub))
        with open(os.path.join(self.wd, "inputs", "script", "script.json"), "w") as fh:
            json.dump({"text": WORDS}, fh)
        for n in ("avatar_id", "voice_id"):
            with open(os.path.join(self.wd, "inputs", n, n + ".json"), "w") as fh:
                json.dump({"text": n + "_1"}, fh)
        with open(os.path.join(self.wd, "brief.json"), "w") as fh:
            json.dump({"brand": {"palette": {"bg": "not a colour"}}}, fh)
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.run_script("--get", "avatar_id").stdout.strip(), "avatar_id_1")
        self.assertEqual(self.run_script("--get", "background").stdout.strip(), "#0F172A")
        self.assertEqual(self.run_script("--get", "nothing").returncode, 1)
        with open(os.path.join(self.wd, "work", "narration.txt")) as fh:
            self.assertEqual(fh.read(), WORDS + "\n")

    def test_no_brief_is_a_plain_failure(self):
        p = self.run_script()
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAILED", p.stderr)


if __name__ == "__main__":
    unittest.main()
