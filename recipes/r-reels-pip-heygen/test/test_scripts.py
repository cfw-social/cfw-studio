#!/usr/bin/env python3
"""Offline tests for the small scripts of r-reels-pip (everything except the card and composite scripts).

  python3 -I recipes/r-reels-pip/test/test_scripts.py -v

No network, no paid account, no private file. Tests that need ffmpeg, node or a block say so and are
skipped by name when it is missing. The pages are checked with the local-only check of b-hyperframes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
SCRIPTS = os.path.join(RECIPE, "scripts")
BLOCKS = os.path.join(os.path.dirname(os.path.dirname(RECIPE)), "blocks")
CHECK_LOCAL = os.path.join(BLOCKS, "b-hyperframes", "scripts", "check_local.py")
FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
HAVE_BLOCKS = os.path.isfile(CHECK_LOCAL) and os.path.isdir(os.path.join(BLOCKS, "b-typing-ui"))


def script(name, args, cwd, stdin=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, name)] + args, cwd=cwd, capture_output=True,
                          text=True, input=stdin)


def dump(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def ff(args, cwd):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, cwd=cwd, check=True)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="pip-scripts-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def local_only(self, comp):
        return subprocess.run([sys.executable, CHECK_LOCAL, "--comp", comp], cwd=self.d, capture_output=True, text=True)


class OptionsTest(Tmp):
    def run_options(self, options):
        dump(os.path.join(self.d, "brief.json"), {"options": options})
        return script("options.py", [], self.d)

    def test_defaults_are_filled(self):
        p = self.run_options({})
        self.assertEqual(p.returncode, 0, p.stderr)
        got = load(os.path.join(self.d, "work", "options.json"))
        self.assertEqual((got["captions"], got["grade"], got["cta_duration"], got["pip_ring"], got["broll_order"]),
                         ("on", "clean-bright", 3, 8, "as-given"))
        self.assertNotIn("stt_model", got)

    def test_the_speech_model_is_not_an_order_option(self):
        p = self.run_options({"stt_model": "/etc/anything", "stt_tool_version": "1"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("stt_model", p.stderr)                 # named as ignored, not silently dropped
        got = load(os.path.join(self.d, "work", "options.json"))
        self.assertNotIn("stt_model", got)

    def test_bad_values_stop_with_one_line(self):
        for bad in ({"grade": "sepia"}, {"pip_ring": 99}, {"pip_ring": 2.5}, {"cta_duration": "soon"},
                    {"broll_order": "transcript-match"}, {"captions": "maybe"},
                    {"broll_min_seconds": 9, "broll_max_seconds": 3}, {"cta_duration": "3; rm -rf x"}):
            p = self.run_options(bad)
            self.assertEqual(p.returncode, 1, bad)
            self.assertIn("options.py: FAILED", p.stderr)
            self.assertEqual(p.stderr.count("\n"), 1, bad)

    def test_unknown_options_are_named_not_silent(self):
        p = self.run_options({"overlay_beats": [{"type": "pill"}], "pip_ring": 4})
        self.assertEqual(p.returncode, 0)
        self.assertIn("overlay_beats", p.stderr)
        self.assertEqual(load(os.path.join(self.d, "work", "options.json"))["pip_ring"], 4)

    def test_booleans_and_numeric_strings(self):
        p = self.run_options({"broll_reuse": True, "cta_duration": "2.5"})
        self.assertEqual(p.returncode, 0, p.stderr)
        got = load(os.path.join(self.d, "work", "options.json"))
        self.assertEqual((got["broll_reuse"], got["cta_duration"]), ("true", 2.5))


@unittest.skipUnless(HAVE_BLOCKS, "needs blocks/b-hyperframes and blocks/b-typing-ui")
class FillPageTest(Tmp):
    def fill(self, card, text, **kw):
        os.makedirs(os.path.join(self.d, "comp"), exist_ok=True)
        dump(os.path.join(self.d, "comp", "text.json"), text)
        with open(os.path.join(self.d, "comp", "gsap.min.js"), "w") as fh:
            fh.write("/* stand-in for the animation library; the real file is fetched by b-hyperframes */\n")
        args = ["--card", card, "--out", "comp/index.html", "--duration", kw.get("duration", "4"),
                "--text-file", "comp/text.json", "--accent", kw.get("accent", "F97316")]
        return script("fill_page.py", args, self.d)

    def page(self):
        return read(os.path.join(self.d, "comp", "index.html"))

    def test_motion_card_keeps_only_the_allowed_markup_and_passes_the_local_check(self):
        text = {"title_html": 'STOP <span class="accent">NOW</span><br>evil.example/x @bob {{ACCENT}} "q" &amp; & \\n',
                "eyebrow": "a </script> b", "ghost": "?"}
        p = self.fill("motion", text)
        self.assertEqual(p.returncode, 0, p.stderr)
        page = self.page()
        self.assertNotIn("{{", page)
        self.assertNotIn("</script> b", page)
        self.assertNotIn("evil.example/x", page)          # the slash is an entity
        self.assertIn("&amp; &amp;", page)               # an entity the author wrote shows as that character
        self.assertIn('<span class="accent">NOW</span><br>', page)
        self.assertEqual(page.count("<script"), 2)         # the library and the timeline; nothing from the text
        c = self.local_only("comp")
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)

    def test_other_markup_in_a_title_is_refused(self):
        for bad in ("<img src=x onerror=alert(1)>", "A <b>B</b>", '<span class="accent">open', "x</span>",
                    '<span class="accent"><span class="accent">n</span></span>', "<script>1</script>"):
            p = self.fill("motion", {"title_html": bad})
            self.assertEqual(p.returncode, 2, bad)
            self.assertFalse(os.path.exists(os.path.join(self.d, "comp", "index.html")), bad)

    def test_text_that_holds_an_address_is_refused_as_the_local_check_would(self):
        for bad in ("see https://x.example", "go to //evil.example", "javascript:alert(1)", "background url(x)",
                    "ftp:thing", "data:text/html,x", "a ws:b", "new WebSocket"):
            for card, key in (("motion", "title_html"), ("motion", "eyebrow"), ("cta", "text"), ("cta", "handle")):
                text = {"title_html": "ok"} if card == "motion" else {"text": "ok"}
                text[key] = bad
                p = self.fill(card, text)
                self.assertEqual(p.returncode, 2, (card, key, bad))
                self.assertIn(key, p.stderr)

    def test_limits_and_colours(self):
        self.assertEqual(self.fill("motion", {"title_html": "x" * 91}).returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok", "eyebrow": "e" * 41}).returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok", "ghost": "12345"}).returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "  "}).returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok", "extra": "x"}).returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok"}, accent="red").returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok"}, accent="F97316; x").returncode, 2)
        self.assertEqual(self.fill("motion", {"title_html": "ok"}, duration="0").returncode, 2)

    def test_cta_card_escapes_copy_and_the_handle_line_is_optional(self):
        p = self.fill("cta", {"text": "Comment 'GUIDE' & get <b>it</b> at x.y/z", "handle": "@brand"})
        self.assertEqual(p.returncode, 0, p.stderr)
        page = self.page()
        self.assertIn('id="cta-handle">&#64;brand</p>', page)
        self.assertNotIn("<b>", page)
        c = self.local_only("comp")
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        p = self.fill("cta", {"text": "Comment GUIDE"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn('id="cta-handle"', self.page().split("<script")[0])
        self.assertEqual(self.fill("cta", {"text": ""}).returncode, 2)       # never invents copy

    def test_output_outside_the_work_folder_is_refused(self):
        dump(os.path.join(self.d, "t.json"), {"text": "x"})
        p = script("fill_page.py", ["--card", "cta", "--out", "../escape.html", "--duration", "3", "--text-file", "t.json",
                                     "--accent", "F97316"], self.d)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.d), "escape.html")))

    def test_templates_themselves_pass_the_local_check_when_filled_with_defaults(self):
        for card, text in (("motion", {"title_html": "HELLO"}), ("cta", {"text": "Hi"})):
            self.assertEqual(self.fill(card, text).returncode, 0)
            self.assertEqual(self.local_only("comp").returncode, 0, card)


@unittest.skipUnless(HAVE_BLOCKS, "needs blocks/b-hyperframes and blocks/b-typing-ui")
class BuildCardsTest(Tmp):
    BEATS = {"beats": [
        {"index": 0, "kind": "graphics", "start": 0, "end": 3,
         "scene": {"type": "hook", "title_html": 'MOST <span class="accent">PEOPLE</span><br>WASTE &amp; TIME', "eyebrow": "THE TRICK"}},
        {"index": 1, "kind": "broll", "start": 3, "end": 6, "broll": {"clip": "inputs/broll/a.mp4", "in": 0, "out": 3}},
        {"index": 2, "kind": "graphics", "start": 6, "end": 10,
         "scene": {"type": "typing-ui", "title_html": "x", "prompt": "Explain </script><img src=x> \"quoted\" \\ it", "label": "My bot"}},
        {"index": 3, "kind": "graphics", "start": 10, "end": 14,
         "scene": {"type": "standard", "title_html": 'A <span class="accent">REEL</span>', "eyebrow": "RESULT", "ghost": "1"}}]}

    def setUp(self):
        # a private tree several levels deep, so that "../" climbs land inside it and can be seen
        self.top = tempfile.mkdtemp(prefix="pip-cards-top-")
        self.d = os.path.join(self.top, "l1", "l2", "l3", "wd")
        os.makedirs(self.d)
        self.addCleanup(shutil.rmtree, self.top, True)

    def tearDown(self):
        pass

    def run_cards(self, beats, brand=None):
        dump(os.path.join(self.d, "prior", "beat_list.json"), beats)
        dump(os.path.join(self.d, "work", "brand.json"), brand if brand is not None else {"accent": "#22C55E"})
        os.makedirs(os.path.join(self.d, "vendor"), exist_ok=True)
        with open(os.path.join(self.d, "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* stand-in */\n")
        return script("build_cards.py", ["--beats", "prior/beat_list.json", "--brand", "work/brand.json"], self.d)

    def test_one_page_per_graphics_beat_all_local_only(self):
        p = self.run_cards(self.BEATS)
        self.assertEqual(p.returncode, 0, p.stderr)
        cards = load(os.path.join(self.d, "work", "cards.json"))
        self.assertEqual([(c["index"], c["kind"]) for c in cards], [(0, "hook"), (2, "typing"), (3, "motion")])
        self.assertEqual(cards[1]["out"], "work/bg_beats/bg_beat2.mp4")
        for c in cards:
            r = self.local_only(c["dir"])
            self.assertEqual(r.returncode, 0, c["dir"] + r.stdout + r.stderr)
        hook = read(os.path.join(self.d, "work", "gfx_0", "index.html"))
        self.assertIn("MOST", hook)
        self.assertIn("22C55E", hook.upper())                   # the brand accent
        typing = read(os.path.join(self.d, "work", "gfx_2", "index.html"))
        self.assertNotIn("</script><img", typing)
        self.assertIn("pip-safe", typing)

    def test_a_plain_scene_becomes_a_card_with_no_text(self):
        beats = json.loads(json.dumps(self.BEATS))
        beats["beats"][3]["scene"] = {"type": "plain", "title_html": "note only, not drawn"}
        p = self.run_cards(beats)
        self.assertEqual(p.returncode, 0, p.stderr)
        cards = load(os.path.join(self.d, "work", "cards.json"))
        self.assertEqual(cards[-1]["kind"], "plain")
        page = read(os.path.join(self.d, "work", "gfx_3", "index.html"))
        self.assertNotIn("note only", page)
        self.assertEqual(self.local_only(cards[-1]["dir"]).returncode, 0)

    def test_typing_scene_without_a_prompt_stops_and_names_the_beat(self):
        beats = json.loads(json.dumps(self.BEATS))
        del beats["beats"][2]["scene"]["prompt"]
        p = self.run_cards(beats)
        self.assertEqual(p.returncode, 1)
        self.assertIn("beat 2", p.stderr)
        self.assertIn("never invents copy", p.stderr)

    def test_a_bad_brand_colour_stops(self):
        p = self.run_cards(self.BEATS, brand={"accent": "orange"})
        self.assertEqual(p.returncode, 1)
        self.assertIn("beat 0", p.stderr)

    def test_beat_kinds_this_recipe_does_not_build_are_refused(self):
        beats = {"beats": [{"index": 0, "kind": "avatar", "start": 0, "end": 3, "avatar": {}}]}
        p = self.run_cards(beats)
        self.assertEqual(p.returncode, 1)
        self.assertIn("avatar", p.stderr)

    def outside_listing(self):
        """Every file and folder in the private tree that is not inside the work folder."""
        names = set()
        for base, dirs, files in os.walk(self.top):
            if base == self.d or base.startswith(self.d + os.sep):
                dirs[:] = []
                continue
            names.update(os.path.join(base, x) for x in files + dirs)
        return names

    def test_a_hostile_beat_index_writes_nothing_anywhere(self):
        hostile = ("../../../../escaped-outside2/x", "../../../x", "../x", "1/../../x", "-1", "1000", 1.5, True, None, [1], {"a": 1},
                   "7", "gfx")
        for bad in hostile:
            for key_beat in (0, 2):   # a bad index on a card beat, and on any other beat
                beats = json.loads(json.dumps(self.BEATS))
                beats["beats"][key_beat]["index"] = bad
                before = self.outside_listing()
                p = self.run_cards(beats)
                self.assertEqual(p.returncode, 1, (bad, key_beat))
                self.assertIn("index", p.stderr)
                self.assertEqual(self.outside_listing(), before, "something was written outside the work folder for %r" % (bad,))
        
                self.assertFalse(os.path.exists(os.path.join(self.d, "work", "cards.json")), bad)
                self.assertEqual([n for n in os.listdir(os.path.join(self.d, "work")) if n.startswith("gfx_")], [], bad)

    def test_a_work_folder_that_is_a_link_out_is_refused(self):
        outside = os.path.join(self.top, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.d, "work"))
        dump(os.path.join(self.d, "prior", "beat_list.json"), self.BEATS)
        os.makedirs(os.path.join(self.d, "vendor"))
        with open(os.path.join(self.d, "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* stand-in */\n")
        with open(os.path.join(outside, "brand.json"), "w") as fh:
            fh.write("{}")
        p = script("build_cards.py", ["--beats", "prior/beat_list.json", "--brand", "work/brand.json"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(sorted(os.listdir(outside)), ["brand.json"])

    def test_missing_library_is_named(self):
        dump(os.path.join(self.d, "prior", "beat_list.json"), self.BEATS)
        dump(os.path.join(self.d, "work", "brand.json"), {})
        p = script("build_cards.py", ["--beats", "prior/beat_list.json", "--brand", "work/brand.json"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertIn("fetch_gsap.py", p.stderr)


class CaptionScriptsTest(Tmp):
    def groups(self):
        def g(words, style):
            return {"start": words[0][1], "end": words[-1][2], "style": style,
                    "words": [{"w": w, "s": s, "e": e, "em": False} for w, s, e in words]}
        return [g([("she", 0.0, 0.3), ("approved", 0.3, 0.8), ("them", 0.8, 1.0), ("with", 1.0, 1.2)], 0),
                g([("flour", 1.2, 1.6), ("still", 1.6, 2.0)], 1),
                g([("on", 2.0, 2.2), ("her", 2.2, 2.4), ("hands.", 2.4, 3.0)], 2)]

    def test_a_split_phrase_is_repaired_without_moving_any_time(self):
        path = os.path.join(self.d, "plan.json")
        dump(path, {"caption_groups": self.groups()})
        self.assertEqual(script("caption_phrases.py", ["--check", "plan.json"], self.d).returncode, 1)
        p = script("caption_phrases.py", ["plan.json"], self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        plan = load(path)
        all_words = [w for g in plan["caption_groups"] for w in g["words"]]
        self.assertEqual([(w["w"], w["s"], w["e"]) for w in all_words],
                         [(w["w"], w["s"], w["e"]) for g in self.groups() for w in g["words"]])
        for g in plan["caption_groups"][:-1]:
            self.assertNotIn(g["words"][-1]["w"], ("with", "on", "her", "the"))
        self.assertEqual(script("caption_phrases.py", ["--check", "plan.json"], self.d).returncode, 0)

    def test_broken_timing_is_refused_not_repaired(self):
        gs = self.groups()
        gs[1]["end"] = gs[1]["start"] - 0.1
        dump(os.path.join(self.d, "plan.json"), {"caption_groups": gs})
        p = script("caption_phrases.py", ["plan.json"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertIn("must end after it starts", p.stderr)

    def test_missing_plan_says_so(self):
        p = script("caption_phrases.py", ["nope.json"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertIn("plan not found", p.stderr)

    def test_clamp_drops_and_cuts_cues_at_the_end_card_window(self):
        dump(os.path.join(self.d, "work", "cta-window.json"), {"cta_start": 5.0})
        words = [{"text": "a", "start": 1.0, "end": 1.4}, {"text": "b", "start": 4.8, "end": 5.3},
                 {"text": "c", "start": 5.5, "end": 5.9}]
        dump(os.path.join(self.d, "prior", "transcripts.json"), {"words": words})
        p = script("clamp_captions.py", ["words", "prior/transcripts.json", "work/words.json"], self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        got = load(os.path.join(self.d, "work", "words.json"))
        self.assertEqual([(w["text"], w["end"]) for w in got], [("a", 1.4), ("b", 5.0)])
        plan = {"caption_groups": [{"start": 4.0, "end": 6.0, "style": 0, "words": [
            {"w": "x", "s": 4.0, "e": 4.5}, {"w": "y", "s": 5.2, "e": 5.9}]}, {"start": 5.5, "end": 6, "style": 1,
                                                                             "words": [{"w": "z", "s": 5.5, "e": 6}]}]}
        dump(os.path.join(self.d, "plan.json"), plan)
        self.assertEqual(script("clamp_captions.py", ["plan", "plan.json"], self.d).returncode, 0)
        got = load(os.path.join(self.d, "plan.json"))["caption_groups"]
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["end"], [w["w"] for w in got[0]["words"]]), (5.0, ["x"]))

    def test_without_an_end_card_the_words_are_copied_unchanged(self):
        words = [{"text": "a", "start": 1.0, "end": 1.4}, {"text": "c", "start": 19.5, "end": 20.9}]
        os.makedirs(os.path.join(self.d, "work"))
        dump(os.path.join(self.d, "prior", "transcripts.json"), {"words": words})
        self.assertEqual(script("clamp_captions.py", ["words", "prior/transcripts.json", "work/words.json"], self.d).returncode, 0)
        self.assertEqual(load(os.path.join(self.d, "work", "words.json")), words)


@unittest.skipUnless(FFMPEG, "needs ffmpeg")
class MediaScriptsTest(Tmp):
    def make(self, name, size, vf="", seconds=2, audio=None):
        args = ["-f", "lavfi", "-i", "color=white:s=%s:d=%s:r=30" % (size, seconds)]
        if audio:
            args += ["-f", "lavfi", "-i", audio, "-c:a", "aac", "-shortest"]
        if vf:
            args += ["-vf", vf]
        ff(args + ["-pix_fmt", "yuv420p", name], self.d)
        return name

    def crop(self, clip):
        p = script("bars.py", [clip], self.d)
        return p.returncode, p.stdout.strip(), p.stderr

    def test_a_matched_top_and_bottom_bar_pair_is_cropped(self):
        clip = self.make("th.mp4", "640x640", "drawbox=x=0:y=140:w=640:h=360:color=gray:t=fill")
        self.assertEqual(self.crop(clip)[:2], (0, "crop=640:360:0:140,"))

    def test_no_bars_means_no_crop(self):
        clip = self.make("th.mp4", "640x360", "drawbox=x=0:y=0:w=640:h=360:color=gray:t=fill")
        self.assertEqual(self.crop(clip)[:2], (0, ""))

    def test_unreadable_clip_stops(self):
        with open(os.path.join(self.d, "bad.mp4"), "wb") as fh:
            fh.write(b"not a video")
        self.assertNotEqual(self.crop("bad.mp4")[0], 0)

    def test_broll_cues_list_length_label_and_words(self):
        os.makedirs(os.path.join(self.d, "inputs", "broll"))
        self.make("inputs/broll/demo.mp4", "320x180", seconds=3)
        dump(os.path.join(self.d, "work", "cues", "demo.json"), [{"text": "hello", "start": 0.1, "end": 0.5}])
        p = script("broll_cues.py", [], self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        got = load(os.path.join(self.d, "work", "broll_cues.json"))
        self.assertEqual((got[0]["clip"], got[0]["label"], got[0]["cues"]), ("inputs/broll/demo.mp4", "demo",
                                                                           [{"start": 0.1, "end": 0.5, "text": "hello"}]))
        self.assertAlmostEqual(got[0]["duration"], 3.0, delta=0.1)

    def test_broll_cues_without_a_folder_or_with_a_broken_file(self):
        self.assertEqual(script("broll_cues.py", [], self.d).returncode, 0)
        self.assertEqual(load(os.path.join(self.d, "work", "broll_cues.json")), [])
        os.makedirs(os.path.join(self.d, "inputs", "broll"))
        with open(os.path.join(self.d, "inputs", "broll", "bad.mp4"), "wb") as fh:
            fh.write(b"nope")
        p = script("broll_cues.py", [], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertIn("bad.mp4 is not a video", p.stderr)

    def test_assemble_background_cuts_broll_joins_and_cuts_to_the_bed(self):
        os.makedirs(os.path.join(self.d, "inputs", "broll"))
        os.makedirs(os.path.join(self.d, "work", "bg_beats"))
        self.make("inputs/broll/a.mp4", "1280x720", seconds=4)
        self.make("work/bg_beats/bg_beat0.mp4", "1080x1920", seconds=2)
        self.make("voice.mp4", "320x180", seconds=4, audio="sine=frequency=300:duration=4")
        dump(os.path.join(self.d, "beats.json"), {"beats": [
            {"index": 0, "kind": "graphics", "start": 0, "end": 2},
            {"index": 1, "kind": "broll", "start": 2, "end": 4, "broll": {"clip": "inputs/broll/a.mp4", "in": 1, "out": 3}}]})
        p = script("assemble_background.py", ["--beats", "beats.json", "--voice", "voice.mp4", "--out", "saves/background.mp4"], self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                               "-of", "default=nw=1", os.path.join(self.d, "saves", "background.mp4")],
                              capture_output=True, text=True).stdout
        self.assertIn("width=1080", info)
        self.assertIn("height=1920", info)
        self.assertNotIn("audio", info)
        self.assertAlmostEqual(float(info.split("duration=")[1].split()[0]), 4.0, delta=0.15)

    def test_assemble_background_names_a_beat_with_no_clip(self):
        os.makedirs(os.path.join(self.d, "work", "bg_beats"))
        self.make("voice.mp4", "320x180", seconds=2, audio="sine=frequency=300:duration=2")
        dump(os.path.join(self.d, "beats.json"), {"beats": [{"index": 7, "kind": "graphics", "start": 0, "end": 2}]})
        p = script("assemble_background.py", ["--beats", "beats.json", "--voice", "voice.mp4", "--out", "bg.mp4"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertIn("beat 7 has no rendered clip", p.stderr)

    def test_assemble_background_refuses_a_hostile_index_or_clip(self):
        os.makedirs(os.path.join(self.d, "inputs", "broll"))
        os.makedirs(os.path.join(self.d, "work", "bg_beats"))
        self.make("outside.mp4", "320x180", seconds=3)
        self.make("voice.mp4", "320x180", seconds=2, audio="sine=frequency=300:duration=2")
        cases = [{"index": "../../escape", "kind": "graphics", "start": 0, "end": 2},
                 {"index": True, "kind": "graphics", "start": 0, "end": 2},
                 {"index": 5000, "kind": "graphics", "start": 0, "end": 2},
                 {"index": 1, "kind": "broll", "start": 0, "end": 2, "broll": {"clip": "outside.mp4", "in": 0, "out": 2}},
                 {"index": 1, "kind": "broll", "start": 0, "end": 2, "broll": {"clip": "../outside.mp4", "in": 0, "out": 2}},
                 {"index": 1, "kind": "broll", "start": 0, "end": 2, "broll": {"clip": "inputs/broll/a.mp4", "in": "x", "out": 2}}]
        for beat in cases:
            dump(os.path.join(self.d, "beats.json"), {"beats": [beat]})
            p = script("assemble_background.py", ["--beats", "beats.json", "--voice", "voice.mp4", "--out", "bg.mp4"], self.d)
            self.assertEqual(p.returncode, 1, beat)
            self.assertFalse(os.path.exists(os.path.join(self.d, "bg.mp4")), beat)
            self.assertEqual(os.listdir(os.path.join(self.d, "work", "bg_beats")), [], beat)

    def test_bars_has_help_and_one_line_errors(self):
        p = script("bars.py", ["--help"], self.d)
        self.assertEqual(p.returncode, 0)
        self.assertIn("matched pair", p.stdout)
        with open(os.path.join(self.d, "bad.mp4"), "wb") as fh:
            fh.write(b"not a video")
        p = script("bars.py", ["bad.mp4"], self.d)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(p.stderr.count("\n"), 1)
        self.assertEqual(script("bars.py", [], self.d).returncode, 2)

    def test_check_reel_range(self):
        self.make("good.mp4", "320x180", seconds=3)
        self.assertEqual(script("check_reel.py", ["range", "--video", "good.mp4", "--min", "2", "--max", "4"], self.d).returncode, 0)
        self.assertEqual(script("check_reel.py", ["range", "--video", "good.mp4", "--min", "5", "--max", "9"], self.d).returncode, 1)
        with open(os.path.join(self.d, "bad.mp4"), "wb") as fh:
            fh.write(b"x")
        self.assertEqual(script("check_reel.py", ["range", "--video", "bad.mp4", "--min", "1", "--max", "9"], self.d).returncode, 2)

    def test_check_reel_frames_duration_and_voice(self):
        self.make("good.mp4", "320x180", seconds=3, audio="sine=frequency=300:duration=3")
        ff(["-f", "lavfi", "-i", "color=black:s=320x180:d=3:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
            "-c:a", "aac", "-pix_fmt", "yuv420p", "black.mp4"], self.d)
        dump(os.path.join(self.d, "beats.json"), {"beats": [{"start": 0, "end": 1.5}, {"start": 1.5, "end": 3}]})
        self.assertEqual(script("check_reel.py", ["frames", "--video", "good.mp4"], self.d).returncode, 0)
        bad = script("check_reel.py", ["frames", "--video", "black.mp4"], self.d)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("black", bad.stdout)
        self.assertEqual(script("check_reel.py", ["duration", "--video", "good.mp4", "--expect", "3"], self.d).returncode, 0)
        self.assertEqual(script("check_reel.py", ["duration", "--video", "good.mp4", "--expect", "5"], self.d).returncode, 1)
        self.assertEqual(script("check_reel.py", ["voice", "--video", "good.mp4", "--beats", "beats.json"], self.d).returncode, 0)
        silent = script("check_reel.py", ["voice", "--video", "black.mp4", "--beats", "beats.json"], self.d)
        self.assertEqual(silent.returncode, 1)
        self.assertIn("silent", silent.stdout)
        self.assertEqual(script("check_reel.py", ["voice", "--video", "good.mp4", "--beats", "nope.json"], self.d).returncode, 2)


class DeliveryCheckTest(Tmp):
    """check_delivery.py stops unless a finalized PASS scorecard records exactly this video."""

    def setUp(self):
        super().setUp()
        import hashlib
        from pathlib import Path
        self.video = os.path.join(self.d, "final.mp4")
        with open(self.video, "wb") as fh:
            fh.write(b"pretend video bytes" * 100)
        self.good = {"scorecard_version": 1, "kind": "reel", "spec": "acceptance.json", "finalized": True, "verdict": "PASS",
                     "counts": {"pass": 2, "fail": 0, "look": 0},
                     "checks": [{"id": "a", "status": "PASS"}, {"id": "b", "status": "PASS"}],
                     "input_sha256": hashlib.sha256(Path(self.video).read_bytes()).hexdigest(), "input_bytes": 1900}

    def run_check(self, card=None, video="final.mp4"):
        if card is not None:
            dump(os.path.join(self.d, "sc.json"), card)
        return script("check_delivery.py", ["--video", video, "--scorecard", "sc.json", "--spec", "somewhere/acceptance.json"], self.d)

    def test_a_clean_finalized_pass_for_this_file_passes(self):
        p = self.run_check(self.good)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DELIVERY OK", p.stdout)

    def test_every_way_of_not_passing_blocks(self):
        def variant(**kw):
            c = json.loads(json.dumps(self.good))
            c.update(kw)
            return c
        for name, card in (("fail verdict", variant(verdict="FAIL", counts={"pass": 1, "fail": 1, "look": 0})),
                           ("not finalized", variant(finalized=False, verdict="PASS_WITH_LOOKS", counts={"pass": 1, "fail": 0, "look": 1})),
                           ("no finalized flag", {k: v for k, v in self.good.items() if k != "finalized"}),
                           ("a look left", variant(counts={"pass": 1, "fail": 0, "look": 1})),
                           ("a row not PASS", variant(checks=[{"id": "a", "status": "PASS"}, {"id": "b", "status": "LOOK"}])),
                           ("no rows", variant(checks=[])),
                           ("other spec", variant(spec="other.json")),
                           ("image kind", variant(kind="image")),
                           ("wrong hash", variant(input_sha256="0" * 64)),
                           ("wrong size", variant(input_bytes=5)),
                           ("not a scorecard", {"verdict": "PASS"})):
            p = self.run_check(card)
            self.assertEqual(p.returncode, 1, name)
            self.assertIn("DELIVERY BLOCKED", p.stdout, name)

    def test_a_swapped_or_changed_video_blocks(self):
        self.run_check(self.good)
        with open(self.video, "ab") as fh:
            fh.write(b"x")
        p = self.run_check()
        self.assertEqual(p.returncode, 1)
        self.assertIn("not the file the gate checked", p.stdout)

    def test_missing_files_are_exit_2_not_a_pass(self):
        self.assertEqual(script("check_delivery.py", ["--video", "final.mp4", "--scorecard", "nope.json"], self.d).returncode, 2)
        dump(os.path.join(self.d, "sc.json"), self.good)
        self.assertEqual(script("check_delivery.py", ["--video", "nope.mp4", "--scorecard", "sc.json"], self.d).returncode, 2)
        with open(os.path.join(self.d, "sc.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(script("check_delivery.py", ["--video", "final.mp4", "--scorecard", "sc.json"], self.d).returncode, 2)


class SceneAndCaptionRulesTest(Tmp):
    def plan_check(self, scenes, copy=True, card="on", bed=30.0, cta_scene=False, cta_duration=3):
        dump(os.path.join(self.d, "plan.json"), {"version": 1, "scenes": scenes})
        dump(os.path.join(self.d, "brief.json"), {"brand": {"cta": "Comment GUIDE" if copy else ""}})
        dump(os.path.join(self.d, "work", "options.json"), {"cta_card": card, "cta_duration": cta_duration})
        return script("check_scene_plan.py", ["--plan", "plan.json", "--bed-dur", str(bed)], self.d)

    def test_a_text_card_under_the_end_card_is_refused_and_plain_or_broll_is_fine(self):
        base = [{"id": "a", "kind": "graphic", "start": 0, "end": 27, "type": "standard", "headline": "X"}]
        text_tail = base + [{"id": "tail", "kind": "graphic", "start": 27, "end": 30, "type": "standard", "headline": "Y"}]
        p = self.plan_check(text_tail)
        self.assertEqual(p.returncode, 1)
        self.assertIn("tail", p.stdout)
        self.assertIn("plain", p.stdout)
        long_card = [{"id": "a", "kind": "graphic", "start": 0, "end": 30, "type": "hook", "headline": "X"}]
        self.assertEqual(self.plan_check(long_card).returncode, 1)
        for ok in (base + [{"id": "tail", "kind": "graphic", "start": 27, "end": 30, "type": "plain", "headline": "x"}],
                   base + [{"id": "tail", "kind": "broll", "start": 27, "end": 30, "asset": "c"}]):
            self.assertEqual(self.plan_check(ok).returncode, 0)

    def test_a_time_that_is_not_a_real_finite_number_is_refused(self):
        tail = {"id": "tail", "kind": "graphic", "start": 27, "type": "standard", "headline": "Y"}
        for bad in (float("nan"), float("inf"), True, "30", -1):
            p = self.plan_check([dict(tail, end=bad)])
            self.assertEqual(p.returncode, 2, "end %r" % (bad,))
            self.assertEqual(len(p.stderr.strip().splitlines()), 1, p.stderr)
            self.assertIn("tail", p.stderr)
            p = self.plan_check([dict(tail, end=30)], cta_duration=bad)
            self.assertEqual(p.returncode, 2, "cta_duration %r" % (bad,))
            self.assertEqual(len(p.stderr.strip().splitlines()), 1, p.stderr)
            self.assertIn("cta_duration", p.stderr)
        self.assertEqual(self.plan_check([dict(tail, end=30)], bed=float("nan")).returncode, 2)

    def test_nothing_is_checked_when_no_end_card_is_drawn(self):
        text_tail = [{"id": "tail", "kind": "graphic", "start": 0, "end": 30, "type": "standard", "headline": "Y"}]
        self.assertEqual(self.plan_check(text_tail, copy=False).returncode, 0)
        self.assertEqual(self.plan_check(text_tail, card="off").returncode, 0)
        with_cta = [{"id": "c", "kind": "graphic", "start": 0, "end": 30, "type": "cta", "headline": "Y"}]
        self.assertEqual(self.plan_check(with_cta).returncode, 0)

    def test_the_last_scene_is_checked_even_when_timed_by_phrases(self):
        scenes = [{"id": "a", "kind": "graphic", "start": 0, "end": 20, "type": "standard", "headline": "X"},
                  {"id": "z", "kind": "graphic", "start_phrase": "comment", "type": "standard", "headline": "Y"}]
        self.assertEqual(self.plan_check(scenes).returncode, 1)

    def test_a_caption_group_never_spans_a_sentence_end(self):
        def g(words, style):
            return {"start": words[0][1], "end": words[-1][2], "style": style,
                    "words": [{"w": w, "s": s, "e": e, "em": False} for w, s, e in words]}
        plan = {"caption_groups": [g([("wet", 0.0, 0.3), ("leaves.", 0.3, 0.7), ("finally", 0.7, 1.0)], 0),
                                   g([("feels", 1.0, 1.3), ("dry", 1.3, 1.6), ("it?", 1.6, 1.9), ("now", 1.9, 2.2)], 1)]}
        dump(os.path.join(self.d, "plan.json"), plan)
        chk = script("caption_phrases.py", ["--check", "plan.json"], self.d)
        self.assertEqual(chk.returncode, 1)
        self.assertEqual(chk.stderr.count("spans a sentence end"), 2)
        self.assertEqual(script("caption_phrases.py", ["plan.json"], self.d).returncode, 0)
        got = load(os.path.join(self.d, "plan.json"))["caption_groups"]
        for grp in got:
            for w in grp["words"][:-1]:
                self.assertNotRegex(w["w"], r"[.!?]$")
        self.assertEqual([w["w"] for grp in got for w in grp["words"]], ["wet", "leaves.", "finally", "feels", "dry", "it?", "now"])
        self.assertEqual(script("caption_phrases.py", ["--check", "plan.json"], self.d).returncode, 0)

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.d, "work"), exist_ok=True)


@unittest.skipUnless(HAVE_BLOCKS, "needs blocks/b-hyperframes and blocks/b-typing-ui")
class PlainCardTest(Tmp):
    def test_a_plain_card_has_no_text_and_passes_the_local_check(self):
        os.makedirs(os.path.join(self.d, "comp"))
        dump(os.path.join(self.d, "comp", "text.json"), {"plain": "true"})
        with open(os.path.join(self.d, "comp", "gsap.min.js"), "w") as fh:
            fh.write("/* stand-in */\n")
        p = script("fill_page.py", ["--card", "motion", "--out", "comp/index.html", "--duration", "3", "--text-file", "comp/text.json",
                                    "--accent", "F97316"], self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        page = read(os.path.join(self.d, "comp", "index.html"))
        self.assertIn('id="mc-title"></div>', page)
        self.assertNotIn("{{", page)
        self.assertEqual(subprocess.run([sys.executable, CHECK_LOCAL, "--comp", "comp"], cwd=self.d, capture_output=True).returncode, 0)
        for bad in ({"plain": "yes"}, {"plain": True}, {"eyebrow": "x"}):
            dump(os.path.join(self.d, "comp", "text.json"), bad)
            self.assertEqual(script("fill_page.py", ["--card", "motion", "--out", "comp/index.html", "--duration", "3",
                                                      "--text-file", "comp/text.json", "--accent", "F97316"], self.d).returncode, 2, bad)


class WordsFoundTest(Tmp):
    def check(self, words):
        dump(os.path.join(self.d, "saves", "transcripts.json"), {"words": words})
        return subprocess.run(["bash", os.path.join(RECIPE, "checks", "words_found.sh"), self.d], capture_output=True, text=True)

    def test_one_word_entries_pass_and_sentences_fail(self):
        good = [{"text": "w%d" % i, "start": i * 0.3, "end": i * 0.3 + 0.25} for i in range(20)]
        self.assertEqual(self.check(good).returncode, 0)
        sentences = [{"text": "this is a whole spoken sentence here", "start": 0.0, "end": 5.0}]
        self.assertNotEqual(self.check(sentences).returncode, 0)
        self.assertNotEqual(self.check([]).returncode, 0)
        self.assertNotEqual(self.check([{"text": "a", "start": 2, "end": 3}, {"text": "b", "start": 1, "end": 2}]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
