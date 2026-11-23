#!/usr/bin/env python3
"""Tests that run the recipe's steps with the REAL blocks `b-kie-ai` and `b-qa-gate`.

  python3 -I test/test_blocks_flow.py -v        (from this recipe's folder)

No network, no real key and no paid account. A small fake Kie server runs on 127.0.0.1. Every
test runs the step's OWN code blocks, read from the step files, in a throwaway work folder. The
real `generate.py` runs through the command line the step documents. The only addition is a tiny
stand-in file at the path `$BLOCKS_DIR/b-kie-ai/scripts/generate.py` that calls the real script and
appends the test-only `--base-url` options, so the fake server is used instead of the Kie hosts.
The real `check.py` of `b-qa-gate` is used as is.

Needs python3, bash, ffmpeg and ffprobe, as the recipe does.
"""
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
import warnings
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

warnings.simplefilter("ignore", ResourceWarning)   # the tests read small files with a bare open()

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(RECIPE))
REAL_GEN = os.path.join(REPO, "blocks", "b-kie-ai", "scripts", "generate.py")
REAL_QA = os.path.join(REPO, "blocks", "b-qa-gate")
SHARED = os.path.join(RECIPE, "steps", "_shared.md")
STEP01 = os.path.join(RECIPE, "steps", "01-plan-prompts.md")
STEP02 = os.path.join(RECIPE, "steps", "02-generate.md")
STEP03 = os.path.join(RECIPE, "steps", "03-qa-gate.md")
KEY = "test-key-not-real"
LOOK_IDS = ["subject_rendered", "no_artifacts", "legible_text", "palette_premium", "composition_quality"]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def bash_block(path, heading):
    """The first ```bash block after `heading` in a step file."""
    text = read(path)
    at = text.index(heading)
    m = re.compile(r"```bash\n(.*?)\n```", re.S).search(text, at)
    assert m, "no bash block after %r in %s" % (heading, path)
    return m.group(1)


def text_blocks(path):
    return re.findall(r"```text\n(.*?)\n```", read(path), re.S)


