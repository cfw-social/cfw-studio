#!/usr/bin/env python3
"""End-to-end tests of r-inspired-reel through the step files' own bash blocks.

  python3 -I -m unittest discover -s recipes/r-inspired-reel/test -v     (from the repository root)

No account, no real key, no network beyond 127.0.0.1. They run:

  * the bash blocks of the three step files, read from the step files themselves;
  * the REAL blocks/b-audio/scripts/transcribe.py with a small fake speech tool (no model, no speech);
  * the REAL blocks/b-heygen/scripts/render.py against a small fake HeyGen server (a thin wrapper adds the
    local-only --base-url and a short --poll-seconds; nothing else changes);
  * the REAL blocks/b-reel-premium check_plan.py, mux.py and qa.py, and the REAL blocks/b-qa-gate/check.py.

NOT run here: HyperFrames install and render (they need Node and a download), and a real HeyGen account.
The only key used is a made-up string, which must appear in no output file and no output stream.
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

import helpers as H
from helpers import BLOCKS, FFMPEG, KEY, REF_TEXT, RECIPE, STEPS, make_avatar_video, make_cut_video, read, timed, write

BASH = shutil.which("bash")
REAL_RENDER = os.path.join(BLOCKS, "b-heygen", "scripts", "render.py")

FAKE_WHISPER = '''#!{py}
import json, sys
a = sys.argv[1:]
if "-m" not in a or "-f" not in a or "-ojf" not in a:
    sys.exit(9)
prefix = a[a.index("-of") + 1]
def tok(t, f, to):
    return {{"text": t, "offsets": {{"from": f, "to": to}}}}
seg = {{"tokens": [tok("[_BEG_]", 0, 0), tok(" Hello", 200, 600), tok(" wor", 700, 800),
        tok("ld", 800, 1000), tok(".", 1000, 1100), tok(" again", 1500, 1900)]}}
json.dump({{"transcription": [seg]}}, open(prefix + ".json", "w"))
'''


class FakeHeyGen(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, video_path, scenario="ok"):
        super().__init__(("127.0.0.1", 0), Handler)
        self.video = H.read_bytes(video_path)
        self.scenario = scenario
        self.seen = []
        self.bodies = []
        self.url = "http://127.0.0.1:%d" % self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except OSError:
            pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.seen.append(("POST", self.path, self.headers.get("x-api-key")))
        self.server.bodies.append(json.loads(body or b"{}"))
        if self.server.scenario == "echo_key":
            return self._send(401, {"error": {"message": "bad key " + str(self.headers.get("x-api-key"))}})
        self._send(200, {"data": {"video_id": "vid_1", "status": "pending"}})

    def do_GET(self):
        self.server.seen.append(("GET", self.path, self.headers.get("x-api-key")))
        if self.path == "/v3/videos/vid_1":
            if self.server.scenario == "failed":
                return self._send(200, {"data": {"id": "vid_1", "status": "failed", "failure_code": "x",
                                                 "failure_message": "avatar problem, key " + str(self.headers.get("x-api-key"))}})
            url = "http://127.0.0.1:%d/files/out.mp4" % self.server.server_port
            return self._send(200, {"data": {"id": "vid_1", "status": "completed", "video_url": url}})
        if self.path == "/files/out.mp4":
            return self._send(200, self.server.video, "video/mp4")
        self._send(404, {})


def make_alpha_mov(path, seconds):
    """A fully transparent 1080x1920 ProRes 4444 video: a stand-in for the caption render."""
    H.ff("-f", "lavfi", "-i", "color=c=black@0.0:s=1080x1920:d=%s:r=30,format=yuva444p10le" % seconds,
         "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", path)


def bash_block(name, heading, nth=0):
    """The nth ```bash block after `heading` in a step file."""
    text = read(os.path.join(STEPS, name))
    at = text.index(heading)
    return re.findall(r"```bash\n(.*?)\n```", text[at:], re.S)[nth]


S1, S2, S3 = "01-reference-to-script.md", "02-narration.md", "03-captions-and-checks.md"


@unittest.skipUnless(FFMPEG and BASH, "ffmpeg, ffprobe and bash are needed")
class Chain(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="insp-e2e-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.wd = os.path.join(self.root, "wd")
        os.makedirs(self.wd)
        self.outputs = []
        self.fakes = []
        self.shim = os.path.join(self.root, "shim")
        write(os.path.join(self.shim, "b-heygen", "scripts", "render.py"),
              "import os, sys\n"
              "u = os.environ['TEST_FAKE_URL']\n"
              "os.execv(sys.executable, [sys.executable, os.environ['TEST_REAL_RENDER']] + sys.argv[1:]"
              " + ['--base-url', u, '--poll-seconds', '0.05'])\n")
        whisper = os.path.join(self.wd, "fake-whisper")
        write(whisper, FAKE_WHISPER.format(py=sys.executable))
        os.chmod(whisper, 0o755)
        write(os.path.join(self.wd, "model.bin"), "fake model bytes")

    def p(self, *parts):
        return os.path.join(self.wd, *parts)

    def bash(self, code, blocks=BLOCKS, key=None, extra=None, fake=None):
        env = {k: v for k, v in os.environ.items() if k not in ("HEYGEN_API_KEY", "ORDER_KEY", "BG")}
        env.update(RECIPE_DIR=RECIPE, BLOCKS_DIR=blocks, WHISPER_VERSION="9.9.9-fake", WHISPER_MODEL="model.bin",
                   WHISPER_BIN=self.p("fake-whisper"), TEST_REAL_RENDER=REAL_RENDER)
        if fake:
            env["TEST_FAKE_URL"] = fake.url
        if key:
            env["ORDER_KEY"] = key
        env.update(extra or {})
        r = subprocess.run([BASH, "-c", "set -eu\n" + code], cwd=self.wd, env=env, capture_output=True, text=True, timeout=900)
        self.outputs += [r.stdout, r.stderr]
        return r

    def ok(self, code, **kw):
        r = self.bash(code, **kw)
        self.assertEqual(r.returncode, 0, "STDOUT:\n%s\nSTDERR:\n%s" % (r.stdout, r.stderr))
        return r

    def assert_no_key_anywhere(self):
        text = "\n".join(self.outputs)
        for d, _dirs, files in os.walk(self.root):
            for f in files:
                path = os.path.join(d, f)
                if path.startswith(self.shim) or f.endswith((".mp4", ".wav")):
                    continue
                text += H.read_bytes(path).decode("latin-1")
        self.assertNotIn(KEY, text)

    # ---- step 1 -----------------------------------------------------------------------------
    def stage1_inputs(self):
        make_cut_video(self.p("inputs", "reference_reel", "ref.mp4"), shots=(5, 5, 5, 5))
        write(self.p("inputs", "topic", "topic.md"), "Why tomatoes split after rain.\n")

    def run_step1_to_format(self):
        self.stage1_inputs()
        setup = bash_block(S1, "## How")
        self.ok(setup + "\n" + bash_block(S1, "### 1. Take in the reference"))
        self.assertTrue(os.path.exists(self.p("ref", "audio.wav")))
        words = json.loads(read(self.p("ref", "words.json")))
        self.assertEqual([w["text"] for w in words], ["Hello", "world.", "again"])   # the real b-audio ran the fake tool
        self.assertIn("text", json.loads(read(self.p("ref", "words.meta.json"))))
        # the fake tool hears three words; put a made-up transcript in its place for the rest of the chain
        write(self.p("ref", "words.json"), json.dumps(timed(REF_TEXT, gap=0.22, pause=0.3)))
        self.ok(setup + "\n" + bash_block(S1, "### 2. Measure the format"))
        return setup

    def good_script(self):
        fmt = json.loads(read(self.p("saves", "format.json")))
        paras = []
        for i, b in enumerate(fmt["beats"]):
            paras.append(" ".join("tomato%dx%d" % (i, k) for k in range(b["words"])) + ".")
        write(self.p("work", "script.txt"), "\n\n".join(paras))

    def test_step1_format_script_overlap_and_deletion(self):
        setup = self.run_step1_to_format()
        fmt = json.loads(read(self.p("saves", "format.json")))
        self.assertEqual(fmt["duration_s"], 20.0)
        self.assertEqual(fmt["cut_count"], 3)
        self.good_script()
        self.ok(setup + "\n" + bash_block(S1, "### 3. Write the new script"))
        self.assertEqual(json.loads(read(self.p("saves", "overlap.json")))["verdict"], "PASS")
        self.ok(setup + "\n" + bash_block(S1, "### 4. Delete the reference"))
        self.assertFalse(os.path.exists(self.p("ref")))
        self.assertEqual(sorted(os.listdir(self.p("saves"))), ["cleanup.json", "format.json", "overlap.json", "script.md"])
        for name in os.listdir(self.p("saves")):                 # nothing of the reference was saved
            self.assertNotIn("garden", read(self.p("saves", name)).lower())
        self.assertTrue(os.path.exists(self.p("inputs", "reference_reel", "ref.mp4")))   # the person's file is untouched
        self.assert_no_key_anywhere()

    def test_step1_refuses_a_script_that_shares_six_words(self):
        setup = self.run_step1_to_format()
        self.good_script()
        text = read(self.p("work", "script.txt"))
        paras = text.split("\n\n")
        paras[1] = "so remember that every kink in the line steals half the flow " + paras[1]   # six or more shared words
        write(self.p("work", "script.txt"), "\n\n".join(paras))
        r = self.bash(setup + "\n" + bash_block(S1, "### 3. Write the new script"))
        # the shape check may also object to the extra words; the overlap check must be reached on its own
        r2 = self.bash("RS=\"$RECIPE_DIR/scripts\"\n" + "python3 \"$RS/check_overlap.py\" --script work/script.txt --reference ref/words.json")
        self.assertEqual(r2.returncode, 1)
        self.assertIn("OVERLAP: FAIL", r2.stdout)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(self.p("ref", "words.json")))   # nothing deleted until the script passes

    # ---- step 2 -----------------------------------------------------------------------------
    def stage2_inputs(self, seconds=20):
        for d in ("work", "saves"):
            os.makedirs(self.p(d), exist_ok=True)
        fmt = H.valid_format(duration_s=20.0)
        write(self.p("prior", "format.json"), json.dumps(fmt))
        paras = [" ".join("w%dx%d" % (i, k) for k in range(n)) + "." for i, n in enumerate((20, 60, 20))]
        write(self.p("prior", "script.md"), "\n\n".join(paras))
        write(self.p("inputs", "avatar_id", "avatar_id.md"), "avatar_TEST\n")
        write(self.p("inputs", "voice_id", "voice_id.md"), "voice_TEST\n")
        make_avatar_video(self.p("fake-heygen.mp4"), seconds=seconds)

    def narrate(self, scenario="ok", key=KEY, seconds=20, extra=None):
        self.stage2_inputs(seconds)
        fake = FakeHeyGen(self.p("fake-heygen.mp4"), scenario)
        self.fakes.append(fake)
        self.addCleanup(fake.stop)
        setup = bash_block(S2, "## How")
        r = self.bash(setup + "\n" + bash_block(S2, "### 1. Narrate"), blocks=self.shim, key=key, fake=fake, extra=extra)
        return r, fake, setup

    def test_step2_narration_request_and_base_reel(self):
        r, fake, setup = self.narrate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        creates = [s for s in fake.seen if s[0] == "POST"]
        self.assertEqual(len(creates), 1)                          # one paid create, never repeated
        sent = fake.bodies[0]
        self.assertEqual(sent["type"], "avatar")
        self.assertEqual((sent["avatar_id"], sent["voice_id"]), ("avatar_TEST", "voice_TEST"))
        self.assertEqual((sent["aspect_ratio"], sent["resolution"]), ("9:16", "1080p"))
        self.assertEqual(sent["background"], {"type": "color", "value": "#14181F"})
        spoken = read(self.p("work", "narration.txt")).strip()
        self.assertEqual(sent["script"], spoken)
        self.assertEqual(len(spoken.splitlines()), 1)
        self.assertTrue(spoken.startswith("w0x0 w0x1"))
        self.assertEqual(creates[0][2], KEY)                      # the key went to the API host in the header
        self.assertIsNone([s for s in fake.seen if s[1] == "/files/out.mp4"][0][2])   # and not to the download
        r = self.bash(setup + "\n" + bash_block(S2, "### 2. Fit the canvas"), blocks=self.shim)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                               "-of", "csv=p=0", self.p("saves", "base_reel.mp4")], capture_output=True, text=True).stdout.strip()
        self.assertEqual(dims, "1080,1920")
        self.assert_no_key_anywhere()

    def test_step2_render_record_is_saved_and_a_rerun_does_not_pay_twice(self):
        r, fake, setup = self.narrate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.loads(read(self.p("saves", "render_record.json")))
        self.assertEqual(rec["video_id"], "vid_1")
        self.assertNotIn(KEY, json.dumps(rec))
        # a fresh work/ (a new attempt in the same folder): the saved record is restored, the render is resumed
        shutil.rmtree(self.p("work"))
        os.makedirs(self.p("work"))
        r = self.bash(setup + "\n" + bash_block(S2, "### 1. Narrate"), blocks=self.shim, key=KEY, fake=fake)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len([s for s in fake.seen if s[0] == "POST"]), 1)   # still one paid create

    def test_step2_a_failed_render_still_keeps_its_record(self):
        r, fake, _ = self.narrate("failed")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(self.p("saves", "render_record.json")))

    def test_step2_key_variable_is_read_silently_and_not_exported(self):
        block = bash_block(S2, "### 0. Fill the key variable")
        for shell in [BASH] + ([shutil.which("zsh")] if shutil.which("zsh") else []):
            code = block + "\nprintf 'len=%s\\n' \"${#ORDER_KEY}\"\nenv | grep -c '^ORDER_KEY=' || true\nsh -c 'echo child=${ORDER_KEY:-unset}'"
            env = {k: v for k, v in os.environ.items() if k != "ORDER_KEY"}
            r = subprocess.run([shell, "-c", code], input=KEY + "\n", capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, shell + r.stderr)
            self.assertEqual(r.stdout.split(), ["len=%d" % len(KEY), "0", "child=unset"], shell)
            self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_step2_background_colour_from_the_bot(self):
        r, fake, _ = self.narrate(extra={"BG": "#336699"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(fake.bodies[0]["background"], {"type": "color", "value": "#336699"})

    def test_step2_no_key_sends_nothing(self):
        r, fake, _ = self.narrate(key=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(fake.seen, [])
        self.assertIn("key", (r.stdout + r.stderr).lower())

    def test_step2_a_server_that_echoes_the_key_never_leaks_it(self):
        r, fake, _ = self.narrate("echo_key")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len([s for s in fake.seen if s[0] == "POST"]), 1)   # no second paid attempt
        self.assert_no_key_anywhere()

    def test_step2_a_failed_render_stops(self):
        r, fake, _ = self.narrate("failed")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("saves", "base_reel.mp4")))
        self.assert_no_key_anywhere()

    def test_step2_a_script_with_the_wrong_shape_is_stopped_before_any_call(self):
        self.stage2_inputs()
        write(self.p("prior", "script.md"), "Only one short paragraph here.")
        fake = FakeHeyGen(self.p("fake-heygen.mp4"))
        self.addCleanup(fake.stop)
        r = self.bash(bash_block(S2, "## How"), blocks=self.shim, key=KEY, fake=fake)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(fake.seen, [])

    # ---- step 3, with the real blocks ----------------------------------------------------------
    def plan(self, seconds=20):
        groups, t, i = [], 0.0, 0
        while t < seconds - 0.5:
            end = min(t + 2.0, float(seconds))
            groups.append({"start": t, "end": end, "style": i % 3,
                           "words": [{"w": "WORD", "s": t + 0.1, "e": t + 0.8, "em": False},
                                     {"w": "HERE", "s": t + 0.9, "e": end - 0.1, "em": i % 2 == 0}]})
            t, i = end, i + 1
        return {"grade": "clean-bright", "brand": {"accent": "#F97316", "fg": "#F1F5F9"}, "caption_groups": groups,
                "sfx": [{"t": 1.5, "name": "pop", "gain": 0.2}, {"t": min(8.0, seconds - 1.0), "name": "click", "gain": 0.2}]}

    def test_full_chain_with_real_blocks_and_the_final_gate(self):
        # steps 1 and 2 first, then hand the saves forward as prior/ files, as an order does
        setup1 = self.run_step1_to_format()
        self.good_script()
        self.ok(setup1 + "\n" + bash_block(S1, "### 3. Write the new script"))
        self.ok(setup1 + "\n" + bash_block(S1, "### 4. Delete the reference"))
        prior = self.p("prior")
        os.makedirs(prior, exist_ok=True)
        for name in ("format.json", "script.md"):
            os.replace(self.p("saves", name), os.path.join(prior, name))
        for name in os.listdir(self.p("saves")):
            os.remove(self.p("saves", name))
        write(self.p("inputs", "avatar_id", "avatar_id.md"), "avatar_TEST\n")
        write(self.p("inputs", "voice_id", "voice_id.md"), "voice_TEST\n")
        make_avatar_video(self.p("fake-heygen.mp4"), seconds=20)
        fake = FakeHeyGen(self.p("fake-heygen.mp4"))
        self.addCleanup(fake.stop)
        setup2 = bash_block(S2, "## How")
        self.ok(setup2 + "\n" + bash_block(S2, "### 1. Narrate"), blocks=self.shim, key=KEY, fake=fake)
        self.ok(setup2 + "\n" + bash_block(S2, "### 2. Fit the canvas"), blocks=self.shim)
        os.replace(self.p("saves", "base_reel.mp4"), os.path.join(prior, "base_reel.mp4"))

        setup3 = bash_block(S3, "## How")
        self.ok(setup3 + "\n" + bash_block(S3, "### 1. Transcribe the new narration"))
        self.assertEqual(len(json.loads(read(self.p("premium", "words.json")))), 3)
        write(self.p("premium", "plan.json"), json.dumps(self.plan(20)))
        self.ok(setup3 + "\n" + bash_block(S3, "### 2. Write the caption plan"))      # the real check_plan.py
        self.assertTrue(os.path.exists(self.p("work", "hint.txt")))
        # HyperFrames is not installed in these tests: a transparent stand-in caption video (alpha, same size) is
        # laid over the reel by the real mux.py. The real render is exercised in the scratch run reported with the recipe.
        make_alpha_mov(self.p("premium", "captions.mov"), 20)
        self.ok(setup3 + "\n" + bash_block(S3, "### 4. Grade and mix"))
        self.assertTrue(os.path.exists(self.p("premium", "polished.mp4")))
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))     # nothing is saved before the gate passes
        self.ok(setup3 + "\n" + bash_block(S3, "### 5. Run the quality gate"))
        card = json.loads(read(self.p("work", "scorecard.json")))
        self.assertEqual(card["verdict"], "PASS_WITH_LOOKS", [c for c in card["checks"] if c["status"] == "FAIL"])
        self.assertEqual(card["recipe"], "r-inspired-reel")
        for c in card["checks"]:
            self.assertNotIn("not supported", c["detail"].lower())
            self.assertNotEqual(c["status"], "FAIL", c)
        kinds = {c["type"] for c in card["checks"]}
        self.assertTrue(kinds <= {"dims", "duration_window", "mean_volume", "perceptual", "qa_gate"}, kinds)
        looks = [c["id"] for c in card["checks"] if c["status"] == "LOOK"]
        self.assertEqual(sorted(looks), sorted(["avatar_on_screen", "captions_readable", "shape_matches_format",
                                                 "nothing_of_the_reference", "cover_frame_clean"]))
        write(self.p("work", "answers.json"), json.dumps({k: {"answer": "yes", "note": "looked"} for k in looks}))
        self.ok(setup3 + "\n" + bash_block(S3, "### 6. Answer the looks"))
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))
        self.ok(setup3 + "\n" + bash_block(S3, "### 7. Confirm nothing of the reference"))
        final = json.loads(read(self.p("saves", "qa_report.json")))
        self.assertEqual(final["verdict"], "PASS")
        self.assertEqual(H.read_bytes(self.p("saves", "final.mp4")), H.read_bytes(self.p("premium", "polished.mp4")))
        # a swapped final file is refused and nothing is delivered
        os.remove(self.p("saves", "final.mp4"))
        os.remove(self.p("saves", "qa_report.json"))
        make_avatar_video(self.p("premium", "polished.mp4"), seconds=20, size="1080x1920")
        r = self.bash(setup3 + "\n" + bash_block(S3, "### 7. Confirm nothing of the reference"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("changed after the scorecard", r.stdout)
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))
        self.assertFalse(os.path.exists(self.p("saves", "qa_report.json")))
        self.assertFalse(os.path.exists(self.p("ref")))
        # the duration window follows format.json: tell the gate the reference was 40 s and the 20 s reel fails
        fmt = json.loads(read(self.p("prior", "format.json")))
        fmt["duration_s"] = 40.0
        write(self.p("prior", "format.json"), json.dumps(fmt))
        r = self.bash(setup3 + "\n" + bash_block(S3, "### 5. Run the quality gate"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("duration_window", read(self.p("work", "scorecard.json")))
        self.assertEqual(json.loads(read(self.p("work", "scorecard.json")))["verdict"], "FAIL")
        self.assert_no_key_anywhere()

    def light_setup(self):
        """Step 3's setup block without the check for the earlier steps' saves (these tests do not make them)."""
        return bash_block(S3, "## How").replace("for f in prior/base_reel.mp4 prior/format.json prior/script.md; do",
                                                "for f in prior/format.json; do")

    def test_step3_no_captions_path(self):
        make_avatar_video(self.p("work", "avatar.mp4"), seconds=6)
        self.ok("python3 \"$RECIPE_DIR/scripts/make_base_reel.py\" --avatar work/avatar.mp4 --out prior/base_reel.mp4")
        write(self.p("prior", "format.json"), json.dumps(H.valid_format(duration_s=6.0)))
        plan = self.plan(6)
        plan["grade"] = "off"
        write(self.p("premium", "plan.json"), json.dumps(plan))
        setup = self.light_setup()
        self.ok(setup + "\n" + bash_block(S3, "### 4. Grade and mix"), extra={"NO_CAPTIONS": "1"})
        self.assertTrue(os.path.exists(self.p("premium", "polished.mp4")))

    def test_a_look_answered_no_fails_the_gate(self):
        make_avatar_video(self.p("work", "avatar.mp4"), seconds=20)
        self.ok("python3 \"$RECIPE_DIR/scripts/make_base_reel.py\" --avatar work/avatar.mp4 --out premium/polished.mp4")
        write(self.p("prior", "format.json"), json.dumps(H.valid_format(duration_s=20.0)))
        setup = self.light_setup()
        self.ok(setup + "\n" + bash_block(S3, "### 5. Run the quality gate"))
        looks = [c["id"] for c in json.loads(read(self.p("work", "scorecard.json")))["checks"] if c["status"] == "LOOK"]
        write(self.p("work", "answers.json"), json.dumps({k: {"answer": "no" if k == "nothing_of_the_reference" else "yes", "note": "x"} for k in looks}))
        r = self.bash(setup + "\n" + bash_block(S3, "### 6. Answer the looks"))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("saves", "qa_report.json")))
        # the FAIL scorecard cannot be delivered: step 7 stops and saves nothing
        r = self.bash(setup + "\n" + bash_block(S3, "### 7. Confirm nothing of the reference"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DELIVERY: REFUSED", r.stdout)
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))
        self.assertFalse(os.path.exists(self.p("saves", "qa_report.json")))

    def test_a_missing_answer_stops_the_step_and_nothing_is_delivered(self):
        make_avatar_video(self.p("work", "avatar.mp4"), seconds=20)
        self.ok("python3 \"$RECIPE_DIR/scripts/make_base_reel.py\" --avatar work/avatar.mp4 --out premium/polished.mp4")
        write(self.p("prior", "format.json"), json.dumps(H.valid_format(duration_s=20.0)))
        setup = self.light_setup()
        self.ok(setup + "\n" + bash_block(S3, "### 5. Run the quality gate"))
        looks = [c["id"] for c in json.loads(read(self.p("work", "scorecard.json")))["checks"] if c["status"] == "LOOK"]
        write(self.p("work", "answers.json"), json.dumps({k: {"answer": "yes", "note": "x"} for k in looks[1:]}))
        r = self.bash(setup + "\n" + bash_block(S3, "### 6. Answer the looks"))
        self.assertNotEqual(r.returncode, 0)
        r = self.bash(setup + "\n" + bash_block(S3, "### 7. Confirm nothing of the reference"))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))

    def test_step3_final_check_fails_when_reference_files_are_left(self):
        write(self.p("prior", "format.json"), json.dumps(H.valid_format()))
        write(self.p("ref", "words.json"), json.dumps(timed(REF_TEXT)))
        r = self.bash(self.light_setup() + "\n" + bash_block(S3, "### 7. Confirm nothing"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("still there: ref/words.json", r.stdout)


class StaticChecks(unittest.TestCase):
    def test_step_files_have_the_blocks_the_tests_use(self):
        for name, heads in ((S1, ["## How", "### 1.", "### 2.", "### 3.", "### 4."]),
                            (S2, ["## How", "### 1.", "### 2."]),
                            (S3, ["## How", "### 1.", "### 2.", "### 4.", "### 5.", "### 6.", "### 7."])):
            for h in heads:
                self.assertTrue(bash_block(name, h))
            self.assertTrue(bash_block(name, "## How").startswith("set -eu"), name)   # every command stops the step
            self.assertIn("absolute paths", bash_block(name, "## How"), name)

    def test_every_ffmpeg_and_ffprobe_call_in_the_steps_reads_local_files_only(self):
        for name in (S1, S2, S3):
            text = read(os.path.join(STEPS, name))
            for block in re.findall(r"```bash\n(.*?)\n```", text, re.S):
                for line in block.splitlines():
                    if re.match(r"\s*(ffmpeg|ffprobe)\b", line):
                        self.assertIn("-protocol_whitelist file", line, line)

    def test_a_relative_recipe_or_blocks_folder_is_refused(self):
        for name in (S1, S2, S3):
            r = subprocess.run([BASH, "-c", bash_block(name, "## How")], capture_output=True, text=True,
                               env={"PATH": os.environ["PATH"], "RECIPE_DIR": "recipes/r-inspired-reel", "BLOCKS_DIR": "blocks"})
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("absolute paths", r.stdout)

    def test_options_are_arrays_never_one_unquoted_text_string(self):
        for name in (S1, S2, S3):
            for block in re.findall(r"```bash\n(.*?)\n```", read(os.path.join(STEPS, name)), re.S):
                self.assertNotRegex(block, r"\$\{?[A-Z_]*(ARGS|OPTS|FLAGS)\}?[ \n]", name)
                self.assertNotRegex(block, r"\$\{[A-Za-z_]+:\+[^}]*\}", name)     # the unquoted ${X:+--opt "$X"} idiom
                for m in re.finditer(r"\$\{(\w+)\[@\]\}", block):
                    self.assertIn('"${%s[@]}"' % m.group(1), block)

    def test_no_step_puts_order_text_or_a_key_on_a_command_line(self):
        for name in (S1, S2, S3):
            text = read(os.path.join(STEPS, name))
            self.assertNotRegex(text, r"--api-key|--key[ =]|HEYGEN_API_KEY=[A-Za-z0-9]")
            self.assertNotIn("eval ", text)
            self.assertNotIn("bash -c", text)
            self.assertNotIn("set -x", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
