#!/usr/bin/env python3
"""Read and check the three inputs of step 00 before anything is sent to the provider. Standard library only.

  python3 heygen_inputs.py            read the inputs, check them, write work/narration.txt and work/heygen.json
  python3 heygen_inputs.py --get KEY  print one value from work/heygen.json (avatar_id, voice_id or background)

Inputs, each a folder under inputs/ holding plain text (script.txt, script.md) or a JSON object with a
"text" key (script.json):
  inputs/script/     the narration the avatar will say; 50 to 150 words (about 20 to 60 seconds), at most 5000
                     characters. Plain prose: no stage directions and no markdown.
  inputs/avatar_id/  the provider's avatar id: 1 to 128 letters, digits, - or _
  inputs/voice_id/   the provider's voice id, same form
When an id folder is absent the brief's brand.heygen.avatarId / voiceId is used. This recipe ships no id.
The background is the brand's palette.bg (six hex digits) or 0F172A, written as #RRGGBB.

Order text is data: the narration goes to a file the provider script reads (never a shell string); the ids
are checked against the pattern above before the step puts them on a command line.
Exit 0 ready, 1 bad input or file (one plain line), 3 an input is missing or unusable: needs_input.json is
written (inputId, reason) and the step stops without calling the provider.
"""
import glob
import json
import os
import re
import sys

ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
HEX = re.compile(r"#?([0-9A-Fa-f]{6})")


def text_input(name):
    path = "inputs/%s/%s.json" % (name, name)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except ValueError:
            raise SystemExit("inputs/%s/%s.json is not valid JSON" % (name, name))
        return str(data.get("text") or "").strip() if isinstance(data, dict) else ""
    for p in sorted(glob.glob("inputs/%s/*" % name)):
        if p.endswith((".txt", ".md")) and os.path.isfile(p) and not os.path.islink(p):
            with open(p, encoding="utf-8") as fh:
                return fh.read().strip()
    return ""


def ask(input_id, reason):
    with open("needs_input.json", "w", encoding="utf-8") as fh:
        json.dump({"inputId": input_id, "reason": reason, "count": 1}, fh)
    print("asked for %s: see needs_input.json" % input_id)
    return 3


def get(key):
    try:
        with open("work/heygen.json", encoding="utf-8") as fh:
            print(json.load(fh)[key])
    except (OSError, ValueError, KeyError):
        sys.stderr.write("heygen_inputs.py: FAILED - work/heygen.json has no %s; run this script without --get first\n" % key)
        return 1
    return 0


def main(argv):
    if argv[:1] == ["--get"] and len(argv) == 2:
        return get(argv[1])
    if argv:
        sys.stderr.write("usage: heygen_inputs.py [--get KEY]\n")
        return 1
    try:
        with open("brief.json", encoding="utf-8") as fh:
            brief = json.load(fh)
        brand = brief.get("brand") if isinstance(brief, dict) and isinstance(brief.get("brand"), dict) else {}
        hg = brand.get("heygen") if isinstance(brand.get("heygen"), dict) else {}
        script = text_input("script")
        avatar = text_input("avatar_id") or str(hg.get("avatarId") or "").strip()
        voice = text_input("voice_id") or str(hg.get("voiceId") or "").strip()
    except (OSError, ValueError, SystemExit) as e:
        sys.stderr.write("heygen_inputs.py: FAILED - %s\n" % (e if isinstance(e, SystemExit) and isinstance(e.code, str) else "brief.json or an input cannot be read"))
        return 1
    if not script:
        return ask("script", "Please provide the narration script for the avatar to read.")
    words = len(script.split())
    if not 50 <= words <= 150 or len(script) > 5000:
        return ask("script", "The script is %d words. A 20 to 60 second reel needs about 50 to 150 words." % words)
    if not avatar:
        return ask("avatar_id", "No avatar is set for this brand. Please provide the avatar id to use.")
    if not voice:
        return ask("voice_id", "No voice is set for this brand. Please provide the voice id to use.")
    for name, value in (("avatar_id", avatar), ("voice_id", voice)):
        if not ID.fullmatch(value):
            return ask(name, "The %s is not a valid id (letters, digits, - and _ only, up to 128). Please check it." % name.replace("_", " "))
    pal = brand.get("palette") if isinstance(brand.get("palette"), dict) else {}
    m = HEX.fullmatch(str(pal.get("bg") or brand.get("bg") or "0F172A").strip())
    background = "#" + (m.group(1) if m else "0F172A").upper()
    os.makedirs("work", exist_ok=True)
    with open("work/narration.txt", "w", encoding="utf-8") as fh:
        fh.write(script + "\n")
    with open("work/heygen.json", "w", encoding="utf-8") as fh:
        json.dump({"avatar_id": avatar, "voice_id": voice, "background": background}, fh)
    print("inputs OK: %d words, background %s" % (words, background))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
