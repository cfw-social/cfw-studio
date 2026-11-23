#!/usr/bin/env python3
"""Offline tests for the helper scripts in r-reels-faceless.

  python3 -I test/test_scripts.py -v        (from the recipe folder)

No network, no paid API, no server. Needs python3 and ffmpeg/ffprobe. Media are
small made-up clips made with ffmpeg in a temporary folder. Tests that use a block
(`../../blocks/b-broll-sync`, `b-typing-ui`, `b-hyperframes`, `b-qa-gate`) are skipped, by name,
when it is not there.
"""
import ast
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
BLOCKS = os.path.join(os.path.dirname(os.path.dirname(RECIPE)), "blocks")
STEPS = os.path.join(RECIPE, "steps")
SCRIPTS = os.path.join(RECIPE, "scripts")
FRAME_QA = os.path.join(SCRIPTS, "frame_qa.py")
HANDLE = "@" + "testbrand"
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
need_ffmpeg = unittest.skipUnless(HAVE_FFMPEG, "ffmpeg and ffprobe are not installed")


def block_dir(name):
    path = os.path.join(BLOCKS, name)
    if not os.path.isdir(path):
        raise unittest.SkipTest("block %s is not published yet (../../blocks/%s)" % (name, name))
    return path


def slurp(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def put(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jdump(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + list(args), check=True)


def qa(*args):
    return subprocess.run([sys.executable, "-I", FRAME_QA] + list(args), capture_output=True, text=True)


def script(name, *args, cwd=None):
    return subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, name)] + list(args),
                          capture_output=True, text=True, cwd=cwd)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,start_time,duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def rgb_at(path, t, crop="64:64:500:500"):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf",
                          "crop=%s,scale=1:1:flags=area,format=rgb24" % crop, "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    return tuple(out[:3])


def card_clip(path, dur, canvas="0xF4F4F4", ink="0x111111", late=0.0, faded=0.0, band=True):
    """A 1080x1920 card: canvas, a headline bar and a hero block (ink), a dark caption band.
    late: the headline and hero appear only `late` s in (an empty first frame).
    faded: for the first `faded` s the hero is drawn at 25 % strength."""
    when = "gte(t\\,%g)" % late if late else "1"
    hero_full = "gte(t\\,%g)" % faded if faded else "1"
    vf = ["drawbox=x=80:y=160:w=900:h=140:color=%s:t=fill:enable='%s'" % (ink, when),
          "drawbox=x=80:y=360:w=640:h=110:color=%s:t=fill:enable='%s'" % (ink, when),
          "drawbox=x=120:y=560:w=840:h=560:color=%s:t=fill:enable='%s*%s'" % (ink, when, hero_full)]
    if faded:
        vf.append("drawbox=x=120:y=560:w=840:h=560:color=%s@0.25:t=fill:enable='lt(t\\,%g)'" % (ink, faded))
    if band:
        vf.append("drawbox=x=0:y=1392:w=1080:h=528:color=0x111111:t=fill")
        vf.append("drawbox=x=420:y=1850:w=240:h=40:color=0xDDDDDD:t=fill")
    ff("-f", "lavfi", "-i", "color=c=%s:s=1080x1920:r=30:d=%g" % (canvas, dur), "-vf", ",".join(vf),
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path)