def png_bytes(w=16, h=16):
    """A PNG with four colour quadrants, so it is neither black nor flat."""
    cols = [(200, 60, 60), (40, 160, 200), (240, 230, 40), (30, 30, 90)]
    rows = b""
    for y in range(h):
        row = b"".join(bytes(cols[(y >= h // 2) * 2 + (x >= w // 2)]) for x in range(w))
        rows += b"\x00" + row

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class Fake(ThreadingHTTPServer):
    """A fake Kie. scenario: ok, fail (task fails), echo_key (create refused, the reply holds the key)."""
    daemon_threads = True

    def __init__(self, scenario="ok"):
        super().__init__(("127.0.0.1", 0), Handler)
        self.scenario = scenario
        self.seen = []
        self.created = None
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

    def do_POST(self):
        s = self.server
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        s.seen.append(("POST", self.path, dict(self.headers), body))
        if self.path.startswith("/api/file-stream-upload"):
            return self._send(200, {"code": 200, "data": {"downloadUrl": s.url + "/files/ref.png"}})
        if self.path.startswith("/api/v1/jobs/createTask"):
            if s.scenario == "echo_key":
                return self._send(401, {"code": 401, "msg": "bad key " + KEY})
            s.created = json.loads(body)
            return self._send(200, {"code": 200, "data": {"taskId": "task_%d" % len(
                [x for x in s.seen if x[1].startswith("/api/v1/jobs/createTask")])}})
        self._send(404, {"code": 404})

    def do_GET(self):
        s = self.server
        s.seen.append(("GET", self.path, dict(self.headers), b""))
        if self.path.startswith("/api/v1/jobs/recordInfo"):
            created = s.created or {"model": "m", "input": {"prompt": "p"}}
            data = {"state": "success", "param": json.dumps(created),
                    "resultJson": json.dumps({"resultUrls": [s.url + "/img/ok"]})}
            if s.scenario == "fail":
                data = {"state": "fail", "param": json.dumps(created), "failMsg": "rejected " + KEY}
            return self._send(200, {"code": 200, "data": data})
        if self.path == "/img/ok":
            return self._send(200, png_bytes(), "image/png")
        self._send(404, b"nope", "text/plain")


STAND_IN = """import os, sys
# test stand-in: runs the real generate.py with the test-only server options added at the end
args = sys.argv[1:] + ["--base-url", %r, "--upload-base-url", %r, "--poll", "1"]
os.execv(sys.executable, [sys.executable, %r] + args)
"""


class Case(unittest.TestCase):
    """One throwaway tree: recipes/r-ai-image (spec only), blocks/ (stand-in and real check.py), a work folder."""

    @classmethod
    def setUpClass(cls):
        for tool in ("ffmpeg", "ffprobe"):
            assert shutil.which(tool), "%s is required (the recipe needs it too)" % tool
        assert os.path.isfile(REAL_GEN) and os.path.isfile(os.path.join(REAL_QA, "check.py")), "blocks are missing"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aiimg-flow-")
        self.recipe_dir = os.path.join(self.root, "recipes", "r-ai-image")
        os.makedirs(self.recipe_dir)
        shutil.copy(os.path.join(RECIPE, "acceptance.json"), self.recipe_dir)
        os.makedirs(os.path.join(self.root, "blocks", "b-kie-ai", "scripts"))
        os.symlink(REAL_QA, os.path.join(self.root, "blocks", "b-qa-gate"))
        self.wd = os.path.join(self.root, "work-folder")
        os.makedirs(self.wd)
        self.server = None
        self.outputs = []

    def tearDown(self):
        if self.server:
            self.server.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, scenario="ok"):
        self.server = Fake(scenario)
        write(os.path.join(self.root, "blocks", "b-kie-ai", "scripts", "generate.py"),
              STAND_IN % (self.server.url, self.server.url, REAL_GEN))

    def order(self, count=1, aspect="1:1", reference=False, model=None, negative="blurry, watermark"):
        prompts = {"count": count, "aspect_ratio": aspect, "negative": negative, "has_reference": reference,
                   "model": model or ("gpt-image-2-image-to-image" if reference else "z-image"),
                   "images": [{"n": i, "variant": "v%d" % i,
                               "prompt": "A calm red cube on a wooden table in soft morning light, variant %d." % i}
                              for i in range(1, count + 1)]}
        write(os.path.join(self.wd, "prior", "prompts.json"), json.dumps(prompts))
        if reference:
            os.makedirs(os.path.join(self.wd, "inputs", "reference_image"))
            with open(os.path.join(self.wd, "inputs", "reference_image", "ref.png"), "wb") as fh:
                fh.write(png_bytes(64, 48))
        return prompts

    def sh(self, script, key=False, extra_env=None, shim=False):
        """Run a script after the paths snippet from _shared.md. The key is the unexported shell variable
        KEY (as the steps say), never in the environment of the shell itself."""
        env = {k: v for k, v in os.environ.items() if k != "KIE_AI_API_KEY"}
        env["RECIPE_DIR"] = self.recipe_dir
        if shim:
            env["PATH"] = self.make_shim() + os.pathsep + env["PATH"]
        env.update(extra_env or {})
        prelude = bash_block(SHARED, "## Tools and pins") + "\n" + ("KEY=%s\n" % KEY if key else "")
        r = subprocess.run(["bash", "-c", "set -eu\n" + prelude + script], cwd=self.wd, env=env,
                           capture_output=True, text=True, timeout=180)
        self.outputs.append(r.stdout + r.stderr)
        return r

    def make_shim(self):
        """A PATH folder whose ffmpeg, ffprobe and python3 log each call and whether the key was in its environment."""
        d = os.path.join(self.root, "shim")
        os.makedirs(d, exist_ok=True)
        self.shim_log = os.path.join(self.root, "shim.log")
        for name, real in (("ffmpeg", shutil.which("ffmpeg")), ("ffprobe", shutil.which("ffprobe")), ("python3", sys.executable)):
            p = os.path.join(d, name)
            write(p, "#!/bin/sh\nprintf '%%s|%%s|%%s\\n' '%s' \"${KIE_AI_API_KEY:+KEY}\" \"$*\" >> '%s'\nexec '%s' \"$@\"\n"
                  % (name, self.shim_log, real))
            os.chmod(p, 0o755)
        return d

    def step02(self, shim=False):
        """Section 0 and 1 (the key is on the generate command only); then sections 2 and 3 without any key."""
        setup = bash_block(STEP02, "### 0. Set up")
        r = self.sh(setup + "\n" + bash_block(STEP02, "### 1. Generate"), key=True, shim=shim)
        if r.returncode != 0:
            return r
        return self.sh(setup + "\n" + bash_block(STEP02, "### 2. Fit to the canvas") + "\n"
                       + bash_block(STEP02, "### 3. Write the saves"), shim=shim)

    def to_step03(self):
        shutil.rmtree(os.path.join(self.wd, "prior"), ignore_errors=True)
        os.makedirs(os.path.join(self.wd, "prior"))
        for f in ("images.json", "image_1.png", "contact_sheet.png"):
            shutil.copy(os.path.join(self.wd, "saves", f), os.path.join(self.wd, "prior", f))
        # the prompts stay: step 03 reads them next to each image
        write(os.path.join(self.wd, "prior", "prompts.json"), json.dumps(self.prompts))

    def gate(self):
        """Step 03, sections 0, 1 and 2 (the mechanical checks)."""
        setup = bash_block(STEP03, "## How")
        return self.sh(setup + "\n" + bash_block(STEP03, "### 1. Re-split") + "\n"
                       + bash_block(STEP03, "### 2. Mechanical checks"))

    def answers(self, n, answer="yes"):
        card = json.load(open(os.path.join(self.wd, "work", "scorecard-%d.json" % n)))
        looks = [c["id"] for c in card["checks"] if c["status"] == "LOOK"]
        self.assertEqual(looks, LOOK_IDS)
        write(os.path.join(self.wd, "work", "answers-%d.json" % n),
              json.dumps({i: {"answer": answer, "note": "looked"} for i in looks}))

    def finish(self, env=None):
        setup = bash_block(STEP03, "## How")
        return self.sh(setup + "\n" + bash_block(STEP03, "### 3. Answer the looks") + "\n"
                       + bash_block(STEP03, "### 4. Pick the final"), extra_env=env)

    def created(self):
        return [x for x in self.server.seen if x[1].startswith("/api/v1/jobs/createTask")]

    def all_text(self):
        text = "".join(self.outputs)
        for dirpath, _d, files in os.walk(self.root):
            for f in files:
                p = os.path.join(dirpath, f)
                if os.path.islink(p):
                    continue
                with open(p, "rb") as fh:
                    text += fh.read().decode("latin-1")
        return text


def dims(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    return tuple(int(v) for v in out.split(","))


class TextToImageEndToEnd(Case):
    def test_documented_command_makes_a_png_and_the_gate_passes(self):
        self.start()
        self.prompts = self.order(count=1)
        r = self.step02()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # generate.py ran through the documented command and wrote a PNG in the work folder
        raw = os.path.join(self.wd, "work", "raw-1.png")
        self.assertTrue(open(raw, "rb").read().startswith(b"\x89PNG"))
        self.assertEqual(dims(os.path.join(self.wd, "saves", "image_1.png")), (1080, 1080))
        sent = self.created()
        self.assertEqual(len(sent), 1)
        body = json.loads(sent[0][3])
        self.assertEqual(body["model"], "z-image")
        self.assertEqual(body["input"]["aspect_ratio"], "1:1")
        self.assertTrue(body["input"]["prompt"].endswith(". Avoid: blurry, watermark"))
        self.assertNotIn("input_urls", body["input"])
        self.assertEqual(sent[0][2]["Authorization"], "Bearer " + KEY)       # the key reached Kie, as a header
        tasks = json.load(open(os.path.join(self.wd, "work", "tasks.json")))
        self.assertEqual(tasks["1"]["attempts"], 1)
        self.assertEqual(json.load(open(os.path.join(self.wd, "saves", "images.json")))["images"][0]["attempts"], 1)

        # the real check.py, the recipe's acceptance.json, directly: exit 4 (looks owed) or 0
        card = os.path.join(self.wd, "work", "direct.json")
        run = subprocess.run([sys.executable, os.path.join(REAL_QA, "check.py"), "--kind", "image", "--spec",
                              os.path.join(RECIPE, "acceptance.json"), "--input", "work/img-1.png", "--out", "work/direct.json"],
                             cwd=self.wd, capture_output=True, text=True)
        self.assertIn(run.returncode, (0, 4), run.stdout + run.stderr)
        rows = json.load(open(card))["checks"]
        for row in rows:
            self.assertNotIn("not supported", row["detail"])
            self.assertNotIn("not known", row["detail"])
        self.assertEqual({r["status"] for r in rows if r["type"] != "perceptual"}, {"PASS"})
        answers = {r["id"]: {"answer": "yes", "note": "looked"} for r in rows if r["status"] == "LOOK"}
        write(os.path.join(self.wd, "work", "direct-answers.json"), json.dumps(answers))
        fin = subprocess.run([sys.executable, os.path.join(REAL_QA, "check.py"), "--finalize", "work/direct.json",
                              "--answers", "work/direct-answers.json", "--out", "work/direct-final.json"],
                             cwd=self.wd, capture_output=True, text=True)
        self.assertEqual(fin.returncode, 0, fin.stdout + fin.stderr)
        self.assertEqual(json.load(open(os.path.join(self.wd, "work", "direct-final.json")))["verdict"], "PASS")

        # and the same through step 03's own blocks
        self.to_step03()
        g = self.gate()
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        self.assertEqual(open(os.path.join(self.wd, "work", "gate-status.txt")).read().split(), ["1", "4"])
        self.answers(1)
        f = self.finish()
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        report = json.load(open(os.path.join(self.wd, "saves", "qa_report.json")))
        self.assertEqual((report["final_n"], report["images"][0]["verdict"]), (1, "PASS"))
        self.assertEqual(dims(os.path.join(self.wd, "saves", "final.png")), (1080, 1080))

    def test_portrait_batch_of_two_is_checked_against_its_own_canvas(self):
        self.start()
        self.prompts = self.order(count=2, aspect="9:16")
        r = self.step02()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.created()), 2)
        self.assertEqual({json.loads(c[3])["input"]["aspect_ratio"] for c in self.created()}, {"9:16"})
        self.assertEqual(dims(os.path.join(self.wd, "work", "img-2.png")), (1080, 1920))
        self.to_step03()
        g = self.gate()
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        spec = json.load(open(os.path.join(self.wd, "work", "acceptance.json")))
        self.assertEqual([(c["w"], c["h"]) for c in spec["checks"] if c["type"] == "dims"], [(1080, 1920)])
        for n in (1, 2):
            self.answers(n)
        f = self.finish(env={"FINAL_N": "2"})
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        self.assertEqual(json.load(open(os.path.join(self.wd, "saves", "qa_report.json")))["final_n"], 2)

    def test_a_no_answer_fails_the_image_and_the_step(self):
        self.start()
        self.prompts = self.order(count=1)
        self.assertEqual(self.step02().returncode, 0)
        self.to_step03()
        self.assertEqual(self.gate().returncode, 0)
        self.answers(1, answer="no")
        f = self.finish()
        self.assertNotEqual(f.returncode, 0)
        self.assertIn("did not pass the quality gate", f.stdout + f.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.wd, "saves", "final.png")))

    def test_a_flat_image_fails_the_mechanical_gate(self):
        self.start()
        self.prompts = self.order(count=1)
        self.assertEqual(self.step02().returncode, 0)
        self.to_step03()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x808080:s=1080x1080", "-frames:v", "1",
                        os.path.join(self.wd, "prior", "image_1.png")], check=True)
        # keep the recorded hash honest for this edit
        import hashlib
        meta = json.load(open(os.path.join(self.wd, "prior", "images.json")))
        meta["images"][0]["sha256"] = hashlib.sha256(open(os.path.join(self.wd, "prior", "image_1.png"), "rb").read()).hexdigest()
        write(os.path.join(self.wd, "prior", "images.json"), json.dumps(meta))
        g = self.gate()
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        self.assertEqual(open(os.path.join(self.wd, "work", "gate-status.txt")).read().split(), ["1", "1"])
        self.assertIn("FAIL frame_not_flat", g.stdout)


