#!/usr/bin/env python3
"""Offline tests for the card, end-card and composite scripts of r-reels-pip.

  python3 -I recipes/r-reels-pip/test/test_card_and_cta.py -v

No network and no paid account. Needs python3 and ffmpeg.

- scripts/cta_takeover.py: the reel ends on ONE call to action and the copy is never invented.
- scripts/pip_card.py: the rounded mask and the ring + shadow frame, standard library only, checked by
  reading pixels back.
- scripts/composite_pip.py: the real ffmpeg run on a tiny generated fixture: the card is rounded and
  ringed, the video is as long as the bed and the audio is the bed's audio, copied.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE_DIR = os.path.dirname(HERE)
CTA_SCRIPT = os.path.join(RECIPE_DIR, "scripts", "cta_takeover.py")
CARD_SCRIPT = os.path.join(RECIPE_DIR, "scripts", "pip_card.py")
COMPOSITE = os.path.join(RECIPE_DIR, "scripts", "composite_pip.py")

ACCENT = (0xF9, 0x73, 0x16)  # F97316
CW, CH, RADIUS, RING, SHADOW = 364, 504, 40, 8, 22
PAD = RING + SHADOW
FW, FH = CW + 2 * PAD, CH + 2 * PAD


def beat(i, start, end, scene_type, kind="graphics"):
    b = {"index": i, "start": start, "end": end, "kind": kind, "slug": "beat%d-%s" % (i, scene_type)}
    if kind == "graphics":
        b["scene"] = {"id": scene_type, "type": scene_type, "scene_id": scene_type,
                      "title_html": "LINE %d" % i, "source": "scene_plan"}
    else:
        b["broll"] = {"clip": "inputs/broll/a.mp4", "in": 0, "out": end - start}
    return b


ENDS_ON_CTA = [beat(0, 0, 10, "hook"), beat(1, 10, 24, "standard"), beat(2, 24, 30, "cta")]
EARLY_CTA = [beat(0, 0, 10, "hook"), beat(1, 10, 24, "cta"), beat(2, 24, 30, "standard")]
ENDS_ON_CONTENT = [beat(0, 0, 10, "hook"), beat(1, 10, 24, "standard"), beat(2, 24, 30, "standard")]


def make_workdir(root, beats, cta=None, brand=None, options=None):
    """A step workdir shaped like the harness's: brief.json, prior/, inputs/, work/."""
    wd = tempfile.mkdtemp(dir=root)
    os.makedirs(os.path.join(wd, "prior"))
    os.makedirs(os.path.join(wd, "work"))
    brief = {"recipe": "r-reels-pip", "intent": "test", "targets": ["instagram"],
             "brand": brand if brand is not None else {"slug": "test-brand", "name": "Test Brand"},
             "options": options or {}}
    with open(os.path.join(wd, "brief.json"), "w") as fh:
        json.dump(brief, fh)
    with open(os.path.join(wd, "prior", "beat_list.json"), "w") as fh:
        json.dump({"bed_duration": 30.0, "cover_at": 12.0, "beats": beats}, fh)
    if cta is not None:
        os.makedirs(os.path.join(wd, "inputs", "cta"))
        with open(os.path.join(wd, "inputs", "cta", "cta.json"), "w") as fh:
            json.dump(cta, fh)
    return wd