def concat(paths, out):
    folder = os.path.dirname(out)
    lines = []
    for index, path in enumerate(paths):
        name = "part-%04d.mp4" % index
        shutil.copy(path, os.path.join(folder, name))
        lines.append("file '%s'\n" % name)
    put(out + ".txt", "".join(lines))
    ff("-f", "concat", "-safe", "1", "-i", out + ".txt", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", out)


def beats_json(path, spans, types=None, slugs=None):
    beats, t = [], 0.0
    for i, s in enumerate(spans):
        typ = (types or ["standard"] * len(spans))[i]
        slug = (slugs or ["beat%d-s%d" % (j, j) for j in range(len(spans))])[i]
        beats.append({"index": i, "kind": "graphics", "slug": slug, "start": round(t, 3), "end": round(t + s, 3),
                      "scene": {"type": typ, "title_html": "LINE %d" % i, "source": "scene_plan"}})
        t += s
    jdump({"bed_duration": round(t, 3), "cover_at": 1.0, "beats": beats}, path)
    return beats


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="faceless-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@need_ffmpeg
class PictureCoversFile(Base):
    def test_av_span_flags_a_sound_tail(self):
        clip = os.path.join(self.tmp, "tail.mp4")
        ff("-f", "lavfi", "-i", "color=c=0xE0E0E0:s=1080x1920:r=30:d=2", "-f", "lavfi", "-i",
           "anullsrc=r=48000:cl=stereo", "-t", "2.3", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset",
           "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", clip)
        r = qa("av-span", clip)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("black tail", r.stdout)

    def test_av_target_pads_to_a_tenth_of_a_second(self):
        clip = os.path.join(self.tmp, "t.mp4")
        ff("-f", "lavfi", "-i", "color=c=0xE0E0E0:s=1080x1920:r=30:d=2.05", "-f", "lavfi", "-i",
           "anullsrc=r=48000:cl=stereo", "-t", "2.05", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset",
           "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", clip)
        r = qa("av-target", clip)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertAlmostEqual(float(r.stdout), 2.1, places=1)


class HyphenPhrase(Base):
    def test_validator_accepts_a_four_part_phrase_split_by_the_recogniser(self):
        validator = os.path.join(block_dir("b-broll-sync"), "scripts", "validate-scene-plan.js")
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        words = ["here", "is", "my", "four", "-part", "plan", "for", "a", "fast", "sale", "start", "with", "the",
                 "front", "door", "and", "book", "a", "call"]
        tw = os.path.join(self.tmp, "words.json")
        jdump([{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.45} for i, w in enumerate(words)], tw)
        sp = os.path.join(self.tmp, "plan.json")
        jdump({"version": 1, "scenes": [
            {"id": "hook", "kind": "graphic", "start": 0, "end_phrase": "four-part plan", "headline": "A"},
            {"id": "plan", "kind": "graphic", "start_phrase": "four-part plan", "end_phrase": "start with", "headline": "B"},
            {"id": "cta", "kind": "graphic", "start_phrase": "start with", "headline": "C", "type": "cta"}]}, sp)
        r = subprocess.run(["node", validator, "plan.json", "--bed-dur", str(len(words) * 0.5), "--transcript", "words.json"],
                           capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class CtaCopy(Base):
    def resolve(self, files, brand=None):
        wd = tempfile.mkdtemp(dir=self.tmp)
        os.makedirs(os.path.join(wd, "inputs"))
        if files:
            os.makedirs(os.path.join(wd, "inputs", "cta"))
            for name, body in files.items():
                put(os.path.join(wd, "inputs", "cta", name), body)
        jdump({"brand": brand or {"name": "Test Brand"}, "options": {}}, os.path.join(wd, "brief.json"))
        r = script("cta_copy.py", "resolve", "--out", "work/cta.json", cwd=wd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), jload(os.path.join(wd, "work", "cta.json")))   # stdout is JSON
        return wd, jload(os.path.join(wd, "work", "cta.json"))

    def test_typed_cta_md_is_read(self):
        _, d = self.resolve({"cta.md": "Book your free home audit today\n" + HANDLE + "\n"})
        self.assertEqual(d["text"], "Book your free home audit today")
        self.assertEqual(d["handle"], HANDLE)
        self.assertEqual(d["source"], "inputs/cta/cta.md")
        _, d = self.resolve({"cta.md": "Visit example.com/audit for a free check"})
        self.assertEqual(d["handle"], "example.com/audit")

    def test_cta_json_and_brand_fallback(self):
        _, d = self.resolve({"cta.json": json.dumps({"text": "Call us", "handle": HANDLE, "brandName": "TB"})})
        self.assertEqual((d["text"], d["handle"], d["brandName"]), ("Call us", HANDLE, "TB"))
        _, d = self.resolve(None)
        self.assertEqual((d["text"], d["handle"], d["brandName"], d["source"]), ("", "", "Test Brand", "none"))

    def test_hostile_text_stays_data(self):
        _, d = self.resolve({"cta.md": "Join now; $(touch pwned) `id` </script>\n"})
        self.assertIn("$(touch pwned)", d["text"])

    def test_end_card_check(self):
        wd, _ = self.resolve({"cta.md": "Book your free home audit today " + HANDLE})
        page = os.path.join(wd, "card.html")
        words = "".join("<span class=\"w\">%s</span> " % w.upper() for w in "Book your free home audit today".split())
        put(page, "<div class=\"hero\">%s</div><div class=\"handle\">%s</div>" % (words, html.escape(HANDLE)))
        cta = os.path.join(wd, "work", "cta.json")
        self.assertEqual(script("cta_copy.py", "check", "--cta", cta, "--html", page).returncode, 0)
        put(page, "<div class=\"hero\">%s</div>" % words)
        self.assertEqual(script("cta_copy.py", "check", "--cta", cta, "--html", page).returncode, 1)

    def plain(self, raw):
        sys.path.insert(0, SCRIPTS)
        try:
            import cta_copy
        finally:
            sys.path.pop(0)
        return cta_copy.from_plain(raw)

    def test_tech_words_and_email_domains_are_not_handles(self):
        for raw in ("Built with Node.js and Next.js", "Node.js", "Mail me@example.com today", "Edit server.py now"):
            self.assertEqual(self.plain(raw)["handle"], "", raw)
            self.assertEqual(self.plain(raw)["text"], raw)

    def test_real_handles_and_urls_still_work(self):
        for raw, want in (("Book now\n" + HANDLE, HANDLE), ("Follow " + HANDLE + "!", HANDLE),
                          ("Visit example.com/audit today", "example.com/audit"), ("brand.io", "brand.io"),
                          ("See https://example.com/a, thanks", "https://example.com/a"), ("Buy\nwww.example.com", "www.example.com")):
            self.assertEqual(self.plain(raw)["handle"], want, raw)

    def test_no_cta_means_no_handle_line(self):
        self.assertEqual(self.plain("")["handle"], "")


@need_ffmpeg
class FirstFrameWhole(Base):
    def test_empty_and_faded_first_frames_fail(self):
        clips = []
        for i, kw in enumerate(({}, {"late": 0.5}, {"faded": 0.4})):
            p = os.path.join(self.tmp, "c%d.mp4" % i)
            card_clip(p, 2.0, **kw)
            clips.append(p)
        body = os.path.join(self.tmp, "body.mp4")
        concat(clips, body)
        beats = os.path.join(self.tmp, "beats.json")
        beats_json(beats, [2.0, 2.0, 2.0], slugs=["beat0-whole", "beat1-empty", "beat2-faded"])
        r = qa("first-frames", body, beats, "--out", os.path.join(self.tmp, "first"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"PASS\s+beat0-whole")
        self.assertRegex(r.stdout, r"FAIL\s+beat1-empty")
        self.assertRegex(r.stdout, r"FAIL\s+beat2-faded")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "first", "first-beat1-empty.png")))
        cover = os.path.join(self.tmp, "cover.mp4")
        card_clip(cover, 0.4)
        outro = os.path.join(self.tmp, "outro.mp4")
        card_clip(outro, 1.5, canvas="0xE8E8E8")
        final = os.path.join(self.tmp, "final.mp4")
        concat([cover, clips[0], clips[0], clips[0], outro], final)
        r = qa("first-frames", final, beats, "--offset", "0.4", "--outro", "6.4")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stdout, r"PASS\s+outro")


@need_ffmpeg
class BottomBand(Base):
    """Every frame is scanned: the fault hit single frames and short runs, so a sample would miss it."""
    BAD = [7, 31] + list(range(70, 83)) + [150]

    def video(self, bad):
        enable = "+".join("eq(n\\,%d)" % f for f in bad) or "0"
        p = os.path.join(self.tmp, "band-%d.mp4" % len(bad))
        vf = ",".join([
            "drawbox=x=0:y=1392:w=1080:h=528:color=0x111111:t=fill",
            "drawbox=x=420:y=1850:w=240:h=40:color=0xDDDDDD:t=fill",
            "drawbox=x='40+mod(t*270\\,700)':y=500:w=300:h=300:color=0x3B82F6:t=fill",
            "drawbox=x=0:y=1832:w=1080:h=88:color=0xF4F4F4:t=fill:enable='%s'" % enable])
        ff("-f", "lavfi", "-i", "color=c=0xF4F4F4:s=1080x1920:r=30:d=6", "-vf", vf, "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", p)
        return p

    def test_scan_flags_exactly_the_dropped_frames(self):
        beats = os.path.join(self.tmp, "beats.json")
        beats_json(beats, [2.0, 2.0, 2.0])
        r = qa("band-scan", self.video(self.BAD), "--beats", beats)
        self.assertEqual(r.returncode, 1, r.stdout)
        got = [int(x) for x in re.findall(r"(\d+) \(\d+\.\d+s\)", r.stdout)]
        self.assertEqual(got, self.BAD)
        self.assertEqual(qa("band-scan", self.video([]), "--beats", beats).returncode, 0)


def step_python_blocks(name):
    return re.findall(r"```python\n(.*?)```", slurp(os.path.join(STEPS, name)), re.S)


