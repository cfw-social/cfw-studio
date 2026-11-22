#!/usr/bin/env python3
"""Fill the typing card template (templates/typing-scene.html) from a JSON text file.

  python3 typing_fill.py --out work/typing.html --duration 9.0 --text-file work/typing.json \
          --accent F97316 [--bg 0F172A] [--fg F8FAFC] [--prompt-size 44] [--speed 1.0] [--variant full|pip-safe] \
          [--wrap standalone|template] [--slot ID]

The text file is a JSON object. `prompt` is required; the rest are optional:

  {"prompt": "text to type", "label": "AI chat", "card_label": "The prompt", "bottom_tag": ""}

All text is escaped here, and no text reaches the page any other way. Exit 0 written,
2 bad input or unsafe path (nothing written), 1 an unexpected error (one fixed line, no stack trace), 3 the block's own template is missing or was
changed. Python standard library only. No network. Starts no other program.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill_common as fc  # noqa: E402

ANCHOR = '<template id="typing-scene-template">'
VARIANTS = ("full", "pip-safe")
KEYS = ("prompt", "label", "card_label", "bottom_tag")
LIMITS = {"prompt": 4000, "label": 60, "card_label": 60, "bottom_tag": 80}


DEFAULT_SIZE = {"full": 44, "pip-safe": 38}
BUBBLE_MAX = {"full": 1300, "pip-safe": 640}
SIZE_RANGE = (24, 72)


def estimate_fit(prompt, size, variant):
    """Rough count of lines the prompt needs and lines the box holds (mono letters are about 0.6 em wide)."""
    per_line = max(1, int(860 / (0.6 * size)))
    needed = sum(max(1, -(-len(line) // per_line)) for line in prompt.split("\n"))
    holds = max(1, int((BUBBLE_MAX[variant] - 56) / (size * 1.45)))
    return needed, holds


# The template's own timing (templates/typing-scene.html, function typingWindow): typing starts at 0.5 s (earlier in a very
# short clip), the whole prompt is on screen TYPING_HOLD seconds before the clip ends, and the typed window is
# duration * 0.88 / speed long, at least 0.5 s, and never later than the hold. The template always finishes the typing
# inside that window, however many characters there are, so a long prompt in a short beat is typed too fast to read.
# MAX_CHARS_PER_SECOND is this block's own limit on how fast that may be (about 6 words a second).
TYPING_START = 0.5
TYPING_HOLD = 0.6
MIN_WINDOW = 0.5
WINDOW_FRACTION = 0.88
MAX_CHARS_PER_SECOND = 30.0


def typing_window(duration, speed):
    """(start, end) of the typed window in seconds, exactly as the template computes it."""
    latest = max(0.0, duration - TYPING_HOLD)
    start = min(TYPING_START, latest / 2)
    end = max(start + MIN_WINDOW, duration * WINDOW_FRACTION / speed)
    end = min(end, latest)
    return start, max(end, start)


def typed_length(prompt):
    """The prompt's length as the page counts it (UTF-16 code units)."""
    return len(prompt.encode("utf-16-le")) // 2


def window_length(duration, speed):
    start, end = typing_window(duration, speed)
    return end - start


def check_typing_fits(prompt, duration, speed):
    """Raise FillError when the prompt would be typed faster than MAX_CHARS_PER_SECOND."""
    n = typed_length(prompt)
    need = n / MAX_CHARS_PER_SECOND
    if window_length(duration, speed) + 1e-9 >= need:
        return
    # smallest duration, in 0.1 s steps, whose window holds the prompt at this speed
    d = max(round((need + TYPING_START) * speed / WINDOW_FRACTION, 1), round(need + TYPING_START + TYPING_HOLD, 1))
    while window_length(d, speed) + 1e-9 < need:
        d = round(d + 0.1, 1)
    now = int(round(n / max(window_length(duration, speed), 0.001)))
    msg = ("the prompt (%d characters) cannot finish typing in %g s at --speed %g: it would be typed at about %d characters a second, "
           "and this block allows at most %d, with the whole prompt on screen for the last %g s. "
           "Fix it with a shorter prompt, or a longer beat (the minimum --duration for this prompt at --speed %g is %.1f s)"
           % (n, duration, speed, now, int(MAX_CHARS_PER_SECOND), TYPING_HOLD, speed, d))
    if duration - TYPING_HOLD - min(TYPING_START, max(0.0, duration - TYPING_HOLD) / 2) >= need:
        msg += ", or a lower --speed (this beat needs --speed %.2f or lower; a higher speed types faster)" % (WINDOW_FRACTION * duration / (need + TYPING_START))
    else:
        msg += "; no --speed can help at this length"
    raise fc.FillError(msg)


