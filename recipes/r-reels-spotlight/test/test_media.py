#!/usr/bin/env python3
"""Offline tests for the media helpers (they need ffmpeg and ffprobe; the recipe needs them too).

  python3 -I recipes/r-reels-spotlight/test/test_media.py -v

No HyperFrames render, no network, no paid call. The takeover pages are built and inspected, not rendered.
"""
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, FFMPEG, FFPROBE, NEEDS_FFMPEG, RECIPE_DIR, SCRIPTS, Tmp, duration, load_json, make_video, py, read, write_json, write_text


def probe_size(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    return out


@NEEDS_FFMPEG
class BarsTest(Tmp):
    def test_a_matched_bar_pair_is_cropped_and_a_plain_clip_is_not(self):
        padded, plain = self.path("padded.mp4"), self.path("plain.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=2",
                        "-vf", "pad=320:568:0:194:color=white", "-c:v", "libx264", "-pix_fmt", "yuv420p", padded], check=True)
        make_video(plain, size="320x568", tone=False)
        got = py("bars.py", padded)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertRegex(got.stdout.strip(), r"^crop=\d+:\d+:\d+:\d+,$")
        self.assertEqual(py("bars.py", plain).stdout.strip(), "")


@NEEDS_FFMPEG
class BedLoudnessTest(Tmp):
    def test_step_01_uses_one_loudness_target_and_the_bed_lands_on_it(self):
        text = read("steps/01-prepare-footage.md")
        found = {float(v) for v in re.findall(r"loudnorm=I=(-?\d+(?:\.\d+)?)", text)}
        found |= {float(v) for v in re.findall(r"`I=(-?\d+(?:\.\d+)?):TP=", text)}
        self.assertEqual(found, {-14.0})
        af = re.findall(r'-af "(loudnorm=I=[^"]+)"', text)
        self.assertEqual(len(af), 1)
        src, bed = self.path("talk.wav"), self.path("bed.wav")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.05:duration=14:seed=7",
                        "-af", "volume='if(lt(mod(t,0.6),0.38),1,0.03)':eval=frame", "-ar", "48000", src], check=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-af", af[0], "-ar", "48000", "-ac", "2", bed], check=True)
        log = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", bed, "-af", "ebur128", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        lufs = float(re.findall(r"^\s+I:\s+(-?\d+(?:\.\d+)?) LUFS", log, re.M)[-1])
        self.assertLessEqual(abs(lufs - (-14.0)), 1.0, "sealed bed %.1f LUFS" % lufs)


