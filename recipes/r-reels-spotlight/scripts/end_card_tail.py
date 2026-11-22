#!/usr/bin/env python3
# usage: python3 scripts/end_card_tail.py BED.mp4 CTA_CARD(on|off) CTA_DURATION_SECONDS
# Hold the last frame with silence so the end card fits after the last spoken word.
import json, math, os, re, subprocess, sys
src, card, want = sys.argv[1], sys.argv[2], float(sys.argv[3])
MARGIN, MAX_TAIL = 0.5, 3.5   # speech end + cta_duration + MARGIN, tail at most MAX_TAIL
def dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)
if card != "on":
    print("[spotlight] end-card tail: cta_card off, no tail"); sys.exit(0)
# step 06 skips the card when the order has no CTA copy, so a tail would be dead air. Same rule
# as step 06 (scripts/cta_copy.py): inputs/cta/cta.json, else cta.md / cta.txt, else brief.json brand.cta.
# An unreadable file stops the step.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cta_copy
try:
    copy = cta_copy.resolve("inputs/cta", "brief.json")
except cta_copy.Bad as e:
    sys.exit("end-card tail: cannot read inputs/cta/cta.json or brief.json: %s" % e)
if not copy["text"]:
    print("[spotlight] end-card tail: the order has no CTA copy, so no end card and no tail"); sys.exit(0)
d = dur(src)
log = subprocess.run(["ffmpeg", "-hide_banner", "-protocol_whitelist", "file", "-i", src, "-af", "silencedetect=noise=-40dB:d=0.3", "-f", "null", "-"],
                     capture_output=True, text=True).stderr
starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", log)]
ends = [float(x) for x in re.findall(r"silence_end: (-?[0-9.]+)", log)]
speech_end = d                       # no silence runs to the end: the speech fills the clip
if starts and (len(ends) < len(starts) or ends[-1] >= d - 0.05):
    speech_end = max(0.0, starts[-1])
tail = math.ceil(max(0.0, min(want + MARGIN, MAX_TAIL) - (d - speech_end)) * 30) / 30
if tail <= 0:
    print("[spotlight] end-card tail: %.2fs of silence already follows the speech, no tail" % (d - speech_end)); sys.exit(0)
tmp = src[:-4] + "-tail.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-protocol_whitelist", "file", "-i", src, "-vf", "tpad=stop_mode=clone:stop_duration=%.3f" % tail,
                "-af", "apad=pad_dur=%.3f" % tail, "-c:v", "libx264", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", tmp], check=True)
got = dur(tmp)
if abs(got - (d + tail)) > 0.1:
    sys.exit("end-card tail: bed is %.3fs, expected %.3fs" % (got, d + tail))
os.replace(tmp, src)
print("[spotlight] end-card tail: speech ends %.2fs, held the last frame + silence for %.2fs (bed %.2fs)" % (speech_end, tail, got))