class GradeRule(Base):
    def test_docs_say_clean_bright_is_the_default(self):
        self.assertIn("grade=clean-bright", slurp(os.path.join(STEPS, "_shared.md")))
        text = slurp(os.path.join(STEPS, "05-assemble.md"))
        self.assertIn("`clean-bright` (the default)", text)
        self.assertNotIn("warm-amber` by default", text)


class Palette(Base):
    def palette(self, pal):
        p = os.path.join(self.tmp, "brief.json")
        jdump({"brand": {"palette": pal} if pal is not None else {}}, p)
        out = os.path.join(self.tmp, "pal.json")
        r = script("brand_palette.py", "--brief", p, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(json.loads(r.stdout)), {"BG", "FG", "ACCENT", "BAND", "CAP_FG"})   # JSON, not shell text
        return jload(out)

    def test_three_colour_palette_gets_a_light_canvas_and_light_captions(self):
        d = self.palette({"accent": "#3B82F6", "primary": "#111111", "secondary": "#F4F4F4"})
        self.assertEqual((d["BG"], d["FG"], d["ACCENT"], d["BAND"], d["CAP_FG"]),
                         ("#F4F4F4", "#111111", "#3B82F6", "#111111", "#F4F4F4"))

    def test_default_explicit_and_near_black(self):
        d = self.palette(None)
        self.assertEqual((d["BG"], d["FG"], d["ACCENT"]), ("#0F172A", "#F1F5F9", "#F97316"))
        d = self.palette({"bg": "#0F172A", "fg": "#F1F5F9", "accent": "#F97316"})
        self.assertEqual((d["BG"], d["BAND"], d["CAP_FG"]), ("#0F172A", "#0F172A", "#F1F5F9"))
        d = self.palette({"bg": "#000000", "fg": "#FFFFFF", "accent": "#F97316"})
        r, g, b = (int(d["BG"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreaterEqual(0.299 * r + 0.587 * g + 0.114 * b, 24)

    def test_values_that_are_not_hex_colours_are_ignored(self):
        d = self.palette({"bg": "url(https://example.invalid/x)", "accent": "red;}</style>"})
        self.assertEqual((d["BG"], d["ACCENT"]), ("#0F172A", "#F97316"))


@need_ffmpeg
class CoverAndDrift(Base):
    def test_cover_pick_moves_off_a_dark_card(self):
        dark = os.path.join(self.tmp, "dark.mp4")
        ff("-f", "lavfi", "-i", "color=c=0x0B0B0B:s=1080x1920:r=30:d=2", "-vf",
           "drawbox=x=100:y=200:w=300:h=60:color=0xFFFFFF:t=fill", "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", dark)
        bright = os.path.join(self.tmp, "bright.mp4")
        card_clip(bright, 2.0)
        reel = os.path.join(self.tmp, "reel.mp4")
        concat([dark, dark, bright], reel)
        beats = os.path.join(self.tmp, "beats.json")
        beats_json(beats, [2.0, 2.0, 2.0], types=["hook", "standard", "standard"])
        r = qa("cover-pick", reel, beats, "--cover-at", "3.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreaterEqual(float(r.stdout), 4.0)
        self.assertEqual(float(qa("cover-pick", reel, beats, "--cover-at", "5.0").stdout), 5.0)

    def test_color_drift_measures_a_green_shift(self):
        a, b = os.path.join(self.tmp, "a.mp4"), os.path.join(self.tmp, "b.mp4")
        for p, c in ((a, "0xECEFEF"), (b, "0xE9F0EC")):
            ff("-f", "lavfi", "-i", "color=c=%s:s=1080x1920:r=30:d=1" % c, "-c:v", "libx264", "-preset", "ultrafast",
               "-pix_fmt", "yuv420p", p)
        self.assertEqual(qa("color-drift", a, b).returncode, 1)
        self.assertEqual(qa("color-drift", a, a).returncode, 0)

    def test_luma_floor_and_tail_luma_fail_a_black_reel(self):
        black = os.path.join(self.tmp, "black.mp4")
        ff("-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=2", "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", black)
        self.assertEqual(qa("luma-floor", black, "--floor", "16").returncode, 1)
        self.assertEqual(qa("tail-luma", black, "--min", "30").returncode, 1)


HEAD = ('Three <span class="accent">checks</span> before you ship')


def beat(kind, **scene):
    scene.setdefault("title_html", HEAD)
    return {"beats": [{"index": 0, "kind": "graphics", "slug": "beat0-x", "start": 0, "end": 4,
                       "scene": dict(scene, type=kind)}]}


PALETTE = {"BG": "#0F172A", "FG": "#F1F5F9", "ACCENT": "#F97316", "BAND": "#0F172A", "CAP_FG": "#F1F5F9"}
HERO_FIELDS = {"standard": {}, "hook": {}, "stat": {"stat": "10", "unit": "minutes"},
               "chips": {"chips": ["one", "two", "three"]}, "flow": {"flow": ["Write", "Test", "Ship"]},
               "checklist": {"items": ["Run the tests", "Read the diff"]}, "terminal": {"lines": ["npm test", "all passed"]},
               "cta": {}}


class CardFill(Base):
    def fill(self, beats, cta=None, extra=(), name="index.html"):
        jdump(beats, os.path.join(self.tmp, "beats.json"))
        jdump(PALETTE, os.path.join(self.tmp, "pal.json"))
        args = ["--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out", "comp/" + name]
        if cta is not None:
            jdump(cta, os.path.join(self.tmp, "cta.json"))
            args += ["--cta", "cta.json"]
        return script("card_fill.py", *(args + list(extra)), cwd=self.tmp)

    def check_local(self):
        """b-hyperframes' local-only check on the filled page, with a stand-in animation library."""
        checker = os.path.join(block_dir("b-hyperframes"), "scripts", "check_local.py")
        put(os.path.join(self.tmp, "comp", "gsap.min.js"), "/* stand-in for the animation library */\n")
        return subprocess.run([sys.executable, "-I", checker, "--comp", "comp"], cwd=self.tmp, capture_output=True, text=True)

    def test_every_card_type_fills_and_passes_the_local_only_check(self):
        for kind, fields in HERO_FIELDS.items():
            r = self.fill(beat(kind, **fields), cta={"text": "Comment GUIDE", "handle": HANDLE})
            self.assertEqual(r.returncode, 0, kind + r.stderr)
            page = slurp(os.path.join(self.tmp, "comp", "index.html"))
            self.assertNotRegex(page, r"\{\{[A-Z_]+\}\}", kind)
            self.assertIn('data-card-type="%s"' % kind, page)
            self.assertIn('data-composition-id="main"', page)
            self.assertIn('window.__timelines["main"]', page)
            c = self.check_local()
            self.assertEqual(c.returncode, 0, "%s: %s%s" % (kind, c.stdout, c.stderr))

    def test_hostile_text_stays_inert_in_every_field(self):
        evil = '</script><img src=x onerror=alert(1)> "q" \\ {{DURATION}} example.invalid/x @h $(id) \u2028'
        scene = {"eyebrow": evil[:40], "ghost": "<b>", "sub": evil, "title_html": 'A <span class="accent">%s</span>' % evil[:30].replace("<", "x"),
                 "chips": [evil[:24], "b"], "items": [evil[:50], "b"], "flow": [evil[:20], "b"], "lines": [evil[:50]], "stat": "<9>", "unit": evil[:14]}
        for kind in ("chips", "checklist", "flow", "terminal", "stat", "standard"):
            r = self.fill(beat(kind, **scene), cta={"handle": "@x"})
            self.assertEqual(r.returncode, 0, kind + r.stderr)
            page = slurp(os.path.join(self.tmp, "comp", "index.html"))
            body = page[page.index('<div id="root"'):]
            self.assertEqual(body.count("</script>"), 2, kind)          # the library and the timeline, nothing more
            self.assertNotRegex(body.lower(), r"<[^>]*onerror")
            self.assertNotIn("example.invalid", page)
            self.assertNotRegex(body, r"<img", kind)
            self.assertEqual(body.count("{{"), 0, kind)
            c = self.check_local()
            self.assertEqual(c.returncode, 0, "%s: %s%s" % (kind, c.stdout, c.stderr))

    def test_refusals_name_the_reason_and_write_nothing(self):
        cases = {"markup in the headline": beat("standard", title_html="<b>hi</b>"),
                 "script in the headline": beat("standard", title_html="<script>x</script>"),
                 "blank headline": beat("standard", title_html=" <br> "),
                 "headline too long": beat("standard", title_html="x" * 91),
                 "placeholder ghost": beat("standard", ghost="CTA"),
                 "unknown type": beat("spinner"),
                 "typing is not filled here": beat("typing", prompt="hi"),
                 "no chips": beat("chips"), "one flow step": beat("flow", flow=["a"]),
                 "no stat": beat("stat"), "too many items": beat("checklist", items=["a"] * 7),
                 "non-text field": beat("standard", sub=5),
                 "address in the headline": beat("standard", title_html="See https://example.com now"),
                 "script address in sub": beat("standard", sub="javascript:alert(1)"),
                 "css url in a chip": beat("chips", chips=["url(x)", "b"]),
                 "protocol-relative in a step": beat("flow", flow=["a", "go to //evil.example"])}
        for label, beats in cases.items():
            r = self.fill(beats, name="refused.html")
            self.assertEqual(r.returncode, 2, label + r.stdout)
            self.assertIn("FAILED", r.stderr, label)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "comp", "refused.html")), label)
        bad = beat("standard")
        bad["beats"][0]["end"] = 0.1
        self.assertEqual(self.fill(bad, name="refused.html").returncode, 2)

    def test_colours_fonts_and_paths_are_checked(self):
        jdump(beat("standard"), os.path.join(self.tmp, "beats.json"))
        jdump(dict(PALETTE, ACCENT="red;}</style>"), os.path.join(self.tmp, "pal.json"))
        r = script("card_fill.py", "--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out", "o.html", cwd=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.fill(beat("standard"), extra=["--display-font", 'X"; } body{display:none}']).returncode, 2)
        ok = self.fill(beat("standard"), extra=["--display-font", "Example Sans", "--body-font", "Example Text"])
        self.assertEqual(ok.returncode, 0, ok.stderr)
        page = slurp(os.path.join(self.tmp, "comp", "index.html"))
        self.assertIn('@font-face { font-family: "Example Sans"; src: local("Example Sans"); }', page)
        self.assertEqual(self.check_local().returncode, 0)
        outside = tempfile.mkdtemp()
        try:
            r = script("card_fill.py", "--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out",
                       os.path.join(outside, "o.html"), cwd=self.tmp)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(outside, "o.html")))
            os.symlink(os.path.join(outside, "target.html"), os.path.join(self.tmp, "link.html"))
            jdump(PALETTE, os.path.join(self.tmp, "pal.json"))
            r = script("card_fill.py", "--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out", "link.html", cwd=self.tmp)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(outside, "target.html")))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_the_folder_is_checked_before_it_is_made(self):
        jdump(beat("standard"), os.path.join(self.tmp, "beats.json"))
        jdump(PALETTE, os.path.join(self.tmp, "pal.json"))
        outside = tempfile.mkdtemp()
        try:
            target = os.path.join(outside, "made", "deeper", "o.html")
            r = script("card_fill.py", "--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out", target, cwd=self.tmp)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertFalse(os.path.exists(os.path.join(outside, "made")), "the folder must not be created")
            os.symlink(outside, os.path.join(self.tmp, "linkdir"))
            r = script("card_fill.py", "--beats", "beats.json", "--index", "0", "--palette", "pal.json", "--out", "linkdir/new/o.html", cwd=self.tmp)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(outside, "new")))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_cta_card_shows_the_exact_handle_and_none_when_absent(self):
        r = self.fill(beat("cta", title_html="Comment GUIDE"), cta={"handle": HANDLE})
        self.assertEqual(r.returncode, 0, r.stderr)
        page = os.path.join(self.tmp, "comp", "index.html")
        cta = os.path.join(self.tmp, "cta.json")
        jdump({"text": "Comment GUIDE", "handle": HANDLE}, cta)
        self.assertEqual(script("cta_copy.py", "check", "--cta", cta, "--html", page).returncode, 0)
        r = self.fill(beat("cta", title_html="Comment GUIDE"), cta={"handle": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('class="btn', slurp(page))

    def test_the_template_keeps_the_first_frame_whole(self):
        template = slurp(os.path.join(os.path.dirname(SCRIPTS), "templates", "card.html"))
        self.assertRegex(template, r'tl\.from\("#headline", \{ y: 48')
        headline_tween = re.search(r'tl\.from\("#headline"[^;]*;', template).group(0)
        self.assertNotIn("opacity", headline_tween)
        self.assertNotIn("repeat: -1", template)
        self.assertNotIn("innerHTML", template)


class BlockFillers(Base):
    """The block fillers the steps call, run exactly as the step writes them, then the local-only check."""

    def run_block(self, name, args):
        return subprocess.run([sys.executable, "-I", os.path.join(block_dir("b-typing-ui"), "scripts", name)] + args,
                              cwd=self.tmp, capture_output=True, text=True)

    def test_hook_and_typing_cards_with_hostile_text_pass_the_local_only_check(self):
        checker = os.path.join(block_dir("b-hyperframes"), "scripts", "check_local.py")
        evil = '</script><b>x</b> "q" \\ example.invalid/a {{DURATION}}'
        jdump({"eyebrow": evil[:40], "line1": evil[:40], "line2": "two", "line3": "", "subhead": evil[:60]}, os.path.join(self.tmp, "hook.json"))
        jdump({"prompt": evil + "\nline two", "label": "AI chat", "card_label": "The prompt", "bottom_tag": evil[:20]},
              os.path.join(self.tmp, "typing.json"))
        for name, args, out in (("hook_fill.py", ["--duration", "3", "--text-file", "hook.json", "--accent", "F97316", "--bg", "0F172A", "--fg", "F1F5F9"], "hook"),
                                ("typing_fill.py", ["--duration", "5", "--text-file", "typing.json", "--accent", "F97316", "--bg", "0F172A", "--fg", "F1F5F9"], "typing")):
            os.makedirs(os.path.join(self.tmp, out), exist_ok=True)
            put(os.path.join(self.tmp, out, "gsap.min.js"), "/* stand-in */\n")
            r = self.run_block(name, ["--out", out + "/index.html"] + args)
            self.assertEqual(r.returncode, 0, r.stderr)
            c = subprocess.run([sys.executable, "-I", checker, "--comp", out], cwd=self.tmp, capture_output=True, text=True)
            self.assertEqual(c.returncode, 0, c.stdout + c.stderr)

    def test_block_fillers_refuse_an_address_in_the_text(self):
        jdump({"prompt": "see https://example.com"}, os.path.join(self.tmp, "typing.json"))
        r = self.run_block("typing_fill.py", ["--out", "t.html", "--duration", "5", "--text-file", "typing.json",
                                              "--accent", "F97316"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "t.html")))

    def test_low_contrast_colours_are_refused(self):
        jdump({"line1": "Hello"}, os.path.join(self.tmp, "hook.json"))
        r = self.run_block("hook_fill.py", ["--out", "h.html", "--duration", "3", "--text-file", "hook.json",
                                            "--accent", "F97316", "--bg", "F1F5F9", "--fg", "FFFFFF"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_the_step_names_the_block_flags_that_exist(self):
        text = slurp(os.path.join(STEPS, "04-render-graphics.md"))
        for name in ("hook_fill.py", "typing_fill.py"):
            help_text = self.run_block(name, ["--help"]).stdout
            line = next(l for l in text.splitlines() if name in l and l.startswith("python3"))
            for flag in re.findall(r"(--[a-z-]+)", line):
                self.assertIn(flag, help_text, "%s does not take %s" % (name, flag))


@need_ffmpeg
class AcceptanceSpec(Base):
    """The recipe's acceptance.json must use only kinds b-qa-gate owns, or the perceptual kind."""

    def test_the_real_gate_knows_every_kind_in_the_spec(self):
        gate = os.path.join(block_dir("b-qa-gate"), "check.py")
        spec = jload(os.path.join(RECIPE, "acceptance.json"))
        kinds = {c["type"] for c in spec["checks"]} | {c["type"] for st in spec["steps"].values() for c in st["checks"]}
        self.assertTrue(kinds <= {"qa_gate", "duration_window", "dims", "luma_floor", "contrast_floor", "loudness", "mean_volume",
                                  "perceptual"}, kinds)
        clip = os.path.join(self.tmp, "final.mp4")
        ff("-f", "lavfi", "-i", "color=c=0xE0E0E0:s=1080x1920:r=30:d=5", "-f", "lavfi", "-i", "sine=f=220:d=5", "-af",
           "tremolo=f=3:d=0.7,volume=0.2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", clip)
        out = os.path.join(self.tmp, "scorecard.json")
        r = subprocess.run([sys.executable, "-I", gate, "--kind", "reel", "--spec", os.path.join(RECIPE, "acceptance.json"),
                            "--input", "final.mp4", "--out", "scorecard.json"], cwd=self.tmp, capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 1, 4), r.stdout + r.stderr)            # 1 is expected: 5 s is under the 30 s window
        card = jload(out)
        for row in card["checks"]:
            self.assertNotIn("not supported", row["detail"], row)
            self.assertNotIn("not known", row["detail"], row)
        ids = {row["id"] for row in card["checks"]}
        self.assertTrue({"qa_gate.video", "qa_gate.loudness", "qa_gate.cover", "duration_window", "canvas_1080x1920"} <= ids, ids)
        looks = [row for row in card["checks"] if row["status"] == "LOOK"]
        self.assertEqual(len(looks), sum(1 for c in spec["checks"] if c["type"] == "perceptual"))
        self.assertTrue(all(row.get("question") for row in looks))
        duration = next(row for row in card["checks"] if row["id"] == "duration_window")
        self.assertEqual(duration["status"], "FAIL")                           # the 30 to 90 s window is enforced

    def test_the_qa_gate_note_says_it_is_the_mechanical_floor(self):
        spec = jload(os.path.join(RECIPE, "acceptance.json"))
        note = next(c for c in spec["checks"] if c["id"] == "qa_gate")["_note"]
        self.assertIn("mechanical", note)
        self.assertIn("not an aggregate", note)

    def test_voicebed_and_assembled_steps_run_on_stand_in_files(self):
        gate = os.path.join(block_dir("b-qa-gate"), "check.py")
        gate_run = lambda: subprocess.run([sys.executable, "-I", gate, "--kind", "reel", "--spec", os.path.join(RECIPE, "acceptance.json"),
                                           "--step", "voicebed", "--input", "vo.wav", "--out", "vo-card.json"], cwd=self.tmp,
                                          capture_output=True, text=True)
        ff("-f", "lavfi", "-i", "sine=f=220:d=29.2", "-af", "tremolo=f=3:d=0.7,loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
           os.path.join(self.tmp, "vo.wav"))
        r = gate_run()
        self.assertEqual(r.returncode, 1, "a 29.2 s voice bed must fail: " + r.stdout)
        self.assertIn("vo_duration_window", r.stdout)
        ff("-f", "lavfi", "-i", "sine=f=220:d=31", "-af", "tremolo=f=3:d=0.7,loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
           os.path.join(self.tmp, "vo.wav"))
        r = gate_run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        card_clip(os.path.join(self.tmp, "body.mp4"), 2.0)
        r = subprocess.run([sys.executable, "-I", gate, "--kind", "reel", "--spec", os.path.join(RECIPE, "acceptance.json"), "--step",
                            "assembled", "--input", "body.mp4", "--out", "body-card.json"], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@need_ffmpeg
class BandScanSkipsBroll(Base):
    def test_skip_broll_leaves_moving_footage_alone(self):
        p = os.path.join(self.tmp, "mixed.mp4")
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", p)
        beats = os.path.join(self.tmp, "beats.json")
        jdump({"bed_duration": 4, "beats": [{"index": 0, "kind": "broll", "start": 0, "end": 4,
                                              "broll": {"clip": "x", "in": 0, "out": 4}}]}, beats)
        self.assertEqual(qa("band-scan", p, "--beats", beats, "--skip-broll").returncode, 0)


@need_ffmpeg
class Segments(Base):
    def setUp(self):
        super().setUp()
        for d in ("work/seg", "inputs/broll", "saves"):
            os.makedirs(os.path.join(self.tmp, d))
        ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           os.path.join(self.tmp, "inputs/broll/a.mp4"))
        card_clip(os.path.join(self.tmp, "work/seg/gfx-beat0-hook.mp4"), 2.0)
        card_clip(os.path.join(self.tmp, "work/seg/gfx-beat2-cta.mp4"), 1.5)
        jdump({"bed_duration": 5, "beats": [
            {"index": 0, "kind": "graphics", "slug": "beat0-hook", "start": 0, "end": 2, "scene": {"title_html": "A", "type": "hook"}},
            {"index": 1, "kind": "broll", "start": 2, "end": 3.5, "broll": {"clip": "inputs/broll/a.mp4", "in": 0.5, "out": 2}},
            {"index": 2, "kind": "graphics", "slug": "beat2-cta", "start": 3.5, "end": 5, "scene": {"title_html": "B", "type": "cta"}}]},
            os.path.join(self.tmp, "beat_list.json"))

    def test_segments_are_named_by_beat_index_and_joined(self):
        r = script("segments.py", "--beats", "beat_list.json", "--bed-duration", "5", "--out", "saves/body_video.mp4", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "work/seg")) ),
                         sorted(["gfx-beat0-hook.mp4", "gfx-beat2-cta.mp4", "seg-0000.mp4", "seg-0001.mp4", "seg-0002.mp4", "concat.txt"]))
        self.assertEqual(slurp(os.path.join(self.tmp, "work/seg/concat.txt")),
                         "file 'seg-0000.mp4'\nfile 'seg-0001.mp4'\nfile 'seg-0002.mp4'\n")
        info = probe(os.path.join(self.tmp, "saves/body_video.mp4"))
        self.assertAlmostEqual(float(info["format"]["duration"]), 5.0, delta=0.15)
        size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0",
                               os.path.join(self.tmp, "saves/body_video.mp4")], capture_output=True, text=True).stdout.strip()
        self.assertEqual(size, "1080,1920,30/1")

    def test_missing_page_clip_outside_inputs_and_bad_paths_are_refused(self):
        os.remove(os.path.join(self.tmp, "work/seg/gfx-beat2-cta.mp4"))
        r = script("segments.py", "--beats", "beat_list.json", "--bed-duration", "5", "--out", "saves/body_video.mp4", cwd=self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "saves/body_video.mp4")))
        beats = jload(os.path.join(self.tmp, "beat_list.json"))
        beats["beats"][1]["broll"]["clip"] = "../a.mp4"
        jdump(beats, os.path.join(self.tmp, "beat_list.json"))
        self.assertEqual(script("segments.py", "--beats", "beat_list.json", "--bed-duration", "5", "--out", "saves/b.mp4", cwd=self.tmp).returncode, 1)
        self.assertEqual(script("segments.py", "--beats", "beat_list.json", "--bed-duration", "5", "--out", "/tmp/x.mp4", cwd=self.tmp).returncode, 2)