@NEEDS_FFMPEG
class BrollHelpersTest(Tmp):
    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "work"))
        os.makedirs(os.path.join(self.wd, "inputs", "broll"))
        self.clip = os.path.join("inputs", "broll", "wide.mp4")   # 16:9: the fit-plus-blurred-fill path
        make_video(os.path.join(self.wd, self.clip), seconds=3, size="320x180", tone=False)

    def beats(self, clip):
        write_json(os.path.join(self.wd, "work", "beat_list.json"),
                   {"beats": [{"index": 3, "kind": "broll", "start": 2, "end": 3, "broll": {"clip": clip, "in": 0.0, "out": 1.0}}]})

    def test_takeover_clip_is_1080x1920_and_overlay_composites(self):
        self.beats(self.clip)
        r = py("broll_takeovers.py", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        out = os.path.join(self.wd, "work", "broll_takeovers", "broll_tk3.mp4")
        self.assertEqual(probe_size(out), "1080,1920")
        make_video(os.path.join(self.wd, "work", "visuals.mp4"), seconds=4, size="1080x1920", tone=False)
        r = py("broll_overlay.py", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        self.assertEqual(probe_size(os.path.join(self.wd, "work", "scenes.mp4")), "1080,1920")

    def test_a_clip_outside_inputs_broll_is_refused(self):
        outside = self.path("secret.mp4")
        make_video(outside, size="64x64", tone=False)
        self.beats(outside)
        r = py("broll_takeovers.py", cwd=self.wd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("outside inputs/broll", r.stderr)

    def test_beats_guard(self):
        plan = {"takeovers": [{"start": 4, "end": 7}]}
        write_json(os.path.join(self.wd, "plan.json"), plan)
        good = {"beats": [{"index": 0, "kind": "broll", "start": 2, "end": 3, "broll": {"clip": self.clip, "in": 0, "out": 1}}], "achieved_broll_pct": 10}
        write_json(os.path.join(self.wd, "beats.json"), good)
        self.assertEqual(py("beats_guard.py", "beats.json", "plan.json", "10", cwd=self.wd).returncode, 0)
        for name, edit in (("overlap", {"start": 3.5, "end": 4.5}), ("too early", {"start": 1, "end": 2}),
                           ("out past the clip", None), ("no broll", "none")):
            with self.subTest(name):
                bad = load_json(os.path.join(self.wd, "beats.json"))
                if edit == "none":
                    bad["beats"][0]["kind"] = "graphics"
                elif edit is None:
                    bad["beats"][0]["broll"]["out"] = 99
                else:
                    bad["beats"][0].update(edit)
                write_json(os.path.join(self.wd, "bad.json"), bad)
                self.assertNotEqual(py("beats_guard.py", "bad.json", "plan.json", "10", cwd=self.wd).returncode, 0)


@NEEDS_FFMPEG
class FinalGateTest(Tmp):
    def test_continuity_needs_audible_voice_under_every_window(self):
        wd = self.path("wd")
        os.makedirs(os.path.join(wd, "prior"))
        write_json(os.path.join(wd, "prior", "edit_plan.json"), {"takeovers": [{"start": 0.5, "end": 1.5}]})
        make_video(os.path.join(wd, "loud.mp4"), seconds=2, tone=True)
        self.assertEqual(py("final_gate.py", "continuity", "loud.mp4", cwd=wd).returncode, 0)
        make_video(os.path.join(wd, "mute.mp4"), seconds=2, tone=False)   # no audio stream at all
        self.assertNotEqual(py("final_gate.py", "continuity", "mute.mp4", cwd=wd).returncode, 0)

    SPEC = {"checks": [{"id": "qa_gate", "type": "qa_gate"}, {"id": "dims", "type": "dims"}, {"id": "look", "type": "perceptual"}]}

    def card(self, video, **change):
        import hashlib
        with open(video, "rb") as fh:
            raw = fh.read()
        rows = [{"id": "qa_gate.video", "status": "PASS"}, {"id": "qa_gate.audio", "status": "PASS"}, {"id": "dims", "status": "PASS"}, {"id": "look", "status": "PASS"}]
        card = {"finalized": True, "verdict": "PASS", "counts": {"pass": 4, "fail": 0, "look": 0}, "checks": rows,
                "input_sha256": hashlib.sha256(raw).hexdigest(), "input_bytes": len(raw)}
        card.update(change)
        return card

    def setup_delivery(self, seconds=22, size="1080x1920"):
        wd = self.path("wd")
        os.makedirs(os.path.join(wd, "work"))
        make_video(os.path.join(wd, "work", "final_video.mp4"), seconds=seconds, size=size)
        write_json(os.path.join(wd, "work", "spec.json"), self.SPEC)
        return wd

    def deliver(self, wd, card=None):
        if card is not None:
            write_json(os.path.join(wd, "work", "final-scorecard.json"), card)
        return py("final_gate.py", "delivery", "work/final-scorecard.json", "work/spec.json", "work/final_video.mp4", cwd=wd)

    def test_delivery_gate(self):
        wd = self.setup_delivery(seconds=2, size="64x64")
        r = self.deliver(wd)
        self.assertEqual(r.returncode, 1)
        self.assertIn("1080x1920", r.stdout)       # wrong size
        self.assertIn("outside 20-65s", r.stdout)  # too short
        self.assertIn("missing or unreadable", r.stdout)

    def test_a_good_scorecard_passes(self):
        wd = self.setup_delivery()
        r = self.deliver(wd, self.card(os.path.join(wd, "work", "final_video.mp4")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DELIVERY GATE PASSED", r.stdout)

    def test_a_scorecard_with_only_the_verdict_changed_is_refused(self):
        wd = self.setup_delivery()
        video = os.path.join(wd, "work", "final_video.mp4")
        cases = {
            "a FAIL row": (self.card(video, checks=[{"id": "qa_gate.video", "status": "FAIL"}, {"id": "qa_gate.audio", "status": "PASS"}, {"id": "dims", "status": "PASS"}, {"id": "look", "status": "PASS"}]), "is FAIL, not PASS"),
            "an unanswered look": (self.card(video, checks=[{"id": "qa_gate.video", "status": "PASS"}, {"id": "qa_gate.audio", "status": "PASS"}, {"id": "dims", "status": "PASS"}, {"id": "look", "status": "LOOK"}]), "is LOOK, not PASS"),
            "counts say a failure": (self.card(video, counts={"pass": 3, "fail": 1, "look": 0}), "counts do not match"),
            "counts do not add up": (self.card(video, counts={"pass": 9, "fail": 0, "look": 0}), "counts do not match"),
            "a spec check has no row": (self.card(video, checks=[{"id": "qa_gate.video", "status": "PASS"}, {"id": "qa_gate.audio", "status": "PASS"}, {"id": "look", "status": "PASS"}], counts={"pass": 3, "fail": 0, "look": 0}), "has no row"),
            "a different hash": (self.card(video, input_sha256="0" * 64), "hash or size"),
            "a different size": (self.card(video, input_bytes=5), "hash or size"),
            "not finalized": (self.card(video, finalized=False), "not finalized"),
            "a verdict that is not PASS": (self.card(video, verdict="PASS_WITH_LOOKS"), "verdict ="),
            "no rows": (self.card(video, checks=[], counts={"pass": 0, "fail": 0, "look": 0}), "no check rows"),
        }
        for name, (card, needle) in cases.items():
            with self.subTest(name):
                r = self.deliver(wd, card)
                self.assertEqual(r.returncode, 1, name)
                self.assertIn(needle, r.stdout)

    def test_the_card_must_be_for_the_file_given(self):
        wd = self.setup_delivery()
        other = os.path.join(wd, "work", "other.mp4")
        make_video(other, seconds=23, size="1080x1920")
        write_json(os.path.join(wd, "work", "final-scorecard.json"), self.card(other))
        r = self.deliver(wd)
        self.assertEqual(r.returncode, 1)
        self.assertIn("hash or size", r.stdout)

    def test_window_top_is_the_same_everywhere(self):
        top = int(re.search(r"MAX_SECONDS = (\d+)", read("scripts/final_gate.py")).group(1))
        self.assertEqual(top, int(re.search(r"duration within 20–(\d+) s", read("steps/07-final-checks.md")).group(1)))
        acc = [c for c in load_json(os.path.join(RECIPE_DIR, "acceptance.json"))["checks"] if c["id"] == "duration_window"]
        self.assertEqual(int(acc[0]["max_s"]), top)
        label = [c["label"] for s in load_json(os.path.join(RECIPE_DIR, "manifest.json"))["steps"] for c in s.get("checks", []) if c["id"] == "duration_window"]
        self.assertIn("20–%d s" % top, label[0])
        # step 01 can hand step 07 a bed of up to a 60 s clip plus the longest tail
        tail = float(re.search(r"MARGIN, MAX_TAIL = [0-9.]+, ([0-9.]+)", read("scripts/end_card_tail.py")).group(1))
        self.assertLessEqual(60 + tail, top)


class BuildTakeoversTest(Tmp):
    """build_takeovers.py runs from the work folder: every path it is given must be inside it."""

    def build(self, takeovers, blocks=None):
        wd = self.path("wd")
        os.makedirs(wd, exist_ok=True)
        write_json(os.path.join(wd, "work", "plan.json"), {"duration": 12.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}, "takeovers": takeovers})
        write_text(os.path.join(wd, "work", "base.mp4"), "stand-in")
        write_text(os.path.join(wd, "vendor", "gsap.min.js"), "/* stand-in */")
        r = py("build_takeovers.py", "work", RECIPE_DIR, blocks or BLOCKS, "vendor/gsap.min.js", cwd=wd)
        return r, os.path.join(wd, "work")

    def page(self, work, i=0):
        with open(os.path.join(work, "comp", "compositions", "tk%d.html" % i), encoding="utf-8") as fh:
            return fh.read()

    def test_text_is_escaped_and_placeholders_fill_once(self):
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword",
                               "fill": {"WORD": '<img src=x onerror=alert(1)>', "SUPPORT": "{{BG}} & more"}}])
        self.assertEqual(r.returncode, 0, r.stderr)
        page = self.page(work)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;img", page)
        self.assertIn("&#123;&#123;BG&#125;&#125; &amp; more", page, "a value must never fill another placeholder")

    def test_an_address_in_text_is_refused_not_dressed_up(self):
        # b-hyperframes' check reads a page after undoing entities, so such text could not pass it
        for word in ("https://evil.example/x", "javascript:alert(1)", "url(//x)", "see //host/x", "@import now"):
            with self.subTest(word):
                r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword", "fill": {"WORD": "OK", "SUPPORT": word}}])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("takeover 0 SUPPORT contains", r.stderr)
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword", "fill": {"WORD": "OK", "SUPPORT": "example.com/path, me@example.com, 50% off (today)"}}])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_script_words_are_written_with_one_letter_as_an_entity(self):
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword", "fill": {"WORD": "OK", "SUPPORT": "WebSocket and innerHTML"}}])
        self.assertEqual(r.returncode, 0, r.stderr)
        page = self.page(work)
        self.assertNotIn("WebSocket", page)
        self.assertIn("&#87;ebSocket", page)

    def test_only_the_accent_span_survives_in_title_and_quote(self):
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-list",
                               "fill": {"TITLE": 'Grow <span class="accent">fast</span><script>x()</script>', "ITEM1": "a", "ITEM2": "b", "ITEM3": "c"}}])
        self.assertEqual(r.returncode, 0, r.stderr)
        page = self.page(work)
        self.assertIn('<span class="accent">fast</span>', page)
        self.assertNotIn("<script>x()", page)
        self.assertIn("&lt;script&gt;x&#40;&#41;", page)

    def test_a_missing_key_stops_the_build(self):
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-list", "fill": {"TITLE": "t", "ITEM1": "a"}}])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unfilled placeholders", r.stderr)

    def test_root_shell_lists_each_takeover_on_its_own_track(self):
        r, work = self.build([{"start": 3, "end": 6, "template": "tk-stat", "fill": {"EYEBROW": "e", "STAT": "3X", "LABEL": "l"}},
                              {"start": 10, "end": 12, "template": "tk-keyword", "fill": {"WORD": "w", "SUPPORT": "s"}}])
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(work, "comp", "index.html"), encoding="utf-8") as fh:
            index = fh.read()
        self.assertIn('data-track-index="1"', index)
        self.assertIn('data-track-index="2"', index)
        self.assertNotIn("{{", index)

    def test_a_typing_takeover_goes_through_the_block_filler(self):
        r, work = self.build([{"start": 3, "end": 8, "template": "tk-typing-ui",
                               "fill": {"PROMPT": 'Write </script><img src=x> {{BG}} "hi"', "LABEL": "AI chat", "TYPING_SPEED": "1.2"}}])
        self.assertEqual(r.returncode, 0, r.stderr)
        page = self.page(work)
        self.assertIn('<template id="tk0-template">', page)
        self.assertNotIn("<img", page)
        self.assertNotIn("</script><img", page)
        with open(os.path.join(work, "comp", "index.html"), encoding="utf-8") as fh:
            self.assertIn('data-composition-src="compositions/tk0.html"', fh.read())

    def test_a_refusal_from_the_block_filler_stops_the_build(self):
        r, work = self.build([{"start": 3, "end": 8, "template": "tk-typing-ui", "fill": {"PROMPT": "x", "LABEL": "x" * 99}}])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("typing_fill.py refused takeover 0", r.stderr)

    def test_a_template_name_is_never_a_path(self):
        wd = self.path("wd")
        evil = os.path.join(wd, "inputs", "evil")
        os.makedirs(evil)
        write_text(os.path.join(evil, "x.html"), '<template id="{{ID}}-template"><script>alert("pwn")</script></template>')
        for name in ("../../inputs/evil/x", "../inputs/evil/x", "tk-stat/../../../inputs/evil/x", "/etc/passwd", "tk-unknown", "", None, 5):
            with self.subTest(name):
                r, work = self.build([{"start": 3, "end": 7, "template": name, "fill": {}}])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("is not one of", r.stderr)
                self.assertFalse(os.path.exists(os.path.join(work, "comp", "compositions", "tk0.html")), "a page was written")

    def test_a_fill_cannot_override_the_values_the_script_sets(self):
        for key in ("ID", "BG", "DURATION", "ACCENT", "FG", "VIDEO_SRC"):
            with self.subTest(key):
                r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword", "fill": {"WORD": "OK", "SUPPORT": "s", key: "x"}}])
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("fill keys", r.stderr)
                self.assertFalse(os.path.exists(os.path.join(work, "comp", "compositions", "tk0.html")))

    def test_bad_times_and_values_are_refused(self):
        for name, tk in (("text time", {"start": "3", "end": 7}), ("backwards", {"start": 7, "end": 3}), ("past the end", {"start": 3, "end": 99}),
                         ("nan", {"start": 3, "end": float("nan")}), ("bool", {"start": True, "end": 7})):
            with self.subTest(name):
                r, work = self.build([dict(tk, template="tk-keyword", fill={"WORD": "a", "SUPPORT": "b"})])
                self.assertNotEqual(r.returncode, 0)
        r, work = self.build([{"start": 3, "end": 7, "template": "tk-keyword", "fill": {"WORD": ["a"], "SUPPORT": "b"}}])
        self.assertNotEqual(r.returncode, 0)

    def test_a_missing_gsap_stops_the_build(self):
        wd = self.path("wd2")
        write_json(os.path.join(wd, "work", "plan.json"), {"duration": 5.0, "brand": {"bg": "#000000", "accent": "#FFFFFF", "fg": "#FFFFFF"}, "takeovers": []})
        write_text(os.path.join(wd, "work", "base.mp4"), "x")
        r = py("build_takeovers.py", "work", RECIPE_DIR, BLOCKS, "absent.js", cwd=wd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gsap.min.js not found", r.stderr)

    def test_a_path_outside_the_work_folder_is_refused(self):
        wd = self.path("wd3")
        os.makedirs(wd)
        write_text(self.path("gsap.min.js"), "x")
        r = py("build_takeovers.py", "work", RECIPE_DIR, BLOCKS, self.path("gsap.min.js"), cwd=wd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("outside the work folder", r.stderr)


@NEEDS_FFMPEG
class BrollPathsTest(Tmp):
    """Values from beat_list.json never become paths or ffmpeg inputs unchecked."""

    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "work", "broll_takeovers"))
        os.makedirs(os.path.join(self.wd, "inputs", "broll"))
        make_video(os.path.join(self.wd, "inputs", "broll", "a.mp4"), seconds=3, size="320x180", tone=False)
        make_video(os.path.join(self.wd, "work", "visuals.mp4"), seconds=4, size="1080x1920", tone=False)

    def beats(self, **beat):
        b = {"index": 3, "kind": "broll", "start": 2, "end": 3, "broll": {"clip": "inputs/broll/a.mp4", "in": 0.0, "out": 1.0}}
        b.update(beat)
        write_json(os.path.join(self.wd, "work", "beat_list.json"), {"beats": [b]})

    def test_a_beat_index_that_is_not_a_whole_number_is_refused(self):
        for bad in ("../../inputs/evil", "3", 3.5, -1, True, None):
            with self.subTest(bad):
                self.beats(index=bad)
                self.assertNotEqual(py("broll_takeovers.py", cwd=self.wd).returncode, 0)
                self.assertNotEqual(py("broll_overlay.py", cwd=self.wd).returncode, 0)

    def test_bad_in_out_values_are_refused(self):
        for bad in ({"clip": "inputs/broll/a.mp4", "in": "0", "out": 1}, {"clip": "inputs/broll/a.mp4", "in": 2, "out": 1}, {"clip": 5, "in": 0, "out": 1}):
            with self.subTest(bad):
                self.beats(broll=bad)
                self.assertNotEqual(py("broll_takeovers.py", cwd=self.wd).returncode, 0)

    def test_the_overlay_ignores_a_planted_rendered_path_and_never_reuses_a_stale_scene(self):
        outside = self.path("outside.mp4")
        make_video(outside, size="64x64", tone=False)
        self.beats(_rendered_path=outside)
        write_text(os.path.join(self.wd, "work", "scenes.mp4"), "stale")
        r = py("broll_overlay.py", cwd=self.wd)
        self.assertNotEqual(r.returncode, 0, "the planted path must not be used; the real clip is missing")
        self.assertIn("broll_tk3.mp4 is missing", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.wd, "work", "scenes.mp4")), "the stale scenes.mp4 was left in place")
        self.assertEqual(py("broll_takeovers.py", cwd=self.wd).returncode, 0)
        self.assertEqual(py("broll_overlay.py", cwd=self.wd).returncode, 0)
        self.assertEqual(probe_size(os.path.join(self.wd, "work", "scenes.mp4")), "1080,1920")