class ReferenceEndToEnd(Case):
    def test_reference_is_uploaded_and_sent_as_input_urls(self):
        self.start()
        self.prompts = self.order(count=1, aspect="16:9", reference=True)
        r = self.step02()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        uploads = [x for x in self.server.seen if x[1].startswith("/api/file-stream-upload")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0][2]["Authorization"], "Bearer " + KEY)
        body = json.loads(self.created()[0][3])
        self.assertEqual(body["model"], "gpt-image-2-image-to-image")
        self.assertEqual(body["input"]["resolution"], "2K")
        self.assertEqual(body["input"]["aspect_ratio"], "16:9")
        self.assertEqual(body["input"]["input_urls"], [self.server.url + "/files/ref.png"])
        self.assertEqual(dims(os.path.join(self.wd, "saves", "image_1.png")), (1920, 1080))
        # the reference was shrunk to a JPEG in the work folder and that file went out, not the original
        self.assertTrue(os.path.isfile(os.path.join(self.wd, "work", "ref-in.jpg")))

    def test_plan_and_reference_must_agree(self):
        self.start()
        self.prompts = self.order(count=1, reference=True, model="z-image")
        r = self.step02()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("did not choose the reference model", r.stdout + r.stderr)
        self.assertEqual(self.server.seen, [])

    def test_no_reference_with_the_reference_model_stops_before_any_call(self):
        self.start()
        self.prompts = self.order(count=1, model="gpt-image-2-image-to-image")
        r = self.step02()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.server.seen, [])