@need_ffmpeg
class SegmentsSymlinks(Base):
    def test_planted_links_are_refused_and_nothing_is_written_through_them(self):
        for d in ("work/seg", "inputs/broll", "saves"):
            os.makedirs(os.path.join(self.tmp, d))
        card_clip(os.path.join(self.tmp, "work/seg/gfx-beat0-a.mp4"), 1.0)
        card_clip(os.path.join(self.tmp, "work/seg/gfx-beat1-b.mp4"), 1.0)
        jdump({"bed_duration": 2, "beats": [
            {"index": 0, "kind": "graphics", "slug": "beat0-a", "start": 0, "end": 1, "scene": {"title_html": "A", "type": "hook"}},
            {"index": 1, "kind": "graphics", "slug": "beat1-b", "start": 1, "end": 2, "scene": {"title_html": "B", "type": "cta"}}]},
            os.path.join(self.tmp, "beat_list.json"))
        outside = tempfile.mkdtemp()
        try:
            victims = {}
            for name in ("work/seg/seg-0000.mp4", "work/seg/concat.txt", "saves/body_video.mp4"):
                v = os.path.join(outside, os.path.basename(name))
                put(v, "keep me")
                os.symlink(v, os.path.join(self.tmp, name))
                victims[name] = v
                r = script("segments.py", "--beats", "beat_list.json", "--bed-duration", "2", "--out", "saves/body_video.mp4", cwd=self.tmp)
                self.assertNotEqual(r.returncode, 0, name + r.stdout)
                self.assertEqual(slurp(v), "keep me", name)
                os.remove(os.path.join(self.tmp, name))
            os.symlink(outside, os.path.join(self.tmp, "linkseg"))
            r = script("segments.py", "--beats", "beat_list.json", "--bed-duration", "2", "--out", "saves/body_video.mp4",
                       "--seg-dir", "linkseg", cwd=self.tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(sorted(os.listdir(outside)), sorted(os.path.basename(v) for v in victims.values()))
        finally:
            shutil.rmtree(outside, ignore_errors=True)


@need_ffmpeg
class Proofs(Base):
    def beats(self, spans):
        beats, t = [], 0.0
        for i, sp in enumerate(spans):
            beats.append({"index": i, "kind": "graphics", "slug": "beat%d-x" % i, "start": t, "end": t + sp})
            t += sp
        jdump({"bed_duration": t, "beats": beats}, os.path.join(self.tmp, "beats.json"))

    def run_proof(self, *a):
        return script("proofs.py", *a, cwd=self.tmp)

    def test_psnr_passes_a_moving_picture_and_fails_a_frozen_one(self):
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           os.path.join(self.tmp, "moving.mp4"))
        ff("-f", "lavfi", "-i", "color=c=0x336699:s=1080x1920:r=30:d=4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           os.path.join(self.tmp, "frozen.mp4"))
        self.beats([2.0, 2.0])
        self.assertEqual(self.run_proof("psnr", "--video", "moving.mp4", "--beats", "beats.json").returncode, 0)
        r = self.run_proof("psnr", "--video", "frozen.mp4", "--beats", "beats.json")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FAIL", r.stdout)

    def test_psnr_works_on_files_with_audio_every_time(self):
        """Regression: with `-frames:v 1` the summary line was often missing on a file with an audio track."""
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=12", "-f", "lavfi", "-i", "sine=f=220:d=12", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "av.mp4"))
        self.beats([1.5] * 8)
        for _ in range(3):
            r = self.run_proof("psnr", "--video", "av.mp4", "--beats", "beats.json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.count("PASS beat"), 8, r.stdout)
        ff("-f", "lavfi", "-i", "color=c=0x336699:s=1080x1920:r=30:d=12", "-f", "lavfi", "-i", "sine=f=220:d=12", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "frozen-av.mp4"))
        r = self.run_proof("psnr", "--video", "frozen-av.mp4", "--beats", "beats.json")
        self.assertEqual(r.returncode, 1, "a frozen picture with sound must still fail: " + r.stdout)
        self.assertIn("FAIL beat", r.stdout)

    def test_volume_uses_the_offset_and_fails_silence(self):
        ff("-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=4", "-f", "lavfi", "-i", "sine=f=220:d=4", "-af", "volume=0.3",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "loud.mp4"))
        ff("-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=4", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "silent.mp4"))
        self.beats([1.5, 1.5])
        self.assertEqual(self.run_proof("volume", "--video", "loud.mp4", "--beats", "beats.json", "--offset", "0.4").returncode, 0)
        self.assertEqual(self.run_proof("volume", "--video", "silent.mp4", "--beats", "beats.json").returncode, 1)
        self.assertEqual(self.run_proof("volume", "--video", "../x.mp4", "--beats", "beats.json").returncode, 2)


