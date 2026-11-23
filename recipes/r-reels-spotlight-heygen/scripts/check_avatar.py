#!/usr/bin/env python3
"""usage: python3 scripts/check_avatar.py VIDEO.mp4

Check the avatar video that step 00 downloaded, before it becomes `talking_head`. Exit 1 with one plain
line when it is not a decodable video, has no audio stream, is not portrait, or is not 20 to 60 seconds.
The 20 to 60 second window is the one `heygen_inputs.py` aims at with its 50 to 150 word range (150 words
a minute). A video outside it is a failure, not an ask: the paid render has already happened.
On success print `avatar WIDTHxHEIGHT SECONDSs` and exit 0. Starts only ffprobe, with an argument list.
"""
import json
import subprocess
import sys


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries",
                              "stream=codec_type,width,height:format=duration", "-of", "json", "-i", argv[1]],
                             capture_output=True, text=True)
        info = json.loads(out.stdout or "{}")
    except (OSError, ValueError):
        sys.exit("check_avatar: ffprobe is not available or gave no answer")
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if out.returncode != 0 or not video:
        sys.exit("check_avatar: the download is not a decodable video")
    if not any(s.get("codec_type") == "audio" for s in streams):
        sys.exit("check_avatar: the avatar video has no audio stream")
    try:
        dur = float((info.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        sys.exit("check_avatar: the video has no usable duration")
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if not h > w > 0:
        sys.exit("check_avatar: the video is %dx%d; this recipe needs a portrait render (9:16)" % (w, h))
    if not 20 <= dur <= 60:
        sys.exit("check_avatar: the video is %.1f s, outside 20 to 60 s; lengthen or shorten the script (a new paid render)" % dur)
    print("avatar %dx%d %.1fs" % (w, h, dur))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