class PlanGuardOptimizedTest(Tmp):
    def test_the_guard_still_refuses_under_python_O(self):
        plan = {"duration": 8.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}, "cover_at": 6.5,
                "takeovers": [{"start": 2.5, "end": 6.0, "template": "../../inputs/evil/x", "fill": {}}],
                "caption_groups": [{"start": 0, "end": 8, "style": 0, "words": [{"w": "HI", "s": 0, "e": 1, "em": False}]}], "sfx": []}
        write_json(self.path("plan.json"), plan)
        r = subprocess.run([sys.executable, "-I", "-O", os.path.join(SCRIPTS, "plan_guard.py"), self.path("plan.json"), "8.0"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("plan OK", r.stdout)
        self.assertIn("unknown takeover template", r.stderr)

    def test_the_other_guards_also_refuse_under_python_O(self):
        write_json(self.path("beats.json"), {"beats": []})
        write_json(self.path("p.json"), {"takeovers": []})
        r = subprocess.run([sys.executable, "-I", "-O", os.path.join(SCRIPTS, "beats_guard.py"), self.path("beats.json"), self.path("p.json"), "10"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


@NEEDS_FFMPEG
class BrollCuesAndOptionsTest(Tmp):
    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "inputs", "broll"))
        make_video(os.path.join(self.wd, "inputs", "broll", "talk.mp4"), seconds=2, tone=True)
        make_video(os.path.join(self.wd, "inputs", "broll", "silent.mp4"), seconds=3, tone=False)
        write_text(os.path.join(self.wd, "inputs", "broll", "notes.txt"), "not a video")

    def test_cues_come_from_the_words_files_and_the_rest_are_empty(self):
        write_json(os.path.join(self.wd, "work", "broll_words", "talk.mp4.json"), [{"text": "hello", "start": 0.1, "end": 0.5}])
        r = py("broll_cues.py", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipped inputs/broll/notes.txt", r.stderr)
        cues = {c["clip"]: c for c in load_json(os.path.join(self.wd, "work", "broll_cues.json"))}
        self.assertEqual(set(cues), {"inputs/broll/talk.mp4", "inputs/broll/silent.mp4"})
        self.assertEqual(cues["inputs/broll/talk.mp4"]["cues"], [{"start": 0.1, "end": 0.5, "text": "hello"}])
        self.assertEqual(cues["inputs/broll/silent.mp4"]["cues"], [])
        self.assertAlmostEqual(cues["inputs/broll/silent.mp4"]["duration"], 3.0, delta=0.2)

    def test_only_clips_with_sound_are_listed_for_speech_to_text(self):
        r = py("broll_cues.py", "--list-audio", cwd=self.wd)
        self.assertEqual(r.stdout.split(), ["inputs/broll/talk.mp4"])


class BrollOptionsTest(Tmp):
    def run_it(self, options):
        write_json(self.path("brief.json"), {"options": options})
        return py("broll_options.py", self.path("brief.json"))

    def test_defaults_and_values(self):
        self.assertEqual(self.run_it({}).stdout.split(), ["30", "4", "2", "6", "as-given", "false"])
        r = self.run_it({"broll_order": "even", "broll_coverage_pct": 40, "broll_reuse": "true"})
        self.assertEqual(r.stdout.split(), ["40", "4", "2", "6", "even", "true"])

    def test_other_orders_and_text_are_refused(self):
        r = self.run_it({"broll_order": "anything-else"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("scene_plan.json", r.stderr)
        for bad in ({"broll_order": "x; touch PWNED"}, {"broll_order": "transcript-match"}, {"broll_coverage_pct": "30; touch PWNED"}, {"broll_coverage_pct": 101},
                    {"broll_min_seconds": 7}, {"broll_reuse": "maybe"}):
            with self.subTest(bad):
                r = self.run_it(bad)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, "")


class PadColorTest(Tmp):
    def run_it(self, brief):
        write_json(self.path("brief.json"), brief)
        return py("pad_color.py", self.path("brief.json"))

    def test_default_and_brand_colours(self):
        self.assertEqual(self.run_it({}).stdout.strip(), "0x0F172A")
        self.assertEqual(self.run_it({"brand": {"palette": {"bg": "#aa00ff"}}}).stdout.strip(), "0xAA00FF")
        self.assertEqual(self.run_it({"brand": {"bg": "123ABC"}}).stdout.strip(), "0x123ABC")

    def test_a_brief_that_cannot_be_read_is_an_error_not_the_default(self):
        self.assertNotEqual(py("pad_color.py", self.path("absent.json")).returncode, 0)
        write_text(self.path("bad.json"), "{not json")
        r = py("pad_color.py", self.path("bad.json"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        write_text(self.path("list.json"), "[]")
        self.assertNotEqual(py("pad_color.py", self.path("list.json")).returncode, 0)

    def test_anything_else_is_refused(self):
        for bad in ("red", "#12345", "#1234567", "0F172A:x=1", "#0F172A;rm", 5, ["#000000"]):
            with self.subTest(bad):
                r = self.run_it({"brand": {"palette": {"bg": bad}}})
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, "")


class PremiumPlanTest(Tmp):
    def run_it(self, options, edit=None):
        edit = edit or {"grade": "warm-amber", "duration": 9, "brand": {"bg": "#000000", "accent": "#F97316", "fg": "#F1F5F9"},
                        "takeovers": [{"start": 2}], "caption_groups": [{"start": 0, "end": 1, "style": 0, "words": [{"w": "HI", "s": 0, "e": 1, "em": False}]}],
                        "sfx": [{"t": 2.5, "name": "pop", "gain": 0.4}], "cover_at": 4}
        write_json(self.path("edit.json"), edit)
        write_json(self.path("brief.json"), {"options": options})
        r = py("premium_plan.py", "--edit-plan", self.path("edit.json"), "--brief", self.path("brief.json"), "--out", self.path("premium", "plan.json"))
        return r

    def test_the_block_plan_keeps_only_what_the_block_reads(self):
        r = self.run_it({})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["on", "on", "warm-amber"])
        plan = load_json(self.path("premium", "plan.json"))
        self.assertEqual(sorted(plan), ["brand", "caption_groups", "grade", "sfx"])
        self.assertEqual(plan["brand"], {"accent": "#F97316", "fg": "#F1F5F9"})
        self.assertEqual(plan["sfx"], [{"t": 2.5, "name": "pop", "gain": 0.4}])

    def test_options_turn_sound_off_and_name_music(self):
        r = self.run_it({"sfx": "off", "captions": "off", "music": "inputs/bed.mp3"})
        self.assertEqual(r.stdout.split(), ["off", "off", "warm-amber"])
        plan = load_json(self.path("premium", "plan.json"))
        self.assertEqual(plan["sfx"], [])
        self.assertEqual(plan["music"], {"file": "inputs/bed.mp3"})

    def test_a_bad_option_stops(self):
        self.assertNotEqual(self.run_it({"captions": "yes"}).returncode, 0)

    def test_a_grade_the_block_does_not_know_stops(self):
        self.assertNotEqual(self.run_it({}, edit={"grade": "sepia x", "brand": {}, "caption_groups": []}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