class FailuresAndTheKey(Case):
    def test_a_failed_task_is_not_repeated(self):
        self.start("fail")
        self.prompts = self.order(count=1)
        r = self.step02()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("IMAGE_FAILED", r.stdout + r.stderr)
        self.assertEqual(len(self.created()), 1, "the step must never start a second paid call")
        self.assertNotIn(KEY, self.all_text())

    def test_no_key_sends_nothing_and_says_so(self):
        self.start()
        self.prompts = self.order(count=1)
        setup = bash_block(STEP02, "### 0. Set up")
        r = self.sh(setup + "\n" + bash_block(STEP02, "### 1. Generate"), key=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no Kie key", r.stdout + r.stderr)
        self.assertEqual(self.server.seen, [])

    def test_the_key_is_in_no_output_file_stdout_or_stderr(self):
        self.start()
        self.prompts = self.order(count=2, reference=True)
        r = self.step02()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.to_step03()
        self.assertEqual(self.gate().returncode, 0)
        for n in (1, 2):
            self.answers(n)
        self.assertEqual(self.finish().returncode, 0)
        self.assertNotIn(KEY, self.all_text())

    def test_a_server_that_echoes_the_key_does_not_get_it_into_any_output(self):
        self.start("echo_key")
        self.prompts = self.order(count=1)
        r = self.step02()
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(KEY, self.all_text())

    def test_the_key_is_on_the_generate_command_only(self):
        """Every ffmpeg, ffprobe and python3 call is logged with whether it saw KIE_AI_API_KEY."""
        self.start()
        self.prompts = self.order(count=2, reference=True)
        r = self.step02(shim=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = [line.split("|", 2) for line in open(self.shim_log).read().splitlines()]
        with_key = [c for c in calls if c[1] == "KEY"]
        self.assertEqual(len(with_key), 2, with_key)                       # one generate call per image
        for name, _k, args in with_key:
            self.assertEqual(name, "python3")
            self.assertIn("b-kie-ai/scripts/generate.py", args)
        self.assertTrue([c for c in calls if c[0] == "ffmpeg"] and [c for c in calls if c[0] == "python3" and not c[1]])
        for name, _k, args in calls:                                       # every ffmpeg and ffprobe call blocks non-file input
            if name in ("ffmpeg", "ffprobe"):
                self.assertIn("-protocol_whitelist file", args)

    def test_the_reference_prep_command_whitelists_only_files(self):
        self.assertIn('ffmpeg -y -v error -protocol_whitelist file -i "$REF"', read(STEP02))

    def test_only_must_be_digits_and_within_the_batch(self):
        self.start()
        self.prompts = self.order(count=2)
        setup = bash_block(STEP02, "### 0. Set up")
        for bad in ("abc", "1;echo x", "$((1+1))", "0", "07", "3", "-1", " 1"):
            r = self.sh(setup, key=True, extra_env={"ONLY": bad})
            self.assertNotEqual(r.returncode, 0, repr(bad))
            self.assertIn("ONLY", r.stdout + r.stderr)
        self.assertEqual(self.sh(setup, key=True, extra_env={"ONLY": "2"}).returncode, 0)
        self.assertEqual(self.server.seen, [])

    def test_the_documented_text_commands_are_accepted_by_the_real_script(self):
        """Run the two documented command lines with --dry-run (nothing is sent)."""
        cmds = [b for b in text_blocks(STEP02) if "$GEN" in b]
        self.assertEqual(len(cmds), 2)
        os.makedirs(os.path.join(self.wd, "work"))
        write(os.path.join(self.wd, "work", "prompt-1.txt"), "a red cube on a table")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xc04040:s=32x32", "-frames:v", "1",
                        os.path.join(self.wd, "work", "ref-in.jpg")], check=True)
        for c in cmds:
            line = c.replace("work/prompt-N.txt", "work/prompt-1.txt").replace("raw-N.png", "raw-1.png")
            r = self.sh('GEN=%s; AR=9:16; %s --dry-run' % (REAL_GEN, line), key=True)
            self.assertEqual(r.returncode, 0, line + "\n" + r.stdout + r.stderr)
            self.assertIn("no request was sent", r.stdout)


