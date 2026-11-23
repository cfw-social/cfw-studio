#!/usr/bin/env python3
"""Measure the FORMAT of a reference reel and write format.json (numbers and labels only).

  python3 measure_format.py --input-dir inputs/reference_reel --words ref/words.json --out saves/format.json
                            [--scene-threshold 0.30] [--hook-type question|claim|stat|story|other]

Length and size come from ffprobe. Cuts come from ffmpeg scene detection. Pace and beats come from
the word timings: the speech is cut into sentences (end punctuation, or a pause of 0.8 s or more),
very short sentences are joined to a neighbour, then the first sentence is the hook, the last is
the call to action, and the sentences between are grouped into points. format.json holds no
transcript text: the output is checked against a fixed list of keys and labels before it is written.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from format_schema import HOOK_TYPES, validate_format  # noqa: E402
from rs_common import (Stop, main, need_tools, normalize, number, probe, resolve, run as run_tool,  # noqa: E402
                       single_video, timed_words, work_root, write_json)

MIN_WORDS = 15
PAUSE_S = 0.8
QUESTION_WORDS = ("what", "why", "how", "who", "when", "where", "which")
STORY_WORDS = ("i", "my", "we", "our", "last", "yesterday", "once", "when")
NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred",
                "thousand", "million", "percent")


def cut_times(path, threshold, duration):
    vf = "scale=320:-2,select='gt(scene,%.3f)',showinfo" % threshold
    p = run_tool(["ffmpeg", "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-i", path,
                  "-an", "-vf", vf, "-f", "null", "-"], 900)
    if p.returncode != 0:
        raise Stop("scene detection failed", 1)
    times = [float(m) for m in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", p.stderr)]
    return sorted({round(t, 1) for t in times if 0.2 <= t < duration - 0.2})


def sentences(words):
    """Index ranges (first, last) of sentences. Short ones (under 3 words) join a neighbour."""
    out, start = [], 0
    for i, w in enumerate(words):
        end_mark = re.search(r"[.?!]['\")\]]*$", w["text"].strip()) is not None
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 0
        if i + 1 == len(words) or end_mark or gap >= PAUSE_S:
            out.append([start, i])
            start = i + 1
    merged = []
    for s in out:
        if merged and (s[1] - s[0] + 1 < 3 or merged[-1][1] - merged[-1][0] + 1 < 3):
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return merged


def hook_type(words, first):
    text = " ".join(w["text"] for w in words[first[0]:first[1] + 1])
    toks = normalize(text)
    if text.rstrip("\"')] ").endswith("?"):
        return "question"
    if any(t.isdigit() for t in toks) or any(t in NUMBER_WORDS for t in toks) or "%" in text:
        return "stat"
    if toks and toks[0] in STORY_WORDS:
        return "story"
    return "claim"


def make_beats(words, sents):
    k = len(sents)
    if k == 1:
        groups, labels = [sents[0]], ["hook"]
    elif k == 2:
        groups, labels = [sents[0], sents[1]], ["hook", "cta"]
    else:
        middle = sents[1:-1]
        points = min(5, max(1, round(len(middle) / 2)))
        size, extra = divmod(len(middle), points)
        groups, labels, at = [sents[0]], ["hook"], 0
        for p in range(points):
            n = size + (1 if p < extra else 0)
            part = middle[at:at + n]
            at += n
            groups.append([part[0][0], part[-1][1]])
            labels.append("point_%d" % (p + 1))
        groups.append(sents[-1])
        labels.append("cta")
    span_start, span_end = words[0]["start"], words[-1]["end"]
    span = max(span_end - span_start, 1e-6)
    beats = []
    for n, (g, label) in enumerate(zip(groups, labels)):
        start = words[g[0]]["start"]
        end = words[groups[n + 1][0]]["start"] if n + 1 < len(groups) else span_end
        beats.append({"label": label, "start_s": round(start, 2), "end_s": round(end, 2),
                      "share": round((end - start) / span, 2), "words": g[1] - g[0] + 1})
    points = sum(1 for b in beats if b["label"].startswith("point_"))
    parts = ["hook"] + (["%d point%s" % (points, "" if points == 1 else "s")] if points else []) \
        + (["cta"] if any(b["label"] == "cta" for b in beats) else [])
    return beats, ", ".join(parts)


def run(argv):
    ap = argparse.ArgumentParser(prog="measure_format.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--input-dir", required=True, help="folder holding the one reference video")
    ap.add_argument("--words", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scene-threshold", default="0.30")
    ap.add_argument("--hook-type", choices=HOOK_TYPES)
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    thr = number(a.scene_threshold, "--scene-threshold", 0.05, 0.9)
    root = work_root(a.workdir)
    need_tools("ffmpeg", "ffprobe")
    video = single_video(root, a.input_dir)
    out = resolve(root, a.out)
    if os.path.abspath(out) in (os.path.abspath(video), os.path.abspath(resolve(root, a.words))):
        raise Stop("--out must not be an input file")
    words = timed_words(root, a.words)
    if len(words) < MIN_WORDS:
        raise Stop("fewer than %d words in the transcript; the reel may be music only" % MIN_WORDS, 1)
    info = probe(video)
    if not info["has_video"] or info["width"] <= 0 or info["height"] <= 0:
        raise Stop("the reference has no picture", 1)
    dur = info["duration"]
    cuts = cut_times(video, thr, dur)
    span = words[-1]["end"] - words[0]["start"]
    if span <= 0:
        raise Stop("the word times have no length", 1)
    sents = sentences(words)
    beats, structure = make_beats(words, sents)
    w, h = info["width"], info["height"]
    fmt = {
        "format_version": 1,
        "duration_s": round(dur, 2), "width": w, "height": h,
        "orientation": "portrait" if h > w * 1.1 else ("landscape" if w > h * 1.1 else "square"),
        "fps": round(info["fps"], 2),
        "speech_span_s": round(span, 2), "first_word_at_s": round(words[0]["start"], 2),
        "word_count": len(words), "wpm": round(len(words) / (span / 60.0), 2),
        "speech_share": round(min(1.0, span / dur), 2),
        "cut_count": len(cuts), "cuts_per_10s": round(len(cuts) / dur * 10.0, 2),
        "mean_shot_s": round(dur / (len(cuts) + 1), 2),
        "scene_threshold": round(thr, 2), "cut_times_s": cuts,
        "hook": {"type": a.hook_type or hook_type(words, sents[0]),
                 "type_source": "given" if a.hook_type else "rules",
                 "seconds": beats[0]["end_s"] - beats[0]["start_s"] if len(beats) > 1 else round(span, 2)},
        "beats": beats, "structure": structure,
    }
    fmt["hook"]["seconds"] = round(fmt["hook"]["seconds"], 2)
    validate_format(fmt)
    write_json(root, a.out, fmt)
    print("FORMAT: %s, %.1f s, %.0f words a minute, %.1f cuts per 10 s -> %s"
          % (structure, dur, fmt["wpm"], fmt["cuts_per_10s"], a.out))
    return 0


if __name__ == "__main__":
    main(run)