def run_cta(wd, cta_card="on"):
    """Run the decision as step 05 does and return it. Stdout is empty: nothing is evaluated."""
    p = subprocess.run([sys.executable, CTA_SCRIPT, "--brief", "brief.json", "--beats", "prior/beat_list.json",
                        "--cta", "inputs/cta/cta.json", "--cta-card", cta_card,
                        "--decision", "work/cta-decision.json", "--card-text", "work/cta-text.json"], cwd=wd, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError("cta_takeover.py failed (%d): %s" % (p.returncode, p.stderr))
    if p.stdout != "":
        raise AssertionError("cta_takeover.py printed on stdout: %r" % p.stdout)
    with open(os.path.join(wd, "work", "cta-decision.json")) as fh:
        decision = json.load(fh)
    return {"takeover": "on" if decision["takeover"] else "off", "text": decision["text"],
            "handle": decision["handle"], "reason": decision["reason"],
            "stderr": p.stderr, "decision": decision}


def read_png_rgba(path):
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype = ihdr[0], ihdr[1], ihdr[2], ihdr[3]
    assert (depth, ctype) == (8, 6), "expected 8-bit RGBA, got depth %d type %d" % (depth, ctype)
    raw, bpp, stride = zlib.decompress(idat), 4, w * 4
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        rows.append(line)
        prev = line
    return w, h, lambda x, y: tuple(rows[y][x * 4:x * 4 + 4])


def blocked_env(root):
    """An env where `import PIL` fails even if Pillow is installed: run python with -S
    (no site-packages) and a PIL package on PYTHONPATH that raises ImportError."""
    block = os.path.join(root, "pil-blocker")
    os.makedirs(os.path.join(block, "PIL"), exist_ok=True)
    with open(os.path.join(block, "PIL", "__init__.py"), "w") as fh:
        fh.write("raise ImportError('Pillow is blocked by this test')\n")
    return dict(os.environ, PYTHONPATH=block)


def run_card(root, args, env):
    return subprocess.run([sys.executable, "-S", CARD_SCRIPT] + args, cwd=root, env=env,
                          capture_output=True, text=True)


def card_args(out, accent="F97316", ring=RING, shadow=SHADOW, frame=True):
    a = ["--card", "%dx%d" % (CW, CH), "--radius", str(RADIUS), "--ring", str(ring),
         "--shadow", str(shadow), "--accent", accent, "--mask", os.path.join(out, "pip-mask.png")]
    a += ["--frame", os.path.join(out, "pip-frame.png") if frame else ""]
    return a


def close(px, rgb, tol):
    return all(abs(int(p) - int(q)) <= tol for p, q in zip(px[:3], rgb))


def close(px, rgb, tol):
    return all(abs(int(p) - int(q)) <= tol for p, q in zip(px[:3], rgb))


class CtaTakeoverTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pip-cta-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_no_cta_json_and_plan_ends_on_cta_beat_skips_takeover(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CTA))
        self.assertEqual(r["takeover"], "off")
        self.assertEqual(r["text"], "")
        self.assertIn("already contains a CTA beat", r["reason"])
        self.assertIn("no second CTA and no scrim", r["reason"])
        self.assertEqual(r["decision"]["cta_beat"], {"index": 2, "slug": "beat2-cta", "start": 24, "end": 30})
        self.assertIn("[pip] end card skipped", r["stderr"])

    def test_a2_cta_beat_wins_even_with_cta_json(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CTA, cta={"text": "Comment GUIDE", "handle": "testbrand"}))
        self.assertEqual(r["takeover"], "off")
        self.assertIn("inputs/cta/cta.json copy was not drawn", r["reason"])

    def test_a3_cta_beat_found_by_largest_end_not_list_order(self):
        beats = [ENDS_ON_CTA[2], ENDS_ON_CTA[0], ENDS_ON_CTA[1]]
        self.assertEqual(run_cta(make_workdir(self.root, beats))["takeover"], "off")

    def test_early_cta_suppresses_takeover_even_when_content_follows(self):
        r = run_cta(make_workdir(self.root, EARLY_CTA, cta={"text": "A second CTA"}))
        self.assertEqual(r["takeover"], "off")
        self.assertEqual(r["decision"]["cta_beat"]["index"], 1)
        self.assertIn("copy was not drawn", r["reason"])

    def test_b_no_copy_and_no_cta_beat_skips_and_says_so(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT))
        self.assertEqual(r["takeover"], "off")
        self.assertEqual(r["text"], "")
        self.assertIn("no CTA copy", r["reason"])
        self.assertIn("never invents copy", r["reason"])
        self.assertNotIn("Follow", r["text"] + r["reason"])
        self.assertIn("[pip] end card skipped: no CTA copy", r["stderr"])

    def test_b2_cta_json_without_text_is_no_copy(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT, cta={"brandName": "Test Brand", "handle": "testbrand"}))
        self.assertEqual(r["takeover"], "off")
        self.assertIn("no CTA copy", r["reason"])

    def test_c_cta_json_and_no_cta_beat_uses_cta_json(self):
        text = "Comment 'GUIDE' & I'll DM you"
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT, cta={"text": text, "handle": "testbrand"},
                                 brand={"name": "Test Brand", "cta": "brand line", "handle": "otherhandle"}))
        self.assertEqual(r["takeover"], "on")
        self.assertEqual(r["text"], text)
        self.assertEqual(r["handle"], "testbrand")
        self.assertIn("inputs/cta/cta.json", r["reason"])

    def test_c2_brand_cta_used_when_no_cta_json(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT, brand={"name": "Test Brand", "cta": "Comment GUIDE"}))
        self.assertEqual((r["takeover"], r["text"], r["handle"]), ("on", "Comment GUIDE", ""))

    def typed_cta(self, name, body, **kw):
        """A workdir whose order carries only the typed CTA answer, as the bot guide writes it (inputs/cta/<id>.md)."""
        wd = make_workdir(self.root, ENDS_ON_CONTENT, **kw)
        os.makedirs(os.path.join(wd, "inputs", "cta"), exist_ok=True)
        with open(os.path.join(wd, "inputs", "cta", name), "w") as fh:
            fh.write(body)
        return wd

    def test_typed_cta_md_alone_is_the_end_card_copy(self):
        # The bot writes the typed `cta` answer as inputs/cta/cta.md; with no cta.json the card used to vanish.
        r = run_cta(self.typed_cta("cta.md", "Comment 'GUIDE' and I'll send it\n@testbrand\n"))
        self.assertEqual(r["takeover"], "on", r["reason"])
        self.assertEqual(r["text"], "Comment 'GUIDE' and I'll send it")
        self.assertEqual(r["handle"], "@testbrand")
        self.assertIn("inputs/cta/cta.md", r["reason"])

    def test_typed_cta_txt_alone_is_the_end_card_copy(self):
        r = run_cta(self.typed_cta("cta.txt", "DM me GUIDE"))
        self.assertEqual((r["takeover"], r["text"], r["handle"]), ("on", "DM me GUIDE", ""))

    def test_typed_cta_md_beats_the_brand_cta_and_cta_json_beats_md(self):
        brand = {"name": "Test Brand", "cta": "brand line", "handle": "brandhandle"}
        r = run_cta(self.typed_cta("cta.md", "Typed line", brand=brand))
        self.assertEqual((r["takeover"], r["text"], r["handle"]), ("on", "Typed line", "brandhandle"))
        wd = self.typed_cta("cta.md", "Typed line")
        with open(os.path.join(wd, "inputs", "cta", "cta.json"), "w") as fh:
            json.dump({"text": "JSON line"}, fh)
        r = run_cta(wd)
        self.assertEqual((r["text"], r["decision"]["source"]), ("JSON line", "inputs/cta/cta.json"))

    def test_empty_typed_cta_is_no_copy_and_invents_nothing(self):
        r = run_cta(self.typed_cta("cta.md", "  \n"))
        self.assertEqual((r["takeover"], r["text"]), ("off", ""))
        self.assertIn("no CTA copy", r["reason"])
        self.assertNotIn("Follow", r["text"] + r["reason"])

    def test_broll_last_beat_is_not_a_cta_beat(self):
        beats = [beat(0, 0, 20, "hook"), beat(1, 20, 30, "clip", kind="broll")]
        r = run_cta(make_workdir(self.root, beats, cta={"text": "Comment GUIDE"}))
        self.assertEqual(r["takeover"], "on")

    def test_cta_card_off(self):
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT, cta={"text": "Comment GUIDE"}), cta_card="off")
        self.assertEqual(r["takeover"], "off")
        self.assertIn("cta_card=off", r["reason"])

    def test_missing_beat_list_fails_loudly(self):
        wd = make_workdir(self.root, ENDS_ON_CONTENT, cta={"text": "Comment GUIDE"})
        os.remove(os.path.join(wd, "prior", "beat_list.json"))
        p = subprocess.run([sys.executable, CTA_SCRIPT, "--beats", "prior/beat_list.json"], cwd=wd,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("beat list prior/beat_list.json is missing", p.stderr)
        self.assertEqual(p.stdout, "")


    def test_empty_beat_list_fails_loudly(self):
        wd = make_workdir(self.root, [], cta={"text": "Comment GUIDE"})
        p = subprocess.run([sys.executable, CTA_SCRIPT, "--beats", "prior/beat_list.json"], cwd=wd,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("has no beats", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_brand_without_accent_or_handle_is_not_a_cta_problem(self):
        # a bare brand: copy from cta.json only, no handle line, no invented handle
        r = run_cta(make_workdir(self.root, ENDS_ON_CONTENT, cta={"text": "Comment GUIDE"}, brand={}))
        self.assertEqual((r["takeover"], r["text"], r["handle"]), ("on", "Comment GUIDE", ""))


class PipCardWithoutPillowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pip-card-")
        cls.env = blocked_env(cls.root)
        cls.out = os.path.join(cls.root, "out")
        os.makedirs(cls.out)
        cls.proc = run_card(cls.root, card_args(cls.out), cls.env)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_d0_pillow_really_is_unavailable_in_this_env(self):
        p = subprocess.run([sys.executable, "-S", "-c", "import PIL"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("ImportError", p.stderr)

    def test_d1_files_are_produced(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        for name in ("pip-mask.png", "pip-frame.png"):
            self.assertGreater(os.path.getsize(os.path.join(self.out, name)), 0)

    def test_d2_mask_has_rounded_corners(self):
        w, h, px = read_png_rgba(os.path.join(self.out, "pip-mask.png"))
        self.assertEqual((w, h), (CW, CH))
        for x, y in ((0, 0), (CW - 1, 0), (0, CH - 1), (CW - 1, CH - 1), (5, 5)):
            self.assertEqual(px(x, y)[3], 0, "corner pixel (%d,%d) must be transparent" % (x, y))
        for x, y in ((CW // 2, CH // 2), (0, CH // 2), (CW // 2, 0), (RADIUS, RADIUS)):
            self.assertEqual(px(x, y), (255, 255, 255, 255), "inside pixel (%d,%d) must be opaque white" % (x, y))

    def test_d3_frame_has_accent_ring_rounded_corners_and_shadow(self):
        w, h, px = read_png_rgba(os.path.join(self.out, "pip-frame.png"))
        self.assertEqual((w, h), (FW, FH))
        mid = PAD - RING // 2  # middle of the ring band
        for x, y in ((mid, FH // 2), (FW - 1 - mid, FH // 2), (FW // 2, mid), (FW // 2, FH - 1 - mid)):
            self.assertEqual(px(x, y), ACCENT + (255,), "ring pixel (%d,%d) must be the accent" % (x, y))
        self.assertEqual(px(0, 0)[3], 0, "outer corner must be transparent")
        corner = px(PAD - RING, PAD - RING)  # the ring rectangle's own corner pixel: rounded off
        self.assertLess(corner[3], 255)
        self.assertFalse(corner[3] == 255 and corner[:3] == ACCENT, "ring corner is square")
        shadow = px(FW // 2, FH - (PAD - RING) + 4)  # just below the ring, bottom middle
        self.assertGreater(shadow[3], 0, "no drop shadow under the ring")
        self.assertEqual(shadow[:3], (0, 0, 0))

    def test_mask_keeps_partial_coverage_after_ffmpeg_format_gray(self):
        mask = os.path.join(self.out, "pip-mask.png")
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mask, "-vf", "format=gray",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             check=True, capture_output=True).stdout
        self.assertEqual(len(raw), CW * CH)
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[(CH // 2) * CW + CW // 2], 255)
        self.assertTrue(any(0 < value < 255 for value in raw), "alphamerge would see a hard 0/255 edge")

    def test_alphamerge_keeps_partial_alpha_at_the_card_edge(self):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                              "color=red:s=%dx%d,format=yuva444p" % (CW, CH),
                              "-i", os.path.join(self.out, "pip-mask.png"),
                              "-filter_complex", "[0:v][1:v]alphamerge,alphaextract",
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             check=True, capture_output=True).stdout
        self.assertEqual(len(raw), CW * CH)
        self.assertTrue(any(0 < value < 255 for value in raw), "composited alpha lost the soft edge")

    def test_d4_ring_colour_follows_the_brand_accent(self):
        out = os.path.join(self.root, "cyan")
        os.makedirs(out)
        p = run_card(self.root, card_args(out, accent="#06B6D4"), self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        _, _, px = read_png_rgba(os.path.join(out, "pip-frame.png"))
        self.assertEqual(px(PAD - RING // 2, FH // 2), (0x06, 0xB6, 0xD4, 255))

    def test_three_digit_shorthand_accent(self):
        out = os.path.join(self.root, "short")
        os.makedirs(out)
        p = run_card(self.root, card_args(out, accent="#0CF"), self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        _, _, px = read_png_rgba(os.path.join(out, "pip-frame.png"))
        self.assertEqual(px(PAD - RING // 2, FH // 2), (0x00, 0xCC, 0xFF, 255))
        for bad in ("", "#12", "12345", "GGGGGG"):
            q = run_card(self.root, card_args(out, accent=bad), self.env)
            self.assertEqual(q.returncode, 1, bad)
            self.assertIn("is not a 6-digit hex colour", q.stderr)

    def test_d5_ring_zero_writes_mask_only(self):
        out = os.path.join(self.root, "noring")
        os.makedirs(out)
        p = run_card(self.root, card_args(out, ring=0, frame=False), self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.exists(os.path.join(out, "pip-mask.png")))
        self.assertFalse(os.path.exists(os.path.join(out, "pip-frame.png")))

    def test_d6_failure_exits_nonzero_and_names_what_failed(self):
        bad = run_card(self.root, card_args(self.out, accent="orange"), self.env)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("brand accent 'orange' is not a 6-digit hex colour", bad.stderr)
        missing = os.path.join(self.root, "no-such-dir")
        nowrite = run_card(self.root, card_args(missing), self.env)
        self.assertEqual(nowrite.returncode, 1)
        self.assertIn("FAILED - rounded mask %s" % os.path.join(missing, "pip-mask.png"), nowrite.stderr)
        self.assertFalse(os.path.exists(missing))


class CtaCardTextTest(unittest.TestCase):
    """The text file fill_page.py reads exists only when a takeover is drawn."""

    def test_card_text_written_only_for_a_takeover(self):
        root = tempfile.mkdtemp(prefix="pip-cta-text-")
        try:
            wd = make_workdir(root, ENDS_ON_CONTENT, cta={"text": "Comment GUIDE", "handle": "@x"})
            run_cta(wd)
            with open(os.path.join(wd, "work", "cta-text.json")) as fh:
                self.assertEqual(json.load(fh), {"text": "Comment GUIDE", "handle": "@x"})
            wd2 = make_workdir(root, ENDS_ON_CTA, cta={"text": "Comment GUIDE"})
            run_cta(wd2)
            self.assertFalse(os.path.exists(os.path.join(wd2, "work", "cta-text.json")))
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg")
class CompositeScriptTest(unittest.TestCase):
    """composite_pip.py on generated media: rounded ringed card, bed length, the bed's audio."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pip-ff-")
        r = cls.root
        p = run_card(r, card_args(r), blocked_env(r))
        assert p.returncode == 0, p.stderr
        ff = ["ffmpeg", "-v", "error", "-y"]
        subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=0x2040A0:s=1080x1920:r=30:d=1.0",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "bg.mp4"], cwd=r, check=True)
        # the head is a little shorter than the background on purpose: its last frame is held
        subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=red:s=360x640:r=30:d=0.9",
                             "-f", "lavfi", "-i", "sine=frequency=220:duration=1.0",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "head.mp4"], cwd=r, check=True)
        subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=0x00000000:s=1080x1920:r=30:d=0.4,format=yuva444p",
                             "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "cta.mov"],
                       cwd=r, check=True)

    def compose(self, args):
        return subprocess.run([sys.executable, COMPOSITE, "--background", "bg.mp4", "--voice", "head.mp4",
                               "--mask", "pip-mask.png", "--bed-dur", "1.0", "--out", "out.mp4"] + args,
                              cwd=self.root, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def frame(self, name, t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", os.path.join(self.root, name), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
        self.assertEqual(len(raw), 1080 * 1920 * 3)
        return lambda x, y: tuple(raw[(y * 1080 + x) * 3:(y * 1080 + x) * 3 + 3])

    def probe(self, name, entries):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "default=nw=1",
                              os.path.join(self.root, name)], capture_output=True, text=True).stdout
        return dict(line.split("=", 1) for line in out.split())

    def test_card_is_rounded_ringed_and_the_length_is_the_beds(self):
        p = self.compose(["--frame", "pip-frame.png", "--pad", str(PAD)])
        self.assertEqual(p.returncode, 0, p.stderr)
        px = self.frame("out.mp4", 0.2)
        x0, y0 = (1080 - CW) // 2, 1920 - CH - 110
        self.assertTrue(close(px(540, y0 + CH // 2), (255, 0, 0), 40), "head missing")
        self.assertTrue(close(px(x0 - RING // 2, y0 + CH // 2), ACCENT, 30), "left ring")
        self.assertTrue(close(px(540, y0 - RING // 2), ACCENT, 30), "top ring")
        corner = px(x0 + 1, y0 + 1)
        self.assertGreater(corner[2], 100, "card corner is not background (square card?)")
        self.assertLess(corner[0], 60, "card corner shows the head (square card?)")
        d = self.probe("out.mp4", "format=duration")
        self.assertAlmostEqual(float(d["duration"]), 1.0, delta=0.1)
        late = self.frame("out.mp4", 0.95)   # the head ended at 0.9 s: the card is still there
        self.assertTrue(close(late(540, y0 + CH // 2), (255, 0, 0), 40), "card vanished after the head ended")

    def test_audio_is_copied_not_reencoded(self):
        p = self.compose(["--frame", "pip-frame.png", "--pad", str(PAD)])
        self.assertEqual(p.returncode, 0, p.stderr)

        def audio(name):
            return subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "a:0", "-show_entries",
                                   "stream=codec_name,sample_rate,nb_read_packets", "-of", "csv=p=0",
                                   os.path.join(self.root, name)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(audio("out.mp4"), audio("head.mp4"))   # same codec, rate and packet count: copied

    def test_no_ring_still_makes_a_rounded_card(self):
        p = self.compose([])
        self.assertEqual(p.returncode, 0, p.stderr)
        px = self.frame("out.mp4", 0.2)
        y0 = 1920 - CH - 110
        self.assertTrue(close(px(540, y0 + CH // 2), (255, 0, 0), 40))
        self.assertGreater(px((1080 - CW) // 2 + 1, y0 + 1)[2], 100)

    def test_end_card_overlay_runs_and_keeps_the_length(self):
        p = self.compose(["--frame", "pip-frame.png", "--pad", str(PAD), "--cta-mov", "cta.mov", "--cta-start", "0.6", "--cta-dur", "0.4"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertAlmostEqual(float(self.probe("out.mp4", "format=duration")["duration"]), 1.0, delta=0.1)

    def test_bad_arguments_are_refused(self):
        for args in (["--card", "big"], ["--margin", "-1"], ["--bed-dur", "0"]):
            p = self.compose(args if "--bed-dur" not in args else [])
            if "--bed-dur" in args:
                p = subprocess.run([sys.executable, COMPOSITE, "--background", "bg.mp4", "--voice", "head.mp4",
                                    "--mask", "pip-mask.png", "--bed-dur", "0", "--out", "o.mp4"],
                                   cwd=self.root, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, (args, p.stderr))
        missing = subprocess.run([sys.executable, COMPOSITE, "--background", "nope.mp4", "--voice", "head.mp4",
                                  "--mask", "pip-mask.png", "--bed-dur", "1", "--out", "o.mp4"],
                                 cwd=self.root, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("nope.mp4 is missing", missing.stderr)


if __name__ == "__main__":
    unittest.main()