class PlanSelfCheck(Case):
    """Step 01's own self-check block."""

    def run_check(self, prompts, reference=False):
        write(os.path.join(self.wd, "work", "prompts.json"), json.dumps(prompts))
        os.makedirs(os.path.join(self.wd, "saves"), exist_ok=True)
        if reference:
            write(os.path.join(self.wd, "inputs", "reference_image", "ref.png"), "x")
        return self.sh(bash_block(STEP01, "### 3. Write the save and self-check"))

    def plan(self, **kw):
        p = {"count": 1, "aspect_ratio": "1:1", "model": "z-image", "has_reference": False, "negative": "blurry",
             "images": [{"n": 1, "variant": "v", "prompt": "A calm red cube on a wooden table in soft morning light today."}]}
        p.update(kw)
        return p

    def test_a_good_plan_passes(self):
        r = self.run_check(self.plan())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.wd, "saves", "prompts.json")))

    def test_a_prompt_over_the_z_image_limit_is_refused(self):
        long = "A calm red cube on a wooden table in soft morning light. " * 20
        r = self.run_check(self.plan(images=[{"n": 1, "variant": "v", "prompt": long}]))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("takes at most 1000", r.stderr)

    def test_the_negative_list_counts_toward_the_limit(self):
        base = "A calm red cube on a wooden table in soft morning light. " * 16          # under 1000 alone
        self.assertLess(len(base), 1000)
        r = self.run_check(self.plan(negative="blurry " * 20, images=[{"n": 1, "variant": "v", "prompt": base}]))
        self.assertNotEqual(r.returncode, 0)

    def test_models_other_than_the_two_confirmed_ones_are_refused(self):
        for m in ("google/imagen4-fast", "seedream/4.5-text-to-image", "gpt-image-2-text-to-image"):
            r = self.run_check(self.plan(model=m))
            self.assertNotEqual(r.returncode, 0, m)

    def test_a_reference_needs_the_image_to_image_model(self):
        self.assertNotEqual(self.run_check(self.plan(has_reference=True), reference=True).returncode, 0)
        ok = self.plan(has_reference=True, model="gpt-image-2-image-to-image")
        self.assertEqual(self.run_check(ok, reference=True).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2, warnings="ignore")
