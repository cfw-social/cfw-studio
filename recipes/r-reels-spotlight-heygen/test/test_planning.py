#!/usr/bin/env python3
"""Offline tests for the word-list and planning helpers.

  python3 -I recipes/r-reels-spotlight-heygen/test/test_planning.py -v

No speech-to-text runs here (that is the b-audio block). No network, no paid call.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Tmp, load_json, py, write_json, write_text

WORDS = [("This", 0.00, 0.26), ("is", 0.26, 0.44), ("a", 0.44, 0.60), ("real", 0.60, 0.82),
         ("bakery's", 0.82, 1.42), ("entire", 1.42, 1.86), ("month", 1.86, 2.20), ("of", 2.20, 2.32),
         ("orders.", 2.32, 2.90), ("She", 3.40, 3.58), ("approved", 3.58, 4.02), ("them", 4.02, 4.20),
         ("with", 4.20, 4.36), ("flour", 4.36, 4.70), ("still", 4.70, 4.98), ("on", 4.98, 5.10),
         ("her", 5.10, 5.24), ("hands.", 5.24, 5.80)]


def entries():
    return [{"text": w, "start": s, "end": e} for w, s, e in WORDS]


def group(words, style=0, em=None):
    return {"start": words[0][1], "end": words[-1][2], "style": style,
            "words": [{"w": w, "s": s, "e": e, "em": w == em} for w, s, e in words]}


class CaptionPhrasesTest(Tmp):
    def plan(self, groups):
        write_json(self.path("plan.json"), {"caption_groups": groups})
        return self.path("plan.json")

    def test_a_break_after_a_joiner_is_repaired(self):
        p = self.plan([group(WORDS[9:13], 0), group(WORDS[13:18], 1)])   # ... them with | flour still ...
        self.assertNotEqual(py("caption_phrases.py", "--check", p).returncode, 0)
        self.assertEqual(py("caption_phrases.py", p).returncode, 0)
        groups = load_json(p)["caption_groups"]
        self.assertNotEqual(groups[0]["words"][-1]["w"], "with")
        self.assertEqual(py("caption_phrases.py", "--check", p).returncode, 0)

    def test_equal_styles_and_a_second_emphasis_are_fixed(self):
        g0 = group(WORDS[0:5], 1, em="real")
        g1 = group(WORDS[5:9], 1)
        g0["words"][1]["em"] = True
        p = self.plan([g0, g1])
        self.assertEqual(py("caption_phrases.py", p).returncode, 0)
        out = load_json(p)["caption_groups"]
        self.assertNotEqual(out[0]["style"], out[1]["style"])
        self.assertLessEqual(sum(1 for w in out[0]["words"] if w["em"]), 1)

    def test_a_backwards_group_is_refused(self):
        bad = group(WORDS[0:3])
        bad["end"] = bad["start"]
        r = py("caption_phrases.py", "--check", self.plan([bad]))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("must end after it starts", r.stderr)


class TakeoverBrandTest(Tmp):
    def run_it(self, fill, template="tk-keyword", words=None, brand="Acme", check=False):
        write_json(self.path("plan.json"), {"takeovers": [{"start": 3, "end": 7, "template": template, "fill": fill}]})
        write_json(self.path("words.json"), words or [{"text": t} for t in "XQZ already learned her voice and it is great".split()])
        args = (["--check"] if check else []) + [self.path("plan.json"), self.path("words.json"), brand]
        r = py("takeover_brand.py", *args)
        return r, load_json(self.path("plan.json"))["takeovers"][0]["fill"]

    def test_a_foreign_name_becomes_the_order_brand(self):
        r, fill = self.run_it({"WORD": "XQZ", "SUPPORT": "XQZ wins"}, words=[{"text": "XQZ"}, {"text": "wins"}, {"text": "now"}])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(fill["WORD"], "ACME")   # an all-caps name becomes the brand in all caps

    def test_a_word_for_word_quote_keeps_its_words(self):
        r, fill = self.run_it({"WORD": "x", "SUPPORT": "XQZ already learned her voice"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(fill["SUPPORT"], "XQZ already learned her voice")

    def test_generic_acronyms_are_left_alone(self):
        r, fill = self.run_it({"WORD": "CAC", "SUPPORT": "MLS and NYC"}, words=[{"text": "CAC"}, {"text": "MLS"}, {"text": "NYC"}])
        self.assertEqual(fill, {"WORD": "CAC", "SUPPORT": "MLS and NYC"})

    def test_check_mode_reports_without_writing(self):
        r, fill = self.run_it({"WORD": "XQZ"}, words=[{"text": "we"}, {"text": "see"}, {"text": "XQZ"}], check=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(fill["WORD"], "XQZ")


class ScriptAlignTest(Tmp):
    def run_in(self, words, script=None, intent=None):
        wd = self.path("wd")
        os.makedirs(os.path.join(wd, "work"), exist_ok=True)
        write_json(os.path.join(wd, "work", "words.json"), words)
        write_json(os.path.join(wd, "brief.json"), {"intent": intent or "an unrelated topic line"})
        if script:
            write_text(os.path.join(wd, "inputs", "script", "script.md"), script)
        r = py("script_align.py", "work/words.json", cwd=wd)
        return r, load_json(os.path.join(wd, "work", "words.json"))

    def test_a_misheard_word_takes_the_script_word(self):
        heard = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.3} for i, t in enumerate("She approved them with flowers still on her hands.".split())]
        r, out = self.run_in(heard, script="She approved them with flour still on her hands.")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("flour", [w["text"] for w in out])
        self.assertEqual([w["start"] for w in out], [w["start"] for w in heard])

    def test_no_script_leaves_the_words_alone(self):
        r, out = self.run_in(entries())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out, entries())

    def test_a_script_that_does_not_match_changes_nothing(self):
        r, out = self.run_in(entries(), script="Completely different words about another subject entirely here")
        self.assertEqual(out, entries())


class HintFileTest(Tmp):
    def run_it(self, script, brand=None):
        wd = self.path("wd")
        os.makedirs(os.path.join(wd, "work"), exist_ok=True)
        write_json(os.path.join(wd, "brief.json"), {"brand": {"name": brand}} if brand else {})
        if script is not None:
            write_text(os.path.join(wd, "inputs", "script", "script.md"), script)
        return py("script_align.py", "--write-hint", "work/hint.txt", cwd=wd), os.path.join(wd, "work", "hint.txt")

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_names_and_unusual_words_only(self):
        r, hint = self.run_it("Most bakeries ask. We use QuickBooks and the NYC 2025 plan. Then Anna said yes.", brand="Sample Co")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(hint), "Sample Co, QuickBooks, NYC, 2025, Anna")

    def test_the_whole_script_is_never_the_hint(self):
        r, hint = self.run_it("Most small bakeries lose customers for one simple reason. They wait for orders. " * 20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(hint), "plain sentences give no hint")

    def test_the_hint_is_short_and_plain(self):
        r, hint = self.run_it(" ".join("Word%d QuickBooks%d" % (i, i) for i in range(200)), brand="A <b>x</b>")
        text = self.read(hint)
        self.assertLessEqual(len(text), 300)
        self.assertNotIn("<", text)

    def test_no_script_and_no_brand_means_no_hint_file(self):
        r, hint = self.run_it(None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(hint))


class WordsTest(Tmp):
    def test_clean_words_accepts_words_and_refuses_sentences(self):
        write_json(self.path("w.json"), [{"word": " " + w, "start": s, "end": e} for w, s, e in WORDS] + [{"word": "♪", "start": 6, "end": 7}])
        self.assertEqual(py("clean_words.py", self.path("w.json")).returncode, 0)
        out = load_json(self.path("w.json"))
        self.assertEqual([(w["text"], w["start"], w["end"]) for w in out], WORDS)
        write_json(self.path("s.json"), [{"text": "This is a real bakery's entire month of orders.", "start": 0.0, "end": 2.9},
                                         {"text": "She approved them with flour still on her hands.", "start": 3.4, "end": 5.8}])
        r = py("clean_words.py", self.path("s.json"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("look like sentences", r.stderr)


class PlanGuardTest(Tmp):
    def good(self):
        return {"duration": 8.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}, "cover_at": 6.5,
                "takeovers": [{"start": 2.5, "end": 6.0, "template": "tk-keyword", "fill": {"WORD": "GROW", "SUPPORT": "fast"}}],
                "caption_groups": [group(WORDS[0:4], 0), group(WORDS[4:9], 1), group(WORDS[9:12], 2), group(WORDS[12:18], 0)],
                "sfx": [{"t": 2.5, "name": "whoosh-deep", "gain": 0.5}]}

    def run_it(self, plan, dur="8.0"):
        write_json(self.path("plan.json"), plan)
        return py("plan_guard.py", self.path("plan.json"), dur)

    def test_a_good_plan_passes(self):
        r = self.run_it(self.good())
        self.assertIn("plan OK", r.stdout, r.stdout + r.stderr)

    def test_unsafe_or_invalid_plans_are_refused(self):
        cases = {}
        p = self.good(); p["takeovers"][0]["fill"]["WORD"] = "<img src=x onerror=alert(1)>"; cases["markup in a takeover"] = p
        p = self.good(); p["caption_groups"][0]["words"][0]["w"] = "</script>"; cases["markup in a caption"] = p
        p = self.good(); p["sfx"][0]["name"] = "../../etc/passwd"; cases["sfx path"] = p
        p = self.good(); p["brand"]["accent"] = "red;}"; cases["bad hex"] = p
        p = self.good(); p["takeovers"][0]["template"] = "tk-evil"; cases["unknown template"] = p
        p = self.good(); p["cover_at"] = 4.0; cases["cover inside a takeover"] = p
        for name, plan in cases.items():
            with self.subTest(name):
                r = self.run_it(plan)
                self.assertNotEqual(r.returncode, 0, name + " passed")
                self.assertNotIn("plan OK", r.stdout)

    def test_sfx_gain_above_the_block_limit_is_refused(self):
        p = self.good()
        p["sfx"][0]["gain"] = 0.6
        self.assertIn("plan OK", self.run_it(p).stdout)
        p["sfx"][0]["gain"] = 0.7
        self.assertNotEqual(self.run_it(p).returncode, 0, "b-reel-premium refuses a gain above 0.6")

    def test_typing_takeover_limits_follow_the_block_filler(self):
        def typing(**fill):
            p = self.good()
            p["takeovers"][0] = {"start": 2.5, "end": 6.0, "template": "tk-typing-ui", "fill": dict({"PROMPT": "write a haiku", "LABEL": "AI chat"}, **fill)}
            return p
        self.assertIn("plan OK", self.run_it(typing()).stdout)
        for name, fill in (("empty prompt", {"PROMPT": " "}), ("long label", {"LABEL": "x" * 61}),
                           ("speed", {"TYPING_SPEED": 9}), ("long prompt", {"PROMPT": "x" * 4001})):
            with self.subTest(name):
                self.assertNotEqual(self.run_it(typing(**fill)).returncode, 0)

    def test_an_address_in_takeover_text_is_refused(self):
        p = self.good()
        p["takeovers"][0]["fill"]["SUPPORT"] = "see https://x.example"
        r = self.run_it(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("web address", r.stderr)

    def test_the_accent_span_is_the_only_markup_allowed(self):
        p = self.good()
        p["takeovers"][0] = {"start": 2.5, "end": 6.0, "template": "tk-quote", "fill": {"QUOTE": 'Make it <span class="accent">pop</span>', "ATTR": "A"}}
        self.assertIn("plan OK", self.run_it(p).stdout)
        p["takeovers"][0]["fill"]["QUOTE"] = "Make it <b>pop</b>"
        self.assertNotEqual(self.run_it(p).returncode, 0)


if __name__ == "__main__":
    unittest.main()
