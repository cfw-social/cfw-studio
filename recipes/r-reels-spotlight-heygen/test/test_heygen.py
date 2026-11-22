#!/usr/bin/env python3
"""Step 00 through its own command line, against a small local fake server. No HeyGen account, no real key.

  python3 -I recipes/r-reels-spotlight-heygen/test/test_heygen.py -v

The command the tests run is the one printed in steps/00-generate-avatar.md (read from the file), with two
test-only options added (the fake server's address and a short poll). The fake server answers the shapes
`blocks/b-heygen/README.md` describes and serves a small generated portrait video. The key is checked to
appear in no output and in no file. Needs ffmpeg and the b-heygen block beside the recipe.
"""
import http.server
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, FFMPEG, NEEDS_FFMPEG, RECIPE_DIR, Tmp, load_json, py, read, write_json, write_text

KEY = "test-key-0123456789abcdef"
RENDER = os.path.join(BLOCKS, "b-heygen", "scripts", "render.py")
AVATAR = "avatar_PLACEHOLDER"
VOICE = "voice_PLACEHOLDER"
SCRIPT = " ".join(["This is one sentence of the narration for the reel."] * 8) + "\n"   # 88 words
STEP = "steps/00-generate-avatar.md"
STATE = {"video": b"", "mode": "success", "log": [], "bodies": []}


