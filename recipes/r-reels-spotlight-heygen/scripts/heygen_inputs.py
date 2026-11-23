#!/usr/bin/env python3
"""usage (from the step work folder): python3 scripts/heygen_inputs.py [BRIEF.json]

Check what step 00 needs BEFORE anything is sent or paid for, and print ONE line:

  AVATAR_ID VOICE_ID SCRIPT_FILE

- SCRIPT_FILE is `inputs/script/script.txt` or `inputs/script/script.md` (exactly one of them, a plain
  file, not a link), UTF-8 text of 50 to 150 words and at most 5000 characters (b-heygen's own cap). The
  word range is the one the gate's `script_timed_20_60s` check uses: at 150 words a minute, 50 words is 20 s
  and 150 words is 60 s, which is the window `check_avatar.py` enforces on the video.
- The avatar id is the first line of `inputs/avatar_id/avatar_id.txt`, else `brief.json`
  `brand.heygen.avatarId`; the voice id is the same with `voice_id`. This recipe ships none: they come from
  the person, and must belong to the brand and to a person who agreed. An id is 1 to 128 letters, digits,
  `-` or `_` (b-heygen's rule).

A missing or invalid input before the render is a question for the person, not a failure: the script writes
`needs_input.json` in the work folder (through a temporary file; a link there is refused, exit 2), `{"inputId", "reason", "count": 1}` (the reason in plain words, with
no path and no secret), prints the same reason on standard error and exits 1. A file it cannot read as UTF-8 is a one-line
error and exit 2. The step then stops without
sending anything. This script reads no key and starts no program. The script text is data: it is never put
in a shell command.
"""
import json
import os
import re
import sys
import tempfile

ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
MAX_CHARS = 5000
MIN_WORDS, MAX_WORDS = 50, 150


def fail(message, code=2):
    sys.stderr.write("heygen_inputs: %s\n" % message)
    sys.exit(code)


def ask(input_id, reason):
    """Write needs_input.json and stop: the person has to supply or fix this input.

    The file is written through a fresh temporary file in the work folder and moved into place; a
    needs_input.json that is a link or a folder is refused (exit 2), never written through."""
    target = "needs_input.json"
    if os.path.islink(target) or os.path.isdir(target):
        fail("needs_input.json is a link or a folder; remove it first")
    fd, tmp = tempfile.mkstemp(dir=".", prefix=".needs-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"inputId": input_id, "reason": reason, "count": 1}, fh)
        os.replace(tmp, target)
        tmp = None
    finally:
        if tmp is not None and os.path.lexists(tmp):
            os.unlink(tmp)
    sys.stderr.write("heygen_inputs: %s\n" % reason)
    sys.exit(1)


def plain_file(path):
    return not os.path.islink(path) and os.path.isfile(path)


def script_file():
    found = [p for p in ("inputs/script/script.txt", "inputs/script/script.md") if os.path.lexists(p)]
    if not found:
        ask("script", "Please provide the narration script for the avatar to read.")
    if len(found) > 1:
        ask("script", "Two narration files were supplied; please keep just one.")
    path = found[0]
    if not plain_file(path):
        ask("script", "The narration must be a plain text file.")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        ask("script", "The narration could not be read as plain text.")
    words = len(text.split())
    if not text.strip():
        ask("script", "The narration is empty; please provide the script for the avatar to read.")
    if len(text) > MAX_CHARS:
        ask("script", "The narration is too long (%d characters; the limit is %d)." % (len(text), MAX_CHARS))
    if not MIN_WORDS <= words <= MAX_WORDS:
        ask("script", "The narration is %d words; a 20 to 60 second reel needs about %d to %d." % (words, MIN_WORDS, MAX_WORDS))
    return path


def an_id(name, brief_key, brief, label):
    path = "inputs/%s/%s.txt" % (name, name)
    value = ""
    if os.path.lexists(path):
        if not plain_file(path):
            ask(name, "The %s must be a plain text file." % label)
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().strip().splitlines()
        except (OSError, UnicodeDecodeError):
            fail("%s is not readable UTF-8 text" % path)
        value = lines[0].strip() if lines else ""
    elif isinstance(brief, dict):
        heygen = (brief.get("brand") or {}).get("heygen") if isinstance(brief.get("brand"), dict) else None
        value = str(heygen.get(brief_key) or "").strip() if isinstance(heygen, dict) else ""
    if not value:
        ask(name, "No %s is set for this brand; please provide the brand's own %s." % (label, label))
    if not ID.fullmatch(value):
        ask(name, "The %s is not valid (1 to 128 letters, digits, - or _); please check it." % label)
    return value


def main(argv):
    brief_path = argv[1] if len(argv) > 1 else "brief.json"
    try:
        with open(brief_path, encoding="utf-8") as fh:
            brief = json.load(fh)
    except (OSError, ValueError):
        brief = {}
    script = script_file()
    print(an_id("avatar_id", "avatarId", brief, "HeyGen avatar id"), an_id("voice_id", "voiceId", brief, "HeyGen voice id"), script)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
