#!/usr/bin/env python3
"""End-to-end test of r-ai-character through its own documented command lines.

  python3 -I test/test_end_to_end.py -v

No account, no real key, no paid call, no network beyond 127.0.0.1. It runs:

  * the bash blocks of steps 02, 03 and 04, read from the step files;
  * the REAL blocks/b-kie-ai/scripts/generate.py, against a small fake Kie server for the
    create, status, upload and download calls (a thin wrapper adds the two local-only
    --base-url flags and shortens --poll to 1 second; nothing else changes);
  * the REAL blocks/b-qa-gate/check.py with this recipe's acceptance.json.

The reference image is drawn in the test (a plain shape, not a person). The only key used is
a made-up string, which must appear in no output file and no output stream.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(RECIPE))
BLOCKS = os.path.join(REPO, "blocks")
REAL_GEN = os.path.join(BLOCKS, "b-kie-ai", "scripts", "generate.py")
REAL_GATE = os.path.join(BLOCKS, "b-qa-gate", "check.py")
STEPS = os.path.join(RECIPE, "steps")
BASH = shutil.which("bash")
KEY = "test-key-not-real"
W, H = 1080, 1920


def shape_png(w, h, bg=(60, 60, 70), fg=(230, 200, 60)):
    """A plain drawn shape (a round head on a block body) as a PNG. Not a person."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    cx, cy, r = w // 2, h // 3, w // 5
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            on = (x - cx) ** 2 + (y - cy) ** 2 <= r * r or (abs(x - cx) <= r and cy + r <= y <= cy + 3 * r)
            row += bytes(fg if on else bg)
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