class Fake(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        STATE["log"].append(("POST", self.path, self.headers.get("x-api-key")))
        STATE["bodies"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self._json(200, {"data": {"video_id": "vid_123", "status": "waiting"}})

    def do_GET(self):
        STATE["log"].append(("GET", self.path, self.headers.get("x-api-key")))
        if self.path == "/v3/videos/vid_123":
            if STATE["mode"] == "failed":
                return self._json(200, {"data": {"status": "failed", "failure_code": "x", "failure_message": "no credits for key %s" % self.headers.get("x-api-key")}})
            url = "http://127.0.0.1:%d/files/out.mp4" % self.server.server_port
            return self._json(200, {"data": {"status": "completed", "video_url": url}})
        if self.path == "/files/out.mp4":
            body = STATE["video"]
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {})

    def log_message(self, *a):
        pass


def make_avatar(path, seconds=22, size="1080x1920", audio=True):
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x0F172A:s=%s:r=30:d=%s" % (size, seconds)]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=f=220:d=%s" % seconds, "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True)


def step_command(base, text=None):
    """The render.py argument list printed in step 00, with the variables filled in and test options added."""
    text = text if text is not None else read(STEP)
    line = re.search(r"(?m)^HEYGEN_API_KEY=\"\$\{BRAND_KEY:\?missing\}\" python3 \"\$BLOCKS_DIR/b-heygen/scripts/render\.py\" (.*)$", text).group(1)
    args = shlex.split(line)
    sub = {"$SCRIPT_FILE": "inputs/script/script.txt", "$AVATAR_ID": AVATAR, "$VOICE_ID": VOICE}
    return [sys.executable, RENDER] + [sub.get(a, a) for a in args] + ["--base-url", base, "--poll-seconds", "0.05"]


def section_two_block(base):
    """The bash block of section 2 of step 00, with the two test-only options added to the render command."""
    text = read(STEP)
    block = [b for b in re.findall(r"```bash\n(.*?)```", text, re.S) if "render.py" in b and "BRAND_KEY" in b and "avatar_render.json" in b][0]
    return block.replace('--background "#0F172A"', '--background "#0F172A" --base-url %s --poll-seconds 0.05' % base)


class StepZeroTest(Tmp):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        STATE.update(mode="success", log=[], bodies=[])
        self.wd = self.path("wd")
        write_text(os.path.join(self.wd, "inputs", "script", "script.txt"), SCRIPT)
        write_text(os.path.join(self.wd, "inputs", "avatar_id", "avatar_id.txt"), AVATAR + "\n")
        write_text(os.path.join(self.wd, "inputs", "voice_id", "voice_id.txt"), VOICE + "\n")
        write_json(os.path.join(self.wd, "brief.json"), {"brand": {"name": "Sample Co"}})
        avatar = self.path("fake-avatar.mp4")
        make_avatar(avatar)
        with open(avatar, "rb") as fh:
            STATE["video"] = fh.read()

    def render(self, key=KEY, stdin=None, extra=()):
        env = {k: v for k, v in os.environ.items() if k != "HEYGEN_API_KEY"}
        cmd = step_command(self.base) + list(extra)
        if stdin is None and key:
            env["HEYGEN_API_KEY"] = key
        return subprocess.run(cmd, cwd=self.wd, capture_output=True, text=True, env=env, input=stdin)

    def no_key_anywhere(self, r):
        self.assertNotIn(KEY, r.stdout)
        self.assertNotIn(KEY, r.stderr)
        for root, _, names in os.walk(self.wd):
            for n in names:
                with open(os.path.join(root, n), "rb") as fh:
                    self.assertNotIn(KEY.encode(), fh.read(), n)

    @NEEDS_FFMPEG
    def test_the_whole_step_from_inputs_to_saved_video(self):
        r = py("heygen_inputs.py", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [AVATAR, VOICE, "inputs/script/script.txt"])
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("VIDEO_FILE: work/avatar.mp4", r.stdout)
        post = STATE["bodies"][0]
        self.assertEqual((post["avatar_id"], post["voice_id"], post["script"]), (AVATAR, VOICE, SCRIPT.strip()))
        self.assertEqual((post["aspect_ratio"], post["resolution"]), ("9:16", "1080p"))
        self.assertEqual(post["background"], {"type": "color", "value": "#0F172A"})
        self.assertEqual(STATE["log"][0][:2], ("POST", "/v3/videos"))
        self.assertTrue(all(k == KEY for m, p, k in STATE["log"] if p != "/files/out.mp4"))
        self.no_key_anywhere(r)
        c = py("check_avatar.py", "work/avatar.mp4", cwd=self.wd)
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertEqual(c.stdout.strip(), "avatar 1080x1920 22.0s")

    def test_a_rerun_resumes_and_never_pays_twice(self):
        self.assertEqual(self.render().returncode, 0)
        record = os.path.join(self.wd, "work", "avatar.mp4.render.json")
        self.assertTrue(os.path.isfile(record))
        self.assertNotIn(KEY, load_json(record).__str__())
        self.assertEqual(self.render().returncode, 0)
        self.assertEqual(sum(1 for m, p, k in STATE["log"] if m == "POST"), 1, "a second submit would be a second charge")

    def test_a_failed_render_is_reported_and_not_resubmitted(self):
        STATE["mode"] = "failed"
        r = self.render()
        self.assertEqual(r.returncode, 1)
        self.no_key_anywhere(r)
        r = self.render()
        self.assertEqual(sum(1 for m, p, k in STATE["log"] if m == "POST"), 1)

    def test_no_key_sends_nothing(self):
        r = self.render(key=None)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(STATE["log"], [])

    def test_the_key_can_come_on_standard_input(self):
        r = self.render(stdin=KEY + "\n", extra=("--key-stdin",))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(STATE["log"][0][2], KEY)
        self.no_key_anywhere(r)

    def test_the_command_in_the_step_has_no_key_option_and_no_id(self):
        text = read(STEP)
        cmd = re.search(r"(?m)^HEYGEN_API_KEY=.* python3 .*$", text).group(0)
        self.assertIn('HEYGEN_API_KEY="${BRAND_KEY:?missing}"', cmd)
        self.assertNotRegex(cmd, r"--(?:api-)?key\b(?!-stdin)")
        self.assertNotRegex(cmd, r"avatar[_-]?[0-9a-f]{8,}")
        self.assertIn("--aspect-ratio 9:16", cmd)
        self.assertIn("--resolution 1080p", cmd)
        self.assertIn('--background "#0F172A"', cmd)


class SectionTwoTest(Tmp):
    """Section 2 of step 00 run as written (under bash), against the fake server."""

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        STATE.update(mode="success", log=[], bodies=[])
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "work"))
        os.makedirs(os.path.join(self.wd, "saves"))
        write_text(os.path.join(self.wd, "inputs", "script", "script.txt"), SCRIPT)
        avatar = self.path("fake-avatar.mp4")
        if FFMPEG:
            make_avatar(avatar)
            with open(avatar, "rb") as fh:
                STATE["video"] = fh.read()
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "BLOCKS_DIR": BLOCKS, "RECIPE_DIR": RECIPE_DIR,
                    "AVATAR_ID": AVATAR, "VOICE_ID": VOICE, "SCRIPT_FILE": "inputs/script/script.txt"}

    def run_block(self, key=KEY):
        r = subprocess.run(["bash", "-c", section_two_block(self.base)], cwd=self.wd, capture_output=True, text=True, env=self.env,
                           input=(key + "\n") if key is not None else "")
        return r

    def test_the_key_is_read_without_echo_and_never_exported(self):
        r = self.run_block()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(STATE["log"][0][2], KEY)
        self.assertNotIn(KEY, r.stdout + r.stderr)
        block = section_two_block("http://x")
        self.assertIn("IFS= read -rs BRAND_KEY", block)
        self.assertIn("unset BRAND_KEY", block)
        self.assertNotRegex(block, r"export\s+(BRAND_KEY|HEYGEN_API_KEY)")
        self.assertNotRegex(block, r"set -x|set -o xtrace")

    def test_the_record_is_saved_after_the_render_and_restored_before_a_rerun(self):
        self.assertEqual(self.run_block().returncode, 0)
        record = os.path.join(self.wd, "saves", "avatar_render.json")
        self.assertTrue(os.path.isfile(record))
        # the runner discards work/ between steps: the rerun must resume from saves/, not pay again
        shutil.rmtree(os.path.join(self.wd, "work"))
        os.makedirs(os.path.join(self.wd, "work"))
        self.assertEqual(self.run_block().returncode, 0)
        self.assertEqual(sum(1 for m, p, k in STATE["log"] if m == "POST"), 1, "a second submit would be a second charge")

    def test_the_record_is_saved_even_when_the_render_fails(self):
        STATE["mode"] = "failed"
        r = self.run_block()
        self.assertEqual(r.returncode, 1)
        self.assertTrue(os.path.isfile(os.path.join(self.wd, "saves", "avatar_render.json")))
        self.assertNotIn(KEY, r.stdout + r.stderr)
        shutil.rmtree(os.path.join(self.wd, "work"))
        os.makedirs(os.path.join(self.wd, "work"))
        self.run_block()
        self.assertEqual(sum(1 for m, p, k in STATE["log"] if m == "POST"), 1)

    def test_no_key_stops_the_block_and_sends_nothing(self):
        r = self.run_block(key="")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(STATE["log"], [])


