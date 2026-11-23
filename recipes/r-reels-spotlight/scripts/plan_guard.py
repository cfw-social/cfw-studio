#!/usr/bin/env python3
"""usage: python3 scripts/plan_guard.py PLAN.json BED_DURATION_SECONDS [WORDS.json]

The mechanical guard for edit_plan.json. Prints `plan OK` or exits non-zero with the reason.
Every check is an explicit test that exits non-zero, never an `assert`, so `python -O` cannot switch it off.
Beyond timing and shape, it refuses anything that could turn text into markup or a file path: the takeover
template must be one of the five fixed names, each template accepts only its own fill keys, caption words and
takeover text may not contain angle brackets (except the one allowed <span class="accent"> wrapper in TITLE
and QUOTE) or a web address, and sfx names must be in the fixed list. Steps 03 and 05 both run it.
"""
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import page_text  # noqa: E402

SFX_NAMES = {"whoosh-deep", "whoosh-air", "impact-sub", "impact-punch", "riser", "click", "pop", "swipe"}
FILL_KEYS = {
    "tk-stat": ("EYEBROW", "STAT", "LABEL"),
    "tk-keyword": ("WORD", "SUPPORT"),
    "tk-list": ("TITLE", "ITEM1", "ITEM2", "ITEM3"),
    "tk-quote": ("QUOTE", "ATTR"),
    "tk-typing-ui": ("PROMPT", "LABEL", "CARD_LABEL", "BOTTOM_TAG", "TYPING_SPEED"),
}
ACCENT_SPAN = re.compile(r'</?span(?: class="accent")?>')
TYPING_LIMITS = {"PROMPT": 4000, "LABEL": 60, "CARD_LABEL": 60, "BOTTOM_TAG": 80}   # the b-typing-ui filler's limits