def fill(template, duration, text, accent, bg="0F172A", speed=1.0, variant="full", wrap="standalone", slot=None,
         fg="F8FAFC", prompt_size=None):
    """Return the filled page. `text` is the parsed JSON object."""
    unknown = sorted(set(text) - set(KEYS))
    if unknown:
        raise fc.FillError("unknown text key(s): %s" % ", ".join(unknown))
    if not isinstance(text.get("prompt"), str) or not text["prompt"].strip():
        raise fc.FillError("the prompt is empty; there is nothing to type")
    if variant not in VARIANTS:
        raise fc.FillError("variant %r is not one of %s" % (variant, ", ".join(VARIANTS)))
    if wrap not in ("standalone", "template"):
        raise fc.FillError("wrap must be standalone or template")
    accent = fc.hex6(accent, "accent")
    bg = fc.hex6(bg, "bg")
    fg = fc.hex6(fg, "fg")
    size = fc.number(DEFAULT_SIZE[variant] if prompt_size is None else prompt_size, "prompt-size", *SIZE_RANGE)
    card, bubble = fc.mix(bg, "000000", 80), fc.mix(bg, "FFFFFF", 96)
    fc.require_contrast([("fg on bg", fg, bg), ("fg on the card", fg, card), ("fg on the prompt box", fg, bubble)])
    slot = fc.slot_name(slot)
    bottom = text.get("bottom_tag", "")
    vals = {
        "DURATION": "%g" % fc.number(duration, "duration", 0.5, 300),
        "TYPING_SPEED": "%g" % fc.number(speed, "speed", 0.25, 4),
        "ACCENT": accent,
        "BG": bg,
        "FG": fg,
        "PROMPT_SIZE": "%g" % size,
        "BUBBLE_MAX": str(BUBBLE_MAX[variant]),
        "VARIANT": variant,
        "LABEL": fc.one_line(text.get("label") or "AI chat", "label", LIMITS["label"]),
        "CARD_LABEL": fc.one_line(text.get("card_label") or "The prompt", "card_label", LIMITS["card_label"]),
        "BOTTOM_TAG": fc.one_line(bottom, "bottom_tag", LIMITS["bottom_tag"]),
        "BOTTOM_TAG_DISPLAY": "" if bottom.strip() else "display:none",
        "PROMPT": fc.js_string_body(fc.multi_line(text["prompt"], "prompt", LIMITS["prompt"])),
    }
    check_typing_fits(text["prompt"], fc.number(duration, "duration", 0.5, 300), fc.number(speed, "speed", 0.25, 4))
    block = fc.cut_template(template, ANCHOR)
    if slot:
        # Rename on the bare template, before any text goes in, so text is never rewritten.
        block = fc.rename_slot(block, "typing-scene", "ts", slot)
    page = fc.one_pass(block, vals)
    return fc.standalone(fc.unwrap(page), bg) if wrap == "standalone" else page + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="Fill the typing card template from a JSON text file.")
    p.add_argument("--out", required=True, help="page to write; must be inside the work folder")
    p.add_argument("--duration", required=True, help="clip length in seconds")
    p.add_argument("--text-file", required=True, help="JSON file with prompt, label, card_label, bottom_tag")
    p.add_argument("--accent", required=True, help="six-digit hex colour")
    p.add_argument("--bg", default="0F172A", help="background colour, six hex digits")
    p.add_argument("--fg", default="F8FAFC", help="text colour, six hex digits; must have contrast 3.0 or more against the background")
    p.add_argument("--prompt-size", default=None, help="prompt text size in pixels, 24 to 72 (default 44, or 38 for pip-safe)")
    p.add_argument("--speed", default="1.0", help="typing speed multiplier, 0.25 to 4")
    p.add_argument("--variant", default="full", choices=VARIANTS)
    p.add_argument("--wrap", default="standalone", choices=("standalone", "template"))
    p.add_argument("--slot", default=None, help="give the scene its own id so several can share one page")
    a = p.parse_args(argv)
    try:
        text = fc.load_text_json(a.text_file, KEYS, ("prompt",))
        page = fill(fc.read_template("typing-scene.html"), a.duration, text, a.accent, a.bg, a.speed, a.variant, a.wrap, a.slot, a.fg, a.prompt_size)
        fc.write_in_work(a.out, page, inputs=(a.text_file,))
    except fc.FillError as e:
        sys.stderr.write("typing_fill.py: FAILED - %s\n" % e)
        return e.code
    print("typing card written: %s" % a.out)
    size = float(a.prompt_size) if a.prompt_size is not None else DEFAULT_SIZE[a.variant]
    needed, holds = estimate_fit(text["prompt"], size, a.variant)
    if needed > holds:
        fc.note("typing_fill.py: note - the prompt needs about %d lines and the box holds about %d; the end will be cut off. Shorten the prompt or lower --prompt-size" % (needed, holds))
    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(a.out)), "gsap.min.js")):
        fc.note("typing_fill.py: note - gsap.min.js is not beside the page yet; put the pinned copy from b-hyperframes there before rendering")
    return 0


if __name__ == "__main__":
    sys.exit(fc.run_main(main))