class InputsTest(Tmp):
    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        write_text(os.path.join(self.wd, "inputs", "script", "script.txt"), SCRIPT)
        write_text(os.path.join(self.wd, "inputs", "avatar_id", "avatar_id.txt"), AVATAR)
        write_text(os.path.join(self.wd, "inputs", "voice_id", "voice_id.txt"), VOICE)

    def run_it(self):
        return py("heygen_inputs.py", cwd=self.wd)

    def test_ids_can_come_from_the_brief(self):
        self.reset()
        os.remove(os.path.join(self.wd, "inputs", "avatar_id", "avatar_id.txt"))
        os.remove(os.path.join(self.wd, "inputs", "voice_id", "voice_id.txt"))
        write_json(os.path.join(self.wd, "brief.json"), {"brand": {"heygen": {"avatarId": "a-1", "voiceId": "v_2"}}})
        r = self.run_it()
        self.assertEqual(r.stdout.split(), ["a-1", "v_2", "inputs/script/script.txt"])

    def reset(self):
        for rel, body in (("script/script.txt", SCRIPT), ("avatar_id/avatar_id.txt", AVATAR), ("voice_id/voice_id.txt", VOICE)):
            write_text(os.path.join(self.wd, "inputs", rel), body)
        for gone in (os.path.join(self.wd, "inputs", "script", "script.md"), os.path.join(self.wd, "needs_input.json")):
            if os.path.exists(gone):
                os.remove(gone)

    def test_missing_or_bad_inputs_before_the_render_ask_the_person(self):
        wd = self.wd
        cases = {
            "no avatar id": (lambda: os.remove(os.path.join(wd, "inputs", "avatar_id", "avatar_id.txt")), "avatar_id", "avatar id"),
            "no voice id": (lambda: os.remove(os.path.join(wd, "inputs", "voice_id", "voice_id.txt")), "voice_id", "voice id"),
            "bad id": (lambda: write_text(os.path.join(wd, "inputs", "voice_id", "voice_id.txt"), "bad id; rm -rf"), "voice_id", "not valid"),
            "short script": (lambda: write_text(os.path.join(wd, "inputs", "script", "script.txt"), "Too short."), "script", "words"),
            "long script": (lambda: write_text(os.path.join(wd, "inputs", "script", "script.txt"), "word " * 1200), "script", "too long"),
            "no script": (lambda: os.remove(os.path.join(wd, "inputs", "script", "script.txt")), "script", "provide the narration"),
            "two scripts": (lambda: write_text(os.path.join(wd, "inputs", "script", "script.md"), SCRIPT), "script", "just one"),
        }
        for name, (mutate, input_id, needle) in cases.items():
            with self.subTest(name):
                self.reset()
                mutate()
                r = self.run_it()
                self.assertEqual(r.returncode, 1, name)
                self.assertIn(needle, r.stderr)
                self.assertEqual(r.stdout, "")
                ask = load_json(os.path.join(wd, "needs_input.json"))
                self.assertEqual((ask["inputId"], ask["count"]), (input_id, 1))
                self.assertNotRegex(ask["reason"], r"/|\\.py|Traceback")

    def test_the_word_range_is_the_gates_twenty_to_sixty_seconds(self):
        # 150 words a minute: 50 words is 20 s, 150 words is 60 s. Run the real gate's own rule on the same texts.
        gate = os.path.join(BLOCKS, "b-qa-gate", "check.py")
        spec = os.path.join(RECIPE_DIR, "acceptance.json")
        for words, ok in ((49, False), (50, True), (150, True), (151, False)):
            with self.subTest(words):
                self.reset()
                write_text(os.path.join(self.wd, "inputs", "script", "script.txt"), " ".join(["word"] * words))
                self.assertEqual(self.run_it().returncode == 0, ok)
                r = subprocess.run([sys.executable, "-I", gate, "--kind", "reel", "--spec", spec, "--step", "script", "--input",
                                    "inputs/script/script.txt", "--out", "work/g.json"], cwd=self.wd, capture_output=True, text=True,
                                   env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
                self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)

    def test_needs_input_is_never_written_through_a_link(self):
        self.reset()
        os.remove(os.path.join(self.wd, "inputs", "voice_id", "voice_id.txt"))
        victim = self.path("victim.txt")
        write_text(victim, "keep me")
        os.symlink(victim, os.path.join(self.wd, "needs_input.json"))
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("link or a folder", r.stderr)
        with open(victim, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me")
        os.remove(os.path.join(self.wd, "needs_input.json"))
        r = self.run_it()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(load_json(os.path.join(self.wd, "needs_input.json"))["inputId"], "voice_id")
        self.assertEqual([n for n in os.listdir(self.wd) if n.startswith(".needs-")], [], "a temporary file was left behind")

    def test_an_id_file_that_is_not_utf8_is_a_one_line_error(self):
        self.reset()
        with open(os.path.join(self.wd, "inputs", "avatar_id", "avatar_id.txt"), "wb") as fh:
            fh.write(b"\xff\xfe\x00bad")
        r = self.run_it()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertIn("not readable UTF-8", r.stderr)

    def test_the_script_is_never_a_shell_string(self):
        write_text(os.path.join(self.wd, "inputs", "script", "script.txt"), "$(touch PWNED) `touch PWNED2` " + SCRIPT)
        self.assertEqual(self.run_it().returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.wd, "PWNED")))