def need(ok, why):
    if not ok:
        sys.exit("plan_guard: " + why)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def main(argv):
    need(len(argv) in (3, 4), "usage: plan_guard.py PLAN.json BED_DURATION_SECONDS [WORDS.json]")
    plan_path = argv[1]
    try:
        dur = float(argv[2])
    except ValueError:
        sys.exit("plan_guard: the bed duration must be a number")
    need(math.isfinite(dur) and dur > 0, "the bed duration must be above 0")
    words_path = argv[3] if len(argv) > 3 else None
    try:
        with open(plan_path, encoding="utf-8") as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        sys.exit("plan_guard: the plan is not readable JSON")
    need(isinstance(p, dict), "the plan must be a JSON object")
    groups = p.get("caption_groups")
    need(isinstance(groups, list) and groups, "no caption groups")
    for g in groups:
        need(isinstance(g, dict) and is_num(g.get("start")) and is_num(g.get("end")) and isinstance(g.get("words"), list) and g["words"],
             "every caption group needs start, end and words")
    # The bed ends in a silent end-card tail (at most 3.5 s), so allow 4.5 s.
    need(abs(groups[-1]["end"] - dur) < 4.5, "captions do not cover the bed")
    need(not re.search(r"[ऀ-ॿ]", json.dumps(p, ensure_ascii=False)), "Devanagari in plan: Latin script only")
    brand = p.get("brand")
    need(isinstance(brand, dict), "brand must be an object")
    for k in ("bg", "accent", "fg"):
        need(isinstance(brand.get(k), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", brand[k]) is not None, "brand.%s must be a single-# 6-digit hex" % k)
    tks = p.get("takeovers", [])
    need(isinstance(tks, list), "takeovers must be a list")
    for n, tk in enumerate(tks):
        need(isinstance(tk, dict), "takeover %d is not an object" % n)
        need(isinstance(tk.get("template"), str) and tk["template"] in FILL_KEYS, "unknown takeover template %r" % (tk.get("template"),))
        need(is_num(tk.get("start")) and is_num(tk.get("end")), "takeover %d needs numeric start and end" % n)
        need(2.5 <= tk["end"] - tk["start"] <= 7, "bad takeover window %s" % tk)
        fill = tk.get("fill")
        need(isinstance(fill, dict), "takeover %d has no fill object" % n)
        extra = sorted(set(fill) - set(FILL_KEYS[tk["template"]]))
        need(not extra, "takeover %d (%s) has fill keys it does not read: %s" % (n, tk["template"], ", ".join(map(str, extra))))
        for key, val in fill.items():
            need(isinstance(val, (str, int, float)) and not isinstance(val, bool), "takeover %d %s must be text or a number" % (n, key))
            if not isinstance(val, str):
                continue
            rest = ACCENT_SPAN.sub("", val) if key in ("TITLE", "QUOTE") else val
            need("<" not in rest and ">" not in rest, "takeover %s holds markup; only the accent span is allowed" % key)
            try:
                page_text.refuse_addresses(val, "takeover %d %s" % (n, key))
            except ValueError as exc:
                sys.exit("plan_guard: %s" % exc)
        if tk["template"] == "tk-typing-ui":
            need(isinstance(fill.get("PROMPT"), str) and fill["PROMPT"].strip(), "tk-typing-ui needs a PROMPT")
            for key, limit in TYPING_LIMITS.items():
                if key in fill:
                    need(isinstance(fill[key], str) and len(fill[key]) <= limit, "tk-typing-ui %s is over %d characters" % (key, limit))
            try:
                speed = float(fill.get("TYPING_SPEED", 1.0))
            except (TypeError, ValueError):
                speed = -1.0
            need(0.25 <= speed <= 4, "tk-typing-ui TYPING_SPEED must be a number from 0.25 to 4")
    for a, b in zip(tks, tks[1:]):
        need(b["start"] - a["end"] >= 4, "<4s of speaker between takeovers %s -> %s" % (a["end"], b["start"]))
        need(a["template"] != b["template"], "same template twice in a row")
    need(all(tk["end"] <= dur - 2 for tk in tks), "takeover inside the final 2s")
    cover = p.get("cover_at", dur * 0.4)
    need(is_num(cover), "cover_at must be a number")
    cover_t = float(cover)
    need(cover_t >= 2.0, "cover_at=%s is inside the hook: it must be >= 2s" % cover_t)
    need(not any(tk["start"] <= cover_t <= tk["end"] for tk in tks), "cover_at falls inside a takeover")
    for g in groups:
        for w in g["words"]:
            need(isinstance(w, dict) and "w" in w, "every caption word needs a w")
        need(sum(1 for w in g["words"] if w.get("em")) <= 1, "more than one emphasis word in a group")
        for w in g["words"]:
            need(not re.search(r"[<>]", str(w["w"])), "a caption word holds an angle bracket")
    sfx = p.get("sfx", [])
    need(isinstance(sfx, list) and len(sfx) <= 12, "more than 12 sfx cues")
    for c in sfx:
        need(isinstance(c, dict) and c.get("name") in SFX_NAMES, "unknown sfx name %r" % (c.get("name") if isinstance(c, dict) else c,))
        gain = c.get("gain", 0.5)
        need(is_num(gain) and 0 <= gain <= 0.6, "sfx gain out of range (0 to 0.6)")
        need(is_num(c.get("t")) and 0 <= c["t"] <= dur, "sfx cue outside the bed")
    need(subprocess.run([sys.executable, os.path.join(HERE, "caption_phrases.py"), "--check", plan_path]).returncode == 0,
         "a caption group splits a phrase mid-clause: run python3 scripts/caption_phrases.py work/edit_plan.json")
    if words_path:
        need(subprocess.run([sys.executable, os.path.join(HERE, "takeover_brand.py"), "--check", plan_path, words_path]).returncode == 0,
             "takeover text names a brand the order does not own: run python3 scripts/takeover_brand.py PLAN WORDS")
    print("plan OK: %d groups, %d takeovers, %d sfx, cover_at=%ss" % (len(groups), len(tks), len(sfx), cover_t))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
