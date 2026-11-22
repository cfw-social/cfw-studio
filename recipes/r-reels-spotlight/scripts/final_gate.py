#!/usr/bin/env python3
"""usage (from the step work folder):
  python3 scripts/final_gate.py continuity prior/assembled_video.mp4
  python3 scripts/final_gate.py delivery work/final-scorecard.json work/acceptance.run.json VIDEO.mp4

continuity: the voice must be audible (a real mean volume, not -inf) under every takeover window
            of prior/edit_plan.json and every b-roll beat of prior/beat_list.json.
delivery:   VIDEO.mp4 is 1080x1920 and 20-65 s, and the final scorecard (written by
            `b-qa-gate/check.py --finalize`) agrees with itself, the spec and the file: finalized, verdict PASS,
            counts fail 0 / look 0 / pass = the number of rows, every row PASS (no FAIL row, no unanswered look),
            every check of the spec has a PASS row, and the recorded input hash and size match VIDEO.mp4. A
            scorecard is a record, not proof: this refuses one whose verdict alone was changed, not one that
            someone rewrote together with its file. Exit 1 on any failure.
"""
import hashlib
import json
import os
import subprocess
import sys

MAX_SECONDS = 65


def continuity(out):
    plan = json.load(open("prior/edit_plan.json", encoding="utf-8"))
    windows = [(float(t["start"]), float(t["end"])) for t in plan.get("takeovers", [])]
    if os.path.exists("prior/beat_list.json"):
        windows += [(float(b["start"]), float(b["end"]))
                    for b in json.load(open("prior/beat_list.json", encoding="utf-8"))["beats"] if b["kind"] == "broll"]
    bad = []
    for s, e in sorted(windows):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(s), "-t", str(e - s), "-protocol_whitelist", "file", "-i", out,
                            "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        line = next((l for l in r.stderr.splitlines() if "mean_volume" in l), "MISSING")
        print(f"window {s:.1f}-{e:.1f}s: {line.strip()}")
        if "MISSING" in line or "-inf" in line:
            bad.append((s, e))
    if bad:
        sys.exit("voice silent under takeover windows %s" % (bad,))


def delivery(scorecard, spec_path, video):
    """Check the video and the final scorecard together. A scorecard is a record, not proof: this does not stop
    someone who edits it AND the file it describes, but it refuses a card whose verdict alone was changed."""
    fail = []
    out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", video], capture_output=True, text=True)
    try:
        m = json.loads(out.stdout)
        w, h, d = m["streams"][0]["width"], m["streams"][0]["height"], float(m["format"]["duration"])
    except (ValueError, KeyError, IndexError, TypeError):
        sys.exit("DELIVERY GATE FAILURES:\n  x %s is not a readable video" % video)
    if (w, h) != (1080, 1920):
        fail.append(f"final dims {w}x{h} != 1080x1920")
    if not (20 <= d <= MAX_SECONDS):
        fail.append(f"duration {d:.1f}s outside 20-{MAX_SECONDS}s")
    try:
        with open(scorecard, encoding="utf-8") as fh:
            card = json.load(fh)
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError):
        card, spec = None, None
    if not isinstance(card, dict) or not isinstance(spec, dict):
        fail.append("final scorecard or spec missing or unreadable: run the QA gate and finalize it")
    else:
        fail += scorecard_problems(card, spec, video)
    if fail:
        print("DELIVERY GATE FAILURES:")
        for f in fail:
            print("  x", f)
        raise SystemExit(1)
    print("DELIVERY GATE PASSED")


def scorecard_problems(card, spec, video):
    """Everything the scorecard claims, checked against itself, the spec and the file."""
    bad = []
    rows = card.get("checks")
    if not card.get("finalized"):
        bad.append("scorecard is not finalized: answer the looks with check.py --finalize")
    if card.get("verdict") != "PASS":
        bad.append("QA gate verdict = %s" % card.get("verdict"))
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        return bad + ["the scorecard has no check rows"]
    counts = card.get("counts") if isinstance(card.get("counts"), dict) else {}
    if counts.get("fail") != 0 or counts.get("look") != 0 or counts.get("pass") != len(rows):
        bad.append("the scorecard counts do not match its rows (fail 0, look 0, pass %d expected; got %s)" % (len(rows), counts))
    for r in rows:
        if r.get("status") != "PASS":
            bad.append("row %s is %s, not PASS" % (r.get("id"), r.get("status")))
    ids = [str(r.get("id")) for r in rows]
    for c in spec.get("checks") or []:
        cid = c.get("id")
        if not isinstance(cid, str) or not any(i == cid or i.startswith(cid + ".") for i in ids):
            bad.append("the spec's check %s has no row in the scorecard" % cid)
    digest, size = hashlib.sha256(), 0
    with open(video, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    if card.get("input_sha256") != digest.hexdigest() or card.get("input_bytes") != size:
        bad.append("the scorecard was made for a different file than %s (hash or size differs)" % video)
    return bad


if __name__ == "__main__":
    if sys.argv[1:2] == ["continuity"] and len(sys.argv) == 3:
        continuity(sys.argv[2])
    elif sys.argv[1:2] == ["delivery"] and len(sys.argv) == 5:
        delivery(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        sys.exit(__doc__)