@NEEDS_FFMPEG
class CheckAvatarTest(Tmp):
    def check(self, **kw):
        make_avatar(self.path("v.mp4"), **kw)
        return py("check_avatar.py", self.path("v.mp4"))

    def test_good_and_bad_videos(self):
        self.assertEqual(self.check().returncode, 0)
        for name, kw, needle in (("landscape", {"size": "1920x1080"}, "portrait"), ("short", {"seconds": 5}, "20 to 60"),
                                 ("long", {"seconds": 70, "size": "270x480"}, "20 to 60"), ("silent", {"audio": False}, "no audio")):
            with self.subTest(name):
                r = self.check(**kw)
                self.assertEqual(r.returncode, 1)
                self.assertIn(needle, r.stderr)
        write_text(self.path("junk.mp4"), "not a video")
        self.assertNotEqual(py("check_avatar.py", self.path("junk.mp4")).returncode, 0)


class PlainFactsTest(unittest.TestCase):
    def test_step_zero_says_the_plain_facts(self):
        text = read("steps/00-generate-avatar.md").lower()
        for needle in ("script text is uploaded", "brand's own", "agreed", "one paid render", "resumes", "not proven with a real account",
                       "never invent or reuse", "9:16", "1080p", "#0f172a"):
            self.assertIn(needle, text)

    def test_the_shared_rules_tell_the_truth_about_the_key_and_the_record(self):
        shared = read("steps/_shared.md")
        self.assertNotIn("uses no provider key", shared)
        self.assertIn("Only step 00 uses a provider key", shared)
        self.assertIn("unexported shell variable", shared)
        self.assertIn("saves/avatar_render.json", shared)
        step = read(STEP)
        for needle in ("unexported", "without echoing", "saves/avatar_render.json", "needs_input.json", "not an ask", "50 to 150"):
            self.assertIn(needle, step)
        self.assertNotIn("40 to 180", step)

    def test_readme_says_them_too(self):
        text = read("README.md").lower()
        for needle in ("uploaded", "agreed", "one paid render", "resumes", "not proven", "api.heygen.com"):
            self.assertIn(needle, text)

    def test_no_avatar_voice_or_person_is_shipped(self):
        for rel in ("steps/00-generate-avatar.md", "README.md", "SKILL.md", "manifest.json"):
            self.assertNotRegex(read(rel), r"(?i)(avatar|voice)[_ -]?id[\"'`:= ]+[0-9a-f]{16,}", rel)


if __name__ == "__main__":
    unittest.main()