class Fake(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, scenario="ok"):
        super().__init__(("127.0.0.1", 0), Handler)
        self.scenario = scenario
        self.seen = []
        self.created = []
        self.png = shape_png(54, 96)
        self.url = "http://127.0.0.1:%d" % self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _record(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.seen.append((self.command, self.path, dict(self.headers), body))
        return body

    def do_POST(self):
        s = self.server
        body = self._record()
        if self.path.startswith("/api/file-stream-upload"):
            return self._send(200, {"code": 200, "data": {"downloadUrl": s.url + "/files/ref.png"}})
        if self.path.startswith("/api/v1/jobs/createTask"):
            if s.scenario == "echo_key":
                return self._send(401, {"code": 401, "msg": "bad key " + KEY})
            s.created.append(json.loads(body))
            return self._send(200, {"code": 200, "data": {"taskId": "task_%d" % len(s.created)}})
        self._send(404, {"code": 404})

    def do_GET(self):
        s = self.server
        self._record()
        if self.path.startswith("/api/v1/jobs/recordInfo"):
            c = s.created[-1]
            rj = {"resultUrls": [s.url + "/img/ok"]}
            data = {"state": "success", "resultJson": json.dumps(rj),
                    "param": json.dumps({"model": c["model"], "input": c["input"]})}
            return self._send(200, {"code": 200, "data": data})
        if self.path == "/img/ok":
            return self._send(200, s.png, "image/png")
        self._send(404, b"nope", "text/plain")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        fh.write(text)


def bash_block(name, heading, nth=0):
    """The nth ```bash block after `heading` in a step file."""
    text = read(os.path.join(STEPS, name))
    at = text.index(heading)
    blocks = re.findall(r"```bash\n(.*?)\n```", text[at:], re.S)
    return blocks[nth]


class Chain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("ffmpeg", "ffprobe", "convert"):
            if not shutil.which(tool):
                raise unittest.SkipTest("%s is not installed" % tool)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aichar-e2e-")
        self.wd = os.path.join(self.root, "wd")
        os.makedirs(self.wd)
        self.fake = Fake()
        self.outputs = []          # every stdout and stderr the steps produced
        # A blocks folder whose b-kie-ai/scripts/generate.py is a thin wrapper around the real
        # script. It adds the local-only base URLs and shortens --poll. Nothing else changes.
        self.shim_recipe = os.path.join(self.root, "recipes", "r-ai-character")   # BLOCKS_DIR is RECIPE_DIR/../../blocks
        os.makedirs(self.shim_recipe)
        self.shim_blocks = os.path.join(self.root, "blocks")
        write(os.path.join(self.shim_blocks, "b-kie-ai", "scripts", "generate.py"),
              "import os, sys\n"
              "args = sys.argv[1:]\n"
              "if '--poll' in args: args[args.index('--poll') + 1] = '1'\n"
              "u = os.environ['TEST_FAKE_URL']\n"
              "os.execv(sys.executable, [sys.executable, os.environ['TEST_REAL_GEN']] + args + ['--base-url', u, '--upload-base-url', u])\n")

    def tearDown(self):
        self.fake.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def bash(self, code, recipe_dir=None, key=KEY, extra=None):
        env = {k: v for k, v in os.environ.items() if k != "KIE_AI_API_KEY"}
        env.pop("BLOCKS_DIR", None)
        env.update(RECIPE_DIR=recipe_dir or self.shim_recipe,
                   TEST_FAKE_URL=self.fake.url, TEST_REAL_GEN=REAL_GEN)
        env.pop("ORDER_KEY", None)
        if key:
            env["ORDER_KEY"] = key
        env.update(extra or {})
        p = subprocess.run([BASH, "-c", "set -eu\n" + code], cwd=self.wd, env=env, capture_output=True, text=True, timeout=300)
        self.outputs += [p.stdout, p.stderr]
        return p

    def dims(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout
        return tuple(int(v) for v in out.strip().split(","))

    def gen_blocks(self, step, heading, setup):
        return setup + "\n" + bash_block(step, heading)

    def assert_no_key_anywhere(self):
        text = "\n".join(self.outputs)
        for dirpath, _d, files in os.walk(self.root):
            for f in files:
                if os.path.join(dirpath, f) == os.path.join(self.shim_blocks, "b-kie-ai", "scripts", "generate.py"):
                    continue
                with open(os.path.join(dirpath, f), "rb") as fh:
                    text += fh.read().decode("latin-1")
        self.assertNotIn(KEY, text)

    # -- step 02, with a reference image drawn in the test ----------------------------------
    def run_step_02(self):
        ref = shape_png(90, 160, bg=(30, 30, 40), fg=(200, 80, 80))
        write(os.path.join(self.wd, "inputs", "reference_image", "ref.png"), ref, "wb")
        write(os.path.join(self.wd, "prior", "character_lock.json"),
              json.dumps({"type": "human", "attributes": {}, "lock_prompt": "a round-headed figure in a red coat"}))
        write(os.path.join(self.wd, "work", "prompt.txt"), "a round-headed figure in a red coat. Full body, plain white studio background, no text.")
        code = bash_block("02-character-ref.md", "## How") + "\n" + bash_block("02-character-ref.md", "### 2. Create, poll, download")
        p = self.bash(code)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("IMAGE_FILE: work/raw-ref.png", p.stdout)
        self.assertEqual(self.dims(os.path.join(self.wd, "work", "char-ref.png")), (W, H))
        return ref

    def test_reference_step_uploads_the_reference_and_sends_one_create(self):
        self.run_step_02()
        creates = [x for x in self.fake.seen if x[1].startswith("/api/v1/jobs/createTask")]
        self.assertEqual(len(creates), 1)                       # the create call is made once
        sent = self.fake.created[0]
        self.assertEqual(sent["model"], "gpt-image-2-image-to-image")
        self.assertEqual(sent["input"]["aspect_ratio"], "9:16")
        self.assertEqual(sent["input"]["resolution"], "2K")
        self.assertEqual(sent["input"]["input_urls"], [self.fake.url + "/files/ref.png"])
        self.assertTrue(sent["input"]["prompt"].startswith("a round-headed figure"))
        self.assertEqual(creates[0][2]["Authorization"], "Bearer " + KEY)
        uploads = [x for x in self.fake.seen if x[1].startswith("/api/file-stream-upload")]
        self.assertEqual(len(uploads), 1)                       # the reference really was uploaded
        self.assertIn(b"\xff\xd8\xff", uploads[0][3])          # the JPEG copy of the reference was sent
        self.assertEqual(uploads[0][2]["Authorization"], "Bearer " + KEY)
        download = [x for x in self.fake.seen if x[1] == "/img/ok"][0]
        self.assertNotIn("Authorization", download[2])          # the download carries no key
        self.assertFalse([f for f in os.listdir(os.path.join(self.wd, "work")) if f.endswith(".download")])
        self.assert_no_key_anywhere()

    def test_reference_step_without_a_picture_uses_z_image_and_no_upload(self):
        write(os.path.join(self.wd, "prior", "character_lock.json"), json.dumps({"type": "human", "lock_prompt": "x"}))
        write(os.path.join(self.wd, "work", "prompt.txt"), "a round-headed figure in a red coat, plain background")
        code = bash_block("02-character-ref.md", "## How") + "\n" + bash_block("02-character-ref.md", "### 2. Create, poll, download")
        p = self.bash(code)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.fake.created[0]["model"], "z-image")
        self.assertNotIn("input_urls", self.fake.created[0]["input"])
        self.assertFalse([x for x in self.fake.seen if x[1].startswith("/api/file-stream-upload")])
        self.assert_no_key_anywhere()

    def test_no_key_stops_with_nothing_sent(self):
        write(os.path.join(self.wd, "prior", "character_lock.json"), json.dumps({"type": "human", "lock_prompt": "x"}))
        write(os.path.join(self.wd, "work", "prompt.txt"), "a figure")
        code = bash_block("02-character-ref.md", "## How") + "\n" + bash_block("02-character-ref.md", "### 2. Create, poll, download")
        p = self.bash(code, key=None)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("IMAGE_FAILED:", p.stdout)
        self.assertIn("no Kie key", p.stdout)
        self.assertEqual(self.fake.seen, [])                    # nothing was sent, nothing spent

    def test_a_server_that_echoes_the_key_never_leaks_it(self):
        self.fake.scenario = "echo_key"
        write(os.path.join(self.wd, "prior", "character_lock.json"), json.dumps({"type": "human", "lock_prompt": "x"}))
        write(os.path.join(self.wd, "work", "prompt.txt"), "a figure")
        code = bash_block("02-character-ref.md", "## How") + "\n" + bash_block("02-character-ref.md", "### 2. Create, poll, download")
        p = self.bash(code)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("IMAGE_FAILED:", p.stdout)
        self.assert_no_key_anywhere()

    # -- the whole chain: 02 -> 03 -> 04 ------------------------------------------------------
    def test_full_chain_from_reference_to_final_scorecards(self):
        self.run_step_02()
        # step 02 saves (the bot's audit file is written by the bot)
        p = self.bash("TASK=task_1\nMODEL=gpt-image-2-image-to-image\n" + bash_block("02-character-ref.md", "### 3. Audit against the lock"),
                      extra={"RECIPE_DIR": RECIPE})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.bash(bash_block("02-character-ref.md", "### 4. Write the saves"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        shutil.copy(os.path.join(self.wd, "saves", "char_ref.png"), os.path.join(self.wd, "prior", "char_ref.png"))
        n = 3
        write(os.path.join(self.wd, "prior", "story_arc.json"), json.dumps({"num_scenes": n}))
        setup = bash_block("03-scene-images.md", "## How")
        step = bash_block("03-scene-images.md", "### 1. Per scene, in order")
        for i in range(1, n + 1):
            write(os.path.join(self.wd, "work", "prompt-%d.txt" % i), "scene %d: the same round-headed figure in a red coat, walking. No text." % i)
            p = self.bash(setup + "\ni=%d\n" % i + step)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(self.dims(os.path.join(self.wd, "work", "scene-%d.png" % i)), (W, H))
            p = self.bash("TASK=task_%d\ni=%d\n" % (i + 1, i) + bash_block("03-scene-images.md", "### 2. Divergence check"),
                          extra={"RECIPE_DIR": RECIPE})
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # every scene call carried the reference (the generated one, as a JPEG copy)
        for c in self.fake.created[1:]:
            self.assertEqual(c["model"], "gpt-image-2-image-to-image")
            self.assertEqual(len(c["input"]["input_urls"]), 1)
        self.assertEqual(sorted(json.loads(read(os.path.join(self.wd, "work", "tasks.json")))), ["1", "2", "3"])
        p = self.bash("N=%d\n%s" % (n, bash_block("03-scene-images.md", "### 3. Write the saves")))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for f in ("scene_1.png", "scene_sheet.png", "scenes.json"):
            shutil.copy(os.path.join(self.wd, "saves", f), os.path.join(self.wd, "prior", f))

        # step 04, with the REAL b-qa-gate
        p = self.bash(bash_block("04-qa-gate.md", "## How") + "\n" + bash_block("04-qa-gate.md", "### 1. Re-split the set from the sheet")
                      + "\n" + bash_block("04-qa-gate.md", "### 2. Run the gate on each scene"), recipe_dir=RECIPE)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for i in range(1, n + 1):
            card = json.loads(read(os.path.join(self.wd, "work", "scorecard-%d.json" % i)))
            self.assertEqual(card["verdict"], "PASS_WITH_LOOKS")
            kinds = {c["type"] for c in card["checks"]}
            self.assertTrue(kinds <= {"dims", "luma_floor", "not_flat", "perceptual"}, kinds)
            for c in card["checks"]:
                self.assertNotIn("not supported", c["detail"].lower())
                self.assertNotEqual(c["status"], "FAIL", c)
            looks = [c["id"] for c in card["checks"] if c["status"] == "LOOK"]
            self.assertEqual("cover_is_moneyshot" in looks, i == 1)   # only scene 1 owes the cover look
            write(os.path.join(self.wd, "work", "answers-%d.json" % i),
                  json.dumps({k: {"answer": "yes", "note": "looked"} for k in looks}))
        p = self.bash(bash_block("04-qa-gate.md", "## How") + "\n" + bash_block("04-qa-gate.md", "### 4. Record the answers"), recipe_dir=RECIPE)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.bash(bash_block("04-qa-gate.md", "### 5. Write the saves"), recipe_dir=RECIPE)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        report = json.loads(read(os.path.join(self.wd, "saves", "qa_report.json")))
        self.assertEqual([s["verdict"] for s in report["scenes"]], ["PASS"] * n)
        self.assertEqual(self.dims(os.path.join(self.wd, "saves", "final.png")), (W, H))
        self.assert_no_key_anywhere()

    def test_gate_exit_codes_on_the_recipe_spec(self):
        """The real check.py on acceptance.json: 4 with looks owed, then 0 after all-yes answers."""
        ref_png = os.path.join(self.wd, "work", "scene-9.png")
        os.makedirs(os.path.dirname(ref_png))
        small = os.path.join(self.wd, "work", "small.png")
        write(small, shape_png(54, 96), "wb")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", small, "-vf", "scale=%d:%d" % (W, H), ref_png], check=True)
        spec = os.path.join(RECIPE, "acceptance.json")
        run = lambda *a: subprocess.run([sys.executable, REAL_GATE] + list(a), cwd=self.wd, capture_output=True, text=True)
        p = run("--kind", "image", "--spec", spec, "--input", "work/scene-9.png", "--out", "work/card.json")
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        card = json.loads(read(os.path.join(self.wd, "work", "card.json")))
        looks = [c["id"] for c in card["checks"] if c["status"] == "LOOK"]
        self.assertGreaterEqual(len(looks), 5)
        write(os.path.join(self.wd, "work", "ans.json"), json.dumps({k: {"answer": "yes", "note": "ok"} for k in looks}))
        p = run("--finalize", "work/card.json", "--answers", "work/ans.json", "--out", "work/final.json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # one "no" fails the run
        write(os.path.join(self.wd, "work", "ans2.json"), json.dumps({k: {"answer": "no" if k == looks[0] else "yes", "note": "x"} for k in looks}))
        run("--kind", "image", "--spec", spec, "--input", "work/scene-9.png", "--out", "work/card2.json")
        p = run("--finalize", "work/card2.json", "--answers", "work/ans2.json", "--out", "work/final2.json")
        self.assertEqual(p.returncode, 1)
        # a wrong-size image fails the mechanical check
        small2 = os.path.join(self.wd, "work", "wrong.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", small, "-vf", "scale=100:100", small2], check=True)
        p = run("--kind", "image", "--spec", spec, "--input", "work/wrong.png", "--out", "work/card3.json")
        self.assertEqual(p.returncode, 1, p.stdout)

    def test_acceptance_json_uses_only_kinds_the_gate_owns(self):
        spec = json.loads(read(os.path.join(RECIPE, "acceptance.json")))
        lists = [spec["checks"]] + [s["checks"] for s in spec.get("steps", {}).values()]
        for checks in lists:
            for c in checks:
                self.assertIn(c["type"], {"dims", "luma_floor", "not_flat", "perceptual"}, c["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