@need_ffmpeg
class AacOverhang(Base):
    def make(self, name, video_s, audio_s):
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=%g" % video_s, "-f", "lavfi", "-i", "sine=f=220:d=%g" % audio_s, "-af",
           "tremolo=f=3:d=0.7,volume=0.2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
           os.path.join(self.tmp, name))

    def test_av_span_passes_the_real_output_of_the_loudness_master(self):
        """Regression: the AAC re-encode ends the audio about 15 ms after the picture; that is not an error."""
        for seconds in (3.0, 3.1, 4.0333):
            self.make("in.mp4", seconds, seconds)
            r = script("master_loudness.py", "--in", "in.mp4", "--out", "out.mp4", cwd=self.tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for extra in ((), ("--after-captions",)):
                r = qa("av-span", os.path.join(self.tmp, "out.mp4"), *extra)
                self.assertEqual(r.returncode, 0, "%s s %s: %s" % (seconds, extra, r.stdout))

    def test_av_span_passes_the_cover_concat_and_still_fails_real_overhang(self):
        self.make("a.mp4", 3.0, 3.0)
        card_clip(os.path.join(self.tmp, "c.mp4"), 0.4)
        ff("-i", os.path.join(self.tmp, "c.mp4"), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.4", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "freeze.mp4"))
        ff("-i", os.path.join(self.tmp, "freeze.mp4"), "-i", os.path.join(self.tmp, "a.mp4"), "-filter_complex",
           "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", os.path.join(self.tmp, "joined.mp4"))
        self.assertEqual(qa("av-span", os.path.join(self.tmp, "joined.mp4"), "--after-captions").returncode, 0)
        self.make("long.mp4", 3.0, 3.2)
        for extra in ((), ("--after-captions",)):
            r = qa("av-span", os.path.join(self.tmp, "long.mp4"), *extra)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("more than one AAC frame", r.stdout)
        self.assertIn("--after-captions", slurp(os.path.join(STEPS, "06-final-checks.md")))

    def test_tail_luma_default_floor_is_26(self):
        self.assertIn("default=26.0", slurp(FRAME_QA))


class CaptionGroups(Base):
    def plan(self, sizes):
        return {"caption_groups": [{"start": i, "end": i + 0.9, "style": 0,
                                    "words": [{"w": "W%d" % j, "s": i, "e": i + 0.1, "em": False} for j in range(n)]}
                                   for i, n in enumerate(sizes)]}

    def run_check(self, sizes):
        jdump(self.plan(sizes), os.path.join(self.tmp, "plan.json"))
        return script("check_captions.py", "--plan", "plan.json", cwd=self.tmp)

    def test_two_to_four_words_pass_and_only_the_last_may_be_one(self):
        self.assertEqual(self.run_check([2, 3, 4, 2]).returncode, 0)
        self.assertEqual(self.run_check([3, 3, 1]).returncode, 0)

    def test_a_single_word_in_the_middle_or_a_long_group_fails(self):
        r = self.run_check([3, 1, 3])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("group 1", r.stdout)
        self.assertEqual(self.run_check([1, 1, 1, 1, 1, 1, 3]).returncode, 1)
        self.assertEqual(self.run_check([3, 5, 2]).returncode, 1)
        self.assertEqual(self.run_check([3, 0]).returncode, 1)

    def test_bad_plan_paths(self):
        self.assertEqual(script("check_captions.py", "--plan", "../x.json", cwd=self.tmp).returncode, 2)
        put(os.path.join(self.tmp, "bad.json"), "not json")
        self.assertEqual(script("check_captions.py", "--plan", "bad.json", cwd=self.tmp).returncode, 2)

    def test_the_step_states_the_same_rule(self):
        text = slurp(os.path.join(STEPS, "05-assemble.md"))
        self.assertIn("every group holds 2 to 4 words", text)
        self.assertIn("check_captions.py", text)
        self.assertNotIn("up to 6", text)


class DeliverFinal(Base):
    def make(self, **change):
        os.makedirs(os.path.join(self.tmp, "work"), exist_ok=True)
        cand = os.path.join(self.tmp, "work", "cand.mp4")
        put(cand, "pretend video bytes")
        import hashlib
        sha = hashlib.sha256(Path(cand).read_bytes()).hexdigest()
        card = {"verdict": "PASS", "finalized": True, "counts": {"pass": 2, "fail": 0, "look": 0}, "input": "work/cand.mp4",
                "input_sha256": sha, "checks": [{"id": "a", "status": "PASS"}, {"id": "b", "status": "PASS"}]}
        card.update(change)
        jdump(card, os.path.join(self.tmp, "work", "card.json"))

    def deliver(self):
        return script("deliver_final.py", "--candidate", "work/cand.mp4", "--scorecard", "work/card.json", "--out", "saves/final_video.mp4", cwd=self.tmp)

    def test_a_finalized_pass_for_this_file_is_delivered(self):
        self.make()
        r = self.deliver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(slurp(os.path.join(self.tmp, "saves/final_video.mp4")), "pretend video bytes")

    def test_everything_else_is_refused_and_nothing_is_written(self):
        cases = {"fail verdict": dict(verdict="FAIL"), "pass with looks": dict(verdict="PASS_WITH_LOOKS"),
                 "not finalized": dict(finalized=False), "no finalized key": dict(finalized=None),
                 "a look owed": dict(counts={"pass": 1, "fail": 0, "look": 1}), "a fail count": dict(counts={"pass": 1, "fail": 1, "look": 0}),
                 "a row not pass": dict(checks=[{"id": "a", "status": "LOOK"}]), "other file": dict(input="work/other.mp4"),
                 "wrong hash": dict(input_sha256="0" * 64), "no hash": dict(input_sha256=None)}
        for label, change in cases.items():
            self.make(**change)
            r = self.deliver()
            self.assertEqual(r.returncode, 1, label + r.stdout)
            self.assertIn("REFUSED", r.stdout, label)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "saves/final_video.mp4")), label)
        self.make()
        put(os.path.join(self.tmp, "work", "cand.mp4"), "changed after the scorecard")
        self.assertEqual(self.deliver().returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "saves/final_video.mp4")))
        os.remove(os.path.join(self.tmp, "work", "card.json"))
        self.assertEqual(self.deliver().returncode, 1)

    def test_the_real_gate_scorecard_shape_is_accepted_only_after_finalize(self):
        gate = os.path.join(block_dir("b-qa-gate"), "check.py")
        if not HAVE_FFMPEG:
            self.skipTest("ffmpeg is not installed")
        os.makedirs(os.path.join(self.tmp, "work"), exist_ok=True)
        ff("-f", "lavfi", "-i", "color=c=0xE0E0E0:s=1080x1920:r=30:d=2", "-f", "lavfi", "-i", "sine=f=220:d=2", "-af",
           "tremolo=f=3:d=0.7,loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.tmp, "work", "cand.mp4"))
        spec = {"recipe": "t", "checks": [{"id": "dims", "type": "dims", "w": 1080, "h": 1920},
                                           {"id": "look", "type": "perceptual", "desc": "Does it look right?"}]}
        jdump(spec, os.path.join(self.tmp, "spec.json"))
        run = lambda *a: subprocess.run([sys.executable, "-I", gate, *a], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(run("--kind", "reel", "--spec", "spec.json", "--input", "work/cand.mp4", "--out", "work/sc.json").returncode, 4)
        r = script("deliver_final.py", "--candidate", "work/cand.mp4", "--scorecard", "work/sc.json", "--out", "saves/final_video.mp4", cwd=self.tmp)
        self.assertEqual(r.returncode, 1, "an unfinalized scorecard must be refused")
        jdump({"look": {"answer": "yes", "note": "ok"}}, os.path.join(self.tmp, "ans.json"))
        self.assertEqual(run("--finalize", "work/sc.json", "--answers", "ans.json", "--out", "work/final-sc.json").returncode, 0)
        r = script("deliver_final.py", "--candidate", "work/cand.mp4", "--scorecard", "work/final-sc.json", "--out", "saves/final_video.mp4", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        jdump({"look": {"answer": "no", "note": "bad"}}, os.path.join(self.tmp, "ans.json"))
        os.remove(os.path.join(self.tmp, "saves/final_video.mp4"))
        self.assertEqual(run("--finalize", "work/sc.json", "--answers", "ans.json", "--out", "work/final-no.json").returncode, 1)
        r = script("deliver_final.py", "--candidate", "work/cand.mp4", "--scorecard", "work/final-no.json", "--out", "saves/final_video.mp4", cwd=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "saves/final_video.mp4")))


class ProtocolWhitelist(unittest.TestCase):
    def test_every_ffmpeg_input_in_the_steps_and_scripts_is_local_only(self):
        seen = 0
        for name in sorted(os.listdir(STEPS)):
            for code in step_python_blocks(name):
                for m in re.finditer(r"'-i',", code):
                    before = re.sub(r"'-f', 'lavfi',\s*$", "", code[:m.start()].rstrip()).rstrip()
                    self.assertTrue(before.endswith("'-protocol_whitelist', 'file',"), "%s: an -i without the whitelist" % name)
                    seen += 1
        for name in sorted(os.listdir(SCRIPTS)):
            if not name.endswith(".py") or name == "voiceover.py":
                continue
            text = slurp(os.path.join(SCRIPTS, name))
            for m in re.finditer(r'"-i"', text):
                self.assertIn("protocol_whitelist", text[max(0, m.start() - 160):m.start()], "%s: an -i without the whitelist" % name)
                seen += 1
            for m in re.finditer(r'\["ffprobe"', text):
                self.assertIn("protocol_whitelist", text[m.start():m.start() + 160], "%s: ffprobe without the whitelist" % name)
                seen += 1
        self.assertGreater(seen, 15)


class StepRules(unittest.TestCase):
    def test_every_render_goes_through_the_one_wrapper(self):
        renders = 0
        for name in sorted(os.listdir(STEPS)):
            text = slurp(os.path.join(STEPS, name))
            self.assertNotIn("hyperframes@", text, name)
            self.assertNotIn("npx", text, name)
            for line in text.splitlines():
                if "hf_render.py" in line and line.startswith("python3"):
                    self.assertIn("$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py", line)
                    self.assertIn("--quiet", line)
                    self.assertIn("--comp", line)
                    renders += 1
        self.assertGreaterEqual(renders, 3)
        shared = slurp(os.path.join(STEPS, "_shared.md"))
        self.assertIn("hf_install.py", shared)
        self.assertIn("fetch_gsap.py", shared)
        self.assertIn("check_local.py", shared)

    def test_premium_commands_use_the_final_interface(self):
        text = slurp(os.path.join(STEPS, "05-assemble.md"))
        premium = os.path.join(BLOCKS, "b-reel-premium", "scripts")
        for name in ("check_plan.py", "build_comp.py", "mux.py", "qa.py"):
            line = next(l for l in text.splitlines() if l.startswith("python3") and "/" + name in l)
            help_text = subprocess.run([sys.executable, "-I", os.path.join(premium, name), "--help"], capture_output=True, text=True).stdout
            for flag in re.findall(r"(--[a-z-]+)", line):
                self.assertIn(flag, help_text, "%s does not take %s" % (name, flag))
        self.assertIn("--format mov", text)
        self.assertNotIn("--visuals", text)
        self.assertNotIn("--max 4", text)

    def test_steps_name_blocks_by_relative_path_only(self):
        for name in sorted(os.listdir(STEPS)) + ["../SKILL.md", "../README.md"]:
            text = slurp(os.path.join(STEPS, name))
            self.assertNotIn(".hub", text, name)
            self.assertNotRegex(text, "/" + "Users/|[A-Z]:" + r"\\" + "Users", name)

    def test_no_step_tells_a_bot_to_skip_permission_checks_or_run_shell_blocks(self):
        for name in sorted(os.listdir(STEPS)):
            text = slurp(os.path.join(STEPS, name))
            self.assertNotRegex(text, r"```(?:bash|sh|zsh|powershell)\b", name)
            self.assertNotIn("dangerously", text.lower(), name)


if __name__ == "__main__":
    unittest.main()
