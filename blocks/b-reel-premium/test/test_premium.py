#!/usr/bin/env python3
"""Tests for b-reel-premium. They need Python 3.9 or newer, ffmpeg and ffprobe, and (for the page
checks) node. No network, no account, no private file. Run from the repository root:

  python3 -m unittest discover -s blocks/b-reel-premium/test -v

Work happens in temporary folders. A test whose tool is missing is reported as skipped, by name.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = os.path.dirname(HERE)
SCRIPTS = os.path.join(BLOCK, "scripts")
SFX = os.path.join(BLOCK, "assets", "sfx")
CHECK_LOCAL = os.path.join(os.path.dirname(BLOCK), "b-hyperframes", "scripts", "check_local.py")
sys.path.insert(0, SCRIPTS)
import plan_lib as pl  # noqa: E402

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
NODE = shutil.which("node")
NAMES = ["whoosh-deep", "whoosh-air", "impact-sub", "impact-punch", "riser", "click", "pop", "swipe"]


def run(script, args, cwd):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args, cwd=cwd,
                          capture_output=True, text=True, check=False)


def good_plan(**over):
    plan = {
        "grade": "clean-bright",
        "brand": {"accent": "#F97316", "fg": "#F1F5F9"},
        "caption_groups": [
            {"start": 0.0, "end": 1.0, "style": 0, "words": [
                {"w": "HELLO", "s": 0.1, "e": 0.4, "em": False}, {"w": "THERE", "s": 0.5, "e": 0.9, "em": True}]},
            {"start": 1.0, "end": 2.0, "style": 1, "words": [
                {"w": "SECOND", "s": 1.1, "e": 1.5, "em": False}, {"w": "GROUP", "s": 1.5, "e": 1.9, "em": False}]},
        ],
        "sfx": [{"t": 0.5, "name": "pop", "gain": 0.4}, {"t": 1.2, "name": "whoosh-air", "gain": 0.3}],
    }
    plan.update(over)
    return plan


class WorkDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = os.path.realpath(self.tmp.name)
        os.makedirs(os.path.join(self.work, "inputs"))

    def path(self, *parts):
        return os.path.join(self.work, *parts)

    def write_plan(self, plan, name="plan.json"):
        with open(self.path(name), "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        return name

    def check(self, plan, *extra, duration="2.0"):
        name = self.write_plan(plan)
        return run("check_plan.py", ["--plan", name, "--duration", duration] + list(extra), self.work)


class CheckPlan(WorkDir):
    def test_good_plan_passes(self):
        r = self.check(good_plan())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("premium plan OK", r.stdout)

    def test_colours_with_or_without_hash(self):
        r = self.check(good_plan(brand={"accent": "F97316", "fg": "#f1f5f9"}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_colours_are_refused(self):
        for bad in ("red", "#FFF", "#GGGGGG", "#F97316; x", "##F97316", "#F973160", 5, None, "url(x)"):
            with self.subTest(bad=bad):
                r = self.check(good_plan(brand={"accent": bad, "fg": "#FFFFFF"}))
                self.assertEqual(r.returncode, 1)
                self.assertIn("brand.accent", r.stderr)

    def test_unknown_sound_name_is_refused(self):
        for bad in ("boom", "../../etc/passwd", 'x"; rm -rf /', "pop.wav", "POP", "", None):
            with self.subTest(bad=bad):
                plan = good_plan(sfx=[{"t": 0.5, "name": bad, "gain": 0.3}])
                r = self.check(plan)
                self.assertEqual(r.returncode, 1)
                self.assertIn("sfx cue 0", r.stderr)

    def test_all_eight_names_are_accepted(self):
        plan = good_plan(sfx=[{"t": 0.1 * i, "name": n, "gain": 0.2} for i, n in enumerate(NAMES)])
        r = self.check(plan)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sfx_time_and_gain_limits(self):
        for bad in ({"t": 5, "name": "pop"}, {"t": -1, "name": "pop"}, {"t": 0.5, "name": "pop", "gain": 0.9},
                    {"t": "1", "name": "pop"}, {"t": 0.5, "name": "pop", "gain": -0.1}):
            with self.subTest(bad=bad):
                r = self.check(good_plan(sfx=[bad]))
                self.assertEqual(r.returncode, 1)

    def test_times_out_of_order(self):
        plan = good_plan()
        plan["caption_groups"].reverse()
        r = self.check(plan)
        self.assertEqual(r.returncode, 1)
        self.assertIn("in order", r.stderr)
        r = self.check(good_plan(sfx=[{"t": 1.5, "name": "pop"}, {"t": 0.5, "name": "pop"}]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("time order", r.stderr)
        plan = good_plan()
        plan["caption_groups"][0]["words"].reverse()
        self.assertEqual(self.check(plan).returncode, 1)
        plan = good_plan()
        plan["caption_groups"][0]["end"] = 0.0
        self.assertEqual(self.check(plan).returncode, 1)

    def test_captions_must_reach_the_end(self):
        r = self.check(good_plan(), duration="10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("end of the reel", r.stderr)
        r = self.check(good_plan(), "--cover-tolerance", "9", duration="10")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_and_missing_grade(self):
        r = self.check(good_plan(grade="sepia"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("grade", r.stderr)
        plan = good_plan()
        del plan["grade"]
        self.assertEqual(self.check(plan).returncode, 1)

    def test_every_problem_is_listed(self):
        plan = good_plan(grade="x", brand={"accent": "no", "fg": "no"}, sfx=[{"t": 0.5, "name": "bad"}])
        r = self.check(plan)
        self.assertEqual(r.returncode, 1)
        for needle in ("grade", "brand.accent", "brand.fg", "sfx cue 0"):
            self.assertIn(needle, r.stderr)

    def test_emphasis_style_and_length_limits(self):
        plan = good_plan()
        plan["caption_groups"][0]["words"][0]["em"] = True
        self.assertEqual(self.check(plan).returncode, 1)
        plan = good_plan()
        plan["caption_groups"][0]["style"] = 3
        self.assertEqual(self.check(plan).returncode, 1)
        plan = good_plan()
        plan["caption_groups"][0]["words"][0]["w"] = "X" * 41
        self.assertEqual(self.check(plan).returncode, 1)
        plan = good_plan()
        plan["caption_groups"][0]["words"][0]["w"] = "bad\x07"
        self.assertEqual(self.check(plan).returncode, 1)

    def test_latin_only_by_default(self):
        plan = good_plan()
        plan["caption_groups"][0]["words"][0]["w"] = "\u0928\u092e\u0938\u094d\u0924\u0947"
        self.assertEqual(self.check(plan).returncode, 1)
        self.assertEqual(self.check(plan, "--any-script").returncode, 0)

    def test_hostile_text_is_allowed_by_the_check_and_handled_by_the_page(self):
        plan = good_plan()
        plan["caption_groups"][0]["words"][0]["w"] = "<b>&"
        self.assertEqual(self.check(plan).returncode, 0)

    def test_captions_off_and_sfx_off(self):
        plan = good_plan(caption_groups=[], sfx=[{"t": 99, "name": "bad"}])
        self.assertEqual(self.check(plan).returncode, 1)
        self.assertEqual(self.check(plan, "--captions", "off", "--sfx", "off").returncode, 0)

    def test_bad_json_nan_and_usage(self):
        with open(self.path("bad.json"), "w") as fh:
            fh.write("{not json")
        r = run("check_plan.py", ["--plan", "bad.json", "--duration", "2"], self.work)
        self.assertEqual(r.returncode, 2)
        with open(self.path("nan.json"), "w") as fh:
            fh.write('{"grade": "off", "x": NaN}')
        r = run("check_plan.py", ["--plan", "nan.json", "--duration", "2"], self.work)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(run("check_plan.py", [], self.work).returncode, 2)
        self.assertEqual(run("check_plan.py", ["--plan", "x", "--duration", "2", "--nope"], self.work).returncode, 2)
        self.assertEqual(run("check_plan.py", ["--plan", "nofile.json", "--duration", "2"], self.work).returncode, 1)

    def test_plan_outside_workdir_is_refused(self):
        with tempfile.TemporaryDirectory() as other:
            p = os.path.join(other, "plan.json")
            with open(p, "w") as fh:
                json.dump(good_plan(), fh)
            r = run("check_plan.py", ["--plan", p, "--duration", "2"], self.work)
            self.assertEqual(r.returncode, 1)
            self.assertIn("outside the work folder", r.stderr)


class MusicPath(WorkDir):
    def music_plan(self, file):
        return good_plan(music={"file": file, "gain": 0.1})

    def test_inside_inputs_is_accepted(self):
        with open(self.path("inputs", "bed.mp3"), "wb") as fh:
            fh.write(b"x")
        self.assertEqual(self.check(self.music_plan("inputs/bed.mp3")).returncode, 0)

    def test_outside_inputs_is_refused(self):
        with open(self.path("other.mp3"), "wb") as fh:
            fh.write(b"x")
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = os.path.join(elsewhere, "bed.mp3")
            with open(outside, "wb") as fh:
                fh.write(b"x")
            for bad in ("other.mp3", "../bed.mp3", "inputs/../other.mp3", outside, "/etc/hosts", "inputs", "", None,
                        "inputs/missing.mp3", "inputs/\x00.mp3"):
                with self.subTest(bad=bad):
                    r = self.check(self.music_plan(bad))
                    self.assertEqual(r.returncode, 1, bad)
                    self.assertIn("music.file", r.stderr)
            # a symlink inside inputs that points outside is refused too
            os.symlink(outside, self.path("inputs", "link.mp3"))
            r = self.check(self.music_plan("inputs/link.mp3"))
            self.assertEqual(r.returncode, 1)

    def test_wrong_extension_and_gain(self):
        with open(self.path("inputs", "bed.txt"), "wb") as fh:
            fh.write(b"x")
        self.assertEqual(self.check(self.music_plan("inputs/bed.txt")).returncode, 1)
        with open(self.path("inputs", "bed.mp3"), "wb") as fh:
            fh.write(b"x")
        self.assertEqual(self.check(good_plan(music={"file": "inputs/bed.mp3", "gain": 0.9})).returncode, 1)


@unittest.skipUnless(NODE, "node is not installed: page checks skipped")
class BuildComp(WorkDir):
    def build(self, plan, cap_top="1180", extra=()):
        self.write_plan(plan)
        for name, data in (("reel.mp4", b"not a real video"), ("gsap.min.js", b"/* stand-in */")):
            with open(self.path(name), "wb") as fh:
                fh.write(data)
        return run("build_comp.py", ["--plan", "plan.json", "--reel", "reel.mp4", "--cap-top", cap_top,
                                     "--gsap", "gsap.min.js", "--outdir", "comp", "--duration", "2.0"] + list(extra), self.work)

    def pages(self):
        out = {}
        for rel in ("index.html", os.path.join("compositions", "caption-overlay.html")):
            with open(self.path("comp", rel), encoding="utf-8") as fh:
                out[rel] = fh.read()
        return out

    def groups_from_page(self, page):
        m = re.search(r"var GROUPS = (.*?);\n", page)
        self.assertIsNotNone(m)
        js = "console.log(JSON.stringify(%s))" % m.group(1)
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)

    def test_files_are_written_and_placeholders_filled(self):
        r = self.build(good_plan())
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in ("index.html", "gsap.min.js", os.path.join("compositions", "caption-overlay.html")):
            self.assertTrue(os.path.isfile(self.path("comp", rel)), rel)
        for name, page in self.pages().items():
            self.assertNotIn("{{", page, name)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        self.assertIn("top: 1180px;", cap)
        self.assertIn('var ACCENT = "#F97316";', cap)
        self.assertIn("color: #F1F5F9;", cap)

    HOSTILE = [
        "</script><script>alert(1)</script>", "<img src=x onerror=alert(1)>", '"; alert(1); "', "' onmouseover='x",
        "</SCRIPT >", "{{FG}}", "\u2028\u2029x", "a&b<c>d", "`${x}`", "\\", "</script", "<!--", "fetch(", "\U0001F600",
    ]

    def hostile_plan(self):
        groups = []
        for i, text in enumerate(self.HOSTILE):
            groups.append({"start": i * 0.1, "end": i * 0.1 + 0.1, "style": i % 3,
                           "words": [{"w": text[:40], "s": i * 0.1, "e": i * 0.1 + 0.05, "em": i % 2 == 0}]})
        groups[-1]["end"] = 2.0
        return good_plan(caption_groups=groups)

    def test_hostile_caption_text_never_becomes_markup_or_script(self):
        plan = self.hostile_plan()
        r = self.build(plan, extra=["--any-script"])
        self.assertEqual(r.returncode, 0, r.stderr)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        self.assertEqual(len(re.findall(r"</script", cap, re.I)), 2, "only the template's own two script tags")
        self.assertEqual(len(re.findall(r"<script", cap, re.I)), 2)
        for bad in ("onerror=", "onmouseover=", "<img", "alert(", "javascript:", "http:", "//evil", "fetch(", "@import"):
            self.assertNotIn(bad, cap, bad)
        # the text still arrives intact in the browser's data
        back = self.groups_from_page(cap)
        self.assertEqual([g["words"][0]["w"] for g in back], [t[:40] for t in self.HOSTILE])

    def test_the_filled_scripts_parse(self):
        self.assertEqual(self.build(self.hostile_plan(), extra=["--any-script"]).returncode, 0)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        bodies = re.findall(r"<script>(.*?)</script>", cap, re.S)
        self.assertEqual(len(bodies), 1)
        with open(self.path("body.js"), "w", encoding="utf-8") as fh:
            fh.write(bodies[0])
        r = subprocess.run(["node", "--check", self.path("body.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_filled_pages_hold_no_remote_address(self):
        self.assertEqual(self.build(self.hostile_plan(), extra=["--any-script"]).returncode, 0)
        remote = re.compile(r"(?i)(?:https?|wss?|ftp):|(?<![\w*])//|fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|@import|<iframe|<object|<embed|<base\b|http-equiv|javascript:")
        for name, page in self.pages().items():
            self.assertIsNone(remote.search(page), name)
            srcs = re.findall(r"(?i)\b(?:src|href)\s*=\s*[\"']?([^\"'\s>]+)", page)
            for s in srcs:
                self.assertIn(s, ("gsap.min.js", "compositions/caption-overlay.html"), s)
            self.assertNotRegex(page, r"(?i)url\(")

    def test_hostile_colours_and_numbers_are_refused_and_nothing_is_written(self):
        plan = good_plan(brand={"accent": "#F97316; } body { background: url(http://x)", "fg": "#FFFFFF"})
        r = self.build(plan)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(self.path("comp")))
        for bad in ("-1", "1921", "12px", "1e3", "x"):
            r = self.build(good_plan(), cap_top=bad)
            self.assertIn(r.returncode, (1, 2), bad)
            self.assertFalse(os.path.exists(self.path("comp")), bad)

    def test_outdir_gsap_and_reel_must_be_inside_the_work_folder(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            self.write_plan(good_plan())
            for name in ("reel.mp4", "gsap.min.js"):
                with open(self.path(name), "wb") as fh:
                    fh.write(b"x")
            outside = os.path.join(elsewhere, "g.js")
            with open(outside, "wb") as fh:
                fh.write(b"x")
            base = ["--plan", "plan.json", "--reel", "reel.mp4", "--cap-top", "1180", "--gsap", "gsap.min.js",
                    "--outdir", "comp", "--duration", "2"]
            for flag, value in (("--outdir", os.path.join(elsewhere, "comp")), ("--outdir", "../comp"), ("--outdir", "."),
                                ("--gsap", outside), ("--reel", outside)):
                args = list(base)
                args[args.index(flag) + 1] = value
                r = run("build_comp.py", args, self.work)
                self.assertEqual(r.returncode, 1, (flag, value))
            self.assertFalse(os.path.exists(os.path.join(elsewhere, "comp")))

    def local_check(self):
        r = subprocess.run([sys.executable, CHECK_LOCAL, "--comp", "comp", "--work", self.work], cwd=self.work,
                           capture_output=True, text=True)
        return r

    def test_normal_plan_passes_the_local_only_check(self):
        self.assertEqual(self.build(good_plan()).returncode, 0)
        r = self.local_check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LOCAL_ONLY: PASS", r.stdout)

    def test_hostile_plan_passes_the_local_only_check(self):
        self.assertEqual(self.build(self.hostile_plan(), extra=["--any-script"]).returncode, 0)
        r = self.local_check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LOCAL_ONLY: PASS", r.stdout)

    def make_font(self, name="inputs/brand.ttf", head=b"\x00\x01\x00\x00", size=64):
        with open(self.path(name), "wb") as fh:
            fh.write(head + b"\x00" * size)
        return name

    def test_plan_with_a_local_font_file_passes_the_local_only_check(self):
        brand = {"accent": "#F97316", "fg": "#FFFFFF", "font_file": self.make_font()}
        self.assertEqual(self.build(good_plan(brand=brand)).returncode, 0)
        self.assertTrue(os.path.isfile(self.path("comp", "fonts", "caption-font.ttf")))
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        self.assertIn('@font-face { font-family: "CaptionFont"; src: url("fonts/caption-font.ttf")', cap)
        r = self.local_check()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_a_font_file_only_a_generic_family_is_named(self):
        self.assertEqual(self.build(good_plan()).returncode, 0)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        self.assertIn("font-family: sans-serif;", cap)
        self.assertNotIn("Oswald", cap)
        self.assertFalse(os.path.exists(self.path("comp", "fonts")))

    def test_bad_font_files_are_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = os.path.join(elsewhere, "f.ttf")
            with open(outside, "wb") as fh:
                fh.write(b"\x00\x01\x00\x00" + b"\x00" * 8)
            self.make_font("other.ttf")
            self.make_font("inputs/note.txt")
            self.make_font("inputs/fake.ttf", head=b"<svg")
            self.make_font("inputs/big.otf", head=b"OTTO", size=3 * 1024 * 1024 + 1)
            for bad in (outside, "other.ttf", "../other.ttf", "inputs/note.txt", "inputs/fake.ttf", "inputs/big.otf",
                        "inputs/missing.ttf", "inputs", 7):
                with self.subTest(bad=bad):
                    r = self.build(good_plan(brand={"accent": "#F97316", "fg": "#FFFFFF", "font_file": bad}))
                    self.assertEqual(r.returncode, 1, bad)
                    self.assertIn("brand.font_file", r.stderr)
                    self.assertFalse(os.path.exists(self.path("comp")), bad)

    def test_default_gsap_is_vendor_gsap_min_js(self):
        self.write_plan(good_plan())
        os.makedirs(self.path("vendor"))
        with open(self.path("vendor", "gsap.min.js"), "wb") as fh:
            fh.write(b"/* stand-in */")
        with open(self.path("reel.mp4"), "wb") as fh:
            fh.write(b"x")
        r = run("build_comp.py", ["--plan", "plan.json", "--reel", "reel.mp4", "--cap-top", "1180", "--outdir", "comp",
                                  "--duration", "2.0"], self.work)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.path("comp", "gsap.min.js")))

    def test_planted_links_cannot_redirect_a_write_outside(self):
        for planted in ("index.html", "gsap.min.js", os.path.join("compositions", "caption-overlay.html"),
                        os.path.join("compositions", "gsap.min.js")):
            with self.subTest(planted=planted), tempfile.TemporaryDirectory() as elsewhere:
                victim = os.path.join(elsewhere, "victim.txt")
                with open(victim, "w") as fh:
                    fh.write("keep")
                shutil.rmtree(self.path("comp"), ignore_errors=True)
                os.makedirs(os.path.dirname(self.path("comp", planted)))
                os.symlink(victim, self.path("comp", planted))
                r = self.build(good_plan())
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("symbolic link", r.stderr)
                with open(victim) as fh:
                    self.assertEqual(fh.read(), "keep")
                self.assertEqual(os.listdir(elsewhere), ["victim.txt"])
                self.assertEqual([f for f in self.all_files("comp") if ".tmp-" in f], [])

    AWKWARD = ['"quoted"', "it's", "<b>", "a<b>c", "Tom&Jerry", "&amp;", "\U0001F600", "a/b", "1:2", "50%", "me@example.com",
               "example.com", "www.example.com/x", "C:", "10:30", "http", "data", "url", "{x}", "$5"]
    REFUSED = ["https://example.com/x", "//host/x", "javascript:alert(1)", "url(x)", "@import", "data:text/html,x",
               "ftp://x", "HTTP://X", "wss://x", "vbscript:x", "image-set(x)", "&#104;ttps://x", "htt&#x70;s:x",
               "\\u0068ttp://x", "h\\74tp://x", "h&#x74;tp&colon;//x", "a:   //x"]

    def words_plan(self, words, step=0.1):
        groups = [{"start": i * step, "end": i * step + step, "style": i % 3,
                   "words": [{"w": w, "s": i * step, "e": i * step + step / 2, "em": i % 2 == 0}]} for i, w in enumerate(words)]
        groups[-1]["end"] = 2.0
        return good_plan(caption_groups=groups)

    def test_awkward_but_harmless_words_are_accepted_and_pass_the_render_check(self):
        plan = self.words_plan(self.AWKWARD)
        name = self.write_plan(plan)
        r = run("check_plan.py", ["--plan", name, "--duration", "2.0"], self.work)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.build(plan).returncode, 0)
        r = self.local_check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LOCAL_ONLY: PASS", r.stdout)
        back = self.groups_from_page(self.pages()[os.path.join("compositions", "caption-overlay.html")])
        self.assertEqual([g["words"][0]["w"] for g in back], self.AWKWARD)

    def test_addresses_in_caption_text_are_refused_with_a_clear_message_and_nothing_is_written(self):
        for bad in self.REFUSED:
            with self.subTest(bad=bad):
                shutil.rmtree(self.path("comp"), ignore_errors=True)
                plan = self.words_plan(["fine", bad, "ok"])
                name = self.write_plan(plan)
                c = run("check_plan.py", ["--plan", name, "--duration", "2.0"], self.work)
                self.assertEqual(c.returncode, 1, bad)
                self.assertIn("caption group 1 word 0", c.stderr)
                self.assertRegex(c.stderr, r"write example\.com|leave the|write import|write the words")
                r = self.build(plan)
                self.assertEqual(r.returncode, 1, bad)
                self.assertIn("caption group 1 word 0", r.stderr)
                self.assertFalse(os.path.exists(self.path("comp")))

    def test_a_planted_link_stops_everything_before_any_file_is_written(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            victim = os.path.join(elsewhere, "victim.txt")
            with open(victim, "w") as fh:
                fh.write("keep")
            os.makedirs(self.path("comp"))
            os.symlink(victim, self.path("comp", "index.html"))
            r = self.build(good_plan())
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(os.listdir(self.path("comp")), ["index.html"])
            self.assertFalse(os.path.lexists(self.path("comp", "compositions")))
            with open(victim) as fh:
                self.assertEqual(fh.read(), "keep")
        # the same for a link planted in the last file written, and for a folder in a file's place
        os.unlink(self.path("comp", "index.html"))
        os.makedirs(self.path("comp", "fonts"))
        os.symlink(self.path("plan.json"), self.path("comp", "compositions.link"))
        os.makedirs(self.path("comp", "compositions", "gsap.min.js"))
        r = self.build(good_plan())
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertFalse(os.path.exists(self.path("comp", "index.html")))
        self.assertFalse(os.path.exists(self.path("comp", "compositions", "caption-overlay.html")))

    def all_files(self, rel):
        out = []
        for d, _, files in os.walk(self.path(rel)):
            out += [os.path.join(d, f) for f in files]
        return out

    def test_a_link_in_place_of_a_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            os.makedirs(self.path("comp"))
            os.symlink(elsewhere, self.path("comp", "compositions"))
            r = self.build(good_plan())
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(os.listdir(elsewhere), [])
            shutil.rmtree(self.path("comp"))
            os.symlink(elsewhere, self.path("comp"))
            r = self.build(good_plan())
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(os.listdir(elsewhere), [])
            os.unlink(self.path("comp"))
            os.makedirs(self.path("real"))
            os.symlink(self.path("real"), self.path("comp"))
            self.assertEqual(self.build(good_plan()).returncode, 1)
            self.assertEqual(os.listdir(self.path("real")), [])

    def test_an_output_equal_to_an_input_is_refused(self):
        self.write_plan(good_plan())
        os.makedirs(self.path("comp"))
        with open(self.path("comp", "gsap.min.js"), "wb") as fh:
            fh.write(b"input")
        with open(self.path("reel.mp4"), "wb") as fh:
            fh.write(b"x")
        r = run("build_comp.py", ["--plan", "plan.json", "--reel", "reel.mp4", "--cap-top", "1180",
                                  "--gsap", "comp/gsap.min.js", "--outdir", "comp", "--duration", "2"], self.work)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("also an input", r.stderr)
        with open(self.path("comp", "gsap.min.js"), "rb") as fh:
            self.assertEqual(fh.read(), b"input")

    def test_no_temporary_files_are_left_after_success(self):
        self.assertEqual(self.build(good_plan()).returncode, 0)
        self.assertEqual([f for f in self.all_files("comp") if ".tmp-" in f], [])

    def test_unexpected_errors_print_one_fixed_line_not_a_traceback(self):
        def boom(argv):
            raise ValueError("secret detail /private/path")
        import io
        err, old = io.StringIO(), sys.stderr
        sys.stderr = err
        try:
            code = pl.run_main(boom, "demo.py", [])
        finally:
            sys.stderr = old
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue().count("\n"), 1)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("secret", err.getvalue())

    def test_caption_timeline_is_written_out_without_loops(self):
        self.assertEqual(self.build(good_plan()).returncode, 0)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        self.assertNotRegex(cap, r"tl\.(?:to|fromTo|set)\((?:sel|wsel)\b")
        for needle in ('tl.fromTo("#cg-0"', 'tl.fromTo("#cg-1"', 'tl.to("#cw-0-0"', 'tl.set("#cg-1"'):
            self.assertIn(needle, cap)
        self.assertEqual(len(re.findall(r"tl\.fromTo\(\"#cg-", cap)), 2)

    SCRIPT_WORDS = ["innerHTML", "outerHTML", "DOMParser", "WebSocket", "XMLHttpRequest", "EventSource", "sendBeacon",
                    "importScripts", "serviceWorker", "insertAdjacentHTML", "createContextualFragment", "new Function",
                    "new Image", "Worker", "Function", "eval", "fetch", "import", "location", "document write",
                    "createElement", "setAttribute", "srcdoc"]

    def test_words_the_render_check_refuses_in_script_build_and_pass_the_check(self):
        plan = self.words_plan(self.SCRIPT_WORDS, step=0.08)
        name = self.write_plan(plan)
        c = run("check_plan.py", ["--plan", name, "--duration", "2.0"], self.work)
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertEqual(self.build(plan).returncode, 0)
        r = self.local_check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LOCAL_ONLY: PASS", r.stdout)
        cap = self.pages()[os.path.join("compositions", "caption-overlay.html")]
        for word in ("innerHTML", "WebSocket", "DOMParser", "fetch", "eval"):
            self.assertNotIn(word, cap.split("var GROUPS")[1].split("\n")[0], word)
        back = self.groups_from_page(cap)
        self.assertEqual([g["words"][0]["w"] for g in back], self.SCRIPT_WORDS)

    def test_the_root_page_has_no_video_and_a_transparent_background(self):
        self.assertEqual(self.build(good_plan()).returncode, 0)
        root = self.pages()["index.html"]
        self.assertNotIn("<video", root)
        self.assertNotIn("#000", root)
        self.assertFalse(os.path.exists(self.path("comp", "reel-in.mp4")))

    def test_templates_have_only_known_placeholders(self):
        known = {"DURATION", "CAP_TOP", "ACCENT", "FG", "GROUPS_JSON", "TIMELINE_JS", "FONT_FACE", "FONT_STACK", "FONT_NAME"}
        for name in ("caption-overlay.html", "root-shell-polish.html"):
            found = set(re.findall(r"\{\{([A-Z_]+)\}\}", pl.read_template(name)))
            self.assertTrue(found <= known, found - known)
        with self.assertRaises(pl.PlanError):
            pl.fill_template("{{NOPE}}", {})

    def test_script_json_properties(self):
        text = "<>&\"'/\\:;{}()`$\u2028\u2029\n\x00\u00e9\U0001F600 ok 9"
        out = pl.script_json({"w": text})
        self.assertRegex(out, r'^\{"w":"[A-Za-z0-9 \\]*"\}$')
        if NODE:
            r = subprocess.run(["node", "-e", "console.log(JSON.stringify(%s))" % out], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(r.stdout), {"w": text})


@unittest.skipUnless(FFMPEG, "ffmpeg and ffprobe are not installed: mix and qa tests skipped")
class Mix(WorkDir):
    def make_reel(self, name="reel.mp4", seconds=2, silent=True):
        src = "anullsrc=r=48000:cl=stereo" if silent else "sine=frequency=440:sample_rate=48000,aformat=channel_layouts=stereo"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=%d" % seconds,
                        "-f", "lavfi", "-i", src, "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", self.path(name)], check=True)
        return name

    def make_music(self, name="inputs/bed.wav"):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=3",
                        self.path(name)], check=True)
        return name

    def probe(self, name, entries):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", self.path(name)],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def max_volume(self, name):
        r = subprocess.run(["ffmpeg", "-nostdin", "-i", self.path(name), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
        return float(m.group(1)) if m else -91.0

    def mux(self, plan, *extra):
        self.write_plan(plan)
        return run("mux.py", ["--reel", "reel.mp4", "--no-captions", "--plan", "plan.json", "--out", "out/polished.mp4"] + list(extra), self.work)

    def test_mix_produces_a_real_audio_and_video_file_with_effects_audible(self):
        self.make_reel(silent=True)
        self.assertLess(self.max_volume("reel.mp4"), -80)
        r = self.mux(good_plan(grade="warm-amber"))
        self.assertEqual(r.returncode, 0, r.stderr)
        info = self.probe("out/polished.mp4", "stream=codec_type,codec_name,sample_rate,channels:format=duration")
        kinds = {s["codec_type"] for s in info["streams"]}
        self.assertEqual(kinds, {"video", "audio"})
        self.assertAlmostEqual(float(info["format"]["duration"]), 2.0, delta=0.15)
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
        self.assertEqual((audio["codec_name"], audio["sample_rate"], audio["channels"]), ("aac", "48000", 2))
        self.assertGreater(self.max_volume("out/polished.mp4"), -40, "the effects are in the mix")

    def test_every_sound_name_mixes(self):
        self.make_reel(silent=True)
        plan = good_plan(grade="off", sfx=[{"t": 0.1 * i, "name": n, "gain": 0.3} for i, n in enumerate(NAMES)])
        r = self.mux(plan)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_voice_level_is_not_changed_when_there_are_no_effects(self):
        self.make_reel(silent=False)
        before = self.max_volume("reel.mp4")
        r = self.mux(good_plan(grade="off", sfx=[]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertAlmostEqual(self.max_volume("out/polished.mp4"), before, delta=1.0)

    def test_sfx_off_ignores_the_cues(self):
        self.make_reel(silent=True)
        r = self.mux(good_plan(), "--sfx", "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(self.max_volume("out/polished.mp4"), -60)

    def test_music_inside_inputs_is_mixed(self):
        self.make_reel(silent=True)
        self.make_music()
        r = self.mux(good_plan(sfx=[], music={"file": "inputs/bed.wav", "gain": 0.2}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(self.max_volume("out/polished.mp4"), -40)

    def test_music_outside_inputs_is_refused_and_nothing_is_written(self):
        self.make_reel(silent=True)
        self.make_music("other.wav")
        for bad in ("other.wav", "../other.wav", "inputs/../other.wav"):
            r = self.mux(good_plan(music={"file": bad, "gain": 0.2}))
            self.assertEqual(r.returncode, 1, bad)
            self.assertFalse(os.path.exists(self.path("out")), bad)

    def test_bad_plan_is_refused_before_ffmpeg(self):
        self.make_reel()
        for plan in (good_plan(sfx=[{"t": 0.5, "name": 'x"; rm -rf /', "gain": 0.3}]), good_plan(grade="sepia"),
                     good_plan(sfx=[{"t": 0.5, "name": "pop", "gain": 5}]), good_plan(sfx=[{"t": 99, "name": "pop"}])):
            r = self.mux(plan)
            self.assertEqual(r.returncode, 1)
            self.assertFalse(os.path.exists(self.path("out")))

    def test_output_must_be_inside_the_work_folder(self):
        self.make_reel()
        self.write_plan(good_plan())
        with tempfile.TemporaryDirectory() as elsewhere:
            for out in (os.path.join(elsewhere, "x.mp4"), "../x.mp4", "reel.mp4", "out.txt"):
                r = run("mux.py", ["--reel", "reel.mp4", "--no-captions", "--plan", "plan.json", "--out", out], self.work)
                self.assertEqual(r.returncode, 1, out)
            self.assertEqual(os.listdir(elsewhere), [])

    def test_reel_without_audio_is_refused(self):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", self.path("reel.mp4")], check=True)
        r = self.mux(good_plan())
        self.assertEqual(r.returncode, 1)
        self.assertIn("no audio", r.stderr)

    def test_command_is_an_argument_list_with_only_block_sound_files(self):
        self.make_reel()
        self.make_music()
        r = self.mux(good_plan(music={"file": "inputs/bed.wav", "gain": 0.2}), "--print-command")
        self.assertEqual(r.returncode, 0, r.stderr)
        cmd = json.loads(r.stdout)
        self.assertEqual(cmd[0], "ffmpeg")
        inputs = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
        wavs = [p for p in inputs if p.startswith(SFX)]
        self.assertEqual(len(wavs), 2)
        self.assertEqual(sorted(os.path.basename(p) for p in wavs), ["pop.wav", "whoosh-air.wav"])
        self.assertIn(self.path("inputs", "bed.wav"), inputs)
        self.assertIn("normalize=0", " ".join(cmd))
        self.assertNotIn("loudnorm", " ".join(cmd))

    def test_a_symlinked_output_is_refused_and_nothing_is_written_through_it(self):
        self.make_reel()
        self.write_plan(good_plan())
        with tempfile.TemporaryDirectory() as elsewhere:
            victim = os.path.join(elsewhere, "victim.mp4")
            with open(victim, "w") as fh:
                fh.write("keep")
            inside_target = self.path("inside.mp4")
            with open(inside_target, "w") as fh:
                fh.write("keep")
            for target in (victim, inside_target):
                os.symlink(target, self.path("link.mp4"))
                r = run("mux.py", ["--reel", "reel.mp4", "--no-captions", "--plan", "plan.json", "--out", "link.mp4"], self.work)
                self.assertEqual(r.returncode, 1, r.stderr)
                with open(target) as fh:
                    self.assertEqual(fh.read(), "keep")
                os.unlink(self.path("link.mp4"))
            os.symlink(elsewhere, self.path("outlink"))
            r = run("mux.py", ["--reel", "reel.mp4", "--no-captions", "--plan", "plan.json", "--out", "outlink/x.mp4"], self.work)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(sorted(os.listdir(elsewhere)), ["victim.mp4"])

    def test_output_equal_to_any_input_is_refused(self):
        self.make_reel()
        self.make_music()
        self.write_plan(good_plan())
        for out in ("reel.mp4", "plan.json", "./reel.mp4"):
            r = run("mux.py", ["--reel", "reel.mp4", "--no-captions", "--plan", "plan.json", "--out", out], self.work)
            self.assertEqual(r.returncode, 1, out)

    def test_a_failed_mix_leaves_no_temporary_file(self):
        self.make_reel()
        with open(self.path("bad.mp4"), "wb") as fh:
            fh.write(b"not a video")
        self.write_plan(good_plan())
        os.makedirs(self.path("out"))
        r = run("mux.py", ["--reel", "reel.mp4", "--captions-mov", "bad.mp4", "--plan", "plan.json", "--out", "out/x.mp4"], self.work)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(os.listdir(self.path("out")), [])

    def test_successful_mix_leaves_only_the_output(self):
        self.make_reel()
        self.assertEqual(self.mux(good_plan()).returncode, 0)
        self.assertEqual(os.listdir(self.path("out")), ["polished.mp4"])

    def test_every_ffmpeg_input_has_a_protocol_whitelist(self):
        self.make_reel()
        self.make_music()
        r = self.mux(good_plan(music={"file": "inputs/bed.wav", "gain": 0.2}), "--print-command")
        cmd = json.loads(r.stdout)
        idx = [i for i, a in enumerate(cmd) if a == "-i"]
        self.assertGreaterEqual(len(idx), 4)
        for i in idx:
            self.assertIn(["-protocol_whitelist", "file"], [cmd[i - 4:i - 2], cmd[i - 2:i]])

    def make_audio(self, name, *args):
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=3"]
                           + list(args) + [self.path(name)], capture_output=True)
        return r.returncode == 0

    def test_music_must_be_a_plain_audio_file_in_a_named_format(self):
        self.make_reel()
        accepted = []
        for name, args in (("a.wav", []), ("a.flac", []), ("a.m4a", ["-c:a", "aac"]), ("a.ogg", ["-c:a", "libvorbis"]),
                           ("a.mp3", ["-c:a", "libmp3lame"])):
            if self.make_audio("inputs/" + name, *args):
                accepted.append(name)
        self.assertIn("a.wav", accepted)
        self.assertIn("a.m4a", accepted)
        for name in accepted:
            with self.subTest(good=name):
                r = self.mux(good_plan(sfx=[], music={"file": "inputs/" + name, "gain": 0.2}))
                self.assertEqual(r.returncode, 0, r.stderr)
        # refused: text named as audio, a video file named as audio, another audio format named as wav
        with open(self.path("inputs", "fake.wav"), "w") as fh:
            fh.write("this is not audio")
        shutil.copyfile(self.path("reel.mp4"), self.path("inputs", "video.mp3"))
        if self.make_audio("inputs/real.aiff", "-f", "aiff"):
            os.rename(self.path("inputs", "real.aiff"), self.path("inputs", "aiff-as.wav"))
        for bad in ("fake.wav", "video.mp3", "aiff-as.wav"):
            if not os.path.exists(self.path("inputs", bad)):
                continue
            with self.subTest(bad=bad):
                shutil.rmtree(self.path("out"), ignore_errors=True)
                r = self.mux(good_plan(sfx=[], music={"file": "inputs/" + bad, "gain": 0.2}))
                self.assertEqual(r.returncode, 1, bad)
                self.assertIn("music.file", r.stderr)
                self.assertFalse(os.path.exists(self.path("out")))

    def make_overlay(self, name="captions.mov", size="160x284", seconds=2, pix_fmt="yuva444p10le", colour="0xF97316", box=(40, 100, 120, 160)):
        """A transparent video: an opaque block of `colour` in the middle, nothing elsewhere."""
        w, h = size.split("x")
        rgb = int(colour, 16)
        src = ("color=c=black:s=%s:r=30:d=%d,format=rgba,geq=r=%d:g=%d:b=%d:a='if(between(X,%d,%d)*between(Y,%d,%d),255,0)'"
               % ((size, seconds, rgb >> 16, (rgb >> 8) & 255, rgb & 255, box[0], box[2], box[1], box[3])))
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-c:v", "prores_ks",
                            "-profile:v", "4444", "-pix_fmt", pix_fmt, self.path(name)], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return name

    def mux_overlay(self, plan, overlay="captions.mov", out="out/polished.mp4", *extra):
        self.write_plan(plan)
        return run("mux.py", ["--reel", "reel.mp4", "--captions-mov", overlay, "--plan", "plan.json", "--out", out] + list(extra), self.work)

    def test_inputs_must_hold_the_right_streams(self):
        self.make_reel()
        self.make_audio("audio-only.mp4", "-c:a", "aac")
        with open(self.path("text.mp4"), "w") as fh:
            fh.write("not a video")
        self.make_overlay("small.mov", size="80x142")
        self.make_overlay("opaque.mov", pix_fmt="yuv444p10le")
        self.make_overlay("ok.mov")
        for reel, cap, needle in (("audio-only.mp4", "ok.mov", "--reel"), ("text.mp4", "ok.mov", "not a readable"),
                                  ("reel.mp4", "small.mov", "same size"), ("reel.mp4", "opaque.mov", "no alpha"),
                                  ("reel.mp4", "text.mp4", "not a readable"), ("reel.mp4", "audio-only.mp4", "--captions-mov")):
            with self.subTest(reel=reel, cap=cap):
                self.write_plan(good_plan())
                r = run("mux.py", ["--reel", reel, "--captions-mov", cap, "--plan", "plan.json", "--out", "out/x.mp4"], self.work)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn(needle, r.stderr)
                self.assertFalse(os.path.exists(self.path("out")))

    def test_one_of_captions_mov_or_no_captions_is_required(self):
        self.make_reel()
        self.write_plan(good_plan())
        self.assertEqual(run("mux.py", ["--reel", "reel.mp4", "--plan", "plan.json", "--out", "out/x.mp4"], self.work).returncode, 2)
        self.make_overlay()
        r = run("mux.py", ["--reel", "reel.mp4", "--captions-mov", "captions.mov", "--no-captions", "--plan", "plan.json",
                           "--out", "out/x.mp4"], self.work)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(run("mux.py", ["--reel", "reel.mp4", "--visuals", "reel.mp4", "--plan", "plan.json", "--out", "x.mp4"], self.work).returncode, 2)

    def planes(self, name, t=1.0, size=(160, 284)):
        w, h = size
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(t), "-i", self.path(name), "-frames:v", "1",
                              "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"], capture_output=True).stdout
        return raw[:w * h], raw[w * h:w * h + (w // 2) * (h // 2)], raw[w * h + (w // 2) * (h // 2):], w

    def yuv_at(self, name, x, y):
        Y, U, V, w = self.planes(name)
        return Y[y * w + x], U[(y // 2) * (w // 2) + x // 2], V[(y // 2) * (w // 2) + x // 2]

    def test_grade_changes_the_footage_but_not_the_caption_colours(self):
        self.make_reel(silent=False)
        self.make_overlay()
        r0 = self.mux_overlay(good_plan(grade="off", sfx=[]), out="out/off.mp4")
        r1 = self.mux_overlay(good_plan(grade="warm-amber", sfx=[]), out="out/amber.mp4")
        self.assertEqual((r0.returncode, r1.returncode), (0, 0), r0.stderr + r1.stderr)
        foot_off, foot_amber = self.yuv_at("out/off.mp4", 10, 10), self.yuv_at("out/amber.mp4", 10, 10)
        self.assertGreater(max(abs(a - b) for a, b in zip(foot_off, foot_amber)), 4, "the grade changed the footage")
        cap_off, cap_amber = self.yuv_at("out/off.mp4", 80, 130), self.yuv_at("out/amber.mp4", 80, 130)
        for a, b in zip(cap_off, cap_amber):
            self.assertLessEqual(abs(a - b), 2, "caption colour is the same with and without a grade")

    def test_footage_colour_is_not_shifted_by_the_overlay(self):
        self.make_reel(silent=False)
        self.make_overlay(box=(70, 130, 76, 136))   # captions cover a few percent of a real frame, not a tenth
        self.assertEqual(self.mux_overlay(good_plan(grade="off", sfx=[])).returncode, 0)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "off"], self.work)
        self.assertEqual(q.returncode, 0, q.stderr)

    def test_qa_colour_check_catches_an_unplanned_grade(self):
        self.make_reel(silent=False)
        self.assertEqual(self.mux(good_plan(grade="warm-amber", sfx=[])).returncode, 0)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "off"], self.work)
        self.assertEqual(q.returncode, 1)
        self.assertIn("colour shifted", q.stderr)
        self.assertFalse(os.path.exists(self.path("out", ".gate")))
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "warm-amber"], self.work)
        self.assertEqual(q.returncode, 0, q.stderr)

    def test_qa_requires_the_grade_flag_and_records_it(self):
        self.make_reel()
        self.assertEqual(self.mux(good_plan()).returncode, 0)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa"], self.work)
        self.assertEqual(q.returncode, 2)
        self.assertFalse(os.path.exists(self.path("out", ".gate")))
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "clean-bright"], self.work)
        self.assertEqual(q.returncode, 0, q.stderr)
        with open(self.path("out", ".gate", "premium.json")) as fh:
            stamp = json.load(fh)
        self.assertEqual((stamp["grade"], stamp["colour_check"]), ("clean-bright", "skipped (a grade is applied)"))
        self.make_reel()
        self.assertEqual(self.mux(good_plan(grade="off", sfx=[]), "--sfx", "off").returncode, 0)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "off"], self.work)
        self.assertEqual(q.returncode, 0, q.stderr)
        with open(self.path("out", ".gate", "premium.json")) as fh:
            self.assertEqual(json.load(fh)["colour_check"], "ran")

    def test_inputs_are_opened_with_their_named_format(self):
        self.make_reel()
        self.make_music()
        self.make_overlay()
        r = self.mux_overlay(good_plan(music={"file": "inputs/bed.wav", "gain": 0.2}), "captions.mov", "out/x.mp4", "--print-command")
        cmd = json.loads(r.stdout)
        formats = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-f"]
        self.assertEqual([cmd[i - 2:i] for i, a in enumerate(cmd) if a == "-i"][0], ["-f", "mov"])
        for i, a in enumerate(cmd):
            if a == "-i":
                self.assertEqual(cmd[i - 2], "-f", cmd[i - 4:i + 2])
        self.assertIn("wav", formats)
        # and the real thing still works for plain mp4, a mov overlay and wav music
        r = self.mux_overlay(good_plan(music={"file": "inputs/bed.wav", "gain": 0.2}), "captions.mov")
        self.assertEqual(r.returncode, 0, r.stderr)

    def probe_format_name(self, name):
        out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=format_name", "-of", "csv=p=0",
                              "-i", self.path(name)], capture_output=True, text=True, check=True)
        return out.stdout.strip().strip('"')

    def test_every_accepted_format_works_end_to_end(self):
        self.make_reel()
        shutil.copyfile(self.path("reel.mp4"), self.path("reel.mov"))
        self.make_overlay("captions.mov")
        mov_family = "mov,mp4,m4a,3gp,3g2,mj2"
        for name in ("reel.mp4", "reel.mov", "captions.mov"):
            self.assertEqual(self.probe_format_name(name), mov_family, name)
        for name, args, probe_name in (("a.wav", [], "wav"), ("a.mp3", ["-c:a", "libmp3lame"], "mp3"), ("a.m4a", ["-c:a", "aac"], mov_family),
                                       ("a.aac", ["-c:a", "aac", "-f", "adts"], "aac"), ("a.flac", [], "flac"),
                                       ("a.ogg", ["-c:a", "libvorbis"], "ogg")):
            with self.subTest(music=name):
                if not self.make_audio("inputs/" + name, *args):
                    self.skipTest("this ffmpeg cannot make %s" % name)
                self.assertEqual(self.probe_format_name("inputs/" + name), probe_name)
                self.write_plan(good_plan(sfx=[], music={"file": "inputs/" + name, "gain": 0.2}))
                r = run("mux.py", ["--reel", "reel.mov", "--captions-mov", "captions.mov", "--plan", "plan.json", "--out", "out/%s.mp4" % name], self.work)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(os.path.exists(self.path("out", name + ".mp4")))

    def test_formats_outside_the_list_are_refused_not_guessed(self):
        self.make_reel()
        self.make_overlay("real-captions.mov")
        self.make_music("inputs/real.wav")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", self.path("reel.mp4"), "-c", "copy", "-f", "mpegts", self.path("seg.ts")], check=True)
        playlist = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:3\n#EXTINF:2.0,\nseg.ts\n#EXT-X-ENDLIST\n"
        concat = "ffconcat version 1.0\nfile reel.mp4\n"
        for kind, text, probe_name in (("playlist", playlist, "hls"), ("concat", concat, "concat")):
            for slot in ("reel", "captions", "music"):
                with self.subTest(kind=kind, slot=slot):
                    fake = "inputs/fake.wav" if slot == "music" else "fake-%s.mp4" % kind
                    with open(self.path(fake), "w", encoding="utf-8") as fh:
                        fh.write(text)
                    reel = fake if slot == "reel" else "reel.mp4"
                    caps = fake if slot == "captions" else "real-captions.mov"
                    music = {"file": fake if slot == "music" else "inputs/real.wav", "gain": 0.2}
                    self.write_plan(good_plan(sfx=[], music=music))
                    out = "out/%s-%s.mp4" % (kind, slot)
                    r = run("mux.py", ["--reel", reel, "--captions-mov", caps, "--plan", "plan.json", "--out", out], self.work)
                    self.assertEqual(r.returncode, 1, r.stderr)
                    self.assertFalse(os.path.exists(self.path(out)))
                    self.assertIn("problem(s)", r.stderr)   # one clear list of problems, not an ffmpeg dump
                    self.assertNotIn("Traceback", r.stderr)
        # ffprobe reads a concat text file, so the format helper itself must refuse it and name the format
        with open(self.path("list.mp4"), "w", encoding="utf-8") as fh:
            fh.write(concat)
        with self.assertRaises(pl.PlanError) as ctx:
            pl.input_format_args(self.path("list.mp4"), "--reel")
        self.assertIn("not accepted", ctx.exception.problems[0])
        self.assertIn("'concat'", ctx.exception.problems[0])
        # a playlist saved with an .mp4 name is not even readable as media
        with open(self.path("list2.mp4"), "w", encoding="utf-8") as fh:
            fh.write(playlist)
        with self.assertRaises(pl.PlanError):
            pl.input_format_args(self.path("list2.mp4"), "--reel")

    def test_a_symlinked_gate_folder_is_refused(self):
        self.make_reel()
        self.assertEqual(self.mux(good_plan()).returncode, 0)
        with tempfile.TemporaryDirectory() as elsewhere:
            os.symlink(elsewhere, self.path("out", ".gate"))
            q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "clean-bright"], self.work)
            self.assertEqual(q.returncode, 1, q.stderr)
            self.assertIn("symbolic link", q.stderr)
            self.assertEqual(os.listdir(elsewhere), [])

    def test_a_symlinked_stamp_or_frame_is_refused(self):
        self.make_reel()
        self.assertEqual(self.mux(good_plan()).returncode, 0)
        with tempfile.TemporaryDirectory() as elsewhere:
            victim = os.path.join(elsewhere, "victim")
            with open(victim, "w") as fh:
                fh.write("keep")
            os.makedirs(self.path("out", ".gate"))
            os.symlink(victim, self.path("out", ".gate", "premium.json"))
            q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "clean-bright"], self.work)
            self.assertEqual(q.returncode, 1, q.stderr)
            os.unlink(self.path("out", ".gate", "premium.json"))
            os.makedirs(self.path("out", "qa"), exist_ok=True)
            os.symlink(victim, self.path("out", "qa", "qa_35.png"))
            q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "clean-bright"], self.work)
            self.assertEqual(q.returncode, 1, q.stderr)
            with open(victim) as fh:
                self.assertEqual(fh.read(), "keep")
            self.assertEqual(os.listdir(elsewhere), ["victim"])
            self.assertEqual([f for f in os.listdir(self.path("out", "qa")) if f.startswith(".tmp-")], [])

    def test_qa_passes_and_stamps(self):
        self.make_reel()
        r = self.mux(good_plan())
        self.assertEqual(r.returncode, 0, r.stderr)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "out/polished.mp4", "--frames-dir", "out/qa", "--grade", "clean-bright"], self.work)
        self.assertEqual(q.returncode, 0, q.stderr)
        self.assertEqual(sorted(os.listdir(self.path("out", "qa"))), ["qa_10.png", "qa_35.png", "qa_60.png", "qa_85.png"])
        with open(self.path("out", ".gate", "premium.json")) as fh:
            self.assertEqual(json.load(fh)["by"], "b-reel-premium")

    def test_qa_fails_on_length_change_and_writes_no_stamp(self):
        self.make_reel()
        self.make_reel("short.mp4", seconds=1)
        q = run("qa.py", ["--reel-in", "reel.mp4", "--reel-out", "short.mp4", "--frames-dir", "qa", "--grade", "off"], self.work)
        self.assertEqual(q.returncode, 1)
        self.assertIn("length changed", q.stderr)
        self.assertFalse(os.path.exists(self.path(".gate")))


class Assets(unittest.TestCase):
    def test_exactly_eight_wavs_matching_the_sums_file(self):
        files = sorted(f for f in os.listdir(SFX) if f.endswith(".wav"))
        self.assertEqual(files, sorted(n + ".wav" for n in NAMES))
        self.assertEqual(sorted(pl.SFX_NAMES), sorted(NAMES))
        sums = {}
        with open(os.path.join(SFX, "SHA256SUMS")) as fh:
            for line in fh:
                digest, name = line.split()
                sums[name] = digest
        self.assertEqual(sorted(sums), files)
        for f in files:
            with open(os.path.join(SFX, f), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sums[f], f)

    def test_note_file_says_who_supplies_them(self):
        with open(os.path.join(SFX, "NOTE.txt")) as fh:
            text = fh.read()
        self.assertIn("supplied by the owner of this repository", text)
        self.assertIn("repository licence", text)

    def test_a_changed_sound_file_is_refused(self):
        import mux
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(SFX, os.path.join(d, "sfx"))
            with open(os.path.join(d, "sfx", "pop.wav"), "ab") as fh:
                fh.write(b"x")
            old = pl.SFX_DIR
            pl.SFX_DIR = os.path.join(d, "sfx")
            try:
                with self.assertRaises(pl.PlanError):
                    mux.sfx_path("pop")
                self.assertTrue(mux.sfx_path("click").endswith("click.wav"))
                with self.assertRaises(pl.PlanError):
                    mux.sfx_path("../pop")
            finally:
                pl.SFX_DIR = old

    def test_no_shell_no_generated_scripts_no_network_in_the_scripts(self):
        banned = re.compile(r"shell\s*=\s*True|os\.system|os\.popen|\bbash\b|\bsh -c|mux\.sh|urllib|requests|socket|http\.client|\beval\(|\bexec\(")
        for f in sorted(os.listdir(SCRIPTS)):
            if f.endswith(".py"):
                with open(os.path.join(SCRIPTS, f), encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIsNone(banned.search(text), f)
        self.assertEqual([f for f in os.listdir(SCRIPTS) if not f.endswith(".py") and f != "__pycache__"], [])

    def test_templates_load_only_the_local_animation_file(self):
        for name in ("caption-overlay.html", "root-shell-polish.html"):
            text = pl.read_template(name)
            self.assertEqual(re.findall(r"<script[^>]*\bsrc=\"([^\"]+)\"", text), ["gsap.min.js"])
            self.assertNotRegex(text, r"(?i)https?:|//")

    def test_the_hyperframes_block_is_present(self):
        self.assertTrue(os.path.isfile(CHECK_LOCAL), CHECK_LOCAL)


if __name__ == "__main__":
    unittest.main()
